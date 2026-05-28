from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path


LOG_FILENAMES = ("runtime.log", "message_tool.log")
_TICKER_PATH_RE = re.compile(r"^[A-Za-z0-9._\-\^]+$")
_ANALYSIS_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TRADINGAGENTS_REPO_ROOT = Path(__file__).resolve().parents[1]


def safe_ticker_component(value: str, *, max_len: int = 32) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"ticker must be a non-empty string, got {value!r}")
    if len(value) > max_len:
        raise ValueError(f"ticker exceeds {max_len} chars: {value!r}")
    if not _TICKER_PATH_RE.fullmatch(value):
        raise ValueError(
            f"ticker contains characters not allowed in a filesystem path: {value!r}"
        )
    if set(value) == {"."}:
        raise ValueError(f"ticker cannot consist solely of dots: {value!r}")
    return value


def safe_analysis_date(value: str) -> str:
    if not isinstance(value, str) or not _ANALYSIS_DATE_RE.fullmatch(value):
        raise ValueError(f"analysis_date must match YYYY-MM-DD, got {value!r}")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(
            f"analysis_date must be a valid calendar date, got {value!r}"
        ) from exc
    return value


def _report_root(analysis_date: str) -> Path:
    return TRADINGAGENTS_REPO_ROOT / "reports" / analysis_date


def _log_roots(repo_root: Path, ticker: str, analysis_date: str) -> list[Path]:
    return [
        repo_root / ".tradingagents" / "logs" / ticker / analysis_date,
        Path.home() / ".tradingagents" / "logs" / ticker / analysis_date,
    ]


def discover_latest_report(
    repo_root: Path, ticker: str, analysis_date: str
) -> dict[str, str]:
    validated_ticker = safe_ticker_component(ticker)
    validated_analysis_date = safe_analysis_date(analysis_date)
    report_root = _report_root(validated_analysis_date)
    report_files = sorted(report_root.glob(f"{validated_ticker}_*/complete_report.md"))
    if not report_files:
        raise FileNotFoundError(
            f"no complete_report.md found for {validated_ticker} on {validated_analysis_date}"
        )

    report_path = report_files[-1]
    report_dir = report_path.parent

    runtime_log_path = ""
    message_tool_log_path = ""
    for log_root in _log_roots(repo_root, validated_ticker, validated_analysis_date):
        runtime_log = log_root / "runtime.log"
        message_log = log_root / "message_tool.log"
        if runtime_log.exists() or message_log.exists():
            runtime_log_path = str(runtime_log) if runtime_log.exists() else ""
            message_tool_log_path = str(message_log) if message_log.exists() else ""
            break

    return {
        "run_id": f"{validated_analysis_date}__{validated_ticker}__{report_dir.name}",
        "report_dir": str(report_dir),
        "report_path": str(report_path),
        "runtime_log_path": runtime_log_path,
        "message_tool_log_path": message_tool_log_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--analysis-date", required=True)
    args = parser.parse_args(argv)

    payload = discover_latest_report(
        repo_root=Path(args.repo_root),
        ticker=args.ticker,
        analysis_date=args.analysis_date,
    )
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
