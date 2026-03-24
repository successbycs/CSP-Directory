"""Tests for blocked-site discovery mode helpers."""

from services.config.load_config import load_pipeline_config
from services.enrichment import discovery_mode


class MockResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text


def _config():
    return load_pipeline_config().enrichment


def test_discover_vendor_links_extracts_same_site_urls_from_script_payload():
    homepage_payload = {
        "website": "https://gainsight.com",
        "status_code": 200,
        "html": (
            '<html><body><script>'
            'window.__NEXT_DATA__={"links":["/staircase-ai","https://docs.gainsight.com/api","/privacy"]};'
            "</script></body></html>"
        ),
    }

    result = discovery_mode.discover_vendor_links(homepage_payload, _config())

    assert ("https://gainsight.com/staircase-ai", "staircase ai") in result
    assert ("https://docs.gainsight.com/api", "api") in result


def test_discover_vendor_links_reads_sitemap_when_homepage_is_blocked(monkeypatch):
    homepage_payload = {
        "website": "https://gainsight.com",
        "status_code": 403,
        "html": "",
    }

    def mock_get(url: str, timeout: int = 10):
        if url == "https://gainsight.com/sitemap.xml":
            return MockResponse(
                200,
                (
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    "<urlset>"
                    "<url><loc>https://gainsight.com/staircase-ai</loc></url>"
                    "<url><loc>https://gainsight.com/customers</loc></url>"
                    "<url><loc>https://gainsight.com/privacy</loc></url>"
                    "</urlset>"
                ),
            )
        return MockResponse(404, "not found")

    monkeypatch.setattr(discovery_mode.requests, "get", mock_get)

    result = discovery_mode.discover_vendor_links(homepage_payload, _config())

    assert ("https://gainsight.com/staircase-ai", "staircase ai") in result
    assert ("https://gainsight.com/customers", "customers") in result


def test_discover_vendor_links_follows_sitemap_index(monkeypatch):
    homepage_payload = {
        "website": "https://gainsight.com",
        "status_code": 403,
        "html": "",
    }

    def mock_get(url: str, timeout: int = 10):
        if url == "https://gainsight.com/sitemap.xml":
            return MockResponse(301, "")
        if url == "https://gainsight.com/sitemap_index.xml":
            return MockResponse(
                200,
                (
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    "<sitemapindex>"
                    "<sitemap><loc>https://gainsight.com/page-sitemap.xml</loc></sitemap>"
                    "</sitemapindex>"
                ),
            )
        if url == "https://gainsight.com/page-sitemap.xml":
            return MockResponse(
                200,
                (
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    "<urlset>"
                    "<url><loc>https://gainsight.com/staircase-ai</loc></url>"
                    "<url><loc>https://gainsight.com/customer-success</loc></url>"
                    "</urlset>"
                ),
            )
        return MockResponse(404, "not found")

    monkeypatch.setattr(discovery_mode.requests, "get", mock_get)

    result = discovery_mode.discover_vendor_links(homepage_payload, _config())

    assert ("https://gainsight.com/staircase-ai", "staircase ai") in result
    assert ("https://gainsight.com/customer-success", "customer success") in result


def test_discover_vendor_links_uses_browser_when_sparse(monkeypatch):
    homepage_payload = {
        "website": "https://gainsight.com",
        "status_code": 200,
        "html": "<html><body><a href=\"/pricing\">Pricing</a></body></html>",
    }

    monkeypatch.setattr(
        discovery_mode,
        "fetch_page_with_browser",
        lambda url, config: {
            "status_code": 200,
            "html": (
                '<html><body>'
                '<a href="/staircase-ai">Staircase AI</a>'
                '<a href="/customer-success">Customer Success</a>'
                "</body></html>"
            ),
            "text": "Staircase AI Customer Success",
        },
    )

    result = discovery_mode.discover_vendor_links(homepage_payload, _config())

    assert ("https://gainsight.com/staircase-ai", "Staircase AI") in result
    assert ("https://gainsight.com/customer-success", "Customer Success") in result
