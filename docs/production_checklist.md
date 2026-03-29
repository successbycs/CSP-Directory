# Production Checklist

Use this sequence to move CSP Directory to production cleanly.

## 1. Local repo verification

Run from the repo root:

```bash
.venv/bin/python scripts/autonomous_audit.py
.venv/bin/python -m pytest
```

Expected result:
- audit passes
- pytest passes without live-network canaries

Optional explicit live tests:

```bash
.venv/bin/python -m pytest -m live
```

Use this only when you want to verify external dependencies such as Tracxn from a networked environment.

## 2. Environment setup

Create `.env` from `.env.example` and fill the required keys.

Minimum local pipeline/admin env:
- `OPENAI_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `N8N_BASE_URL` if n8n-backed enrichment/discovery is enabled

Optional:
- `GOOGLE_SHEETS_ID`
- `GOOGLE_SHEETS_CREDENTIALS_JSON`
- `GITHUB_TOKEN`
- `GITHUB_PUBLISH=true`
- `RAPIDAPI_KEY`
- `RAPIDAPI_G2_HOST`

## 3. Supabase schema

Before running the live pipeline or lead capture, ensure the target Supabase project has the repo schema:

```bash
.venv/bin/python scripts/check_supabase.py
```

If the schema is missing or incomplete:
- run [supabase/core_persistence_schema.sql](/home/chris/projects/CSP-Directory/supabase/core_persistence_schema.sql) in the Supabase SQL editor
- apply any pending repo-owned migration SQL that your current rollout requires

If you are moving to a new Supabase project:
- run [supabase/migrate_to_new_project.sql](/home/chris/projects/CSP-Directory/supabase/migrate_to_new_project.sql)
- then use [scripts/migrate_supabase.py](/home/chris/projects/CSP-Directory/scripts/migrate_supabase.py)

## 4. Vercel project

Create or connect the Vercel project to this repo.

Required settings:
- Framework preset: Other
- Output directory: `docs/website`

Required Vercel environment variables:
- `SUPABASE_URL`
- `SUPABASE_KEY`

Important:
- `SUPABASE_KEY` is server-side only in this setup
- do not expose it in browser code
- the public pages should call `/api/lead-capture` relatively so preview deploys and production both work

## 5. Public site validation

After a Vercel deploy:

1. Open `/`
2. Open `/browse`
3. Confirm directory data loads from `docs/website/data/directory_dataset.json`
4. Submit a lead-capture form
5. Confirm the row appears in Supabase `lead_captures`

## 6. Admin and pipeline host

The admin API, enrichment pipeline, and n8n are intentionally private and run outside Vercel.

Start the admin API:

```bash
.venv/bin/python -m services.admin.admin_api
```

If using Docker/n8n locally, also verify the private operator stack is reachable before running enrichment.

## 7. Publish workflow

To update live vendor data:

1. Run the enrichment/discovery pipeline on the private host
2. Publish the dataset from the admin surface or export it directly
3. Ensure `docs/website/data/directory_dataset.json` is updated
4. Commit and push
5. Let Vercel auto-deploy

Useful commands:

```bash
.venv/bin/python scripts/export_directory_dataset.py
.venv/bin/python scripts/pipeline_health_check.py
```

## 8. Release gate

Do not call production ready until all of these are true:
- audit passes
- default pytest passes
- Supabase schema check passes against the target project
- Vercel env vars are set
- `/api/lead-capture` works on the deployed hostname
- a real lead shows up in `lead_captures`
- the latest dataset is committed and deployed
