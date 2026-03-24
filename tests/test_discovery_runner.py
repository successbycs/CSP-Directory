"""Tests for the explicit Phase 1 discovery runner."""

from types import SimpleNamespace

from services.pipeline.discovery_runner import run_discovery_phase


def test_run_discovery_phase_deduplicates_candidates_and_queues_new_domains(monkeypatch):
    monkeypatch.setattr(
        "services.pipeline.discovery_runner.load_pipeline_config",
        lambda: _fake_pipeline_config(max_candidate_domains_per_run=10),
    )

    candidate_records = [
        _candidate_record("renewai.com", "query one", 1),
        _candidate_record("renewai.com", "query two", 2),
        _candidate_record("onboardflow.io", "query two", 3),
    ]

    records, queued_candidates, skipped_existing_count = run_discovery_phase(
        ["query one", "query two"],
        fetch_candidate_records_fn=lambda _queries: candidate_records,
        vendor_exists_fn=lambda website: website == "https://onboardflow.io",
    )

    assert skipped_existing_count == 1
    assert records == [
        {
            **_candidate_record("renewai.com", "query one", 1),
            "candidate_status": "queued_for_enrichment",
            "status": "queued_for_enrichment",
        },
        {
            **_candidate_record("onboardflow.io", "query two", 3),
            "candidate_status": "enriched",
            "status": "enriched",
        },
    ]
    assert queued_candidates == [
        {
            "candidate_domain": "renewai.com",
            "candidate_title": "Renewai",
            "candidate_description": "Customer success platform",
            "source_query": "query one",
            "source_rank": "1",
            "discovered_at": "2026-03-16T00:00:00+00:00",
            "candidate_status": "queued_for_enrichment",
            "status": "queued_for_enrichment",
            "company_name": "Renewai",
            "vendor_name": "Renewai",
            "website": "https://renewai.com",
            "source": "google_search",
            "raw_description": "Customer success platform",
        }
    ]


def test_run_discovery_phase_honors_candidate_limit(monkeypatch):
    monkeypatch.setattr(
        "services.pipeline.discovery_runner.load_pipeline_config",
        lambda: _fake_pipeline_config(max_candidate_domains_per_run=1),
    )

    candidate_records = [
        _candidate_record("renewai.com", "query one", 1),
        _candidate_record("onboardflow.io", "query one", 2),
    ]

    records, queued_candidates, skipped_existing_count = run_discovery_phase(
        "query one",
        fetch_candidate_records_fn=lambda _queries: candidate_records,
        vendor_exists_fn=None,
    )

    assert skipped_existing_count == 0
    assert len(records) == 1
    assert len(queued_candidates) == 1
    assert records[0]["candidate_domain"] == "renewai.com"


def _candidate_record(candidate_domain: str, source_query: str, source_rank: int) -> dict[str, object]:
    vendor_name = candidate_domain.split(".")[0].title()
    return {
        "candidate_domain": candidate_domain,
        "candidate_title": vendor_name,
        "candidate_description": "Customer success platform",
        "source_query": source_query,
        "source_rank": source_rank,
        "discovered_at": "2026-03-16T00:00:00+00:00",
        "candidate_status": "new",
        "status": "new",
        "company_name": vendor_name,
        "website": f"https://{candidate_domain}",
        "raw_description": "Customer success platform",
        "source": "google_search",
    }


def _fake_pipeline_config(*, max_candidate_domains_per_run: int):
    return SimpleNamespace(
        discovery=SimpleNamespace(max_candidate_domains_per_run=max_candidate_domains_per_run)
    )
