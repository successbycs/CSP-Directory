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
from services.discovery import discovery_store
from services.export import search_visibility_report
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
    list_leads_fn: Callable[[], dict[str, Any]] | None = None,
    create_lead_fn: Callable[[dict[str, str]], dict[str, Any]] | None = None,
    update_lead_follow_up_fn: Callable[..., dict[str, Any]] | None = None,
    include_vendor_fn: Callable[[str], dict[str, Any]] | None = None,
    exclude_vendor_fn: Callable[[str], dict[str, Any]] | None = None,
    rerun_vendor_enrichment_fn: Callable[[str], dict[str, Any]] | None = None,
):
    """Return a small WSGI app exposing admin JSON endpoints and public capture intake."""
    list_candidates_fn = list_candidates_fn or list_candidate_records
    list_vendors_fn = list_vendors_fn or list_vendor_records
    list_runs_fn = list_runs_fn or list_run_records
    list_search_visibility_fn = list_search_visibility_fn or list_search_visibility_data
    list_leads_fn = list_leads_fn or list_lead_capture_data
    create_lead_fn = create_lead_fn or lead_capture_store.create_lead_capture
    update_lead_follow_up_fn = update_lead_follow_up_fn or lead_capture_store.update_lead_follow_up
    include_vendor_fn = include_vendor_fn or admin_actions.include_vendor
    exclude_vendor_fn = exclude_vendor_fn or admin_actions.exclude_vendor
    rerun_vendor_enrichment_fn = rerun_vendor_enrichment_fn or admin_actions.rerun_vendor_enrichment

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
        if method == "GET" and path == "/admin/leads":
            return _safe_payload_response(start_response, list_leads_fn, label="leads")
        if method == "POST" and path == "/api/lead-capture":
            payload = _parse_action_payload(environ)
            return _lead_capture_response(start_response, create_lead_fn, payload)
        if method == "POST" and path == "/admin/vendor/include":
            payload = _parse_action_payload(environ)
            return _action_response(start_response, include_vendor_fn, payload)
        if method == "POST" and path == "/admin/vendor/exclude":
            payload = _parse_action_payload(environ)
            return _action_response(start_response, exclude_vendor_fn, payload)
        if method == "POST" and path == "/admin/vendor/rerun-enrichment":
            payload = _parse_action_payload(environ)
            return _action_response(start_response, rerun_vendor_enrichment_fn, payload)
        if method == "POST" and path == "/admin/lead/follow-up":
            payload = _parse_action_payload(environ)
            return _lead_follow_up_response(start_response, update_lead_follow_up_fn, payload)
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
    payload: dict[str, str],
):
    try:
        result = create_lead_fn(payload)
    except ValueError as error:
        return _json_response(start_response, {"ok": False, "error": str(error)}, status="400 Bad Request")
    except Exception as error:  # pragma: no cover - defensive error surface
        logger.exception("Lead capture failed")
        return _json_response(start_response, {"ok": False, "error": str(error)}, status="500 Internal Server Error")
    return _json_response(start_response, {"ok": True, "lead": result})


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
