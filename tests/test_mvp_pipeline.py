"""Tests for the two-phase MVP pipeline orchestration module."""

from services.pipeline import run_mvp_pipeline as pipeline_module
from services.pipeline import orchestrator
from services.pipeline.run_mvp_pipeline import run_mvp_pipeline


def test_run_mvp_pipeline_runs_discovery_and_enrichment_phases(monkeypatch, caplog):
    caplog.set_level("INFO")
    calls = []
    candidate_records = [
        {"candidate_domain": "gainsight.com", "candidate_status": "queued_for_enrichment", "status": "queued_for_enrichment"},
        {"candidate_domain": "vitally.io", "candidate_status": "queued_for_enrichment", "status": "queued_for_enrichment"},
    ]
    queued_vendor_candidates = [
        {"vendor_name": "Gainsight", "website": "https://gainsight.com", "candidate_domain": "gainsight.com"},
        {"vendor_name": "Vitally", "website": "https://vitally.io", "candidate_domain": "vitally.io"},
    ]
    sheet_rows = [
        _sheet_row("Gainsight", "https://gainsight.com"),
        _sheet_row("Vitally", "https://vitally.io"),
    ]

    monkeypatch.setattr(pipeline_module.supabase_client, "is_configured", lambda: False)
    monkeypatch.setattr(pipeline_module.supabase_client, "supports_export_ready_vendor_profiles", lambda: False)
    monkeypatch.setattr(pipeline_module.llm_extractor, "start_pipeline_run", lambda: calls.append(("start", None)))
    monkeypatch.setattr(
        pipeline_module.llm_extractor,
        "log_runtime_configuration",
        lambda: calls.append(("log", None)),
    )
    monkeypatch.setattr(pipeline_module.orchestrator, "_persist_run_record", lambda run_record: None)
    monkeypatch.setattr(pipeline_module.orchestrator, "_write_run_snapshot", lambda run_record: None)
    monkeypatch.setattr(pipeline_module.orchestrator, "_write_candidate_review_snapshot", lambda candidate_records: None)
    monkeypatch.setattr(
        pipeline_module.orchestrator.discovery_runner,
        "run_discovery_phase",
        lambda query, **kwargs: (
            calls.append(("discovery", query)) or (candidate_records, queued_vendor_candidates, 0)
        ),
    )
    monkeypatch.setattr(
        pipeline_module.orchestrator.enrichment_runner,
        "run_enrichment_phase",
        lambda queued_vendor_candidates, **kwargs: (
            calls.append(("enrichment", len(queued_vendor_candidates))) or (sheet_rows, [], 1, 1)
        ),
    )
    monkeypatch.setattr(
        pipeline_module.orchestrator.google_sheets,
        "publish_ops_review_export",
        lambda **kwargs: calls.append(("review_export", kwargs["run_record"]["run_status"])),
    )
    monkeypatch.setattr(
        pipeline_module.orchestrator,
        "_export_directory_dataset",
        lambda enrichment_results: calls.append(("directory_export", len(enrichment_results))) or [],
    )
    monkeypatch.setattr(
        pipeline_module.orchestrator,
        "_export_vendor_review_dataset",
        lambda enrichment_results: calls.append(("review_dataset_export", len(enrichment_results))) or [],
    )
    monkeypatch.setattr(
        pipeline_module.orchestrator,
        "_persist_search_visibility_queries",
        lambda enrichment_results: calls.append(("search_query_persistence", len(enrichment_results))) or [],
    )
    monkeypatch.setattr(
        pipeline_module.orchestrator,
        "_export_search_visibility_artifacts",
        lambda enrichment_results: calls.append(("search_visibility_export", len(enrichment_results)))
        or {"metrics": {"query_count": 2, "ranking_count": 3, "vendor_count": 2}},
    )

    result = run_mvp_pipeline("ai customer success platform")

    assert result == sheet_rows
    assert calls == [
        ("start", None),
        ("log", None),
        ("discovery", "ai customer success platform"),
        ("enrichment", 2),
        ("review_export", "completed"),
        ("directory_export", 0),
        ("review_dataset_export", 0),
        ("search_query_persistence", 0),
        ("search_visibility_export", 0),
    ]
    assert "Phase 1 discovery produced 2 candidate domains and queued 2 vendors for enrichment" in caplog.text
    assert "LLM stage summary: successes=1 fallback_or_skipped=1" in caplog.text


def test_run_mvp_pipeline_retries_discovery_when_persistence_is_unavailable(monkeypatch, caplog):
    caplog.set_level("INFO")
    calls = []

    class MissingTableError(Exception):
        pass

    def fake_run_discovery_phase(query, **kwargs):
        calls.append(("discovery", kwargs.get("vendor_exists_fn") is not None))
        if kwargs.get("vendor_exists_fn") is not None:
            raise MissingTableError('relation "public.cs_vendors" does not exist')
        return ([], [], 0)

    monkeypatch.setattr(pipeline_module.supabase_client, "is_configured", lambda: True)
    monkeypatch.setattr(pipeline_module.supabase_client, "supports_export_ready_vendor_profiles", lambda: True)
    monkeypatch.setattr(pipeline_module.supabase_client, "vendor_exists", lambda _website: False)
    monkeypatch.setattr(pipeline_module.supabase_client, "upsert_vendor_result", lambda *_args: None)
    monkeypatch.setattr(pipeline_module.orchestrator, "_persist_run_record", lambda run_record: None)
    monkeypatch.setattr(pipeline_module.orchestrator, "_write_run_snapshot", lambda run_record: None)
    monkeypatch.setattr(pipeline_module.orchestrator, "_write_candidate_review_snapshot", lambda candidate_records: None)
    monkeypatch.setattr(
        pipeline_module.orchestrator.supabase_client,
        "is_persistence_unavailable_error",
        lambda error: "does not exist" in str(error),
    )
    monkeypatch.setattr(pipeline_module.llm_extractor, "start_pipeline_run", lambda: None)
    monkeypatch.setattr(pipeline_module.llm_extractor, "log_runtime_configuration", lambda: None)
    monkeypatch.setattr(
        pipeline_module.orchestrator.discovery_runner,
        "run_discovery_phase",
        fake_run_discovery_phase,
    )
    monkeypatch.setattr(
        pipeline_module.orchestrator.enrichment_runner,
        "run_enrichment_phase",
        lambda queued_vendor_candidates, **kwargs: ([], [], 0, 0),
    )
    monkeypatch.setattr(
        pipeline_module.orchestrator.google_sheets,
        "publish_ops_review_export",
        lambda **kwargs: calls.append(("review_export", kwargs["run_record"]["run_status"])),
    )
    monkeypatch.setattr(
        pipeline_module.orchestrator,
        "_export_directory_dataset",
        lambda enrichment_results: calls.append(("directory_export", len(enrichment_results))) or [],
    )
    monkeypatch.setattr(
        pipeline_module.orchestrator,
        "_export_vendor_review_dataset",
        lambda enrichment_results: calls.append(("review_dataset_export", len(enrichment_results))) or [],
    )

    result = run_mvp_pipeline("query")

    assert result == []
    assert calls == [
        ("discovery", True),
        ("discovery", False),
        ("review_export", "completed"),
        ("directory_export", 0),
        ("review_dataset_export", 0),
    ]
    assert "Persistence unavailable, continuing without deduplication" in caplog.text


def test_run_mvp_pipeline_updates_candidate_statuses_from_enrichment_results(monkeypatch):
    candidate_records = [
        {"candidate_domain": "signal.example.com", "candidate_status": "queued_for_enrichment", "status": "queued_for_enrichment"},
        {"candidate_domain": "weak.example.com", "candidate_status": "queued_for_enrichment", "status": "queued_for_enrichment"},
    ]
    queued_vendor_candidates = [
        {"vendor_name": "SignalAI", "website": "https://signal.example.com", "candidate_domain": "signal.example.com"},
        {"vendor_name": "WeakAI", "website": "https://weak.example.com", "candidate_domain": "weak.example.com"},
    ]
    enrichment_results = [
        {"candidate_domain": "signal.example.com", "status": "enriched"},
        {"candidate_domain": "weak.example.com", "status": "failed"},
    ]

    monkeypatch.setattr(pipeline_module.supabase_client, "is_configured", lambda: False)
    monkeypatch.setattr(pipeline_module.supabase_client, "supports_export_ready_vendor_profiles", lambda: False)
    monkeypatch.setattr(pipeline_module.llm_extractor, "start_pipeline_run", lambda: None)
    monkeypatch.setattr(pipeline_module.llm_extractor, "log_runtime_configuration", lambda: None)
    monkeypatch.setattr(pipeline_module.orchestrator, "_persist_run_record", lambda run_record: None)
    monkeypatch.setattr(pipeline_module.orchestrator, "_write_run_snapshot", lambda run_record: None)
    monkeypatch.setattr(pipeline_module.orchestrator, "_write_candidate_review_snapshot", lambda candidate_records: None)
    monkeypatch.setattr(
        pipeline_module.orchestrator.discovery_runner,
        "run_discovery_phase",
        lambda query, **kwargs: (candidate_records, queued_vendor_candidates, 0),
    )
    monkeypatch.setattr(
        pipeline_module.orchestrator.enrichment_runner,
        "run_enrichment_phase",
        lambda queued_vendor_candidates, **kwargs: (
            [_sheet_row("SignalAI", "https://signal.example.com")],
            enrichment_results,
            0,
            1,
        ),
    )
    monkeypatch.setattr(
        pipeline_module.orchestrator.google_sheets,
        "publish_ops_review_export",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        pipeline_module.orchestrator,
        "_export_directory_dataset",
        lambda enrichment_results: [],
    )
    monkeypatch.setattr(
        pipeline_module.orchestrator,
        "_export_vendor_review_dataset",
        lambda enrichment_results: [],
    )

    result = run_mvp_pipeline("query")

    assert result == [_sheet_row("SignalAI", "https://signal.example.com")]
    assert candidate_records == [
        {"candidate_domain": "signal.example.com", "candidate_status": "enriched", "status": "enriched"},
        {"candidate_domain": "weak.example.com", "candidate_status": "failed", "status": "failed"},
    ]


def test_run_mvp_pipeline_continues_when_google_sheets_review_export_fails(monkeypatch, caplog):
    caplog.set_level("INFO")
    calls = []
    candidate_records = [
        {"candidate_domain": "gainsight.com", "candidate_status": "queued_for_enrichment", "status": "queued_for_enrichment"},
    ]
    queued_vendor_candidates = [
        {"vendor_name": "Gainsight", "website": "https://gainsight.com", "candidate_domain": "gainsight.com"},
    ]
    sheet_rows = [
        _sheet_row("Gainsight", "https://gainsight.com"),
    ]

    monkeypatch.setattr(pipeline_module.supabase_client, "is_configured", lambda: False)
    monkeypatch.setattr(pipeline_module.supabase_client, "supports_export_ready_vendor_profiles", lambda: False)
    monkeypatch.setattr(pipeline_module.llm_extractor, "start_pipeline_run", lambda: None)
    monkeypatch.setattr(pipeline_module.llm_extractor, "log_runtime_configuration", lambda: None)
    monkeypatch.setattr(pipeline_module.orchestrator, "_persist_run_record", lambda run_record: None)
    monkeypatch.setattr(pipeline_module.orchestrator, "_write_run_snapshot", lambda run_record: None)
    monkeypatch.setattr(pipeline_module.orchestrator, "_write_candidate_review_snapshot", lambda candidate_records: None)
    monkeypatch.setattr(
        pipeline_module.orchestrator.discovery_runner,
        "run_discovery_phase",
        lambda query, **kwargs: (candidate_records, queued_vendor_candidates, 0),
    )
    monkeypatch.setattr(
        pipeline_module.orchestrator.enrichment_runner,
        "run_enrichment_phase",
        lambda queued_vendor_candidates, **kwargs: (sheet_rows, [], 0, 0),
    )
    monkeypatch.setattr(
        pipeline_module.orchestrator.google_sheets,
        "publish_ops_review_export",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("sheet range invalid")),
    )
    monkeypatch.setattr(
        pipeline_module.orchestrator,
        "_export_directory_dataset",
        lambda enrichment_results: calls.append(("directory_export", len(enrichment_results))) or [],
    )
    monkeypatch.setattr(
        pipeline_module.orchestrator,
        "_export_vendor_review_dataset",
        lambda enrichment_results: calls.append(("review_dataset_export", len(enrichment_results))) or [],
    )
    monkeypatch.setattr(
        pipeline_module.orchestrator,
        "_persist_search_visibility_queries",
        lambda enrichment_results: calls.append(("search_query_persistence", len(enrichment_results))) or [],
    )
    monkeypatch.setattr(
        pipeline_module.orchestrator,
        "_export_search_visibility_artifacts",
        lambda enrichment_results: calls.append(("search_visibility_export", len(enrichment_results)))
        or {"metrics": {"query_count": 0, "ranking_count": 0, "vendor_count": 0}},
    )

    result = run_mvp_pipeline("ai customer success platform")

    assert result == sheet_rows
    assert calls == [
        ("directory_export", 0),
        ("review_dataset_export", 0),
        ("search_query_persistence", 0),
        ("search_visibility_export", 0),
    ]
    assert "Google Sheets ops review export failed, continuing with local artifacts only" in caplog.text


def test_run_mvp_pipeline_skips_existing_vendor_dedup_only_when_export_ready(monkeypatch, caplog):
    caplog.set_level("INFO")
    calls = []

    monkeypatch.setattr(pipeline_module.supabase_client, "is_configured", lambda: True)
    monkeypatch.setattr(pipeline_module.orchestrator.supabase_client, "is_configured", lambda: True)
    monkeypatch.setattr(
        pipeline_module.orchestrator.supabase_client,
        "supports_export_ready_vendor_profiles",
        lambda: False,
    )
    monkeypatch.setattr(pipeline_module.orchestrator.supabase_client, "vendor_exists", lambda _website: True)
    monkeypatch.setattr(pipeline_module.orchestrator.supabase_client, "upsert_vendor_result", lambda *_args: None)
    monkeypatch.setattr(pipeline_module.llm_extractor, "start_pipeline_run", lambda: None)
    monkeypatch.setattr(pipeline_module.llm_extractor, "log_runtime_configuration", lambda: None)
    monkeypatch.setattr(pipeline_module.orchestrator, "_persist_run_record", lambda run_record: None)
    monkeypatch.setattr(pipeline_module.orchestrator, "_write_run_snapshot", lambda run_record: None)
    monkeypatch.setattr(pipeline_module.orchestrator, "_write_candidate_review_snapshot", lambda candidate_records: None)
    monkeypatch.setattr(
        pipeline_module.orchestrator.discovery_runner,
        "run_discovery_phase",
        lambda query, **kwargs: (
            calls.append(("discovery_has_vendor_exists", kwargs.get("vendor_exists_fn") is not None)) or ([], [], 0)
        ),
    )
    monkeypatch.setattr(
        pipeline_module.orchestrator.enrichment_runner,
        "run_enrichment_phase",
        lambda queued_vendor_candidates, **kwargs: ([], [], 0, 0),
    )
    monkeypatch.setattr(pipeline_module.orchestrator.google_sheets, "publish_ops_review_export", lambda **kwargs: None)
    monkeypatch.setattr(pipeline_module.orchestrator, "_export_directory_dataset", lambda enrichment_results: [])
    monkeypatch.setattr(pipeline_module.orchestrator, "_export_vendor_review_dataset", lambda enrichment_results: [])

    pipeline_module.orchestrator.run_mvp_pipeline("query")

    assert calls == [("discovery_has_vendor_exists", False)]
    assert "Persistence schema is not export-ready, continuing without deduplication against existing vendors" in caplog.text


def test_run_mvp_pipeline_wrapper_only_enables_vendor_exists_when_export_ready(monkeypatch):
    captured = {}

    monkeypatch.setattr(pipeline_module.supabase_client, "is_configured", lambda: True)
    monkeypatch.setattr(pipeline_module.supabase_client, "supports_export_ready_vendor_profiles", lambda: False)
    monkeypatch.setattr(pipeline_module.supabase_client, "vendor_exists", lambda _website: True)
    monkeypatch.setattr(pipeline_module.supabase_client, "upsert_vendor_result", lambda *_args: None)

    def fake_orchestrator(query, **kwargs):
        captured["query"] = query
        captured["vendor_exists_fn"] = kwargs.get("vendor_exists_fn")
        captured["upsert_vendor_result_fn"] = kwargs.get("upsert_vendor_result_fn")
        return []

    monkeypatch.setattr(pipeline_module.orchestrator, "run_mvp_pipeline", fake_orchestrator)

    result = run_mvp_pipeline("query")

    assert result == []
    assert captured == {
        "query": "query",
        "vendor_exists_fn": None,
        "upsert_vendor_result_fn": pipeline_module.supabase_client.upsert_vendor_result,
    }


def _sheet_row(vendor_name: str, website: str) -> dict[str, str]:
    return {
        "vendor_name": vendor_name,
        "website": website,
        "source": "",
        "mission": "",
        "usp": "",
        "icp": "",
        "use_cases": "",
        "lifecycle_stages": "",
        "pricing": "",
        "free_trial": "",
        "soc2": "",
        "founded": "",
        "case_studies": "",
        "customers": "",
        "value_statements": "",
        "confidence": "",
        "evidence_urls": "",
        "directory_fit": "",
        "directory_category": "",
        "include_in_directory": "",
    }


def test_export_directory_dataset_retries_with_explicit_fallback_profiles(monkeypatch):
    profile = pipeline_module.vendor_intel.VendorIntelligence(
        vendor_name="Fallback Vendor",
        website="https://fallback.example.com",
        include_in_directory=True,
    )
    calls: list[bool] = []

    def fake_export_directory_dataset(*, fallback_profiles=None, prefer_fallback_profiles=False, output_path=None, client=None):
        calls.append(prefer_fallback_profiles)
        if not prefer_fallback_profiles:
            raise RuntimeError("supabase unavailable")
        return [{"vendor_name": "Fallback Vendor"}]

    monkeypatch.setattr(orchestrator.directory_dataset, "export_directory_dataset", fake_export_directory_dataset)

    dataset = orchestrator._export_directory_dataset([{"profile": profile}])

    assert dataset == [{"vendor_name": "Fallback Vendor"}]
    assert calls == [True]


def test_export_directory_dataset_falls_back_when_supabase_returns_empty(monkeypatch):
    profile = pipeline_module.vendor_intel.VendorIntelligence(
        vendor_name="Fallback Vendor",
        website="https://fallback.example.com",
        include_in_directory=True,
    )
    calls: list[bool] = []

    def fake_export_directory_dataset(*, fallback_profiles=None, prefer_fallback_profiles=False, output_path=None, client=None):
        calls.append(prefer_fallback_profiles)
        return [{"vendor_name": "Fallback Vendor"}]

    monkeypatch.setattr(orchestrator.directory_dataset, "export_directory_dataset", fake_export_directory_dataset)

    dataset = orchestrator._export_directory_dataset([{"profile": profile}])

    assert dataset == [{"vendor_name": "Fallback Vendor"}]
    assert calls == [True]


def test_export_vendor_review_dataset_retries_with_explicit_fallback_profiles(monkeypatch):
    profile = pipeline_module.vendor_intel.VendorIntelligence(
        vendor_name="Fallback Vendor",
        website="https://fallback.example.com",
        include_in_directory=True,
    )
    calls: list[bool] = []

    def fake_export_vendor_review_artifacts(
        *,
        fallback_profiles=None,
        prefer_fallback_profiles=False,
        dataset_output_path=None,
        html_output_path=None,
        client=None,
    ):
        calls.append(prefer_fallback_profiles)
        if not prefer_fallback_profiles:
            raise RuntimeError("supabase unavailable")
        return [{"vendor_name": "Fallback Vendor"}]

    monkeypatch.setattr(orchestrator.vendor_review_dataset, "export_vendor_review_artifacts", fake_export_vendor_review_artifacts)

    dataset = orchestrator._export_vendor_review_dataset([{"profile": profile}])

    assert dataset == [{"vendor_name": "Fallback Vendor"}]
    assert calls == [True]


def test_export_vendor_review_dataset_falls_back_when_supabase_rows_are_stale(monkeypatch):
    profile = pipeline_module.vendor_intel.VendorIntelligence(
        vendor_name="Fallback Vendor",
        website="https://fallback.example.com",
        include_in_directory=True,
        confidence="high",
        directory_fit="high",
        directory_category="cs_core",
        mission="Helps customer success teams reduce churn.",
        use_cases=["renewals"],
    )
    calls: list[bool] = []

    def fake_export_vendor_review_artifacts(*, fallback_profiles=None, prefer_fallback_profiles=False, dataset_output_path=None, html_output_path=None, client=None):
        calls.append(prefer_fallback_profiles)
        if not prefer_fallback_profiles:
            return [{
                "vendor_name": "Stale Vendor",
                "confidence": "",
                "directory_fit": "",
                "directory_category": "",
                "include_in_directory": None,
                "mission_summary": "Marketing copy without classification",
                "use_case_summary": "generic summary",
            }]
        return [{"vendor_name": "Fallback Vendor", "confidence": "high", "directory_fit": "high", "directory_category": "cs_core", "include_in_directory": True, "mission_summary": "Helps customer success teams reduce churn.", "use_case_summary": "renewals"}]

    monkeypatch.setattr(orchestrator.vendor_review_dataset, "export_vendor_review_artifacts", fake_export_vendor_review_artifacts)

    dataset = orchestrator._export_vendor_review_dataset([{"profile": profile}])

    assert dataset == [{
        "vendor_name": "Fallback Vendor",
        "confidence": "high",
        "directory_fit": "high",
        "directory_category": "cs_core",
        "include_in_directory": True,
        "mission_summary": "Helps customer success teams reduce churn.",
        "use_case_summary": "renewals",
    }]
    assert calls == [True]


def test_export_vendor_review_dataset_ignores_dropped_profiles(monkeypatch):
    kept_profile = pipeline_module.vendor_intel.VendorIntelligence(
        vendor_name="Kept Vendor",
        website="https://kept.example.com",
        include_in_directory=True,
        confidence="high",
    )
    dropped_profile = pipeline_module.vendor_intel.VendorIntelligence(
        vendor_name="Dropped Vendor",
        website="https://dropped.example.com",
        include_in_directory=False,
        confidence="low",
    )
    captured = {}

    def fake_export_vendor_review_artifacts(
        *,
        fallback_profiles=None,
        prefer_fallback_profiles=False,
        dataset_output_path=None,
        html_output_path=None,
        client=None,
    ):
        captured["prefer_fallback_profiles"] = prefer_fallback_profiles
        captured["fallback_profile_names"] = [profile.vendor_name for profile in fallback_profiles or []]
        return [{"vendor_name": "Kept Vendor"}]

    monkeypatch.setattr(orchestrator.vendor_review_dataset, "export_vendor_review_artifacts", fake_export_vendor_review_artifacts)

    dataset = orchestrator._export_vendor_review_dataset(
        [
            {"status": "enriched", "profile": kept_profile},
            {"status": "dropped_low_confidence", "profile": dropped_profile},
        ]
    )

    assert dataset == [{"vendor_name": "Kept Vendor"}]
    assert captured == {
        "prefer_fallback_profiles": True,
        "fallback_profile_names": ["Kept Vendor"],
    }


def test_persist_search_visibility_queries_uses_current_run_profiles(monkeypatch):
    profile = pipeline_module.vendor_intel.VendorIntelligence(
        vendor_name="Gainsight",
        website="https://gainsight.com",
        icp_buyer=[
            {
                "persona": "VP Customer Success",
                "confidence": "high",
                "google_queries": ["customer success platform"],
                "geo_queries": ["What AI tools reduce churn?"],
            }
        ],
    )
    captured = {}

    monkeypatch.setattr(orchestrator.supabase_client, "is_configured", lambda: True)

    def fake_upsert(vendor_profiles, *, generated_at=None, client=None):
        captured["vendor_names"] = [item.vendor_name for item in vendor_profiles]
        return [{"query_signature": "sig-1"}]

    monkeypatch.setattr(
        orchestrator.search_visibility_store,
        "upsert_buyer_search_queries_from_vendor_profiles",
        fake_upsert,
    )

    rows = orchestrator._persist_search_visibility_queries([{"status": "enriched", "profile": profile}])

    assert rows == [{"query_signature": "sig-1"}]
    assert captured == {"vendor_names": ["Gainsight"]}


def test_export_search_visibility_artifacts_uses_current_run_buyer_queries(monkeypatch):
    profile = pipeline_module.vendor_intel.VendorIntelligence(
        vendor_name="Gainsight",
        website="https://gainsight.com",
        icp_buyer=[
            {
                "persona": "VP Customer Success",
                "confidence": "high",
                "google_queries": ["tools to improve SaaS retention"],
                "geo_queries": ["What AI tools help reduce SaaS churn?"],
            }
        ],
    )
    captured = {}

    def fake_build_query_rows(vendor_profiles, *, generated_at=None):
        captured["fallback_profiles"] = [item.vendor_name for item in vendor_profiles]
        return [
            {
                "query_signature": "sig-1",
                "buyer_role": "VP Customer Success",
                "search_channel": "google",
                "search_provider": "google",
                "query_text": "tools to improve SaaS retention",
            }
        ]

    def fake_export(*, fallback_query_rows=None, fallback_result_rows=None, prefer_fallback_rows=False, client=None, report_output_path=None, html_output_path=None):
        captured["fallback_query_rows"] = fallback_query_rows
        captured["prefer_fallback_rows"] = prefer_fallback_rows
        return {
            "metrics": {"query_count": 1, "ranking_count": 0, "vendor_count": 0},
            "role_query_rankings": [],
            "vendor_visibility_summary": [],
        }

    monkeypatch.setattr(orchestrator.search_visibility_store, "build_buyer_search_query_rows", fake_build_query_rows)
    monkeypatch.setattr(orchestrator.search_visibility_report, "export_search_visibility_artifacts", fake_export)

    report = orchestrator._export_search_visibility_artifacts([{"status": "enriched", "profile": profile}])

    assert report["metrics"]["query_count"] == 1
    assert captured == {
        "fallback_profiles": ["Gainsight"],
        "fallback_query_rows": [
            {
                "query_signature": "sig-1",
                "buyer_role": "VP Customer Success",
                "search_channel": "google",
                "search_provider": "google",
                "query_text": "tools to improve SaaS retention",
            }
        ],
        "prefer_fallback_rows": False,
    }
