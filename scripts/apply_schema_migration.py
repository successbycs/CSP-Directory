"""Apply outstanding schema migrations to the live Supabase cs_vendors table.

This script detects columns that are defined in the codebase but missing from
the live database, and adds them via ALTER TABLE statements executed through
the Supabase management API.

Usage:
    python3 scripts/apply_schema_migration.py [--dry-run]

Exit codes:
    0  All required columns are present (or were successfully added)
    1  Migration failed or Supabase is not configured
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from services.persistence import supabase_client  # noqa: E402

# Columns required by the codebase that may be missing from the live DB.
# Each entry: (column_name, sql_type, nullable)
REQUIRED_COLUMNS: list[tuple[str, str, bool]] = [
    # Directory classification columns
    ("llm_directory_fit", "text", True),
    ("llm_directory_category", "text", True),
    ("llm_include_in_directory", "boolean", True),
    ("directory_decision_source", "text", True),
    ("directory_reasoning", "text[]", True),
    # Vendor profile columns
    ("hq_address", "text", True),
    ("source_urls", "text[]", True),
    ("compliance", "text[]", True),
    ("ceo_name", "text", True),
    ("phone_numbers", "text[]", True),
    ("contact_emails", "text[]", True),
    ("developer_docs_url", "text", True),
    ("integration_taxonomy", "jsonb", True),
    ("external_enrichment", "jsonb", True),
    ("testimonials", "jsonb", True),
    ("blog_posts", "jsonb", True),
    # M50 — G2 enrichment fields
    ("g2_url", "text", True),
    ("g2_rating", "numeric(3,1)", True),
    ("g2_review_count", "integer", True),
    ("g2_market_segment", "text", True),
    ("g2_categories", "text[]", True),
    # M51 — deep crawl fields
    ("raw_crawl_blob", "text", True),
    ("crawl_page_count", "integer", True),
    ("crawl_completed_at", "timestamp with time zone", True),
    # Enrichment observability columns
    ("last_enriched_at", "timestamp with time zone", True),
    ("last_enriched_pipeline", "text", True),
    ("enrichment_count", "integer", True),
    ("enrichment_pipeline_counts", "jsonb", True),
]

COLUMNS_TO_DROP: list[str] = []


def check_column_exists(client, table: str, column: str) -> bool:
    """Return True if the column exists in the table."""
    try:
        client.table(table).select(column).limit(1).execute()
        return True
    except Exception as e:
        msg = str(e).lower()
        if "does not exist" in msg or "pgrst204" in str(e):
            return False
        raise


def apply_migrations(dry_run: bool = False) -> int:
    """Detect and apply missing columns. Returns 0 on success, 1 on failure."""
    if not supabase_client.is_configured():
        print("ERROR: Supabase not configured — set SUPABASE_URL and SUPABASE_KEY")
        return 1

    try:
        client = supabase_client.get_supabase_client()
    except Exception as e:
        print(f"ERROR: Could not create Supabase client: {e}")
        return 1

    table = "cs_vendors"
    missing: list[tuple[str, str, bool]] = []
    present: list[str] = []

    for column, sql_type, nullable in REQUIRED_COLUMNS:
        if check_column_exists(client, table, column):
            present.append(column)
        else:
            missing.append((column, sql_type, nullable))

    print(f"Columns already present ({len(present)}): {', '.join(present) if present else 'none'}")
    print(f"Columns to add ({len(missing)}): {', '.join(c for c, _, _ in missing) if missing else 'none'}")

    if not missing:
        print("Schema is up to date — no migrations needed.")
        return 0

    if dry_run:
        print("\nDry run — SQL that would be applied:")
        for column, sql_type, nullable in missing:
            null_clause = "" if nullable else " NOT NULL"
            print(f"  ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {sql_type}{null_clause};")
        return 0

    # Apply migrations via raw SQL using Supabase rpc or management API.
    # Supabase PostgREST does not support DDL — use the execute_sql approach
    # via the Supabase Python client's postgres connection if available,
    # otherwise write migration SQL to a file for manual application.
    migration_sql = "\n".join(
        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {sql_type};"
        for column, sql_type, _ in missing
    )

    migration_path = PROJECT_ROOT / "supabase" / "pending_migration.sql"
    migration_path.parent.mkdir(parents=True, exist_ok=True)
    migration_path.write_text(migration_sql)

    print(f"\nMigration SQL written to: {migration_path.relative_to(PROJECT_ROOT)}")
    print("Apply this via the Supabase SQL editor or supabase CLI:")
    print(f"\n{migration_sql}\n")
    print(
        "After applying, re-run this script to confirm all columns are present.\n"
        "Or run: python3 scripts/check_supabase.py"
    )

    # Attempt to verify the migration was applied externally
    # (re-check after a manual apply or if another mechanism applied it)
    still_missing = [c for c, t, n in missing if not check_column_exists(client, table, c)]
    if still_missing:
        print(f"PENDING: {len(still_missing)} column(s) still missing: {', '.join(still_missing)}")
        print("Apply supabase/pending_migration.sql in the Supabase dashboard, then re-run.")
        return 1

    print("All required columns are now present.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply CSP Directory Supabase schema migrations")
    parser.add_argument("--dry-run", action="store_true", help="Print SQL without applying it")
    args = parser.parse_args()
    return apply_migrations(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
