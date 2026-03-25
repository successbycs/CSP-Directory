"""Tests for the read-only admin API."""

import json
from io import BytesIO
from pathlib import Path

from services.admin import admin_api


def test_admin_api_returns_candidates_endpoint():
    app = admin_api.build_admin_app(
        list_candidates_fn=lambda: [{"candidate_domain": "renewai.com"}],
        list_vendors_fn=lambda: [],
        list_runs_fn=lambda: [],
    )
    status_headers = {}

    def start_response(status, headers):
        status_headers["status"] = status
        status_headers["headers"] = headers

    response_body = b"".join(app({"PATH_INFO": "/admin/candidates", "QUERY_STRING": ""}, start_response))

    assert status_headers["status"] == "200 OK"
    assert b'"candidate_domain": "renewai.com"' in response_body


def test_admin_api_returns_not_found_for_unknown_path():
    app = admin_api.build_admin_app(
        list_candidates_fn=lambda: [],
        list_vendors_fn=lambda: [],
        list_runs_fn=lambda: [],
    )
    status_headers = {}

    def start_response(status, headers):
        status_headers["status"] = status
        status_headers["headers"] = headers

    response_body = b"".join(app({"PATH_INFO": "/admin/unknown", "QUERY_STRING": ""}, start_response))

    assert status_headers["status"] == "404 Not Found"
    assert b'"error": "not_found"' in response_body


def test_admin_api_returns_empty_items_when_candidates_backend_fails():
    app = admin_api.build_admin_app(
        list_candidates_fn=lambda: (_ for _ in ()).throw(RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set")),
        list_vendors_fn=lambda: [],
        list_runs_fn=lambda: [],
    )
    status_headers = {}

    def start_response(status, headers):
        status_headers["status"] = status
        status_headers["headers"] = headers

    response_body = b"".join(app({"PATH_INFO": "/admin/candidates", "QUERY_STRING": ""}, start_response))

    assert status_headers["status"] == "200 OK"
    assert b'"items": []' in response_body
    assert b'"error": "candidates_unavailable"' in response_body


def test_admin_api_include_action_endpoint():
    app = admin_api.build_admin_app(
        list_candidates_fn=lambda: [],
        list_vendors_fn=lambda: [],
        list_runs_fn=lambda: [],
        include_vendor_fn=lambda vendor: {"ok": True, "action": "include", "vendor": vendor},
    )
    status_headers = {}

    def start_response(status, headers):
        status_headers["status"] = status
        status_headers["headers"] = headers

    response_body = b"".join(
        app(
            {
                "PATH_INFO": "/admin/vendor/include",
                "QUERY_STRING": "",
                "REQUEST_METHOD": "POST",
                "CONTENT_LENGTH": "22",
                "wsgi.input": BytesIO(b'{"vendor":"gainsight"}'),
            },
            start_response,
        )
    )

    assert status_headers["status"] == "200 OK"
    assert b'"action": "include"' in response_body


def test_admin_api_returns_runs_endpoint_with_status_fields():
    app = admin_api.build_admin_app(
        list_candidates_fn=lambda: [],
        list_vendors_fn=lambda: [],
        list_runs_fn=lambda: [{"run_id": "run-1", "run_status": "completed_with_warnings", "error_summary": ""}],
    )
    status_headers = {}

    def start_response(status, headers):
        status_headers["status"] = status
        status_headers["headers"] = headers

    response_body = b"".join(app({"PATH_INFO": "/admin/runs", "QUERY_STRING": ""}, start_response))

    assert status_headers["status"] == "200 OK"
    assert b'"run_status": "completed_with_warnings"' in response_body


def test_admin_api_returns_search_visibility_endpoint():
    app = admin_api.build_admin_app(
        list_candidates_fn=lambda: [],
        list_vendors_fn=lambda: [],
        list_runs_fn=lambda: [],
        list_search_visibility_fn=lambda: {
            "metrics": {"query_count": 1, "ranking_count": 1, "vendor_count": 1},
            "role_query_rankings": [{"surfaced_vendor_name": "Gainsight"}],
            "vendor_visibility_summary": [{"surfaced_vendor_name": "Gainsight"}],
        },
    )
    status_headers = {}

    def start_response(status, headers):
        status_headers["status"] = status
        status_headers["headers"] = headers

    response_body = b"".join(app({"PATH_INFO": "/admin/search-visibility", "QUERY_STRING": ""}, start_response))

    assert status_headers["status"] == "200 OK"
    assert b'"vendor_count": 1' in response_body
    assert b'"surfaced_vendor_name": "Gainsight"' in response_body


def test_admin_api_returns_leads_endpoint():
    app = admin_api.build_admin_app(
        list_candidates_fn=lambda: [],
        list_vendors_fn=lambda: [],
        list_runs_fn=lambda: [],
        list_leads_fn=lambda: {
            "metrics": {"lead_count": 1, "qualified_lead_count": 0},
            "items": [{"lead_email": "ops@example.com", "follow_up_status": "new"}],
        },
    )
    status_headers = {}

    def start_response(status, headers):
        status_headers["status"] = status
        status_headers["headers"] = headers

    response_body = b"".join(app({"PATH_INFO": "/admin/leads", "QUERY_STRING": ""}, start_response))

    assert status_headers["status"] == "200 OK"
    assert b'"lead_count": 1' in response_body
    assert b'"lead_email": "ops@example.com"' in response_body


def test_admin_api_public_lead_capture_endpoint():
    app = admin_api.build_admin_app(
        list_candidates_fn=lambda: [],
        list_vendors_fn=lambda: [],
        list_runs_fn=lambda: [],
        create_lead_fn=lambda payload: {"lead_id": "lead-1", "lead_email": payload["email"], "follow_up_status": "new"},
    )
    status_headers = {}

    def start_response(status, headers):
        status_headers["status"] = status
        status_headers["headers"] = headers

    response_body = b"".join(
        app(
            {
                "PATH_INFO": "/api/lead-capture",
                "QUERY_STRING": "",
                "REQUEST_METHOD": "POST",
                "CONTENT_LENGTH": "200",
                "wsgi.input": BytesIO(b'{"name":"Taylor","email":"taylor@example.com","company":"Example","intent":"advisory"}'),
            },
            start_response,
        )
    )

    assert status_headers["status"] == "200 OK"
    assert b'"lead_id": "lead-1"' in response_body
    assert b'"lead_email": "taylor@example.com"' in response_body


def test_admin_api_lead_follow_up_requires_lead_id():
    app = admin_api.build_admin_app(
        list_candidates_fn=lambda: [],
        list_vendors_fn=lambda: [],
        list_runs_fn=lambda: [],
    )
    status_headers = {}

    def start_response(status, headers):
        status_headers["status"] = status
        status_headers["headers"] = headers

    response_body = b"".join(
        app(
            {
                "PATH_INFO": "/admin/lead/follow-up",
                "QUERY_STRING": "",
                "REQUEST_METHOD": "POST",
                "CONTENT_LENGTH": "2",
                "wsgi.input": BytesIO(b"{}"),
            },
            start_response,
        )
    )

    assert status_headers["status"] == "400 Bad Request"
    assert b'"lead_id_required"' in response_body


def test_admin_api_rerun_action_requires_vendor_lookup():
    app = admin_api.build_admin_app(
        list_candidates_fn=lambda: [],
        list_vendors_fn=lambda: [],
        list_runs_fn=lambda: [],
    )
    status_headers = {}

    def start_response(status, headers):
        status_headers["status"] = status
        status_headers["headers"] = headers

    response_body = b"".join(
        app(
            {
                "PATH_INFO": "/admin/vendor/rerun-enrichment",
                "QUERY_STRING": "",
                "REQUEST_METHOD": "POST",
                "CONTENT_LENGTH": "2",
                "wsgi.input": BytesIO(b"{}"),
            },
            start_response,
        )
    )

    assert status_headers["status"] == "400 Bad Request"
    assert b'"vendor_lookup_required"' in response_body


def test_list_vendor_records_falls_back_to_local_review_output(monkeypatch, tmp_path: Path):
    results_path = tmp_path / "vendor_review_dataset.json"
    results_path.write_text('[{"vendor_name": "ExampleCorp", "website": "https://example.com"}]', encoding="utf-8")

    monkeypatch.setattr(admin_api.supabase_client, "is_configured", lambda: True)
    monkeypatch.setattr(
        admin_api.supabase_client,
        "list_vendor_profiles",
        lambda limit=200: (_ for _ in ()).throw(RuntimeError("column cs_vendors.icp does not exist")),
    )
    monkeypatch.setattr(admin_api.supabase_client, "is_persistence_unavailable_error", lambda error: "does not exist" in str(error))
    monkeypatch.setattr(admin_api, "DEFAULT_VENDOR_RESULTS_PATH", results_path)

    result = admin_api.list_vendor_records(limit=50)
    fallback = admin_api.read_vendor_review_results(results_path)

    assert fallback == [{"vendor_name": "ExampleCorp", "website": "https://example.com"}]
    assert result == [{"vendor_name": "ExampleCorp", "website": "https://example.com"}]


def test_list_candidate_records_falls_back_to_local_review_output(monkeypatch, tmp_path: Path):
    results_path = tmp_path / "candidate_review_dataset.json"
    results_path.write_text('[{"candidate_domain": "renewai.com", "candidate_status": "enriched"}]', encoding="utf-8")

    monkeypatch.setattr(admin_api.supabase_client, "is_configured", lambda: True)
    monkeypatch.setattr(
        admin_api.discovery_store,
        "list_candidate_records",
        lambda limit=200: (_ for _ in ()).throw(RuntimeError("public.discovery_candidates does not exist")),
    )
    monkeypatch.setattr(admin_api.discovery_store, "is_discovery_store_unavailable_error", lambda error: "does not exist" in str(error))
    monkeypatch.setattr(admin_api, "DEFAULT_CANDIDATE_RESULTS_PATH", results_path)

    result = admin_api.list_candidate_records(limit=50)

    assert result == [{"candidate_domain": "renewai.com", "candidate_status": "enriched"}]


def test_list_search_visibility_data_falls_back_to_local_report_output(monkeypatch, tmp_path: Path):
    results_path = tmp_path / "search_visibility_report.json"
    results_path.write_text(
        '{"metrics":{"query_count":1,"ranking_count":1,"vendor_count":1},"role_query_rankings":[{"surfaced_vendor_name":"Gainsight"}],"vendor_visibility_summary":[{"surfaced_vendor_name":"Gainsight"}]}',
        encoding="utf-8",
    )

    monkeypatch.setattr(admin_api.supabase_client, "is_configured", lambda: True)
    monkeypatch.setattr(
        admin_api.search_visibility_report,
        "export_search_visibility_artifacts",
        lambda: (_ for _ in ()).throw(RuntimeError("public.buyer_search_results does not exist")),
    )
    monkeypatch.setattr(
        admin_api.search_visibility_store,
        "is_search_visibility_store_unavailable_error",
        lambda error: "does not exist" in str(error),
    )
    monkeypatch.setattr(admin_api, "DEFAULT_SEARCH_VISIBILITY_RESULTS_PATH", results_path)

    result = admin_api.list_search_visibility_data()

    assert result["metrics"]["vendor_count"] == 1
    assert result["role_query_rankings"][0]["surfaced_vendor_name"] == "Gainsight"


def _make_wsgi_environ(method="POST", path="/admin/publish"):
    return {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": "",
        "CONTENT_LENGTH": "0",
        "wsgi.input": BytesIO(b""),
    }


def test_admin_publish_endpoint_success():
    published = []

    def fake_publish():
        published.append(True)
        return {"ok": True, "vendor_count": 5, "output_path": "/tmp/directory_dataset.json"}

    app = admin_api.build_admin_app(
        list_candidates_fn=lambda: [],
        list_vendors_fn=lambda: [],
        list_runs_fn=lambda: [],
        publish_directory_fn=fake_publish,
    )
    status_headers = {}

    def start_response(status, headers):
        status_headers["status"] = status

    body = b"".join(app(_make_wsgi_environ(), start_response))
    data = json.loads(body)

    assert status_headers["status"] == "200 OK"
    assert data["ok"] is True
    assert data["vendor_count"] == 5
    assert data["output_path"] == "/tmp/directory_dataset.json"
    assert published  # publish function was called


def test_admin_publish_endpoint_export_failure():
    def failing_publish():
        raise RuntimeError("Supabase unavailable")

    app = admin_api.build_admin_app(
        list_candidates_fn=lambda: [],
        list_vendors_fn=lambda: [],
        list_runs_fn=lambda: [],
        publish_directory_fn=failing_publish,
    )
    status_headers = {}

    def start_response(status, headers):
        status_headers["status"] = status

    body = b"".join(app(_make_wsgi_environ(), start_response))
    data = json.loads(body)

    assert status_headers["status"] == "500 Internal Server Error"
    assert data["ok"] is False
    assert "Supabase unavailable" in data["error"]
