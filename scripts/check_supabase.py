"""Beginner-friendly Supabase schema and connectivity check."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.discovery import discovery_store
from services.persistence import run_store
from services.persistence import search_visibility_store
from services.persistence import supabase_client

SCHEMA_SQL_PATH = PROJECT_ROOT / "supabase" / "core_persistence_schema.sql"


def build_required_schema() -> list[dict[str, Any]]:
    """Return the required tables and columns for core persistence paths."""
    vendor_columns: list[str] = []
    for column in (
        *supabase_client.get_vendor_profile_columns(),
        *supabase_client.get_vendor_write_columns(),
    ):
        if column not in vendor_columns:
            vendor_columns.append(column)
    return [
        {
            "table": "cs_vendors",
            "columns": vendor_columns,
            "purpose": "vendor persistence writes plus export and admin vendor visibility",
        },
        {
            "table": discovery_store.DISCOVERY_CANDIDATE_TABLE,
            "columns": list(discovery_store.DISCOVERY_CANDIDATE_COLUMNS),
            "purpose": "candidate persistence and admin candidate visibility",
        },
        {
            "table": run_store.PIPELINE_RUNS_TABLE,
            "columns": list(run_store.PIPELINE_RUN_COLUMNS),
            "purpose": "pipeline run tracking and admin run visibility",
        },
        {
            "table": search_visibility_store.BUYER_SEARCH_QUERY_TABLE,
            "columns": list(search_visibility_store.get_buyer_search_query_columns()),
            "purpose": "buyer-role prompt persistence for search visibility reporting",
        },
        {
            "table": search_visibility_store.BUYER_SEARCH_RESULT_TABLE,
            "columns": list(search_visibility_store.get_buyer_search_result_columns()),
            "purpose": "ranked search visibility persistence for operator reporting",
        },
    ]


def main() -> int:
    """Run the Supabase connectivity and schema check."""
    load_dotenv(PROJECT_ROOT / ".env")

    if not supabase_client.is_configured():
        print("Supabase config missing: set SUPABASE_URL and SUPABASE_KEY.")
        return 1

    try:
        client = supabase_client.get_supabase_client()
    except Exception as error:
        print(f"Supabase client creation failed: {error}")
        return 1

    results = []
    missing_tables: list[str] = []
    missing_columns: list[str] = []
    other_errors: list[str] = []

    for table_check in build_required_schema():
        result = check_table(client, table_check["table"], table_check["columns"])
        result["purpose"] = table_check["purpose"]
        results.append(result)
        if result["status"] == "missing_table":
            missing_tables.append(table_check["table"])
        if result["status"] == "missing_columns":
            missing_columns.extend(f"{table_check['table']}.{column}" for column in result["missing_columns"])
        if result["status"] == "error":
            other_errors.append(table_check["table"])

    print(json.dumps({"tables": results}, indent=2))

    if missing_tables or missing_columns or other_errors:
        print(
            "Supabase schema check failed: "
            f"{len(missing_tables)} missing table(s), "
            f"{len(missing_columns)} missing column(s), "
            f"{len(other_errors)} connectivity/unknown error(s)."
        )
        print(f"Apply the repo-owned schema fix in: {SCHEMA_SQL_PATH.relative_to(PROJECT_ROOT)}")
        return 1

    print("Supabase schema check succeeded.")
    return 0


def check_table(client: Any, table: str, columns: list[str]) -> dict[str, Any]:
    """Check whether one table and its required columns are available."""
    remaining_columns = list(columns)
    missing_columns: list[str] = []

    while remaining_columns:
        result = _check_table_once(client, table, remaining_columns)
        if result["status"] == "ok":
            return {
                "table": table,
                "status": "missing_columns" if missing_columns else "ok",
                "missing_columns": missing_columns,
                "error": result["error"],
            }
        if result["status"] == "missing_columns" and result["missing_columns"]:
            newly_missing = [column for column in result["missing_columns"] if column not in missing_columns]
            if not newly_missing:
                return result
            missing_columns.extend(newly_missing)
            remaining_columns = [column for column in remaining_columns if column not in newly_missing]
            continue
        if result["status"] == "missing_columns" and missing_columns:
            return {
                "table": table,
                "status": "missing_columns",
                "missing_columns": missing_columns,
                "error": result["error"],
            }
        if result["status"] == "error" and missing_columns:
            return {
                "table": table,
                "status": "missing_columns",
                "missing_columns": missing_columns,
                "error": result["error"],
            }
        return result

    return {
        "table": table,
        "status": "missing_columns",
        "missing_columns": missing_columns,
        "error": "",
    }


def _check_table_once(client: Any, table: str, columns: list[str]) -> dict[str, Any]:
    """Check one table once with a specific column set."""
    try:
        client.table(table).select(",".join(columns)).limit(1).execute()
    except Exception as error:
        error_message = str(error)
        error_code = _error_code(error)
        missing_columns = [column for column in columns if _error_mentions_missing_column(error_message, table, column)]
        if error_code == "PGRST204" or missing_columns:
            return {
                "table": table,
                "status": "missing_columns",
                "missing_columns": missing_columns,
                "error": error_message,
            }
        if error_code == "PGRST205" or _error_mentions_missing_table(error_message, table):
            return {
                "table": table,
                "status": "missing_table",
                "missing_columns": [],
                "error": error_message,
            }
        return {
            "table": table,
            "status": "error",
            "missing_columns": [],
            "error": error_message,
        }

    return {
        "table": table,
        "status": "ok",
        "missing_columns": [],
        "error": "",
    }


def _error_code(error: Exception) -> str:
    direct_code = getattr(error, "code", "")
    if isinstance(direct_code, str) and direct_code.strip():
        return direct_code.strip()
    for arg in getattr(error, "args", ()):
        if isinstance(arg, dict):
            code = arg.get("code")
            if isinstance(code, str) and code.strip():
                return code.strip()
    return ""


def _error_mentions_missing_table(error_message: str, table: str) -> bool:
    lowered = error_message.lower()
    table_lowered = table.lower()
    if f"column {table_lowered}." in lowered:
        return False
    return all(marker in lowered for marker in [table_lowered, "does not exist"]) or "could not find the table" in lowered


def _error_mentions_missing_column(error_message: str, table: str, column: str) -> bool:
    lowered = error_message.lower()
    table_lowered = table.lower()
    column_lowered = column.lower()
    return (
        f"column {table_lowered}.{column_lowered} does not exist" in lowered
        or f"could not find the '{column_lowered}' column of '{table_lowered}'" in lowered
    )


if __name__ == "__main__":
    raise SystemExit(main())
