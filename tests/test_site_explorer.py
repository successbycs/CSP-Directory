"""Tests for vendor site exploration."""

from services.enrichment import site_explorer


class MockResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text


def test_explore_vendor_site_discovers_high_value_pages_and_extra_pages(monkeypatch):
    homepage_payload = {
        "vendor_name": "ExampleCorp",
        "website": "https://example.com",
        "source": "google_search",
        "page_type": "homepage",
        "status_code": 200,
        "html": (
            '<html><body>'
            '<a href="/pricing">Pricing</a>'
            '<a href="/platform">Platform</a>'
            '<a href="/customers">Customers</a>'
            '<a href="/security">Security</a>'
            '<a href="/about">About</a>'
            '<a href="/team">Team</a>'
            '<a href="/contact">Contact</a>'
            '<a href="/demo">Book Demo</a>'
            '<a href="/help">Help Center</a>'
            '<a href="/integrations">Integrations</a>'
            '<a href="/ai-copilot">AI Copilot</a>'
            '<a href="https://reddit.com/r/customersuccess">Reddit</a>'
            "</body></html>"
        ),
        "text": "Homepage text",
    }

    def mock_get(url: str, timeout: int = 10):
        responses = {
            "https://example.com/pricing": MockResponse(200, "<html><body>$99 per user per month</body></html>"),
            "https://example.com/platform": MockResponse(200, "<html><body>Customer success platform</body></html>"),
            "https://example.com/customers": MockResponse(200, "<html><body>Customer stories</body></html>"),
            "https://example.com/security": MockResponse(200, "<html><body>SOC2 and trust center</body></html>"),
            "https://example.com/about": MockResponse(200, "<html><body>About ExampleCorp</body></html>"),
            "https://example.com/team": MockResponse(200, "<html><body>Leadership team</body></html>"),
            "https://example.com/contact": MockResponse(200, "<html><body>Contact us</body></html>"),
            "https://example.com/demo": MockResponse(200, "<html><body>Book a demo</body></html>"),
            "https://example.com/help": MockResponse(200, "<html><body>Help center</body></html>"),
            "https://example.com/integrations": MockResponse(200, "<html><body>Integrations with Salesforce</body></html>"),
        }
        return responses[url]

    monkeypatch.setattr(site_explorer.requests, "get", mock_get)

    result = site_explorer.explore_vendor_site(homepage_payload)

    assert list(result) == [
        "homepage",
        "extra_pages",
        "pricing_page",
        "product_page",
        "case_studies_page",
        "security_page",
        "about_page",
        "team_page",
        "contact_page",
        "demo_page",
        "help_page",
        "integrations_page",
    ]
    assert result["pricing_page"]["website"] == "https://example.com/pricing"
    assert result["product_page"]["text"] == "Customer success platform"
    assert result["team_page"]["website"] == "https://example.com/team"
    assert result["contact_page"]["website"] == "https://example.com/contact"
    assert result["demo_page"]["website"] == "https://example.com/demo"
    assert result["help_page"]["website"] == "https://example.com/help"
    assert result["integrations_page"]["url"] == "https://example.com/integrations"
    assert result["extra_pages"] == []


def test_explore_vendor_site_filters_external_and_junk_links_and_keeps_best_priority(monkeypatch):
    homepage_payload = {
        "vendor_name": "ExampleCorp",
        "website": "https://example.com",
        "source": "google_search",
        "page_type": "homepage",
        "status_code": 200,
        "html": (
            '<html><body>'
            '<a href="/docs">Docs</a>'
            '<a href="/privacy">Privacy</a>'
            '<a href="/plans">Pricing</a>'
            '<a href="/features">Features</a>'
            '<a href="/about">About</a>'
            '<a href="/team">Team</a>'
            '<a href="/contact">Contact</a>'
            '<a href="https://external.example.com/integrations">External</a>'
            '<a href="/ai-copilot">AI Copilot</a>'
            "</body></html>"
        ),
        "text": "Homepage text",
    }

    def mock_get(url: str, timeout: int = 10):
        responses = {
            "https://example.com/docs": MockResponse(200, "<html><body>Developer docs</body></html>"),
            "https://example.com/plans": MockResponse(200, "<html><body>$49 per seat</body></html>"),
            "https://example.com/features": MockResponse(200, "<html><body>Feature overview</body></html>"),
            "https://example.com/about": MockResponse(200, "<html><body>About ExampleCorp</body></html>"),
            "https://example.com/team": MockResponse(200, "<html><body>Leadership team</body></html>"),
            "https://example.com/contact": MockResponse(200, "<html><body>Contact us</body></html>"),
            "https://example.com/ai-copilot": MockResponse(200, "<html><body>AI copilot for CSMs</body></html>"),
        }
        return responses[url]

    monkeypatch.setattr(site_explorer.requests, "get", mock_get)

    result = site_explorer.explore_vendor_site(homepage_payload)

    assert "privacy_page" not in result
    assert result["developer_docs_page"]["website"] == "https://example.com/docs"
    assert result["pricing_page"]["website"] == "https://example.com/plans"
    assert result["product_page"]["website"] == "https://example.com/features"
    assert result["about_page"]["website"] == "https://example.com/about"
    assert result["team_page"]["website"] == "https://example.com/team"
    assert result["contact_page"]["website"] == "https://example.com/contact"
    assert result["extra_pages"] == [
        {
            "vendor_name": "",
            "website": "https://example.com/ai-copilot",
            "url": "https://example.com/ai-copilot",
            "page_type": "product_page",
            "status_code": 200,
            "html": "<html><body>AI copilot for CSMs</body></html>",
            "text": "AI copilot for CSMs",
            "fetch_backend": "requests",
        }
    ]


def test_explore_vendor_site_handles_unreachable_pages_gracefully(monkeypatch):
    homepage_payload = {
        "vendor_name": "ExampleCorp",
        "website": "https://example.com",
        "source": "google_search",
        "page_type": "homepage",
        "status_code": 200,
        "html": (
            '<html><body>'
            '<a href="/plans">Pricing</a>'
            '<a href="/trust-center">Security and Compliance</a>'
            "</body></html>"
        ),
        "text": "Homepage text",
    }

    def mock_get(url: str, timeout: int = 10):
        if url == "https://example.com/plans":
            return MockResponse(200, "<html><body>$49 per seat</body></html>")
        raise site_explorer.requests.RequestException("timeout")

    monkeypatch.setattr(site_explorer.requests, "get", mock_get)
    # Prevent real Playwright/Apify calls for unreachable pages
    monkeypatch.setattr(site_explorer.discovery_mode, "fetch_page_with_fallback", lambda url, config: None)

    result = site_explorer.explore_vendor_site(homepage_payload)

    assert result["pricing_page"]["website"] == "https://example.com/plans"
    assert "security_page" not in result
    assert result["extra_pages"] == []


def test_explore_vendor_site_discovers_developer_docs_page(monkeypatch):
    homepage_payload = {
        "vendor_name": "ExampleCorp",
        "website": "https://example.com",
        "source": "google_search",
        "page_type": "homepage",
        "status_code": 200,
        "html": (
            '<html><body>'
            '<a href="/developers">Developers</a>'
            '<a href="/docs/api">API Docs</a>'
            "</body></html>"
        ),
        "text": "Homepage text",
    }

    def mock_get(url: str, timeout: int = 10):
        responses = {
            "https://example.com/developers": MockResponse(200, "<html><body>Developer portal</body></html>"),
            "https://example.com/docs/api": MockResponse(200, "<html><body>API reference</body></html>"),
            "https://example.com/sitemap.xml": MockResponse(404, "<html><body>Not found</body></html>"),
            "https://example.com/sitemap_index.xml": MockResponse(404, "<html><body>Not found</body></html>"),
        }
        return responses[url]

    monkeypatch.setattr(site_explorer.requests, "get", mock_get)

    result = site_explorer.explore_vendor_site(homepage_payload)

    assert result["developer_docs_page"]["website"] == "https://example.com/developers"


def test_explore_vendor_site_uses_seed_paths_when_homepage_html_is_unavailable(monkeypatch):
    homepage_payload = {
        "vendor_name": "ExampleCorp",
        "website": "https://example.com",
        "source": "google_search",
        "page_type": "homepage",
        "status_code": 403,
        "html": "",
        "text": "",
    }

    def mock_get(url: str, timeout: int = 10):
        responses = {
            "https://example.com/our-story": MockResponse(200, "<html><body>About ExampleCorp</body></html>"),
            "https://example.com/contact-us": MockResponse(200, "<html><body>Contact us</body></html>"),
            "https://example.com/blog": MockResponse(200, "<html><body>Blog articles</body></html>"),
        }
        if url in responses:
            return responses[url]
        return MockResponse(403, "<html><body>403 Forbidden</body></html>")

    monkeypatch.setattr(site_explorer.requests, "get", mock_get)

    result = site_explorer.explore_vendor_site(homepage_payload)

    assert result["about_page"]["website"] == "https://example.com/our-story"
    assert result["contact_page"]["website"] == "https://example.com/contact-us"
    assert result["blog_page"]["website"] == "https://example.com/blog"


def test_explore_vendor_site_allows_trusted_docs_subdomain(monkeypatch):
    homepage_payload = {
        "vendor_name": "ExampleCorp",
        "website": "https://example.com",
        "source": "google_search",
        "page_type": "homepage",
        "status_code": 200,
        "html": '<html><body><a href="https://docs.example.com/">Documentation</a></body></html>',
        "text": "Homepage text",
    }

    def mock_get(url: str, timeout: int = 10):
        if url == "https://docs.example.com":
            return MockResponse(200, "<html><body>API reference</body></html>")
        return MockResponse(404, "<html><body>Not found</body></html>")

    monkeypatch.setattr(site_explorer.requests, "get", mock_get)

    result = site_explorer.explore_vendor_site(homepage_payload)

    assert result["developer_docs_page"]["website"] == "https://docs.example.com"


def test_explore_vendor_site_uses_discovery_mode_links_for_sparse_homepages(monkeypatch):
    homepage_payload = {
        "vendor_name": "Gainsight",
        "website": "https://gainsight.com",
        "source": "google_search",
        "page_type": "homepage",
        "status_code": 200,
        "html": "<html><body><a href=\"/pricing\">Pricing</a></body></html>",
        "text": "Homepage text",
    }

    def mock_get(url: str, timeout: int = 10):
        responses = {
            "https://gainsight.com/pricing": MockResponse(200, "<html><body>Pricing details</body></html>"),
            "https://gainsight.com/staircase-ai": MockResponse(200, "<html><body>AI conversation insights</body></html>"),
            "https://gainsight.com/customer-success": MockResponse(200, "<html><body>Retention and expansion workflows</body></html>"),
            "https://gainsight.com/sitemap.xml": MockResponse(404, "<html><body>Not found</body></html>"),
            "https://gainsight.com/sitemap_index.xml": MockResponse(404, "<html><body>Not found</body></html>"),
        }
        return responses[url]

    monkeypatch.setattr(site_explorer.requests, "get", mock_get)
    monkeypatch.setattr(
        site_explorer.discovery_mode,
        "discover_vendor_links",
        lambda homepage_payload, config: [
            ("https://gainsight.com/staircase-ai", "Staircase AI"),
            ("https://gainsight.com/customer-success", "Customer Success"),
        ],
    )
    # Prevent real Playwright/Apify calls for any URL not in mock_get dict
    monkeypatch.setattr(site_explorer.discovery_mode, "fetch_page_with_fallback", lambda url, config: None)

    result = site_explorer.explore_vendor_site(homepage_payload)

    assert result["pricing_page"]["website"] == "https://gainsight.com/pricing"
    assert result["product_page"]["website"] == "https://gainsight.com/staircase-ai"
    assert result["extra_pages"] == [
        {
            "vendor_name": "",
            "website": "https://gainsight.com/customer-success",
            "url": "https://gainsight.com/customer-success",
            "page_type": "product_page",
            "status_code": 200,
            "html": "<html><body>Retention and expansion workflows</body></html>",
            "text": "Retention and expansion workflows",
            "fetch_backend": "requests",
        }
    ]


def test_explore_vendor_site_uses_browser_fallback_for_blocked_child_pages(monkeypatch):
    homepage_payload = {
        "vendor_name": "Gainsight",
        "website": "https://gainsight.com",
        "source": "google_search",
        "page_type": "homepage",
        "status_code": 200,
        "html": '<html><body><a href="/staircase-ai">Staircase AI</a></body></html>',
        "text": "Homepage text",
    }

    def mock_get(url: str, timeout: int = 10):
        if url == "https://gainsight.com/staircase-ai":
            return MockResponse(403, "<html><body>Access denied</body></html>")
        if url in {"https://gainsight.com/sitemap.xml", "https://gainsight.com/sitemap_index.xml"}:
            return MockResponse(404, "<html><body>Not found</body></html>")
        raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr(site_explorer.requests, "get", mock_get)
    monkeypatch.setattr(
        site_explorer.discovery_mode,
        "fetch_page_with_fallback",
        lambda url, config: {
            "status_code": 200,
            "html": "<html><body>Rendered product page</body></html>",
            "text": "Rendered product page",
            "fetch_backend": "apify",
        },
    )

    result = site_explorer.explore_vendor_site(homepage_payload)

    assert result["product_page"]["website"] == "https://gainsight.com/staircase-ai"
    assert result["product_page"]["text"] == "Rendered product page"
    assert result["product_page"]["fetch_backend"] == "apify"
