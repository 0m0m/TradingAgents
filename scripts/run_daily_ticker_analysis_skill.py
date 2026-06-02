from __future__ import annotations

import argparse
import csv
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SHALLOW_THINKER = "MiniMax-M2.7"
DEFAULT_DEEP_THINKER = "MiniMax-M2.7"
ARTIFACT_FILENAMES = [
    "run.json",
    "discovery.json",
    "summary.json",
    "finalize_result.json",
]
DEFAULT_CONFIG = None
TradingAgentsGraph = None
save_report_to_disk = None


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


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON payload must be an object: {path}")
    return payload


def normalize_tickers(positionals: list[str], ticker_args: list[str]) -> list[str]:
    run_module = _load_module("run_tradingagents_daily")
    tickers: list[str] = []
    seen: set[str] = set()
    for value in [*positionals, *ticker_args]:
        safe_ticker = run_module.safe_ticker_component(value)
        if safe_ticker not in seen:
            tickers.append(safe_ticker)
            seen.add(safe_ticker)
    if not tickers:
        raise ValueError("at least one ticker is required")
    return tickers


def latest_artifacts_dir(
    repo_root: Path, analysis_date: str, ticker: str
) -> Path | None:
    preferred_root = repo_root / "reports" / analysis_date / "artifacts" / ticker
    if preferred_root.exists():
        candidates = sorted(path for path in preferred_root.iterdir() if path.is_dir())
        return candidates[-1] if candidates else None

    legacy_root = repo_root / "docs" / "tradingagents" / "artifacts" / analysis_date / ticker
    if not legacy_root.exists():
        return None
    candidates = sorted(path for path in legacy_root.iterdir() if path.is_dir())
    return candidates[-1] if candidates else None


def csv_rows_for(
    csv_path: Path,
    analysis_date: str,
    ticker: str,
    shallow_model: str,
    deep_model: str,
) -> list[dict[str, str]]:
    if not csv_path.exists():
        return []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [
        row
        for row in rows
        if row.get("analysis_date") == analysis_date
        and row.get("ticker") == ticker
        and row.get("shallow_model") == shallow_model
        and row.get("deep_model") == deep_model
    ]


def verify_ticker(
    repo_root: Path,
    ticker: str,
    analysis_date: str,
    shallow_model: str,
    deep_model: str,
    csv_path: Path,
    markdown_path: Path,
    html_path: Path | None = None,
) -> dict[str, Any]:
    missing: list[str] = []
    csv_rows = csv_rows_for(
        csv_path=csv_path,
        analysis_date=analysis_date,
        ticker=ticker,
        shallow_model=shallow_model,
        deep_model=deep_model,
    )
    if len(csv_rows) != 1:
        missing.append(f"csv_rows={len(csv_rows)}")

    artifacts_dir = latest_artifacts_dir(repo_root, analysis_date, ticker)
    discovery_payload: dict[str, Any] = {}
    report_path = ""
    report_dir = ""
    if artifacts_dir is None:
        missing.append("artifacts_dir")
    else:
        for filename in ARTIFACT_FILENAMES:
            if not (artifacts_dir / filename).exists():
                missing.append(filename)
        discovery_path = artifacts_dir / "discovery.json"
        if discovery_path.exists():
            try:
                discovery_payload = _read_json(discovery_path)
                report_path = str(discovery_payload.get("report_path", ""))
                report_dir = str(discovery_payload.get("report_dir", ""))
            except Exception as exc:
                missing.append(f"discovery_read={type(exc).__name__}")

    if not report_path or not Path(report_path).exists():
        missing.append("complete_report.md")
    if not report_dir or not (Path(report_dir) / "summary.json").exists():
        missing.append("report_summary.json")

    for key in ["runtime_log_path", "message_tool_log_path"]:
        value = str(discovery_payload.get(key, ""))
        if not value or not Path(value).exists():
            missing.append(key)

    if not markdown_path.exists():
        missing.append("markdown")

    resolved_html_path = html_path or markdown_path.with_suffix(".html")
    if not resolved_html_path.exists():
        missing.append("html")

    return {
        "ticker": ticker,
        "csv_rows": len(csv_rows),
        "report_path": report_path,
        "artifacts_dir": str(artifacts_dir) if artifacts_dir else "",
        "missing": missing,
    }


def repair_finalize_if_possible(
    csv_path: Path,
    markdown_path: Path,
    artifacts_dir: str,
    error: str = "",
    write_artifact_result: bool = True,
) -> dict[str, Any] | None:
    if not artifacts_dir:
        return None
    root = Path(artifacts_dir)
    run_json_path = root / "run.json"
    discovery_json_path = root / "discovery.json"
    summary_json_path = root / "summary.json"
    if not all(
        path.exists()
        for path in [run_json_path, discovery_json_path, summary_json_path]
    ):
        return None
    finalize_module = _load_module("finalize_tradingagents_csv")
    payload = finalize_module.finalize_csv(
        csv_path=csv_path,
        run_json_path=run_json_path,
        discovery_json_path=discovery_json_path,
        summary_json_path=summary_json_path,
        error=error,
        replace=True,
        markdown_path=markdown_path,
    )
    if write_artifact_result:
        finalize_result_path = root / "finalize_result.json"
        finalize_result_path.write_text(
            json.dumps(_jsonable(payload), ensure_ascii=False), encoding="utf-8"
        )
    return payload


def _default_config() -> dict[str, Any]:
    global DEFAULT_CONFIG
    if DEFAULT_CONFIG is None:
        from tradingagents.default_config import DEFAULT_CONFIG as loaded_config

        DEFAULT_CONFIG = loaded_config
    return DEFAULT_CONFIG


def _trading_graph_class():
    global TradingAgentsGraph
    if TradingAgentsGraph is None:
        from tradingagents.graph.trading_graph import TradingAgentsGraph as loaded_graph

        TradingAgentsGraph = loaded_graph
    return TradingAgentsGraph


def _save_report_to_disk(final_state, ticker: str, save_path: Path, summary_options: dict[str, object]):
    global save_report_to_disk
    if save_report_to_disk is None:
        from cli.main import save_report_to_disk as loaded_save_report_to_disk

        save_report_to_disk = loaded_save_report_to_disk
    return save_report_to_disk(final_state, ticker, save_path, None, summary_options)


def load_report_markdown(report_dir: Path, relative_path: str) -> str:
    path = report_dir / relative_path
    if not path.exists():
        raise FileNotFoundError(f"required report markdown missing: {path}")
    return path.read_text(encoding="utf-8")


def _refresh_config(
    shallow_model: str,
    deep_model: str,
    output_language: str,
    summary_model: str | None,
) -> dict[str, Any]:
    config = _default_config().copy()
    config["quick_think_llm"] = shallow_model
    config["deep_think_llm"] = deep_model
    config["output_language"] = output_language
    if summary_model:
        config["summary_model"] = summary_model
    return config


def _summary_options(config: dict[str, Any]) -> dict[str, object]:
    return {
        "enabled": config.get("summary_enabled", True),
        "provider": config.get("summary_provider") or config["llm_provider"],
        "model": config.get("summary_model") or config["quick_think_llm"],
        "base_url": config.get("summary_backend_url") or config.get("backend_url"),
        "output_language": config.get("output_language", "Chinese"),
    }


def run_sentiment_downstream_refresh(
    repo_root: Path,
    ticker: str,
    analysis_date: str,
    shallow_model: str,
    deep_model: str,
    output_language: str,
    summary_model: str | None,
    csv_path: Path,
    markdown_path: Path,
) -> dict[str, Any]:
    artifacts_dir = latest_artifacts_dir(repo_root, analysis_date, ticker)
    if artifacts_dir is None:
        raise FileNotFoundError(f"artifacts_dir not found for {ticker} {analysis_date}")

    discovery_payload = _read_json(artifacts_dir / "discovery.json")
    report_dir = Path(str(discovery_payload["report_dir"]))
    report_path = Path(str(discovery_payload["report_path"]))
    old_reports = {
        "market_report": load_report_markdown(report_dir, "1_analysts/market.md"),
        "news_report": load_report_markdown(report_dir, "1_analysts/news.md"),
        "fundamentals_report": load_report_markdown(report_dir, "1_analysts/fundamentals.md"),
    }

    config = _refresh_config(
        shallow_model=shallow_model,
        deep_model=deep_model,
        output_language=output_language,
        summary_model=summary_model,
    )
    graph = _trading_graph_class()(selected_analysts=["social"], config=config)
    initial_state = graph.propagator.create_initial_state(ticker, analysis_date, past_context="")
    initial_state.update(old_reports)
    final_state = graph.graph.invoke(initial_state, **graph.propagator.get_graph_args())
    final_state.update(old_reports)

    saved_report_path = _save_report_to_disk(
        final_state=final_state,
        ticker=ticker,
        save_path=report_dir,
        summary_options=_summary_options(config),
    )
    report_summary_path = report_dir / "summary.json"
    if not report_summary_path.exists():
        raise FileNotFoundError(f"summary.json not generated: {report_summary_path}")
    (artifacts_dir / "summary.json").write_text(
        report_summary_path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    finalize_payload = repair_finalize_if_possible(
        csv_path=csv_path,
        markdown_path=markdown_path,
        artifacts_dir=str(artifacts_dir),
        write_artifact_result=True,
    ) or {}

    return {
        "ticker": ticker,
        "status": "completed",
        "run_id": str(discovery_payload.get("run_id", artifacts_dir.name)),
        "report_path": str(report_path if report_path.exists() else saved_report_path),
        "artifacts_dir": str(artifacts_dir),
        "csv_status": finalize_payload.get("status", ""),
        "markdown_path": str(finalize_payload.get("markdown_path", "")),
        "html_path": str(finalize_payload.get("html_path", "")),
        "failed_stage": "",
        "error": "",
    }


def root_report_paths(
    repo_root: Path,
    root_csv_path: str | None,
    root_markdown_path: str | None,
) -> tuple[Path, Path]:
    root_csv = (
        Path(root_csv_path)
        if root_csv_path
        else repo_root / "reports" / "daily_ticker_analysis.csv"
    )
    root_markdown = Path(root_markdown_path) if root_markdown_path else root_csv.with_suffix(".md")
    return root_csv, root_markdown


def is_same_path(left: Path, right: Path) -> bool:
    return left.resolve() == right.resolve()


def sync_root_report_from_verifications(
    root_csv_path: Path,
    root_markdown_path: Path,
    verifications: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for verification in verifications:
        ticker = str(verification.get("ticker", ""))
        payload = repair_finalize_if_possible(
            csv_path=root_csv_path,
            markdown_path=root_markdown_path,
            artifacts_dir=str(verification.get("artifacts_dir", "")),
            write_artifact_result=False,
        )
        if payload is None:
            results.append(
                {
                    "ticker": ticker,
                    "status": "skipped_missing_artifacts",
                    "csv_path": str(root_csv_path),
                    "markdown_path": str(root_markdown_path),
                    "html_path": str(root_markdown_path.with_suffix(".html")),
                }
            )
            continue
        results.append(
            {
                "ticker": ticker,
                "status": payload.get("status", ""),
                "csv_path": payload.get("csv_path", str(root_csv_path)),
                "markdown_path": payload.get("markdown_path", str(root_markdown_path)),
                "html_path": payload.get("html_path", str(root_markdown_path.with_suffix(".html"))),
                "row_count": payload.get("row_count", 0),
            }
        )
    return results


def recover_saved_report(
    repo_root: Path,
    ticker: str,
    analysis_date: str,
    shallow_model: str,
    deep_model: str,
    output_language: str,
    csv_path: Path,
    markdown_path: Path,
    error: str,
) -> dict[str, Any] | None:
    pipeline_module = _load_module("run_tradingagents_daily_pipeline")
    discover_module = _load_module("discover_latest_tradingagents_report")
    summary_payload = None
    discovery_payload = discover_module.discover_latest_report(
        repo_root=repo_root,
        ticker=ticker,
        analysis_date=analysis_date,
    )
    report_dir = Path(str(discovery_payload["report_dir"]))
    report_summary_path = report_dir / "summary.json"
    if report_summary_path.exists():
        summary_payload = _read_json(report_summary_path)
    elif hasattr(pipeline_module, "_load_module"):
        extract_module = pipeline_module._load_module("extract_tradingagents_summary")
        summary_payload = extract_module.build_error_summary(error)
    if summary_payload is None:
        return None

    run_payload = {
        "ticker": ticker,
        "analysis_date": analysis_date,
        "shallow_model": shallow_model,
        "deep_model": deep_model,
        "output_language": output_language,
        "returncode": 1,
        "stdout": "",
        "stderr": error,
    }
    run_id = str(discovery_payload["run_id"])
    artifacts_dir = pipeline_module._artifacts_dir(
        repo_root=repo_root,
        analysis_date=analysis_date,
        ticker=ticker,
        run_id=run_id,
    )
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (artifacts_dir / "run.json").write_text(
        json.dumps(_jsonable(run_payload), ensure_ascii=False), encoding="utf-8"
    )
    (artifacts_dir / "discovery.json").write_text(
        json.dumps(_jsonable(discovery_payload), ensure_ascii=False), encoding="utf-8"
    )
    (artifacts_dir / "summary.json").write_text(
        json.dumps(_jsonable(summary_payload), ensure_ascii=False), encoding="utf-8"
    )
    finalize_payload = repair_finalize_if_possible(
        csv_path=csv_path,
        markdown_path=markdown_path,
        artifacts_dir=str(artifacts_dir),
        error=error,
    )
    return {
        "run_id": run_id,
        "report_path": str(discovery_payload["report_path"]),
        "csv_status": finalize_payload.get("status", "") if finalize_payload else "",
        "markdown_path": finalize_payload.get("markdown_path", "")
        if finalize_payload
        else "",
        "artifacts_dir": str(artifacts_dir),
        "failed_stage": "recovered",
    }


def run_one_ticker(
    repo_root: Path,
    ticker: str,
    analysis_date: str,
    shallow_model: str,
    deep_model: str,
    output_language: str,
    summary_model: str | None,
    csv_path: Path,
    markdown_path: Path,
) -> dict[str, Any]:
    pipeline_module = _load_module("run_tradingagents_daily_pipeline")
    try:
        payload = pipeline_module.run_tradingagents_daily_pipeline(
            repo_root=repo_root,
            ticker=ticker,
            analysis_date=analysis_date,
            shallow_model=shallow_model,
            deep_model=deep_model,
            csv_path=csv_path,
            output_language=output_language,
            summary_model=summary_model,
        )
        return {"ticker": ticker, "status": "completed", **payload, "error": ""}
    except Exception as exc:
        error = str(exc)
        try:
            recovered = recover_saved_report(
                repo_root=repo_root,
                ticker=ticker,
                analysis_date=analysis_date,
                shallow_model=shallow_model,
                deep_model=deep_model,
                output_language=output_language,
                csv_path=csv_path,
                markdown_path=markdown_path,
                error=error,
            )
        except Exception:
            recovered = None
        if recovered:
            return {
                "ticker": ticker,
                "status": "recovered",
                **recovered,
                "error": error,
            }
        return {"ticker": ticker, "status": "failed", "error": error}


def _run_parallel(
    tickers: list[str],
    max_concurrency: int,
    worker,
) -> list[dict[str, Any]]:
    results_by_ticker: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
        futures = {executor.submit(worker, ticker): ticker for ticker in tickers}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                results_by_ticker[ticker] = future.result()
            except Exception as exc:
                results_by_ticker[ticker] = {
                    "ticker": ticker,
                    "status": "failed",
                    "error": str(exc),
                }
    return [results_by_ticker[ticker] for ticker in tickers]


def run_batch(
    tickers: list[str],
    repo_root: Path,
    analysis_date: str,
    shallow_model: str,
    deep_model: str,
    output_language: str,
    summary_model: str | None,
    csv_path: Path,
    markdown_path: Path,
    max_concurrency: int,
) -> list[dict[str, Any]]:
    def worker(ticker: str) -> dict[str, Any]:
        return run_one_ticker(
            repo_root=repo_root,
            ticker=ticker,
            analysis_date=analysis_date,
            shallow_model=shallow_model,
            deep_model=deep_model,
            output_language=output_language,
            summary_model=summary_model,
            csv_path=csv_path,
            markdown_path=markdown_path,
        )

    return _run_parallel(tickers, max_concurrency, worker)


def refresh_batch(
    tickers: list[str],
    repo_root: Path,
    analysis_date: str,
    shallow_model: str,
    deep_model: str,
    output_language: str,
    summary_model: str | None,
    csv_path: Path,
    markdown_path: Path,
    max_concurrency: int,
) -> list[dict[str, Any]]:
    def worker(ticker: str) -> dict[str, Any]:
        return run_sentiment_downstream_refresh(
            repo_root=repo_root,
            ticker=ticker,
            analysis_date=analysis_date,
            shallow_model=shallow_model,
            deep_model=deep_model,
            output_language=output_language,
            summary_model=summary_model,
            csv_path=csv_path,
            markdown_path=markdown_path,
        )

    return _run_parallel(tickers, max_concurrency, worker)


def build_final_payload(
    run_results: list[dict[str, Any]],
    verifications: list[dict[str, Any]],
) -> dict[str, Any]:
    verification_by_ticker = {item["ticker"]: item for item in verifications}
    items: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for result in run_results:
        ticker = str(result["ticker"])
        verification = verification_by_ticker[ticker]
        item = {**result, **verification}
        items.append(item)
        if verification["missing"] or result.get("status") == "failed":
            missing.append(
                {
                    "ticker": ticker,
                    "missing": verification["missing"],
                    "error": result.get("error", ""),
                }
            )

    if not missing:
        evidence_sufficiency = "sufficient"
        blocked_reason = ""
        next_retrieval = ""
    else:
        evidence_sufficiency = (
            "blocked" if any(item.get("error") for item in missing) else "insufficient"
        )
        blocked_reason = "; ".join(
            f"{item['ticker']}: {', '.join(item['missing']) or item['error']}"
            for item in missing
        )
        next_retrieval = "补齐 missing 中列出的最小缺口后，重新运行本脚本或对应 ticker 的 finalize 修复。"

    return {
        "items": items,
        "missing": missing,
        "evidence_sufficiency": evidence_sufficiency,
        "blocked_reason": blocked_reason,
        "next_retrieval": next_retrieval,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tickers", nargs="*")
    parser.add_argument("--ticker", action="append", default=[])
    parser.add_argument("--repo-root", default=str(SCRIPT_DIR.parent))
    parser.add_argument("--analysis-date", default=date.today().isoformat())
    parser.add_argument(
        "--shallow-thinker", dest="shallow_model", default=DEFAULT_SHALLOW_THINKER
    )
    parser.add_argument(
        "--deep-thinker", dest="deep_model", default=DEFAULT_DEEP_THINKER
    )
    parser.add_argument("--output-language", default="Chinese")
    parser.add_argument("--summary-model")
    parser.add_argument("--csv-path")
    parser.add_argument("--markdown-path")
    parser.add_argument("--root-csv-path")
    parser.add_argument("--root-markdown-path")
    parser.add_argument(
        "--no-sync-root",
        action="store_true",
        help="do not sync finalized date-level rows to reports/daily_ticker_analysis.*",
    )
    parser.add_argument("--max-concurrency", type=int, default=2)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="only verify existing CSV, Markdown, reports, logs, and artifacts",
    )
    parser.add_argument(
        "--refresh-sentiment-downstream-only",
        action="store_true",
        help="reuse existing market/news/fundamentals reports and rerun sentiment plus downstream reports",
    )
    args = parser.parse_args(argv)

    if args.max_concurrency < 1:
        raise ValueError("--max-concurrency must be >= 1")
    if args.refresh_sentiment_downstream_only and args.verify_only:
        raise ValueError("--refresh-sentiment-downstream-only cannot be combined with --verify-only")

    tickers = normalize_tickers(args.tickers, args.ticker)
    repo_root = Path(args.repo_root)
    csv_path = (
        Path(args.csv_path)
        if args.csv_path
        else repo_root / "reports" / args.analysis_date / "daily_ticker_analysis.csv"
    )
    markdown_path = (
        Path(args.markdown_path) if args.markdown_path else csv_path.with_suffix(".md")
    )

    if args.verify_only:
        run_results = [
            {"ticker": ticker, "status": "verified_existing", "error": ""}
            for ticker in tickers
        ]
    elif args.refresh_sentiment_downstream_only:
        run_results = refresh_batch(
            tickers=tickers,
            repo_root=repo_root,
            analysis_date=args.analysis_date,
            shallow_model=args.shallow_model,
            deep_model=args.deep_model,
            output_language=args.output_language,
            summary_model=args.summary_model,
            csv_path=csv_path,
            markdown_path=markdown_path,
            max_concurrency=args.max_concurrency,
        )
    else:
        run_results = run_batch(
            tickers=tickers,
            repo_root=repo_root,
            analysis_date=args.analysis_date,
            shallow_model=args.shallow_model,
            deep_model=args.deep_model,
            output_language=args.output_language,
            summary_model=args.summary_model,
            csv_path=csv_path,
            markdown_path=markdown_path,
            max_concurrency=args.max_concurrency,
        )

    verifications = []
    for ticker in tickers:
        verification = verify_ticker(
            repo_root=repo_root,
            ticker=ticker,
            analysis_date=args.analysis_date,
            shallow_model=args.shallow_model,
            deep_model=args.deep_model,
            csv_path=csv_path,
            markdown_path=markdown_path,
        )
        if (
            verification["missing"]
            and verification["artifacts_dir"]
            and not args.verify_only
        ):
            repair_finalize_if_possible(
                csv_path=csv_path,
                markdown_path=markdown_path,
                artifacts_dir=verification["artifacts_dir"],
            )
            verification = verify_ticker(
                repo_root=repo_root,
                ticker=ticker,
                analysis_date=args.analysis_date,
                shallow_model=args.shallow_model,
                deep_model=args.deep_model,
                csv_path=csv_path,
                markdown_path=markdown_path,
            )
        verifications.append(verification)

    root_csv_path, root_markdown_path = root_report_paths(
        repo_root=repo_root,
        root_csv_path=args.root_csv_path,
        root_markdown_path=args.root_markdown_path,
    )

    root_sync: list[dict[str, Any]] = []
    should_sync_root = (
        not args.verify_only
        and not args.no_sync_root
        and not is_same_path(csv_path, root_csv_path)
    )
    if should_sync_root:
        root_sync = sync_root_report_from_verifications(
            root_csv_path=root_csv_path,
            root_markdown_path=root_markdown_path,
            verifications=verifications,
        )

    payload = build_final_payload(run_results, verifications)
    payload["root_sync"] = root_sync
    print(json.dumps(_jsonable(payload), ensure_ascii=False, indent=2))
    return 0 if payload["evidence_sufficiency"] == "sufficient" else 1


if __name__ == "__main__":
    raise SystemExit(main())
