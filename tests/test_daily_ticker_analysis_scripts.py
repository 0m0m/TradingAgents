from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _load_script(module_name: str):
    module_path = SCRIPTS_DIR / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_run_context_uses_tradingagents_relative_reports_root(
    monkeypatch, tmp_path: Path
):
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
        / "docs"
        / "tradingagents"
        / "artifacts"
        / analysis_date
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

    csv_path = repo_root / "docs" / "tradingagents" / "daily_ticker_analysis.csv"
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
                "ticker": "AAPL",
                "final_action": "BUY",
                "direction": "LONG",
                "confidence": "HIGH",
                "time_horizon": "SHORT",
                "status": "completed",
                "report_path": "reports/2026-05-28/AAPL/complete_report.md",
                "run_id": "run_123",
                "shallow_model": "MiniMax-M2.7",
                "deep_model": "gpt-5.5",
                "runtime_log_path": "logs/AAPL/2026-05-28/runtime.log",
                "message_tool_log_path": "logs/AAPL/2026-05-28/message_tool.log",
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

    payload = html_module.render_html(csv_path, html_path)
    assert payload["status"] == "rendered"
    assert payload["row_count"] == 1
    assert html_path.exists()

    html_content = html_path.read_text(encoding="utf-8")
    assert "<title>TradingAgents 每日标的分析看板</title>" in html_content
    assert "AAPL" in html_content
    assert "BUY" in html_content
    assert "earnings beat" in html_content
    assert "product launch" in html_content
    assert "Strong fundamentals and news catalyst." in html_content
    assert "市场技术面" in html_content
    assert "Bullish trend line." in html_content


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
                "report_path": 'reports/\"bad\"/complete_report.md',
                "run_id": "<script>alert(2)</script>",
                "shallow_model": "MiniMax-M2.7",
                "deep_model": "gpt-5.5",
                "runtime_log_path": "",
                "message_tool_log_path": "",
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
