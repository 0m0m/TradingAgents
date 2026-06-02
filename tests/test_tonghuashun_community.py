import pytest


@pytest.mark.unit
def test_fetch_tonghuashun_community_posts_returns_transparent_placeholder():
    from tradingagents.dataflows.tonghuashun_community import fetch_tonghuashun_community_posts

    result = fetch_tonghuashun_community_posts("000100.SZ", limit=30)

    assert result == "<Tonghuashun community unavailable: no stable public community-post interface configured>"


@pytest.mark.unit
def test_fetch_tonghuashun_community_posts_does_not_fabricate_posts():
    from tradingagents.dataflows.tonghuashun_community import fetch_tonghuashun_community_posts

    result = fetch_tonghuashun_community_posts("TCL科技")

    assert "阅读" not in result
    assert "评论" not in result
    assert "Link:" not in result
    assert "no stable public community-post interface" in result
