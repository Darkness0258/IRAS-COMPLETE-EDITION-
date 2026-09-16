from __future__ import annotations

from html.parser import HTMLParser
import ipaddress
import re
import socket
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse
import webbrowser

import httpx

from iras.models import PermissionLevel
from iras.tools.base import Tool


class _ReadableHTML(HTMLParser):
    """Small dependency-free HTML-to-text extractor for research tools."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        name = str(tag or "").lower()
        if name in {"script", "style", "noscript", "svg"}:
            self._skip += 1
            return
        if not self._skip and name in {
            "p", "div", "section", "article", "main", "header", "footer",
            "h1", "h2", "h3", "h4", "h5", "h6", "li", "br", "tr",
            "blockquote", "pre", "dt", "dd",
        }:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        name = str(tag or "").lower()
        if name in {"script", "style", "noscript", "svg"} and self._skip:
            self._skip -= 1
            return
        if not self._skip and name in {
            "p", "div", "section", "article", "main", "h1", "h2", "h3",
            "h4", "h5", "h6", "li", "tr", "blockquote", "pre", "dt", "dd",
        }:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip and data:
            self.parts.append(str(data))


def html_to_text(raw: str, max_chars: int = 30000) -> str:
    parser = _ReadableHTML()
    try:
        parser.feed(str(raw or ""))
        parser.close()
        text = "".join(parser.parts)
    except Exception:
        text = str(raw or "")
    lines = []
    for line in text.splitlines():
        cleaned = re.sub(r"[ \t\r\f\v]+", " ", line).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)[: max(1, min(int(max_chars), 100000))]


def _validate_public(url):
    u = urlparse(url)
    if u.scheme not in {"http", "https"} or not u.hostname:
        raise ValueError("Only http/https URLs are allowed.")
    if u.username is not None or u.password is not None:
        raise ValueError("Credentials embedded in URLs are not allowed.")
    if len(str(url)) > 4096:
        raise ValueError("URL exceeds the 4096-character safety limit.")
    for info in socket.getaddrinfo(
        u.hostname,
        u.port or (443 if u.scheme == "https" else 80),
        type=socket.SOCK_STREAM,
    ):
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise PermissionError("Private/local network destinations are blocked by http_get.")


def _bounded_response_bytes(response, *, max_bytes: int = 2_000_000) -> bytes:
    max_bytes = max(1024, min(int(max_bytes), 5_000_000))
    declared = response.headers.get("content-length")
    if declared:
        try:
            if int(declared) > max_bytes:
                raise ValueError(f"HTTP response exceeds the {max_bytes:,}-byte safety limit.")
        except ValueError as exc:
            if "safety limit" in str(exc):
                raise
    chunks = []
    total = 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > max_bytes:
            raise ValueError(f"HTTP response exceeds the {max_bytes:,}-byte safety limit.")
        chunks.append(chunk)
    return b"".join(chunks)


def _decode_response(response, raw: bytes) -> str:
    encoding = response.encoding or "utf-8"
    try:
        return raw.decode(encoding, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _is_textual_content_type(content_type: str) -> bool:
    value = str(content_type or "").lower().split(";", 1)[0].strip()
    if not value:
        return True
    return (
        value.startswith("text/")
        or value in {
            "application/json", "application/ld+json", "application/xml",
            "application/xhtml+xml", "application/javascript", "application/x-javascript",
            "application/x-www-form-urlencoded",
        }
        or value.endswith("+json")
        or value.endswith("+xml")
    )


def http_get(url, max_chars=30000):
    max_chars = max(1, min(int(max_chars), 100000))
    current = str(url)
    with httpx.Client(
        timeout=httpx.Timeout(30.0, connect=10.0),
        follow_redirects=False,
        headers={"User-Agent": "IRAS/4.3 (+https://github.com/Darkness0258/IRAS-COMPLETE-EDITION-)"},
    ) as client:
        response = None
        raw = b""
        for _ in range(6):
            _validate_public(current)
            with client.stream("GET", current) as streamed:
                if streamed.status_code in {301, 302, 303, 307, 308}:
                    location = str(streamed.headers.get("location") or "").strip()
                    if not location:
                        response = streamed
                        raw = _bounded_response_bytes(streamed)
                        break
                    current = urljoin(current, location)
                    continue
                response = streamed
                raw = _bounded_response_bytes(streamed)
                break
        else:
            raise RuntimeError("Too many HTTP redirects.")
    if response is None:
        raise RuntimeError("HTTP request did not produce a response.")
    content_type = str(response.headers.get("content-type") or "")
    if not _is_textual_content_type(content_type):
        raise ValueError(f"http_get only accepts text/JSON/XML responses, not {content_type or 'binary data'!r}.")
    text_raw = _decode_response(response, raw)
    text = html_to_text(text_raw, max_chars=max_chars) if "html" in content_type.lower() else text_raw[:max_chars]
    return {
        "status": response.status_code,
        "content_type": content_type,
        "url": str(response.url),
        "text": text,
        "truncated": len(text_raw) > max_chars,
        "bytes": len(raw),
    }


class _DuckResults(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._current_href = ""
        self._current_text: list[str] = []
        self._capture = False

    def handle_starttag(self, tag, attrs):
        if str(tag).lower() != "a":
            return
        data = {str(k): str(v or "") for k, v in attrs}
        classes = set(data.get("class", "").split())
        if "result__a" not in classes:
            return
        self._current_href = data.get("href", "")
        self._current_text = []
        self._capture = True

    def handle_data(self, data):
        if self._capture:
            self._current_text.append(str(data))

    def handle_endtag(self, tag):
        if str(tag).lower() != "a" or not self._capture:
            return
        title = " ".join("".join(self._current_text).split())
        href = _normalize_search_href(self._current_href)
        if title and href.startswith(("http://", "https://")):
            self.results.append({"title": title, "url": href})
        self._current_href = ""
        self._current_text = []
        self._capture = False


def _normalize_search_href(href: str) -> str:
    raw = str(href or "").strip()
    if raw.startswith("//"):
        raw = "https:" + raw
    try:
        parsed = urlparse(raw)
        if parsed.hostname and parsed.hostname.endswith("duckduckgo.com"):
            target = parse_qs(parsed.query).get("uddg", [""])[0]
            if target:
                return unquote(target)
    except Exception:
        pass
    return raw


def _parse_duck_results(raw: str, limit: int) -> list[dict[str, str]]:
    parser = _DuckResults()
    parser.feed(str(raw or ""))
    parser.close()
    unique: list[dict[str, str]] = []
    seen = set()
    for item in parser.results:
        url = item["url"]
        if url in seen:
            continue
        seen.add(url)
        unique.append(item)
        if len(unique) >= limit:
            break
    return unique


def web_search(query, max_results=6):
    """Search the public web without opening a browser UI."""
    query = " ".join(str(query or "").split())
    if not query:
        raise ValueError("Search query is required.")
    max_results = max(1, min(int(max_results), 10))
    endpoint = "https://html.duckduckgo.com/html/?q=" + quote_plus(query)
    with httpx.Client(
        timeout=30,
        follow_redirects=True,
        max_redirects=5,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/131 Safari/537.36"
            )
        },
    ) as client:
        response = client.get(endpoint)
    results = _parse_duck_results(response.text, max_results)
    return {
        "query": query,
        "status": response.status_code,
        "results": results,
        "result_count": len(results),
    }


def open_url(url):
    parsed = urlparse(str(url))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only http/https URLs are allowed.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Credentials embedded in URLs are not allowed.")
    if len(str(url)) > 4096:
        raise ValueError("URL exceeds the 4096-character safety limit.")
    return {"opened": bool(webbrowser.open(url)), "url": str(url)}


TOOLS = [
    Tool(
        "web_search",
        "Search the PUBLIC web and return result titles plus URLs without opening a browser window.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["query"],
        },
        web_search,
        PermissionLevel.READ,
    ),
    Tool(
        "http_get",
        "Fetch readable text from a PUBLIC internet URL. HTML is converted to article-like text; private/local IPs are blocked.",
        {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "max_chars": {"type": "integer"},
            },
            "required": ["url"],
        },
        http_get,
        PermissionLevel.READ,
    ),
    Tool(
        "open_url",
        "Open an http/https URL in the user default browser.",
        {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
        open_url,
        PermissionLevel.SAFE_ACTION,
    ),
]
