"""opencli-based Chinese/A-share news provider."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, timedelta
from typing import Any

from .cls_news import ClsNewsError, get_cls_kuaixun_records

_CN_NAME_RE = re.compile(r"^[一-鿿A-Za-z0-9·（）()\-\s]+$")
_A_SHARE_RE = re.compile(r"^(?P<digits>\d{6})(?:\.(?P<suffix>SS|SH|SZ|BJ))?$", re.IGNORECASE)


def get_opencli_cn_news(ticker: str, start_date: str, end_date: str) -> str:
    normalized = _normalize_cn_ticker(ticker)
    if not normalized["supported"]:
        return f"opencli_cn could not fetch news for {ticker}: {normalized['reason']}"

    aliases = list(normalized["aliases"])
    records: list[dict[str, Any]] = []

    try:
        stock_payload = _run_opencli_json(["sinafinance", "stock", normalized["sina_query"]])
        aliases.extend(alias for alias in _extract_stock_aliases(stock_payload) if alias not in aliases)
        records.extend(_news_records_from_payload(stock_payload, "sinafinance"))
    except _OpenCliError:
        pass

    records = _filter_records_by_date(records, start_date, end_date)

    if not records:
        try:
            sina_news_payload = _run_opencli_json(["sinafinance", "news", "--limit", "50", "--type", "1"])
            sina_news_records = _records_from_payload(sina_news_payload, "sinafinance")
            sina_news_records = _filter_records_by_ticker(sina_news_records, aliases)
            records.extend(_filter_records_by_date(sina_news_records, start_date, end_date))
        except _OpenCliError:
            pass

    if not records:
        try:
            cls_records = get_cls_kuaixun_records(limit=50)
            cls_records = _filter_records_by_ticker(cls_records, aliases)
            records.extend(_filter_records_by_date(cls_records, start_date, end_date))
        except ClsNewsError:
            pass

    if not records:
        try:
            eastmoney_payload = _run_opencli_json(["eastmoney", "kuaixun", "--limit", "50"])
            eastmoney_records = _records_from_payload(eastmoney_payload, "eastmoney_kuaixun")
            eastmoney_records = _filter_records_by_ticker(eastmoney_records, aliases)
            records.extend(_filter_records_by_date(eastmoney_records, start_date, end_date))
        except _OpenCliError:
            pass

    records = _dedupe_records(records)
    heading = f"## {ticker} Chinese/A-share News, from {start_date} to {end_date}:"
    empty_message = (
        f"No Chinese/A-share news found for {ticker} from opencli_cn between {start_date} and {end_date}.\n\n"
        "Tried sources:\n"
        "- sinafinance stock\n"
        "- sinafinance news\n"
        "- cls kuaixun\n"
        "- eastmoney kuaixun"
    )
    return _format_records(records, heading, empty_message)


def get_opencli_cn_global_news(curr_date: str, look_back_days: int = 7, limit: int = 10) -> str:
    safe_limit = max(1, min(int(limit), 50))
    start_date = (datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=look_back_days)).strftime("%Y-%m-%d")
    records: list[dict[str, Any]] = []

    try:
        cls_records = get_cls_kuaixun_records(limit=safe_limit)
        records.extend(_filter_records_by_date(cls_records, start_date, curr_date))
    except ClsNewsError:
        pass

    if not records:
        try:
            sina_payload = _run_opencli_json(["sinafinance", "news", "--limit", str(safe_limit), "--type", "1"])
            sina_records = _records_from_payload(sina_payload, "sinafinance")
            records.extend(_filter_records_by_date(sina_records, start_date, curr_date))
        except _OpenCliError:
            pass

    if not records:
        try:
            eastmoney_payload = _run_opencli_json(["eastmoney", "kuaixun", "--limit", str(safe_limit)])
            eastmoney_records = _records_from_payload(eastmoney_payload, "eastmoney_kuaixun")
            records.extend(_filter_records_by_date(eastmoney_records, start_date, curr_date))
        except _OpenCliError:
            pass

    records = _dedupe_records(records)[:safe_limit]
    heading = f"## Chinese Financial Market News, from {start_date} to {curr_date}:"
    empty_message = (
        f"No Chinese financial market news found from opencli_cn for {curr_date}.\n\n"
        "Tried sources:\n"
        "- cls kuaixun\n"
        "- sinafinance news\n"
        "- eastmoney kuaixun"
    )
    return _format_records(records, heading, empty_message)


def _normalize_cn_ticker(symbol: str) -> dict[str, Any]:
    raw = symbol.strip()
    match = _A_SHARE_RE.fullmatch(raw)

    if match:
        digits = match.group("digits")
        suffix = (match.group("suffix") or "").upper()
        exchange = _infer_exchange(digits, suffix)
        if exchange is None:
            return {
                "supported": False,
                "raw": raw,
                "reason": "unsupported mainland A-share exchange prefix",
            }

        aliases = [digits, f"{exchange}{digits}", f"{exchange.lower()}{digits}"]
        if exchange == "SH":
            aliases.extend([f"{digits}.SS", f"{digits}.SH"])
        else:
            aliases.append(f"{digits}.{exchange}")

        return {
            "supported": True,
            "raw": raw,
            "digits": digits,
            "exchange": exchange,
            "sina_query": digits,
            "aliases": aliases,
        }

    if raw and _CN_NAME_RE.fullmatch(raw) and any("一" <= char <= "鿿" for char in raw):
        return {
            "supported": True,
            "raw": raw,
            "digits": None,
            "exchange": None,
            "sina_query": raw,
            "aliases": [raw],
            "name_query": True,
        }

    return {
        "supported": False,
        "raw": raw,
        "reason": "opencli_cn supports Chinese names and mainland A-share tickers only",
    }


def _infer_exchange(digits: str, suffix: str) -> str | None:
    if suffix in {"SS", "SH"}:
        return "SH"
    if suffix == "SZ":
        return "SZ"
    if suffix == "BJ":
        return "BJ"
    if digits.startswith(("6", "9")):
        return "SH"
    if digits.startswith(("0", "2", "3")):
        return "SZ"
    if digits.startswith(("4", "8")):
        return "BJ"
    return None


class _OpenCliError(RuntimeError):
    pass


def _opencli_executable() -> str:
    executable = shutil.which("opencli") or shutil.which("opencli.cmd")
    if executable is None:
        raise _OpenCliError("opencli executable was not found")
    return executable


def _run_opencli_json(args: list[str], timeout: int = 15) -> Any:
    executable = _opencli_executable()
    command = [executable, *args]
    if "-f" not in command and "--format" not in command:
        command.extend(["-f", "json"])

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=False,
            timeout=timeout,
            check=False,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise _OpenCliError("opencli executable was not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise _OpenCliError("opencli command timed out") from exc

    stdout = _decode_opencli_output(completed.stdout)
    stderr = _decode_opencli_output(completed.stderr)

    if completed.returncode != 0:
        detail = stderr.strip() or stdout.strip() or f"exit code {completed.returncode}"
        raise _OpenCliError(f"opencli command failed: {detail}")

    try:
        return json.loads(stdout or "null")
    except json.JSONDecodeError as exc:
        raise _OpenCliError("opencli returned invalid JSON") from exc


def _decode_opencli_output(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    for encoding in ("utf-8", "gb18030"):
        try:
            return value.decode(encoding)
        except UnicodeDecodeError:
            continue
    return value.decode("utf-8", errors="replace")


def _normalize_record(raw: dict[str, Any], source: str) -> dict[str, Any]:
    stocks = raw.get("stocks") or raw.get("stock") or raw.get("Symbol") or raw.get("symbol") or []
    if isinstance(stocks, str):
        stocks = [item.strip() for item in re.split(r"[,，]", stocks) if item.strip()]
    elif not isinstance(stocks, list):
        stocks = [str(stocks)] if stocks else []

    content = raw.get("content")
    title = raw.get("title") or raw.get("headline") or raw.get("name") or raw.get("Name")
    summary = raw.get("summary") or raw.get("description") or raw.get("Description") or ""
    if not title and content:
        title, summary = _split_content_title_summary(str(content))
    time_value = raw.get("time") or raw.get("date") or raw.get("datetime") or raw.get("publishTime")
    url = raw.get("url") or raw.get("link") or raw.get("Link") or ""

    return {
        "title": str(title).strip() or "No title",
        "summary": str(summary).strip(),
        "time": str(time_value).strip() if time_value else None,
        "source": source,
        "url": str(url).strip() or None,
        "stocks": [str(stock).strip() for stock in stocks if str(stock).strip()],
    }


def _split_content_title_summary(content: str) -> tuple[str, str]:
    text = content.strip()
    if text.startswith("【") and "】" in text:
        title, summary = text[1:].split("】", 1)
        return title.strip(), summary.strip()
    return text, ""


def _news_records_from_payload(payload: Any, source: str) -> list[dict[str, Any]]:
    records = _records_from_payload(payload, source)
    return [
        record
        for record in records
        if record["title"] != "No title" and (record.get("summary") or record.get("time") or record.get("url"))
    ]


def _records_from_payload(payload: Any, source: str) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, dict):
        for key in ("data", "items", "results", "list"):
            value = payload.get(key)
            if isinstance(value, list):
                return [_normalize_record(item, source) for item in value if isinstance(item, dict)]
        return [_normalize_record(payload, source)]
    if isinstance(payload, list):
        return [_normalize_record(item, source) for item in payload if isinstance(item, dict)]
    return []


def _extract_stock_aliases(payload: Any) -> list[str]:
    aliases = []
    for item in _payload_items(payload):
        for key in ("Name", "name", "Symbol", "symbol", "code", "Code"):
            value = item.get(key)
            if value:
                aliases.append(str(value).strip())
    return [alias for alias in aliases if alias]


def _payload_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "items", "results", "list"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def _filter_records_by_ticker(records: list[dict[str, Any]], aliases: list[str]) -> list[dict[str, Any]]:
    normalized_aliases = {alias.lower() for alias in aliases if alias}
    filtered = []

    for record in records:
        stock_text = " ".join(record.get("stocks", [])).lower()
        body_text = f"{record.get('title', '')} {record.get('summary', '')}".lower()
        if any(alias in stock_text or alias in body_text for alias in normalized_aliases):
            filtered.append(record)

    return filtered


def _filter_records_by_date(records: list[dict[str, Any]], start_date: str, end_date: str) -> list[dict[str, Any]]:
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    filtered = []

    for record in records:
        value = record.get("time")
        if not value:
            filtered.append(record)
            continue

        parsed = _parse_time(value)
        if parsed is None or start_dt <= parsed <= end_dt:
            filtered.append(record)

    return filtered


def _parse_time(value: str) -> datetime | None:
    normalized = value[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    return None


def _dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []

    for record in records:
        key = (record.get("title"), record.get("time"), record.get("source"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)

    return deduped


def _format_records(records: list[dict[str, Any]], heading: str, empty_message: str) -> str:
    if not records:
        return empty_message

    lines = [heading, ""]
    for index, record in enumerate(records, start=1):
        lines.append(f"### {index}. {record['title']}")
        lines.append("")
        lines.append(f"- 时间: {record.get('time') or '未提供'}")
        lines.append(f"- 来源: {record['source']}")
        if record.get("stocks"):
            lines.append(f"- 相关股票: {', '.join(record['stocks'])}")
        if record.get("summary"):
            lines.append(f"- 摘要: {record['summary']}")
        if record.get("url"):
            lines.append(f"Link: {record['url']}")
        lines.append("")

    return "\n".join(lines).strip()
