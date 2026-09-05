"""No-key, policy-aware HTML/text extraction for Mac and cloud Hermes."""
from __future__ import annotations

from html.parser import HTMLParser
import re
from typing import Any
from urllib.parse import urljoin, urlparse


MAX_REDIRECTS = 5
MAX_RESPONSE_BYTES = 2_000_000
MAX_WECHAT_RESPONSE_BYTES = 5_000_000
DEFAULT_TIMEOUT_SECONDS = 20.0
ALLOWED_CONTENT_TYPES = (
    "text/",
    "application/json",
    "application/xml",
    "application/xhtml+xml",
)
DEFAULT_USER_AGENT = (
    "AI-Lab-Hermes-Extractor/1.0 "
    "(+https://github.com/Johnie198946/ai-lab-platform)"
)
WECHAT_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
    "AppleWebKit/605.1.15 Mobile/15E148 MicroMessenger/8.0.49 "
    "NetType/WIFI Language/zh_CN"
)


class _ReadableHTML(HTMLParser):
    _SKIP = {"script", "style", "noscript", "svg", "canvas", "template"}
    _BREAK = {
        "article", "aside", "blockquote", "br", "div", "footer", "h1", "h2",
        "h3", "h4", "h5", "h6", "header", "li", "main", "nav", "p", "pre",
        "section", "table", "td", "th", "tr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_title = False
        self.title_parts: list[str] = []
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.casefold()
        if tag in self._SKIP:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if not self._skip_depth and tag in self._BREAK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag == "title":
            self._in_title = False
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        if not self._skip_depth and tag in self._BREAK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        value = re.sub(r"[ \t\f\v]+", " ", data).strip()
        if not value:
            return
        if self._in_title:
            self.title_parts.append(value)
            return
        self.parts.append(value + " ")

    def result(self) -> tuple[str, str]:
        title = " ".join(self.title_parts).strip()
        text = "".join(self.parts)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text).strip()
        return title, text


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only public http/https URLs are supported")
    from tools.url_safety import is_safe_url
    from tools.website_policy import check_website_access

    if not is_safe_url(url):
        raise ValueError("Blocked: URL targets a private or internal network address")
    blocked = check_website_access(url)
    if blocked:
        raise ValueError(str(blocked.get("message") or "Blocked by website policy"))


def _request_profile(url: str) -> tuple[dict[str, str], int]:
    """Use a browser profile only where the publisher requires it."""
    host = (urlparse(url).hostname or "").casefold()
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": (
            "text/html,text/plain,application/xhtml+xml,application/json,"
            "application/xml;q=0.9,*/*;q=0.1"
        ),
    }
    limit = MAX_RESPONSE_BYTES
    if host == "mp.weixin.qq.com":
        headers.update({
            "User-Agent": WECHAT_USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://mp.weixin.qq.com/",
        })
        # WeChat embeds large script/config payloads; readable text is much
        # smaller, but article HTML can exceed the generic 2 MB wire cap.
        limit = MAX_WECHAT_RESPONSE_BYTES
    return headers, limit


def _decode_response(response: Any, body: bytes) -> tuple[str, str]:
    content_type = str(response.headers.get("content-type") or "").casefold()
    if content_type and not any(item in content_type for item in ALLOWED_CONTENT_TYPES):
        raise ValueError(f"Unsupported content type: {content_type.split(';', 1)[0]}")
    encoding = response.encoding or "utf-8"
    text = body.decode(encoding, errors="replace")
    if "html" in content_type or "<html" in text[:1000].casefold():
        parser = _ReadableHTML()
        parser.feed(text)
        return parser.result()
    return "", re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_one(url: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Fetch one public page with validated redirects and a hard byte cap."""
    import httpx

    current = url
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        for redirect_count in range(MAX_REDIRECTS + 1):
            _validate_url(current)
            headers, response_limit = _request_profile(current)
            with client.stream("GET", current, headers=headers) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("Redirect response did not include Location")
                    if redirect_count >= MAX_REDIRECTS:
                        raise ValueError("Too many redirects")
                    current = urljoin(current, location)
                    continue
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > response_limit:
                        raise ValueError(f"Response exceeds {response_limit} byte limit")
                    chunks.append(chunk)
                body = b"".join(chunks)
                title, content = _decode_response(response, body)
                if not content:
                    raise ValueError("No readable content found")
                return {
                    "url": current,
                    "title": title,
                    "content": content,
                    "raw_content": "",
                    "metadata": {
                        "sourceURL": current,
                        "title": title,
                        "status_code": response.status_code,
                        "content_type": response.headers.get("content-type", ""),
                        "bytes": len(body),
                    },
                }
    raise ValueError("Extraction failed")


def build_provider():
    """Build against the active Hermes ABC only inside the Hermes runtime."""
    from agent.web_search_provider import WebSearchProvider

    class AILabNativeExtractProvider(WebSearchProvider):
        @property
        def name(self) -> str:
            return "ai-lab-native"

        @property
        def display_name(self) -> str:
            return "AI Lab Native Extract"

        def is_available(self) -> bool:
            return True

        def supports_search(self) -> bool:
            return False

        def supports_extract(self) -> bool:
            return True

        def extract(self, urls: list[str], **kwargs: Any) -> list[dict[str, Any]]:
            del kwargs
            results = []
            for url in urls:
                try:
                    results.append(extract_one(url))
                except Exception as exc:  # noqa: BLE001 - per-URL typed failure
                    results.append({
                        "url": url,
                        "title": "",
                        "content": "",
                        "raw_content": "",
                        "error": f"AI Lab native extract failed: {exc}",
                        "metadata": {"sourceURL": url},
                    })
            return results

    return AILabNativeExtractProvider()
