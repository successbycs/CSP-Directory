"""Tests for the vendor fetcher enrichment module."""

from services.enrichment import vendor_fetcher


def test_fetch_vendor_homepage_returns_structured_payload(monkeypatch):
    # Mock requests.get
    class MockResponse:
        def __init__(self, status_code, text):
            self.status_code = status_code
            self.text = text

    def mock_get(url, timeout=None):
        return MockResponse(200, "<html><body>Hello World</body></html>")

    monkeypatch.setattr(vendor_fetcher.requests, "get", mock_get)

    vendor = {
        "vendor_name": "Gainsight",
        "website": "https://gainsight.com",
        "source": "web_search"
    }

    result = vendor_fetcher.fetch_vendor_homepage(vendor)

    expected = {
        "vendor_name": "Gainsight",
        "website": "https://gainsight.com",
        "url": "https://gainsight.com",
        "source": "web_search",
        "page_type": "homepage",
        "status_code": 200,
        "html": "<html><body>Hello World</body></html>",
        "text": "Hello World",
        "fetch_backend": "requests",
    }

    assert result == expected


def test_fetch_vendor_homepage_handles_network_error(monkeypatch):
    # Mock requests.get to raise exception; also mock fallback so no real network call
    def mock_get(url, timeout=None):
        raise vendor_fetcher.requests.RequestException("Network error")

    monkeypatch.setattr(vendor_fetcher.requests, "get", mock_get)
    monkeypatch.setattr(vendor_fetcher, "fetch_page_with_fallback", lambda url, config: None)

    vendor = {
        "vendor_name": "Gainsight",
        "website": "https://gainsight.com",
        "source": "web_search"
    }

    result = vendor_fetcher.fetch_vendor_homepage(vendor)

    expected = {
        "vendor_name": "Gainsight",
        "website": "https://gainsight.com",
        "url": "https://gainsight.com",
        "source": "web_search",
        "page_type": "homepage",
        "status_code": 0,
        "html": "",
        "text": "",
        "fetch_backend": "",
    }

    assert result == expected


def test_fetch_vendor_homepage_prefers_homepage_derived_vendor_name(monkeypatch):
    class MockResponse:
        def __init__(self, status_code, text):
            self.status_code = status_code
            self.text = text

    def mock_get(url, timeout=None):
        return MockResponse(
            200,
            (
                '<html><head><meta property="og:site_name" content="Pylon" />'
                "<title>CSM Tools: 15 Best Customer Success Platforms for 2026</title></head>"
                "<body><h1>Pylon</h1></body></html>"
            ),
        )

    monkeypatch.setattr(vendor_fetcher.requests, "get", mock_get)

    vendor = {
        "vendor_name": "CSM Tools: 15 Best Customer Success Platforms for 2026",
        "website": "https://usepylon.com",
        "source": "web_search",
    }

    result = vendor_fetcher.fetch_vendor_homepage(vendor)

    assert result["vendor_name"] == "Pylon"


def test_fetch_vendor_homepage_uses_domain_fallback_when_homepage_name_is_weak(monkeypatch):
    class MockResponse:
        def __init__(self, status_code, text):
            self.status_code = status_code
            self.text = text

    def mock_get(url, timeout=None):
        return MockResponse(
            200,
            (
                "<html><head><title>Best Customer Success Platforms 2026</title></head>"
                "<body><h1>Customer Success Platform</h1></body></html>"
            ),
        )

    monkeypatch.setattr(vendor_fetcher.requests, "get", mock_get)

    vendor = {
        "vendor_name": "Best Customer Success Platforms 2026",
        "website": "https://usepylon.com",
        "source": "web_search",
    }

    result = vendor_fetcher.fetch_vendor_homepage(vendor)

    assert result["vendor_name"] == "Usepylon"


def test_fetch_vendor_homepage_uses_domain_fallback_for_what_is_titles(monkeypatch):
    class MockResponse:
        def __init__(self, status_code, text):
            self.status_code = status_code
            self.text = text

    def mock_get(url, timeout=None):
        return MockResponse(
            200,
            (
                "<html><head><title>What is Customer Onboarding Automation?</title></head>"
                "<body><h1>Customer Onboarding Automation</h1></body></html>"
            ),
        )

    monkeypatch.setattr(vendor_fetcher.requests, "get", mock_get)

    vendor = {
        "vendor_name": "What is Customer Onboarding Automation?",
        "website": "https://onramp.us",
        "source": "web_search",
    }

    result = vendor_fetcher.fetch_vendor_homepage(vendor)

    assert result["vendor_name"] == "Onramp"


def test_fetch_vendor_homepage_skips_error_and_interstitial_pages(monkeypatch):
    class MockResponse:
        def __init__(self, status_code, text):
            self.status_code = status_code
            self.text = text

    def mock_get(_url, timeout=None):
        return MockResponse(403, "<html><title>403 Forbidden</title><body>Access denied</body></html>")

    monkeypatch.setattr(vendor_fetcher.requests, "get", mock_get)
    # Also mock fallback so no real Playwright/Apify call is made
    monkeypatch.setattr(vendor_fetcher, "fetch_page_with_fallback", lambda url, config: None)

    vendor = {
        "vendor_name": "BlockedVendor",
        "website": "https://blocked.example.com",
        "source": "web_search",
    }

    result = vendor_fetcher.fetch_vendor_homepage(vendor)

    assert result["status_code"] == 403
    assert result["html"] == ""
    assert result["text"] == ""


def test_fetch_vendor_homepage_uses_browser_fallback_when_blocked(monkeypatch):
    class MockResponse:
        def __init__(self, status_code, text):
            self.status_code = status_code
            self.text = text

    def mock_get(_url, timeout=None):
        return MockResponse(403, "<html><title>403 Forbidden</title><body>Access denied</body></html>")

    monkeypatch.setattr(vendor_fetcher.requests, "get", mock_get)
    monkeypatch.setattr(
        vendor_fetcher,
        "fetch_page_with_fallback",
        lambda url, config: {
            "status_code": 200,
            "html": "<html><head><title>Gainsight</title></head><body>Customer success platform</body></html>",
            "text": "Customer success platform",
            "fetch_backend": "playwright",
        },
    )

    vendor = {
        "vendor_name": "Gainsight",
        "website": "https://gainsight.com",
        "source": "web_search",
    }

    result = vendor_fetcher.fetch_vendor_homepage(vendor)

    assert result["status_code"] == 200
    assert result["html"].startswith("<html>")
    assert result["text"] == "Customer success platform"
    assert result["fetch_backend"] == "playwright"
