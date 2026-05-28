from __future__ import annotations

import argparse
import contextlib
import csv
import json
import os
import time
from pathlib import Path


CSV_COLUMNS = [
    "run_id",
    "analysis_date",
    "ticker",
    "shallow_model",
    "deep_model",
    "report_dir",
    "report_path",
    "runtime_log_path",
    "message_tool_log_path",
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
    "raw_summary_json",
    "status",
    "error",
]
KEY_COLUMNS = ["analysis_date", "ticker", "shallow_model", "deep_model"]


@contextlib.contextmanager
def acquire_csv_lock(csv_path: Path, timeout_seconds: float = 30.0):
    lock_path = csv_path.with_suffix(csv_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_seconds
    fd: int | None = None
    while fd is None:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"timed out waiting for CSV lock: {lock_path}")
            time.sleep(0.05)
    try:
        yield
    finally:
        os.close(fd)
        lock_path.unlink(missing_ok=True)


def _normalize_row(row: dict[str, str]) -> dict[str, str]:
    normalized = {column: "" for column in CSV_COLUMNS}
    for key, value in row.items():
        if key in normalized:
            normalized[key] = "" if value is None else str(value)
    return normalized


def _read_rows(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        return []
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_rows(csv_path: Path, rows: list[dict[str, str]]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _same_identity(left: dict[str, str], right: dict[str, str]) -> bool:
    return all((left.get(key, "") == right.get(key, "")) for key in KEY_COLUMNS)


def append_summary_row(
    csv_path: Path,
    row: dict[str, str],
    replace: bool = False,
    use_lock: bool = True,
) -> str:
    if use_lock:
        with acquire_csv_lock(csv_path):
            return append_summary_row(
                csv_path=csv_path,
                row=row,
                replace=replace,
                use_lock=False,
            )

    normalized = _normalize_row(row)
    rows = [_normalize_row(existing) for existing in _read_rows(csv_path)]

    for index, existing in enumerate(rows):
        if not _same_identity(existing, normalized):
            continue
        should_replace = replace or (
            existing.get("status", "") == "pending_summary"
            and normalized.get("status", "") == "completed"
        )
        if should_replace:
            rows[index] = normalized
            _write_rows(csv_path, rows)
            return "replaced"
        return "skipped_duplicate"

    rows.append(normalized)
    _write_rows(csv_path, rows)
    return "appended"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-path", required=True)
    parser.add_argument("--row-json-path", required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args(argv)

    row = json.loads(Path(args.row_json_path).read_text(encoding="utf-8"))
    status = append_summary_row(
        csv_path=Path(args.csv_path),
        row=row,
        replace=args.replace,
    )
    print(
        json.dumps(
            {
                "status": status,
                "csv_path": str(Path(args.csv_path)),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
