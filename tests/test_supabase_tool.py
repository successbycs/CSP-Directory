"""Tests for the repo-owned Supabase tool CLI."""

from __future__ import annotations

from tools.supabase import cli as supabase_tool


def test_resolve_backend_prefers_direct_for_apply_schema_when_available(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setattr(supabase_tool.shutil, "which", lambda command: "/usr/bin/psql" if command == "psql" else None)

    assert supabase_tool.resolve_backend("apply_schema", "auto") == "direct"


def test_resolve_backend_requires_direct_schema_admin_for_apply_schema(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.setattr(supabase_tool.shutil, "which", lambda command: None)

    try:
        supabase_tool.resolve_backend("apply_schema", "auto")
    except RuntimeError as error:
        assert "DATABASE_URL or SUPABASE_DB_URL" in str(error)
    else:
        raise AssertionError("apply_schema should require direct schema-admin access")


def test_parse_key_values_parses_scalars_and_json():
    values = supabase_tool.parse_key_values(
        [
            "include_in_directory=true",
            "directory_fit=high",
            "note=null",
            "candidate_count=4",
            'use_cases=["Reduce churn","Improve onboarding"]',
        ]
    )
    assert values == {
        "include_in_directory": True,
        "directory_fit": "high",
        "note": None,
        "candidate_count": 4,
        "use_cases": ["Reduce churn", "Improve onboarding"],
    }


def test_build_delete_sql_is_guarded():
    sql = supabase_tool.build_delete_sql("pipeline_runs", "run_id", "run-123")
    assert sql == "delete from pipeline_runs where run_id = 'run-123' returning *;"


def test_sanitize_run_values_enforces_identity_for_create():
    try:
        supabase_tool.sanitize_run_values({"run_status": "ok"}, require_identity=True)
    except RuntimeError as error:
        assert "run_id" in str(error)
    else:
        raise AssertionError("create_run should require run_id")


def test_sanitize_candidate_values_rejects_unsupported_field():
    try:
        supabase_tool.sanitize_candidate_values({"arbitrary_field": "bad"})
    except RuntimeError as error:
        assert "Unsupported field" in str(error)
    else:
        raise AssertionError("Unsupported field should be rejected")
