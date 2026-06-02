import pytest


@pytest.mark.unit
def test_prefetch_sentiment_blocks_uses_domestic_community_for_a_share(monkeypatch):
    import tradingagents.agents.analysts.sentiment_analyst as sentiment

    monkeypatch.setattr(sentiment.get_news, "func", lambda ticker, start, end: "cn news")
    monkeypatch.setattr(sentiment, "fetch_eastmoney_guba_posts", lambda ticker, limit=30: "eastmoney guba", raising=False)
    monkeypatch.setattr(sentiment, "fetch_xueqiu_hot_signals", lambda ticker: "xueqiu hot", raising=False)
    monkeypatch.setattr(
        sentiment,
        "fetch_tonghuashun_community_posts",
        lambda ticker, limit=30: "tonghuashun unavailable",
        raising=False,
    )

    def unexpected_stocktwits(*args, **kwargs):
        raise AssertionError("StockTwits should be skipped for mainland A-share sentiment")

    def unexpected_reddit(*args, **kwargs):
        raise AssertionError("Reddit should be skipped for mainland A-share sentiment")

    monkeypatch.setattr(sentiment, "fetch_stocktwits_messages", unexpected_stocktwits)
    monkeypatch.setattr(sentiment, "fetch_reddit_posts", unexpected_reddit)

    blocks = sentiment._prefetch_sentiment_blocks("000100.SZ", "2026-05-23", "2026-05-30")

    assert blocks == {
        "news_block": "cn news",
        "cn_social_block": "eastmoney guba\n\nxueqiu hot\n\ntonghuashun unavailable",
        "stocktwits_block": "<StockTwits skipped for mainland A-share; use Chinese domestic community and attention blocks>",
        "reddit_block": "<Reddit skipped for mainland A-share; use Chinese domestic community and attention blocks>",
    }


@pytest.mark.unit
def test_prefetch_sentiment_blocks_keeps_stocktwits_and_reddit_for_overseas(monkeypatch):
    import tradingagents.agents.analysts.sentiment_analyst as sentiment

    monkeypatch.setattr(sentiment.get_news, "func", lambda ticker, start, end: "us news")
    monkeypatch.setattr(sentiment, "fetch_stocktwits_messages", lambda ticker, limit=30: "stocktwits")
    monkeypatch.setattr(sentiment, "fetch_reddit_posts", lambda ticker: "reddit")

    def unexpected_domestic(*args, **kwargs):
        raise AssertionError("Chinese domestic sentiment sources should not be called for overseas sentiment")

    monkeypatch.setattr(sentiment, "fetch_eastmoney_guba_posts", unexpected_domestic, raising=False)
    monkeypatch.setattr(sentiment, "fetch_xueqiu_hot_signals", unexpected_domestic, raising=False)
    monkeypatch.setattr(sentiment, "fetch_tonghuashun_community_posts", unexpected_domestic, raising=False)

    blocks = sentiment._prefetch_sentiment_blocks("AAPL", "2026-05-23", "2026-05-30")

    assert blocks == {
        "news_block": "us news",
        "cn_social_block": "<Chinese domestic community source not applicable for AAPL>",
        "stocktwits_block": "stocktwits",
        "reddit_block": "reddit",
    }


@pytest.mark.unit
def test_build_system_message_passes_cn_social_block_to_prompt(monkeypatch):
    import tradingagents.agents.analysts.sentiment_analyst as sentiment

    captured = {}

    def fake_render_prompt(relative_path, **context):
        captured.update(context)
        return "rendered prompt"

    monkeypatch.setattr(sentiment, "render_prompt", fake_render_prompt)
    monkeypatch.setattr(sentiment, "get_language_instruction", lambda: "")

    result = sentiment._build_system_message(
        ticker="000100.SZ",
        start_date="2026-05-23",
        end_date="2026-05-30",
        news_block="news",
        cn_social_block="guba",
        stocktwits_block="stocktwits",
        reddit_block="reddit",
    )

    assert result == "rendered prompt"
    assert captured["cn_social_block"] == "guba"
