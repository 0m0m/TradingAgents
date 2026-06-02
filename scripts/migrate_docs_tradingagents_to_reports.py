from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import shutil
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent


def _load_module(module_name: str):
    module_path = SCRIPT_DIR / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"failed to load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_rows(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        return []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _row_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        row.get("analysis_date", ""),
        row.get("ticker", ""),
        row.get("shallow_model", ""),
        row.get("deep_model", ""),
    )


def _write_rows(csv_path: Path, rows: list[dict[str, str]], columns: list[str]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _merge_csv_for_date(
    source_rows: list[dict[str, str]],
    target_csv: Path,
    columns: list[str],
    dry_run: bool,
) -> dict[str, int]:
    target_rows = _read_rows(target_csv)
    existing_keys = {_row_key(row) for row in target_rows}
    rows_to_append = []
    for row in source_rows:
        key = _row_key(row)
        if key in existing_keys:
            continue
        existing_keys.add(key)
        rows_to_append.append(row)

    normalized_columns = [*columns]
    for column in source_rows[0].keys() if source_rows else []:
        if column not in normalized_columns:
            normalized_columns.append(column)

    if not dry_run and rows_to_append:
        normalized_rows = [
            {column: row.get(column, "") for column in normalized_columns}
            for row in [*target_rows, *rows_to_append]
        ]
        _write_rows(target_csv, normalized_rows, normalized_columns)

    return {
        "source_rows": len(source_rows),
        "existing_rows": len(target_rows),
        "appended_rows": len(rows_to_append),
        "skipped_duplicate_rows": len(source_rows) - len(rows_to_append),
    }


def _copy_artifacts(source_root: Path, target_root: Path, dry_run: bool) -> dict[str, int]:
    if not source_root.exists():
        return {"copied": 0, "skipped_existing": 0}

    copied = 0
    skipped_existing = 0
    for run_dir in sorted(path for path in source_root.glob("*/*/*") if path.is_dir()):
        relative = run_dir.relative_to(source_root)
        target_dir = target_root / relative.parts[0] / "artifacts" / relative.parts[1] / relative.parts[2]
        if target_dir.exists():
            skipped_existing += 1
            continue
        copied += 1
        if not dry_run:
            shutil.copytree(run_dir, target_dir)
    return {"copied": copied, "skipped_existing": skipped_existing}


def _render_views(csv_paths: list[Path], dry_run: bool) -> list[dict[str, Any]]:
    if dry_run:
        return [
            {
                "csv_path": str(csv_path),
                "markdown_path": str(csv_path.with_suffix(".md")),
                "html_path": str(csv_path.with_suffix(".html")),
                "status": "dry_run",
            }
            for csv_path in csv_paths
        ]

    markdown_module = _load_module("render_tradingagents_daily_markdown")
    html_module = _load_module("render_tradingagents_daily_html")
    payloads = []
    for csv_path in csv_paths:
        markdown_payload = markdown_module.render_markdown(
            csv_path=csv_path,
            markdown_path=csv_path.with_suffix(".md"),
        )
        html_payload = html_module.render_html(
            csv_path=csv_path,
            html_path=csv_path.with_suffix(".html"),
        )
        payloads.append(
            {
                "csv_path": str(csv_path),
                "markdown_path": markdown_payload["markdown_path"],
                "html_path": html_payload["html_path"],
                "status": "rendered",
            }
        )
    return payloads


def migrate_docs_tradingagents_to_reports(
    source_dir: Path,
    target_root: Path,
    dry_run: bool = True,
) -> dict[str, Any]:
    source_csv = source_dir / "daily_ticker_analysis.csv"
    source_rows = _read_rows(source_csv)
    append_module = _load_module("append_tradingagents_csv")
    columns = list(append_module.CSV_COLUMNS)

    rows_by_date: dict[str, list[dict[str, str]]] = {}
    for row in source_rows:
        analysis_date = row.get("analysis_date", "")
        if analysis_date:
            rows_by_date.setdefault(analysis_date, []).append(row)

    csv_results = {}
    affected_csv_paths = []
    for analysis_date, rows in sorted(rows_by_date.items()):
        target_csv = target_root / analysis_date / "daily_ticker_analysis.csv"
        result = _merge_csv_for_date(rows, target_csv, columns, dry_run)
        csv_results[analysis_date] = {**result, "target_csv": str(target_csv)}
        if result["appended_rows"] or target_csv.exists():
            affected_csv_paths.append(target_csv)

    artifact_result = _copy_artifacts(
        source_root=source_dir / "artifacts",
        target_root=target_root,
        dry_run=dry_run,
    )
    rendered_views = _render_views(sorted(set(affected_csv_paths)), dry_run)

    return {
        "status": "dry_run" if dry_run else "migrated",
        "source_dir": str(source_dir),
        "target_root": str(target_root),
        "csv": csv_results,
        "artifacts": artifact_result,
        "views": rendered_views,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", default=str(REPO_ROOT / "docs" / "tradingagents"))
    parser.add_argument("--target-root", default=str(REPO_ROOT / "reports"))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    payload = migrate_docs_tradingagents_to_reports(
        source_dir=Path(args.source_dir),
        target_root=Path(args.target_root),
        dry_run=not args.execute,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
