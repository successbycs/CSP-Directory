# Supabase Tool

This tool defines the repo-owned execution boundary for Supabase operations during development.

Scope:

- schema inspection
- schema application
- schema verification
- controlled create/read/update/delete for vendors, candidates, and runs

Source of truth:

- `supabase/core_persistence_schema.sql`

Execution model:

- `tools/supabase/tool_spec.json` defines the allowed operations and role access model
- `tools/supabase/cli.py` is the executable entrypoint for direct operations
- direct repo-owned scripts and SQL are the execution path
- real Supabase credentials, broker credentials, service-role keys, and database URLs must not be committed in repo files
- direct execution must read secrets from environment variables or other untracked local operator configuration
- example commands and configs must use placeholders only

Current operation groups:

- schema admin: `inspect_schema`, `verify_schema`, `apply_schema`
- vendor data CRUD: `read_vendors`, `create_vendor`, `update_vendor`, `delete_vendor`
- candidate data CRUD: `read_candidates`, `create_candidate`, `update_candidate`, `delete_candidate`
- run data CRUD: `read_runs`, `create_run`, `update_run`, `delete_run`

Safety rules:

- write-capable operations require approval when the environment or tool policy says so
- reviewer and QA should stay read-only
- production use is out of scope for this tool definition unless a future milestone expands it explicitly
