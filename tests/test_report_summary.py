from __future__ import annotations

import json


from tradingagents.reporting import summary
from tradingagents.reporting.summary import (
    SUMMARY_FIELDS,
    ReportSummary,
    build_error_summary,
    generate_report_summary,
    normalize_summary_payload,
    save_summary_artifacts,
)


def test_normalize_summary_payload_fills_missing_fields():
    payload = normalize_summary_payload({"final_action": "买入"})

    assert payload["final_action"] == "买入"
    assert payload["key_catalysts"] == []
    assert payload["key_risks"] == []
    assert payload["status"] == "completed"
    assert payload["error"] == ""
    for field in SUMMARY_FIELDS:
        assert field in payload


def test_build_error_summary_marks_pending_summary():
    payload = build_error_summary("模型输出不可解析")

    assert payload["status"] == "pending_summary"
    assert payload["error"] == "模型输出不可解析"
    assert payload["key_catalysts"] == []
    assert payload["key_risks"] == []
    assert payload["final_action"] == ""


class _Client:
    def __init__(self, llm):
        self._llm = llm

    def get_llm(self):
        return self._llm


class _StructuredRunnable:
    def invoke(self, prompt):
        return ReportSummary(
            final_action="买入",
            direction="看多",
            confidence="高",
            time_horizon="短期",
            key_catalysts=["资金流入"],
            key_risks=["波动放大"],
            decision_rationale="趋势改善",
        )


class _StructuredLLM:
    def with_structured_output(self, schema):
        assert schema is ReportSummary
        return _StructuredRunnable()

    def invoke(self, prompt):
        raise AssertionError("structured success should not invoke free text")


def test_generate_report_summary_prefers_structured_output(tmp_path, monkeypatch):
    report_path = tmp_path / "complete_report.md"
    report_path.write_text("# report\n结论：买入。", encoding="utf-8")

    calls = []

    def fake_create_llm_client(**kwargs):
        calls.append(kwargs)
        return _Client(_StructuredLLM())

    monkeypatch.setattr(summary, "create_llm_client", fake_create_llm_client)

    payload = generate_report_summary(
        report_path,
        provider="openai",
        model="MiniMax-M2.7",
        base_url="https://example.invalid/v1",
        output_language="Chinese",
    )

    assert calls == [
        {
            "provider": "openai",
            "model": "MiniMax-M2.7",
            "base_url": "https://example.invalid/v1",
        }
    ]
    assert payload["status"] == "completed"
    assert payload["final_action"] == "买入"
    assert payload["key_catalysts"] == ["资金流入"]


class _TextResponse:
    def __init__(self, content: str):
        self.content = content


class _FallbackLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def with_structured_output(self, schema):
        raise NotImplementedError("no structured output")

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return _TextResponse(self.responses.pop(0))


def test_generate_report_summary_repairs_invalid_json(tmp_path, monkeypatch):
    report_path = tmp_path / "complete_report.md"
    report_path.write_text("# report\n结论：持有。", encoding="utf-8")
    llm = _FallbackLLM(
        [
            "不是 JSON",
            json.dumps(
                {"final_action": "持有", "key_risks": ["成交不足"]}, ensure_ascii=False
            ),
        ]
    )
    monkeypatch.setattr(summary, "create_llm_client", lambda **kwargs: _Client(llm))

    payload = generate_report_summary(
        report_path, provider="openai", model="gpt-5.4-mini"
    )

    assert payload["status"] == "completed"
    assert payload["final_action"] == "持有"
    assert payload["key_risks"] == ["成交不足"]
    assert len(llm.prompts) == 2
    assert "上一次回答没有包含可解析 JSON" in llm.prompts[1]


def test_generate_report_summary_returns_pending_when_repair_fails(
    tmp_path, monkeypatch
):
    report_path = tmp_path / "complete_report.md"
    report_path.write_text("# report", encoding="utf-8")
    llm = _FallbackLLM(["bad", "still bad"])
    monkeypatch.setattr(summary, "create_llm_client", lambda **kwargs: _Client(llm))

    payload = generate_report_summary(
        report_path, provider="openai", model="gpt-5.4-mini"
    )

    assert payload["status"] == "pending_summary"
    assert payload["error"]


def test_save_summary_artifacts_writes_json_and_error_file(tmp_path):
    payload = build_error_summary("summary failed")

    summary_path = save_summary_artifacts(tmp_path, payload)

    assert summary_path == tmp_path / "summary.json"
    assert (
        json.loads(summary_path.read_text(encoding="utf-8"))["status"]
        == "pending_summary"
    )
    assert (tmp_path / "summary_error.md").read_text(
        encoding="utf-8"
    ) == "summary failed"
