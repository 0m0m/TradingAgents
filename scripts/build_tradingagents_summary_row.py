from __future__ import annotations

import argparse
import json
from pathlib import Path


SUMMARY_FIELDS = [
    "final_action",
    "direction",
    "confidence",
    "time_horizon",
    "market_report_summary",
    "sentiment_report_summary",
    "news_report_summary",
    "fundamentals_report_summary",
    "bull_case_summary",
    "bear_case_summary",
    "research_manager_summary",
    "trader_plan_summary",
    "risk_aggressive_summary",
    "risk_conservative_summary",
    "risk_neutral_summary",
    "portfolio_manager_summary",
    "key_catalysts",
    "key_risks",
    "decision_rationale",
]


def _stringify(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def build_summary_row(
    run_payload: dict[str, object],
    discovery_payload: dict[str, object],
    summary_payload: dict[str, object] | None,
    error: str = "",
) -> dict[str, str]:
    row = {
        "run_id": _stringify(discovery_payload.get("run_id")),
        "analysis_date": _stringify(run_payload.get("analysis_date")),
        "ticker": _stringify(run_payload.get("ticker")),
        "shallow_model": _stringify(run_payload.get("shallow_model")),
        "deep_model": _stringify(run_payload.get("deep_model")),
        "report_dir": _stringify(discovery_payload.get("report_dir")),
        "report_path": _stringify(discovery_payload.get("report_path")),
        "runtime_log_path": _stringify(discovery_payload.get("runtime_log_path")),
        "message_tool_log_path": _stringify(
            discovery_payload.get("message_tool_log_path")
        ),
    }
    for field in SUMMARY_FIELDS:
        row[field] = ""

    if summary_payload is None:
        row["raw_summary_json"] = ""
        row["status"] = "pending_summary"
        row["error"] = error
        return row

    for field in SUMMARY_FIELDS:
        row[field] = _stringify(summary_payload.get(field))

    row["raw_summary_json"] = json.dumps(summary_payload, ensure_ascii=False)
    row["status"] = _stringify(summary_payload.get("status")) or "completed"
    row["error"] = error or _stringify(summary_payload.get("error"))
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-json-path", required=True)
    parser.add_argument("--discovery-json-path", required=True)
    parser.add_argument("--summary-json-path")
    parser.add_argument("--error", default="")
    args = parser.parse_args(argv)

    run_payload = json.loads(Path(args.run_json_path).read_text(encoding="utf-8"))
    discovery_payload = json.loads(
        Path(args.discovery_json_path).read_text(encoding="utf-8")
    )
    summary_payload = None
    if args.summary_json_path:
        summary_payload = json.loads(
            Path(args.summary_json_path).read_text(encoding="utf-8")
        )

    row = build_summary_row(
        run_payload=run_payload,
        discovery_payload=discovery_payload,
        summary_payload=summary_payload,
        error=args.error,
    )
    print(json.dumps(row, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
