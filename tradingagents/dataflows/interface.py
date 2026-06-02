import os
from typing import Annotated

# Import from vendor-specific modules
from .y_finance import (
    get_YFin_data_online,
    get_stock_stats_indicators_window,
    get_fundamentals as get_yfinance_fundamentals,
    get_balance_sheet as get_yfinance_balance_sheet,
    get_cashflow as get_yfinance_cashflow,
    get_income_statement as get_yfinance_income_statement,
    get_insider_transactions as get_yfinance_insider_transactions,
)
from .yfinance_news import get_news_yfinance, get_global_news_yfinance
from .opencli_cn_news import get_opencli_cn_news, get_opencli_cn_global_news
from .market_utils import has_chinese_characters, is_mainland_a_share_ticker
from .tushare import (
    get_stock_data as get_tushare_stock,
    get_fundamentals as get_tushare_fundamentals,
    get_balance_sheet as get_tushare_balance_sheet,
    get_cashflow as get_tushare_cashflow,
    get_income_statement as get_tushare_income_statement,
)
from .akshare import (
    get_stock_data as get_akshare_stock,
    get_indicators as get_akshare_indicator,
    get_fundamentals as get_akshare_fundamentals,
    get_balance_sheet as get_akshare_balance_sheet,
    get_cashflow as get_akshare_cashflow,
    get_income_statement as get_akshare_income_statement,
    get_news as get_akshare_news,
)
from .alpha_vantage import (
    get_stock as get_alpha_vantage_stock,
    get_indicator as get_alpha_vantage_indicator,
    get_fundamentals as get_alpha_vantage_fundamentals,
    get_balance_sheet as get_alpha_vantage_balance_sheet,
    get_cashflow as get_alpha_vantage_cashflow,
    get_income_statement as get_alpha_vantage_income_statement,
    get_insider_transactions as get_alpha_vantage_insider_transactions,
    get_news as get_alpha_vantage_news,
    get_global_news as get_alpha_vantage_global_news,
)
from .alpha_vantage_common import AlphaVantageRateLimitError
from .cache import load_cached_vendor_result, save_cached_vendor_result

# Configuration and routing logic
from .config import get_config

# Tools organized by category
TOOLS_CATEGORIES = {
    "core_stock_apis": {
        "description": "OHLCV stock price data",
        "tools": [
            "get_stock_data"
        ]
    },
    "technical_indicators": {
        "description": "Technical analysis indicators",
        "tools": [
            "get_indicators"
        ]
    },
    "fundamental_data": {
        "description": "Company fundamentals",
        "tools": [
            "get_fundamentals",
            "get_balance_sheet",
            "get_cashflow",
            "get_income_statement"
        ]
    },
    "news_data": {
        "description": "News and insider data",
        "tools": [
            "get_news",
            "get_global_news",
            "get_insider_transactions",
        ]
    }
}

VENDOR_LIST = [
    "opencli_cn",
    "tushare",
    "akshare",
    "yfinance",
    "alpha_vantage",
]

# Mapping of methods to their vendor-specific implementations
VENDOR_METHODS = {
    # core_stock_apis
    "get_stock_data": {
        "tushare": get_tushare_stock,
        "akshare": get_akshare_stock,
        "alpha_vantage": get_alpha_vantage_stock,
        "yfinance": get_YFin_data_online,
    },
    # technical_indicators
    "get_indicators": {
        "akshare": get_akshare_indicator,
        "alpha_vantage": get_alpha_vantage_indicator,
        "yfinance": get_stock_stats_indicators_window,
    },
    # fundamental_data
    "get_fundamentals": {
        "tushare": get_tushare_fundamentals,
        "akshare": get_akshare_fundamentals,
        "alpha_vantage": get_alpha_vantage_fundamentals,
        "yfinance": get_yfinance_fundamentals,
    },
    "get_balance_sheet": {
        "tushare": get_tushare_balance_sheet,
        "akshare": get_akshare_balance_sheet,
        "alpha_vantage": get_alpha_vantage_balance_sheet,
        "yfinance": get_yfinance_balance_sheet,
    },
    "get_cashflow": {
        "tushare": get_tushare_cashflow,
        "akshare": get_akshare_cashflow,
        "alpha_vantage": get_alpha_vantage_cashflow,
        "yfinance": get_yfinance_cashflow,
    },
    "get_income_statement": {
        "tushare": get_tushare_income_statement,
        "akshare": get_akshare_income_statement,
        "alpha_vantage": get_alpha_vantage_income_statement,
        "yfinance": get_yfinance_income_statement,
    },
    # news_data
    "get_news": {
        "akshare": get_akshare_news,
        "opencli_cn": get_opencli_cn_news,
        "alpha_vantage": get_alpha_vantage_news,
        "yfinance": get_news_yfinance,
    },
    "get_global_news": {
        "opencli_cn": get_opencli_cn_global_news,
        "yfinance": get_global_news_yfinance,
        "alpha_vantage": get_alpha_vantage_global_news,
    },
    "get_insider_transactions": {
        "alpha_vantage": get_alpha_vantage_insider_transactions,
        "yfinance": get_yfinance_insider_transactions,
    },
}

CN_VENDOR_PRIORITY = {
    "get_stock_data": ["tushare", "akshare"],
    "get_indicators": ["akshare", "tushare"],
    "get_fundamentals": ["tushare", "akshare"],
    "get_balance_sheet": ["tushare", "akshare"],
    "get_cashflow": ["tushare", "akshare"],
    "get_income_statement": ["tushare", "akshare"],
    "get_news": ["akshare", "opencli_cn"],
}


def get_category_for_method(method: str) -> str:
    """Get the category that contains the specified method."""
    for category, info in TOOLS_CATEGORIES.items():
        if method in info["tools"]:
            return category
    raise ValueError(f"Method '{method}' not found in any category")

def get_vendor(category: str, method: str = None) -> str:
    """Get the configured vendor for a data category or specific tool method.
    Tool-level configuration takes precedence over category-level.
    """
    config = get_config()

    # Check tool-level configuration first (if method provided)
    if method:
        tool_vendors = config.get("tool_vendors", {})
        if method in tool_vendors:
            return tool_vendors[method]

    # Fall back to category-level configuration
    return config.get("data_vendors", {}).get(category, "default")

def _extract_instrument_for_method(method: str, args, kwargs):
    if method == "get_global_news":
        return None

    for key in ("symbol", "ticker"):
        if key in kwargs:
            return kwargs[key]

    if args:
        return args[0]

    return None


def _ordered_unique(vendors):
    ordered = []
    for vendor in vendors:
        if vendor and vendor not in ordered:
            ordered.append(vendor)
    return ordered


def _is_cn_instrument_for_method(method: str, instrument) -> bool:
    if method == "get_news":
        return is_mainland_a_share_ticker(instrument) or has_chinese_characters(instrument)
    return is_mainland_a_share_ticker(instrument)


def _build_fallback_vendors(method: str, vendor_config: str, args, kwargs):
    primary_vendors = [v.strip() for v in vendor_config.split(",")]
    instrument = _extract_instrument_for_method(method, args, kwargs)
    all_available_vendors = list(VENDOR_METHODS[method].keys())

    if method in CN_VENDOR_PRIORITY and _is_cn_instrument_for_method(method, instrument):
        return _ordered_unique(CN_VENDOR_PRIORITY[method] + primary_vendors + all_available_vendors)

    overseas_vendors = [vendor for vendor in all_available_vendors if vendor not in {"tushare", "akshare"}]
    return _ordered_unique(primary_vendors + overseas_vendors)


def _prepare_vendor_call_args(method: str, args):
    if method != "get_global_news":
        return args

    prepared = list(args)
    while prepared and prepared[-1] is None:
        prepared.pop()
    return tuple(prepared)


def _opencli_cn_result_should_fallback(method: str, result: str) -> bool:
    lowered = result.lower()
    return (
        "opencli_cn could not fetch news" in lowered
        or "supports chinese names and mainland a-share tickers only" in lowered
        or "no chinese/a-share news found" in lowered
        or "no chinese financial market news found" in lowered
    )


def route_to_vendor(method: str, *args, **kwargs):
    """Route method calls to appropriate vendor implementation with fallback support."""
    category = get_category_for_method(method)
    vendor_config = get_vendor(category, method)

    if method not in VENDOR_METHODS:
        raise ValueError(f"Method '{method}' not supported")

    fallback_vendors = _build_fallback_vendors(method, vendor_config, args, kwargs)

    last_error = None

    last_no_data: NoMarketDataError | None = None
    first_error: Exception | None = None
    for vendor in fallback_vendors:
        if vendor not in VENDOR_METHODS[method]:
            continue

        cached = load_cached_vendor_result(method, vendor, args, kwargs)
        if cached is not None:
            return cached

        vendor_impl = VENDOR_METHODS[method][vendor]
        impl_func = vendor_impl[0] if isinstance(vendor_impl, list) else vendor_impl
        call_args = _prepare_vendor_call_args(method, args)

        try:
            result = impl_func(*call_args, **kwargs)

            # opencli_cn 在非 A 股/中文标的或无结果时可能返回文本而非抛错；
            # 这种场景应触发 fallback 到后续 vendor，而不是被当作成功结果。
            if (
                vendor == "opencli_cn"
                and method in {"get_news", "get_global_news"}
                and isinstance(result, str)
                and _opencli_cn_result_should_fallback(method, result)
            ):
                last_error = RuntimeError(result)
                continue

            save_cached_vendor_result(method, vendor, args, kwargs, result)
            return result
        except AlphaVantageRateLimitError as e:
            # Expected transient error: try next vendor
            last_error = e
            continue
        except Exception as e:
            # Non-rate-limit vendor failures (e.g., upstream TLS/network/data-source issues)
            # should also trigger fallback to improve resilience.
            # If Alpha Vantage key is missing, treat it as a skippable fallback condition
            # and avoid overriding a more meaningful prior vendor failure.
            if (
                vendor == "alpha_vantage"
                and "ALPHA_VANTAGE_API_KEY" in str(e)
                and "not set" in str(e)
            ):
                if last_error is None:
                    last_error = e
                continue

            last_error = e
            continue

    if last_error is not None:
        raise RuntimeError(
            f"No available vendor for '{method}'. Last error: {last_error}"
        ) from last_error

    raise RuntimeError(f"No available vendor for '{method}'")
