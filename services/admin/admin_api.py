"""Thin admin API for ops visibility and lead-capture operations."""

from __future__ import annotations

import argparse
import json
import logging
import mimetypes
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

from dotenv import load_dotenv

from services.admin import admin_actions
from services.admin import pipeline_control
from services.config.load_config import load_pipeline_config
from services.discovery import discovery_store
from services.extraction import vendor_intel
from services.export import directory_dataset as directory_dataset_export
from services.export import search_visibility_report
from services import lead_capture_notifications
from services.persistence import lead_capture_store
from services.persistence import search_visibility_store
from services.persistence import supabase_client
from services.persistence import run_store

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_RESULTS_PATH = PROJECT_ROOT / "outputs" / "pipeline_runs.json"
DEFAULT_CANDIDATE_RESULTS_PATH = PROJECT_ROOT / "outputs" / "candidate_review_dataset.json"
DEFAULT_VENDOR_RESULTS_PATH = PROJECT_ROOT / "outputs" / "vendor_review_dataset.json"
DEFAULT_SEARCH_VISIBILITY_RESULTS_PATH = PROJECT_ROOT / "outputs" / "search_visibility_report.json"
WEBSITE_ROOT = PROJECT_ROOT / "docs" / "website"
logger = logging.getLogger(__name__)


def build_admin_app(
    *,
    list_candidates_fn: Callable[[], list[dict[str, Any]]] | None = None,
    list_vendors_fn: Callable[[], list[dict[str, Any]]] | None = None,
    list_runs_fn: Callable[[], list[dict[str, Any]]] | None = None,
    list_search_visibility_fn: Callable[[], dict[str, Any]] | None = None,
    list_enrichment_metrics_fn: Callable[[], dict[str, Any]] | None = None,
    list_discovery_queries_fn: Callable[[], dict[str, Any]] | None = None,
    list_pipeline_runners_fn: Callable[[], dict[str, Any]] | None = None,
    list_n8n_integrations_fn: Callable[[], dict[str, Any]] | None = None,
    list_integration_catalog_fn: Callable[[], dict[str, Any]] | None = None,
    sync_integration_catalog_fn: Callable[[], dict[str, Any]] | None = None,
    list_pipelines_fn: Callable[[], dict[str, Any]] | None = None,
    trigger_pipeline_fn: Callable[[str], dict[str, Any]] | None = None,
    list_leads_fn: Callable[[], dict[str, Any]] | None = None,
    create_lead_fn: Callable[[dict[str, str]], dict[str, Any]] | None = None,
    notify_lead_capture_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    update_lead_follow_up_fn: Callable[..., dict[str, Any]] | None = None,
    include_vendor_fn: Callable[[str], dict[str, Any]] | None = None,
    exclude_vendor_fn: Callable[[str], dict[str, Any]] | None = None,
    rerun_vendor_enrichment_fn: Callable[[str], dict[str, Any]] | None = None,
    publish_directory_fn: Callable[[], dict[str, Any]] | None = None,
    enrich_write_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
):
    """Return a small WSGI app exposing admin JSON endpoints and public capture intake."""
    list_candidates_fn = list_candidates_fn or list_candidate_records
    list_vendors_fn = list_vendors_fn or list_vendor_records
    list_runs_fn = list_runs_fn or list_run_records
    list_search_visibility_fn = list_search_visibility_fn or list_search_visibility_data
    list_enrichment_metrics_fn = list_enrichment_metrics_fn or list_enrichment_metrics
    list_discovery_queries_fn = list_discovery_queries_fn or list_discovery_queries
    list_pipeline_runners_fn = list_pipeline_runners_fn or list_pipeline_runners
    list_n8n_integrations_fn = list_n8n_integrations_fn or list_n8n_integrations
    list_integration_catalog_fn = list_integration_catalog_fn or list_integration_catalog
    sync_integration_catalog_fn = sync_integration_catalog_fn or sync_integration_catalog
    list_pipelines_fn = list_pipelines_fn or pipeline_control.list_pipeline_controls
    trigger_pipeline_fn = trigger_pipeline_fn or pipeline_control.trigger_pipeline_run
    list_leads_fn = list_leads_fn or list_lead_capture_data
    create_lead_fn = create_lead_fn or lead_capture_store.create_lead_capture
    notify_lead_capture_fn = notify_lead_capture_fn or _notify_lead_capture
    update_lead_follow_up_fn = update_lead_follow_up_fn or lead_capture_store.update_lead_follow_up
    include_vendor_fn = include_vendor_fn or admin_actions.include_vendor
    exclude_vendor_fn = exclude_vendor_fn or admin_actions.exclude_vendor
    rerun_vendor_enrichment_fn = rerun_vendor_enrichment_fn or admin_actions.rerun_vendor_enrichment
    publish_directory_fn = publish_directory_fn or _run_publish_directory
    enrich_write_fn = enrich_write_fn or _run_enrich_write

    def app(environ, start_response):
        path = environ.get("PATH_INFO", "")
        query_params = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=False)
        method = environ.get("REQUEST_METHOD", "GET").upper()

        if method == "OPTIONS":
            return _json_response(start_response, {"ok": True})

        if method == "GET" and path == "/admin/candidates":
            return _safe_items_response(start_response, list_candidates_fn, label="candidates")
        if method == "GET" and path == "/admin/vendors":
            return _safe_items_response(start_response, list_vendors_fn, label="vendors")
        if method == "GET" and path == "/admin/runs":
            limit = _query_limit(query_params)
            return _safe_items_response(
                start_response,
                lambda: list_runs_fn()[:limit],
                label="runs",
            )
        if method == "GET" and path == "/admin/search-visibility":
            return _safe_payload_response(
                start_response,
                list_search_visibility_fn,
                label="search_visibility",
            )
        if method == "GET" and path == "/admin/enrichment-metrics":
            return _safe_payload_response(
                start_response,
                list_enrichment_metrics_fn,
                label="enrichment_metrics",
            )
        if method == "GET" and path == "/admin/discovery-queries":
            return _safe_payload_response(
                start_response,
                list_discovery_queries_fn,
                label="discovery_queries",
            )
        if method == "GET" and path == "/admin/pipeline-runners":
            return _safe_payload_response(
                start_response,
                list_pipeline_runners_fn,
                label="pipeline_runners",
            )
        if method == "GET" and path == "/admin/n8n-integrations":
            return _safe_payload_response(
                start_response,
                list_n8n_integrations_fn,
                label="n8n_integrations",
            )
        if method == "GET" and path == "/admin/integration-catalog":
            return _safe_payload_response(
                start_response,
                list_integration_catalog_fn,
                label="integration_catalog",
            )
        if method == "POST" and path == "/admin/integration-catalog/sync":
            return _safe_payload_response(
                start_response,
                sync_integration_catalog_fn,
                label="integration_catalog_sync",
            )
        if method == "GET" and path == "/admin/pipelines":
            return _safe_payload_response(start_response, list_pipelines_fn, label="pipelines")
        if method == "GET" and path == "/admin/leads":
            return _safe_payload_response(start_response, list_leads_fn, label="leads")
        if method == "POST" and path == "/api/lead-capture":
            payload = _parse_action_payload(environ)
            return _lead_capture_response(start_response, create_lead_fn, notify_lead_capture_fn, payload)
        if method == "POST" and path == "/admin/vendor/include":
            payload = _parse_action_payload(environ)
            return _action_response(start_response, include_vendor_fn, payload)
        if method == "POST" and path == "/admin/vendor/exclude":
            payload = _parse_action_payload(environ)
            return _action_response(start_response, exclude_vendor_fn, payload)
        if method == "POST" and path == "/admin/vendor/rerun-enrichment":
            payload = _parse_action_payload(environ)
            return _action_response(start_response, rerun_vendor_enrichment_fn, payload)
        if method == "GET" and path == "/admin/pipeline-log":
            return _pipeline_log_response(start_response)
        if method == "POST" and path == "/admin/publish":
            return _publish_response(start_response, publish_directory_fn)
        if method == "POST" and path == "/admin/enrich-write":
            payload = _parse_enrich_write_payload(environ)
            return _enrich_write_response(start_response, enrich_write_fn, payload)
        if method == "POST" and path == "/admin/lead/follow-up":
            payload = _parse_action_payload(environ)
            return _lead_follow_up_response(start_response, update_lead_follow_up_fn, payload)
        if method == "POST" and path == "/admin/pipelines/run":
            payload = _parse_action_payload(environ)
            return _pipeline_run_response(start_response, trigger_pipeline_fn, payload)
        if method == "POST" and path == "/admin/ops/store-crawl-result":
            payload = _parse_enrich_write_payload(environ)
            return _store_crawl_result_response(start_response, payload)
        if method == "POST" and path == "/admin/ops/store-pages":
            payload = _parse_enrich_write_payload(environ)
            return _store_pages_response(start_response, payload)
        if method == "GET" and path == "/admin/ops/field-coverage":
            return _field_coverage_response(start_response, query_params)
        if method == "GET":
            static_response = _static_response(path)
            if static_response is not None:
                status, headers, body = static_response
                start_response(status, headers)
                return [body]

        return _json_response(start_response, {"error": "not_found"}, status="404 Not Found")

    return app


def read_pipeline_run_results(runs_path: Path | None = None) -> list[dict[str, Any]]:
    """Read stored pipeline run snapshots for admin visibility."""
    runs_path = runs_path or DEFAULT_RUN_RESULTS_PATH
    if not runs_path.exists():
        return []
    try:
        payload = json.loads(runs_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def read_candidate_review_results(results_path: Path | None = None) -> list[dict[str, Any]]:
    """Read local candidate review rows for admin fallback visibility."""
    return _read_json_items(results_path or DEFAULT_CANDIDATE_RESULTS_PATH)


def read_vendor_review_results(results_path: Path | None = None) -> list[dict[str, Any]]:
    """Read local vendor review rows for admin fallback visibility."""
    return _read_json_items(results_path or DEFAULT_VENDOR_RESULTS_PATH)


def read_search_visibility_results(results_path: Path | None = None) -> dict[str, Any]:
    """Read local search visibility report output for admin fallback visibility."""
    results_path = results_path or DEFAULT_SEARCH_VISIBILITY_RESULTS_PATH
    if not results_path.exists():
        return {"metrics": {}, "role_query_rankings": [], "vendor_visibility_summary": []}
    try:
        payload = json.loads(results_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"metrics": {}, "role_query_rankings": [], "vendor_visibility_summary": []}
    if not isinstance(payload, dict):
        return {"metrics": {}, "role_query_rankings": [], "vendor_visibility_summary": []}
    payload.setdefault("metrics", {})
    payload.setdefault("role_query_rankings", [])
    payload.setdefault("vendor_visibility_summary", [])
    return payload


def list_candidate_records(*, limit: int = 200) -> list[dict[str, Any]]:
    """Return discovery candidates, falling back to local review output when needed."""
    if supabase_client.is_configured():
        try:
            return discovery_store.list_candidate_records(limit=limit)
        except Exception as error:
            if discovery_store.is_discovery_store_unavailable_error(error) or supabase_client.is_persistence_unavailable_error(error):
                logger.warning("Discovery candidate persistence unavailable, falling back to local candidate review output: %s", error)
            else:
                logger.warning("Discovery candidate load failed, falling back to local candidate review output: %s", error)
    return read_candidate_review_results()[:limit]


def list_vendor_records(*, limit: int = 200) -> list[dict[str, Any]]:
    """Return enriched vendors, falling back to local review output when needed."""
    if supabase_client.is_configured():
        try:
            return supabase_client.list_vendor_profiles(limit=limit)
        except Exception as error:
            if supabase_client.is_persistence_unavailable_error(error):
                logger.warning("Vendor persistence unavailable, falling back to local vendor review output: %s", error)
            else:
                logger.warning("Vendor load failed, falling back to local vendor review output: %s", error)
    return read_vendor_review_results()[:limit]


def list_run_records(*, limit: int = 100) -> list[dict[str, Any]]:
    """Return persisted run records, falling back to local JSON snapshots."""
    if supabase_client.is_configured():
        try:
            return run_store.list_run_records(limit=limit)
        except Exception as error:
            if run_store.is_run_store_unavailable_error(error) or supabase_client.is_persistence_unavailable_error(error):
                logger.warning("Pipeline run persistence unavailable, falling back to local run snapshots: %s", error)
            else:
                raise
    return read_pipeline_run_results()[:limit]


def list_search_visibility_data() -> dict[str, Any]:
    """Return search-visibility report data, falling back to local artifacts when needed."""
    if supabase_client.is_configured():
        try:
            return search_visibility_report.export_search_visibility_artifacts()
        except Exception as error:
            if (
                search_visibility_store.is_search_visibility_store_unavailable_error(error)
                or supabase_client.is_persistence_unavailable_error(error)
            ):
                logger.warning(
                    "Search visibility persistence unavailable, falling back to local report output: %s",
                    error,
                )
            else:
                logger.warning("Search visibility report build failed, falling back to local report output: %s", error)
    return read_search_visibility_results()


def list_enrichment_metrics(*, limit: int = 2000) -> dict[str, Any]:
    """Return enrichment execution metrics aggregated across vendor rows."""
    rows: list[dict[str, Any]] = []
    if supabase_client.is_configured():
        try:
            rows = supabase_client.list_vendor_profiles(limit=limit)
        except Exception as error:
            if supabase_client.is_persistence_unavailable_error(error):
                logger.warning("Enrichment metrics unavailable from persistence, using local fallback: %s", error)
            else:
                logger.warning("Enrichment metrics load failed, using local fallback: %s", error)
            rows = read_vendor_review_results()[:limit]
    else:
        rows = read_vendor_review_results()[:limit]

    pipeline_counts: dict[str, int] = {}
    total_events = 0
    vendors_with_enrichment = 0
    latest_enriched_at = ""

    for row in rows:
        if not isinstance(row, dict):
            continue
        row_count = row.get("enrichment_count")
        try:
            numeric_count = int(row_count) if row_count is not None else 0
        except (TypeError, ValueError):
            numeric_count = 0
        if numeric_count > 0:
            vendors_with_enrichment += 1

        row_latest = str(row.get("last_enriched_at") or "")
        if row_latest > latest_enriched_at:
            latest_enriched_at = row_latest

        per_pipeline = row.get("enrichment_pipeline_counts")
        if not isinstance(per_pipeline, dict):
            continue
        for raw_pipeline, raw_count in per_pipeline.items():
            pipeline = _normalize_pipeline_name(raw_pipeline)
            try:
                count = max(int(raw_count), 0)
            except (TypeError, ValueError):
                continue
            pipeline_counts[pipeline] = pipeline_counts.get(pipeline, 0) + count
            total_events += count

    if total_events == 0:
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                total_events += max(int(row.get("enrichment_count") or 0), 0)
            except (TypeError, ValueError):
                continue

    ordered_pipeline_counts = dict(sorted(pipeline_counts.items(), key=lambda item: (-item[1], item[0])))
    return {
        "metrics": {
            "vendor_count": len(rows),
            "vendors_with_enrichment": vendors_with_enrichment,
            "total_enrichment_events": total_events,
            "latest_enriched_at": latest_enriched_at,
            "pipeline_count": len(ordered_pipeline_counts),
        },
        "pipeline_counts": ordered_pipeline_counts,
    }


def list_discovery_queries() -> dict[str, Any]:
    """Return the configured search query set passed to Apify Google Search discovery."""
    discovery = load_pipeline_config().discovery
    queries = list(discovery.queries)
    return {
        "items": [
            {
                "position": index + 1,
                "query": query,
            }
            for index, query in enumerate(queries)
        ],
        "source_engine": discovery.source_engine,
        "actor_id": discovery.actor_id,
        "max_pages_per_query": discovery.max_pages_per_query,
        "results_per_page": discovery.results_per_page,
        "query_count": len(queries),
    }


def list_pipeline_runners() -> dict[str, Any]:
    """Return read-only runner stages and key config used in discovery/enrichment."""
    config = load_pipeline_config()
    discovery = config.discovery
    enrichment = config.enrichment
    llm = config.llm

    items = [
        {
            "step_order": 1,
            "step_id": "discovery_apify_google_search",
            "phase": "discovery",
            "runner": "Apify Google Search",
            "details": "Runs configured query set to produce vendor candidates.",
            "config": {
                "source_engine": discovery.source_engine,
                "actor_id": discovery.actor_id,
                "query_count": len(discovery.queries),
                "max_pages_per_query": discovery.max_pages_per_query,
                "results_per_page": discovery.results_per_page,
                "max_candidate_domains_per_run": discovery.max_candidate_domains_per_run,
            },
        },
        {
            "step_order": 2,
            "step_id": "enrichment_homepage_fetch",
            "phase": "enrichment",
            "runner": "Homepage fetch",
            "details": "Fetches vendor homepage before deeper crawl/exploration.",
            "config": {
                "request_timeout_seconds": enrichment.request_timeout_seconds,
                "external_fetch_backend": enrichment.external_fetch_backend,
                "external_fetch_actor_id": enrichment.external_fetch_actor_id,
                "external_fetch_max_pages": enrichment.external_fetch_max_pages,
            },
        },
        {
            "step_order": 3,
            "step_id": "enrichment_site_exploration",
            "phase": "enrichment",
            "runner": "Apify/Web site crawl",
            "details": "Explores high-signal pages for each vendor.",
            "config": {
                "discovery_mode": enrichment.discovery_mode,
                "max_crawl_depth": enrichment.max_crawl_depth,
                "max_non_homepage_pages": enrichment.max_non_homepage_pages,
                "max_pages_total": enrichment.max_pages_total,
            },
        },
        {
            "step_order": 4,
            "step_id": "extraction_deterministic",
            "phase": "enrichment",
            "runner": "Deterministic extraction",
            "details": "Rule-based extraction from fetched pages.",
            "config": {},
        },
        {
            "step_order": 5,
            "step_id": "extraction_llm",
            "phase": "enrichment",
            "runner": "LLM extraction",
            "details": "Optional semantic extraction/augmentation.",
            "config": {
                "enabled": llm.enabled,
                "model": llm.model,
                "request_timeout_seconds": llm.request_timeout_seconds,
                "max_page_text_chars": llm.max_page_text_chars,
                "max_site_text_chars": llm.max_site_text_chars,
            },
        },
    ]

    return {"items": items}


def list_n8n_integrations() -> dict[str, Any]:
    """Return read-only metadata for n8n workflow integrations in-repo."""
    workflow_dir = PROJECT_ROOT / "n8n" / "workflows"
    workflow_files = sorted(workflow_dir.glob("*.json"))
    items: list[dict[str, Any]] = []

    for workflow_path in workflow_files:
        try:
            payload = json.loads(workflow_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue

        nodes = payload.get("nodes")
        node_list = nodes if isinstance(nodes, list) else []

        webhook_path = ""
        webhook_id = ""
        for node in node_list:
            if not isinstance(node, dict):
                continue
            if str(node.get("type", "")).strip() != "n8n-nodes-base.webhook":
                continue
            params = node.get("parameters")
            if isinstance(params, dict):
                webhook_path = str(params.get("path") or "").strip()
            webhook_id = str(node.get("webhookId") or "").strip()
            if webhook_path or webhook_id:
                break

        items.append(
            {
                "workflow_name": str(payload.get("name") or workflow_path.stem),
                "file_name": workflow_path.name,
                "webhook_path": webhook_path,
                "webhook_id": webhook_id,
                "description": str((payload.get("meta") or {}).get("description") or "").strip() if isinstance(payload.get("meta"), dict) else "",
                "node_count": len(node_list),
                "active": bool(payload.get("active", False)),
            }
        )

    return {
        "items": items,
        "workflow_count": len(items),
        "source_directory": str(workflow_dir.relative_to(PROJECT_ROOT)),
    }


def list_integration_catalog() -> dict[str, Any]:
    """Return the canonical integration catalog used for vendor extraction/mapping."""
    items = [
        {
            "integration_name": canonical_name,
            "category": category,
            "aliases": list(aliases),
        }
        for canonical_name, category, aliases in vendor_intel.INTEGRATION_BRAND_RULES
    ]
    categories = sorted({str(item["category"]) for item in items})
    return {
        "items": items,
        "integration_count": len(items),
        "category_count": len(categories),
        "categories": categories,
        "source": "services/extraction/vendor_intel.py::INTEGRATION_BRAND_RULES",
        "source_note": "Catalog includes integrations seeded from n8n node catalog and CSP-focused normalization rules.",
    }


def sync_integration_catalog() -> dict[str, Any]:
    """Sync the repo's canonical integration rules into Supabase integration_catalog."""
    return supabase_client.sync_default_integration_catalog()


def list_lead_capture_data(*, limit: int = 200) -> dict[str, Any]:
    """Return lead-capture dashboard data with fallback-safe persistence access."""
    return lead_capture_store.export_lead_capture_dashboard(limit=limit)


def main() -> int:
    """Run the admin API with the standard library server."""
    parser = argparse.ArgumentParser(description="Run the lightweight admin API and static dashboard server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    load_dotenv(PROJECT_ROOT / ".env")
    app = build_admin_app()
    with make_server(args.host, args.port, app) as server:
        print(f"Admin API available at http://{args.host}:{args.port}")
        server.serve_forever()
    return 0


def _json_response(start_response, payload: dict[str, Any], *, status: str = "200 OK"):
    body = json.dumps(payload, indent=2).encode("utf-8")
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
        ("Access-Control-Allow-Origin", "*"),
        ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"),
        ("Access-Control-Allow-Headers", "Content-Type"),
    ]
    start_response(status, headers)
    return [body]


def _safe_items_response(start_response, fetch_fn: Callable[[], list[dict[str, Any]]], *, label: str):
    try:
        items = fetch_fn()
    except Exception as error:  # pragma: no cover - defensive API surface
        logger.exception("Admin API failed to load %s", label)
        return _json_response(
            start_response,
            {"items": [], "error": f"{label}_unavailable", "detail": str(error)},
        )
    return _json_response(start_response, {"items": items})


def _safe_payload_response(start_response, fetch_fn: Callable[[], dict[str, Any]], *, label: str):
    try:
        payload = fetch_fn()
    except Exception as error:  # pragma: no cover - defensive API surface
        logger.exception("Admin API failed to load %s", label)
        return _json_response(
            start_response,
            {"error": f"{label}_unavailable", "detail": str(error)},
        )
    return _json_response(start_response, payload if isinstance(payload, dict) else {})


def _query_limit(query_params: dict[str, list[str]]) -> int:
    raw_value = query_params.get("limit", ["50"])[0]
    try:
        parsed = int(raw_value)
    except ValueError:
        return 50
    return max(1, min(parsed, 500))


def _read_json_items(results_path: Path) -> list[dict[str, Any]]:
    if not results_path.exists():
        return []
    try:
        payload = json.loads(results_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _parse_action_payload(environ) -> dict[str, str]:
    content_length = environ.get("CONTENT_LENGTH", "0") or "0"
    try:
        body_length = int(content_length)
    except ValueError:
        body_length = 0
    raw_body = environ["wsgi.input"].read(body_length) if body_length > 0 else b""
    if not raw_body:
        return {}
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items() if value is not None}


def _action_response(start_response, action_fn: Callable[[str], dict[str, Any]], payload: dict[str, str]):
    vendor_lookup = payload.get("vendor", "").strip() or payload.get("website", "").strip()
    if not vendor_lookup:
        return _json_response(start_response, {"ok": False, "error": "vendor_lookup_required"}, status="400 Bad Request")
    try:
        result = action_fn(vendor_lookup)
    except LookupError as error:
        return _json_response(start_response, {"ok": False, "error": str(error)}, status="404 Not Found")
    except Exception as error:  # pragma: no cover - defensive error surface
        logger.exception("Admin action failed")
        return _json_response(start_response, {"ok": False, "error": str(error)}, status="500 Internal Server Error")
    return _json_response(start_response, result)


def _lead_capture_response(
    start_response,
    create_lead_fn: Callable[[dict[str, str]], dict[str, Any]],
    notify_lead_capture_fn: Callable[[dict[str, Any]], dict[str, Any]],
    payload: dict[str, str],
):
    try:
        result = create_lead_fn(payload)
    except ValueError as error:
        return _json_response(start_response, {"ok": False, "error": str(error)}, status="400 Bad Request")
    except Exception as error:  # pragma: no cover - defensive error surface
        logger.exception("Lead capture failed")
        return _json_response(start_response, {"ok": False, "error": str(error)}, status="500 Internal Server Error")
    notification: dict[str, Any] | None = None
    try:
        notification = notify_lead_capture_fn(result)
    except Exception as error:  # pragma: no cover - defensive error surface
        logger.warning("Lead capture notification failed: %s", error)
        notification = {"triggered": False, "error": str(error)}
    return _json_response(
        start_response,
        {
            "ok": True,
            "lead": result,
            "notification": notification,
            "thank_you_message": (notification or {}).get("thank_you_message"),
            "booking_url": (notification or {}).get("booking_url"),
        },
    )


def _notify_lead_capture(lead_row: dict[str, Any]) -> dict[str, Any]:
    return lead_capture_notifications.trigger_lead_capture_notification(lead_row)


def _lead_follow_up_response(
    start_response,
    update_lead_follow_up_fn: Callable[..., dict[str, Any]],
    payload: dict[str, str],
):
    lead_id = payload.get("lead_id", "").strip()
    if not lead_id:
        return _json_response(start_response, {"ok": False, "error": "lead_id_required"}, status="400 Bad Request")
    try:
        result = update_lead_follow_up_fn(
            lead_id,
            follow_up_status=payload.get("follow_up_status"),
            follow_up_owner=payload.get("follow_up_owner"),
            follow_up_notes=payload.get("follow_up_notes"),
        )
    except ValueError as error:
        return _json_response(start_response, {"ok": False, "error": str(error)}, status="400 Bad Request")
    except LookupError as error:
        return _json_response(start_response, {"ok": False, "error": str(error)}, status="404 Not Found")
    except Exception as error:  # pragma: no cover - defensive error surface
        logger.exception("Lead follow-up update failed")
        return _json_response(start_response, {"ok": False, "error": str(error)}, status="500 Internal Server Error")
    return _json_response(start_response, {"ok": True, "lead": result})


def _pipeline_run_response(
    start_response,
    trigger_pipeline_fn: Callable[[str], dict[str, Any]],
    payload: dict[str, str],
):
    pipeline_id = payload.get("pipeline_id", "").strip()
    if not pipeline_id:
        return _json_response(start_response, {"ok": False, "error": "pipeline_id_required"}, status="400 Bad Request")
    try:
        result = trigger_pipeline_fn(pipeline_id)
    except ValueError as error:
        return _json_response(start_response, {"ok": False, "error": str(error)}, status="400 Bad Request")
    except Exception as error:  # pragma: no cover - defensive error surface
        logger.exception("Pipeline run trigger failed")
        return _json_response(start_response, {"ok": False, "error": str(error)}, status="500 Internal Server Error")
    status = "200 OK" if result.get("ok", True) else "409 Conflict"
    return _json_response(start_response, result, status=status)


def _run_publish_directory() -> dict[str, Any]:
    """Export directory_dataset.json and optionally push to GitHub."""
    import os

    dataset = directory_dataset_export.export_directory_dataset()
    output_path = directory_dataset_export.DEFAULT_DIRECTORY_DATASET_PATH
    # Keep the static site dataset in sync so a git push deploys updated data
    web_data_path = PROJECT_ROOT / "docs" / "website" / "data" / "directory_dataset.json"
    directory_dataset_export.write_directory_dataset(dataset, web_data_path)

    result: dict[str, Any] = {"ok": True, "vendor_count": len(dataset), "output_path": str(output_path)}

    if os.environ.get("GITHUB_PUBLISH", "").lower() == "true":
        try:
            from scripts.publish_to_github import publish_to_github  # noqa: PLC0415
            gh_result = publish_to_github(local_file=web_data_path)
            result["github"] = gh_result
            logger.info("GitHub publish: %s", gh_result)
        except Exception as exc:
            logger.warning("GitHub publish failed (non-fatal): %s", exc)
            result["github"] = {"ok": False, "error": str(exc)}

    return result


RUN_HISTORY_PATH = PROJECT_ROOT / "runs" / "run_history.json"
_PIPELINE_LOG_LIMIT = 50


def _read_pipeline_log(limit: int = _PIPELINE_LOG_LIMIT) -> list[dict[str, Any]]:
    """Return the last `limit` entries from runs/run_history.json as structured log lines."""
    if not RUN_HISTORY_PATH.exists():
        return []
    try:
        raw: list[dict[str, Any]] = json.loads(RUN_HISTORY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    entries = raw[-limit:] if len(raw) > limit else raw
    return [
        {
            "timestamp": e.get("timestamp", ""),
            "phase": e.get("phase", ""),
            "milestone": e.get("milestone", ""),
            "action": e.get("action", ""),
            "message": e.get("note", e.get("command", "")),
            "success": e.get("success"),
            "event_type": e.get("event_type", ""),
        }
        for e in reversed(entries)  # newest first
    ]


def _pipeline_log_response(start_response):
    entries = _read_pipeline_log()
    return _json_response(start_response, {"ok": True, "entries": entries, "count": len(entries)})


def _publish_response(start_response, publish_fn: Callable[[], dict[str, Any]]):
    try:
        result = publish_fn()
    except Exception as error:  # pragma: no cover - defensive error surface
        logger.exception("Publish directory failed")
        return _json_response(start_response, {"ok": False, "error": str(error)}, status="500 Internal Server Error")
    return _json_response(start_response, result)


def _parse_enrich_write_payload(environ) -> dict[str, Any]:
    """Parse a JSON body from the request without coercing values to strings."""
    content_length = environ.get("CONTENT_LENGTH", "0") or "0"
    try:
        body_length = int(content_length)
    except ValueError:
        body_length = 0
    raw_body = environ["wsgi.input"].read(body_length) if body_length > 0 else b""
    if not raw_body:
        return {}
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _run_enrich_write(payload: dict[str, Any]) -> dict[str, Any]:
    """Instantiate VendorIntelligence from an n8n enrichment payload, normalise and upsert."""
    from services.extraction.vendor_intel import VendorIntelligence

    website = str(payload.get("website") or "").strip()
    vendor_name = str(payload.get("vendor_name") or payload.get("name") or "").strip()

    validation_errors: list[str] = []
    if not website:
        validation_errors.append("website is required")

    if validation_errors:
        return {"ok": False, "vendor": None, "fields_written": [], "validation_errors": validation_errors}

    # Build kwargs for VendorIntelligence — pass through every recognised field
    vi_kwargs: dict[str, Any] = {"website": website, "vendor_name": vendor_name}
    _SCALAR_FIELDS = {
        "source", "mission", "usp", "founded", "confidence",
        "directory_fit", "directory_category", "ceo_name", "hq_address",
        "company_hq", "contact_email", "contact_page_url", "demo_url",
        "help_center_url", "support_url", "about_url", "team_url",
        "developer_docs_url", "directory_decision_source",
        "llm_directory_fit", "llm_directory_category",
        "g2_url", "g2_market_segment", "g2_rating", "g2_review_count",
        "pricing_source", "funding_stage", "total_funding", "youtube_channel_url",
        "company_size", "revenue", "linkedin_url", "ceo_linkedin",
    }
    _BOOL_FIELDS = {"free_trial", "soc2", "include_in_directory", "llm_include_in_directory", "has_public_pricing_page"}
    _LIST_FIELDS = {
        "icp", "use_cases", "lifecycle_stages", "pricing", "compliance",
        "integration_categories", "integrations", "support_signals",
        "case_studies", "case_study_signals", "customers", "value_statements",
        "source_urls", "evidence_urls", "phone_numbers", "contact_emails",
        "directory_reasoning", "g2_categories",
    }
    _DICT_LIST_FIELDS = {
        "icp_buyer", "products", "leadership", "integration_taxonomy",
        "external_enrichment", "case_study_details", "testimonials", "blog_posts",
    }

    for f in _SCALAR_FIELDS:
        if f in payload:
            vi_kwargs[f] = payload[f]
    for f in _BOOL_FIELDS:
        if f in payload:
            vi_kwargs[f] = payload[f]
    for f in _LIST_FIELDS:
        if f in payload:
            vi_kwargs[f] = payload[f]
    for f in _DICT_LIST_FIELDS:
        if f in payload:
            vi_kwargs[f] = payload[f]

    try:
        intelligence = VendorIntelligence(**vi_kwargs)
    except (TypeError, ValueError) as exc:
        return {"ok": False, "vendor": website, "fields_written": [], "validation_errors": [str(exc)]}

    fields_written = [f for f in payload if f not in {"website", "vendor_name", "name", "pipeline_name"}]
    pipeline_name = _infer_enrichment_pipeline_name(payload)

    if supabase_client.is_configured():
        try:
            supabase_client.upsert_vendor_result(
                {"source": str(payload.get("source") or "n8n_enrich")},
                {"website": website, "vendor_name": vendor_name, "text": ""},
                intelligence,
                enrichment_pipeline=pipeline_name,
                preserve_existing=True,
            )
        except Exception as exc:
            return {
                "ok": False,
                "vendor": website,
                "fields_written": fields_written,
                "validation_errors": [f"upsert_failed: {exc}"],
            }

    return {
        "ok": True,
        "vendor": website,
        "fields_written": fields_written,
        "validation_errors": [],
        "enrichment_pipeline": pipeline_name,
    }


def _infer_enrichment_pipeline_name(payload: dict[str, Any]) -> str:
    explicit = _normalize_pipeline_name(payload.get("pipeline_name") or payload.get("source") or "")
    if explicit and explicit not in {"n8n_enrich", "unknown"}:
        return explicit
    keys = {str(key) for key in payload.keys()}
    if any(key.startswith("g2_") for key in keys):
        return "g2"
    if "tracxn_url" in keys:
        return "tracxn"
    if "pricing_source" in keys or "has_public_pricing_page" in keys:
        return "pricing"
    if "raw_crawl_blob" in keys or "crawl_page_count" in keys or "crawl_completed_at" in keys:
        return "apify"
    return "n8n_enrich"


def _normalize_pipeline_name(value: object) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value or "").strip())
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized.strip("_")


def _enrich_write_response(
    start_response,
    enrich_write_fn: Callable[[dict[str, Any]], dict[str, Any]],
    payload: dict[str, Any],
):
    try:
        result = enrich_write_fn(payload)
    except Exception as error:  # pragma: no cover - defensive error surface
        logger.exception("Enrich-write failed")
        return _json_response(
            start_response,
            {"ok": False, "vendor": None, "fields_written": [], "validation_errors": [str(error)]},
            status="500 Internal Server Error",
        )
    status = "200 OK" if result.get("ok") else "400 Bad Request"
    return _json_response(start_response, result, status=status)


_ALLOWED_CRAWL_RESULT_COLUMNS = frozenset({
    "crawl_tier1_result",
    "crawl_tier2_result",
    "crawl_tier3_result",
    "crawl_datagma_result",
    "crawl_g2_result",
    "crawl_llm_result",
})


def _store_crawl_result_response(start_response, payload: dict[str, Any]):
    """Write a JSONB blob to a named crawl_*_result column. Never touches main schema columns."""
    vendor_website = str(payload.get("vendor_website") or "").strip()
    column = str(payload.get("column") or "").strip()
    result_payload = payload.get("payload")

    if not vendor_website:
        return _json_response(start_response, {"ok": False, "error": "vendor_website required"}, status="400 Bad Request")
    if column not in _ALLOWED_CRAWL_RESULT_COLUMNS:
        return _json_response(start_response, {"ok": False, "error": f"unknown column: {column}"}, status="400 Bad Request")
    if not isinstance(result_payload, dict):
        return _json_response(start_response, {"ok": False, "error": "payload must be a JSON object"}, status="400 Bad Request")

    if not supabase_client.is_configured():
        return _json_response(start_response, {"ok": False, "error": "supabase_not_configured"}, status="503 Service Unavailable")

    try:
        client = supabase_client.get_supabase_client()
        client.table("cs_vendors").update({column: result_payload}).eq("website", vendor_website).execute()
    except Exception as error:
        logger.exception("store-crawl-result failed for %s column=%s", vendor_website, column)
        return _json_response(start_response, {"ok": False, "error": str(error)}, status="500 Internal Server Error")

    return _json_response(start_response, {"ok": True, "vendor_website": vendor_website, "column": column})


def _store_pages_response(start_response, payload: dict[str, Any]):
    """Upsert a batch of crawled pages into vendor_pages. Called by n8n tier crawl workflows."""
    vendor_website = str(payload.get("vendor_website") or "").strip()
    tier_used = str(payload.get("tier_used") or "").strip()
    pages = payload.get("pages")

    if not vendor_website:
        return _json_response(start_response, {"ok": False, "error": "vendor_website required"}, status="400 Bad Request")
    if not isinstance(pages, list) or not pages:
        return _json_response(start_response, {"ok": False, "error": "pages must be a non-empty list"}, status="400 Bad Request")
    if not supabase_client.is_configured():
        return _json_response(start_response, {"ok": False, "error": "supabase_not_configured"}, status="503 Service Unavailable")

    rows = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_url = str(page.get("page_url") or "").strip()
        if not page_url:
            continue
        rows.append({
            "vendor_website": vendor_website,
            "page_url": page_url,
            "title": page.get("title"),
            "clean_text": page.get("clean_text"),
            "word_count": page.get("word_count"),
            "page_depth": page.get("page_depth"),
            "tier_used": tier_used or page.get("tier_used"),
        })

    if not rows:
        return _json_response(start_response, {"ok": False, "error": "no valid pages after filtering"}, status="400 Bad Request")

    try:
        client = supabase_client.get_supabase_client()
        client.table("vendor_pages").upsert(rows, on_conflict="vendor_website,page_url").execute()
    except Exception as error:
        logger.exception("store-pages failed for %s", vendor_website)
        return _json_response(start_response, {"ok": False, "error": str(error)}, status="500 Internal Server Error")

    return _json_response(start_response, {"ok": True, "vendor_website": vendor_website, "pages_stored": len(rows)})


def _field_coverage_response(start_response, query_params: dict[str, list[str]]):
    """Return per-field source coverage for a vendor, or vendor_pages row count check."""
    vendor_website = query_params.get("vendor_website", [""])[0].strip()
    check = query_params.get("check", [""])[0].strip()

    if not vendor_website:
        return _json_response(start_response, {"ok": False, "error": "vendor_website required"}, status="400 Bad Request")
    if not supabase_client.is_configured():
        return _json_response(start_response, {"ok": False, "error": "supabase_not_configured"}, status="503 Service Unavailable")

    try:
        client = supabase_client.get_supabase_client()

        if check == "vendor_pages_count":
            result = client.table("vendor_pages").select("id", count="exact").eq("vendor_website", vendor_website).execute()
            count = result.count if hasattr(result, "count") and result.count is not None else len(result.data or [])
            return _json_response(start_response, {"ok": True, "vendor_website": vendor_website, "vendor_pages_count": count})

        # Full field coverage report: read all crawl_*_result + source_field_map
        cols = ",".join([*_ALLOWED_CRAWL_RESULT_COLUMNS, "source_field_map"])
        vendor_rows = client.table("cs_vendors").select(cols).eq("website", vendor_website).execute()
        if not vendor_rows.data:
            return _json_response(start_response, {"ok": False, "error": "vendor not found"}, status="404 Not Found")

        row = vendor_rows.data[0]
        coverage: dict[str, Any] = {}
        for col in _ALLOWED_CRAWL_RESULT_COLUMNS:
            result_blob = row.get(col)
            if isinstance(result_blob, dict):
                coverage[col] = {
                    "ok": result_blob.get("ok"),
                    "crawled_at": result_blob.get("crawled_at"),
                    "fields": list((result_blob.get("fields") or {}).keys()),
                }
            else:
                coverage[col] = None

        return _json_response(start_response, {
            "ok": True,
            "vendor_website": vendor_website,
            "source_field_map": row.get("source_field_map"),
            "coverage": coverage,
        })
    except Exception as error:
        logger.exception("field-coverage failed for %s", vendor_website)
        return _json_response(start_response, {"ok": False, "error": str(error)}, status="500 Internal Server Error")


def _static_response(path: str):
    requested_path = "/admin.html" if path in {"", "/"} else path
    candidate_path = (WEBSITE_ROOT / requested_path.lstrip("/")).resolve()
    if not _is_within(candidate_path, WEBSITE_ROOT):
        return None
    if candidate_path.is_file():
        body = candidate_path.read_bytes()
        content_type = mimetypes.guess_type(str(candidate_path))[0] or "application/octet-stream"
        return (
            "200 OK",
            [("Content-Type", content_type), ("Content-Length", str(len(body)))],
            body,
        )

    if requested_path.startswith("/outputs/"):
        output_path = (PROJECT_ROOT / requested_path.lstrip("/")).resolve()
        if _is_within(output_path, PROJECT_ROOT / "outputs") and output_path.is_file():
            body = output_path.read_bytes()
            content_type = mimetypes.guess_type(str(output_path))[0] or "application/octet-stream"
            return (
                "200 OK",
                [("Content-Type", content_type), ("Content-Length", str(len(body)))],
                body,
            )
    return None


def _is_within(candidate_path: Path, root: Path) -> bool:
    try:
        candidate_path.relative_to(root.resolve())
    except ValueError:
        return False
    return True


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
