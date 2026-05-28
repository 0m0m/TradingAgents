# Externalize Agent Prompts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move TradingAgents agent long prompts from Python files into Markdown templates while preserving current runtime behavior.

**Architecture:** Add a small prompt loader under `tradingagents/agents/utils/prompts.py` that reads UTF-8 Markdown templates from `tradingagents/agents/prompts/` and renders them with explicit context. Each agent keeps its existing state access, tool binding, LangChain prompt wiring, and structured-output fallback; only the long prompt text moves out of Python.

**Tech Stack:** Python, pathlib, functools.lru_cache, LangChain prompt/message objects, pytest.

---

## File Structure

- Create: `tradingagents/agents/utils/prompts.py`
  - Owns prompt template loading and `.format(**context)` rendering.
- Create prompt templates:
  - `tradingagents/agents/prompts/analysts/fundamentals.md`
  - `tradingagents/agents/prompts/analysts/market.md`
  - `tradingagents/agents/prompts/analysts/news.md`
  - `tradingagents/agents/prompts/analysts/sentiment.md`
  - `tradingagents/agents/prompts/researchers/bull.md`
  - `tradingagents/agents/prompts/researchers/bear.md`
  - `tradingagents/agents/prompts/risk_mgmt/aggressive.md`
  - `tradingagents/agents/prompts/risk_mgmt/conservative.md`
  - `tradingagents/agents/prompts/risk_mgmt/neutral.md`
  - `tradingagents/agents/prompts/managers/research_manager.md`
  - `tradingagents/agents/prompts/managers/portfolio_manager.md`
  - `tradingagents/agents/prompts/trader/system.md`
  - `tradingagents/agents/prompts/trader/user.md`
- Modify production agents:
  - `tradingagents/agents/analysts/fundamentals_analyst.py`
  - `tradingagents/agents/analysts/market_analyst.py`
  - `tradingagents/agents/analysts/news_analyst.py`
  - `tradingagents/agents/analysts/sentiment_analyst.py`
  - `tradingagents/agents/researchers/bull_researcher.py`
  - `tradingagents/agents/researchers/bear_researcher.py`
  - `tradingagents/agents/risk_mgmt/aggressive_debator.py`
  - `tradingagents/agents/risk_mgmt/conservative_debator.py`
  - `tradingagents/agents/risk_mgmt/neutral_debator.py`
  - `tradingagents/agents/managers/research_manager.py`
  - `tradingagents/agents/managers/portfolio_manager.py`
  - `tradingagents/agents/trader/trader.py`
- Create: `tests/test_prompt_templates.py`
  - Verifies template loading, rendering, missing template errors, and missing placeholder errors.
- Modify if needed: `tests/test_structured_agents.py`
  - Keep behavioral assertions for Trader and Research Manager.

Do not change `tradingagents/agents/schemas.py`; schema `Field(description=...)` strings remain in code for this iteration.

## Task 1: Add prompt template loader

**Files:**
- Create: `tradingagents/agents/utils/prompts.py`
- Test: `tests/test_prompt_templates.py`

- [ ] **Step 1: Write failing tests for prompt loading and rendering**

Create `tests/test_prompt_templates.py` with this content:

```python
import pytest

from tradingagents.agents.utils.prompts import load_prompt, render_prompt


@pytest.mark.unit
class TestPromptTemplates:
    def test_loads_markdown_prompt_from_agents_prompt_dir(self):
        prompt = load_prompt("trader/system.md")

        assert "trading agent" in prompt
        assert "{language_instruction}" in prompt

    def test_renders_prompt_with_explicit_context(self):
        rendered = render_prompt(
            "trader/system.md",
            language_instruction=" Write your entire response in Chinese.",
        )

        assert "{language_instruction}" not in rendered
        assert "Write your entire response in Chinese." in rendered

    def test_missing_prompt_raises_file_not_found_error(self):
        with pytest.raises(FileNotFoundError):
            load_prompt("does/not/exist.md")

    def test_missing_placeholder_raises_key_error(self):
        with pytest.raises(KeyError):
            render_prompt("trader/system.md")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_prompt_templates.py::TestPromptTemplates -v
```

Expected: FAIL because `tradingagents.agents.utils.prompts` and `tradingagents/agents/prompts/trader/system.md` do not exist.

- [ ] **Step 3: Add minimal prompt loader**

Create `tradingagents/agents/utils/prompts.py`:

```python
from functools import lru_cache
from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


@lru_cache(maxsize=None)
def load_prompt(relative_path: str) -> str:
    path = _PROMPTS_DIR / relative_path
    return path.read_text(encoding="utf-8")


def render_prompt(relative_path: str, **context) -> str:
    return load_prompt(relative_path).format(**context)
```

- [ ] **Step 4: Add the first prompt template required by the test**

Create `tradingagents/agents/prompts/trader/system.md`:

```markdown
You are a trading agent analyzing market data to make investment decisions. Based on your analysis, provide a specific recommendation to buy, sell, or hold. Anchor your reasoning in the analysts' reports and the research plan.{language_instruction}
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
pytest tests/test_prompt_templates.py::TestPromptTemplates -v
```

Expected: PASS.

## Task 2: Externalize Trader prompts

**Files:**
- Create: `tradingagents/agents/prompts/trader/user.md`
- Modify: `tradingagents/agents/trader/trader.py`
- Test: `tests/test_structured_agents.py`

- [ ] **Step 1: Add Trader user prompt template**

Create `tradingagents/agents/prompts/trader/user.md`:

```markdown
Based on a comprehensive analysis by a team of analysts, here is an investment plan tailored for {company_name}. {instrument_context} This plan incorporates insights from current technical market trends, macroeconomic indicators, and social media sentiment. Use this plan as a foundation for evaluating your next trading decision.

Proposed Investment Plan: {investment_plan}

Leverage these insights to make an informed and strategic decision.
```

- [ ] **Step 2: Update Trader imports**

In `tradingagents/agents/trader/trader.py`, add this import:

```python
from tradingagents.agents.utils.prompts import render_prompt
```

- [ ] **Step 3: Replace inline Trader messages with rendered templates**

In `tradingagents/agents/trader/trader.py`, replace the current `messages = [...]` block inside `trader_node` with:

```python
        messages = [
            {
                "role": "system",
                "content": render_prompt(
                    "trader/system.md",
                    language_instruction=get_language_instruction(),
                ),
            },
            {
                "role": "user",
                "content": render_prompt(
                    "trader/user.md",
                    company_name=company_name,
                    instrument_context=instrument_context,
                    investment_plan=investment_plan,
                ),
            },
        ]
```

- [ ] **Step 4: Run Trader focused tests**

Run:

```bash
pytest tests/test_structured_agents.py::TestTraderAgent -v
```

Expected: PASS. The existing assertion that the captured prompt contains `Proposed Investment Plan` must still pass.

## Task 3: Externalize Research Manager and Portfolio Manager prompts

**Files:**
- Create: `tradingagents/agents/prompts/managers/research_manager.md`
- Create: `tradingagents/agents/prompts/managers/portfolio_manager.md`
- Modify: `tradingagents/agents/managers/research_manager.py`
- Modify: `tradingagents/agents/managers/portfolio_manager.py`
- Test: `tests/test_structured_agents.py`, `tests/test_memory_log.py`

- [ ] **Step 1: Add Research Manager template**

Create `tradingagents/agents/prompts/managers/research_manager.md` from the existing prompt in `research_manager.py`, preserving the five-tier rating scale. It must contain these placeholders exactly:

```markdown
As the Research Manager, evaluate the debate between the Bull and Bear analysts and produce a clear investment plan for the trader.

{instrument_context}

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction to enter or add to position
- **Overweight**: Favorable outlook, gradually increase exposure
- **Hold**: Maintain current position, no action needed
- **Underweight**: Reduce exposure, take partial profits
- **Sell**: Exit position or avoid entry

**Investment Debate History:**
{history}

---

Choose the rating that best reflects the evidence. Be decisive, reconcile the strongest points from both sides, and provide actionable strategic guidance for the trader.{language_instruction}
```

- [ ] **Step 2: Add Portfolio Manager template**

Create `tradingagents/agents/prompts/managers/portfolio_manager.md`:

```markdown
As the Portfolio Manager, synthesize the risk analysts' debate and deliver the final trading decision.

{instrument_context}

---

**Rating Scale** (use exactly one):
- **Buy**: Strong conviction to enter or add to position
- **Overweight**: Favorable outlook, gradually increase exposure
- **Hold**: Maintain current position, no action needed
- **Underweight**: Reduce exposure, take partial profits
- **Sell**: Exit position or avoid entry

**Context:**
- Research Manager's investment plan: **{research_plan}**
- Trader's transaction proposal: **{trader_plan}**
{lessons_line}
**Risk Analysts Debate History:**
{history}

---

Be decisive and ground every conclusion in specific evidence from the analysts.{language_instruction}
```

- [ ] **Step 3: Update manager imports**

Add this import to both manager files:

```python
from tradingagents.agents.utils.prompts import render_prompt
```

- [ ] **Step 4: Replace Research Manager inline prompt**

In `tradingagents/agents/managers/research_manager.py`, replace the inline `prompt = f"""..."""` assignment with:

```python
        prompt = render_prompt(
            "managers/research_manager.md",
            instrument_context=instrument_context,
            history=history,
            language_instruction=get_language_instruction(),
        )
```

- [ ] **Step 5: Replace Portfolio Manager inline prompt**

In `tradingagents/agents/managers/portfolio_manager.py`, replace the inline `prompt = f"""..."""` assignment with:

```python
        prompt = render_prompt(
            "managers/portfolio_manager.md",
            instrument_context=instrument_context,
            research_plan=research_plan,
            trader_plan=trader_plan,
            lessons_line=lessons_line,
            history=history,
            language_instruction=get_language_instruction(),
        )
```

- [ ] **Step 6: Run manager tests**

Run:

```bash
pytest tests/test_structured_agents.py::TestResearchManagerAgent tests/test_memory_log.py -v
```

Expected: PASS. The Research Manager prompt must still include all five rating tiers.

## Task 4: Externalize researcher and risk debate prompts

**Files:**
- Create: `tradingagents/agents/prompts/researchers/bull.md`
- Create: `tradingagents/agents/prompts/researchers/bear.md`
- Create: `tradingagents/agents/prompts/risk_mgmt/aggressive.md`
- Create: `tradingagents/agents/prompts/risk_mgmt/conservative.md`
- Create: `tradingagents/agents/prompts/risk_mgmt/neutral.md`
- Modify: corresponding researcher and risk files
- Test: import-level pytest collection

- [ ] **Step 1: Create researcher templates**

Create `tradingagents/agents/prompts/researchers/bull.md` using the existing Bull Analyst text and these placeholders:

```markdown
You are a Bull Analyst advocating for investing in the stock. Your task is to build a strong, evidence-based case emphasizing growth potential, competitive advantages, and positive market indicators. Leverage the provided research and data to address concerns and counter bearish arguments effectively.

Focus on:
- Growth opportunities and market expansion
- Competitive advantages and business quality
- Positive technical, sentiment, news, and fundamental evidence
- Rebuttals to bearish claims from the debate history

Current analysis reports:
Market report: {market_report}
Sentiment report: {sentiment_report}
News report: {news_report}
Fundamentals report: {fundamentals_report}

Debate history:
{history}

Use this information to deliver a compelling bull argument, refute the bear's concerns, and engage in a dynamic debate that demonstrates the strengths of the bull position.{language_instruction}
```

Create `tradingagents/agents/prompts/researchers/bear.md` using the existing Bear Analyst text and these placeholders:

```markdown
You are a Bear Analyst making the case against investing in the stock. Your goal is to present a well-reasoned argument emphasizing risks, challenges, and negative indicators. Leverage the provided research and data to highlight potential downsides and counter bullish arguments effectively.

Focus on:
- Business, valuation, macro, sentiment, technical, and execution risks
- Weaknesses or uncertainty in the bull thesis
- Negative indicators from analyst reports
- Rebuttals to bullish claims from the debate history

Current analysis reports:
Market report: {market_report}
Sentiment report: {sentiment_report}
News report: {news_report}
Fundamentals report: {fundamentals_report}

Debate history:
{history}

Use this information to deliver a compelling bear argument, refute the bull's claims, and engage in a dynamic debate that demonstrates the risks and weaknesses of investing in the stock.{language_instruction}
```

- [ ] **Step 2: Create risk templates**

Create `tradingagents/agents/prompts/risk_mgmt/aggressive.md`:

```markdown
As the Aggressive Risk Analyst, advocate for a high-risk, high-reward approach to the trader's proposal. Emphasize upside potential, strategic opportunity, and why accepting volatility may be justified.

Trader's plan:
{trader_plan}

Risk debate history:
{history}

Challenge conservative and neutral objections directly. Focus on debating and persuading, not just presenting data. Output conversationally as if you are speaking without any special formatting.{language_instruction}
```

Create `tradingagents/agents/prompts/risk_mgmt/conservative.md`:

```markdown
As the Conservative Risk Analyst, protect the firm's assets by emphasizing downside risk, capital preservation, volatility control, and sustainable growth.

Trader's plan:
{trader_plan}

Risk debate history:
{history}

Question optimistic assumptions and emphasize overlooked downsides. Focus on debating and critiquing other arguments to demonstrate the strength of a low-risk strategy. Output conversationally as if you are speaking without any special formatting.{language_instruction}
```

Create `tradingagents/agents/prompts/risk_mgmt/neutral.md`:

```markdown
As the Neutral Risk Analyst, provide a balanced perspective that weighs both opportunity and downside risk. Seek a sustainable middle path between aggressive risk-taking and excessive caution.

Trader's plan:
{trader_plan}

Risk debate history:
{history}

Challenge both extremes: question aggressive overconfidence and conservative overcaution. Output conversationally as if you are speaking without any special formatting.{language_instruction}
```

- [ ] **Step 3: Update imports in researcher and risk files**

Add this import to each modified file:

```python
from tradingagents.agents.utils.prompts import render_prompt
```

- [ ] **Step 4: Replace researcher prompt assignments**

In `bull_researcher.py` and `bear_researcher.py`, replace inline `prompt = f"""..."""` assignments with calls matching this shape:

```python
        prompt = render_prompt(
            "researchers/bull.md",
            market_report=market_report,
            sentiment_report=sentiment_report,
            news_report=news_report,
            fundamentals_report=fundamentals_report,
            history=history,
            language_instruction=get_language_instruction(),
        )
```

Use `"researchers/bear.md"` in `bear_researcher.py` with the same context keys.

- [ ] **Step 5: Replace risk prompt assignments**

In each risk debater, replace the inline prompt assignment with:

```python
        prompt = render_prompt(
            "risk_mgmt/aggressive.md",
            trader_plan=trader_plan,
            history=history,
            language_instruction=get_language_instruction(),
        )
```

Use `risk_mgmt/conservative.md` and `risk_mgmt/neutral.md` in the corresponding files.

- [ ] **Step 6: Run import collection for modified modules**

Run:

```bash
pytest --collect-only tests/test_structured_agents.py -q
```

Expected: PASS collection with no import errors.

## Task 5: Externalize analyst prompts

**Files:**
- Create: `tradingagents/agents/prompts/analysts/fundamentals.md`
- Create: `tradingagents/agents/prompts/analysts/market.md`
- Create: `tradingagents/agents/prompts/analysts/news.md`
- Create: `tradingagents/agents/prompts/analysts/sentiment.md`
- Modify: analyst files
- Test: `tests/test_prompt_templates.py`

- [ ] **Step 1: Create fundamentals, market, and news templates**

Create `tradingagents/agents/prompts/analysts/fundamentals.md`:

```markdown
You are a researcher tasked with analyzing fundamental information over the past week about a company. Please write a comprehensive report of the company's fundamental information such as financial documents, company profile, basic company financials, and company financial history to gain a full view of the company's fundamental information to inform traders. Make sure to include as much detail as possible. Provide specific, actionable insights with supporting evidence to help traders make informed decisions. Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read. Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements.{language_instruction}
```

Create `tradingagents/agents/prompts/analysts/news.md`:

```markdown
You are a news researcher tasked with analyzing recent news and trends over the past week. Please write a comprehensive report of the current state of the world that is relevant for trading and macroeconomics. Use the available tools: get_news(query, start_date, end_date) for company-specific or targeted news searches, and get_global_news(curr_date, look_back_days, limit) for broader macroeconomic news. Provide specific, actionable insights with supporting evidence to help traders make informed decisions. Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read.{language_instruction}
```

Create `tradingagents/agents/prompts/analysts/market.md` by moving the existing long indicator-selection text from `market_analyst.py` into Markdown and replacing the final language call with `{language_instruction}`. Preserve the exact indicator names: `close_50_sma`, `close_200_sma`, `close_10_ema`, `macd`, `macds`, `macdh`, `rsi`, `boll`, `boll_ub`, `boll_lb`, `atr`, `vwma`.

- [ ] **Step 2: Create sentiment template**

Create `tradingagents/agents/prompts/analysts/sentiment.md` by moving `_build_system_message(...)` body from `sentiment_analyst.py` into Markdown. It must use these placeholders:

```markdown
{ticker}
{start_date}
{end_date}
{news_block}
{stocktwits_block}
{reddit_block}
{language_instruction}
```

Preserve the `<start_of_news>`, `<end_of_news>`, `<start_of_stocktwits>`, `<end_of_stocktwits>`, `<start_of_reddit>`, and `<end_of_reddit>` delimiters exactly.

- [ ] **Step 3: Update analyst imports**

Add this import to each modified analyst file:

```python
from tradingagents.agents.utils.prompts import render_prompt
```

- [ ] **Step 4: Replace fundamentals, market, and news system messages**

Use this pattern in each tool-calling analyst:

```python
        system_message = render_prompt(
            "analysts/fundamentals.md",
            language_instruction=get_language_instruction(),
        )
```

Use `analysts/market.md` and `analysts/news.md` in the matching files. Keep the existing outer `ChatPromptTemplate.from_messages(...)`, `prompt.partial(...)`, and `llm.bind_tools(tools)` code unchanged.

- [ ] **Step 5: Replace sentiment builder body**

In `tradingagents/agents/analysts/sentiment_analyst.py`, update `_build_system_message(...)` to:

```python
def _build_system_message(
    *,
    ticker: str,
    start_date: str,
    end_date: str,
    news_block: str,
    stocktwits_block: str,
    reddit_block: str,
) -> str:
    return render_prompt(
        "analysts/sentiment.md",
        ticker=ticker,
        start_date=start_date,
        end_date=end_date,
        news_block=news_block,
        stocktwits_block=stocktwits_block,
        reddit_block=reddit_block,
        language_instruction=get_language_instruction(),
    )
```

- [ ] **Step 6: Add template inventory test**

Append this to `tests/test_prompt_templates.py`:

```python
PROMPT_PATHS = [
    "analysts/fundamentals.md",
    "analysts/market.md",
    "analysts/news.md",
    "analysts/sentiment.md",
    "researchers/bull.md",
    "researchers/bear.md",
    "risk_mgmt/aggressive.md",
    "risk_mgmt/conservative.md",
    "risk_mgmt/neutral.md",
    "managers/research_manager.md",
    "managers/portfolio_manager.md",
    "trader/system.md",
    "trader/user.md",
]


@pytest.mark.unit
def test_all_agent_prompt_templates_exist_and_are_nonempty():
    for path in PROMPT_PATHS:
        assert load_prompt(path).strip(), path
```

- [ ] **Step 7: Run prompt template tests**

Run:

```bash
pytest tests/test_prompt_templates.py -v
```

Expected: PASS.

## Task 6: Final verification

**Files:**
- All modified files from earlier tasks

- [ ] **Step 1: Run focused structured-agent tests**

Run:

```bash
pytest tests/test_structured_agents.py -v
```

Expected: PASS.

- [ ] **Step 2: Run memory-log tests**

Run:

```bash
pytest tests/test_memory_log.py -v
```

Expected: PASS.

- [ ] **Step 3: Run full test suite**

Run:

```bash
pytest tests
```

Expected: PASS. If external-data integration tests are skipped or require unavailable credentials, report the exact skipped/failed tests and do not claim full verification.

- [ ] **Step 4: Inspect diff for scope control**

Run:

```bash
git diff -- tradingagents/agents tests/test_prompt_templates.py tests/test_structured_agents.py
```

Expected: diff only moves prompt text into Markdown templates, adds the loader, and updates tests. No changes to `tradingagents/agents/schemas.py`, provider clients, graph orchestration, dataflows, or CLI behavior.

## Self-Review

- Spec coverage: The plan externalizes long prompts only, keeps schema descriptions in code, preserves current agent wiring, and adds loader/tests.
- Placeholder scan: No `TBD`, deferred implementation, or undefined function names remain.
- Type consistency: The loader API is consistently `load_prompt(relative_path: str)` and `render_prompt(relative_path: str, **context)`. Agent snippets use the same function names and relative prompt paths.
- Safety: No commit step is included because commits require explicit user request in this environment.
