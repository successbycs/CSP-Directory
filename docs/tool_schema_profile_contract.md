# Tool Schema Profile Contract

## Overview

Schema profiles are not used in this project. All schema validation is handled by the Python pipeline services directly.

## Supabase Schema

The live schema for `cs_vendors` is validated by `scripts/apply_schema_migration.py`.

Run `scripts/apply_schema_migration.py` to detect and apply missing columns before any milestone that writes to Supabase.

## No Schema Profile Files

There are no schema profile files in `tools/schema_profiles/`. Schema state is the source of truth in the live Supabase table.
