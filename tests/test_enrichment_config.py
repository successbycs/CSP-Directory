"""Tests for repo-level enrichment configuration."""

from pathlib import Path

from services.enrichment.enrichment_config import load_site_explorer_config


def test_load_site_explorer_config_reads_page_limits_and_patterns(tmp_path: Path):
    config_path = tmp_path / "enrichment.toml"
    config_path.write_text(
        """
[site_explorer]
max_non_homepage_pages = 4
request_timeout_seconds = 12
discovery_mode = "browser"
sparse_link_threshold = 2
browser_discovery_timeout_ms = 15000
browser_nav_labels = ["Products", "Company"]
page_priority = ["security_page", "pricing_page"]
junk_hints = ["privacy", "terms"]

[site_explorer.page_patterns]
security_page = ["security", "trust-center"]
""".strip(),
        encoding="utf-8",
    )

    result = load_site_explorer_config(config_path)

    assert result.max_non_homepage_pages == 4
    assert result.request_timeout_seconds == 12
    assert result.discovery_mode == "browser"
    assert result.sparse_link_threshold == 2
    assert result.browser_discovery_timeout_ms == 15000
    assert result.browser_nav_labels == ("products", "company")
    assert result.page_priority == ("security_page", "pricing_page")
    assert "trust-center" in result.resolved_page_patterns()["security_page"]
    assert result.junk_hints == ("privacy", "terms")
