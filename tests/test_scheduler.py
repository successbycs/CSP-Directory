"""Tests for scheduled discovery query resolution."""

from types import SimpleNamespace

from services.pipeline import scheduler


def test_run_discovery_job_uses_configured_queries(monkeypatch):
    monkeypatch.delenv("DISCOVERY_QUERIES", raising=False)
    monkeypatch.delenv("DISCOVERY_QUERY", raising=False)
    monkeypatch.setattr(
        scheduler,
        "load_pipeline_config",
        lambda: _config_with_queries("query one", "query two"),
    )

    called = {}
    monkeypatch.setattr(
        scheduler,
        "run_mvp_pipeline",
        lambda queries: called.setdefault("queries", queries) or [],
    )

    scheduler.run_discovery_job()

    assert called["queries"] == ["query one", "query two"]


def test_run_discovery_job_prefers_comma_separated_env_queries(monkeypatch):
    monkeypatch.setenv("DISCOVERY_QUERIES", "query one, query two")
    monkeypatch.setenv("DISCOVERY_QUERY", "query three")

    called = {}
    monkeypatch.setattr(
        scheduler,
        "run_mvp_pipeline",
        lambda queries: called.setdefault("queries", queries) or [],
    )

    scheduler.run_discovery_job()

    assert called["queries"] == ["query one", "query two"]


def test_run_discovery_job_falls_back_to_single_env_query(monkeypatch):
    monkeypatch.delenv("DISCOVERY_QUERIES", raising=False)
    monkeypatch.setenv("DISCOVERY_QUERY", "query one")

    called = {}
    monkeypatch.setattr(
        scheduler,
        "run_mvp_pipeline",
        lambda queries: called.setdefault("queries", queries) or [],
    )

    scheduler.run_discovery_job()

    assert called["queries"] == ["query one"]


def _config_with_queries(*queries: str):
    return SimpleNamespace(discovery=SimpleNamespace(queries=queries))
