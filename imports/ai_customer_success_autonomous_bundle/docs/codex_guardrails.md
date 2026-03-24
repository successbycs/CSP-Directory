# Codex Guardrails

## Purpose
These rules constrain autonomous development so progress remains safe, reviewable, and aligned with product intent.

## Non-negotiables
- Read `docs/product_design.md`, `docs/architecture.md`, and `docs/implementation_plan.md` before implementing milestones.
- Do not redesign the architecture unless a milestone explicitly requires it.
- Deterministic extraction is the baseline safety net.
- Lifecycle stage assignment remains deterministic in Python.
- LLM enrichment is optional, bounded, and must fail safely.
- Supabase is the source of truth.
- Google Sheets is an ops/export layer only.
- Public directory pages are static for v1.

## Implementation rules
- Complete the highest unfinished milestone unless told otherwise.
- Inspect the current repo state before making changes.
- Keep changes bounded to the milestone.
- Prefer simple, explicit code over clever abstractions.
- Do not add dependencies unless necessary.
- Do not hard-code machine-specific paths.
- Keep config-driven behavior in `config/pipeline_config.json`.

## Verification rules
After implementation:
- Run milestone verification commands
- Run relevant tests
- Produce expected artifacts
- Report changed files, risks, and next step

## Safety rules
- Do not let empty or weak LLM values overwrite strong deterministic data.
- Do not allow malformed LLM output to break the pipeline.
- Do not silently change export schemas.
- Do not ship admin write actions without explicit logging.
- Do not expose internal admin endpoints publicly without clear warning.

## Review rules
When acting as reviewer or QA agent:
- Be repo-specific
- Cite files where possible
- Call out doc vs implementation mismatches
- Call out silent failure risks
