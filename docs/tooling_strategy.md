# Tooling Strategy

## Execution Surface

The primary execution surface for this project is **Python** running in `.venv`.

- pipeline scripts: `scripts/`
- pipeline services: `services/`
- config: `config/`
- proofs: `runs/proofs/`

All milestone implementation work runs Python scripts directly. There is no n8n workflow layer in this project.

## Tool Registry

See `tools/tool_registry.json` for registered tools:
- `supabase` — schema inspection, migration, and CRUD
- `external_enrichment` — Apify-backed vendor site crawling
- `agent_cli` — AI backend execution for AF roles

## Capability Registry

See `tools/capability_registry.json` for approved capabilities:
- `database_persistence` — Supabase schema migration and upsert
- `data_pipeline` — full discovery + enrichment + persistence pipeline
- `llm_extraction` — OpenAI-backed structured field extraction

## Selection Policy

1. Check `tools/capability_registry.json` for an approved capability matching the milestone goal
2. Prefer existing Python scripts in `scripts/` before creating new ones
3. Only create new scripts when no existing script covers the required behaviour
