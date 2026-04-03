#!/usr/bin/env python3
"""Verify Supabase pgvector extension is enabled and M76 tables exist.

Exit 0 — pgvector enabled, vendor_pages and vendor_page_embeddings tables exist
Exit 1 — any check fails
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from services.persistence import supabase_client as sc


def main() -> int:
    if not sc.is_configured():
        print("FAIL: Supabase not configured — check SUPABASE_URL and SUPABASE_KEY in .env")
        return 1

    client = sc.get_supabase_client()
    failures: list[str] = []

    # 1. pgvector extension
    try:
        result = client.rpc("pg_extension_check", {}).execute()
    except Exception:
        pass  # RPC may not exist — fall back to direct query

    try:
        result = client.table("pg_extension").select("extname").eq("extname", "vector").limit(1).execute()
        if not result.data:
            failures.append("pgvector extension not enabled — run: CREATE EXTENSION IF NOT EXISTS vector;")
        else:
            print("  ✓ pgvector extension enabled")
    except Exception as exc:
        # Supabase may not expose pg_extension via REST — try a different check
        try:
            # If vendor_page_embeddings exists with vector column, pgvector is enabled
            client.table("vendor_page_embeddings").select("id").limit(1).execute()
            print("  ✓ pgvector extension enabled (inferred from table existence)")
        except Exception as exc2:
            failures.append(f"Cannot verify pgvector: {exc2}")

    # 2. vendor_pages table
    try:
        client.table("vendor_pages").select("id").limit(1).execute()
        print("  ✓ vendor_pages table exists")
    except Exception as exc:
        failures.append(f"vendor_pages table missing or inaccessible: {exc}")

    # 3. vendor_page_embeddings table
    try:
        client.table("vendor_page_embeddings").select("id").limit(1).execute()
        print("  ✓ vendor_page_embeddings table exists")
    except Exception as exc:
        failures.append(f"vendor_page_embeddings table missing or inaccessible: {exc}")

    # 4. crawl_*_result columns exist on cs_vendors
    required_cols = [
        "crawl_tier1_result", "crawl_tier2_result", "crawl_tier3_result",
        "crawl_datagma_result", "crawl_g2_result", "crawl_llm_result", "source_field_map",
    ]
    try:
        result = client.table("cs_vendors").select(",".join(required_cols)).limit(1).execute()
        print(f"  ✓ All {len(required_cols)} crawl_*_result columns exist on cs_vendors")
    except Exception as exc:
        failures.append(f"crawl_*_result columns missing from cs_vendors: {exc}")

    if failures:
        print("\nFAIL: The following checks failed:")
        for f in failures:
            print(f"  ✗ {f}")
        print("\nRun: python3 scripts/apply_schema_migration.py")
        return 1

    print("\nOK: All pgvector + schema checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
