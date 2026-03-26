"""Tests for the Apify Google Search discovery adapter (n8n-routed)."""

from services.discovery import apify_sources
from services import n8n_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _search_response(*items):
    """Build an n8n Google Search response from (title, url, snippet) tuples."""
    return {
        "sources": [
            {"title": t, "url": u, "snippet": s}
            for t, u, s in items
        ]
    }


def _crawl_response(*pages):
    """Build an n8n Website Content Crawl response from (url, content) tuples."""
    return {"pages": [{"url": u, "content": c} for u, c in pages]}


def _fake_pipeline_config(*, max_pages_per_query=5, results_per_page=10):
    from types import SimpleNamespace
    return SimpleNamespace(
        discovery=SimpleNamespace(
            actor_id=apify_sources.GOOGLE_SEARCH_ACTOR,
            max_pages_per_query=max_pages_per_query,
            results_per_page=results_per_page,
            source_engine="google_search",
            junk_domain_denylist=(
                "facebook.com",
                "gartner.com",
                "google.com",
                "instagram.com",
                "jobs.ca",
                "linkedin.com",
                "medium.com",
                "reddit.com",
                "substack.com",
                "slashdot.org",
                "sourceforge.net",
                "twitter.com",
                "toolify.ai",
                "wikipedia.org",
                "x.com",
                "youtube.com",
            ),
            article_path_hints=("/article", "/articles", "/blog", "/community", "/forum", "/guide", "/news", "/resources"),
            content_hints=("best ", "blog", "community", "compare", "comparison", "guide", "jobs", "newsletter", "review", "reviews", "top ", "vs "),
            product_hints=("automation", "copilot", "platform", "software", "solution", "tool"),
            customer_success_hints=("customer success", "renewal", "onboarding", "adoption", "retention", "churn", "support automation"),
            noise_subdomain_prefixes=("blog.", "careers.", "community.", "jobs.", "newsletter."),
            noise_domain_hints=("greenhouse", "myworkdayjobs"),
            job_path_hints=("/career", "/careers", "/job", "/jobs"),
            interstitial_hints=("403 forbidden", "access denied", "just a moment"),
        ),
        enrichment=SimpleNamespace(
            external_fetch_backend="apify",
            external_fetch_actor_id=apify_sources.WEBSITE_CONTENT_CRAWLER_ACTOR,
            external_fetch_max_pages=1,
            external_fetch_use_proxy=True,
        ),
    )


# ---------------------------------------------------------------------------
# Google Search tests
# ---------------------------------------------------------------------------

def test_fetch_google_search_normalizes_candidates_and_deduplicates(monkeypatch):
    responses = [
        _search_response(
            ("RenewAI", "https://www.renewai.com/pricing", "Renewal automation for customer success teams"),
            ("RenewAI Duplicate", "https://renewai.com/customers", "Duplicate domain should be skipped"),
        ),
        _search_response(
            ("OnboardFlow", "https://onboardflow.io", "Onboarding automation for customer success teams"),
        ),
    ]
    call_log = []

    def fake_post(path, payload):
        call_log.append((path, payload))
        return responses[len(call_log) - 1]

    monkeypatch.setattr(n8n_client, "post_webhook", fake_post)
    monkeypatch.setattr(apify_sources, "load_pipeline_config", lambda: _fake_pipeline_config(max_pages_per_query=7, results_per_page=10))

    results = apify_sources.fetch_google_search(["query one", "query two"])

    assert call_log == [
        (apify_sources._N8N_WEBHOOK_GOOGLE_SEARCH, {"query": "query one", "max_results": 10, "actor_id": apify_sources.GOOGLE_SEARCH_ACTOR}),
        (apify_sources._N8N_WEBHOOK_GOOGLE_SEARCH, {"query": "query two", "max_results": 10, "actor_id": apify_sources.GOOGLE_SEARCH_ACTOR}),
    ]
    assert results == [
        {"company_name": "RenewAI", "website": "https://renewai.com", "raw_description": "Renewal automation for customer success teams", "source": "google_search"},
        {"company_name": "OnboardFlow", "website": "https://onboardflow.io", "raw_description": "Onboarding automation for customer success teams", "source": "google_search"},
    ]


def test_fetch_google_search_returns_empty_list_for_empty_queries():
    assert apify_sources.fetch_google_search([]) == []


def test_fetch_google_search_candidate_records_include_query_and_rank(monkeypatch):
    monkeypatch.setattr(n8n_client, "post_webhook", lambda path, payload: _search_response(
        ("Vendor One", "https://vendorone.com/platform", "Customer success AI platform"),
        ("Vendor Two", "https://vendortwo.io", "Renewal automation software"),
    ))
    monkeypatch.setattr(apify_sources, "load_pipeline_config", lambda: _fake_pipeline_config())

    results = apify_sources.fetch_google_search_candidate_records(["customer success ai"])

    assert results[0]["candidate_domain"] == "vendorone.com"
    assert results[0]["source_query"] == "customer success ai"
    assert results[0]["source_rank"] == 1
    assert results[0]["candidate_status"] == "new"
    assert results[0]["status"] == "new"
    assert results[1]["candidate_domain"] == "vendortwo.io"
    assert results[1]["source_rank"] == 2


def test_fetch_google_search_filters_junk_domains_and_generic_content(monkeypatch):
    monkeypatch.setattr(n8n_client, "post_webhook", lambda path, payload: _search_response(
        ("Google Search", "https://www.google.com/search?q=customer+success+ai", "Search results page"),
        ("Any CSMs doing neat things? : r/CustomerSuccess", "https://www.reddit.com/r/CustomerSuccess/comments/abc123", "Community discussion"),
        ("Best Customer Success Platforms 2026", "https://www.gartner.com/reviews/market/customer-success-management-platforms", "Compare top platforms"),
        ("Customer Success Blog: how to improve retention", "https://examplemedia.com/blog/customer-success-retention", "Guide for reducing churn"),
        ("VendorFlow", "https://vendorflow.io", "Customer success AI platform for onboarding automation"),
    ))
    monkeypatch.setattr(apify_sources, "load_pipeline_config", lambda: _fake_pipeline_config())

    results = apify_sources.fetch_google_search(["customer success ai"])

    assert results == [
        {"company_name": "VendorFlow", "website": "https://vendorflow.io", "raw_description": "Customer success AI platform for onboarding automation", "source": "google_search"},
    ]


def test_fetch_google_search_rejects_malformed_domains_and_canonicalizes_vendor_root(monkeypatch):
    monkeypatch.setattr(n8n_client, "post_webhook", lambda path, payload: _search_response(
        ("Vendor One", "HTTPS://WWW.VENDORONE.COM/platform?ref=ad", "Customer success AI platform"),
        ("Bad Domain", "https://bad_domain.com/platform", "Customer success AI platform"),
        ("Bad Scheme", "javascript:alert(1)", "Customer success AI platform"),
    ))
    monkeypatch.setattr(apify_sources, "load_pipeline_config", lambda: _fake_pipeline_config())

    results = apify_sources.fetch_google_search(["customer success ai"])

    assert results == [
        {"company_name": "Vendor One", "website": "https://vendorone.com", "raw_description": "Customer success AI platform", "source": "google_search"},
    ]


def test_fetch_google_search_keeps_vendor_domains_and_prefers_root_homepage(monkeypatch):
    monkeypatch.setattr(n8n_client, "post_webhook", lambda path, payload: _search_response(
        ("AI for Customer Success: 7 tools that actually deliver value", "https://dock.us/blog/ai-for-customer-success-tools", "Customer success software with AI workflows"),
    ))
    monkeypatch.setattr(apify_sources, "load_pipeline_config", lambda: _fake_pipeline_config())

    results = apify_sources.fetch_google_search(["customer success ai"])

    assert results == [
        {"company_name": "Dock", "website": "https://dock.us", "raw_description": "Customer success software with AI workflows", "source": "google_search"},
    ]


def test_fetch_google_search_filters_jobs_and_interstitial_pages(monkeypatch):
    monkeypatch.setattr(n8n_client, "post_webhook", lambda path, payload: _search_response(
        ("Job Application for AI Engineer at HumanSignal", "https://job-boards.greenhouse.io/humansignal/jobs/123", "Customer success and AI role"),
        ("Just a moment...", "https://blog.hubspot.com/service/ai-and-customer-success", "Access denied"),
        ("Planhat", "https://planhat.com/customer-success-platform", "Customer success platform for retention and expansion"),
    ))
    monkeypatch.setattr(apify_sources, "load_pipeline_config", lambda: _fake_pipeline_config())

    results = apify_sources.fetch_google_search(["customer success ai"])

    assert results == [
        {"company_name": "Planhat", "website": "https://planhat.com", "raw_description": "Customer success platform for retention and expansion", "source": "google_search"},
    ]


def test_fetch_google_search_uses_domain_name_for_vendor_hosted_listicle_titles(monkeypatch):
    monkeypatch.setattr(n8n_client, "post_webhook", lambda path, payload: _search_response(
        ("CSM Tools: 15 Best Customer Success Platforms for 2026", "https://usepylon.com/blog/customer-success-platforms", "Customer success software for onboarding and product adoption"),
    ))

    results = apify_sources.fetch_google_search(["customer success ai"])

    assert results == [
        {"company_name": "Usepylon", "website": "https://usepylon.com", "raw_description": "Customer success software for onboarding and product adoption", "source": "google_search"},
    ]


def test_fetch_google_search_drops_generic_ai_tools_without_cs_signals(monkeypatch):
    monkeypatch.setattr(n8n_client, "post_webhook", lambda path, payload: _search_response(
        ("Forecast Copilot", "https://forecastcopilot.ai", "AI software for revenue teams"),
        ("RenewPilot", "https://renewpilot.ai", "Renewal automation for customer success teams"),
    ))

    results = apify_sources.fetch_google_search(["customer success ai"])

    assert results == [
        {"company_name": "RenewPilot", "website": "https://renewpilot.ai", "raw_description": "Renewal automation for customer success teams", "source": "google_search"},
    ]


# ---------------------------------------------------------------------------
# Content crawl tests
# ---------------------------------------------------------------------------

def test_fetch_rendered_page_runs_website_content_crawler_and_normalizes_result(monkeypatch):
    call_log = []

    def fake_post(path, payload):
        call_log.append((path, payload))
        return _crawl_response(("https://www.gainsight.com/staircase-ai/", "Staircase AI"))

    monkeypatch.setattr(n8n_client, "post_webhook", fake_post)

    result = apify_sources.fetch_rendered_page(
        "https://www.gainsight.com/staircase-ai/",
        actor_id=apify_sources.WEBSITE_CONTENT_CRAWLER_ACTOR,
        max_pages=1,
        use_proxy=True,
    )

    assert call_log == [(
        apify_sources._N8N_WEBHOOK_CONTENT_CRAWL,
        {
            "start_url": "https://gainsight.com/staircase-ai",
            "actor_id": apify_sources.WEBSITE_CONTENT_CRAWLER_ACTOR,
            "max_crawl_pages": 1,
            "include_full_content": True,
        },
    )]
    assert result == {
        "url": "https://gainsight.com/staircase-ai",
        "status_code": 200,
        "html": "<html><body>Staircase AI</body></html>",
        "text": "Staircase AI",
        "fetch_backend": "apify",
        "fetch_actor_id": apify_sources.WEBSITE_CONTENT_CRAWLER_ACTOR,
    }


def test_fetch_rendered_page_prefers_path_match_over_same_domain_result(monkeypatch):
    monkeypatch.setattr(n8n_client, "post_webhook", lambda path, payload: _crawl_response(
        ("https://www.gainsight.com/", "Homepage"),
        ("https://www.gainsight.com/customer-success/", "Customer Success product page"),
    ))

    result = apify_sources.fetch_rendered_page("https://www.gainsight.com/customer-success/")

    assert result == {
        "url": "https://gainsight.com/customer-success",
        "status_code": 200,
        "html": "<html><body>Customer Success product page</body></html>",
        "text": "Customer Success product page",
        "fetch_backend": "apify",
        "fetch_actor_id": apify_sources.WEBSITE_CONTENT_CRAWLER_ACTOR,
    }
