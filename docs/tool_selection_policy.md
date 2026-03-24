# Tool Selection Policy

## Primary Surface

**Python** (`.venv`) is the only approved execution surface for this project.

## Selection Order

1. Check `tools/capability_registry.json` — use an approved capability if one fits
2. Use an existing script in `scripts/` if it covers the need
3. Create a new Python script in `scripts/` scoped to the milestone

## Surfaces

| Surface | Use case |
|---------|----------|
| `python` | All pipeline execution, schema migration, enrichment, persistence |
| `supabase` (via API) | Schema inspection and upsert only |
| `apify` (via API) | Vendor site crawling only |

## No Workflow Layer

This project does not use n8n or any workflow orchestration tool. All orchestration is Python.

## Research

If external information is needed, use `scripts/` to fetch it via HTTP or Apify. Do not request external web research capability unless the milestone explicitly requires it.
