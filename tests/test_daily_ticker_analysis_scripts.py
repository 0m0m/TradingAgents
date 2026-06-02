from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _load_script(module_name: str):
    module_path = SCRIPTS_DIR / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ticker_display_appends_uppercase_pinyin_abbreviation():
    module = _load_script("ticker_display")

    assert module.ticker_display({"ticker": "601857.SS"}) == "601857.SS（中国石油 / ZGSY）"
    assert (
        module.ticker_display({"ticker": "000001.SZ", "ticker_name": "平安银行"})
        == "000001.SZ（平安银行 / PAYH）"
    )
    assert module.ticker_display({"ticker": "AAPL"}) == "AAPL"


def test_render_markdown_adds_ticker_pinyin_abbreviation(tmp_path: Path):
    module = _load_script("render_tradingagents_daily_markdown")
    csv_path = tmp_path / "daily_ticker_analysis.csv"
    markdown_path = tmp_path / "daily_ticker_analysis.md"

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["analysis_date", "ticker", "ticker_name", "final_action"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "analysis_date": "2026-05-30",
                "ticker": "000001.SZ",
                "ticker_name": "平安银行",
                "final_action": "BUY",
            }
        )

    module.render_markdown(csv_path=csv_path, markdown_path=markdown_path)
    content = markdown_path.read_text(encoding="utf-8")

    assert "000001.SZ（平安银行 / PAYH）" in content


def test_run_tradingagents_daily_builds_report_context(monkeypatch, tmp_path: Path):
    module = _load_script("run_tradingagents_daily")
    tradingagents_root = tmp_path / "TradingAgents"
    monkeypatch.setattr(module, "TRADINGAGENTS_REPO_ROOT", tradingagents_root)

    context = module.build_run_context(
        repo_root=tmp_path / "m1",
        ticker="AAPL",
        analysis_date="2026-05-09",
        shallow_model="MiniMax-M2.7",
        deep_model="gpt-5.5",
        timestamp="20260509_090000",
    )

    expected_report_dir = (
        tradingagents_root / "reports" / "2026-05-09" / "AAPL_20260509_090000"
    )
    assert context["report_dir"] == expected_report_dir
    assert context["tradingagents_root"] == tradingagents_root
    assert str(expected_report_dir) in context["stdin_text"]
    assert (
        tmp_path / "m1" / "docs" / "tradingagents" / "reports"
        not in expected_report_dir.parents
    )


def test_discover_latest_report_uses_tradingagents_reports_and_repo_logs(
    monkeypatch, tmp_path: Path
):
    module = _load_script("discover_latest_tradingagents_report")
    tradingagents_root = tmp_path / "TradingAgents"
    repo_root = tmp_path / "m1"
    monkeypatch.setattr(module, "TRADINGAGENTS_REPO_ROOT", tradingagents_root)

    reports_root = tradingagents_root / "reports" / "2026-05-09"
    older_dir = reports_root / "AAPL_20260509_080000"
    newer_dir = reports_root / "AAPL_20260509_090000"
    older_dir.mkdir(parents=True)
    newer_dir.mkdir(parents=True)
    (older_dir / "complete_report.md").write_text("old", encoding="utf-8")
    (newer_dir / "complete_report.md").write_text("new", encoding="utf-8")

    logs_root = repo_root / ".tradingagents" / "logs" / "AAPL" / "2026-05-09"
    logs_root.mkdir(parents=True)
    (logs_root / "runtime.log").write_text("runtime", encoding="utf-8")
    (logs_root / "message_tool.log").write_text("messages", encoding="utf-8")

    payload = module.discover_latest_report(
        repo_root=repo_root,
        ticker="AAPL",
        analysis_date="2026-05-09",
    )

    assert payload["report_dir"] == str(newer_dir)
    assert payload["report_path"] == str(newer_dir / "complete_report.md")
    assert payload["runtime_log_path"] == str(logs_root / "runtime.log")
    assert payload["message_tool_log_path"] == str(logs_root / "message_tool.log")
    assert payload["run_id"] == "2026-05-09__AAPL__AAPL_20260509_090000"


def test_run_tradingagents_daily_uses_tradingagents_cwd_and_utf8_env(
    monkeypatch, tmp_path: Path
):
    module = _load_script("run_tradingagents_daily")
    tradingagents_root = tmp_path / "TradingAgents"
    monkeypatch.setattr(module, "TRADINGAGENTS_REPO_ROOT", tradingagents_root)
    monkeypatch.setenv("VIRTUAL_ENV", str(tmp_path / "m1" / ".venv"))

    class CompletedProcess:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(command, **kwargs):
        assert command[:3] == ["uv", "run", "tradingagents"]
        assert kwargs["cwd"] == tradingagents_root
        assert kwargs["encoding"] == "utf-8"
        assert kwargs["errors"] == "replace"
        assert "VIRTUAL_ENV" not in kwargs["env"]
        assert kwargs["env"]["PYTHONUTF8"] == "1"
        assert kwargs["env"]["PYTHONIOENCODING"] == "utf-8"
        assert str(tradingagents_root / "reports" / "2026-05-09") in kwargs["input"]
        return CompletedProcess()

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.run_tradingagents_daily(
        repo_root=tmp_path / "m1",
        ticker="AAPL",
        analysis_date="2026-05-09",
        shallow_model="MiniMax-M2.7",
        deep_model="gpt-5.5",
    )

    assert payload["returncode"] == 0
    assert payload["tradingagents_root"] == tradingagents_root


def test_verify_ticker_accepts_artifacts_pointing_to_tradingagents_reports(
    tmp_path: Path,
):
    module = _load_script("run_daily_ticker_analysis_skill")
    repo_root = tmp_path / "m1"
    tradingagents_root = tmp_path / "TradingAgents"
    analysis_date = "2026-05-09"
    ticker = "AAPL"
    run_id = "2026-05-09__AAPL__AAPL_20260509_090000"

    report_dir = tradingagents_root / "reports" / analysis_date / "AAPL_20260509_090000"
    report_dir.mkdir(parents=True)
    report_path = report_dir / "complete_report.md"
    report_path.write_text("report", encoding="utf-8")
    (report_dir / "summary.json").write_text(
        json.dumps({"final_action": "BUY", "status": "completed"}),
        encoding="utf-8",
    )

    logs_root = repo_root / ".tradingagents" / "logs" / ticker / analysis_date
    logs_root.mkdir(parents=True)
    runtime_log_path = logs_root / "runtime.log"
    message_tool_log_path = logs_root / "message_tool.log"
    runtime_log_path.write_text("runtime", encoding="utf-8")
    message_tool_log_path.write_text("messages", encoding="utf-8")

    artifacts_dir = (
        repo_root
        / "reports"
        / analysis_date
        / "artifacts"
        / ticker
        / run_id
    )
    artifacts_dir.mkdir(parents=True)
    (artifacts_dir / "run.json").write_text("{}", encoding="utf-8")
    (artifacts_dir / "discovery.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "report_dir": str(report_dir),
                "report_path": str(report_path),
                "runtime_log_path": str(runtime_log_path),
                "message_tool_log_path": str(message_tool_log_path),
            }
        ),
        encoding="utf-8",
    )
    (artifacts_dir / "summary.json").write_text("{}", encoding="utf-8")
    (artifacts_dir / "finalize_result.json").write_text("{}", encoding="utf-8")

    csv_path = repo_root / "reports" / analysis_date / "daily_ticker_analysis.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["analysis_date", "ticker", "shallow_model", "deep_model"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "analysis_date": analysis_date,
                "ticker": ticker,
                "shallow_model": "MiniMax-M2.7",
                "deep_model": "gpt-5.5",
            }
        )

    markdown_path = csv_path.with_suffix(".md")
    markdown_path.write_text("dashboard", encoding="utf-8")
    html_path = csv_path.with_suffix(".html")
    html_path.write_text("html dashboard", encoding="utf-8")

    payload = module.verify_ticker(
        repo_root=repo_root,
        ticker=ticker,
        analysis_date=analysis_date,
        shallow_model="MiniMax-M2.7",
        deep_model="gpt-5.5",
        csv_path=csv_path,
        markdown_path=markdown_path,
    )

    assert payload["missing"] == []
    assert payload["report_path"] == str(report_path)
    assert payload["artifacts_dir"] == str(artifacts_dir)


def test_refresh_sentiment_downstream_reuses_existing_analyst_reports_and_refreshes_summary(monkeypatch, tmp_path: Path):
    module = _load_script("run_daily_ticker_analysis_skill")
    repo_root = tmp_path / "m1"
    analysis_date = "2026-05-30"
    ticker = "000100.SZ"
    run_id = "2026-05-30__000100.SZ__000100_20260530_090000"

    report_dir = tmp_path / "TradingAgents" / "reports" / analysis_date / "000100_20260530_090000"
    analysts_dir = report_dir / "1_analysts"
    analysts_dir.mkdir(parents=True)
    (analysts_dir / "market.md").write_text("old market", encoding="utf-8")
    (analysts_dir / "news.md").write_text("old news", encoding="utf-8")
    (analysts_dir / "fundamentals.md").write_text("old fundamentals", encoding="utf-8")
    report_path = report_dir / "complete_report.md"
    report_path.write_text("old complete", encoding="utf-8")

    artifacts_dir = repo_root / "reports" / analysis_date / "artifacts" / ticker / run_id
    artifacts_dir.mkdir(parents=True)
    (artifacts_dir / "run.json").write_text(
        json.dumps(
            {
                "ticker": ticker,
                "analysis_date": analysis_date,
                "shallow_model": "MiniMax-M2.7",
                "deep_model": "gpt-5.5",
                "output_language": "Chinese",
                "returncode": 0,
            }
        ),
        encoding="utf-8",
    )
    (artifacts_dir / "discovery.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "ticker": ticker,
                "analysis_date": analysis_date,
                "report_dir": str(report_dir),
                "report_path": str(report_path),
            }
        ),
        encoding="utf-8",
    )
    (artifacts_dir / "summary.json").write_text(
        json.dumps({"sentiment_report_summary": "old sentiment"}), encoding="utf-8"
    )

    captured: dict[str, object] = {}

    class FakePropagator:
        def create_initial_state(self, company_name, trade_date, past_context=None):
            captured["initial_args"] = (company_name, trade_date, past_context)
            return {"company_of_interest": company_name, "trade_date": trade_date, "messages": []}

        def get_graph_args(self):
            return {"recursion_limit": 7}

    class FakeCompiledGraph:
        def invoke(self, state, **kwargs):
            captured["graph_state"] = dict(state)
            captured["graph_kwargs"] = kwargs
            return {
                **state,
                "sentiment_report": "new sentiment",
                "investment_debate_state": {
                    "bull_history": "new bull",
                    "bear_history": "new bear",
                    "judge_decision": "new manager",
                },
                "trader_investment_plan": "new trader",
                "risk_debate_state": {
                    "aggressive_history": "new aggressive",
                    "conservative_history": "new conservative",
                    "neutral_history": "new neutral",
                    "judge_decision": "new decision",
                },
            }

    class FakeTradingAgentsGraph:
        def __init__(self, selected_analysts, config):
            captured["selected_analysts"] = selected_analysts
            captured["config"] = config
            self.propagator = FakePropagator()
            self.graph = FakeCompiledGraph()

    def fake_save_report_to_disk(final_state, ticker_arg, save_path, error_context=None, summary_options=None):
        captured["saved_state"] = final_state
        captured["summary_options"] = summary_options
        assert ticker_arg == ticker
        assert save_path == report_dir
        assert error_context is None
        save_path.mkdir(parents=True, exist_ok=True)
        (save_path / "summary.json").write_text(
            json.dumps({"sentiment_report_summary": "new sentiment", "final_action": "BUY"}),
            encoding="utf-8",
        )
        return save_path / "complete_report.md"

    monkeypatch.setattr(module, "TradingAgentsGraph", FakeTradingAgentsGraph, raising=False)
    monkeypatch.setattr(
        module,
        "DEFAULT_CONFIG",
        {
            "llm_provider": "provider",
            "backend_url": "https://backend.invalid/v1",
            "quick_think_llm": "old-quick",
            "deep_think_llm": "old-deep",
            "output_language": "English",
            "summary_enabled": True,
            "summary_provider": "summary-provider",
            "summary_model": None,
            "summary_backend_url": "https://summary.invalid/v1",
        },
        raising=False,
    )
    monkeypatch.setattr(module, "save_report_to_disk", fake_save_report_to_disk, raising=False)

    payload = module.run_sentiment_downstream_refresh(
        repo_root=repo_root,
        ticker=ticker,
        analysis_date=analysis_date,
        shallow_model="MiniMax-M2.7",
        deep_model="gpt-5.5",
        output_language="Chinese",
        summary_model="summary-model",
        csv_path=repo_root / "reports" / analysis_date / "daily_ticker_analysis.csv",
        markdown_path=repo_root / "reports" / analysis_date / "daily_ticker_analysis.md",
    )

    assert captured["selected_analysts"] == ["social"]
    assert captured["initial_args"] == (ticker, analysis_date, "")
    assert captured["graph_kwargs"] == {"recursion_limit": 7}
    assert captured["graph_state"]["market_report"] == "old market"
    assert captured["graph_state"]["news_report"] == "old news"
    assert captured["graph_state"]["fundamentals_report"] == "old fundamentals"
    assert captured["saved_state"]["sentiment_report"] == "new sentiment"
    assert captured["summary_options"] == {
        "enabled": True,
        "provider": "summary-provider",
        "model": "summary-model",
        "base_url": "https://summary.invalid/v1",
        "output_language": "Chinese",
    }
    assert json.loads((artifacts_dir / "summary.json").read_text(encoding="utf-8"))["final_action"] == "BUY"
    assert payload["status"] == "completed"
    assert payload["report_path"] == str(report_path)
    assert payload["artifacts_dir"] == str(artifacts_dir)


def test_refresh_mode_finalizes_date_report_and_rerenders_views(monkeypatch, tmp_path: Path):
    module = _load_script("run_daily_ticker_analysis_skill")
    repo_root = tmp_path / "m1"
    analysis_date = "2026-05-30"
    ticker = "000100.SZ"
    run_id = "2026-05-30__000100.SZ__000100_20260530_090000"
    csv_path = repo_root / "reports" / analysis_date / "daily_ticker_analysis.csv"
    markdown_path = csv_path.with_suffix(".md")

    report_dir = tmp_path / "TradingAgents" / "reports" / analysis_date / "000100_20260530_090000"
    analysts_dir = report_dir / "1_analysts"
    analysts_dir.mkdir(parents=True)
    (analysts_dir / "market.md").write_text("old market", encoding="utf-8")
    (analysts_dir / "news.md").write_text("old news", encoding="utf-8")
    (analysts_dir / "fundamentals.md").write_text("old fundamentals", encoding="utf-8")
    report_path = report_dir / "complete_report.md"
    report_path.write_text("old complete", encoding="utf-8")

    artifacts_dir = repo_root / "reports" / analysis_date / "artifacts" / ticker / run_id
    artifacts_dir.mkdir(parents=True)
    (artifacts_dir / "run.json").write_text(
        json.dumps({"ticker": ticker, "analysis_date": analysis_date}), encoding="utf-8"
    )
    (artifacts_dir / "discovery.json").write_text(
        json.dumps({"run_id": run_id, "report_dir": str(report_dir), "report_path": str(report_path)}),
        encoding="utf-8",
    )
    (artifacts_dir / "summary.json").write_text("{}", encoding="utf-8")

    class FakePropagator:
        def create_initial_state(self, company_name, trade_date, past_context=""):
            return {"company_of_interest": company_name, "trade_date": trade_date, "messages": []}

        def get_graph_args(self):
            return {}

    class FakeCompiledGraph:
        def invoke(self, state, **kwargs):
            return {**state, "sentiment_report": "new sentiment"}

    class FakeTradingAgentsGraph:
        def __init__(self, selected_analysts, config):
            self.propagator = FakePropagator()
            self.graph = FakeCompiledGraph()

    def fake_save_report_to_disk(final_state, ticker_arg, save_path, error_context=None, summary_options=None):
        (save_path / "summary.json").write_text(
            json.dumps({"final_action": "BUY", "sentiment_report_summary": "new sentiment"}),
            encoding="utf-8",
        )
        return save_path / "complete_report.md"

    finalize_calls = []

    def fake_repair_finalize_if_possible(**kwargs):
        finalize_calls.append(kwargs)
        return {
            "status": "replaced",
            "markdown_path": str(markdown_path),
            "html_path": str(markdown_path.with_suffix(".html")),
        }

    monkeypatch.setattr(module, "TradingAgentsGraph", FakeTradingAgentsGraph, raising=False)
    monkeypatch.setattr(module, "save_report_to_disk", fake_save_report_to_disk, raising=False)
    monkeypatch.setattr(module, "repair_finalize_if_possible", fake_repair_finalize_if_possible)
    monkeypatch.setattr(
        module,
        "DEFAULT_CONFIG",
        {
            "llm_provider": "provider",
            "quick_think_llm": "quick",
            "deep_think_llm": "deep",
            "backend_url": None,
            "output_language": "Chinese",
            "summary_enabled": True,
            "summary_provider": None,
            "summary_model": None,
            "summary_backend_url": None,
        },
        raising=False,
    )

    payload = module.run_sentiment_downstream_refresh(
        repo_root=repo_root,
        ticker=ticker,
        analysis_date=analysis_date,
        shallow_model="MiniMax-M2.7",
        deep_model="gpt-5.5",
        output_language="Chinese",
        summary_model=None,
        csv_path=csv_path,
        markdown_path=markdown_path,
    )

    assert finalize_calls == [
        {
            "csv_path": csv_path,
            "markdown_path": markdown_path,
            "artifacts_dir": str(artifacts_dir),
            "write_artifact_result": True,
        }
    ]
    assert payload["csv_status"] == "replaced"
    assert payload["markdown_path"] == str(markdown_path)
    assert payload["artifacts_dir"] == str(artifacts_dir)


def test_main_refresh_mode_syncs_root_report_after_date_report_refresh(monkeypatch, tmp_path: Path, capsys):
    module = _load_script("run_daily_ticker_analysis_skill")
    repo_root = tmp_path / "m1"
    analysis_date = "2026-05-30"
    csv_path = repo_root / "reports" / analysis_date / "daily_ticker_analysis.csv"
    markdown_path = csv_path.with_suffix(".md")
    root_csv_path = repo_root / "reports" / "daily_ticker_analysis.csv"
    root_markdown_path = root_csv_path.with_suffix(".md")
    artifacts_dir = repo_root / "reports" / analysis_date / "artifacts" / "000100.SZ" / "run-1"

    calls: dict[str, object] = {}

    def fake_refresh_batch(**kwargs):
        calls["refresh_batch"] = kwargs
        return [
            {
                "ticker": "000100.SZ",
                "status": "completed",
                "artifacts_dir": str(artifacts_dir),
                "error": "",
            }
        ]

    def fake_verify_ticker(**kwargs):
        calls.setdefault("verify", []).append(kwargs)
        return {
            "ticker": kwargs["ticker"],
            "csv_rows": 1,
            "report_path": "report.md",
            "artifacts_dir": str(artifacts_dir),
            "missing": [],
        }

    def fake_sync_root_report_from_verifications(**kwargs):
        calls["root_sync"] = kwargs
        return [{"ticker": "000100.SZ", "status": "replaced"}]

    monkeypatch.setattr(module, "refresh_batch", fake_refresh_batch, raising=False)
    monkeypatch.setattr(module, "verify_ticker", fake_verify_ticker)
    monkeypatch.setattr(module, "sync_root_report_from_verifications", fake_sync_root_report_from_verifications)

    result = module.main(
        [
            "--repo-root",
            str(repo_root),
            "--ticker",
            "000100.SZ",
            "--analysis-date",
            analysis_date,
            "--refresh-sentiment-downstream-only",
            "--max-concurrency",
            "4",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert result == 0
    assert calls["refresh_batch"] == {
        "tickers": ["000100.SZ"],
        "repo_root": repo_root,
        "analysis_date": analysis_date,
        "shallow_model": "MiniMax-M2.7",
        "deep_model": "gpt-5.5",
        "output_language": "Chinese",
        "summary_model": None,
        "csv_path": csv_path,
        "markdown_path": markdown_path,
        "max_concurrency": 4,
    }
    assert calls["root_sync"] == {
        "root_csv_path": root_csv_path,
        "root_markdown_path": root_markdown_path,
        "verifications": [
            {
                "ticker": "000100.SZ",
                "csv_rows": 1,
                "report_path": "report.md",
                "artifacts_dir": str(artifacts_dir),
                "missing": [],
            }
        ],
    }
    assert payload["items"][0]["status"] == "completed"
    assert payload["root_sync"] == [{"ticker": "000100.SZ", "status": "replaced"}]


def test_main_refresh_mode_skips_root_sync_with_no_sync_root(monkeypatch, tmp_path: Path, capsys):
    module = _load_script("run_daily_ticker_analysis_skill")
    repo_root = tmp_path / "m1"
    analysis_date = "2026-05-30"
    artifacts_dir = repo_root / "reports" / analysis_date / "artifacts" / "000100.SZ" / "run-1"

    monkeypatch.setattr(
        module,
        "refresh_batch",
        lambda **kwargs: [
            {
                "ticker": "000100.SZ",
                "status": "completed",
                "artifacts_dir": str(artifacts_dir),
                "error": "",
            }
        ],
        raising=False,
    )
    monkeypatch.setattr(
        module,
        "verify_ticker",
        lambda **kwargs: {
            "ticker": kwargs["ticker"],
            "csv_rows": 1,
            "report_path": "report.md",
            "artifacts_dir": str(artifacts_dir),
            "missing": [],
        },
    )

    def fail_root_sync(**kwargs):
        raise AssertionError("root sync should be skipped")

    monkeypatch.setattr(module, "sync_root_report_from_verifications", fail_root_sync)

    result = module.main(
        [
            "--repo-root",
            str(repo_root),
            "--ticker",
            "000100.SZ",
            "--analysis-date",
            analysis_date,
            "--refresh-sentiment-downstream-only",
            "--no-sync-root",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["root_sync"] == []


def test_refresh_mode_rejects_verify_only(tmp_path: Path):
    module = _load_script("run_daily_ticker_analysis_skill")

    with pytest.raises(ValueError, match="--refresh-sentiment-downstream-only cannot be combined with --verify-only"):
        module.main(
            [
                "--repo-root",
                str(tmp_path),
                "--ticker",
                "000100.SZ",
                "--analysis-date",
                "2026-05-30",
                "--refresh-sentiment-downstream-only",
                "--verify-only",
            ]
        )


def test_render_html_generates_valid_html_file(tmp_path: Path):
    html_module = _load_script("render_tradingagents_daily_html")
    csv_path = tmp_path / "daily_ticker_analysis.csv"
    html_path = tmp_path / "daily_ticker_analysis.html"

    # Write a mock CSV
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "analysis_date",
                "ticker",
                "ticker_name",
                "final_action",
                "direction",
                "confidence",
                "time_horizon",
                "status",
                "report_path",
                "run_id",
                "shallow_model",
                "deep_model",
                "runtime_log_path",
                "message_tool_log_path",
                "error",
                "decision_rationale",
                "key_catalysts",
                "key_risks",
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
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "analysis_date": "2026-05-28",
                "ticker": "000001.SZ",
                "ticker_name": "平安银行",
                "final_action": "BUY",
                "direction": "LONG",
                "confidence": "HIGH",
                "time_horizon": "SHORT",
                "status": "completed",
                "report_path": "reports/2026-05-28/000001.SZ/complete_report.md",
                "run_id": "run_123",
                "shallow_model": "MiniMax-M2.7",
                "deep_model": "gpt-5.5",
                "runtime_log_path": "logs/000001.SZ/2026-05-28/runtime.log",
                "message_tool_log_path": "logs/000001.SZ/2026-05-28/message_tool.log",
                "error": "",
                "decision_rationale": "Strong fundamentals and news catalyst.",
                "key_catalysts": '["earnings beat", "product launch"]',
                "key_risks": '["regulatory supply chain issues"]',
                "market_report_summary": "Bullish trend line.",
                "sentiment_report_summary": "Positive social sentiment.",
                "news_report_summary": "Macro environment stable.",
                "fundamentals_report_summary": "Undervalued P/E ratio.",
                "bull_case_summary": "Strong growth.",
                "bear_case_summary": "Valuation risk.",
                "research_manager_summary": "Agree with long case.",
                "trader_plan_summary": "Entry at 180.",
                "risk_aggressive_summary": "Go max leverage.",
                "risk_conservative_summary": "Keep stops close.",
                "risk_neutral_summary": "Standard sizing.",
                "portfolio_manager_summary": "Buy action confirmed.",
            }
        )

        writer.writerow(
            {
                "analysis_date": "2026-05-25",
                "ticker": "000001.SZ",
                "ticker_name": "平安银行",
                "final_action": "减持",
                "direction": "中性偏空",
                "confidence": "LOW",
                "time_horizon": "MEDIUM",
                "status": "completed",
                "report_path": "reports/2026-05-25/000001.SZ/complete_report.md",
                "run_id": "run_790",
                "shallow_model": "MiniMax-M2.7",
                "deep_model": "gpt-5.5",
                "runtime_log_path": "logs/000001.SZ/2026-05-25/runtime.log",
                "message_tool_log_path": "logs/000001.SZ/2026-05-25/message_tool.log",
                "error": "",
                "decision_rationale": "Weakening setup.",
                "key_catalysts": '[]',
                "key_risks": '[]',
                "market_report_summary": "Soft trend.",
                "sentiment_report_summary": "Weak sentiment.",
                "news_report_summary": "Minor pressure.",
                "fundamentals_report_summary": "Slightly stretched.",
                "bull_case_summary": "Limited support.",
                "bear_case_summary": "Momentum fading.",
                "research_manager_summary": "Trim exposure.",
                "trader_plan_summary": "Reduce position.",
                "risk_aggressive_summary": "Avoid leverage.",
                "risk_conservative_summary": "Reduce sizing.",
                "risk_neutral_summary": "Monitor downside.",
                "portfolio_manager_summary": "Reduce action confirmed.",
            }
        )

        writer.writerow(
            {
                "analysis_date": "2026-05-26",
                "ticker": "000001.SZ",
                "ticker_name": "平安银行",
                "final_action": "持有",
                "direction": "中性",
                "confidence": "中等",
                "time_horizon": "MEDIUM",
                "status": "completed",
                "report_path": "reports/2026-05-26/000001.SZ/complete_report.md",
                "run_id": "run_789",
                "shallow_model": "MiniMax-M2.7",
                "deep_model": "gpt-5.5",
                "runtime_log_path": "logs/000001.SZ/2026-05-26/runtime.log",
                "message_tool_log_path": "logs/000001.SZ/2026-05-26/message_tool.log",
                "error": "",
                "decision_rationale": "Sideways setup.",
                "key_catalysts": '[]',
                "key_risks": '[]',
                "market_report_summary": "Neutral trend.",
                "sentiment_report_summary": "Mixed sentiment.",
                "news_report_summary": "No major catalyst.",
                "fundamentals_report_summary": "Fair valuation.",
                "bull_case_summary": "Stable demand.",
                "bear_case_summary": "Limited upside.",
                "research_manager_summary": "Wait for clarity.",
                "trader_plan_summary": "Stay flat.",
                "risk_aggressive_summary": "No leverage.",
                "risk_conservative_summary": "Keep cash.",
                "risk_neutral_summary": "Monitor only.",
                "portfolio_manager_summary": "Hold action confirmed.",
            }
        )

        writer.writerow(
            {
                "analysis_date": "2026-05-24",
                "ticker": "000001.SZ",
                "ticker_name": "平安银行",
                "final_action": "持有",
                "direction": "中性",
                "confidence": "",
                "time_horizon": "MEDIUM",
                "status": "completed",
                "report_path": "reports/2026-05-24/000001.SZ/complete_report.md",
                "run_id": "run_788",
                "shallow_model": "MiniMax-M2.7",
                "deep_model": "gpt-5.5",
                "runtime_log_path": "logs/000001.SZ/2026-05-24/runtime.log",
                "message_tool_log_path": "logs/000001.SZ/2026-05-24/message_tool.log",
                "error": "",
                "decision_rationale": "Insufficient confidence.",
                "key_catalysts": '[]',
                "key_risks": '[]',
                "market_report_summary": "No clear signal.",
                "sentiment_report_summary": "Muted sentiment.",
                "news_report_summary": "No major news.",
                "fundamentals_report_summary": "Neutral valuation.",
                "bull_case_summary": "Limited upside.",
                "bear_case_summary": "Limited downside.",
                "research_manager_summary": "Wait for data.",
                "trader_plan_summary": "No action.",
                "risk_aggressive_summary": "No leverage.",
                "risk_conservative_summary": "Hold cash.",
                "risk_neutral_summary": "Observe only.",
                "portfolio_manager_summary": "Unknown confidence hold.",
            }
        )

        writer.writerow(
            {
                "analysis_date": "2026-05-27",
                "ticker": "601857.SS",
                "ticker_name": "中国石油",
                "final_action": "卖出",
                "direction": "看空",
                "confidence": "82%",
                "time_horizon": "LONG",
                "status": "completed",
                "report_path": "reports/2026-05-27/601857.SS/complete_report.md",
                "run_id": "run_456",
                "shallow_model": "MiniMax-M2.7",
                "deep_model": "gpt-5.5",
                "runtime_log_path": "logs/601857.SS/2026-05-27/runtime.log",
                "message_tool_log_path": "logs/601857.SS/2026-05-27/message_tool.log",
                "error": "",
                "decision_rationale": "Weak setup and downside catalyst.",
                "key_catalysts": '["margin pressure"]',
                "key_risks": '["short squeeze"]',
                "market_report_summary": "Bearish reversal.",
                "sentiment_report_summary": "Negative social sentiment.",
                "news_report_summary": "Macro pressure rising.",
                "fundamentals_report_summary": "Growth slowing.",
                "bull_case_summary": "Cloud resilience.",
                "bear_case_summary": "Multiple compression.",
                "research_manager_summary": "Agree with short case.",
                "trader_plan_summary": "Entry below support.",
                "risk_aggressive_summary": "Short with tight stops.",
                "risk_conservative_summary": "Small sizing.",
                "risk_neutral_summary": "Standard short sizing.",
                "portfolio_manager_summary": "Sell action confirmed.",
            }
        )

    payload = html_module.render_html(csv_path, html_path)
    assert payload["status"] == "rendered"
    assert payload["row_count"] == 5
    assert html_path.exists()

    html_content = html_path.read_text(encoding="utf-8")
    assert "<title>TradingAgents 每日标的分析看板</title>" in html_content
    assert "000001.SZ（平安银行 / PAYH）" in html_content
    assert "601857.SS（中国石油 / ZGSY）" in html_content
    assert "买入/增持(+1)" in html_content
    assert "earnings beat" in html_content
    assert "product launch" in html_content
    assert "Strong fundamentals and news catalyst." in html_content
    assert "市场技术面" in html_content
    assert "Bullish trend line." in html_content
    assert "动作方向折线图" in html_content
    assert "指标时间热力图" in html_content
    assert "line-chart" in html_content
    assert "line-series" in html_content
    assert "line-point" in html_content
    assert "line-point-star" in html_content
    assert "line-point-triangle" in html_content
    assert "line-point-circle" in html_content
    assert "line-point-hollow" in html_content
    assert "line-confidence-legend" in html_content
    assert "高置信度：五角星" in html_content
    assert "中置信度：三角形" in html_content
    assert "未知置信度：空心圆点" in html_content
    assert "signal-small-multiples" in html_content
    assert "ticker-line-grid" in html_content
    assert html_content.count('class="ticker-line-card"') == 2
    assert html_content.index("000001.SZ（平安银行 / PAYH）") < html_content.index("601857.SS（中国石油 / ZGSY）")
    assert "每个标的一张图" in html_content
    assert "signal-positive" in html_content
    assert "signal-negative" in html_content
    assert "signal-neutral" in html_content
    assert "同一标的的已有观测点会连成折线" in html_content
    assert "红色偏多、绿色偏空、灰色中性" in html_content
    assert "点颜色表示该点信号方向" in html_content
    assert "当前展示前" not in html_content
    assert 'class="line-series series-color-' not in html_content
    assert "数值和=+2.0" in html_content
    assert "数值和=+0.0" in html_content
    assert "置信度=85%" in html_content
    assert "置信度=25%" in html_content
    assert "metric-matrix" in html_content
    assert "matrix-cell" in html_content
    assert "2026-05-28" in html_content
    assert "2026-05-27" in html_content
    assert "卖出/减持(-1)" in html_content
    assert "看多(+1)" in html_content
    assert "看空(-1)" in html_content
    assert ".action-buy { background: #fef2f2; color: #991b1b; }" in html_content
    assert ".action-sell { background: #ecfdf5; color: #166534; }" in html_content
    assert "background-color: #fef2f2;\n            color: var(--buy);" in html_content
    assert "background-color: #ecfdf5;\n            color: var(--sell);" in html_content
    assert "82%" in html_content
    assert "82.0%" not in html_content
    assert "<th>详情/比较</th>" in html_content
    assert 'href="#ticker-000001-sz"' in html_content
    assert 'href="#decision-000001-sz-2026-05-28-run_123"' in html_content
    assert 'id="ticker-000001-sz"' in html_content
    assert 'id="decision-000001-sz-2026-05-28-run_123"' in html_content
    assert html_content.count('class="ticker-detail-group"') == 2
    assert 'class="ticker-detail-group" id="ticker-000001-sz"' in html_content
    assert 'class="ticker-detail-group" id="ticker-000001-sz" data-ticker="000001.SZ" open' not in html_content
    assert "决策比较" in html_content
    assert 'class="compare-checkbox"' in html_content
    assert 'id="compareCount"' in html_content
    assert 'id="compareClearButton"' in html_content
    assert 'id="compareTableBody"' in html_content
    assert "document.querySelectorAll('.ticker-detail-group')" in html_content
    assert "syncCompareCheckboxes" in html_content
    assert "compareTableBody.replaceChildren()" in html_content

    first_row = html_content.index('data-ticker="000001.SZ" data-date="2026-05-28"')
    second_row = html_content.index('data-ticker="601857.SS" data-date="2026-05-27"')
    third_row = html_content.index('data-ticker="000001.SZ" data-date="2026-05-26"')
    assert first_row < second_row < third_row

def test_render_html_links_windows_absolute_report_path(tmp_path: Path):
    html_module = _load_script("render_tradingagents_daily_html")
    csv_path = tmp_path / "daily_ticker_analysis.csv"
    html_path = tmp_path / "daily_ticker_analysis.html"

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["analysis_date", "ticker", "report_path", "status"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "analysis_date": "2026-05-28",
                "ticker": "000001.SZ",
                "report_path": r"D:\Tools\TradingAgents\reports\2026-05-28\000001.SZ_20260528_090000\complete_report.md",
                "status": "completed",
            }
        )

    html_module.render_html(csv_path, html_path)
    html_content = html_path.read_text(encoding="utf-8")

    assert '>报告</a>' in html_content
    assert 'D:/Tools/TradingAgents/reports/2026-05-28/000001.SZ_20260528_090000/complete_report.md' in html_content


    html_module = _load_script("render_tradingagents_daily_html")
    csv_path = tmp_path / "daily_ticker_analysis.csv"
    html_path = tmp_path / "daily_ticker_analysis.html"

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["analysis_date", "ticker", "final_action", "direction", "confidence", "time_horizon"],
        )
        writer.writeheader()

    payload = html_module.render_html(csv_path, html_path)
    html_content = html_path.read_text(encoding="utf-8")

    assert payload["row_count"] == 0
    assert "总记录数" in html_content
    assert "日期数" in html_content
    assert "标的数" in html_content
    assert "动作方向折线图" in html_content
    assert "指标时间热力图" in html_content
    assert "暂无数据" in html_content


def test_render_html_escapes_untrusted_values(tmp_path: Path):
    html_module = _load_script("render_tradingagents_daily_html")
    csv_path = tmp_path / "daily_ticker_analysis.csv"
    html_path = tmp_path / "daily_ticker_analysis.html"

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "analysis_date",
                "ticker",
                "final_action",
                "direction",
                "confidence",
                "time_horizon",
                "status",
                "report_path",
                "run_id",
                "shallow_model",
                "deep_model",
                "runtime_log_path",
                "message_tool_log_path",
                "error",
                "decision_rationale",
                "key_catalysts",
                "key_risks",
                "market_report_summary",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "analysis_date": "2026-05-28",
                "ticker": 'AA\" onclick=\"alert(1)',
                "final_action": "BUY<script>alert(1)</script>",
                "direction": "LONG",
                "confidence": "HIGH",
                "time_horizon": "SHORT",
                "status": "completed",
                "report_path": "javascript:alert(6)",
                "run_id": "<script>alert(2)</script>",
                "shallow_model": "MiniMax-M2.7",
                "deep_model": "gpt-5.5",
                "runtime_log_path": "data:text/html,<script>alert(7)</script>",
                "message_tool_log_path": "https://example.com/log.txt",
                "error": "<b>boom</b>",
                "decision_rationale": "<img src=x onerror=alert(3)>",
                "key_catalysts": json.dumps(["<script>alert(4)</script>"]),
                "key_risks": json.dumps(['\" onmouseover=\"alert(5)']),
                "market_report_summary": "<iframe></iframe>",
            }
        )

    html_module.render_html(csv_path, html_path)
    html_content = html_path.read_text(encoding="utf-8")

    assert "<script>alert" not in html_content
    assert "onclick=\"alert" not in html_content
    assert "<img src=x onerror=alert" not in html_content
    assert "<iframe>" not in html_content
    assert "&lt;script&gt;alert" in html_content
    assert "AA&quot; onclick=&quot;alert(1)" in html_content
    assert 'href="javascript:' not in html_content
    assert 'href="data:' not in html_content
    assert 'data-compare-id="decision-aa-onclick-alert-1--2026-05-28--script-alert-2-script"' in html_content
    assert 'id="decision-aa-onclick-alert-1--2026-05-28--script-alert-2-script"' in html_content



def test_sync_root_report_from_verifications_replaces_rows_and_renders_views(tmp_path: Path):
    module = _load_script("run_daily_ticker_analysis_skill")
    repo_root = tmp_path / "m1"
    analysis_date = "2026-05-30"
    ticker = "601857.SS"
    run_id = "2026-05-30__601857.SS__601857_20260530_090000"
    artifacts_dir = repo_root / "reports" / analysis_date / "artifacts" / ticker / run_id
    artifacts_dir.mkdir(parents=True)

    report_dir = tmp_path / "TradingAgents" / "reports" / analysis_date / "601857_20260530_090000"
    report_dir.mkdir(parents=True)
    report_path = report_dir / "complete_report.md"
    report_path.write_text("report", encoding="utf-8")

    run_payload = {
        "ticker": ticker,
        "analysis_date": analysis_date,
        "shallow_model": "MiniMax-M2.7",
        "deep_model": "gpt-5.5",
        "output_language": "Chinese",
        "returncode": 0,
    }
    discovery_payload = {
        "run_id": run_id,
        "ticker": ticker,
        "analysis_date": analysis_date,
        "report_dir": str(report_dir),
        "report_path": str(report_path),
        "runtime_log_path": str(tmp_path / "runtime.log"),
        "message_tool_log_path": str(tmp_path / "message_tool.log"),
    }
    summary_payload = {
        "status": "completed",
        "final_action": "BUY",
        "direction": "LONG",
        "confidence": "HIGH",
        "decision_rationale": "root sync rationale",
    }
    (artifacts_dir / "run.json").write_text(json.dumps(run_payload), encoding="utf-8")
    (artifacts_dir / "discovery.json").write_text(json.dumps(discovery_payload), encoding="utf-8")
    (artifacts_dir / "summary.json").write_text(json.dumps(summary_payload), encoding="utf-8")

    root_csv_path = repo_root / "reports" / "daily_ticker_analysis.csv"
    root_markdown_path = root_csv_path.with_suffix(".md")
    root_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with root_csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["analysis_date", "ticker", "shallow_model", "deep_model", "final_action"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "analysis_date": analysis_date,
                "ticker": ticker,
                "shallow_model": "MiniMax-M2.7",
                "deep_model": "gpt-5.5",
                "final_action": "SELL",
            }
        )

    results = module.sync_root_report_from_verifications(
        root_csv_path=root_csv_path,
        root_markdown_path=root_markdown_path,
        verifications=[{"ticker": ticker, "artifacts_dir": str(artifacts_dir)}],
    )

    with root_csv_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["final_action"] == "BUY"
    assert results[0]["status"] == "replaced"
    assert root_markdown_path.exists()
    assert root_markdown_path.with_suffix(".html").exists()
    assert "root sync rationale" in root_markdown_path.read_text(encoding="utf-8")
    assert "601857.SS" in root_markdown_path.with_suffix(".html").read_text(encoding="utf-8")


def test_sync_root_report_from_verifications_skips_missing_artifacts(tmp_path: Path):
    module = _load_script("run_daily_ticker_analysis_skill")
    root_csv_path = tmp_path / "reports" / "daily_ticker_analysis.csv"
    root_markdown_path = root_csv_path.with_suffix(".md")

    results = module.sync_root_report_from_verifications(
        root_csv_path=root_csv_path,
        root_markdown_path=root_markdown_path,
        verifications=[{"ticker": "601857.SS", "artifacts_dir": ""}],
    )

    assert results == [
        {
            "ticker": "601857.SS",
            "status": "skipped_missing_artifacts",
            "csv_path": str(root_csv_path),
            "markdown_path": str(root_markdown_path),
            "html_path": str(root_markdown_path.with_suffix(".html")),
        }
    ]
    assert not root_csv_path.exists()
    module = _load_script("migrate_docs_tradingagents_to_reports")
    source_dir = tmp_path / "docs" / "tradingagents"
    source_dir.mkdir(parents=True)
    source_csv = source_dir / "daily_ticker_analysis.csv"
    with source_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["analysis_date", "ticker", "shallow_model", "deep_model"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "analysis_date": "2026-05-30",
                "ticker": "601857.SS",
                "shallow_model": "MiniMax-M2.7",
                "deep_model": "gpt-5.5",
            }
        )

    payload = module.migrate_docs_tradingagents_to_reports(
        source_dir=source_dir,
        target_root=tmp_path / "reports",
    )

    target_csv = tmp_path / "reports" / "2026-05-30" / "daily_ticker_analysis.csv"
    assert payload["status"] == "dry_run"
    assert payload["csv"]["2026-05-30"]["appended_rows"] == 1
    assert not target_csv.exists()


def test_migrate_docs_tradingagents_to_reports_cli_requires_execute_to_write(tmp_path: Path):
    module = _load_script("migrate_docs_tradingagents_to_reports")
    source_dir = tmp_path / "docs" / "tradingagents"
    target_root = tmp_path / "reports"
    source_dir.mkdir(parents=True)
    source_csv = source_dir / "daily_ticker_analysis.csv"
    with source_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["analysis_date", "ticker", "shallow_model", "deep_model"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "analysis_date": "2026-05-30",
                "ticker": "601857.SS",
                "shallow_model": "MiniMax-M2.7",
                "deep_model": "gpt-5.5",
            }
        )

    assert module.main(
        ["--source-dir", str(source_dir), "--target-root", str(target_root)]
    ) == 0
    target_csv = target_root / "2026-05-30" / "daily_ticker_analysis.csv"
    assert not target_csv.exists()

    assert module.main(
        ["--source-dir", str(source_dir), "--target-root", str(target_root), "--execute"]
    ) == 0
    assert target_csv.exists()


def test_migrate_docs_tradingagents_to_reports_dry_run_does_not_write(tmp_path: Path):
    module = _load_script("migrate_docs_tradingagents_to_reports")
    source_dir = tmp_path / "docs" / "tradingagents"
    source_dir.mkdir(parents=True)
    source_csv = source_dir / "daily_ticker_analysis.csv"
    with source_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["analysis_date", "ticker", "shallow_model", "deep_model", "status"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "analysis_date": "2026-05-30",
                "ticker": "601857.SS",
                "shallow_model": "MiniMax-M2.7",
                "deep_model": "gpt-5.5",
                "status": "completed",
            }
        )

    payload = module.migrate_docs_tradingagents_to_reports(
        source_dir=source_dir,
        target_root=tmp_path / "reports",
        dry_run=True,
    )

    target_csv = tmp_path / "reports" / "2026-05-30" / "daily_ticker_analysis.csv"
    assert payload["status"] == "dry_run"
    assert payload["csv"]["2026-05-30"]["appended_rows"] == 1
    assert not target_csv.exists()


def test_migrate_docs_tradingagents_to_reports_merges_csv_and_renders_views(tmp_path: Path):
    module = _load_script("migrate_docs_tradingagents_to_reports")
    source_dir = tmp_path / "docs" / "tradingagents"
    source_dir.mkdir(parents=True)
    source_csv = source_dir / "daily_ticker_analysis.csv"
    with source_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["analysis_date", "ticker", "shallow_model", "deep_model", "status", "final_action"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "analysis_date": "2026-05-30",
                "ticker": "601857.SS",
                "shallow_model": "MiniMax-M2.7",
                "deep_model": "gpt-5.5",
                "status": "completed",
                "final_action": "BUY",
            }
        )
        writer.writerow(
            {
                "analysis_date": "2026-05-30",
                "ticker": "601857.SS",
                "shallow_model": "MiniMax-M2.7",
                "deep_model": "gpt-5.5",
                "status": "completed",
                "final_action": "SELL",
            }
        )
        writer.writerow(
            {
                "analysis_date": "2026-05-29",
                "ticker": "002332.SZ",
                "shallow_model": "MiniMax-M2.7",
                "deep_model": "gpt-5.5",
                "status": "completed",
                "final_action": "HOLD",
            }
        )

    existing_artifact = tmp_path / "reports" / "2026-05-30" / "artifacts" / "601857.SS" / "existing"
    existing_artifact.mkdir(parents=True)
    source_existing = source_dir / "artifacts" / "2026-05-30" / "601857.SS" / "existing"
    source_existing.mkdir(parents=True)
    (source_existing / "run.json").write_text("source", encoding="utf-8")
    new_artifact = source_dir / "artifacts" / "2026-05-29" / "002332.SZ" / "new-run"
    new_artifact.mkdir(parents=True)
    (new_artifact / "run.json").write_text("new", encoding="utf-8")

    payload = module.migrate_docs_tradingagents_to_reports(
        source_dir=source_dir,
        target_root=tmp_path / "reports",
        dry_run=False,
    )
    target_csv = tmp_path / "reports" / "2026-05-30" / "daily_ticker_analysis.csv"
    with target_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["final_action"] == "BUY"
    assert (tmp_path / "reports" / "2026-05-30" / "daily_ticker_analysis.md").exists()
    html_path = tmp_path / "reports" / "2026-05-30" / "daily_ticker_analysis.html"
    assert html_path.exists()
    assert "601857.SS" in html_path.read_text(encoding="utf-8")
    assert (tmp_path / "reports" / "2026-05-29" / "artifacts" / "002332.SZ" / "new-run" / "run.json").exists()
    assert payload["artifacts"] == {"copied": 1, "skipped_existing": 1}
