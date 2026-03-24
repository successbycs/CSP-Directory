"""Tests for the unified repo-level pipeline config loader."""

from pathlib import Path

import pytest

from services.config.load_config import load_pipeline_config


def test_load_pipeline_config_reads_required_sections(tmp_path: Path):
    config_path = tmp_path / "pipeline_config.json"
    config_path.write_text(
        """
        {
          "discovery": {
            "queries": ["query one", "query two"],
            "source_engine": "google_search",
            "actor_id": "apify/google-search-scraper",
            "max_pages_per_query": 5,
            "results_per_page": 10,
            "max_candidate_domains_per_run": 25,
            "junk_domain_denylist": ["reddit.com"],
            "article_path_hints": ["/blog"],
            "content_hints": ["review"],
            "product_hints": ["platform"],
            "customer_success_hints": ["customer success"],
            "noise_subdomain_prefixes": ["blog."],
            "noise_domain_hints": ["greenhouse"],
            "job_path_hints": ["/jobs"],
            "interstitial_hints": ["just a moment"]
          },
          "enrichment": {
            "max_non_homepage_pages": 5,
            "request_timeout_seconds": 10,
            "discovery_mode": "auto",
            "sparse_link_threshold": 2,
            "browser_discovery_timeout_ms": 9000,
            "browser_nav_labels": ["Products", "Resources"],
            "external_fetch_backend": "apify",
            "external_fetch_actor_id": "apify/website-content-crawler",
            "external_fetch_max_pages": 2,
            "external_fetch_use_proxy": true,
            "page_priority": ["pricing_page", "product_page"],
            "page_patterns": {
              "pricing_page": ["pricing"],
              "product_page": ["product"]
            },
            "junk_hints": ["privacy"]
          },
          "directory_relevance": {
            "include_confidence_levels": ["medium", "high"],
            "core_stages": ["Onboard", "Renew"],
            "support_only_stages": ["Support"],
            "core_use_case_hints": ["onboarding"],
            "adjacent_use_case_hints": ["meeting intelligence"],
            "infra_hints": ["messaging api"]
          },
          "llm": {
            "enabled": true,
            "model": "gpt-5-mini",
            "request_timeout_seconds": 45,
            "max_page_text_chars": 1800,
            "max_site_text_chars": 8000,
            "max_error_body_chars": 300
          },
          "google_sheets": {
            "worksheet_name": "vendors",
            "ops_review_enabled": true,
            "runs_worksheet_name": "runs",
            "candidates_worksheet_name": "candidates",
            "vendors_worksheet_name": "vendors",
            "columns": ["vendor_name", "website", "source"]
          }
        }
        """,
        encoding="utf-8",
    )

    result = load_pipeline_config(config_path)

    assert result.discovery.queries == ("query one", "query two")
    assert result.enrichment.page_patterns["pricing_page"] == ("pricing",)
    assert result.enrichment.discovery_mode == "auto"
    assert result.enrichment.sparse_link_threshold == 2
    assert result.enrichment.browser_discovery_timeout_ms == 9000
    assert result.enrichment.browser_nav_labels == ("Products", "Resources")
    assert result.enrichment.external_fetch_backend == "apify"
    assert result.enrichment.external_fetch_actor_id == "apify/website-content-crawler"
    assert result.enrichment.external_fetch_max_pages == 2
    assert result.enrichment.external_fetch_use_proxy is True
    assert result.directory_relevance.core_stages == ("Onboard", "Renew")
    assert result.llm.model == "gpt-5-mini"
    assert result.google_sheets.columns == ("vendor_name", "website", "source")
    assert result.google_sheets.ops_review_enabled is True


def test_load_pipeline_config_fails_clearly_for_missing_sections(tmp_path: Path):
    config_path = tmp_path / "pipeline_config.json"
    config_path.write_text('{"discovery": {}}', encoding="utf-8")

    with pytest.raises(RuntimeError, match="invalid list key queries"):
        load_pipeline_config(config_path)
