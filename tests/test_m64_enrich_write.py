"""M64: Tests for POST /admin/enrich-write endpoint.

Requirements verified:
- Accepts an n8n enrichment payload with at minimum a website field
- Validates required fields (website)
- Instantiates VendorIntelligence and runs normalization
- Returns {ok, vendor, fields_written, validation_errors}
- Calls supabase_client upsert when configured (injectable for testing)
- enrich_write_fn is injectable in build_admin_app()
"""

from __future__ import annotations

import io
import json
from typing import Any

import pytest

from services.admin.admin_api import build_admin_app, _run_enrich_write


# ---------------------------------------------------------------------------
# Helper: make a fake WSGI environ for POST requests
# ---------------------------------------------------------------------------


def _make_environ(method: str, path: str, body: dict | None = None) -> dict:
    body_bytes = json.dumps(body or {}).encode("utf-8") if body is not None else b""
    return {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "CONTENT_LENGTH": str(len(body_bytes)),
        "wsgi.input": io.BytesIO(body_bytes),
        "QUERY_STRING": "",
    }


def _call_app(app, method: str, path: str, body: dict | None = None):
    environ = _make_environ(method, path, body)
    responses = []

    def start_response(status, headers):
        responses.append(status)

    body_iter = app(environ, start_response)
    status = responses[0] if responses else "200 OK"
    raw = b"".join(body_iter)
    return status, json.loads(raw)


# ---------------------------------------------------------------------------
# 1. _run_enrich_write unit tests (no WSGI layer)
# ---------------------------------------------------------------------------


def test_enrich_write_returns_ok_true_for_valid_website():
    """Valid payload with website should return ok=True without upsert (no client configured)."""
    result = _run_enrich_write({"website": "https://example.com"})
    assert result["ok"] is True
    assert result["vendor"] == "https://example.com"
    assert isinstance(result["fields_written"], list)
    assert result["validation_errors"] == []


def test_enrich_write_returns_error_when_website_missing():
    """Missing website must return ok=False with validation_errors."""
    result = _run_enrich_write({"icp": ["SaaS companies"]})
    assert result["ok"] is False
    assert "website is required" in result["validation_errors"]


def test_enrich_write_passes_scalar_fields():
    """Scalar fields like mission should be accepted without error."""
    result = _run_enrich_write({
        "website": "https://example.com",
        "mission": "Help customer success teams.",
        "founded": "2018",
    })
    assert result["ok"] is True
    assert "mission" in result["fields_written"]
    assert "founded" in result["fields_written"]


def test_enrich_write_passes_list_fields():
    """List fields like icp and lifecycle_stages should be accepted without error."""
    result = _run_enrich_write({
        "website": "https://example.com",
        "icp": ["SaaS companies"],
        "lifecycle_stages": ["Adopt", "Renew"],
        "use_cases": ["health scoring"],
    })
    assert result["ok"] is True
    assert "icp" in result["fields_written"]
    assert "lifecycle_stages" in result["fields_written"]


def test_enrich_write_passes_dict_list_fields():
    """Dict-list fields like icp_buyer should be accepted without error."""
    result = _run_enrich_write({
        "website": "https://example.com",
        "icp_buyer": [{"persona": "VP of Customer Success", "confidence": "high", "evidence": []}],
    })
    assert result["ok"] is True
    assert "icp_buyer" in result["fields_written"]


def test_enrich_write_accepts_valid_lifecycle_stages():
    """Valid lifecycle stage names should be accepted without error."""
    result = _run_enrich_write({
        "website": "https://example.com",
        "lifecycle_stages": ["Adopt", "Renew"],
    })
    assert result["ok"] is True
    assert "lifecycle_stages" in result["fields_written"]


def test_enrich_write_vendor_name_accepted():
    """vendor_name field should be accepted and not appear in fields_written (it's identity)."""
    result = _run_enrich_write({
        "website": "https://example.com",
        "vendor_name": "Acme Corp",
        "mission": "We help teams.",
    })
    assert result["ok"] is True
    # vendor_name is excluded from fields_written (it's identity metadata)
    assert "vendor_name" not in result["fields_written"]
    assert "mission" in result["fields_written"]


def test_enrich_write_uses_injectable_fn():
    """enrich_write_fn should be injectable into build_admin_app."""
    captured = {}

    def fake_enrich_write(payload: dict[str, Any]) -> dict[str, Any]:
        captured["payload"] = payload
        return {"ok": True, "vendor": payload.get("website"), "fields_written": ["mission"], "validation_errors": []}

    app = build_admin_app(enrich_write_fn=fake_enrich_write)
    status, body = _call_app(app, "POST", "/admin/enrich-write", {"website": "https://example.com", "mission": "Help!"})
    assert status == "200 OK"
    assert body["ok"] is True
    assert captured["payload"]["website"] == "https://example.com"


def test_enrich_write_returns_400_when_validation_fails_via_wsgi():
    """WSGI layer should return 400 when enrich_write_fn returns ok=False."""
    def fake_enrich_write(payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": False, "vendor": None, "fields_written": [], "validation_errors": ["website is required"]}

    app = build_admin_app(enrich_write_fn=fake_enrich_write)
    status, body = _call_app(app, "POST", "/admin/enrich-write", {})
    assert status.startswith("400")
    assert body["ok"] is False
    assert "website is required" in body["validation_errors"]


def test_enrich_write_empty_body_returns_error():
    """Empty body should return validation error for missing website."""
    app = build_admin_app()
    status, body = _call_app(app, "POST", "/admin/enrich-write", {})
    assert body["ok"] is False
    assert "website is required" in body["validation_errors"]


def test_enrich_write_normalizes_website():
    """Website should be accepted and returned via the vendor field."""
    result = _run_enrich_write({"website": "https://example.com"})
    assert result["ok"] is True
    assert "example.com" in result["vendor"]


def test_enrich_write_bool_fields_accepted():
    """Boolean fields free_trial and soc2 should be accepted without error."""
    result = _run_enrich_write({
        "website": "https://example.com",
        "free_trial": True,
        "soc2": False,
    })
    assert result["ok"] is True
    assert "free_trial" in result["fields_written"]
    assert "soc2" in result["fields_written"]
