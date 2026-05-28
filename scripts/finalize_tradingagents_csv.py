from __future__ import annotations

import argparse
import csv
import importlib.util
import json
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def _load_module(module_name: str):
    module_path = SCRIPT_DIR / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"failed to load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def finalize_csv(
    csv_path: Path,
    run_json_path: Path,
    discovery_json_path: Path,
    summary_json_path: Path | None = None,
    error: str = "",
    replace: bool = False,
    markdown_path: Path | None = None,
) -> dict[str, object]:
    run_payload = json.loads(run_json_path.read_text(encoding="utf-8"))
    discovery_payload = json.loads(discovery_json_path.read_text(encoding="utf-8"))
    summary_payload = None
    if summary_json_path is not None:
        summary_payload = json.loads(summary_json_path.read_text(encoding="utf-8"))

    row_builder = _load_module("build_tradingagents_summary_row")
    append_module = _load_module("append_tradingagents_csv")
    row = row_builder.build_summary_row(
        run_payload=run_payload,
        discovery_payload=discovery_payload,
        summary_payload=summary_payload,
        error=error,
    )
    with append_module.acquire_csv_lock(csv_path=csv_path):
        status = append_module.append_summary_row(
            csv_path=csv_path,
            row=row,
            replace=replace,
            use_lock=False,
        )
        markdown_module = _load_module("render_tradingagents_daily_markdown")
        markdown_payload = markdown_module.render_markdown(
            csv_path=csv_path,
            markdown_path=markdown_path or csv_path.with_suffix(".md"),
        )
        html_module = _load_module("render_tradingagents_daily_html")
        html_payload = html_module.render_html(
            csv_path=csv_path,
            html_path=(markdown_path or csv_path.with_suffix(".md")).with_suffix(".html"),
        )
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
    return {
        "status": status,
        "csv_path": str(csv_path),
        "markdown_path": markdown_payload["markdown_path"],
        "html_path": html_payload["html_path"],
        "row": row,
        "row_count": len(rows),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-path", required=True)
    parser.add_argument("--run-json-path", required=True)
    parser.add_argument("--discovery-json-path", required=True)
    parser.add_argument("--summary-json-path")
    parser.add_argument("--error", default="")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--markdown-path")
    args = parser.parse_args(argv)

    payload = finalize_csv(
        csv_path=Path(args.csv_path),
        run_json_path=Path(args.run_json_path),
        discovery_json_path=Path(args.discovery_json_path),
        summary_json_path=(
            Path(args.summary_json_path) if args.summary_json_path else None
        ),
        error=args.error,
        replace=args.replace,
        markdown_path=Path(args.markdown_path) if args.markdown_path else None,
    )
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
