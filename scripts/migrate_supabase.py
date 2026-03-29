"""
Migrate all data from old Supabase project to new one.

Usage:
    python3 scripts/migrate_supabase.py

Prerequisites:
    1. Run supabase/migrate_to_new_project.sql in the new project SQL editor first
    2. Set NEW_SUPABASE_URL and NEW_SUPABASE_KEY in .env (service role key preferred)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from supabase import create_client

OLD_URL = os.environ["SUPABASE_URL"]
OLD_KEY = os.environ["SUPABASE_KEY"]
NEW_URL = os.environ["NEW_SUPABASE_URL"]
NEW_KEY = os.environ["SERVICE_ROLE_KEY"]

BATCH_SIZE = 20

TABLES = [
    # (table_name, conflict_key, strip_id)
    ("cs_vendors", "website", True),
    ("discovery_candidates", "candidate_domain", False),
    ("pipeline_runs", "run_id", False),
]


def migrate_table(old, new, table: str, conflict_key: str, strip_id: bool) -> None:
    print(f"\nMigrating {table}...")
    result = old.table(table).select("*").execute()
    rows = result.data
    print(f"  Found {len(rows)} rows")
    if not rows:
        return

    if strip_id:
        for row in rows:
            row.pop("id", None)

    total = len(rows)
    inserted = 0
    errors = []
    for i in range(0, total, BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        try:
            new.table(table).upsert(batch, on_conflict=conflict_key).execute()
            inserted += len(batch)
            print(f"  [{inserted}/{total}] inserted")
        except Exception as e:
            print(f"  ERROR on batch {i}-{i+BATCH_SIZE}: {e}")
            errors.append(str(e))

    print(f"  Done: {inserted}/{total} rows")
    if errors:
        for e in errors:
            print(f"  ERROR: {e}")


def migrate() -> None:
    old = create_client(OLD_URL, OLD_KEY)
    new = create_client(NEW_URL, NEW_KEY)

    for table, conflict_key, strip_id in TABLES:
        migrate_table(old, new, table, conflict_key, strip_id)

    # Verify
    print("\nVerification:")
    for table, _, _ in TABLES:
        check = new.table(table).select("*", count="exact").execute()
        print(f"  {table}: {check.count} rows")


if __name__ == "__main__":
    migrate()
