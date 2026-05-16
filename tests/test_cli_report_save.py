from __future__ import annotations

import json

from cli import main
from cli.main import save_report_to_disk


def _minimal_final_state() -> dict[str, object]:
    return {
        "market_report": "市场报告",
        "trader_investment_plan": "交易计划",
        "risk_debate_state": {"judge_decision": "组合经理决策"},
    }


def test_save_report_to_disk_writes_complete_report_and_summary(tmp_path, monkeypatch):
    def fake_generate_report_summary(report_path, **kwargs):
        assert report_path == tmp_path / "complete_report.md"
        assert kwargs["model"] == "MiniMax-M2.7"
        return {"status": "completed", "error": "", "final_action": "持有"}

    monkeypatch.setattr(main, "generate_report_summary", fake_generate_report_summary)

    report_path = save_report_to_disk(
        _minimal_final_state(),
        "399006.SZ",
        tmp_path,
        summary_options={
            "enabled": True,
            "provider": "minimax-cn",
            "model": "MiniMax-M2.7",
            "base_url": None,
            "output_language": "Chinese",
        },
    )

    assert report_path == tmp_path / "complete_report.md"
    assert report_path.exists()
    summary_payload = json.loads(
        (tmp_path / "summary.json").read_text(encoding="utf-8")
    )
    assert summary_payload["status"] == "completed"
    assert summary_payload["final_action"] == "持有"


def test_save_report_to_disk_preserves_report_when_summary_raises(
    tmp_path, monkeypatch
):
    def raise_summary(*args, **kwargs):
        raise RuntimeError("summary failed")

    monkeypatch.setattr(main, "generate_report_summary", raise_summary)

    report_path = save_report_to_disk(
        _minimal_final_state(),
        "399006.SZ",
        tmp_path,
        summary_options={
            "enabled": True,
            "provider": "openai",
            "model": "gpt-5.4-mini",
        },
    )

    assert report_path.exists()
    summary_payload = json.loads(
        (tmp_path / "summary.json").read_text(encoding="utf-8")
    )
    assert summary_payload["status"] == "pending_summary"
    assert "summary failed" in summary_payload["error"]
    assert (tmp_path / "summary_error.md").exists()


def test_save_report_to_disk_skips_summary_when_disabled(tmp_path, monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("summary should be disabled")

    monkeypatch.setattr(main, "generate_report_summary", fail_if_called)

    report_path = save_report_to_disk(
        _minimal_final_state(),
        "399006.SZ",
        tmp_path,
        summary_options={
            "enabled": False,
            "provider": "openai",
            "model": "gpt-5.4-mini",
        },
    )

    assert report_path.exists()
    assert not (tmp_path / "summary.json").exists()
