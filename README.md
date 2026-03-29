# CSP Directory

AI-powered vendor intelligence directory for the Customer Success ecosystem. Discovers, enriches, and classifies AI-enabled CS vendors against the SuccessByCS 8-stage lifecycle framework.

The canonical dataset lives in Supabase. The public directory is served from exported JSON artifacts.

## Setup

Requires Python 3.12+.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env  # then fill in keys
```

Required environment variables:

- `OPENAI_API_KEY` — LLM extraction
- `SUPABASE_URL` + `SUPABASE_KEY` — server-side Supabase persistence
- `GOOGLE_SHEETS_ID` + `GOOGLE_SHEETS_CREDENTIALS_JSON` — optional, ops review layer

Runtime config lives in `config/pipeline_config.json` (discovery, enrichment, LLM, export) and `config/scheduler.toml` (scheduler timing).

## Run Tests

```sh
.venv/bin/python -m pytest
```

Default test runs exclude `@pytest.mark.live` network canaries. Run them explicitly with:

```sh
.venv/bin/python -m pytest -m live
```

## Run the Pipeline

```sh
.venv/bin/python scripts/run_pipeline.py "ai customer success platform"
```

Run the scheduler:

```sh
.venv/bin/python -m services.pipeline.scheduler
.venv/bin/python -m services.pipeline.scheduler --run-now discovery
.venv/bin/python -m services.pipeline.scheduler --run-now digest
```

Scheduling note:
- Keep scheduled discovery/enrichment weekly by default (`config/scheduler.toml`), and use manual/admin-triggered runs for extra enrichment to control Apify spend.

## Checks and Exports

Supabase connectivity and schema check:

```sh
.venv/bin/python scripts/check_supabase.py
```

Apply the schema if needed:

```sh
# run supabase/core_persistence_schema.sql in the Supabase SQL editor
```

Integration diagnostics:

```sh
.venv/bin/python scripts/check_integrations.py
```

Export the public directory dataset:

```sh
.venv/bin/python scripts/export_directory_dataset.py
# outputs/directory_dataset.json
```

Export the search visibility report:

```sh
.venv/bin/python scripts/export_search_visibility_report.py
# outputs/search_visibility_report.json
# outputs/search_visibility_report.html
```

Admin vendor update:

```sh
.venv/bin/python scripts/admin_update_vendor.py
```

## Pipeline Architecture

1. `services/discovery/` — finds vendor candidates from web search
2. `services/enrichment/` — fetches and explores vendor websites
3. `services/extraction/` — converts pages into structured `VendorIntelligence`
4. `services/persistence/` — upserts to Supabase, tracks pipeline runs
5. `services/export/` — builds directory dataset, vendor review, and search visibility artifacts
6. `services/pipeline/` — orchestrates the end-to-end flow
7. `services/admin/` — operator-facing admin actions and API

## Frontend

Static pages served from `docs/website/`:

- `landing.html` — public vendor directory
- `vendor.html` — individual vendor profile
- `admin.html` — operator review surface
- `ops-console.html` — pipeline run console

## Tool Registry

`tools/tool_registry.json` declares approved integrations:

- `tools/supabase/` — direct Supabase CRUD and schema operations
- `tools/external_enrichment/` — third-party enrichment connectors
- `tools/n8n/` — n8n workflow surface

## Autonomous Development

This repo is managed by the [Autonomous Framework](https://github.com/successbycs/Autonomous-Framework). Milestones are tracked in `milestone_registry.json`.

Run AF cycles against this repo using the `--root` flag:

```sh
python3 /path/to/Autonomous-Framework/scripts/autonomous_controller.py \
  --root /home/chris/projects/CSP-Directory status

python3 /path/to/Autonomous-Framework/scripts/autonomous_controller.py \
  --root /home/chris/projects/CSP-Directory run-cycle
```

Current focus: `M35` — Human test and operator validation. Fix milestones will be added after the review pass.

## Docs

- `docs/product_design.md` — full product architecture and data model
- `docs/architecture.md` — system architecture
- `docs/lead_capture_architecture.md` — lead capture behaviour, admin panel wiring, and data contract
- `docs/project_brain.md` — operator knowledge base
- `docs/solution_enhancement_workflow.md` — enhancement request workflow
- `docs/production_checklist.md` — production deployment checklist
