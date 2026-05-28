from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import date
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SHALLOW_THINKER = "MiniMax-M2.7"
DEFAULT_DEEP_THINKER = "gpt-5.5"


def _load_module(module_name: str):
    module_path = SCRIPT_DIR / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"failed to load module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _jsonable(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_jsonable(payload), ensure_ascii=False), encoding="utf-8"
    )


def _artifacts_dir(
    repo_root: Path,
    analysis_date: str,
    ticker: str,
    run_id: str,
) -> Path:
    run_module = _load_module("run_tradingagents_daily")
    safe_ticker = run_module.safe_ticker_component(ticker)
    safe_analysis_date = run_module.safe_analysis_date(analysis_date)
    return (
        repo_root
        / "docs"
        / "tradingagents"
        / "artifacts"
        / safe_analysis_date
        / safe_ticker
        / run_id
    )


def _load_tradingagents_summary(
    discovery_payload: dict[str, object],
) -> dict[str, object] | None:
    report_dir = discovery_payload.get("report_dir")
    if not report_dir:
        return None
    summary_path = Path(str(report_dir)) / "summary.json"
    if not summary_path.exists():
        return None
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    return payload


def run_tradingagents_daily_pipeline(
    repo_root: Path,
    ticker: str,
    analysis_date: str,
    shallow_model: str,
    deep_model: str,
    csv_path: Path,
    output_language: str = "Chinese",
    summary_model: str | None = None,
) -> dict[str, object]:
    run_module = _load_module("run_tradingagents_daily")
    discover_module = _load_module("discover_latest_tradingagents_report")
    extract_module = _load_module("extract_tradingagents_summary")
    finalize_module = _load_module("finalize_tradingagents_csv")

    run_payload = run_module.run_tradingagents_daily(
        repo_root=repo_root,
        ticker=ticker,
        analysis_date=analysis_date,
        shallow_model=shallow_model,
        deep_model=deep_model,
        output_language=output_language,
    )
    run_payload = {
        **run_payload,
        "ticker": ticker,
        "analysis_date": analysis_date,
        "shallow_model": shallow_model,
        "deep_model": deep_model,
        "output_language": output_language,
    }
    if int(run_payload.get("returncode", 0)) != 0:
        raise RuntimeError(run_payload.get("stderr") or "tradingagents run failed")

    discovery_payload = discover_module.discover_latest_report(
        repo_root=repo_root,
        ticker=ticker,
        analysis_date=analysis_date,
    )
    run_id = str(discovery_payload["run_id"])
    artifacts_dir = _artifacts_dir(
        repo_root=repo_root,
        analysis_date=analysis_date,
        ticker=ticker,
        run_id=run_id,
    )
    run_json_path = artifacts_dir / "run.json"
    discovery_json_path = artifacts_dir / "discovery.json"
    summary_json_path = artifacts_dir / "summary.json"
    finalize_result_json_path = artifacts_dir / "finalize_result.json"
    _write_json(run_json_path, run_payload)
    _write_json(discovery_json_path, discovery_payload)

    failed_stage = ""
    summary_payload = _load_tradingagents_summary(discovery_payload)
    if not summary_payload or summary_payload.get("status") == "pending_summary":
        try:
            summary_payload = extract_module.extract_tradingagents_summary(
                report_path=Path(discovery_payload["report_path"]),
                model=summary_model or shallow_model,
            )
        except Exception as exc:
            failed_stage = "summary"
            if hasattr(extract_module, "build_error_summary"):
                summary_payload = extract_module.build_error_summary(str(exc))
            else:
                summary_payload = {"status": "pending_summary", "error": str(exc)}
    _write_json(summary_json_path, summary_payload)

    finalize_payload = finalize_module.finalize_csv(
        csv_path=csv_path,
        run_json_path=run_json_path,
        discovery_json_path=discovery_json_path,
        summary_json_path=summary_json_path,
    )
    _write_json(finalize_result_json_path, finalize_payload)

    return {
        "run_id": run_id,
        "report_path": str(discovery_payload["report_path"]),
        "csv_status": finalize_payload["status"],
        "markdown_path": finalize_payload.get("markdown_path", ""),
        "artifacts_dir": str(artifacts_dir),
        "failed_stage": failed_stage,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--analysis-date", default=date.today().isoformat())
    parser.add_argument(
        "--shallow-thinker",
        dest="shallow_model",
        default=DEFAULT_SHALLOW_THINKER,
    )
    parser.add_argument(
        "--deep-thinker",
        dest="deep_model",
        default=DEFAULT_DEEP_THINKER,
    )
    parser.add_argument("--output-language", default="Chinese")
    parser.add_argument("--summary-model")
    parser.add_argument("--csv-path")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root)
    csv_path = (
        Path(args.csv_path)
        if args.csv_path
        else repo_root / "docs" / "tradingagents" / "daily_ticker_analysis.csv"
    )
    payload = run_tradingagents_daily_pipeline(
        repo_root=repo_root,
        ticker=args.ticker,
        analysis_date=args.analysis_date,
        shallow_model=args.shallow_model,
        deep_model=args.deep_model,
        csv_path=csv_path,
        output_language=args.output_language,
        summary_model=args.summary_model,
    )
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
