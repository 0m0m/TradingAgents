from __future__ import annotations

import argparse
import csv
import json
import os
from html import escape
from pathlib import Path

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
    path = Path(path_text)
    try:
        if path.is_absolute():
            link = os.path.relpath(path, base_dir)
        else:
            link = path_text
    except ValueError:
        link = path_text
    return escape(link.replace("\\", "/"), quote=True)


def _html(value: object) -> str:
    return escape(str(value or ""), quote=True)


def render_html(csv_path: Path, html_path: Path) -> dict[str, object]:
    rows = _read_rows(csv_path)
    rows.sort(
        key=lambda row: (row.get("analysis_date", ""), row.get("ticker", "")),
        reverse=True,
    )

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
            --buy: #10b981;
            --sell: #ef4444;
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
            background-color: #ecfdf5;
            color: var(--buy);
        }

        .badge-sell {
            background-color: #fef2f2;
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
                </tr>
            </thead>
            <tbody id="tableBody">
""".replace("{csv_name}", _link_path(str(csv_path), html_path.parent)))

    for row in rows:
        action = _html(row.get("final_action", ""))
        badge_class = "badge-neutral"
        if "BUY" in action.upper():
            badge_class = "badge-buy"
        elif "SELL" in action.upper():
            badge_class = "badge-sell"
        elif "HOLD" in action.upper():
            badge_class = "badge-hold"

        report_link = ""
        report_path = row.get("report_path", "")
        if report_path:
            rel_report = _link_path(report_path, html_path.parent)
            report_link = f'<a class="link-btn" href="{rel_report}" target="_blank">报告</a>'
        else:
            report_link = "-"

        html_content.append(f"""
                <tr class="table-row" data-ticker="{_html(row.get('ticker', ''))}" data-date="{_html(row.get('analysis_date', ''))}">
                    <td>{_html(row.get('analysis_date', ''))}</td>
                    <td><strong>{_html(row.get('ticker', ''))}</strong></td>
                    <td><span class="badge {badge_class}">{action}</span></td>
                    <td>{_html(row.get('direction', ''))}</td>
                    <td>{_html(row.get('confidence', ''))}</td>
                    <td>{_html(row.get('time_horizon', ''))}</td>
                    <td>{_html(row.get('status', ''))}</td>
                    <td>{report_link}</td>
                </tr>""")

    html_content.append("""
            </tbody>
        </table>
    </div>

    <h2 class="section-title">每日决策详情</h2>
    <div class="cards-container" id="cardsContainer">
""")

    for row in rows:
        title = " ".join(
            part
            for part in [
                row.get("analysis_date", ""),
                row.get("ticker", ""),
                row.get("final_action", ""),
            ]
            if part
        )
        report_link = ""
        report_path = row.get("report_path", "")
        if report_path:
            report_link = f' | <a href="{_link_path(report_path, html_path.parent)}" target="_blank">完整报告.md</a>'

        logs_part = ""
        runtime_log = row.get("runtime_log_path", "")
        message_log = row.get("message_tool_log_path", "")
        if runtime_log:
            logs_part += f' | <a href="{_link_path(runtime_log, html_path.parent)}" target="_blank">runtime.log</a>'
        if message_log:
            logs_part += f' | <a href="{_link_path(message_log, html_path.parent)}" target="_blank">message_tool.log</a>'

        html_content.append(f"""
        <div class="card" data-ticker="{_html(row.get('ticker', ''))}" data-date="{_html(row.get('analysis_date', ''))}">
            <div class="card-header">
                <h3 class="card-title">{_html(title or row.get('run_id', '未命名记录'))}</h3>
                <div class="card-meta">
                    <span>run_id: <code>{_html(row.get('run_id', ''))}</code></span>
                    <span>模型: <code>{_html(row.get('shallow_model', ''))}</code> / <code>{_html(row.get('deep_model', ''))}</code></span>
                    <span>{report_link}{logs_part}</span>
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

        # 决策理由
        decision_rationale = _html(row.get("decision_rationale", "") or "（空）")
        html_content.append(f"""
                <div class="card-section">
                    <h4 class="card-section-title">决策理由</h4>
                    <div class="rationale">{decision_rationale}</div>
                </div>""")

        # 关键催化
        catalysts = _json_list(row.get("key_catalysts", ""))
        catalysts_li = "\n".join(f"<li>{_html(item)}</li>" for item in catalysts) if catalysts else "<li>（空）</li>"
        html_content.append(f"""
                <div class="card-section">
                    <h4 class="card-section-title">关键催化</h4>
                    <ul class="bullet-list">
                        {catalysts_li}
                    </ul>
                </div>""")

        # 关键风险
        risks = _json_list(row.get("key_risks", ""))
        risks_li = "\n".join(f"<li>{_html(item)}</li>" for item in risks) if risks else "<li>（空）</li>"
        html_content.append(f"""
                <div class="card-section">
                    <h4 class="card-section-title">关键风险</h4>
                    <ul class="bullet-list">
                        {risks_li}
                    </ul>
                </div>""")

        # 分项摘要折叠区
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
                </div>""")

        html_content.append("""
            </div>
        </div>""")

    html_content.append("""
    </div>
</main>

<script>
    // 支持按 Ticker 和日期快速实时搜索
    const searchInput = document.getElementById('searchInput');
    const tableRows = document.querySelectorAll('.table-row');
    const cards = document.querySelectorAll('.card');

    searchInput.addEventListener('input', function(e) {
        const query = e.target.value.toLowerCase().trim();

        // 筛选表格行
        tableRows.forEach(row => {
            const ticker = (row.dataset.ticker || '').toLowerCase();
            const date = (row.dataset.date || '').toLowerCase();
            if (ticker.includes(query) || date.includes(query)) {
                row.style.display = '';
            } else {
                row.style.display = 'none';
            }
        });

        // 筛选详情卡片
        cards.forEach(card => {
            const ticker = (card.dataset.ticker || '').toLowerCase();
            const date = (card.dataset.date || '').toLowerCase();
            if (ticker.includes(query) || date.includes(query)) {
                card.style.display = '';
            } else {
                card.style.display = 'none';
            }
        });
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
