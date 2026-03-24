"""Tests for the Apify Google Search discovery adapter."""

from types import SimpleNamespace

from services.discovery import apify_sources


class FakeDatasetItems:
    def __init__(self, items):
        self.items = items


class FakeDataset:
    def __init__(self, items):
        self.items = items

    def list_items(self):
        return FakeDatasetItems(self.items)


class FakeActor:
    def __init__(self, actor_id: str, dataset_id: str, calls: list[tuple[str, dict[str, object]]]):
        self.actor_id = actor_id
        self.dataset_id = dataset_id
        self.calls = calls

    def call(self, run_input: dict[str, object]):
        self.calls.append((self.actor_id, run_input))
        return {"defaultDatasetId": self.dataset_id}


class FakeApifyClient:
    def __init__(self, datasets: dict[str, list[dict[str, object]]]):
        self.datasets = datasets
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.actor_ids: list[str] = []

    def actor(self, actor_id: str):
        self.actor_ids.append(actor_id)
        dataset_id = f"dataset_{len(self.actor_ids)}"
        return FakeActor(actor_id, dataset_id, self.calls)

    def dataset(self, dataset_id: str):
        return FakeDataset(self.datasets[dataset_id])


def test_fetch_google_search_normalizes_candidates_and_deduplicates(monkeypatch):
    fake_client = FakeApifyClient(
        {
            "dataset_1": [
                {
                    "title": "RenewAI",
                    "url": "https://www.renewai.com/pricing",
                    "description": "Renewal automation for customer success teams",
                },
                {
                    "title": "RenewAI Duplicate",
                    "url": "https://renewai.com/customers",
                    "description": "Duplicate domain should be skipped",
                },
            ],
            "dataset_2": [
                {
                    "title": "OnboardFlow",
                    "url": "https://onboardflow.io",
                    "description": "Onboarding automation for customer success teams",
                }
            ],
        }
    )

    monkeypatch.setattr(apify_sources, "get_apify_client", lambda: fake_client)
    monkeypatch.setattr(
        apify_sources,
        "load_pipeline_config",
        lambda: _fake_pipeline_config(max_pages_per_query=7, results_per_page=10),
    )

    results = apify_sources.fetch_google_search(["query one", "query two"])

    assert fake_client.actor_ids == [
        apify_sources.GOOGLE_SEARCH_ACTOR,
        apify_sources.GOOGLE_SEARCH_ACTOR,
    ]
    assert fake_client.calls == [
        (
            apify_sources.GOOGLE_SEARCH_ACTOR,
            {
                "queries": "query one",
                "maxPagesPerQuery": 7,
                "resultsPerPage": 10,
            },
        ),
        (
            apify_sources.GOOGLE_SEARCH_ACTOR,
            {
                "queries": "query two",
                "maxPagesPerQuery": 7,
                "resultsPerPage": 10,
            },
        ),
    ]
    assert results == [
        {
            "company_name": "RenewAI",
            "website": "https://renewai.com",
            "raw_description": "Renewal automation for customer success teams",
            "source": "google_search",
        },
        {
            "company_name": "OnboardFlow",
            "website": "https://onboardflow.io",
            "raw_description": "Onboarding automation for customer success teams",
            "source": "google_search",
        },
    ]


def test_fetch_google_search_returns_empty_list_for_empty_queries():
    assert apify_sources.fetch_google_search([]) == []


def test_fetch_google_search_candidate_records_include_query_and_rank(monkeypatch):
    fake_client = FakeApifyClient(
        {
            "dataset_1": [
                {
                    "title": "Vendor One",
                    "url": "https://vendorone.com/platform",
                    "description": "Customer success AI platform",
                },
                {
                    "title": "Vendor Two",
                    "url": "https://vendortwo.io",
                    "description": "Renewal automation software",
                },
            ]
        }
    )

    monkeypatch.setattr(apify_sources, "get_apify_client", lambda: fake_client)
    monkeypatch.setattr(
        apify_sources,
        "load_pipeline_config",
        lambda: _fake_pipeline_config(),
    )

    results = apify_sources.fetch_google_search_candidate_records(["customer success ai"])

    assert results[0]["candidate_domain"] == "vendorone.com"
    assert results[0]["source_query"] == "customer success ai"
    assert results[0]["source_rank"] == 1
    assert results[0]["candidate_status"] == "new"
    assert results[0]["status"] == "new"
    assert results[1]["candidate_domain"] == "vendortwo.io"
    assert results[1]["source_rank"] == 2


def test_get_apify_client_requires_api_token(monkeypatch):
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)

    try:
        apify_sources.get_apify_client()
    except RuntimeError as exc:
        assert str(exc) == "APIFY_API_TOKEN must be set"
    else:
        raise AssertionError("Expected RuntimeError when APIFY_API_TOKEN is missing")


def test_fetch_google_search_uses_organic_result_urls_not_google_domain(monkeypatch):
    fake_client = FakeApifyClient(
        {
            "dataset_1": [
                {
                    "url": "https://www.google.com/search?q=customer+success+ai",
                    "organicResults": [
                        {
                            "title": "Vendor One",
                            "url": "https://vendorone.com/platform",
                            "description": "Customer success AI platform",
                        },
                        {
                            "title": "Vendor Two",
                            "url": "https://www.vendortwo.io",
                            "description": "Renewal automation software",
                        },
                    ],
                }
            ]
        }
    )

    monkeypatch.setattr(apify_sources, "get_apify_client", lambda: fake_client)
    monkeypatch.setattr(
        apify_sources,
        "load_pipeline_config",
        lambda: _fake_pipeline_config(),
    )

    results = apify_sources.fetch_google_search(["customer success ai"])

    assert results == [
        {
            "company_name": "Vendor One",
            "website": "https://vendorone.com",
            "raw_description": "Customer success AI platform",
            "source": "google_search",
        },
        {
            "company_name": "Vendor Two",
            "website": "https://vendortwo.io",
            "raw_description": "Renewal automation software",
            "source": "google_search",
        },
    ]


def test_fetch_google_search_filters_junk_domains_and_generic_content(monkeypatch):
    fake_client = FakeApifyClient(
        {
            "dataset_1": [
                {
                    "title": "Google Search",
                    "url": "https://www.google.com/search?q=customer+success+ai",
                    "description": "Search results page",
                },
                {
                    "title": "Any CSMs doing neat things with AI? : r/CustomerSuccess",
                    "url": "https://www.reddit.com/r/CustomerSuccess/comments/abc123",
                    "description": "Community discussion about tools",
                },
                {
                    "title": "Best Customer Success Platforms Reviews 2026",
                    "url": "https://www.gartner.com/reviews/market/customer-success-management-platforms",
                    "description": "Compare top customer success platforms",
                },
                {
                    "title": "Customer Success Blog: how to improve retention",
                    "url": "https://examplemedia.com/blog/customer-success-retention",
                    "description": "Guide for reducing churn",
                },
                {
                    "title": "VendorFlow",
                    "url": "https://vendorflow.io",
                    "description": "Customer success AI platform for onboarding automation",
                },
            ]
        }
    )

    monkeypatch.setattr(apify_sources, "get_apify_client", lambda: fake_client)
    monkeypatch.setattr(
        apify_sources,
        "load_pipeline_config",
        lambda: _fake_pipeline_config(),
    )

    results = apify_sources.fetch_google_search(["customer success ai"])

    assert results == [
        {
            "company_name": "VendorFlow",
            "website": "https://vendorflow.io",
            "raw_description": "Customer success AI platform for onboarding automation",
            "source": "google_search",
        }
    ]


def test_fetch_google_search_rejects_malformed_domains_and_canonicalizes_vendor_root(monkeypatch):
    fake_client = FakeApifyClient(
        {
            "dataset_1": [
                {
                    "title": "Vendor One",
                    "url": "HTTPS://WWW.VENDORONE.COM/platform?ref=ad",
                    "description": "Customer success AI platform",
                },
                {
                    "title": "Bad Domain",
                    "url": "https://bad_domain.com/platform",
                    "description": "Customer success AI platform",
                },
                {
                    "title": "Bad Scheme",
                    "url": "javascript:alert(1)",
                    "description": "Customer success AI platform",
                },
            ]
        }
    )

    monkeypatch.setattr(apify_sources, "get_apify_client", lambda: fake_client)
    monkeypatch.setattr(
        apify_sources,
        "load_pipeline_config",
        lambda: _fake_pipeline_config(),
    )

    results = apify_sources.fetch_google_search(["customer success ai"])

    assert results == [
        {
            "company_name": "Vendor One",
            "website": "https://vendorone.com",
            "raw_description": "Customer success AI platform",
            "source": "google_search",
        }
    ]


def test_fetch_google_search_keeps_vendor_domains_and_prefers_root_homepage(monkeypatch):
    fake_client = FakeApifyClient(
        {
            "dataset_1": [
                {
                    "title": "AI for Customer Success: 7 tools that actually deliver value",
                    "url": "https://dock.us/blog/ai-for-customer-success-tools",
                    "description": "Customer success software with AI workflows",
                }
            ]
        }
    )

    monkeypatch.setattr(apify_sources, "get_apify_client", lambda: fake_client)
    monkeypatch.setattr(
        apify_sources,
        "load_pipeline_config",
        lambda: _fake_pipeline_config(),
    )

    results = apify_sources.fetch_google_search(["customer success ai"])

    assert results == [
        {
            "company_name": "Dock",
            "website": "https://dock.us",
            "raw_description": "Customer success software with AI workflows",
            "source": "google_search",
        }
    ]


def test_fetch_google_search_filters_jobs_and_interstitial_pages(monkeypatch):
    fake_client = FakeApifyClient(
        {
            "dataset_1": [
                {
                    "title": "Job Application for AI Engineer at HumanSignal",
                    "url": "https://job-boards.greenhouse.io/humansignal/jobs/123",
                    "description": "Customer success and AI role",
                },
                {
                    "title": "Just a moment...",
                    "url": "https://blog.hubspot.com/service/ai-and-customer-success",
                    "description": "Access denied",
                },
                {
                    "title": "Planhat",
                    "url": "https://planhat.com/customer-success-platform",
                    "description": "Customer success platform for retention and expansion",
                },
            ]
        }
    )

    monkeypatch.setattr(apify_sources, "get_apify_client", lambda: fake_client)
    monkeypatch.setattr(
        apify_sources,
        "load_pipeline_config",
        lambda: _fake_pipeline_config(),
    )

    results = apify_sources.fetch_google_search(["customer success ai"])

    assert results == [
        {
            "company_name": "Planhat",
            "website": "https://planhat.com",
            "raw_description": "Customer success platform for retention and expansion",
            "source": "google_search",
        }
    ]


def test_fetch_google_search_uses_domain_name_for_vendor_hosted_listicle_titles(monkeypatch):
    fake_client = FakeApifyClient(
        {
            "dataset_1": [
                {
                    "title": "CSM Tools: 15 Best Customer Success Platforms for 2026",
                    "url": "https://usepylon.com/blog/customer-success-platforms",
                    "description": "Customer success software for onboarding and product adoption",
                }
            ]
        }
    )

    monkeypatch.setattr(apify_sources, "get_apify_client", lambda: fake_client)

    results = apify_sources.fetch_google_search(["customer success ai"])

    assert results == [
        {
            "company_name": "Usepylon",
            "website": "https://usepylon.com",
            "raw_description": "Customer success software for onboarding and product adoption",
            "source": "google_search",
        }
    ]


def test_fetch_google_search_drops_generic_ai_tools_without_cs_signals(monkeypatch):
    fake_client = FakeApifyClient(
        {
            "dataset_1": [
                {
                    "title": "Forecast Copilot",
                    "url": "https://forecastcopilot.ai",
                    "description": "AI software for revenue teams",
                },
                {
                    "title": "RenewPilot",
                    "url": "https://renewpilot.ai",
                    "description": "Renewal automation for customer success teams",
                },
            ]
        }
    )

    monkeypatch.setattr(apify_sources, "get_apify_client", lambda: fake_client)

    results = apify_sources.fetch_google_search(["customer success ai"])

    assert results == [
        {
            "company_name": "RenewPilot",
            "website": "https://renewpilot.ai",
            "raw_description": "Renewal automation for customer success teams",
            "source": "google_search",
        }
    ]


def test_fetch_rendered_page_runs_website_content_crawler_and_normalizes_result(monkeypatch):
    fake_client = FakeApifyClient(
        {
            "dataset_1": [
                {
                    "url": "https://www.gainsight.com/staircase-ai/",
                    "statusCode": 200,
                    "html": "<html><body>Staircase AI</body></html>",
                    "text": "Staircase AI",
                }
            ]
        }
    )

    monkeypatch.setattr(apify_sources, "get_apify_client", lambda: fake_client)

    result = apify_sources.fetch_rendered_page(
        "https://www.gainsight.com/staircase-ai/",
        actor_id=apify_sources.WEBSITE_CONTENT_CRAWLER_ACTOR,
        max_pages=1,
        use_proxy=True,
    )

    assert fake_client.actor_ids == [apify_sources.WEBSITE_CONTENT_CRAWLER_ACTOR]
    assert fake_client.calls == [
        (
            apify_sources.WEBSITE_CONTENT_CRAWLER_ACTOR,
            {
                "startUrls": [{"url": "https://gainsight.com/staircase-ai"}],
                "includeUrlGlobs": ["https://gainsight.com/staircase-ai", "https://gainsight.com/staircase-ai/"],
                "maxCrawlPages": 1,
                "saveHtml": True,
                "saveMarkdown": True,
                "removeCookieWarnings": True,
                "proxyConfiguration": {"useApifyProxy": True},
            },
        )
    ]
    assert result == {
        "url": "https://gainsight.com/staircase-ai",
        "status_code": 200,
        "html": "<html><body>Staircase AI</body></html>",
        "text": "Staircase AI",
        "fetch_backend": "apify",
        "fetch_actor_id": apify_sources.WEBSITE_CONTENT_CRAWLER_ACTOR,
    }


def test_fetch_rendered_page_prefers_path_match_over_same_domain_result(monkeypatch):
    fake_client = FakeApifyClient(
        {
            "dataset_1": [
                {
                    "url": "https://www.gainsight.com/",
                    "statusCode": 200,
                    "html": "<html><body>Homepage</body></html>",
                    "text": "Homepage",
                },
                {
                    "url": "https://www.gainsight.com/customer-success/",
                    "statusCode": 200,
                    "markdown": "Customer Success product page",
                },
            ]
        }
    )

    monkeypatch.setattr(apify_sources, "get_apify_client", lambda: fake_client)

    result = apify_sources.fetch_rendered_page("https://www.gainsight.com/customer-success/")

    assert result == {
        "url": "https://gainsight.com/customer-success",
        "status_code": 200,
        "html": "<html><body>Customer Success product page</body></html>",
        "text": "Customer Success product page",
        "fetch_backend": "apify",
        "fetch_actor_id": apify_sources.WEBSITE_CONTENT_CRAWLER_ACTOR,
    }


def _fake_pipeline_config(*, max_pages_per_query: int = 5, results_per_page: int = 10):
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
