from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import os
import re
from html import escape
from pathlib import Path, PureWindowsPath
from urllib.parse import urlsplit


SCRIPT_DIR = Path(__file__).resolve().parent

def _load_module(module_name: str):
    module_path = SCRIPT_DIR / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"failed to load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ticker_display(row: dict[str, str]) -> str:
    display_module = _load_module("ticker_display")
    return display_module.ticker_display(row)


SUMMARY_SECTIONS = [
    ("市场技术面", "market_report_summary"),
    ("情绪面", "sentiment_report_summary"),
    ("新闻与宏观", "news_report_summary"),
    ("基本面", "fundamentals_report_summary"),
    ("多头观点", "bull_case_summary"),
    ("空头观点", "bear_case_summary"),
    ("研究经理", "research_manager_summary"),
    ("交易计划", "trader_plan_summary"),
    ("激进风险", "risk_aggressive_summary"),
    ("保守风险", "risk_conservative_summary"),
    ("中性风险", "risk_neutral_summary"),
    ("组合经理", "portfolio_manager_summary"),
]


def _read_rows(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        return []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _json_list(value: str) -> list[str]:
    if not value:
        return []
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return [value]
    if isinstance(payload, list):
        return [str(item) for item in payload if str(item)]
    return [str(payload)] if payload else []


def _link_path(path_text: str, base_dir: Path) -> str:
    if not path_text:
        return ""
    parsed = urlsplit(path_text)
    if parsed.netloc:
        return ""
    if parsed.scheme and not re.match(r"^[A-Za-z]$", parsed.scheme):
        return ""
    path = Path(path_text)
    try:
        if re.match(r"^[A-Za-z]:[\\/]", path_text):
            try:
                link = os.path.relpath(PureWindowsPath(path_text), base_dir)
            except ValueError:
                link = path_text
        elif path.is_absolute():
            link = os.path.relpath(path, base_dir)
        else:
            link = path_text
    except ValueError:
        return ""
    return escape(link.replace("\\", "/"), quote=True)



def _html(value: object) -> str:
    return escape(str(value or ""), quote=True)


def _anchor_id(prefix: str, *parts: object) -> str:
    raw = "-".join(str(part or "") for part in parts if str(part or ""))
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", raw).strip("-_").lower()
    return f"{prefix}-{safe}" if safe else prefix


def _decision_anchor(row: dict[str, str], index: int) -> str:
    return _anchor_id(
        "decision",
        row.get("ticker", ""),
        row.get("analysis_date", ""),
        row.get("run_id", "") or index,
    )


def _ticker_anchor(row: dict[str, str]) -> str:
    return _anchor_id("ticker", row.get("ticker", ""))



def _timeline_dates(rows: list[dict[str, str]]) -> list[str]:
    return sorted({row.get("analysis_date", "") for row in rows if row.get("analysis_date", "")})



def _confidence_score(value: str) -> float | None:
    normalized = value.strip().upper()
    if not normalized:
        return None
    raw = value.strip()
    buckets = {
        "LOW": 0.25,
        "MEDIUM": 0.5,
        "MID": 0.5,
        "HIGH": 0.85,
        "低": 0.25,
        "低置信度": 0.25,
        "低-中": 0.35,
        "低至中等": 0.35,
        "中低": 0.35,
        "中等偏低": 0.4,
        "中": 0.5,
        "中等": 0.5,
        "中等偏上": 0.65,
        "中偏高": 0.65,
        "中高": 0.65,
        "中等偏高": 0.7,
        "高": 0.85,
    }
    if raw in buckets:
        return buckets[raw]
    if normalized in buckets:
        return buckets[normalized]
    try:
        if normalized.endswith("%"):
            return float(normalized[:-1]) / 100
        score = float(normalized)
    except ValueError:
        return None
    if score > 1:
        score = score / 100
    return max(0, min(score, 1))


def _ticker_rows(rows: list[dict[str, str]]) -> list[tuple[str, str]]:
    display_by_ticker: dict[str, str] = {}
    for row in rows:
        ticker = row.get("ticker", "")
        if ticker and ticker not in display_by_ticker:
            display_by_ticker[ticker] = _ticker_display(row)
    return sorted(display_by_ticker.items(), key=lambda item: item[0])



def _row_by_ticker_date(rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    indexed: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        ticker = row.get("ticker", "")
        analysis_date = row.get("analysis_date", "")
        if ticker and analysis_date:
            indexed[(ticker, analysis_date)] = row
    return indexed



def _normalize_action(action: str) -> str:
    raw = action or ""
    normalized = raw.strip().upper()
    if "STRONG BUY" in normalized or "强烈买入" in raw:
        return "STRONG_BUY"
    if "STRONG SELL" in normalized or "强烈卖出" in raw:
        return "STRONG_SELL"
    if any(token in normalized for token in ["SELL", "UNDERWEIGHT", "REDUCE", "TRIM"]) or any(token in raw for token in ["卖出", "做空", "减持", "减仓", "减配", "低配", "降仓"]):
        return "SELL"
    if any(token in normalized for token in ["BUY", "OVERWEIGHT", "ACCUMULATE", "ADD"]) or any(token in raw for token in ["买入", "做多", "增持", "加仓", "超配"]):
        return "BUY"
    if any(token in normalized for token in ["HOLD", "WATCH", "WAIT", "NEUTRAL"]) or any(token in raw for token in ["持有", "观望", "等待", "中性"]):
        return "HOLD"
    return "UNKNOWN"


def _normalize_direction(direction: str) -> str:
    raw = direction or ""
    normalized = raw.strip().upper()
    if any(token in normalized for token in ["CAUTIOUS SHORT", "SLIGHT SHORT"]) or any(token in raw for token in ["谨慎看空", "谨慎偏空", "中性偏空", "中性偏谨慎", "偏空"]):
        return "SLIGHT_SHORT"
    if any(token in normalized for token in ["SHORT", "UNDERWEIGHT"]) or any(token in raw for token in ["看空", "看跌", "做空", "空头", "下跌", "下行", "卖出", "减配"]):
        return "SHORT"
    if any(token in normalized for token in ["CAUTIOUS LONG", "SLIGHT LONG"]) or any(token in raw for token in ["谨慎看多", "谨慎偏多", "中性偏多", "偏多"]):
        return "SLIGHT_LONG"
    if "LONG" in normalized or any(token in raw for token in ["看多", "做多", "多头", "上行", "增持", "超配"]):
        return "LONG"
    if "NEUTRAL" in normalized or any(token in raw for token in ["中性", "震荡", "横盘"]):
        return "NEUTRAL"
    return "UNKNOWN"


def _action_label(action: str) -> str:
    return {
        "STRONG_BUY": "强烈买入(+1.5)",
        "BUY": "买入/增持(+1)",
        "STRONG_SELL": "强烈卖出(-1.5)",
        "SELL": "卖出/减持(-1)",
        "HOLD": "持有/观望(0)",
        "NEUTRAL": "中性(0)",
    }.get(_normalize_action(action), "未知")


def _direction_label(direction: str) -> str:
    return {
        "LONG": "看多(+1)",
        "SLIGHT_LONG": "谨慎/偏多(+0.5)",
        "NEUTRAL": "中性(0)",
        "SLIGHT_SHORT": "谨慎/偏空(-0.5)",
        "SHORT": "看空(-1)",
    }.get(_normalize_direction(direction), "未知")


def _action_score(action: str) -> float | None:
    return {
        "STRONG_BUY": 1.5,
        "BUY": 1.0,
        "STRONG_SELL": -1.5,
        "SELL": -1.0,
        "HOLD": 0.0,
        "NEUTRAL": 0.0,
    }.get(_normalize_action(action))


def _direction_score(direction: str) -> float | None:
    return {
        "LONG": 1.0,
        "SLIGHT_LONG": 0.5,
        "NEUTRAL": 0.0,
        "SLIGHT_SHORT": -0.5,
        "SHORT": -1.0,
    }.get(_normalize_direction(direction))


def _signal_score(row: dict[str, str]) -> float | None:
    scores = [
        score
        for score in [_action_score(row.get("final_action", "")), _direction_score(row.get("direction", ""))]
        if score is not None
    ]
    if not scores:
        return None
    return sum(scores)


def _signal_text(score: float | None) -> str:
    if score is None:
        return "-"
    return f"{score:+.1f}"


def _action_class(action: str) -> str:
    return {
        "STRONG_BUY": "action-buy",
        "BUY": "action-buy",
        "STRONG_SELL": "action-sell",
        "SELL": "action-sell",
        "HOLD": "action-hold",
        "NEUTRAL": "action-neutral",
    }.get(_normalize_action(action), "action-unknown")


def _badge_class(action: str) -> str:
    return {
        "STRONG_BUY": "badge-buy",
        "BUY": "badge-buy",
        "STRONG_SELL": "badge-sell",
        "SELL": "badge-sell",
        "HOLD": "badge-hold",
        "NEUTRAL": "badge-neutral",
    }.get(_normalize_action(action), "badge-neutral")


def _confidence_class(score: float | None) -> str:
    if score is None:
        return "confidence-unknown"
    if score >= 0.7:
        return "confidence-high"
    if score >= 0.4:
        return "confidence-medium"
    return "confidence-low"


def _confidence_point_kind(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= 0.7:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"


def _star_points(cx: float, cy: float, outer_radius: float = 7.0, inner_radius: float = 3.1) -> str:
    points = []
    for index in range(10):
        radius = outer_radius if index % 2 == 0 else inner_radius
        angle = -math.pi / 2 + index * math.pi / 5
        points.append(f"{cx + math.cos(angle) * radius:.1f},{cy + math.sin(angle) * radius:.1f}")
    return " ".join(points)


def _triangle_points(cx: float, cy: float, radius: float = 6.5) -> str:
    return " ".join(
        f"{cx + math.cos(-math.pi / 2 + index * 2 * math.pi / 3) * radius:.1f},{cy + math.sin(-math.pi / 2 + index * 2 * math.pi / 3) * radius:.1f}"
        for index in range(3)
    )


def _confidence_point_markup(x: float, y: float, score: float | None, title: str, color_class: str) -> str:
    kind = _confidence_point_kind(score)
    title_markup = f"<title>{_html(title)}</title>"
    if kind == "high":
        return f'<polygon class="line-point line-point-star {color_class}" points="{_star_points(x, y)}">{title_markup}</polygon>'
    if kind == "medium":
        return f'<polygon class="line-point line-point-triangle {color_class}" points="{_triangle_points(x, y)}">{title_markup}</polygon>'
    if kind == "low":
        return f'<circle class="line-point line-point-circle {color_class}" cx="{x:.1f}" cy="{y:.1f}" r="4.0">{title_markup}</circle>'
    return f'<circle class="line-point line-point-hollow {color_class}" cx="{x:.1f}" cy="{y:.1f}" r="4.6">{title_markup}</circle>'


def _confidence_text(value: str) -> str:
    score = _confidence_score(value)
    if score is None:
        return "-"
    return f"{round(score * 100):.0f}%"



MAX_SIGNAL_LINE_SERIES = 4


def _signal_color_class(score: float | None) -> str:
    if score is None:
        return "signal-neutral"
    if score > 0:
        return "signal-positive"
    if score < 0:
        return "signal-negative"
    return "signal-neutral"



def _render_signal_line_chart(rows: list[dict[str, str]]) -> str:
    dates = _timeline_dates(rows)
    ticker_rows = _ticker_rows(rows)
    row_lookup = _row_by_ticker_date(rows)

    if not dates or not ticker_rows:
        return """
        <section class="chart-card">
            <h3>动作方向折线图</h3>
            <p class="empty-chart">暂无数据</p>
        </section>"""

    width = max(360, 92 + 72 * max(len(dates) - 1, 1))
    height = 240
    left = 52
    right = 16
    top = 18
    bottom = 44
    plot_width = width - left - right
    plot_height = height - top - bottom
    x_step = plot_width / max(len(dates) - 1, 1)

    def x_at(index: int) -> float:
        return left + index * x_step

    def y_at(score: float) -> float:
        return top + ((2.5 - score) / 5) * plot_height

    grid_lines = []
    for score, label in [(2.5, "+2.5"), (1.0, "+1"), (0.0, "0"), (-1.0, "-1"), (-2.5, "-2.5")]:
        y = y_at(score)
        grid_lines.append(
            f'<line class="signal-grid-line" x1="{left:.1f}" y1="{y:.1f}" x2="{width - right:.1f}" y2="{y:.1f}" />'
            f'<text class="signal-y-label" x="8" y="{y + 4:.1f}">{_html(label)}</text>'
        )

    x_labels = []
    for index, date in enumerate(dates):
        x = x_at(index)
        label = date[5:] if len(date) >= 10 else date
        x_labels.append(
            f'<line class="signal-tick" x1="{x:.1f}" y1="{top:.1f}" x2="{x:.1f}" y2="{height - bottom:.1f}" />'
            f'<text class="signal-x-label" x="{x:.1f}" y="{height - 18:.1f}">{_html(label)}</text>'
        )

    cards = []
    for ticker, display in ticker_rows:
        points_by_date = []
        for date_index, date in enumerate(dates):
            row = row_lookup.get((ticker, date))
            if not row:
                points_by_date.append(None)
                continue
            score = _signal_score(row)
            if score is None:
                points_by_date.append(None)
                continue
            points_by_date.append((date_index, date, row, score, x_at(date_index), y_at(score)))

        valid_points = [point for point in points_by_date if point is not None]
        if not valid_points:
            continue

        segments = []
        current_segment = []
        markers = []
        for point in points_by_date:
            if point is None:
                continue
            _, date, row, score, x, y = point
            current_segment.append(f"{x:.1f},{y:.1f}")
            action = row.get("final_action", "")
            direction = row.get("direction", "")
            confidence = row.get("confidence", "")
            title = " | ".join(
                [
                    display,
                    date,
                    f"动作={_action_label(action)}",
                    f"方向={_direction_label(direction)}",
                    f"数值和={_signal_text(score)}",
                    f"置信度={_confidence_text(confidence)}",
                    f"原始动作={action or '-'}",
                    f"原始方向={direction or '-'}",
                ]
            )
            markers.append(
                _confidence_point_markup(
                    x,
                    y,
                    _confidence_score(confidence),
                    title,
                    _signal_color_class(score),
                )
            )
        if len(current_segment) > 1:
            segments.append(current_segment)

        latest_date, latest_row, latest_score = max(
            (date, row, score) for _, date, row, score, _, _ in valid_points
        )
        latest_summary = "；".join(
            [
                latest_date,
                f"动作 {_action_label(latest_row.get('final_action', ''))}",
                f"方向 {_direction_label(latest_row.get('direction', ''))}",
                f"数值和 {_signal_text(latest_score)}",
                f"置信度 {_confidence_text(latest_row.get('confidence', ''))}",
            ]
        )
        line_class = _signal_color_class(latest_score)
        segment_parts = []
        for segment in segments:
            segment_text = " ".join(segment)
            segment_parts.append(
                f'<polyline class="line-series {line_class}" points="{segment_text}" />'
            )
        cards.append(
            f"""
            <article class="ticker-line-card">
                <div class="ticker-line-header">
                    <h4>{_html(display)}</h4>
                    <span class="ticker-line-latest {_html(line_class)}">{_html(_signal_text(latest_score))}</span>
                </div>
                <p class="ticker-line-summary">{_html(latest_summary)}</p>
                <div class="line-chart ticker-line-chart">
                    <svg class="signal-line-svg" viewBox="0 0 {width} {height}" role="img" aria-label="{_html(display)} 动作方向时间序列折线图">
                        {''.join(grid_lines)}
                        {''.join(x_labels)}
                        {''.join(segment_parts)}
                        {''.join(markers)}
                    </svg>
                </div>
            </article>"""
        )

    if not cards:
        return """
        <section class="chart-card">
            <h3>动作方向折线图</h3>
            <p class="empty-chart">暂无可绘制数据</p>
        </section>"""

    return f"""
        <section class="chart-card signal-small-multiples">
            <h3>动作方向折线图</h3>
            <p class="chart-note">每个标的一张图，X 轴为日期，Y 轴为动作分数 + 方向分数，统一范围 -2.5 到 +2.5；同一标的的已有观测点会连成折线；线条颜色表示最新信号：红色偏多、绿色偏空、灰色中性；点颜色表示该点信号方向，点形状区分置信度高/中/低/未知。</p>
            <div class="line-confidence-legend">
                <span class="confidence-legend-item"><i class="confidence-sample confidence-sample-star"></i>高置信度：五角星</span>
                <span class="confidence-legend-item"><i class="confidence-sample confidence-sample-triangle"></i>中置信度：三角形</span>
                <span class="confidence-legend-item"><i class="confidence-sample confidence-sample-circle"></i>低置信度：圆点</span>
                <span class="confidence-legend-item"><i class="confidence-sample confidence-sample-hollow"></i>未知置信度：空心圆点</span>
            </div>
            <div class="ticker-line-grid">{''.join(cards)}</div>
        </section>"""



def _render_metric_matrix(rows: list[dict[str, str]]) -> str:
    dates = _timeline_dates(rows)
    ticker_rows = _ticker_rows(rows)
    row_lookup = _row_by_ticker_date(rows)

    if not dates or not ticker_rows:
        return """
        <section class="chart-card">
            <h3>指标时间热力图</h3>
            <p class="empty-chart">暂无数据</p>
        </section>"""

    header_cells = "".join(f"<th scope=\"col\">{_html(date)}</th>" for date in dates)
    body_rows = []
    for ticker, display in ticker_rows:
        cells = []
        for date in dates:
            row = row_lookup.get((ticker, date))
            if row:
                action = row.get("final_action", "")
                direction = row.get("direction", "")
                confidence = row.get("confidence", "")
                time_horizon = row.get("time_horizon", "")
                score = _confidence_score(confidence)
                classes = " ".join(
                    [
                        "matrix-cell",
                        _action_class(action),
                        _confidence_class(score),
                    ]
                )
                cells.append(
                    f"<td><div class=\"{classes}\" title=\"{_html(display + ' | ' + date + ' | ' + action + ' | ' + direction + ' | ' + confidence + ' | ' + time_horizon)}\">"
                    f"<span class=\"matrix-action\">{_html(_action_label(action))}</span>"
                    f"<span class=\"matrix-meta\">{_html(_direction_label(direction))}</span>"
                    f"<span class=\"matrix-meta\">{_html(_confidence_text(confidence))}</span>"
                    f"<span class=\"matrix-meta\">{_html(time_horizon or '-')}</span>"
                    f"</div></td>"
                )
            else:
                cells.append('<td><div class="matrix-cell matrix-empty">-</div></td>')
        body_rows.append(
            f"<tr><th scope=\"row\" class=\"series-label\">{_html(display)}</th>{''.join(cells)}</tr>"
        )

    return f"""
        <section class="chart-card metric-matrix">
            <h3>指标时间热力图</h3>
            <div class="matrix-chart">
                <table class="matrix-table">
                    <thead>
                        <tr>
                            <th scope="col" class="series-axis">标的</th>
                            {header_cells}
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(body_rows)}
                    </tbody>
                </table>
            </div>
        </section>"""



def _render_dashboard(rows: list[dict[str, str]]) -> str:
    total = len(rows)
    dates = _timeline_dates(rows)
    ticker_rows = _ticker_rows(rows)
    return f"""
    <section class="dashboard-grid" aria-label="统计图表">
        <div class="metric-card">
            <span class="metric-label">总记录数</span>
            <strong>{total}</strong>
        </div>
        <div class="metric-card">
            <span class="metric-label">日期数</span>
            <strong>{len(dates)}</strong>
        </div>
        <div class="metric-card">
            <span class="metric-label">标的数</span>
            <strong>{len(ticker_rows)}</strong>
        </div>
    </section>
    <section class="dashboard-panels">
        {_render_signal_line_chart(rows)}
        {_render_metric_matrix(rows)}
    </section>
"""


def _sort_table_rows(rows: list[dict[str, str]]) -> None:
    rows.sort(key=lambda row: row.get("ticker", ""))
    rows.sort(key=lambda row: row.get("analysis_date", ""), reverse=True)


def render_html(csv_path: Path, html_path: Path) -> dict[str, object]:
    rows = _read_rows(csv_path)
    _sort_table_rows(rows)

    # 用原生精美 CSS 制作精美、响应式、支持实时搜索和筛选的 HTML 页面
    html_content = []
    html_content.append("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TradingAgents 每日标的分析看板</title>
    <style>
        :root {
            --primary: #1e3a8a;
            --primary-light: #eff6ff;
            --text-main: #1f2937;
            --text-muted: #4b5563;
            --border: #e5e7eb;
            --bg-body: #f9fafb;
            --bg-card: #ffffff;
            --buy: #ef4444;
            --sell: #10b981;
            --hold: #f59e0b;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: var(--bg-body);
            color: var(--text-main);
            margin: 0;
            padding: 0;
            line-height: 1.5;
        }

        header {
            background-color: var(--primary);
            color: white;
            padding: 1.5rem 2rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }

        header h1 {
            margin: 0 0 0.5rem 0;
            font-size: 1.75rem;
            font-weight: 700;
        }

        header p {
            margin: 0;
            font-size: 0.875rem;
            opacity: 0.9;
        }

        header a {
            color: #93c5fd;
            text-decoration: none;
        }

        header a:hover {
            text-decoration: underline;
        }

        main {
            max-width: 1200px;
            margin: 2rem auto;
            padding: 0 1.5rem;
        }

        /* 搜索框 */
        .search-container {
            margin-bottom: 2rem;
            background: var(--bg-card);
            padding: 1rem;
            border-radius: 0.5rem;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
            border: 1px solid var(--border);
            display: flex;
            gap: 1rem;
            align-items: center;
        }

        .search-input {
            flex: 1;
            padding: 0.625rem 1rem;
            border: 1px solid var(--border);
            border-radius: 0.375rem;
            font-size: 0.875rem;
            outline: none;
            transition: border-color 0.15s ease;
        }

        .search-input:focus {
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(30, 58, 138, 0.1);
        }

        .dashboard-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 1rem;
            margin-bottom: 1rem;
        }

        .dashboard-panels {
            display: grid;
            gap: 1rem;
            margin-bottom: 2rem;
        }

        .metric-card,
        .chart-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 0.5rem;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
            padding: 1rem;
        }

        .metric-card {
            display: flex;
            flex-direction: column;
            justify-content: center;
            min-height: 6rem;
        }

        .metric-label {
            color: var(--text-muted);
            font-size: 0.8125rem;
            margin-bottom: 0.25rem;
        }

        .metric-card strong {
            color: var(--primary);
            font-size: 2rem;
            line-height: 1;
        }

        .chart-card h3 {
            margin: 0 0 1rem 0;
            font-size: 1rem;
            color: var(--primary);
        }

        .empty-chart {
            color: var(--text-muted);
            margin: 0;
            font-size: 0.875rem;
        }

        .chart-note {
            color: var(--text-muted);
            margin: -0.35rem 0 0.85rem 0;
            font-size: 0.8125rem;
        }

        .ticker-line-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 1rem;
            margin-top: 1rem;
        }

        @media (max-width: 900px) {
            .ticker-line-grid {
                grid-template-columns: 1fr;
            }
        }

        .ticker-line-card {
            border: 1px solid var(--border);
            border-radius: 0.875rem;
            background: #ffffff;
            padding: 0.875rem;
            overflow: hidden;
        }

        .ticker-line-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            margin-bottom: 0.35rem;
        }

        .ticker-line-header h4 {
            margin: 0;
            color: var(--text-main);
            font-size: 0.95rem;
        }

        .ticker-line-latest {
            border-radius: 999px;
            padding: 0.2rem 0.5rem;
            font-weight: 700;
            font-variant-numeric: tabular-nums;
            background: #f1f5f9;
        }

        .ticker-line-latest.signal-positive { color: #991b1b; }
        .ticker-line-latest.signal-negative { color: #166534; }
        .ticker-line-latest.signal-neutral { color: #475569; }

        .ticker-line-summary {
            margin: 0 0 0.65rem 0;
            color: var(--text-muted);
            font-size: 0.78rem;
            line-height: 1.45;
        }

        .ticker-line-chart {
            border-radius: 0.625rem;
            background: #f8fafc;
        }

        .ticker-line-chart .signal-line-svg {
            height: 240px;
        }

        .line-series.signal-positive { stroke: #dc2626; }
        .line-series.signal-negative { stroke: #16a34a; }
        .line-series.signal-neutral { stroke: #64748b; }
        .line-point.signal-positive { stroke: #dc2626; fill: #dc2626; }
        .line-point.signal-negative { stroke: #16a34a; fill: #16a34a; }
        .line-point.signal-neutral { stroke: #64748b; fill: #64748b; }

        .line-chart,
        .matrix-chart {
            overflow-x: auto;
        }

        .signal-line-svg {
            min-width: 100%;
            height: 360px;
            display: block;
        }

        .signal-grid-line {
            stroke: #d1d5db;
            stroke-width: 1;
        }

        .signal-tick {
            stroke: #eef2f7;
            stroke-width: 1;
        }

        .signal-y-label,
        .signal-x-label {
            fill: var(--text-muted);
            font-size: 12px;
        }

        .signal-x-label {
            text-anchor: middle;
        }

        .line-series {
            fill: none;
            stroke-width: 2.5;
            stroke-linecap: round;
            stroke-linejoin: round;
        }

        .line-point {
            stroke: white;
            stroke-width: 1.5;
        }

        .line-point-star {
            stroke-width: 1.75;
        }

        .line-point-triangle {
            stroke-width: 1.5;
        }

        .line-point-circle {
            stroke-width: 1.25;
            opacity: 0.78;
        }

        .line-point.line-point-hollow {
            fill: white;
            stroke-dasharray: 2 2;
            opacity: 0.8;
        }

        .line-confidence-legend {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem 0.875rem;
            margin-top: 0.65rem;
            color: var(--text-muted);
            font-size: 0.78rem;
        }

        .confidence-sample {
            width: 0.75rem;
            height: 0.75rem;
            display: inline-block;
            background: #64748b;
            border: 2px solid white;
            box-shadow: 0 0 0 1px #cbd5e1;
        }

        .confidence-sample-star {
            clip-path: polygon(50% 0%, 61% 34%, 98% 35%, 68% 56%, 79% 91%, 50% 70%, 21% 91%, 32% 56%, 2% 35%, 39% 34%);
        }

        .confidence-sample-triangle {
            clip-path: polygon(50% 0%, 100% 100%, 0% 100%);
        }

        .confidence-sample-circle {
            border-radius: 999px;
            opacity: 0.78;
        }

        .confidence-sample-hollow {
            border-radius: 999px;
            background: white;
            border-style: dashed;
        }

        .confidence-legend-item {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
        }

        .line-legend {
            display: flex;
            flex-wrap: wrap;
            gap: 0.65rem 1rem;
            margin-top: 0.75rem;
            font-size: 0.8125rem;
            color: var(--text-muted);
        }

        .line-legend-item {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
        }

        .line-legend-item i {
            width: 0.75rem;
            height: 0.75rem;
            border-radius: 999px;
            display: inline-block;
        }

        .series-color-0 { stroke: #2563eb; fill: #2563eb; }
        .series-color-1 { stroke: #dc2626; fill: #dc2626; }
        .series-color-2 { stroke: #16a34a; fill: #16a34a; }
        .series-color-3 { stroke: #9333ea; fill: #9333ea; }
        .series-color-4 { stroke: #ea580c; fill: #ea580c; }
        .series-color-5 { stroke: #0891b2; fill: #0891b2; }
        .series-color-6 { stroke: #4f46e5; fill: #4f46e5; }
        .series-color-7 { stroke: #be123c; fill: #be123c; }

        .matrix-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.8125rem;
        }

        .matrix-table th,
        .matrix-table td {
            border-bottom: 1px solid var(--border);
            padding: 0.5rem 0.625rem;
            vertical-align: middle;
        }

        .matrix-table thead th {
            background: #f8fafc;
            color: var(--text-muted);
            font-weight: 600;
            text-align: center;
            white-space: nowrap;
        }

        .series-axis,
        .series-label {
            text-align: left !important;
            white-space: nowrap;
            color: var(--text-main);
            font-weight: 600;
        }

        .timeline-dot {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 3.5rem;
            padding: 0.25rem 0.45rem;
            border-radius: 999px;
            font-variant-numeric: tabular-nums;
            font-weight: 700;
        }

        .confidence-high { background: #dcfce7; color: #166534; }
        .confidence-medium { background: #fef3c7; color: #92400e; }
        .confidence-low { background: #fee2e2; color: #991b1b; }
        .confidence-unknown { background: #e5e7eb; color: #374151; }

        .matrix-cell {
            display: grid;
            gap: 0.125rem;
            min-width: 7rem;
            padding: 0.45rem 0.55rem;
            border-radius: 0.5rem;
            text-align: center;
            line-height: 1.2;
            background: #f9fafb;
        }

        .matrix-empty {
            color: var(--text-muted);
        }

        .matrix-action {
            font-weight: 700;
        }

        .matrix-meta {
            font-size: 0.72rem;
            color: var(--text-muted);
        }

        .action-buy { background: #fef2f2; color: #991b1b; }
        .action-sell { background: #ecfdf5; color: #166534; }
        .action-hold { background: #fffbeb; color: #92400e; }
        .action-neutral { background: #f3f4f6; color: #4b5563; }
        .action-unknown { background: #f9fafb; color: #374151; }

        .confidence-high.action-buy,
        .confidence-high.action-sell,
        .confidence-high.action-hold,
        .confidence-high.action-neutral,
        .confidence-high.action-unknown { box-shadow: inset 0 0 0 2px rgba(34, 197, 94, 0.18); }

        .confidence-medium.action-buy,
        .confidence-medium.action-sell,
        .confidence-medium.action-hold,
        .confidence-medium.action-neutral,
        .confidence-medium.action-unknown { box-shadow: inset 0 0 0 2px rgba(245, 158, 11, 0.18); }

        .confidence-low.action-buy,
        .confidence-low.action-sell,
        .confidence-low.action-hold,
        .confidence-low.action-neutral,
        .confidence-low.action-unknown { box-shadow: inset 0 0 0 2px rgba(239, 68, 68, 0.18); }

        .confidence-unknown.action-buy,
        .confidence-unknown.action-sell,
        .confidence-unknown.action-hold,
        .confidence-unknown.action-neutral,
        .confidence-unknown.action-unknown { box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.16); }

        /* 表格样式 */
        .table-container {
            background: var(--bg-card);
            border-radius: 0.5rem;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
            border: 1px solid var(--border);
            overflow-x: auto;
            margin-bottom: 2.5rem;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 0.875rem;
        }

        th {
            background-color: #f3f4f6;
            color: var(--text-muted);
            font-weight: 600;
            padding: 0.75rem 1rem;
            border-bottom: 1px solid var(--border);
        }

        td {
            padding: 0.75rem 1rem;
            border-bottom: 1px solid var(--border);
        }

        tr:last-child td {
            border-bottom: none;
        }

        tr:hover {
            background-color: #f9fafb;
        }

        .badge {
            display: inline-block;
            padding: 0.25rem 0.5rem;
            font-size: 0.75rem;
            font-weight: 600;
            border-radius: 0.25rem;
            text-transform: uppercase;
        }

        .badge-buy {
            background-color: #fef2f2;
            color: var(--buy);
        }

        .badge-sell {
            background-color: #ecfdf5;
            color: var(--sell);
        }

        .badge-hold {
            background-color: #fffbeb;
            color: var(--hold);
        }

        .badge-neutral {
            background-color: #f3f4f6;
            color: var(--text-muted);
        }

        .link-btn {
            color: var(--primary);
            text-decoration: none;
            font-weight: 500;
        }

        .link-btn:hover {
            text-decoration: underline;
        }

        .internal-link {
            color: var(--primary);
            text-decoration: none;
            font-weight: 600;
            margin-right: 0.5rem;
        }

        .internal-link:hover {
            text-decoration: underline;
        }

        .compare-checkbox {
            width: 1rem;
            height: 1rem;
            vertical-align: middle;
            accent-color: var(--primary);
        }

        .compare-cell {
            white-space: nowrap;
        }

        .compare-panel {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 0.5rem;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
            padding: 1rem;
            margin-bottom: 2rem;
        }

        .compare-panel-header,
        .compare-actions {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            flex-wrap: wrap;
        }

        .compare-panel h2 {
            margin: 0;
            color: var(--primary);
            font-size: 1.125rem;
        }

        .compare-count {
            color: var(--text-muted);
            font-size: 0.875rem;
        }

        .compare-clear-button {
            border: 1px solid var(--border);
            border-radius: 0.375rem;
            background: #f8fafc;
            color: var(--text-main);
            cursor: pointer;
            padding: 0.45rem 0.75rem;
            font-size: 0.8125rem;
        }

        .compare-clear-button:hover {
            background: var(--primary-light);
            color: var(--primary);
        }

        .compare-empty {
            color: var(--text-muted);
            margin: 1rem 0 0 0;
            font-size: 0.875rem;
        }

        .compare-table-wrap {
            overflow-x: auto;
            margin-top: 1rem;
        }

        .compare-table {
            min-width: 760px;
            font-size: 0.8125rem;
        }

        .compare-table th,
        .compare-table td {
            vertical-align: top;
        }

        .compare-table td:last-child {
            min-width: 16rem;
        }

        .ticker-detail-group {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 0.5rem;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
            overflow: hidden;
        }

        .ticker-detail-summary {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            padding: 1rem 1.25rem;
            color: var(--primary);
            font-size: 1rem;
        }

        .ticker-detail-summary span {
            color: var(--text-muted);
            font-size: 0.8125rem;
            font-weight: 500;
        }

        .ticker-detail-cards {
            display: flex;
            flex-direction: column;
            gap: 1rem;
            padding: 1rem;
            background: #f8fafc;
        }

        .card-actions {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
        }

        .card-actions label {
            color: var(--primary);
            cursor: pointer;
            font-weight: 600;
        }

        /* 详情板块 */
        .section-title {
            font-size: 1.5rem;
            font-weight: 700;
            margin: 2.5rem 0 1rem 0;
            border-bottom: 2px solid var(--primary);
            padding-bottom: 0.5rem;
        }

        .cards-container {
            display: flex;
            flex-direction: column;
            gap: 2rem;
        }

        .card {
            background: var(--bg-card);
            border-radius: 0.5rem;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
            border: 1px solid var(--border);
            overflow: hidden;
        }

        .card-header {
            background-color: #f8fafc;
            border-bottom: 1px solid var(--border);
            padding: 1rem 1.5rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 0.5rem;
        }

        .card-title {
            margin: 0;
            font-size: 1.25rem;
            font-weight: 700;
            color: var(--primary);
        }

        .card-meta {
            font-size: 0.8125rem;
            color: var(--text-muted);
            display: flex;
            gap: 1rem;
            flex-wrap: wrap;
        }

        .card-meta a {
            color: var(--primary);
            text-decoration: none;
        }

        .card-meta a:hover {
            text-decoration: underline;
        }

        .card-body {
            padding: 1.5rem;
        }

        .card-section {
            margin-bottom: 1.5rem;
        }

        .card-section:last-child {
            margin-bottom: 0;
        }

        .card-section-title {
            font-size: 1rem;
            font-weight: 600;
            margin: 0 0 0.5rem 0;
            color: #374151;
            border-left: 3px solid var(--primary);
            padding-left: 0.5rem;
        }

        .rationale {
            background: #fafafa;
            border: 1px solid #f0f0f0;
            padding: 1rem;
            border-radius: 0.375rem;
            font-size: 0.9rem;
            white-space: pre-wrap;
        }

        .bullet-list {
            margin: 0;
            padding-left: 1.25rem;
            font-size: 0.9rem;
        }

        .bullet-list li {
            margin-bottom: 0.25rem;
        }

        /* 可折叠的 Agent 详情列表 */
        .accordion {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
            margin-top: 1rem;
        }

        details {
            border: 1px solid var(--border);
            border-radius: 0.375rem;
            background: #fdfdfd;
        }

        summary {
            padding: 0.75rem 1rem;
            font-weight: 600;
            font-size: 0.875rem;
            cursor: pointer;
            outline: none;
            user-select: none;
            color: #374151;
        }

        summary:hover {
            background-color: #f8fafc;
        }

        details[open] summary {
            border-bottom: 1px solid var(--border);
            background-color: var(--primary-light);
            color: var(--primary);
        }

        .details-content {
            padding: 1rem;
            font-size: 0.875rem;
            color: var(--text-main);
            background: white;
            white-space: pre-wrap;
        }
    </style>
</head>
<body>

<header>
    <h1>TradingAgents 每日标的分析看板</h1>
    <p>数据源：<a href="./{csv_name}" target="_blank"><code>{csv_name}</code></a></p>
</header>

<main>
    <div class="search-container">
        <input type="text" id="searchInput" class="search-input" placeholder="输入 Ticker (标的代码) 或 日期 进行快速检索...">
    </div>

{dashboard}
    <div class="table-container">
        <table>
            <thead>
                <tr>
                    <th>日期</th>
                    <th>标的</th>
                    <th>动作</th>
                    <th>方向</th>
                    <th>置信度</th>
                    <th>周期</th>
                    <th>状态</th>
                    <th>报告</th>
                    <th>详情/比较</th>
                </tr>
            </thead>
            <tbody id="tableBody">
""".replace("{csv_name}", _link_path(str(csv_path), html_path.parent)).replace("{dashboard}", _render_dashboard(rows)))

    for index, row in enumerate(rows):
        raw_action = row.get("final_action", "")
        raw_direction = row.get("direction", "")
        action = _html(_action_label(raw_action))
        direction = _html(_direction_label(raw_direction))
        badge_class = _badge_class(raw_action)
        ticker_anchor = _ticker_anchor(row)
        decision_anchor = _decision_anchor(row, index)
        display = _ticker_display(row)

        report_link = ""
        report_path = row.get("report_path", "")
        if report_path:
            rel_report = _link_path(report_path, html_path.parent)
            report_link = f'<a class="link-btn" href="{rel_report}" target="_blank" rel="noopener noreferrer">报告</a>' if rel_report else "-"
        else:
            report_link = "-"

        html_content.append(f"""
                <tr class="table-row" data-ticker="{_html(row.get('ticker', ''))}" data-date="{_html(row.get('analysis_date', ''))}">
                    <td>{_html(row.get('analysis_date', ''))}</td>
                    <td><a class="internal-link" href="#{_html(ticker_anchor)}">{_html(display)}</a></td>
                    <td><span class="badge {badge_class}">{action}</span></td>
                    <td>{direction}</td>
                    <td>{_html(row.get('confidence', ''))}</td>
                    <td>{_html(row.get('time_horizon', ''))}</td>
                    <td>{_html(row.get('status', ''))}</td>
                    <td>{report_link}</td>
                    <td class="compare-cell">
                        <a class="internal-link" href="#{_html(decision_anchor)}">详情</a>
                        <label><input class="compare-checkbox" type="checkbox" data-compare-id="{_html(decision_anchor)}" data-date="{_html(row.get('analysis_date', ''))}" data-ticker="{_html(display)}" data-action="{_html(_action_label(raw_action))}" data-direction="{_html(_direction_label(raw_direction))}" data-confidence="{_html(row.get('confidence', ''))}" data-horizon="{_html(row.get('time_horizon', ''))}" data-status="{_html(row.get('status', ''))}" data-rationale="{_html(row.get('decision_rationale', ''))}"> 比较</label>
                    </td>
                </tr>""")

    html_content.append("""
            </tbody>
        </table>
    </div>

    <section class="compare-panel" aria-label="决策比较">
        <div class="compare-panel-header">
            <h2>决策比较</h2>
            <div class="compare-actions">
                <span class="compare-count" id="compareCount">已选择 0 条</span>
                <button class="compare-clear-button" type="button" id="compareClearButton">清空选择</button>
            </div>
        </div>
        <p class="compare-empty" id="compareEmpty">勾选表格或详情卡片中的“比较”，即可在这里并列查看动作、方向、置信度、周期、状态和决策理由。</p>
        <div class="compare-table-wrap" id="compareTableWrap" hidden>
            <table class="compare-table">
                <thead>
                    <tr>
                        <th>日期</th>
                        <th>标的</th>
                        <th>动作</th>
                        <th>方向</th>
                        <th>置信度</th>
                        <th>周期</th>
                        <th>状态</th>
                        <th>决策理由</th>
                    </tr>
                </thead>
                <tbody id="compareTableBody"></tbody>
            </table>
        </div>
    </section>

    <h2 class="section-title">每日决策详情</h2>
    <div class="cards-container" id="cardsContainer">
""")

    grouped_rows: dict[str, list[tuple[int, dict[str, str]]]] = {}
    for index, row in enumerate(rows):
        grouped_rows.setdefault(row.get("ticker", ""), []).append((index, row))

    for group_items in grouped_rows.values():
        first_row = group_items[0][1]
        ticker_anchor = _ticker_anchor(first_row)
        html_content.append(f"""
        <details class="ticker-detail-group" id="{_html(ticker_anchor)}" data-ticker="{_html(first_row.get('ticker', ''))}">
            <summary class="ticker-detail-summary"><strong>{_html(_ticker_display(first_row))}</strong><span>{len(group_items)} 条决策</span></summary>
            <div class="ticker-detail-cards">
""")

        for index, row in group_items:
            decision_anchor = _decision_anchor(row, index)
            title = " ".join(
                part
                for part in [
                    row.get("analysis_date", ""),
                    _ticker_display(row),
                    _action_label(row.get("final_action", "")),
                    _direction_label(row.get("direction", "")),
                ]
                if part
            )
            report_link = ""
            report_path = row.get("report_path", "")
            if report_path:
                rel_report = _link_path(report_path, html_path.parent)
                report_link = f' | <a href="{rel_report}" target="_blank" rel="noopener noreferrer">完整报告.md</a>' if rel_report else ""

            logs_part = ""
            runtime_log = row.get("runtime_log_path", "")
            message_log = row.get("message_tool_log_path", "")
            if runtime_log:
                rel_runtime_log = _link_path(runtime_log, html_path.parent)
                if rel_runtime_log:
                    logs_part += f' | <a href="{rel_runtime_log}" target="_blank" rel="noopener noreferrer">runtime.log</a>'
            if message_log:
                rel_message_log = _link_path(message_log, html_path.parent)
                if rel_message_log:
                    logs_part += f' | <a href="{rel_message_log}" target="_blank" rel="noopener noreferrer">message_tool.log</a>'

            html_content.append(f"""
            <div class="card" id="{_html(decision_anchor)}" data-ticker="{_html(row.get('ticker', ''))}" data-date="{_html(row.get('analysis_date', ''))}">
                <div class="card-header">
                    <h3 class="card-title">{_html(title or row.get('run_id', '未命名记录'))}</h3>
                    <div class="card-meta">
                        <span>run_id: <code>{_html(row.get('run_id', ''))}</code></span>
                        <span>模型: <code>{_html(row.get('shallow_model', ''))}</code> / <code>{_html(row.get('deep_model', ''))}</code></span>
                        <span><a href="#tableBody">返回表格</a>{report_link}{logs_part}</span>
                        <span class="card-actions"><label><input class="compare-checkbox" type="checkbox" data-compare-id="{_html(decision_anchor)}" data-date="{_html(row.get('analysis_date', ''))}" data-ticker="{_html(_ticker_display(row))}" data-action="{_html(_action_label(row.get('final_action', '')))}" data-direction="{_html(_direction_label(row.get('direction', '')))}" data-confidence="{_html(row.get('confidence', ''))}" data-horizon="{_html(row.get('time_horizon', ''))}" data-status="{_html(row.get('status', ''))}" data-rationale="{_html(row.get('decision_rationale', ''))}"> 加入比较</label></span>
                    </div>
                </div>
                <div class="card-body">
""")

            if row.get("error"):
                html_content.append(f"""
                    <div class="card-section" style="border: 1px solid #feca57; background: #fffaf0; padding: 1rem; border-radius: 0.375rem; margin-bottom: 1.5rem;">
                        <strong style="color: #d35400;">错误信息:</strong>
                        <div style="font-family: monospace; white-space: pre-wrap; font-size: 0.85rem; margin-top: 0.5rem;">{_html(row.get('error'))}</div>
                    </div>""")

            decision_rationale = _html(row.get("decision_rationale", "") or "（空）")
            html_content.append(f"""
                    <div class="card-section">
                        <h4 class="card-section-title">决策理由</h4>
                        <div class="rationale">{decision_rationale}</div>
                    </div>""")

            catalysts = _json_list(row.get("key_catalysts", ""))
            catalysts_li = "\n".join(f"<li>{_html(item)}</li>" for item in catalysts) if catalysts else "<li>（空）</li>"
            html_content.append(f"""
                    <div class="card-section">
                        <h4 class="card-section-title">关键催化</h4>
                        <ul class="bullet-list">
                            {catalysts_li}
                        </ul>
                    </div>""")

            risks = _json_list(row.get("key_risks", ""))
            risks_li = "\n".join(f"<li>{_html(item)}</li>" for item in risks) if risks else "<li>（空）</li>"
            html_content.append(f"""
                    <div class="card-section">
                        <h4 class="card-section-title">关键风险</h4>
                        <ul class="bullet-list">
                            {risks_li}
                        </ul>
                    </div>""")

            html_content.append("""
                    <div class="card-section">
                        <h4 class="card-section-title">分项摘要</h4>
                        <div class="accordion">""")

            for label, field in SUMMARY_SECTIONS:
                val = _html(row.get(field, "") or "（空）")
                html_content.append(f"""
                            <details>
                                <summary>{_html(label)}</summary>
                                <div class="details-content">{val}</div>
                            </details>""")

            html_content.append("""
                        </div>
                    </div>
                </div>
            </div>""")

        html_content.append("""
            </div>
        </details>""")

    html_content.append("""
    </div>
</main>

<script>
    const searchInput = document.getElementById('searchInput');
    const tableRows = document.querySelectorAll('.table-row');
    const cards = document.querySelectorAll('.card');
    const tickerGroups = document.querySelectorAll('.ticker-detail-group');
    const compareCheckboxes = document.querySelectorAll('.compare-checkbox');
    const compareCount = document.getElementById('compareCount');
    const compareEmpty = document.getElementById('compareEmpty');
    const compareTableWrap = document.getElementById('compareTableWrap');
    const compareTableBody = document.getElementById('compareTableBody');
    const compareClearButton = document.getElementById('compareClearButton');

    function matchesQuery(element, query) {
        const ticker = (element.dataset.ticker || '').toLowerCase();
        const date = (element.dataset.date || '').toLowerCase();
        return !query || ticker.includes(query) || date.includes(query);
    }

    searchInput.addEventListener('input', function(e) {
        const query = e.target.value.toLowerCase().trim();

        tableRows.forEach(row => {
            row.style.display = matchesQuery(row, query) ? '' : 'none';
        });

        cards.forEach(card => {
            card.style.display = matchesQuery(card, query) ? '' : 'none';
        });

        tickerGroups.forEach(group => {
            const groupTicker = (group.dataset.ticker || '').toLowerCase();
            const visibleCards = Array.from(group.querySelectorAll('.card')).some(card => card.style.display !== 'none');
            group.style.display = (!query || groupTicker.includes(query) || visibleCards) ? '' : 'none';
        });
    });

    function selectedCompareItems() {
        const byId = new Map();
        compareCheckboxes.forEach(checkbox => {
            if (checkbox.checked && !byId.has(checkbox.dataset.compareId)) {
                byId.set(checkbox.dataset.compareId, checkbox.dataset);
            }
        });
        return Array.from(byId.values());
    }

    function syncCompareCheckboxes(source) {
        compareCheckboxes.forEach(checkbox => {
            if (checkbox !== source && checkbox.dataset.compareId === source.dataset.compareId) {
                checkbox.checked = source.checked;
            }
        });
    }

    function appendCell(row, value) {
        const cell = document.createElement('td');
        cell.textContent = value || '-';
        row.appendChild(cell);
    }

    function renderComparePanel() {
        const items = selectedCompareItems();
        compareCount.textContent = `已选择 ${items.length} 条`;
        compareEmpty.hidden = items.length > 0;
        compareTableWrap.hidden = items.length === 0;
        compareTableBody.replaceChildren();

        items.forEach(item => {
            const row = document.createElement('tr');
            appendCell(row, item.date);
            appendCell(row, item.ticker);
            appendCell(row, item.action);
            appendCell(row, item.direction);
            appendCell(row, item.confidence);
            appendCell(row, item.horizon);
            appendCell(row, item.status);
            appendCell(row, item.rationale);
            compareTableBody.appendChild(row);
        });
    }

    compareCheckboxes.forEach(checkbox => {
        checkbox.addEventListener('change', function(e) {
            syncCompareCheckboxes(e.target);
            renderComparePanel();
        });
    });

    compareClearButton.addEventListener('click', function() {
        compareCheckboxes.forEach(checkbox => {
            checkbox.checked = false;
        });
        renderComparePanel();
    });
</script>
</body>
</html>
""")

    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text("\n".join(html_content) + "\n", encoding="utf-8")
    return {
        "status": "rendered",
        "csv_path": str(csv_path),
        "html_path": str(html_path),
        "row_count": len(rows),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-path", required=True)
    parser.add_argument("--html-path")
    args = parser.parse_args(argv)

    csv_path = Path(args.csv_path)
    html_path = (
        Path(args.html_path) if args.html_path else csv_path.with_suffix(".html")
    )
    payload = render_html(csv_path=csv_path, html_path=html_path)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
