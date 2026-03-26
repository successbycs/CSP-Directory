"""Pipeline orchestration with optional persistence hooks."""

from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from services.discovery import web_search
from services.discovery import discovery_store
from services.enrichment import site_explorer
from services.enrichment import vendor_fetcher
from services.extraction import llm_extractor
from services.extraction import merge_results
from services.extraction import vendor_intel
from services.extraction import vendor_profile_builder
from services.export import directory_dataset
from services.export import google_sheets
from services.export import search_visibility_report
from services.export import vendor_review_dataset
from services.extraction.vendor_intel import VendorIntelligence
from services.persistence import supabase_client
from services.persistence import run_store
from services.persistence import search_visibility_store
from services.pipeline import discovery_runner
from services.pipeline import enrichment_runner

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_RUNS_PATH = PROJECT_ROOT / "outputs" / "pipeline_runs.json"
CANDIDATE_REVIEW_PATH = PROJECT_ROOT / "outputs" / "candidate_review_dataset.json"

VendorCandidate = dict[str, str]
HomepagePayload = dict[str, str | int]
ExploredPages = dict[str, object]
SheetRow = dict[str, str]


def run_mvp_pipeline(
    query: str | list[str] | None,
    *,
    search_web_candidates_fn: Callable[[str | list[str] | None], list[dict[str, object]]] | None = None,
    fetch_vendor_homepage_fn: Callable[[VendorCandidate], HomepagePayload] | None = None,
    explore_vendor_site_fn: Callable[[HomepagePayload], ExploredPages] | None = None,
    extract_vendor_intelligence_fn: Callable[[dict[str, object]], VendorIntelligence] | None = None,
    extract_vendor_intelligence_llm_fn: Callable[[dict[str, object]], object | None] | None = None,
    merge_vendor_intelligence_fn: Callable[[VendorIntelligence, object | None], VendorIntelligence] | None = None,
    build_vendor_profile_fn: Callable[[VendorCandidate, ExploredPages, VendorIntelligence], VendorIntelligence]
    | None = None,
    vendor_intelligence_to_sheet_row_fn: Callable[[VendorIntelligence], SheetRow] | None = None,
    vendor_exists_fn: Callable[[str], bool] | None = None,
    upsert_vendor_result_fn: Callable[[VendorCandidate, HomepagePayload, VendorIntelligence], object]
    | None = None,
    run_discovery_phase_fn: Callable[..., tuple[list[dict[str, object]], list[VendorCandidate], int]] | None = None,
    run_enrichment_phase_fn: Callable[..., tuple[list[SheetRow], list[dict[str, object]], int, int]] | None = None,
) -> list[SheetRow]:
    """Run the MVP pipeline with optional persistence."""
    search_web_candidates_fn = search_web_candidates_fn or web_search.search_web_candidates
    fetch_vendor_homepage_fn = fetch_vendor_homepage_fn or vendor_fetcher.fetch_vendor_homepage
    explore_vendor_site_fn = explore_vendor_site_fn or site_explorer.explore_vendor_site
    extract_vendor_intelligence_fn = (
        extract_vendor_intelligence_fn or vendor_intel.extract_vendor_intelligence
    )
    extract_vendor_intelligence_llm_fn = (
        extract_vendor_intelligence_llm_fn or llm_extractor.extract_vendor_intelligence
    )
    merge_vendor_intelligence_fn = (
        merge_vendor_intelligence_fn or merge_results.merge_vendor_intelligence
    )
    build_vendor_profile_fn = build_vendor_profile_fn or vendor_profile_builder.build_vendor_profile
    vendor_intelligence_to_sheet_row_fn = (
        vendor_intelligence_to_sheet_row_fn
        or google_sheets.vendor_intelligence_to_sheet_row
    )
    run_discovery_phase_fn = run_discovery_phase_fn or discovery_runner.run_discovery_phase
    run_enrichment_phase_fn = run_enrichment_phase_fn or enrichment_runner.run_enrichment_phase

    if vendor_exists_fn is None and supabase_client.is_configured():
        if supabase_client.supports_export_ready_vendor_profiles():
            vendor_exists_fn = supabase_client.vendor_exists
        else:
            logger.warning(
                "Persistence schema is not export-ready, continuing without deduplication against existing vendors"
            )

    if upsert_vendor_result_fn is None and supabase_client.is_configured():
        upsert_vendor_result_fn = supabase_client.upsert_vendor_result

    logger.info("Starting MVP pipeline for query set: %s", _format_query_log(query))
    llm_extractor.start_pipeline_run()
    llm_extractor.log_runtime_configuration()
    run_started_at = datetime.now(timezone.utc)
    started_run_record = _build_run_record(query=query, started_at=run_started_at, run_status="started")
    _persist_run_record(started_run_record)
    try:
        try:
            candidate_records, queued_vendor_candidates, skipped_existing_count = run_discovery_phase_fn(
                query,
                fetch_candidate_records_fn=search_web_candidates_fn,
                vendor_exists_fn=vendor_exists_fn,
            )
        except Exception as error:
            if supabase_client.is_persistence_unavailable_error(error):
                logger.warning("Persistence unavailable, continuing without deduplication: %s", error)
                vendor_exists_fn = None
                upsert_vendor_result_fn = None
                candidate_records, queued_vendor_candidates, skipped_existing_count = run_discovery_phase_fn(
                    query,
                    fetch_candidate_records_fn=search_web_candidates_fn,
                    vendor_exists_fn=None,
                )
            else:
                raise

        _persist_candidate_records(candidate_records)

        logger.info(
            "Phase 1 discovery produced %s candidate domains and queued %s vendors for enrichment",
            len(candidate_records),
            len(queued_vendor_candidates),
        )

        # M48/cost-gate: annotate each candidate with whether expensive fetch (Playwright/Apify)
        # is needed. Vendors already sufficiently enriched in Supabase skip the expensive path.
        if supabase_client.is_configured():
            _annotate_expensive_fetch_gate(queued_vendor_candidates)

        vendor_rows, enrichment_results, llm_success_count, llm_fallback_count = run_enrichment_phase_fn(
            queued_vendor_candidates,
            fetch_vendor_homepage_fn=fetch_vendor_homepage_fn,
            explore_vendor_site_fn=explore_vendor_site_fn,
            extract_vendor_intelligence_fn=extract_vendor_intelligence_fn,
            extract_vendor_intelligence_llm_fn=extract_vendor_intelligence_llm_fn,
            merge_vendor_intelligence_fn=merge_vendor_intelligence_fn,
            build_vendor_profile_fn=build_vendor_profile_fn,
            vendor_intelligence_to_sheet_row_fn=vendor_intelligence_to_sheet_row_fn,
            upsert_vendor_result_fn=upsert_vendor_result_fn,
            drop_reason_fn=_drop_reason,
        )

        _apply_enrichment_statuses(candidate_records, enrichment_results)
        _persist_candidate_records(candidate_records)
        completed_run_record = _build_run_record(
            query=query,
            started_at=run_started_at,
            candidate_records=candidate_records,
            enrichment_results=enrichment_results,
            queued_count=len(queued_vendor_candidates),
            skipped_existing_count=skipped_existing_count,
            llm_success_count=llm_success_count,
            llm_fallback_count=llm_fallback_count,
            run_status=_derive_run_status(enrichment_results),
        )
        _persist_run_record(completed_run_record)
        _write_run_snapshot(completed_run_record)
        _write_candidate_review_snapshot(candidate_records)

        try:
            google_sheets.publish_ops_review_export(
                run_record=completed_run_record,
                candidate_records=candidate_records,
                enrichment_results=enrichment_results,
            )
        except Exception as error:
            logger.warning(
                "Google Sheets ops review export failed, continuing with local artifacts only: %s",
                error,
            )
        dataset = _export_directory_dataset(enrichment_results)
        review_dataset = _export_vendor_review_dataset(enrichment_results)
        _persist_search_visibility_queries(enrichment_results)
        search_visibility_snapshot = _export_search_visibility_artifacts(enrichment_results)
        search_visibility_metrics = search_visibility_snapshot.get("metrics") or {}

        logger.info(
            "LLM stage summary: successes=%s fallback_or_skipped=%s",
            llm_success_count,
            llm_fallback_count,
        )
        logger.info(
            "Pipeline completed with %s included vendor rows; skipped %s existing vendors; exported %s directory records and %s review rows",
            len(vendor_rows),
            skipped_existing_count,
            len(dataset),
            len(review_dataset),
        )
        logger.info(
            "Search visibility snapshot now covers %s buyer-role prompts, %s ranked results, and %s surfaced vendors",
            search_visibility_metrics.get("query_count", 0),
            search_visibility_metrics.get("ranking_count", 0),
            search_visibility_metrics.get("vendor_count", 0),
        )
        return vendor_rows
    except Exception as error:
        failed_run_record = _build_run_record(
            query=query,
            started_at=run_started_at,
            run_status="failed",
            error_summary=str(error),
        )
        _persist_run_record(failed_run_record)
        _write_run_snapshot(failed_run_record)
        raise


def _drop_reason(profile: VendorIntelligence | dict[str, object], llm_result: object | None) -> str:
    """Return a drop reason when a profile should not be persisted or exported."""
    llm_relevant = getattr(llm_result, "is_cs_relevant", None)
    if llm_relevant is False:
        return "llm_marked_non_cs_relevant"

    confidence = _profile_confidence(profile).lower()
    if confidence == "low":
        return "low_confidence"

    # M48: vendors with no ICP signal must not be included in the directory
    icp = profile.icp if isinstance(profile, VendorIntelligence) else profile.get("icp", [])
    if not icp:
        return "empty_icp"

    return ""


def _annotate_expensive_fetch_gate(vendor_candidates: list[dict[str, object]]) -> None:
    """Set skip_expensive_fetch=True on candidates already sufficiently enriched in Supabase.

    Vendors with all key fields populated (icp, lifecycle_stages, directory_category,
    integrations, pricing) skip Playwright and Apify — plain HTTP is enough for re-enrichment.
    """
    for vendor in vendor_candidates:
        website = str(vendor.get("website") or "")
        if not website:
            continue
        try:
            completeness = supabase_client.get_vendor_enrichment_completeness(website)
            if completeness["is_sufficiently_enriched"]:
                vendor["skip_expensive_fetch"] = True
                logger.info(
                    "Skipping expensive fetch for %s: all key fields already populated in Supabase",
                    website,
                )
        except Exception as error:
            logger.debug("Enrichment completeness check failed for %s: %s", website, error)


def _profile_confidence(profile: VendorIntelligence | dict[str, object]) -> str:
    if isinstance(profile, dict):
        return str(profile.get("confidence", ""))
    return profile.confidence


def _profile_name(profile: VendorIntelligence | dict[str, object]) -> str:
    if isinstance(profile, dict):
        return str(profile.get("vendor_name", ""))
    return profile.vendor_name


def _format_query_log(query: str | list[str] | None) -> str:
    """Format one or more discovery queries for logging."""
    if query is None:
        return "config default queries"
    if isinstance(query, str):
        return query
    return ", ".join(query)


def _count_page_payloads(explored_pages: ExploredPages) -> int:
    """Return the number of fetched page payloads in an explored page bundle."""
    page_count = 0
    for page_value in explored_pages.values():
        if isinstance(page_value, dict):
            page_count += 1
            continue
        if isinstance(page_value, list):
            page_count += sum(1 for item in page_value if isinstance(item, dict))
    return page_count


def _apply_enrichment_statuses(
    candidate_records: list[dict[str, object]],
    enrichment_results: list[dict[str, object]],
) -> None:
    """Update candidate record statuses from Phase 2 results."""
    result_by_domain = {
        str(result.get("candidate_domain", "")): result
        for result in enrichment_results
    }
    for candidate_record in candidate_records:
        candidate_domain = str(candidate_record.get("candidate_domain", ""))
        if candidate_domain in result_by_domain:
            result = result_by_domain[candidate_domain]
            candidate_status = _candidate_status_from_enrichment_status(str(result.get("status", "")))
            candidate_record["candidate_status"] = candidate_status
            candidate_record["status"] = candidate_status
            drop_reason = str(result.get("drop_reason", "")).strip()
            if drop_reason:
                candidate_record["drop_reason"] = drop_reason


def _persist_candidate_records(candidate_records: list[dict[str, object]]) -> None:
    """Persist candidate records when the discovery store is available."""
    if not candidate_records or not supabase_client.is_configured():
        return
    try:
        discovery_store.upsert_candidate_records(candidate_records)
    except Exception as error:
        if discovery_store.is_discovery_store_unavailable_error(error):
            logger.warning("Discovery candidate persistence unavailable, continuing without it: %s", error)
            return
        if supabase_client.is_persistence_unavailable_error(error):
            logger.warning("Persistence unavailable while storing discovery candidates: %s", error)
            return
        raise


def _build_run_record(
    *,
    query: str | list[str] | None,
    started_at: datetime,
    candidate_records: list[dict[str, object]] | None = None,
    enrichment_results: list[dict[str, object]] | None = None,
    queued_count: int | None = None,
    skipped_existing_count: int = 0,
    llm_success_count: int = 0,
    llm_fallback_count: int = 0,
    run_status: str = "completed",
    error_summary: str = "",
) -> dict[str, object]:
    """Build one normalized run record for persistence and local snapshots."""
    candidate_records = candidate_records or []
    enrichment_results = enrichment_results or []
    dropped_count = sum(
        1
        for result in enrichment_results
        if str(result.get("status", "")).startswith("dropped_")
    )
    enriched_count = sum(1 for result in enrichment_results if str(result.get("status", "")) == "enriched")
    return {
        "run_id": started_at.strftime("%Y%m%d%H%M%S"),
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "queries_executed": _format_query_log(query),
        "candidate_count": len(candidate_records),
        "queued_count": queued_count if queued_count is not None else sum(
            1 for record in candidate_records if str(record.get("candidate_status")) == "queued_for_enrichment"
        ),
        "skipped_existing_count": skipped_existing_count,
        "enriched_count": enriched_count,
        "dropped_count": dropped_count,
        "llm_success_count": llm_success_count,
        "llm_fallback_count": llm_fallback_count,
        "run_status": run_status,
        "error_summary": error_summary,
    }


def _write_run_snapshot(run_record: dict[str, object]) -> None:
    """Write the newest run snapshot to the local JSON fallback artifact."""
    existing_runs = _read_pipeline_run_snapshots()
    updated_runs = [run_record, *existing_runs][:100]
    PIPELINE_RUNS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PIPELINE_RUNS_PATH.write_text(json.dumps(updated_runs, indent=2), encoding="utf-8")


def _read_pipeline_run_snapshots() -> list[dict[str, object]]:
    if not PIPELINE_RUNS_PATH.exists():
        return []
    try:
        payload = json.loads(PIPELINE_RUNS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _persist_run_record(run_record: dict[str, object]) -> None:
    """Persist a run record when the run store is available."""
    if not supabase_client.is_configured():
        return
    try:
        run_store.upsert_run_record(run_record)
    except Exception as error:
        if run_store.is_run_store_unavailable_error(error) or supabase_client.is_persistence_unavailable_error(error):
            logger.warning("Pipeline run persistence unavailable, continuing with local run snapshots only: %s", error)
            return
        raise


def _write_candidate_review_snapshot(candidate_records: list[dict[str, object]]) -> None:
    """Write candidate review rows to a local JSON artifact for admin fallback use."""
    CANDIDATE_REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    CANDIDATE_REVIEW_PATH.write_text(json.dumps(candidate_records, indent=2), encoding="utf-8")


def _derive_run_status(enrichment_results: list[dict[str, object]]) -> str:
    statuses = [str(result.get("status", "")) for result in enrichment_results]
    if any(status.startswith("failed_") for status in statuses):
        return "completed_with_warnings"
    if any(status.startswith("dropped_") for status in statuses):
        return "completed_with_warnings"
    return "completed"


def _candidate_status_from_enrichment_status(status: str) -> str:
    if status == "enriched":
        return "enriched"
    if status.startswith("dropped_"):
        return "dropped"
    if status.startswith("failed_"):
        return "failed"
    return status or "failed"


def _export_directory_dataset(enrichment_results: list[dict[str, object]]) -> list[dict[str, object]]:
    """Export the directory dataset from Supabase or current run profiles."""
    fallback_profiles = _current_run_export_profiles(enrichment_results)
    if fallback_profiles:
        try:
            dataset = directory_dataset.export_directory_dataset(
                fallback_profiles=fallback_profiles,
                prefer_fallback_profiles=True,
            )
        except Exception as error:
            logger.warning("Directory dataset export from current run profiles failed: %s", error)
            return []
        logger.info("Exported %s directory dataset row(s) from current run profiles", len(dataset))
        return dataset
    try:
        dataset = directory_dataset.export_directory_dataset(fallback_profiles=fallback_profiles)
        if not dataset and fallback_profiles:
            logger.warning(
                "Directory dataset export returned no includable Supabase rows, falling back to current run profiles"
            )
            dataset = directory_dataset.export_directory_dataset(
                fallback_profiles=fallback_profiles,
                prefer_fallback_profiles=True,
            )
    except Exception as error:
        logger.warning("Directory dataset export from Supabase unavailable, falling back to current run profiles: %s", error)
        try:
            dataset = directory_dataset.export_directory_dataset(
                fallback_profiles=fallback_profiles,
                prefer_fallback_profiles=True,
            )
        except Exception as fallback_error:
            logger.warning("Directory dataset export unavailable: %s", fallback_error)
            return []
    logger.info("Exported %s directory dataset row(s)", len(dataset))
    return dataset


def _export_vendor_review_dataset(enrichment_results: list[dict[str, object]]) -> list[dict[str, object]]:
    """Export a slim vendor review dataset and HTML report."""
    fallback_profiles = _current_run_export_profiles(enrichment_results)
    if fallback_profiles:
        try:
            dataset = vendor_review_dataset.export_vendor_review_artifacts(
                fallback_profiles=fallback_profiles,
                prefer_fallback_profiles=True,
            )
        except Exception as error:
            logger.warning("Vendor review export from current run profiles failed: %s", error)
            return []
        logger.info("Exported %s vendor review row(s) from current run profiles", len(dataset))
        return dataset
    try:
        dataset = vendor_review_dataset.export_vendor_review_artifacts(fallback_profiles=fallback_profiles)
        if _review_dataset_needs_fallback(dataset, fallback_profiles=fallback_profiles):
            logger.warning(
                "Vendor review export returned stale Supabase rows, falling back to current run profiles"
            )
            dataset = vendor_review_dataset.export_vendor_review_artifacts(
                fallback_profiles=fallback_profiles,
                prefer_fallback_profiles=True,
            )
    except Exception as error:
        logger.warning("Vendor review export from Supabase unavailable, falling back to current run profiles: %s", error)
        try:
            dataset = vendor_review_dataset.export_vendor_review_artifacts(
                fallback_profiles=fallback_profiles,
                prefer_fallback_profiles=True,
            )
        except Exception as fallback_error:
            logger.warning("Vendor review export unavailable: %s", fallback_error)
            return []
    logger.info("Exported %s vendor review row(s)", len(dataset))
    return dataset


def _persist_search_visibility_queries(enrichment_results: list[dict[str, object]]) -> list[dict[str, object]]:
    """Persist buyer-role Google and GEO query prompts for current-run vendor profiles."""
    fallback_profiles = _current_run_export_profiles(enrichment_results)
    if not fallback_profiles or not supabase_client.is_configured():
        return []

    try:
        rows = search_visibility_store.upsert_buyer_search_queries_from_vendor_profiles(fallback_profiles)
    except Exception as error:
        if (
            search_visibility_store.is_search_visibility_store_unavailable_error(error)
            or supabase_client.is_persistence_unavailable_error(error)
        ):
            logger.warning(
                "Search visibility query persistence unavailable, continuing with local report fallbacks only: %s",
                error,
            )
            return []
        raise

    logger.info("Persisted %s buyer-role search query row(s)", len(rows))
    return rows


def _export_search_visibility_artifacts(enrichment_results: list[dict[str, object]]) -> dict[str, object]:
    """Export role-based search visibility JSON and HTML artifacts."""
    fallback_profiles = _current_run_export_profiles(enrichment_results)
    fallback_query_rows = search_visibility_store.build_buyer_search_query_rows(fallback_profiles)

    try:
        report = search_visibility_report.export_search_visibility_artifacts(
            fallback_query_rows=fallback_query_rows,
        )
    except Exception as error:
        if not fallback_query_rows:
            logger.warning("Search visibility export unavailable: %s", error)
            return {"metrics": {}, "role_query_rankings": [], "vendor_visibility_summary": []}
        logger.warning(
            "Search visibility export from canonical data failed, falling back to current-run buyer-role prompts: %s",
            error,
        )
        try:
            report = search_visibility_report.export_search_visibility_artifacts(
                fallback_query_rows=fallback_query_rows,
                prefer_fallback_rows=True,
            )
        except Exception as fallback_error:
            logger.warning("Search visibility export unavailable: %s", fallback_error)
            return {"metrics": {}, "role_query_rankings": [], "vendor_visibility_summary": []}

    metrics = report.get("metrics") or {}
    logger.info(
        "Exported search visibility artifacts with %s buyer-role prompts, %s ranked results, and %s surfaced vendors",
        metrics.get("query_count", 0),
        metrics.get("ranking_count", 0),
        metrics.get("vendor_count", 0),
    )
    return report


def _current_run_export_profiles(enrichment_results: list[dict[str, object]]) -> list[VendorIntelligence]:
    """Return current-run profiles that actually survived enrichment."""
    return [
        result["profile"]
        for result in enrichment_results
        if not str(result.get("status", "")).strip().startswith(("dropped_", "failed_"))
        and isinstance(result.get("profile"), VendorIntelligence)
    ]


def _review_dataset_needs_fallback(
    dataset: list[dict[str, object]],
    *,
    fallback_profiles: list[VendorIntelligence],
) -> bool:
    """Return True when the persisted review dataset is empty or lacks review signal."""
    if not fallback_profiles:
        return False
    if not dataset:
        return True

    def has_review_signal(row: dict[str, object]) -> bool:
        return any(
            (
                str(row.get("confidence") or "").strip(),
                str(row.get("directory_fit") or "").strip(),
                str(row.get("directory_category") or "").strip(),
                row.get("include_in_directory") is not None,
            )
        )

    return not any(has_review_signal(row) for row in dataset)
