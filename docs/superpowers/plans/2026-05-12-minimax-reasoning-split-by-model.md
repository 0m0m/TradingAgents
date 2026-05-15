# MiniMax Reasoning Split By Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inject `reasoning_split=True` whenever the selected model is a MiniMax reasoning model, even if the provider is configured as `openai`.

**Architecture:** Keep API-key and base-url resolution provider-driven. Add a model-driven MiniMax detection helper in the capability module, then use it only for selecting `MinimaxChatOpenAI`, whose existing request payload override injects `reasoning_split=True`.

**Tech Stack:** Python, pytest, langchain-openai, existing `tradingagents.llm_clients` adapter layer.

---

## File Structure

- Modify: `tradingagents/llm_clients/capabilities.py`
  - Add `is_minimax_reasoning_model(model_name: str) -> bool` using the same exact-ID and regex coverage as the MiniMax capability table.
- Modify: `tradingagents/llm_clients/openai_client.py`
  - Import the helper and select `MinimaxChatOpenAI` when either provider is MiniMax or model is MiniMax reasoning.
  - Do not change API-key or base-url selection.
- Modify: `tests/test_minimax.py`
  - Add a regression test for `OpenAIClient(model="MiniMax-M2.7", provider="openai")` returning a `MinimaxChatOpenAI` instance whose payload contains `reasoning_split=True`.

## Task 1: Add model-level MiniMax detection

**Files:**
- Modify: `tradingagents/llm_clients/capabilities.py:87-120`
- Test: `tests/test_minimax.py`

- [ ] **Step 1: Add failing tests for model-based MiniMax detection**

Append this test class to `tests/test_minimax.py`:

```python
from tradingagents.llm_clients.capabilities import is_minimax_reasoning_model


@pytest.mark.unit
class TestMinimaxModelDetection:
    def test_known_m2_model_is_minimax_reasoning_model(self):
        assert is_minimax_reasoning_model("MiniMax-M2.7") is True

    def test_future_m_series_model_is_minimax_reasoning_model(self):
        assert is_minimax_reasoning_model("MiniMax-M3") is True

    def test_openai_model_is_not_minimax_reasoning_model(self):
        assert is_minimax_reasoning_model("gpt-5.5") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_minimax.py::TestMinimaxModelDetection -v
```

Expected: FAIL with an import error or missing function error for `is_minimax_reasoning_model`.

- [ ] **Step 3: Add minimal helper implementation**

In `tradingagents/llm_clients/capabilities.py`, add this function after `get_capabilities`:

```python
def is_minimax_reasoning_model(model_name: str) -> bool:
    return get_capabilities(model_name) == _MINIMAX_THINKING
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
pytest tests/test_minimax.py::TestMinimaxModelDetection -v
```

Expected: PASS.

## Task 2: Select MiniMax client by model as well as provider

**Files:**
- Modify: `tradingagents/llm_clients/openai_client.py:8-10,237-245`
- Test: `tests/test_minimax.py`

- [ ] **Step 1: Add failing regression test for provider=openai with MiniMax model**

Update the import in `tests/test_minimax.py`:

```python
from tradingagents.llm_clients.openai_client import MinimaxChatOpenAI, OpenAIClient
```

Append this test class to `tests/test_minimax.py`:

```python
@pytest.mark.unit
class TestMinimaxClientSelection:
    def test_openai_provider_with_minimax_model_injects_reasoning_split(self):
        client = OpenAIClient(
            model="MiniMax-M2.7",
            provider="openai",
            api_key="placeholder",
        )

        llm = client.get_llm()
        payload = llm._get_request_payload([HumanMessage(content="hi")])

        assert isinstance(llm, MinimaxChatOpenAI)
        assert payload.get("reasoning_split") is True
```

- [ ] **Step 2: Run test to verify it fails before implementation**

Run:

```bash
pytest tests/test_minimax.py::TestMinimaxClientSelection -v
```

Expected: FAIL because `OpenAIClient(provider="openai", model="MiniMax-M2.7")` currently returns `NormalizedChatOpenAI`, not `MinimaxChatOpenAI`, so `reasoning_split` is absent.

- [ ] **Step 3: Update `openai_client.py` import**

Change this import:

```python
from .capabilities import get_capabilities
```

To:

```python
from .capabilities import get_capabilities, is_minimax_reasoning_model
```

- [ ] **Step 4: Update client class selection logic**

In `OpenAIClient.get_llm()`, replace this block:

```python
        model_lower = self.model.lower()
        is_deepseek_model = model_lower == "deepseek" or model_lower.startswith("deepseek-")

        if self.provider == "deepseek" or is_deepseek_model:
            chat_cls = DeepSeekChatOpenAI
        elif self.provider in ("minimax", "minimax-cn"):
            chat_cls = MinimaxChatOpenAI
        else:
            chat_cls = NormalizedChatOpenAI
```

With:

```python
        model_lower = self.model.lower()
        is_deepseek_model = model_lower == "deepseek" or model_lower.startswith("deepseek-")
        is_minimax_model = is_minimax_reasoning_model(self.model)

        if self.provider == "deepseek" or is_deepseek_model:
            chat_cls = DeepSeekChatOpenAI
        elif self.provider in ("minimax", "minimax-cn") or is_minimax_model:
            chat_cls = MinimaxChatOpenAI
        else:
            chat_cls = NormalizedChatOpenAI
```

- [ ] **Step 5: Run regression test to verify it passes**

Run:

```bash
pytest tests/test_minimax.py::TestMinimaxClientSelection -v
```

Expected: PASS.

## Task 3: Verify existing MiniMax behavior is unchanged

**Files:**
- Test: `tests/test_minimax.py`

- [ ] **Step 1: Run the full MiniMax test file**

Run:

```bash
pytest tests/test_minimax.py -v
```

Expected: PASS for all MiniMax tests.

- [ ] **Step 2: Confirm API-key behavior is not changed**

Inspect the diff and verify there are no edits to this provider-driven key block in `tradingagents/llm_clients/openai_client.py`:

```python
        if self.provider in _PROVIDER_BASE_URL:
            llm_kwargs["base_url"] = self.base_url or _resolve_provider_base_url(self.provider)
            api_key_env = get_api_key_env(self.provider)
            if api_key_env:
                api_key = os.environ.get(api_key_env)
                if api_key:
                    llm_kwargs["api_key"] = api_key
                else:
                    raise ValueError(
                        f"API key for provider '{self.provider}' is not set. "
                        f"Please set the {api_key_env} environment variable "
                        f"(e.g. add {api_key_env}=your_key to your .env file)."
                    )
            else:
                llm_kwargs["api_key"] = "ollama"
        elif self.base_url:
            llm_kwargs["base_url"] = self.base_url
```

Expected: the only `openai_client.py` behavior change is class selection for MiniMax models.

- [ ] **Step 3: Run the focused LLM client test set if available**

Run:

```bash
pytest tests/test_minimax.py tests/test_openai_client.py -v
```

Expected: PASS if `tests/test_openai_client.py` exists. If it does not exist, run only:

```bash
pytest tests/test_minimax.py -v
```

Expected: PASS.

## Self-Review

- Spec coverage: The plan covers model-level MiniMax detection, class selection, payload injection, and no API-key behavior change.
- Placeholder scan: No placeholders remain.
- Type consistency: `is_minimax_reasoning_model(model_name: str) -> bool`, `OpenAIClient`, and `MinimaxChatOpenAI` names match existing modules and planned imports.

## Commit Guidance

Do not commit automatically. If the user explicitly asks for a commit after implementation, stage only these files:

```bash
git add tradingagents/llm_clients/capabilities.py tradingagents/llm_clients/openai_client.py tests/test_minimax.py docs/superpowers/plans/2026-05-12-minimax-reasoning-split-by-model.md
```

Then create a new commit with a message that describes why MiniMax reasoning behavior is keyed by model, not by provider.
