"""Tests for the Supabase schema check script."""

from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_supabase.py"
MODULE_SPEC = importlib.util.spec_from_file_location("check_supabase_script", MODULE_PATH)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
check_supabase = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(check_supabase)


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeTableQuery:
    def __init__(self, table_name: str, error: Exception | None):
        self.table_name = table_name
        self.error = error

    def select(self, columns: str):
        return self

    def limit(self, count: int):
        return self

    def execute(self):
        if self.error is not None:
            raise self.error
        return FakeResponse([{"ok": True}])


class FakeClient:
    def __init__(self, errors: dict[str, Exception | None]):
        self.errors = errors

    def table(self, table_name: str):
        return FakeTableQuery(table_name, self.errors.get(table_name))


class SequenceFakeTableQuery:
    def __init__(self, client, table_name: str):
        self.client = client
        self.table_name = table_name
        self.columns = ""

    def select(self, columns: str):
        self.columns = columns
        return self

    def limit(self, count: int):
        return self

    def execute(self):
        sequence = self.client.errors[self.table_name]
        if not sequence:
            return FakeResponse([{"ok": True}])
        next_error = sequence.pop(0)
        if next_error is not None:
            raise next_error
        return FakeResponse([{"ok": True}])


class SequenceFakeClient:
    def __init__(self, errors: dict[str, list[Exception | None]]):
        self.errors = {key: list(value) for key, value in errors.items()}

    def table(self, table_name: str):
        return SequenceFakeTableQuery(self, table_name)


def test_check_table_reports_missing_table():
    class MissingTableError(Exception):
        def __init__(self):
            super().__init__({"message": "Could not find the table 'public.pipeline_runs' in the schema cache", "code": "PGRST205"})

    result = check_supabase.check_table(
        FakeClient({"pipeline_runs": MissingTableError()}),
        "pipeline_runs",
        ["run_id", "started_at"],
    )

    assert result["status"] == "missing_table"
    assert result["missing_columns"] == []


def test_check_table_reports_missing_columns():
    class MissingColumnError(Exception):
        def __init__(self):
            super().__init__({"message": "Could not find the 'case_studies' column of 'cs_vendors' in the schema cache", "code": "PGRST204"})

    result = check_supabase.check_table(
        FakeClient({"cs_vendors": MissingColumnError()}),
        "cs_vendors",
        ["name", "case_studies", "website"],
    )

    assert result["status"] == "missing_columns"
    assert result["missing_columns"] == ["case_studies"]


def test_check_table_reports_legacy_missing_column_errors_as_missing_columns():
    class MissingColumnError(Exception):
        def __init__(self):
            super().__init__({"message": "column cs_vendors.icp does not exist", "code": "42703"})

    result = check_supabase.check_table(
        FakeClient({"cs_vendors": MissingColumnError()}),
        "cs_vendors",
        ["name", "icp", "website"],
    )

    assert result["status"] == "missing_columns"
    assert result["missing_columns"] == ["icp"]


def test_check_table_reports_ok_when_select_succeeds():
    result = check_supabase.check_table(
        FakeClient({"cs_vendors": None}),
        "cs_vendors",
        ["name", "website"],
    )

    assert result["status"] == "ok"
    assert result["missing_columns"] == []


def test_main_fails_when_schema_checks_hit_connectivity_errors(monkeypatch, capsys):
    monkeypatch.setattr(check_supabase, "load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(check_supabase.supabase_client, "is_configured", lambda: True)
    monkeypatch.setattr(check_supabase.supabase_client, "get_supabase_client", lambda: object())
    monkeypatch.setattr(
        check_supabase,
        "check_table",
        lambda client, table, columns: {
            "table": table,
            "status": "error",
            "missing_columns": [],
            "error": "Temporary failure in name resolution",
        },
    )

    exit_code = check_supabase.main()

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "connectivity/unknown error(s)" in output


def test_check_table_reports_multiple_missing_columns():
    class MissingIcpError(Exception):
        def __init__(self):
            super().__init__({"message": "column cs_vendors.icp does not exist", "code": "42703"})

    class MissingIncludeError(Exception):
        def __init__(self):
            super().__init__({"message": "column cs_vendors.include_in_directory does not exist", "code": "42703"})

    result = check_supabase.check_table(
        SequenceFakeClient({"cs_vendors": [MissingIcpError(), MissingIncludeError(), None]}),
        "cs_vendors",
        ["name", "icp", "include_in_directory", "website"],
    )

    assert result["status"] == "missing_columns"
    assert result["missing_columns"] == ["icp", "include_in_directory"]


def test_build_required_schema_includes_vendor_write_only_columns():
    schema = check_supabase.build_required_schema()
    vendor_table = next(item for item in schema if item["table"] == "cs_vendors")

    assert "raw_description" in vendor_table["columns"]
    assert "include_in_directory" in vendor_table["columns"]


def test_build_required_schema_includes_search_visibility_tables():
    schema = check_supabase.build_required_schema()
    query_table = next(item for item in schema if item["table"] == "buyer_search_queries")
    result_table = next(item for item in schema if item["table"] == "buyer_search_results")

    assert "query_signature" in query_table["columns"]
    assert "generated_at" in query_table["columns"]
    assert "observed_rank" in result_table["columns"]
    assert "run_timestamp" in result_table["columns"]
