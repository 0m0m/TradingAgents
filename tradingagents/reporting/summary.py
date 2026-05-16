from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from tradingagents.llm_clients.factory import create_llm_client


SUMMARY_FIELDS = [
    "final_action",
    "direction",
    "confidence",
    "time_horizon",
    "key_catalysts",
    "key_risks",
    "decision_rationale",
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
]


class ReportSummary(BaseModel):
    final_action: str = ""
    direction: str = ""
    confidence: str = ""
    time_horizon: str = ""
    key_catalysts: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    decision_rationale: str = ""
    market_report_summary: str = ""
    sentiment_report_summary: str = ""
    news_report_summary: str = ""
    fundamentals_report_summary: str = ""
    bull_case_summary: str = ""
    bear_case_summary: str = ""
    research_manager_summary: str = ""
    trader_plan_summary: str = ""
    risk_aggressive_summary: str = ""
    risk_conservative_summary: str = ""
    risk_neutral_summary: str = ""
    portfolio_manager_summary: str = ""


def _as_dict(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if hasattr(payload, "model_dump"):
        return payload.model_dump()
    if hasattr(payload, "dict"):
        return payload.dict()
    raise TypeError("summary payload must be a dict or pydantic model")


def normalize_summary_payload(
    payload: dict[str, Any] | ReportSummary,
) -> dict[str, object]:
    source = _as_dict(payload)
    normalized: dict[str, object] = {}
    for field in SUMMARY_FIELDS:
        if field in ("key_catalysts", "key_risks"):
            value = source.get(field) or []
            normalized[field] = value if isinstance(value, list) else [str(value)]
        else:
            normalized[field] = source.get(field) or ""
    normalized["status"] = source.get("status") or "completed"
    normalized["error"] = source.get("error") or ""
    return normalized


def build_error_summary(error: str) -> dict[str, object]:
    payload = normalize_summary_payload({})
    payload["status"] = "pending_summary"
    payload["error"] = error
    return payload


def build_summary_prompt(report_path: Path, output_language: str = "Chinese") -> str:
    fields = ", ".join(SUMMARY_FIELDS)
    report_text = report_path.read_text(encoding="utf-8")
    language_rule = "除 status 和 error 外，所有字符串字段必须使用简体中文。"
    if output_language.lower() != "chinese":
        language_rule = (
            f"除 status 和 error 外，所有字符串字段必须使用 {output_language}。"
        )
    return (
        f"请根据这个 TradingAgents markdown 报告文件提炼机器可读摘要，文件路径：{report_path}。"
        "只依据报告正文，不要编造缺失信息。报告全文如下：\n"
        f"{report_text}\n"
        "只返回一个 JSON 对象，不要 markdown 代码块，不要附加解释。"
        f"顶层 key 必须且只能使用这些字段：{fields}，并额外包含 status 和 error。"
        "无法判断的字符串字段使用空字符串。"
        "key_catalysts 和 key_risks 必须使用字符串数组。"
        f"{language_rule}"
        'status 使用 "completed"，error 使用空字符串。'
    )


def _response_text(response: object) -> str:
    content = getattr(response, "content", response)
    return content if isinstance(content, str) else str(content)


def _extract_json_payload(text: str) -> dict[str, object]:
    stripped = text.strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise ValueError("summary response is not valid JSON")
    payload = json.loads(stripped[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("summary response must be a JSON object")
    return payload


def _build_repair_prompt(original_prompt: str, response_text: str) -> str:
    return (
        f"{original_prompt}"
        "上一次回答没有包含可解析 JSON。"
        "请只根据原报告文件重新输出一个合法 JSON 对象，不要 markdown 代码块，不要附加解释。"
        f"上一次回答如下：{response_text[-2000:]}"
    )


def generate_report_summary(
    report_path: Path,
    provider: str,
    model: str,
    base_url: str | None = None,
    output_language: str = "Chinese",
) -> dict[str, object]:
    prompt = build_summary_prompt(report_path, output_language=output_language)
    try:
        client = create_llm_client(provider=provider, model=model, base_url=base_url)
        llm = client.get_llm()
        try:
            structured_llm = llm.with_structured_output(ReportSummary)
            return normalize_summary_payload(structured_llm.invoke(prompt))
        except Exception:
            response_text = _response_text(llm.invoke(prompt))
            try:
                return normalize_summary_payload(_extract_json_payload(response_text))
            except ValueError:
                repair_prompt = _build_repair_prompt(prompt, response_text)
                response_text = _response_text(llm.invoke(repair_prompt))
                return normalize_summary_payload(_extract_json_payload(response_text))
    except Exception as exc:
        return build_error_summary(str(exc))


def save_summary_artifacts(save_path: Path, summary_payload: dict[str, object]) -> Path:
    save_path.mkdir(parents=True, exist_ok=True)
    summary_path = save_path / "summary.json"
    summary_path.write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    error = summary_payload.get("error")
    if summary_payload.get("status") != "completed" and error:
        (save_path / "summary_error.md").write_text(str(error), encoding="utf-8")
    return summary_path
