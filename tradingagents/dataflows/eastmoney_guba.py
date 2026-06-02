from __future__ import annotations

import contextlib
import io
from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from parsel import Selector

from .market_utils import has_chinese_characters, is_mainland_a_share_ticker, normalize_a_share_ticker

_API = "https://guba.eastmoney.com/list,{code}.html"
_BASE_URL = "https://guba.eastmoney.com"
_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"


def fetch_eastmoney_guba_posts(symbol: str, limit: int = 30, timeout: float = 10.0) -> str:
    identity = _resolve_a_share_identity(symbol)
    if not identity["supported"]:
        return "<eastmoney guba supports mainland A-share tickers or Chinese stock names only>"

    url = _API.format(code=identity["code"])
    request = Request(url, headers={"User-Agent": _UA, "Accept": "text/html"})
    try:
        with urlopen(request, timeout=timeout) as response:
            html = _decode_html(response.read())
    except (HTTPError, URLError, TimeoutError) as exc:
        return f"<eastmoney guba unavailable: {type(exc).__name__}>"

    posts = _parse_guba_posts(html, limit=limit)
    if not posts:
        return f"<no Eastmoney Guba posts found for {_identity_label(identity)}>"
    return _format_posts(identity, posts)


def _resolve_a_share_identity(symbol: str) -> dict[str, object]:
    raw = str(symbol).strip()

    if is_mainland_a_share_ticker(raw):
        normalized = normalize_a_share_ticker(raw)
        code, suffix = normalized.split(".", 1)
        name = _stock_name_by_code().get(code, "")
        ticker = _display_ticker(code, suffix)
        return {
            "supported": True,
            "raw": raw,
            "code": code,
            "ticker": ticker,
            "name": name,
            "aliases": _aliases(code, suffix, name),
        }

    if has_chinese_characters(raw):
        for code, name in _stock_name_by_code().items():
            if name == raw:
                suffix = _infer_exchange_suffix(code)
                return {
                    "supported": True,
                    "raw": raw,
                    "code": code,
                    "ticker": _display_ticker(code, suffix),
                    "name": name,
                    "aliases": _aliases(code, suffix, name),
                }

    return {"supported": False, "raw": raw}


@lru_cache(maxsize=1)
def _stock_name_by_code() -> dict[str, str]:
    try:
        import akshare as ak
    except Exception:
        return {}

    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            rows = ak.stock_info_a_code_name()
    except Exception:
        return {}

    names: dict[str, str] = {}
    for row in rows.to_dict("records"):
        code = str(row.get("code", row.get("证券代码", row.get("股票代码", "")))).strip()
        name = str(row.get("name", row.get("证券简称", row.get("股票简称", "")))).strip()
        if len(code) == 6 and name:
            names[code] = name
    return names


def _decode_html(content: bytes) -> str:
    for encoding in ("utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _parse_guba_posts(html: str, limit: int) -> list[dict[str, str]]:
    selector = Selector(text=html)
    rows = selector.css("#articlelistnew .articleh, .articleh, tr")
    posts: list[dict[str, str]] = []

    for row in rows:
        title = _first(row, [".l3 a::attr(title)", ".l3 a::text", "a::attr(title)", "a::text"])
        if not title or title in {"标题", "资讯"}:
            continue

        href = _first(row, [".l3 a::attr(href)", "a::attr(href)"])
        posts.append(
            {
                "title": title,
                "url": _absolute_url(href),
                "read": _first(row, [".l1::text"]),
                "reply": _first(row, [".l2::text"]),
                "author": _first(row, [".l4 a::text", ".l4::text"]),
                "created": _first(row, [".l5::text"]),
            }
        )
        if len(posts) >= max(1, limit):
            break

    return posts


def _format_posts(identity: dict[str, object], posts: list[dict[str, str]]) -> str:
    label = _identity_label(identity)
    lines = [
        f"## 东方财富股吧社区讨论 — {label}",
        "",
        f"Total: {len(posts)} recent posts",
    ]
    for post in posts:
        meta = " · ".join(
            part
            for part in [
                post.get("created", ""),
                f"阅读 {post.get('read')}" if post.get("read") else "",
                f"评论 {post.get('reply')}" if post.get("reply") else "",
                post.get("author", ""),
            ]
            if part
        )
        lines.append(f"[{meta}] {post['title']}" if meta else post["title"])
        if post.get("url"):
            lines.append(f"Link: {post['url']}")
    return "\n".join(lines)


def _first(row, selectors: list[str]) -> str:
    for css in selectors:
        value = row.css(css).get()
        if value:
            return " ".join(value.split())
    return ""


def _absolute_url(href: str) -> str:
    if not href:
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return _BASE_URL + href
    return f"{_BASE_URL}/{href}"


def _identity_label(identity: dict[str, object]) -> str:
    ticker = str(identity.get("ticker") or identity.get("raw") or "")
    name = str(identity.get("name") or "")
    return f"{ticker}（{name}）" if name else ticker


def _aliases(code: str, suffix: str, name: str) -> list[str]:
    exchange = "SH" if suffix in {"SH", "SS"} else suffix
    aliases = [code, f"{exchange}{code}", f"{code}.{exchange}"]
    if exchange == "SH":
        aliases.append(f"{code}.SS")
    if name:
        aliases.append(name)
    return aliases


def _display_ticker(code: str, suffix: str) -> str:
    return f"{code}.SS" if suffix == "SH" else f"{code}.{suffix}"


def _infer_exchange_suffix(code: str) -> str:
    if code.startswith(("6", "9")):
        return "SH"
    if code.startswith(("4", "8")):
        return "BJ"
    return "SZ"
