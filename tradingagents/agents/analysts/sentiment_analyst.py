"""Sentiment analyst — multi-source sentiment analysis for a target ticker.

Previously named ``social_media_analyst``. Renamed and redesigned because
the old version had a prompt that demanded social-media analysis but the
only tool available was Yahoo Finance news — which led LLMs to fabricate
Reddit/X/StockTwits content under prompt pressure (verified live).

The redesigned agent pre-fetches complementary data sources before
the LLM is invoked and injects them into the prompt as structured blocks:

  1. News headlines      — vendor-routed company news
  2. Chinese community   — Eastmoney Guba, Xueqiu hot signals, and
                           Tonghuashun availability status for A-shares
  3. StockTwits messages — retail-trader posts indexed by cashtag, with
                           user-labeled Bullish/Bearish sentiment tags
  4. Reddit posts        — r/wallstreetbets, r/stocks, r/investing

The agent does not use tool-calling; the data is in the prompt from
turn 0. The LLM produces the sentiment report in a single invocation.

See: https://github.com/TauricResearch/TradingAgents/issues/557
"""

from datetime import datetime, timedelta

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
    get_news,
)
from tradingagents.agents.utils.prompts import render_prompt
from tradingagents.dataflows.eastmoney_guba import fetch_eastmoney_guba_posts
from tradingagents.dataflows.market_utils import has_chinese_characters, is_mainland_a_share_ticker
from tradingagents.dataflows.reddit import fetch_reddit_posts
from tradingagents.dataflows.stocktwits import fetch_stocktwits_messages
from tradingagents.dataflows.tonghuashun_community import fetch_tonghuashun_community_posts
from tradingagents.dataflows.xueqiu import fetch_xueqiu_hot_signals


def _seven_days_back(trade_date: str) -> str:
    return (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=7)).strftime(
        "%Y-%m-%d"
    )


def create_sentiment_analyst(llm):
    """Create a sentiment analyst node for the trading graph.

    Pre-fetches news + StockTwits + Reddit data, injects them into the
    prompt as structured blocks, and produces a sentiment report in a
    single LLM call.
    """

    def sentiment_analyst_node(state):
        ticker = state["company_of_interest"]
        end_date = state["trade_date"]
        start_date = _seven_days_back(end_date)
        instrument_context = build_instrument_context(ticker)

        blocks = _prefetch_sentiment_blocks(ticker, start_date, end_date)

        system_message = _build_system_message(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            news_block=blocks["news_block"],
            cn_social_block=blocks["cn_social_block"],
            stocktwits_block=blocks["stocktwits_block"],
            reddit_block=blocks["reddit_block"],
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    "\n{system_message}\n"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=end_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        # No bind_tools — the data is already in the prompt; a single LLM
        # call produces the report directly.
        chain = prompt | llm
        result = chain.invoke(state["messages"])

        return {
            "messages": [result],
            "sentiment_report": result.content,
        }

    return sentiment_analyst_node


def _prefetch_sentiment_blocks(ticker: str, start_date: str, end_date: str) -> dict[str, str]:
    news_block = get_news.func(ticker, start_date, end_date)
    if is_mainland_a_share_ticker(ticker) or has_chinese_characters(ticker):
        return {
            "news_block": news_block,
            "cn_social_block": _build_cn_social_block(ticker),
            "stocktwits_block": "<StockTwits skipped for mainland A-share; use Chinese domestic community and attention blocks>",
            "reddit_block": "<Reddit skipped for mainland A-share; use Chinese domestic community and attention blocks>",
        }

    return {
        "news_block": news_block,
        "cn_social_block": f"<Chinese domestic community source not applicable for {ticker}>",
        "stocktwits_block": fetch_stocktwits_messages(ticker, limit=30),
        "reddit_block": fetch_reddit_posts(ticker),
    }


def _build_cn_social_block(ticker: str) -> str:
    return "\n\n".join(
        [
            fetch_eastmoney_guba_posts(ticker, limit=30),
            fetch_xueqiu_hot_signals(ticker),
            fetch_tonghuashun_community_posts(ticker, limit=30),
        ]
    )


def _build_system_message(
    *,
    ticker: str,
    start_date: str,
    end_date: str,
    news_block: str,
    cn_social_block: str,
    stocktwits_block: str,
    reddit_block: str,
) -> str:
    """Assemble the sentiment-analyst system message with structured data blocks."""
    return render_prompt(
        "analysts/sentiment.md",
        ticker=ticker,
        start_date=start_date,
        end_date=end_date,
        news_block=news_block,
        cn_social_block=cn_social_block,
        stocktwits_block=stocktwits_block,
        reddit_block=reddit_block,
        language_instruction=get_language_instruction(),
    )


# ---------------------------------------------------------------------------
# Backwards-compatibility shim
# ---------------------------------------------------------------------------
def create_social_media_analyst(llm):
    """Deprecated alias for :func:`create_sentiment_analyst`.

    Kept so existing code that imports ``create_social_media_analyst``
    continues to work.

    .. deprecated::
        Import :func:`create_sentiment_analyst` directly instead.
    """
    import warnings

    warnings.warn(
        "create_social_media_analyst is deprecated and will be removed in a "
        "future version. Use create_sentiment_analyst instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return create_sentiment_analyst(llm)
