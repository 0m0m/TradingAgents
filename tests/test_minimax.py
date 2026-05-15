"""Tests for MinimaxChatOpenAI quirks.

Verifies the subclass injects ``reasoning_split=True`` into outgoing
requests so M2.x reasoning models put their <think> block into
``reasoning_details`` instead of polluting ``message.content``.
"""

import os

import pytest
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from tradingagents.llm_clients.capabilities import is_minimax_reasoning_model
from tradingagents.llm_clients.openai_client import (
    MinimaxChatOpenAI,
    OpenAIClient,
)


def _client(model: str = "MiniMax-M2.7"):
    os.environ.setdefault("MINIMAX_API_KEY", "placeholder")
    return MinimaxChatOpenAI(
        model=model,
        api_key="placeholder",
        base_url="https://api.minimax.io/v1",
    )


@pytest.mark.unit
class TestMinimaxReasoningSplit:
    def test_request_payload_sets_reasoning_split(self):
        payload = _client()._get_request_payload([HumanMessage(content="hi")])
        assert payload.get("reasoning_split") is True

    def test_caller_supplied_reasoning_split_is_preserved(self):
        """If the user explicitly sets reasoning_split, don't override it
        (setdefault semantics — caller wins)."""
        client = _client()
        payload = client._get_request_payload(
            [HumanMessage(content="hi")],
            reasoning_split=False,
        )
        assert payload.get("reasoning_split") is False


@pytest.mark.unit
class TestMinimaxStructuredOutputDispatch:
    """M2.x models route through the capability table — tool_choice is
    suppressed but the schema is still bound as a tool."""

    class _Pick(BaseModel):
        action: str

    def _bound_kwargs(self, runnable):
        first = runnable.steps[0] if hasattr(runnable, "steps") else runnable
        return getattr(first, "kwargs", {})

    def test_m2_7_suppresses_tool_choice(self):
        bound = _client("MiniMax-M2.7").with_structured_output(self._Pick)
        kwargs = self._bound_kwargs(bound)
        assert kwargs.get("tool_choice") is None or "tool_choice" not in kwargs

    def test_m2_7_highspeed_suppresses_tool_choice(self):
        bound = _client("MiniMax-M2.7-highspeed").with_structured_output(self._Pick)
        kwargs = self._bound_kwargs(bound)
        assert kwargs.get("tool_choice") is None or "tool_choice" not in kwargs

    def test_schema_still_bound_as_tool(self):
        bound = _client("MiniMax-M2.7").with_structured_output(self._Pick)
        tools = self._bound_kwargs(bound).get("tools", [])
        assert any(t.get("function", {}).get("name") == "_Pick" for t in tools), (
            f"schema not bound: {tools}"
        )


@pytest.mark.unit
class TestMinimaxModelDetection:
    def test_known_m2_model_is_minimax_reasoning_model(self):
        assert is_minimax_reasoning_model("MiniMax-M2.7") is True

    def test_future_m_series_model_is_minimax_reasoning_model(self):
        assert is_minimax_reasoning_model("MiniMax-M3") is True

    def test_openai_model_is_not_minimax_reasoning_model(self):
        assert is_minimax_reasoning_model("gpt-5.5") is False


@pytest.mark.unit
class TestMinimaxClientSelection:
    def test_minimax_provider_with_minimax_model_injects_reasoning_split(self):
        client = OpenAIClient(
            model="MiniMax-M2.7",
            provider="minimax",
            api_key="placeholder",
        )

        llm = client.get_llm()
        payload = llm._get_request_payload([HumanMessage(content="hi")])

        assert isinstance(llm, MinimaxChatOpenAI)
        assert payload.get("reasoning_split") is True

    def test_openai_provider_with_minimax_model_does_not_inject_reasoning_split(self):
        client = OpenAIClient(
            model="MiniMax-M2.7",
            provider="openai",
            api_key="placeholder",
            reasoning_effort="high",
        )

        llm = client.get_llm()
        payload = llm._get_request_payload([HumanMessage(content="hi")])

        assert not isinstance(llm, MinimaxChatOpenAI)
        assert "reasoning_split" not in payload
        assert "reasoning_effort" not in payload
