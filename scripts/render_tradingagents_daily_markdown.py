from __future__ import annotations

import argparse
import csv
import json
import os
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
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _escape_cell(value: str) -> str:
    return (value or "").replace("\n", " ").replace("|", "\\|")


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
    return link.replace("\\", "/")


def _markdown_link(label: str, path_text: str, base_dir: Path) -> str:
    link = _link_path(path_text, base_dir)
    return f"[{label}]({link})" if link else ""


def _bullet_list(items: list[str]) -> list[str]:
    if not items:
        return ["- （空）"]
    return [f"- {item}" for item in items]


def render_markdown(csv_path: Path, markdown_path: Path) -> dict[str, object]:
    rows = _read_rows(csv_path)
    rows.sort(
        key=lambda row: (row.get("analysis_date", ""), row.get("ticker", "")),
        reverse=True,
    )

    lines = [
        "# TradingAgents 每日标的分析看板",
        "",
        f"数据源：`{_link_path(str(csv_path), markdown_path.parent)}`",
        "",
        "| 日期 | 标的 | 动作 | 方向 | 置信度 | 周期 | 状态 | 报告 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for row in rows:
        report_link = _markdown_link(
            "报告", row.get("report_path", ""), markdown_path.parent
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_cell(row.get("analysis_date", "")),
                    _escape_cell(row.get("ticker", "")),
                    _escape_cell(row.get("final_action", "")),
                    _escape_cell(row.get("direction", "")),
                    _escape_cell(row.get("confidence", "")),
                    _escape_cell(row.get("time_horizon", "")),
                    _escape_cell(row.get("status", "")),
                    report_link,
                ]
            )
            + " |"
        )

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
        lines.extend(["", f"## {title or row.get('run_id', '未命名记录')}", ""])
        lines.extend(
            [
                f"- run_id：`{row.get('run_id', '')}`",
                f"- 模型：`{row.get('shallow_model', '')}` / `{row.get('deep_model', '')}`",
                f"- 报告：{_markdown_link('complete_report.md', row.get('report_path', ''), markdown_path.parent)}",
                f"- runtime.log：`{_link_path(row.get('runtime_log_path', ''), markdown_path.parent)}`",
                f"- message_tool.log：`{_link_path(row.get('message_tool_log_path', ''), markdown_path.parent)}`",
            ]
        )
        if row.get("error"):
            lines.append(f"- error：`{row.get('error', '')}`")

        lines.extend(
            ["", "### 决策理由", "", row.get("decision_rationale", "") or "（空）"]
        )
        lines.extend(["", "### 关键催化", ""])
        lines.extend(_bullet_list(_json_list(row.get("key_catalysts", ""))))
        lines.extend(["", "### 关键风险", ""])
        lines.extend(_bullet_list(_json_list(row.get("key_risks", ""))))
        lines.extend(["", "### 分项摘要", ""])
        for label, field in SUMMARY_SECTIONS:
            value = row.get(field, "") or "（空）"
            lines.append(f"- **{label}**：{value}")

    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "status": "rendered",
        "csv_path": str(csv_path),
        "markdown_path": str(markdown_path),
        "row_count": len(rows),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-path", required=True)
    parser.add_argument("--markdown-path")
    args = parser.parse_args(argv)

    csv_path = Path(args.csv_path)
    markdown_path = (
        Path(args.markdown_path) if args.markdown_path else csv_path.with_suffix(".md")
    )
    payload = render_markdown(csv_path=csv_path, markdown_path=markdown_path)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
