import copy

import pytest

import tradingagents.default_config as default_config
import tradingagents.dataflows.config as dataflow_config
from tradingagents.dataflows import interface


BASE_CONFIG = copy.deepcopy(default_config.DEFAULT_CONFIG)


@pytest.fixture(autouse=True)
def reset_config():
    config = copy.deepcopy(BASE_CONFIG)
    config["data_vendors"] = {
        "core_stock_apis": "yfinance",
        "technical_indicators": "yfinance",
        "fundamental_data": "yfinance",
        "news_data": "opencli_cn",
    }
    config["tool_vendors"] = {}
    dataflow_config._config = None
    dataflow_config.set_config(config)
    yield
    dataflow_config._config = None
    dataflow_config.set_config(config)


@pytest.fixture
def isolated_cache(monkeypatch):
    monkeypatch.setattr(interface, "load_cached_vendor_result", lambda *args, **kwargs: None)
    monkeypatch.setattr(interface, "save_cached_vendor_result", lambda *args, **kwargs: None)


@pytest.mark.unit
def test_a_share_stock_data_prefers_tushare_then_akshare_then_existing_vendors(monkeypatch, isolated_cache):
    calls = []

    def failing_vendor(name):
        def impl(*args, **kwargs):
            calls.append(name)
            raise RuntimeError(f"{name} unavailable")
        return impl

    def yfinance_impl(*args, **kwargs):
        calls.append("yfinance")
        return "yfinance result"

    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_stock_data",
        {
            "tushare": failing_vendor("tushare"),
            "akshare": failing_vendor("akshare"),
            "yfinance": yfinance_impl,
            "alpha_vantage": failing_vendor("alpha_vantage"),
        },
    )
    dataflow_config.set_config({"data_vendors": {"core_stock_apis": "yfinance"}})

    result = interface.route_to_vendor("get_stock_data", "600118.SS", "2026-01-01", "2026-01-02")

    assert result == "yfinance result"
    assert calls == ["tushare", "akshare", "yfinance"]


@pytest.mark.unit
def test_overseas_stock_data_does_not_try_cn_vendors(monkeypatch, isolated_cache):
    calls = []

    def unexpected_cn_vendor(name):
        def impl(*args, **kwargs):
            calls.append(name)
            raise AssertionError(f"{name} should not be called")
        return impl

    def yfinance_impl(*args, **kwargs):
        calls.append("yfinance")
        return "yfinance result"

    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_stock_data",
        {
            "tushare": unexpected_cn_vendor("tushare"),
            "akshare": unexpected_cn_vendor("akshare"),
            "yfinance": yfinance_impl,
            "alpha_vantage": unexpected_cn_vendor("alpha_vantage"),
        },
    )

    result = interface.route_to_vendor("get_stock_data", "AAPL", "2026-01-01", "2026-01-02")

    assert result == "yfinance result"
    assert calls == ["yfinance"]


@pytest.mark.unit
def test_a_share_fundamentals_prefers_tushare_then_akshare(monkeypatch, isolated_cache):
    calls = []

    def tushare_impl(*args, **kwargs):
        calls.append("tushare")
        return "tushare fundamentals"

    def akshare_impl(*args, **kwargs):
        calls.append("akshare")
        return "akshare fundamentals"

    def yfinance_impl(*args, **kwargs):
        calls.append("yfinance")
        return "yfinance fundamentals"

    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_fundamentals",
        {
            "tushare": tushare_impl,
            "akshare": akshare_impl,
            "yfinance": yfinance_impl,
        },
    )

    result = interface.route_to_vendor("get_fundamentals", "000001.SZ")

    assert result == "tushare fundamentals"
    assert calls == ["tushare"]


@pytest.mark.unit
def test_overseas_fundamentals_keeps_existing_vendor_order(monkeypatch, isolated_cache):
    calls = []

    def yfinance_impl(*args, **kwargs):
        calls.append("yfinance")
        raise RuntimeError("yfinance unavailable")

    def alpha_vantage_impl(*args, **kwargs):
        calls.append("alpha_vantage")
        return "alpha fundamentals"

    def cn_impl(name):
        def impl(*args, **kwargs):
            calls.append(name)
            raise AssertionError(f"{name} should not be called")
        return impl

    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_fundamentals",
        {
            "tushare": cn_impl("tushare"),
            "akshare": cn_impl("akshare"),
            "yfinance": yfinance_impl,
            "alpha_vantage": alpha_vantage_impl,
        },
    )

    result = interface.route_to_vendor("get_fundamentals", "AAPL")

    assert result == "alpha fundamentals"
    assert calls == ["yfinance", "alpha_vantage"]


@pytest.mark.unit
def test_global_news_is_not_market_aware(monkeypatch, isolated_cache):
    calls = []

    def opencli_impl(*args, **kwargs):
        calls.append("opencli_cn")
        return "global news"

    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_global_news",
        {
            "opencli_cn": opencli_impl,
            "yfinance": lambda *args, **kwargs: "yfinance news",
            "alpha_vantage": lambda *args, **kwargs: "alpha news",
        },
    )

    result = interface.route_to_vendor("get_global_news", "2026-01-01", "2026-01-02")

    assert result == "global news"
    assert calls == ["opencli_cn"]


@pytest.mark.unit
def test_chinese_name_news_prefers_akshare_then_opencli_cn(monkeypatch, isolated_cache):
    calls = []

    def akshare_impl(*args, **kwargs):
        calls.append("akshare")
        return "akshare news"

    def opencli_impl(*args, **kwargs):
        calls.append("opencli_cn")
        return "cn news"

    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_news",
        {
            "akshare": akshare_impl,
            "opencli_cn": opencli_impl,
            "yfinance": lambda *args, **kwargs: "yfinance news",
            "alpha_vantage": lambda *args, **kwargs: "alpha news",
        },
    )

    result = interface.route_to_vendor("get_news", "贵州茅台", "2026-01-01", "2026-01-02")

    assert result == "akshare news"
    assert calls == ["akshare"]


@pytest.mark.unit
def test_a_share_news_falls_back_from_akshare_to_opencli_cn(monkeypatch, isolated_cache):
    calls = []

    def akshare_impl(*args, **kwargs):
        calls.append("akshare")
        raise RuntimeError("akshare unavailable")

    def opencli_impl(*args, **kwargs):
        calls.append("opencli_cn")
        return "cn news"

    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_news",
        {
            "akshare": akshare_impl,
            "opencli_cn": opencli_impl,
            "yfinance": lambda *args, **kwargs: "yfinance news",
            "alpha_vantage": lambda *args, **kwargs: "alpha news",
        },
    )

    result = interface.route_to_vendor("get_news", "600519.SH", "2026-01-01", "2026-01-02")

    assert result == "cn news"
    assert calls == ["akshare", "opencli_cn"]


@pytest.mark.unit
def test_global_news_preserves_middle_none_optional_arg(monkeypatch, isolated_cache):
    calls = []

    def opencli_impl(curr_date, look_back_days=None, limit=10):
        calls.append((curr_date, look_back_days, limit))
        return "global news"

    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_global_news",
        {
            "opencli_cn": opencli_impl,
            "yfinance": lambda *args, **kwargs: "yfinance news",
            "alpha_vantage": lambda *args, **kwargs: "alpha news",
        },
    )

    result = interface.route_to_vendor("get_global_news", "2026-01-01", None, 5)

    assert result == "global news"
    assert calls == [("2026-01-01", None, 5)]


@pytest.mark.unit
def test_global_news_omitted_optional_args_use_provider_defaults(monkeypatch, isolated_cache):
    calls = []

    def opencli_impl(curr_date, look_back_days=7, limit=10):
        calls.append((curr_date, look_back_days, limit))
        return "global news"

    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_global_news",
        {
            "opencli_cn": opencli_impl,
            "yfinance": lambda *args, **kwargs: "yfinance news",
            "alpha_vantage": lambda *args, **kwargs: "alpha news",
        },
    )

    result = interface.route_to_vendor("get_global_news", "2026-01-01", None, None)

    assert result == "global news"
    assert calls == [("2026-01-01", 7, 10)]


@pytest.mark.unit
def test_opencli_cn_empty_global_news_falls_back_to_next_vendor(monkeypatch, isolated_cache):
    calls = []

    def opencli_impl(*args, **kwargs):
        calls.append("opencli_cn")
        return "No Chinese financial market news found from opencli_cn for 2026-01-01."

    def yfinance_impl(*args, **kwargs):
        calls.append("yfinance")
        return "yfinance global news"

    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_global_news",
        {
            "opencli_cn": opencli_impl,
            "yfinance": yfinance_impl,
            "alpha_vantage": lambda *args, **kwargs: "alpha news",
        },
    )

    result = interface.route_to_vendor("get_global_news", "2026-01-01", 7, 10)

    assert result == "yfinance global news"
    assert calls == ["opencli_cn", "yfinance"]
