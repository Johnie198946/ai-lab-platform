"""No-key, policy-aware HTML/text/PDF extraction for Mac and cloud Hermes."""
from __future__ import annotations

from html.parser import HTMLParser
import re
import io
import json
from pathlib import Path
import subprocess
import sys
import time

# Independent PDF budgets; HTML limits and network policy remain unchanged.
MAX_PDF_RESPONSE_BYTES = 32_000_000
MAX_PDF_PAGES = 1000
MAX_PDF_TEXT_CHARS = 1_000_000
PDF_PARSE_TIMEOUT_SECONDS = 20.0
PDF_FETCH_TIMEOUT_SECONDS = 60.0
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


def _media_type(response: Any) -> str:
    return str(response.headers.get("content-type") or "").split(";", 1)[0].strip().casefold()


def _is_pdf(response: Any, prefix: bytes) -> bool:
    media_type = _media_type(response)
    magic = prefix.startswith(b"%PDF-")
    if media_type == "application/pdf":
        if not magic:
            raise ValueError("Invalid PDF: application/pdf without PDF signature")
        return True
    if magic:
        if media_type in {"", "application/octet-stream"}:
            return True
        raise ValueError("PDF signature conflicts with declared content type")
    return False


def _pdf_document(body: bytes, page_limit: int, char_limit: int) -> dict[str, Any]:
    # Library only: no network, OCR, external executable or active PDF content.
    try:
        import pypdf
    except ImportError:
        sys.path.append(str(Path(__file__).resolve().parent / "_pdf_dependencies"))
        try:
            import pypdf
        except ImportError as exc:
            raise ValueError("PDF dependency missing: install requirements-pdf.txt") from exc
    if len(body) > MAX_PDF_RESPONSE_BYTES:
        raise ValueError("PDF byte limit exceeded")
    try:
        reader = pypdf.PdfReader(io.BytesIO(body), strict=True)
        if reader.is_encrypted:
            raise ValueError("Encrypted PDF is not supported")
        total = len(reader.pages)
        parts, empty_pages, reasons = [], [], []
        remaining = char_limit
        extracted = 0
        if total > page_limit:
            reasons.append("page_limit")
        for index in range(min(total, page_limit)):
            text = (reader.pages[index].extract_text() or "").strip()
            extracted += 1
            if not text:
                empty_pages.append(index + 1)
            if len(text) > remaining:
                text = text[:remaining]
                reasons.append("text_limit")
            parts.append(f"[Page {index + 1}]\n{text or '[No text layer; OCR may be required]'}")
            remaining -= len(text)
            if "text_limit" in reasons or (remaining == 0 and index + 1 < total):
                if "text_limit" not in reasons:
                    reasons.append("text_limit")
                break
        if not parts or len(empty_pages) == extracted:
            raise ValueError("PDF has no readable text layer; OCR is required but unavailable")
        content = "\n\n".join(parts)
        if reasons:
            content += "\n\n[PDF truncated: " + ", ".join(reasons) + "]"
        return {"title": str((reader.metadata or {}).get("/Title", ""))[:2000],
                "content": content, "pdf": {"parser": "pypdf", "parser_version": pypdf.__version__,
                "page_count": total, "pages_extracted": extracted, "empty_text_pages": empty_pages,
                "truncated": bool(reasons), "truncation_reasons": reasons,
                "page_limit": page_limit, "text_char_limit": char_limit}}
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Invalid or unsupported PDF ({type(exc).__name__})") from exc


def _parse_pdf(body: bytes) -> dict[str, Any]:
    if len(body) > MAX_PDF_RESPONSE_BYTES:
        raise ValueError("PDF byte limit exceeded")
    # A killable child is needed: a thread deadline cannot stop a stuck parser.
    # Fixed Python/file argv, no shell and no URL passed to this offline worker.
    try:
        completed = subprocess.run(
            [sys.executable, "-I", str(Path(__file__).resolve()), "--pdf-worker",
             str(MAX_PDF_PAGES), str(MAX_PDF_TEXT_CHARS)], input=body,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=PDF_PARSE_TIMEOUT_SECONDS, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("PDF parsing time budget exceeded") from exc
    if completed.returncode:
        raise ValueError("PDF parser failed or exceeded resource budget")
    result = json.loads(completed.stdout)
    if result.get("error"):
        raise ValueError(result["error"])
    return result


def _decode_response(response: Any, body: bytes) -> tuple[str, str]:
    if _is_pdf(response, body[:5]):
        result = _parse_pdf(body)
        return result["title"], result["content"]
    content_type = _media_type(response)
    if content_type and not (content_type.startswith("text/") or content_type in ALLOWED_CONTENT_TYPES[1:]):
        raise ValueError(f"Unsupported content type: {content_type}")
    if b"\x00" in body:
        raise ValueError("Binary response is not readable text")
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
                prefix = b""
                pdf = False
                started = time.monotonic()
                for chunk in response.iter_bytes():
                    prefix = (prefix + chunk)[:5]
                    if len(prefix) >= 5:
                        pdf = _is_pdf(response, prefix)
                    limit = MAX_PDF_RESPONSE_BYTES if pdf else response_limit
                    size += len(chunk)
                    if size > limit:
                        raise ValueError(f"Response exceeds {limit} byte limit")
                    if pdf and time.monotonic() - started > PDF_FETCH_TIMEOUT_SECONDS:
                        raise ValueError("PDF download time budget exceeded")
                    chunks.append(chunk)
                body = b"".join(chunks)
                pdf = _is_pdf(response, body[:5])
                pdf_metadata = {}
                if pdf:
                    if response.status_code >= 400:
                        raise ValueError(f"PDF HTTP error: {response.status_code}")
                    document = _parse_pdf(body)
                    title = document["title"]
                    content = f"Source: {current}\n\n" + document["content"]
                    pdf_metadata = document["pdf"]
                else:
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
                        "requestedURL": url,
                        **({"pdf": pdf_metadata} if pdf else {}),
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


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] != "--pdf-worker":
        raise SystemExit("Offline PDF parser worker only")
    try:
        import resource
        budgets = [(resource.RLIMIT_CPU, 20)]
        # Darwin rejects RLIMIT_DATA/AS changes even when reported unlimited.
        # There the byte/page/text caps and killable wall/CPU deadline apply.
        if sys.platform != "darwin":
            budgets.append((resource.RLIMIT_DATA, 512 * 1024 * 1024))
        for kind, budget in budgets:
            soft, hard = resource.getrlimit(kind)
            finite = [v for v in (soft, hard, budget) if v != resource.RLIM_INFINITY]
            limit = min(finite)
            resource.setrlimit(kind, (limit, limit))
        result = _pdf_document(sys.stdin.buffer.read(MAX_PDF_RESPONSE_BYTES + 1),
                               min(MAX_PDF_PAGES, max(1, int(sys.argv[2]))),
                               min(MAX_PDF_TEXT_CHARS, max(1, int(sys.argv[3]))))
    except Exception as exc:
        result = {"error": str(exc) or type(exc).__name__}
    sys.stdout.write(json.dumps(result, ensure_ascii=True))
