"""Synthetic HTML fixtures for conservative main-content cleaning."""
import importlib.util
from pathlib import Path

import httpx
import pytest


SOURCE = Path(__file__).resolve().parents[1] / "agency/hermes-plugins/ai-lab-capabilities/native_extract_provider.py"


@pytest.fixture
def provider():
    spec = importlib.util.spec_from_file_location("html_provider_test", SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def response():
    return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"})


def test_article_noise_is_removed_and_body_is_preserved(provider):
    paragraphs = "".join(
        f"<p>Evidence paragraph {index} explains the verified finding with enough detail for research.</p>"
        for index in range(12)
    )
    html = (
        "<html><head><title>Verified report</title></head><body>"
        "<header>Campaign banner</header><nav>Home Pricing Subscribe</nav>"
        f"<main><article><h1>Verified finding</h1>{paragraphs}</article></main>"
        "<aside>Sponsored offer</aside><footer>Marketing footer</footer>"
        "</body></html>"
    ).encode()
    title, content = provider._decode_response(
        response(), html, url="https://example.org/report"
    )
    assert title == "Verified report"
    assert "Verified finding" in content and "Evidence paragraph 11" in content
    assert "Campaign banner" not in content
    assert "Sponsored offer" not in content
    assert "Marketing footer" not in content


@pytest.mark.parametrize(
    "marker,critical",
    [
        ('<script type="application/ld+json">{"@type":"Product"}</script>', "Price: $199"),
        ("<table><tr><th>Metric</th><td>42</td></tr></table>", "Metric\n42"),
        ('<div class="discussion-thread">Reply from reviewer</div>', "Reply from reviewer"),
    ],
)
def test_high_recall_pages_keep_short_critical_fields(provider, marker, critical):
    html = (
        "<html><head><title>Structured page</title></head><body><main>"
        + marker
        + "<p>" + critical.replace("\n", " ") + "</p>"
        + "<p>Long descriptive copy. </p>" * 30
        + "</main></body></html>"
    ).encode()
    _, content = provider._decode_response(response(), html)
    for fragment in critical.splitlines():
        assert fragment in content


def test_missing_or_failed_cleaner_falls_back(provider, monkeypatch):
    html = (
        "<html><head><title>Fallback</title></head><body><nav>Navigation kept by fallback</nav>"
        "<main><p>Readable evidence. </p>" + "<p>More evidence. </p>" * 30 + "</main></body></html>"
    ).encode()
    monkeypatch.setattr(provider, "_load_trafilatura", lambda: None)
    title, content = provider._decode_response(response(), html)
    assert title == "Fallback"
    assert "Navigation kept by fallback" in content
    assert "Readable evidence" in content


def test_role_main_is_treated_as_an_article_candidate(provider):
    html = (
        "<html><head><title>Documentation</title></head><body>"
        "<nav>Docs navigation pricing login</nav>"
        '<div role="main"><h1>Documentation</h1>'
        + "<p>Body paragraph explains the documented behavior. </p>" * 20
        + "</div><footer>Legal cookie settings</footer></body></html>"
    ).encode()

    _, content = provider._decode_response(response(), html, url="https://example.com/docs")

    assert "Body paragraph explains" in content
    assert "Docs navigation pricing login" not in content
    assert "Legal cookie settings" not in content
