"""Synthetic real PDFs only; transport is in-memory, never public network."""
import importlib.util
import io
from pathlib import Path
import sys
import types

import httpx
import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

SOURCE = Path(__file__).resolve().parents[1] / "agency/hermes-plugins/ai-lab-capabilities/native_extract_provider.py"


@pytest.fixture
def provider():
    spec = importlib.util.spec_from_file_location("pdf_provider_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pdf_bytes(texts=("Synthetic evidence page one", "Synthetic evidence page two"), encrypted=False, padding=0):
    writer = PdfWriter()
    writer.add_metadata({"/Title": "Synthetic PDF fixture", "/SyntheticPadding": "x" * padding})
    for text in texts:
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                 NameObject("/Subtype"): NameObject("/Type1"),
                                 NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("synthetic-password")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def transport(monkeypatch, handler):
    client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: client(transport=httpx.MockTransport(handler), **kw))


def gates(monkeypatch, *, safe=lambda url: True, blocked=lambda url: None):
    # Exercise the unchanged _validate_url imports, not a replacement guard.
    monkeypatch.setitem(sys.modules, "tools.url_safety", types.SimpleNamespace(is_safe_url=safe))
    monkeypatch.setitem(sys.modules, "tools.website_policy", types.SimpleNamespace(check_website_access=blocked))


@pytest.mark.parametrize("media", ["application/pdf", "Application/PDF; version=1.7", "application/octet-stream", ""])
def test_real_pdf_transport_and_page_locations(provider, monkeypatch, media):
    body = pdf_bytes()
    gates(monkeypatch)
    transport(monkeypatch, lambda req: httpx.Response(200, headers={"content-type": media}, content=body))
    result = provider.extract_one("https://example.org/source.pdf")
    assert "[Page 1]\nSynthetic evidence page one" in result["content"]
    assert "[Page 2]\nSynthetic evidence page two" in result["content"]
    assert result["content"].startswith("Source: https://example.org/source.pdf")
    assert result["title"] == "Synthetic PDF fixture"
    assert result["metadata"]["pdf"]["page_count"] == 2
    assert result["metadata"]["pdf"]["truncated"] is False


@pytest.mark.parametrize("media,body,error", [
    ("application/pdf", b"<html>challenge</html>", "signature"),
    ("text/plain", pdf_bytes(), "conflicts"),
    ("application/evil;text/html", b"not text", "Unsupported"),
    ("application/pdf-evil", pdf_bytes(), "conflicts"),
    ("application/octet-stream", b"\x00binary", "Unsupported"),
    ("", b"\x00binary", "Binary"),
    ("application/pdf", b"%PDF-1.7\ninvalid", "Invalid"),
    ("application/pdf", pdf_bytes(encrypted=True), "Encrypted"),
    ("application/pdf", pdf_bytes(("",)), "OCR"),
])
def test_reject_invalid_binary_encrypted_and_ocr(provider, media, body, error):
    response = httpx.Response(200, headers={"content-type": media})
    with pytest.raises(ValueError, match=error):
        provider._decode_response(response, body)


def test_page_and_text_truncation_real_worker(provider, monkeypatch):
    monkeypatch.setattr(provider, "MAX_PDF_PAGES", 1)
    result = provider._parse_pdf(pdf_bytes())
    assert result["pdf"]["pages_extracted"] == 1
    assert result["pdf"]["truncation_reasons"] == ["page_limit"]
    assert "PDF truncated: page_limit" in result["content"]
    monkeypatch.setattr(provider, "MAX_PDF_PAGES", 1000)
    monkeypatch.setattr(provider, "MAX_PDF_TEXT_CHARS", 5)
    result = provider._parse_pdf(pdf_bytes())
    assert result["pdf"]["truncation_reasons"] == ["text_limit"]
    assert "[Page 1]\nSynth" in result["content"]


def test_mixed_empty_pages(provider):
    result = provider._parse_pdf(pdf_bytes(("", "Text layer exists")))
    assert result["pdf"]["empty_text_pages"] == [1]
    assert "OCR may be required" in result["content"]


def test_timeout_kills_real_worker(provider, monkeypatch):
    monkeypatch.setattr(provider, "PDF_PARSE_TIMEOUT_SECONDS", 0.000001)
    with pytest.raises(ValueError, match="time budget"):
        provider._parse_pdf(pdf_bytes())


@pytest.mark.parametrize("media,is_pdf", [("application/pdf", True), ("text/plain", False)])
def test_separate_stream_byte_caps(provider, monkeypatch, media, is_pdf):
    gates(monkeypatch)
    body = pdf_bytes() if is_pdf else b"x" * 500
    monkeypatch.setattr(provider, "MAX_RESPONSE_BYTES", 100)
    monkeypatch.setattr(provider, "MAX_PDF_RESPONSE_BYTES", len(body) - 1)
    transport(monkeypatch, lambda req: httpx.Response(200, headers={"content-type": media}, content=body))
    with pytest.raises(ValueError, match="byte limit"):
        provider.extract_one("https://example.org/file")


def test_pdf_larger_than_html_cap(provider, monkeypatch):
    gates(monkeypatch)
    monkeypatch.setattr(provider, "MAX_RESPONSE_BYTES", 100)
    body = pdf_bytes()
    transport(monkeypatch, lambda req: httpx.Response(200, headers={"content-type": "application/pdf"}, content=body))
    assert provider.extract_one("https://example.org/file")["metadata"]["pdf"]["page_count"] == 2


@pytest.mark.parametrize("target,policy", [("http://127.0.0.1/private.pdf", False), ("https://blocked.example/file.pdf", True)])
def test_redirect_gates_before_second_request(provider, monkeypatch, target, policy):
    seen = []
    gates(monkeypatch, safe=lambda u: "127.0.0.1" not in u,
          blocked=lambda u: {"message": "Blocked by website policy"} if policy and u == target else None)
    def handler(req):
        seen.append(str(req.url))
        return httpx.Response(302, headers={"location": target})
    transport(monkeypatch, handler)
    with pytest.raises(ValueError, match="Blocked"):
        provider.extract_one("https://example.org/start")
    assert seen == ["https://example.org/start"]


def test_redirect_source_metadata(provider, monkeypatch):
    gates(monkeypatch)
    def handler(req):
        if req.url.path == "/start":
            return httpx.Response(302, headers={"location": "/final.pdf"})
        return httpx.Response(200, headers={"content-type": "application/pdf"}, content=pdf_bytes())
    transport(monkeypatch, handler)
    result = provider.extract_one("https://example.org/start")
    assert result["metadata"]["sourceURL"] == "https://example.org/final.pdf"
    assert result["metadata"]["requestedURL"] == "https://example.org/start"


def test_redirect_limit(provider, monkeypatch):
    gates(monkeypatch)
    seen = []
    def handler(req):
        seen.append(req)
        return httpx.Response(302, headers={"location": "/again"})
    transport(monkeypatch, handler)
    with pytest.raises(ValueError, match="Too many redirects"):
        provider.extract_one("https://example.org/start")
    assert len(seen) == provider.MAX_REDIRECTS + 1


def test_pdf_fetch_deadline(provider, monkeypatch):
    gates(monkeypatch)
    ticks = iter([0, 61])
    monkeypatch.setattr(provider.time, "monotonic", lambda: next(ticks))
    transport(monkeypatch, lambda req: httpx.Response(200, headers={"content-type": "application/pdf"}, content=pdf_bytes()))
    with pytest.raises(ValueError, match="download time budget"):
        provider.extract_one("https://example.org/file")


def test_actual_default_budgets(provider, monkeypatch):
    gates(monkeypatch)
    body = pdf_bytes(padding=provider.MAX_RESPONSE_BYTES)
    assert len(body) > provider.MAX_RESPONSE_BYTES
    transport(monkeypatch, lambda req: httpx.Response(200, headers={"content-type": "application/pdf"}, content=body))
    assert provider.extract_one("https://example.org/large.pdf")["metadata"]["pdf"]["page_count"] == 2
    with pytest.raises(ValueError, match="byte limit"):
        provider._parse_pdf(b"%PDF-" + b"x" * provider.MAX_PDF_RESPONSE_BYTES)


def test_fragmented_pdf_signature(provider, monkeypatch):
    gates(monkeypatch)
    body = pdf_bytes()
    class Fragmented(httpx.SyncByteStream):
        def __iter__(self):
            yield from (body[:1], body[1:3], body[3:5], body[5:])
    transport(monkeypatch, lambda req: httpx.Response(200, headers={"content-type": "application/octet-stream"}, stream=Fragmented()))
    assert provider.extract_one("https://example.org/file")["metadata"]["pdf"]["page_count"] == 2


@pytest.mark.parametrize("url", ["http://127.0.0.1/file.pdf", "file:///tmp/file.pdf"])
def test_initial_ssrf_and_scheme(provider, monkeypatch, url):
    gates(monkeypatch, safe=lambda u: False)
    transport(monkeypatch, lambda req: pytest.fail("No request allowed"))
    with pytest.raises(ValueError, match="Blocked|Only public"):
        provider.extract_one(url)


def test_html_suffix_does_not_grant_pdf_budget(provider, monkeypatch):
    gates(monkeypatch)
    body = b"<html><title>Challenge</title><p>Access denied</p></html>"
    transport(monkeypatch, lambda req: httpx.Response(200, headers={"content-type": "text/html"}, content=body))
    result = provider.extract_one("https://example.org/not-a-pdf.pdf")
    assert "pdf" not in result["metadata"]
    assert result["title"] == "Challenge"


@pytest.mark.parametrize("status", [403, 429, 503, 304])
def test_http_error_html_rejected_before_body(provider, monkeypatch, status):
    gates(monkeypatch)
    class Unreadable(httpx.SyncByteStream):
        def __iter__(self):
            pytest.fail("HTTP error body must not be read or cached as evidence")
            yield b""
    transport(monkeypatch, lambda req: httpx.Response(status, headers={"content-type": "text/html"}, stream=Unreadable()))
    with pytest.raises(ValueError, match=f"HTTP error: {status}"):
        provider.extract_one("https://example.org/error")


def test_shared_concurrency_order_and_failure_isolation(provider, monkeypatch):
    import concurrent.futures
    import threading
    import time
    monkeypatch.setitem(sys.modules, "agent.web_search_provider", types.SimpleNamespace(WebSearchProvider=object))
    gates(monkeypatch)
    lock, release = threading.Lock(), threading.Event()
    active = peak = 0
    reached = threading.Event()
    def handler(req):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            if active == provider.MAX_CONCURRENT_EXTRACTS:
                reached.set()
        try:
            assert release.wait(5), "batch did not execute concurrently"
            time.sleep(0.005 * (3 - int(req.url.path.strip("/")) % 4))
            status = 503 if req.url.path == "/2" else 200
            return httpx.Response(status, headers={"content-type": "text/plain"}, text=str(req.url))
        finally:
            with lock:
                active -= 1
    transport(monkeypatch, handler)
    batches = [[f"https://example.org/{i}" for i in range(start, start + 6)] for start in (0, 6)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        pending = [pool.submit(provider.build_provider().extract, urls) for urls in batches]
        direct = pool.submit(provider.extract_one, "https://example.org/12")
        try:
            assert reached.wait(5), "serial regression: four requests never overlapped"
            assert peak == provider.MAX_CONCURRENT_EXTRACTS
        finally:
            release.set()
        results = [f.result(timeout=10) for f in pending]
        assert direct.result(timeout=10)["content"].endswith("/12")
    assert peak == provider.MAX_CONCURRENT_EXTRACTS
    for urls, rows in zip(batches, results):
        assert [row["url"] for row in rows] == urls
    assert "HTTP error: 503" in results[0][2]["error"]
    assert results[0][2]["content"] == ""
    assert all(row["content"] for row in results[1])


def test_shared_pdf_worker_limit_and_slot_release(provider, monkeypatch):
    import concurrent.futures
    import threading
    import time
    lock = threading.Lock()
    active = peak = calls = 0
    def worker(*args, **kwargs):
        nonlocal active, peak, calls
        with lock:
            active += 1
            calls += 1
            peak = max(peak, active)
        try:
            time.sleep(0.02)
            if kwargs["input"] == b"bad":
                raise provider.subprocess.TimeoutExpired("fixture", 1)
            return types.SimpleNamespace(returncode=0, stdout=b'{"content":"synthetic"}')
        finally:
            with lock:
                active -= 1
    monkeypatch.setattr(provider.subprocess, "run", worker)
    def run(body):
        try:
            return provider._parse_pdf(body)
        except ValueError as exc:
            return str(exc)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(run, [b"bad"] + [b"pdf"] * 7))
    assert calls == 8 and peak == 1
    assert "time budget" in rows[0]
    assert all(row == {"content": "synthetic"} for row in rows[1:])


def test_http_error_pdf_not_evidence(provider, monkeypatch):
    gates(monkeypatch)
    transport(monkeypatch, lambda req: httpx.Response(403, headers={"content-type": "application/pdf"}, content=pdf_bytes()))
    with pytest.raises(ValueError, match="HTTP error: 403"):
        provider.extract_one("https://example.org/file")
