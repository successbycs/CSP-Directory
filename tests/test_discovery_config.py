"""Tests for repo-level discovery configuration."""

from pathlib import Path

from services.discovery.discovery_config import (
    GoogleSearchConfig,
    load_google_search_config,
    parse_google_search_queries,
)


def test_load_google_search_config_reads_toml_values(tmp_path: Path):
    config_path = tmp_path / "discovery.toml"
    config_path.write_text(
        '[google_search]\nqueries = "query one, query two"\nmax_pages_per_query = 12\nresults_per_page = 10\nmax_candidate_domains_per_run = 25\n',
        encoding="utf-8",
    )

    result = load_google_search_config(config_path)

    assert result == GoogleSearchConfig(
        queries=("query one", "query two"),
        max_pages_per_query=12,
        results_per_page=10,
        max_candidate_domains_per_run=25,
    )


def test_load_google_search_config_clamps_invalid_values(tmp_path: Path):
    config_path = tmp_path / "discovery.toml"
    config_path.write_text(
        "[google_search]\nmax_pages_per_query = 999\nresults_per_page = -1\n",
        encoding="utf-8",
    )

    result = load_google_search_config(config_path)

    assert result == GoogleSearchConfig(max_pages_per_query=20, results_per_page=1)


def test_load_google_search_config_uses_defaults_when_file_is_missing(tmp_path: Path):
    result = load_google_search_config(tmp_path / "missing.toml")

    assert result == GoogleSearchConfig()


def test_load_google_search_config_warns_when_values_are_invalid(tmp_path: Path, caplog):
    config_path = tmp_path / "discovery.toml"
    config_path.write_text(
        "[google_search]\nqueries = []\nmax_pages_per_query = \"many\"\nresults_per_page = 99\n",
        encoding="utf-8",
    )

    result = load_google_search_config(config_path)

    assert result == GoogleSearchConfig(max_pages_per_query=20, results_per_page=10)
    assert "google_search.queries" in caplog.text
    assert "google_search.max_pages_per_query" in caplog.text
    assert "google_search.results_per_page" in caplog.text


def test_parse_google_search_queries_splits_and_strips_queries():
    assert parse_google_search_queries(" query one,query two ,, query three ") == [
        "query one",
        "query two",
        "query three",
    ]
