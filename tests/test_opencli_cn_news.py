import json
import subprocess
from unittest.mock import patch

import pytest

from tradingagents.dataflows.opencli_cn_news import (
    _OpenCliError,
    _dedupe_records,
    _filter_records_by_date,
    _filter_records_by_ticker,
    _format_records,
    _normalize_cn_ticker,
    _normalize_record,
    _run_opencli_json,
    get_opencli_cn_global_news,
    get_opencli_cn_news,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("symbol", "digits", "exchange", "sina_query", "aliases"),
    [
        ("600118.SS", "600118", "SH", "600118", {"600118", "SH600118", "sh600118", "600118.SS", "600118.SH"}),
        ("600118.SH", "600118", "SH", "600118", {"600118", "SH600118", "sh600118", "600118.SS", "600118.SH"}),
        ("600118", "600118", "SH", "600118", {"600118", "SH600118", "sh600118", "600118.SS", "600118.SH"}),
        ("000001.SZ", "000001", "SZ", "000001", {"000001", "SZ000001", "sz000001", "000001.SZ"}),
        ("300750", "300750", "SZ", "300750", {"300750", "SZ300750", "sz300750", "300750.SZ"}),
    ],
)
def test_normalize_cn_ticker_a_share_formats(symbol, digits, exchange, sina_query, aliases):
    normalized = _normalize_cn_ticker(symbol)

    assert normalized["supported"] is True
    assert normalized["raw"] == symbol
    assert normalized["digits"] == digits
    assert normalized["exchange"] == exchange
    assert normalized["sina_query"] == sina_query
    assert set(normalized["aliases"]) == aliases


def test_normalize_cn_ticker_accepts_chinese_name():
    normalized = _normalize_cn_ticker("中国卫星")

    assert normalized == {
        "supported": True,
        "raw": "中国卫星",
        "digits": None,
        "exchange": None,
        "sina_query": "中国卫星",
        "aliases": ["中国卫星"],
        "name_query": True,
    }


def test_normalize_cn_ticker_rejects_non_cn_ticker():
    normalized = _normalize_cn_ticker("AAPL")

    assert normalized == {
        "supported": False,
        "raw": "AAPL",
        "reason": "opencli_cn supports Chinese names and mainland A-share tickers only",
    }


def test_run_opencli_json_uses_shell_false_and_json_format():
    completed = subprocess.CompletedProcess(
        args=["opencli"],
        returncode=0,
        stdout=json.dumps([{"title": "测试新闻"}]),
        stderr="",
    )

    with patch("tradingagents.dataflows.opencli_cn_news._opencli_executable", return_value="opencli"), patch("tradingagents.dataflows.opencli_cn_news.subprocess.run", return_value=completed) as run:
        result = _run_opencli_json(["sinafinance", "news", "--limit", "1"])

    assert result == [{"title": "测试新闻"}]
    run.assert_called_once()
    args, kwargs = run.call_args
    assert args[0] == ["opencli", "sinafinance", "news", "--limit", "1", "-f", "json"]
    assert kwargs["shell"] is False
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is False
    assert kwargs["timeout"] == 15


def test_run_opencli_json_raises_on_missing_binary():
    with patch("tradingagents.dataflows.opencli_cn_news.shutil.which", return_value=None):
        with pytest.raises(_OpenCliError, match="opencli executable was not found"):
            _run_opencli_json(["sinafinance", "news"])


def test_run_opencli_json_raises_on_nonzero_exit():
    completed = subprocess.CompletedProcess(
        args=["opencli"],
        returncode=1,
        stdout="",
        stderr="INVALID_ARGUMENT",
    )

    with patch("tradingagents.dataflows.opencli_cn_news._opencli_executable", return_value="opencli"), patch("tradingagents.dataflows.opencli_cn_news.subprocess.run", return_value=completed):
        with pytest.raises(_OpenCliError, match="opencli command failed"):
            _run_opencli_json(["eastmoney", "quote", "600118.SS"])


def test_run_opencli_json_raises_on_invalid_json():
    completed = subprocess.CompletedProcess(
        args=["opencli"],
        returncode=0,
        stdout="not json",
        stderr="",
    )

    with patch("tradingagents.dataflows.opencli_cn_news._opencli_executable", return_value="opencli"), patch("tradingagents.dataflows.opencli_cn_news.subprocess.run", return_value=completed):
        with pytest.raises(_OpenCliError, match="opencli returned invalid JSON"):
            _run_opencli_json(["sinafinance", "news"])


def test_normalize_record_accepts_common_field_names():
    record = _normalize_record(
        {
            "time": "2026-05-08 09:30:00",
            "title": "中国卫星相关快讯",
            "summary": "中国卫星盘中走强。",
            "url": "https://example.com/news",
            "stocks": "SH600118,90.BK1234",
        },
        "eastmoney_kuaixun",
    )

    assert record == {
        "title": "中国卫星相关快讯",
        "summary": "中国卫星盘中走强。",
        "time": "2026-05-08 09:30:00",
        "source": "eastmoney_kuaixun",
        "url": "https://example.com/news",
        "stocks": ["SH600118", "90.BK1234"],
    }


def test_normalize_record_splits_sinafinance_content_title():
    record = _normalize_record(
        {
            "time": "2026-05-08 11:31:26",
            "content": "【午评：创业板指半日跌近1%】三大指数早盘集体下跌。",
        },
        "sinafinance",
    )

    assert record["title"] == "午评：创业板指半日跌近1%"
    assert record["summary"] == "三大指数早盘集体下跌。"


def test_filter_records_by_ticker_matches_aliases_and_text():
    records = [
        {"title": "中国卫星盘中走强", "summary": "航天板块活跃", "stocks": [], "time": None, "source": "eastmoney_kuaixun", "url": None},
        {"title": "无关新闻", "summary": "银行板块", "stocks": ["SH600000"], "time": None, "source": "eastmoney_kuaixun", "url": None},
        {"title": "航天快讯", "summary": "相关股票 SH600118", "stocks": ["SH600118"], "time": None, "source": "eastmoney_kuaixun", "url": None},
    ]

    filtered = _filter_records_by_ticker(records, ["600118", "SH600118", "中国卫星"])

    assert [record["title"] for record in filtered] == ["中国卫星盘中走强", "航天快讯"]


def test_filter_records_by_date_keeps_records_inside_range_and_unknown_time():
    records = [
        {"title": "before", "time": "2026-05-01 08:59:59", "summary": "", "source": "s", "url": None, "stocks": []},
        {"title": "inside", "time": "2026-05-08 09:00:00", "summary": "", "source": "s", "url": None, "stocks": []},
        {"title": "after", "time": "2026-05-10 09:00:00", "summary": "", "source": "s", "url": None, "stocks": []},
        {"title": "unknown", "time": None, "summary": "", "source": "s", "url": None, "stocks": []},
    ]

    filtered = _filter_records_by_date(records, "2026-05-02", "2026-05-08")

    assert [record["title"] for record in filtered] == ["inside", "unknown"]


def test_dedupe_records_uses_title_time_and_source():
    records = [
        {"title": "重复", "time": "2026-05-08 09:00:00", "source": "sinafinance", "summary": "a", "url": None, "stocks": []},
        {"title": "重复", "time": "2026-05-08 09:00:00", "source": "sinafinance", "summary": "b", "url": None, "stocks": []},
        {"title": "不同", "time": "2026-05-08 09:00:00", "source": "sinafinance", "summary": "c", "url": None, "stocks": []},
    ]

    deduped = _dedupe_records(records)

    assert [record["summary"] for record in deduped] == ["a", "c"]


def test_format_records_outputs_markdown():
    markdown = _format_records(
        [
            {
                "title": "中国卫星相关新闻",
                "summary": "摘要内容",
                "time": "2026-05-08 09:30:00",
                "source": "sinafinance",
                "url": "https://example.com/news",
                "stocks": ["SH600118"],
            }
        ],
        "## 600118.SS Chinese/A-share News",
        "未找到新闻",
    )

    assert "## 600118.SS Chinese/A-share News" in markdown
    assert "### 1. 中国卫星相关新闻" in markdown
    assert "- 时间: 2026-05-08 09:30:00" in markdown
    assert "- 来源: sinafinance" in markdown
    assert "- 相关股票: SH600118" in markdown
    assert "摘要内容" in markdown
    assert "Link: https://example.com/news" in markdown


def test_get_opencli_cn_news_uses_sinafinance_stock_records_when_present():
    sina_payload = [
        {
            "time": "2026-05-08 09:30:00",
            "title": "中国卫星获得市场关注",
            "summary": "中国卫星相关消息。",
            "url": "https://example.com/sina",
            "stocks": "SH600118",
        }
    ]

    with patch("tradingagents.dataflows.opencli_cn_news._run_opencli_json", return_value=sina_payload) as run:
        result = get_opencli_cn_news("600118.SS", "2026-05-01", "2026-05-08")

    run.assert_called_once_with(["sinafinance", "stock", "600118"])
    assert "600118.SS Chinese/A-share News" in result
    assert "中国卫星获得市场关注" in result
    assert "sinafinance" in result


def test_get_opencli_cn_news_uses_sinafinance_stock_as_name_lookup_before_news_filter():
    stock_payload = [{"Symbol": "SH600118", "Name": "中国卫星", "Price": "113.220"}]
    news_payload = [
        {
            "time": "2026-05-08 09:30:00",
            "title": "中国卫星相关新闻",
            "summary": "市场关注航天板块。",
        },
        {
            "time": "2026-05-08 09:31:00",
            "title": "无关新闻",
            "summary": "银行板块活跃。",
        },
    ]

    with patch("tradingagents.dataflows.opencli_cn_news._run_opencli_json", side_effect=[stock_payload, news_payload]) as run:
        result = get_opencli_cn_news("600118.SS", "2026-05-01", "2026-05-08")

    assert run.call_args_list[0].args[0] == ["sinafinance", "stock", "600118"]
    assert run.call_args_list[1].args[0] == ["sinafinance", "news", "--limit", "50", "--type", "1"]
    assert "中国卫星相关新闻" in result
    assert "无关新闻" not in result


def test_get_opencli_cn_news_falls_back_to_eastmoney_kuaixun_when_sina_empty():
    eastmoney_payload = [
        {
            "time": "2026-05-08 10:00:00",
            "title": "航天板块异动",
            "summary": "中国卫星盘中走强。",
            "stocks": "SH600118",
        },
        {
            "time": "2026-05-08 10:01:00",
            "title": "银行板块异动",
            "summary": "银行股上涨。",
            "stocks": "SH600000",
        },
    ]

    with patch(
        "tradingagents.dataflows.opencli_cn_news._run_opencli_json",
        side_effect=[[], [], eastmoney_payload],
    ) as run:
        result = get_opencli_cn_news("600118.SS", "2026-05-01", "2026-05-08")

    assert run.call_args_list[0].args[0] == ["sinafinance", "stock", "600118"]
    assert run.call_args_list[1].args[0] == ["sinafinance", "news", "--limit", "50", "--type", "1"]
    assert run.call_args_list[2].args[0] == ["eastmoney", "kuaixun", "--limit", "50"]
    assert "航天板块异动" in result
    assert "银行板块异动" not in result
    assert "eastmoney_kuaixun" in result


def test_get_opencli_cn_news_returns_unsupported_message_for_us_ticker():
    result = get_opencli_cn_news("AAPL", "2026-05-01", "2026-05-08")

    assert "opencli_cn supports Chinese names and mainland A-share tickers only" in result
    assert "AAPL" in result


def test_get_opencli_cn_news_returns_empty_message_when_sources_fail():
    with patch(
        "tradingagents.dataflows.opencli_cn_news._run_opencli_json",
        side_effect=_OpenCliError("network failed"),
    ):
        result = get_opencli_cn_news("600118.SS", "2026-05-01", "2026-05-08")

    assert "No Chinese/A-share news found for 600118.SS" in result
    assert "sinafinance stock" in result
    assert "sinafinance news" in result
    assert "eastmoney kuaixun" in result


def test_get_opencli_cn_global_news_uses_sinafinance_news():
    sina_payload = [
        {
            "time": "2026-05-08 11:00:00",
            "title": "A股三大指数震荡",
            "summary": "市场成交活跃。",
        }
    ]

    with patch("tradingagents.dataflows.opencli_cn_news._run_opencli_json", return_value=sina_payload) as run:
        result = get_opencli_cn_global_news("2026-05-08", look_back_days=7, limit=5)

    run.assert_called_once_with(["sinafinance", "news", "--limit", "5", "--type", "1"])
    assert "Chinese Financial Market News" in result
    assert "A股三大指数震荡" in result
    assert "sinafinance" in result


def test_get_opencli_cn_global_news_falls_back_to_eastmoney_kuaixun():
    eastmoney_payload = [
        {
            "time": "2026-05-08 11:10:00",
            "title": "证券板块异动拉升",
            "summary": "证券板块午后走强。",
        }
    ]

    with patch(
        "tradingagents.dataflows.opencli_cn_news._run_opencli_json",
        side_effect=[[], eastmoney_payload],
    ) as run:
        result = get_opencli_cn_global_news("2026-05-08", look_back_days=7, limit=5)

    assert run.call_args_list[0].args[0] == ["sinafinance", "news", "--limit", "5", "--type", "1"]
    assert run.call_args_list[1].args[0] == ["eastmoney", "kuaixun", "--limit", "5"]
    assert "证券板块异动拉升" in result
    assert "eastmoney_kuaixun" in result


def test_get_opencli_cn_global_news_clamps_limit():
    with patch("tradingagents.dataflows.opencli_cn_news._run_opencli_json", return_value=[]) as run:
        get_opencli_cn_global_news("2026-05-08", look_back_days=7, limit=500)

    assert run.call_args_list[0].args[0] == ["sinafinance", "news", "--limit", "50", "--type", "1"]


def test_opencli_cn_registered_for_news_methods():
    from tradingagents.dataflows.interface import VENDOR_LIST, VENDOR_METHODS

    assert "opencli_cn" in VENDOR_LIST
    assert "opencli_cn" in VENDOR_METHODS["get_news"]
    assert "opencli_cn" in VENDOR_METHODS["get_global_news"]
    assert "opencli_cn" not in VENDOR_METHODS["get_insider_transactions"]


def test_default_news_data_vendor_is_opencli_cn():
    from tradingagents.default_config import DEFAULT_CONFIG

    assert DEFAULT_CONFIG["data_vendors"]["news_data"] == "opencli_cn"


def test_route_to_vendor_can_call_opencli_cn_news(monkeypatch):
    import tradingagents.dataflows.interface as interface

    monkeypatch.setattr(interface, "get_vendor", lambda category, method=None: "opencli_cn")
    monkeypatch.setattr(
        interface,
        "load_cached_vendor_result",
        lambda method, vendor, args, kwargs: None,
    )
    saved = {}

    def fake_save(method, vendor, args, kwargs, result):
        saved["method"] = method
        saved["vendor"] = vendor
        saved["result"] = result

    monkeypatch.setattr(interface, "save_cached_vendor_result", fake_save)
    monkeypatch.setitem(
        interface.VENDOR_METHODS["get_news"],
        "opencli_cn",
        lambda ticker, start_date, end_date: f"news for {ticker} from {start_date} to {end_date}",
    )

    result = interface.route_to_vendor("get_news", "600118.SS", "2026-05-01", "2026-05-08")

    assert result == "news for 600118.SS from 2026-05-01 to 2026-05-08"
    assert saved == {
        "method": "get_news",
        "vendor": "opencli_cn",
        "result": result,
    }
