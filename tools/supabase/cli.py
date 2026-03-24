"""Repo-owned Supabase tool CLI with direct database-backed execution."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.discovery import discovery_store
from services.persistence import run_store, supabase_client
from scripts import check_supabase


DEFAULT_SCHEMA_PATH = PROJECT_ROOT / "supabase" / "core_persistence_schema.sql"
VENDOR_KEY_COLUMN = "website"
CANDIDATE_KEY_COLUMN = "candidate_domain"
RUN_KEY_COLUMN = "run_id"
VENDOR_MUTABLE_COLUMNS = tuple(column for column in supabase_client.get_vendor_write_columns() if column != VENDOR_KEY_COLUMN)
CANDIDATE_MUTABLE_COLUMNS = tuple(column for column in discovery_store.DISCOVERY_CANDIDATE_COLUMNS if column != CANDIDATE_KEY_COLUMN)
RUN_MUTABLE_COLUMNS = tuple(column for column in run_store.PIPELINE_RUN_COLUMNS if column != RUN_KEY_COLUMN)


def build_parser() -> argparse.ArgumentParser:
    """Create the Supabase tool CLI parser."""
    parser = argparse.ArgumentParser(description="Run repo-owned Supabase tool operations.")
    parser.add_argument("operation")
    parser.add_argument("--backend", choices=("auto", "direct"), default="auto")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--lookup")
    parser.add_argument("--value", action="append", default=[], help="key=value update values")
    parser.add_argument("--sql-file", default=str(DEFAULT_SCHEMA_PATH.relative_to(PROJECT_ROOT)))
    parser.add_argument("--migration-name", default="core_persistence_schema")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one Supabase tool operation and print JSON."""
    args = build_parser().parse_args(argv)
    try:
        result = run_operation(
            operation=args.operation,
            backend=args.backend,
            limit=args.limit,
            lookup=args.lookup,
            values=parse_key_values(args.value),
            sql_file=(PROJECT_ROOT / args.sql_file).resolve(),
            migration_name=args.migration_name,
        )
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}, indent=2))
        return 1

    print(json.dumps({"ok": True, **result}, indent=2))
    return 0


def run_operation(
    *,
    operation: str,
    backend: str,
    limit: int,
    lookup: str | None,
    values: dict[str, Any],
    sql_file: Path,
    migration_name: str,
) -> dict[str, Any]:
    """Run one supported Supabase operation."""
    selected_backend = resolve_backend(operation, backend)
    if migration_name:
        _ = migration_name
    if selected_backend != "direct":
        raise RuntimeError(f"Unsupported backend {selected_backend}")
    return run_direct_operation(
        operation=operation,
        limit=limit,
        lookup=lookup,
        values=values,
        sql_file=sql_file,
    )


def resolve_backend(operation: str, backend: str) -> str:
    """Choose the execution backend."""
    if backend == "direct":
        return backend
    if operation == "apply_schema":
        if _has_direct_schema_access():
            return "direct"
        raise RuntimeError("apply_schema requires DATABASE_URL or SUPABASE_DB_URL with psql or psycopg")
    if operation in {"inspect_schema", "verify_schema"}:
        if supabase_client.is_configured():
            return "direct"
        raise RuntimeError("Schema inspection requires configured direct Supabase access")
    if supabase_client.is_configured():
        return "direct"
    raise RuntimeError(f"{operation} requires configured direct Supabase access")


def run_direct_operation(
    *,
    operation: str,
    limit: int,
    lookup: str | None,
    values: dict[str, Any],
    sql_file: Path,
) -> dict[str, Any]:
    """Run one operation using repo-owned direct access."""
    if operation in {"inspect_schema", "verify_schema"}:
        schema = inspect_schema_direct()
        if operation == "verify_schema" and not schema["schema_ok"]:
            raise RuntimeError(schema["summary"])
        return schema
    if operation == "apply_schema":
        return apply_schema_direct(sql_file)
    if operation == "read_vendors":
        return {"backend": "direct", "operation": operation, "rows": supabase_client.list_vendor_profiles(limit=limit)}
    if operation == "create_vendor":
        return {"backend": "direct", "operation": operation, "row": create_vendor_direct(values)}
    if operation == "update_vendor":
        if not lookup:
            raise RuntimeError("update_vendor requires --lookup")
        return {
            "backend": "direct",
            "operation": operation,
            "row": update_vendor_direct(lookup, values),
        }
    if operation == "delete_vendor":
        if not lookup:
            raise RuntimeError("delete_vendor requires --lookup")
        return {"backend": "direct", "operation": operation, "row": delete_row_direct("cs_vendors", VENDOR_KEY_COLUMN, lookup)}
    if operation == "read_candidates":
        return {"backend": "direct", "operation": operation, "rows": discovery_store.list_candidate_records(limit=limit)}
    if operation == "create_candidate":
        return {"backend": "direct", "operation": operation, "row": create_candidate_direct(values)}
    if operation == "update_candidate":
        if not lookup:
            raise RuntimeError("update_candidate requires --lookup")
        return {
            "backend": "direct",
            "operation": operation,
            "row": update_candidate_direct(lookup, values),
        }
    if operation == "delete_candidate":
        if not lookup:
            raise RuntimeError("delete_candidate requires --lookup")
        return {
            "backend": "direct",
            "operation": operation,
            "row": delete_row_direct(discovery_store.DISCOVERY_CANDIDATE_TABLE, CANDIDATE_KEY_COLUMN, lookup),
        }
    if operation == "read_runs":
        return {"backend": "direct", "operation": operation, "rows": run_store.list_run_records(limit=limit)}
    if operation == "create_run":
        return {"backend": "direct", "operation": operation, "row": create_run_direct(values)}
    if operation == "update_run":
        if not lookup:
            raise RuntimeError("update_run requires --lookup")
        return {
            "backend": "direct",
            "operation": operation,
            "row": update_run_direct(lookup, values),
        }
    if operation == "delete_run":
        if not lookup:
            raise RuntimeError("delete_run requires --lookup")
        return {
            "backend": "direct",
            "operation": operation,
            "row": delete_row_direct(run_store.PIPELINE_RUNS_TABLE, RUN_KEY_COLUMN, lookup),
        }
    raise RuntimeError(f"Unsupported direct operation: {operation}")


def inspect_schema_direct() -> dict[str, Any]:
    """Return a structured direct schema inspection report."""
    if not supabase_client.is_configured():
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be configured")
    client = supabase_client.get_supabase_client()
    tables: list[dict[str, Any]] = []
    missing_tables = 0
    missing_columns = 0
    other_errors = 0
    for table_check in check_supabase.build_required_schema():
        result = check_supabase.check_table(client, table_check["table"], table_check["columns"])
        result["purpose"] = table_check["purpose"]
        tables.append(result)
        if result["status"] == "missing_table":
            missing_tables += 1
        elif result["status"] == "missing_columns":
            missing_columns += len(result["missing_columns"])
        elif result["status"] == "error":
            other_errors += 1
    schema_ok = missing_tables == 0 and missing_columns == 0 and other_errors == 0
    return {
        "backend": "direct",
        "operation": "inspect_schema",
        "schema_ok": schema_ok,
        "tables": tables,
        "summary": (
            "Supabase schema check succeeded."
            if schema_ok
            else f"Supabase schema check failed: {missing_tables} missing table(s), {missing_columns} missing column(s), {other_errors} connectivity/unknown error(s)."
        ),
    }


def apply_schema_direct(sql_file: Path) -> dict[str, Any]:
    """Apply repo-owned schema SQL through psql when available."""
    database_url = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL or SUPABASE_DB_URL must be set for direct schema application")
    psql_path = shutil.which("psql")
    if psql_path is not None:
        completed = subprocess.run(
            [psql_path, database_url, "-v", "ON_ERROR_STOP=1", "-f", str(sql_file)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "psql apply failed")
        return {
            "backend": "direct",
            "operation": "apply_schema",
            "sql_file": str(sql_file.relative_to(PROJECT_ROOT)),
            "stdout": completed.stdout.strip(),
        }

    try:
        import psycopg
    except Exception as error:
        raise RuntimeError("direct schema application requires psql or psycopg") from error

    sql = sql_file.read_text(encoding="utf-8")
    with psycopg.connect(database_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql)
    return {
        "backend": "direct",
        "operation": "apply_schema",
        "sql_file": str(sql_file.relative_to(PROJECT_ROOT)),
        "stdout": "applied via psycopg",
    }


def create_vendor_direct(values: dict[str, Any]) -> dict[str, Any]:
    """Insert one vendor row using controlled fields."""
    supabase = supabase_client.get_supabase_client()
    row = sanitize_vendor_values(values, require_identity=True)
    response = supabase.table("cs_vendors").insert(row).execute()
    rows = list(response.data or [])
    return rows[0] if rows else row


def update_vendor_direct(lookup: str, values: dict[str, Any]) -> dict[str, Any]:
    """Apply controlled vendor updates."""
    supabase = supabase_client.get_supabase_client()
    updates = sanitize_vendor_values(values)
    response = supabase.table("cs_vendors").update(updates).eq(VENDOR_KEY_COLUMN, lookup).execute()
    rows = list(response.data or [])
    if not rows:
        raise RuntimeError(f"Vendor {lookup!r} was not found")
    return rows[0]


def create_candidate_direct(values: dict[str, Any]) -> dict[str, Any]:
    """Insert one candidate row using controlled fields."""
    supabase = supabase_client.get_supabase_client()
    row = sanitize_candidate_values(values, require_identity=True)
    response = supabase.table(discovery_store.DISCOVERY_CANDIDATE_TABLE).insert(row).execute()
    rows = list(response.data or [])
    return rows[0] if rows else row


def update_candidate_direct(lookup: str, values: dict[str, Any]) -> dict[str, Any]:
    """Apply controlled candidate updates."""
    supabase = supabase_client.get_supabase_client()
    updates = sanitize_candidate_values(values)
    response = (
        supabase.table(discovery_store.DISCOVERY_CANDIDATE_TABLE)
        .update(updates)
        .eq(CANDIDATE_KEY_COLUMN, lookup)
        .execute()
    )
    rows = list(response.data or [])
    if not rows:
        raise RuntimeError(f"Candidate {lookup!r} was not found")
    return rows[0]


def create_run_direct(values: dict[str, Any]) -> dict[str, Any]:
    """Insert one pipeline-run row using controlled fields."""
    supabase = supabase_client.get_supabase_client()
    row = sanitize_run_values(values, require_identity=True)
    response = supabase.table(run_store.PIPELINE_RUNS_TABLE).insert(row).execute()
    rows = list(response.data or [])
    return rows[0] if rows else row


def update_run_direct(lookup: str, values: dict[str, Any]) -> dict[str, Any]:
    """Apply controlled pipeline-run updates."""
    supabase = supabase_client.get_supabase_client()
    updates = sanitize_run_values(values)
    response = (
        supabase.table(run_store.PIPELINE_RUNS_TABLE)
        .update(updates)
        .eq(RUN_KEY_COLUMN, lookup)
        .execute()
    )
    rows = list(response.data or [])
    if not rows:
        raise RuntimeError(f"Run {lookup!r} was not found")
    return rows[0]


def delete_row_direct(table: str, key_column: str, lookup: str) -> dict[str, Any]:
    """Delete one row by lookup and return the deleted row when available."""
    supabase = supabase_client.get_supabase_client()
    response = supabase.table(table).delete().eq(key_column, lookup).execute()
    rows = list(response.data or [])
    if not rows:
        raise RuntimeError(f"{table} row {lookup!r} was not found")
    return rows[0]


def build_schema_verification_sql() -> str:
    """Return SQL that inspects required tables and columns."""
    tables = check_supabase.build_required_schema()
    table_names = ", ".join(f"'{item['table']}'" for item in tables)
    return (
        "select table_name, column_name "
        "from information_schema.columns "
        f"where table_schema = 'public' and table_name in ({table_names}) "
        "order by table_name, ordinal_position;"
    )


def build_insert_sql(table: str, values: dict[str, Any]) -> str:
    """Return a guarded SQL insert statement."""
    if not values:
        raise RuntimeError("At least one value is required")
    columns = ", ".join(sorted(values))
    literals = ", ".join(sql_literal(values[column]) for column in sorted(values))
    return f"insert into {table} ({columns}) values ({literals}) returning *;"


def build_update_sql(table: str, key_column: str, lookup: str, values: dict[str, Any]) -> str:
    """Return a guarded SQL update statement."""
    if not values:
        raise RuntimeError("At least one update value is required")
    assignments = ", ".join(f"{column} = {sql_literal(value)}" for column, value in sorted(values.items()))
    return (
        f"update {table} set {assignments} where {key_column} = {sql_literal(lookup)} "
        f"returning *;"
    )


def build_delete_sql(table: str, key_column: str, lookup: str) -> str:
    """Return a guarded SQL delete statement."""
    return f"delete from {table} where {key_column} = {sql_literal(lookup)} returning *;"


def parse_key_values(pairs: list[str]) -> dict[str, Any]:
    """Parse repeated key=value arguments."""
    values: dict[str, Any] = {}
    for pair in pairs:
        key, sep, raw_value = pair.partition("=")
        if not sep or not key.strip():
            raise RuntimeError(f"Invalid --value entry: {pair!r}")
        values[key.strip()] = parse_scalar(raw_value.strip())
    return values


def parse_scalar(value: str) -> Any:
    """Parse a scalar CLI string into a simple Python value."""
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none"}:
        return None
    if value.startswith("[") or value.startswith("{"):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
    if value.lstrip("-").isdigit():
        return int(value)
    return value


def coerce_optional_bool(value: Any) -> bool | None:
    """Coerce a value into a bool or None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    lowered = str(value).strip().lower()
    if lowered in {"true", "1", "yes"}:
        return True
    if lowered in {"false", "0", "no"}:
        return False
    raise RuntimeError(f"Expected a boolean value, got {value!r}")


def coerce_optional_str(value: Any) -> str | None:
    """Return a stripped string or None."""
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def sql_literal(value: Any) -> str:
    """Return a minimal SQL literal."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "ARRAY[" + ", ".join(sql_literal(item) for item in value) + "]"
    text = str(value).replace("'", "''")
    return f"'{text}'"


def sanitize_vendor_values(values: dict[str, Any], *, require_identity: bool = False) -> dict[str, Any]:
    """Return controlled vendor values for CRUD operations."""
    return sanitize_values(
        values,
        allowed_columns=(*VENDOR_MUTABLE_COLUMNS, VENDOR_KEY_COLUMN),
        list_columns={"icp", "use_cases", "lifecycle_stages", "case_studies", "customers", "value_statements", "evidence_urls"},
        bool_columns={"free_trial", "soc2", "include_in_directory", "is_new"},
        nullable_text_columns={"source", "mission", "usp", "pricing", "founded", "raw_description", "confidence", "directory_fit", "directory_category"},
        int_columns=set(),
        required_identity=VENDOR_KEY_COLUMN if require_identity else None,
        required_also={"name"} if require_identity else set(),
    )


def sanitize_candidate_values(values: dict[str, Any], *, require_identity: bool = False) -> dict[str, Any]:
    """Return controlled candidate values for CRUD operations."""
    return sanitize_values(
        values,
        allowed_columns=(*CANDIDATE_MUTABLE_COLUMNS, CANDIDATE_KEY_COLUMN),
        list_columns=set(),
        bool_columns=set(),
        nullable_text_columns={"candidate_title", "candidate_description", "source_query", "source_engine", "candidate_status", "drop_reason"},
        int_columns={"source_rank"},
        required_identity=CANDIDATE_KEY_COLUMN if require_identity else None,
    )


def sanitize_run_values(values: dict[str, Any], *, require_identity: bool = False) -> dict[str, Any]:
    """Return controlled run values for CRUD operations."""
    return sanitize_values(
        values,
        allowed_columns=(*RUN_MUTABLE_COLUMNS, RUN_KEY_COLUMN),
        list_columns=set(),
        bool_columns=set(),
        nullable_text_columns={"started_at", "completed_at", "queries_executed", "run_status", "error_summary"},
        int_columns={"candidate_count", "queued_count", "skipped_existing_count", "enriched_count", "dropped_count", "llm_success_count", "llm_fallback_count"},
        required_identity=RUN_KEY_COLUMN if require_identity else None,
    )


def sanitize_values(
    values: dict[str, Any],
    *,
    allowed_columns: tuple[str, ...] | set[str],
    list_columns: set[str],
    bool_columns: set[str],
    nullable_text_columns: set[str],
    int_columns: set[str],
    required_identity: str | None = None,
    required_also: set[str] | None = None,
) -> dict[str, Any]:
    """Normalize and validate controlled tool values."""
    if not values:
        raise RuntimeError("At least one value is required")
    allowed = set(allowed_columns)
    sanitized: dict[str, Any] = {}
    for key, raw_value in values.items():
        if key not in allowed:
            raise RuntimeError(f"Unsupported field {key!r}")
        if key in list_columns:
            sanitized[key] = coerce_text_list(raw_value)
        elif key in bool_columns:
            sanitized[key] = coerce_optional_bool(raw_value)
        elif key in int_columns:
            sanitized[key] = coerce_optional_int(raw_value)
        elif key in nullable_text_columns or key == required_identity or (required_also and key in required_also):
            sanitized[key] = coerce_optional_str(raw_value)
        else:
            sanitized[key] = raw_value
    required_fields = set(required_also or set())
    if required_identity:
        required_fields.add(required_identity)
    missing_required = [field for field in sorted(required_fields) if not sanitized.get(field)]
    if missing_required:
        raise RuntimeError(f"Missing required field(s): {', '.join(missing_required)}")
    return sanitized


def coerce_text_list(value: Any) -> list[str]:
    """Return a normalized list of strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    return [item.strip() for item in text.split(",") if item.strip()]


def coerce_optional_int(value: Any) -> int | None:
    """Coerce a value into an int or None."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.lstrip("-").isdigit():
        return int(text)
    raise RuntimeError(f"Expected an integer value, got {value!r}")


def _has_direct_schema_access() -> bool:
    if not (os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")):
        return False
    if shutil.which("psql"):
        return True
    try:
        import psycopg  # noqa: F401
    except Exception:
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
