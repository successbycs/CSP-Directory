"""Prove live Supabase schema-admin access by adding and removing a temporary column."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def log(step: str, status: str, **details: object) -> None:
    """Print one structured log line."""
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "step": step,
        "status": status,
        **details,
    }
    print(json.dumps(payload))


def main() -> int:
    """Run the schema add/drop proof."""
    load_dotenv(PROJECT_ROOT / ".env")
    database_url = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL")
    if not database_url:
        log("preflight", "failed", reason="DATABASE_URL or SUPABASE_DB_URL is required")
        return 1

    try:
        import psycopg
    except Exception as error:
        log("preflight", "failed", reason="psycopg is required", error=str(error))
        return 1

    column_name = f"tmp_schema_proof_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    table_name = "public.cs_vendors"
    log("connect", "starting", table=table_name, column=column_name)

    try:
        with psycopg.connect(database_url, autocommit=True) as connection:
            log("connect", "ok", host=connection.info.host, dbname=connection.info.dbname)
            with connection.cursor() as cursor:
                add_sql = f"alter table {table_name} add column {column_name} text;"
                log("alter_add", "starting", sql=add_sql)
                cursor.execute(add_sql)
                log("alter_add", "ok")

                cursor.execute(
                    """
                    select 1
                    from information_schema.columns
                    where table_schema = 'public'
                      and table_name = 'cs_vendors'
                      and column_name = %s
                    """,
                    (column_name,),
                )
                exists_after_add = cursor.fetchone() is not None
                log("verify_add", "ok" if exists_after_add else "failed", exists=exists_after_add)
                if not exists_after_add:
                    return 1

                drop_sql = f"alter table {table_name} drop column {column_name};"
                log("alter_drop", "starting", sql=drop_sql)
                cursor.execute(drop_sql)
                log("alter_drop", "ok")

                cursor.execute(
                    """
                    select 1
                    from information_schema.columns
                    where table_schema = 'public'
                      and table_name = 'cs_vendors'
                      and column_name = %s
                    """,
                    (column_name,),
                )
                exists_after_drop = cursor.fetchone() is not None
                log("verify_drop", "ok" if not exists_after_drop else "failed", exists=exists_after_drop)
                if exists_after_drop:
                    return 1
    except Exception as error:
        log("proof", "failed", error=type(error).__name__, detail=str(error))
        return 1

    log("proof", "ok", table=table_name, column=column_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
