"""Tests for the discovery web search module."""

from types import SimpleNamespace

from services.discovery import web_search


def test_search_web_calls_apify_google_search_and_returns_vendor_records(monkeypatch):
    called = {}

    def fake_fetch_google_search(queries: list[str]):
        called["queries"] = queries
        return [
            {
                "company_name": "Gainsight",
                "website": "https://gainsight.com",
                "raw_description": "Customer success platform",
                "source": "google_search",
            },
            {
                "company_name": "Vitally",
                "website": "https://vitally.io",
                "raw_description": "Customer health software",
                "source": "google_search",
            },
        ]

    monkeypatch.setattr(
        web_search.apify_sources,
        "fetch_google_search",
        fake_fetch_google_search,
    )

    results = web_search.search_web("customer success case studies")

    assert called["queries"] == ["customer success case studies"]
    expected = [
        {
            "company_name": "Gainsight",
            "vendor_name": "Gainsight",
            "website": "https://gainsight.com",
            "source": "google_search",
            "raw_description": "Customer success platform",
        },
        {
            "company_name": "Vitally",
            "vendor_name": "Vitally",
            "website": "https://vitally.io",
            "source": "google_search",
            "raw_description": "Customer health software",
        },
    ]
    assert results == expected


def test_search_web_accepts_multiple_queries(monkeypatch):
    called = {}

    def fake_fetch_google_search(queries: list[str]):
        called["queries"] = queries
        return []

    monkeypatch.setattr(
        web_search.apify_sources,
        "fetch_google_search",
        fake_fetch_google_search,
    )

    web_search.search_web(["query one", "query two"])

    assert called["queries"] == ["query one", "query two"]


def test_search_web_uses_config_queries_when_no_query_is_provided(monkeypatch):
    called = {}

    def fake_fetch_google_search(queries: list[str]):
        called["queries"] = queries
        return []

    monkeypatch.setattr(
        web_search.apify_sources,
        "fetch_google_search",
        fake_fetch_google_search,
    )
    monkeypatch.setattr(
        web_search,
        "load_pipeline_config",
        lambda: SimpleNamespace(discovery=SimpleNamespace(queries=("query one", "query two"))),
    )

    web_search.search_web()

    assert called["queries"] == ["query one", "query two"]


def test_search_web_candidates_returns_candidate_records(monkeypatch):
    monkeypatch.setattr(
        web_search.apify_sources,
        "fetch_google_search_candidate_records",
        lambda queries: [{"candidate_domain": "gainsight.com", "source_query": queries[0]}],
    )

    results = web_search.search_web_candidates("customer success ai")

    assert results == [{"candidate_domain": "gainsight.com", "source_query": "customer success ai"}]
