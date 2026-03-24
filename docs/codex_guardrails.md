# Guardrails

## Source Of Truth

Always align with:
- `docs/product_design.md`
- `docs/architecture.md`
- `milestone_registry.json`
- `project_state.json`

## Implementation Rules

- complete the active milestone only
- inspect the repo before changing code
- keep changes as small as possible
- do not refactor unrelated code
- prefer Python scripts in `.venv` as the execution surface
- scripts live in `scripts/`, services in `services/`
- never modify milestone_registry.json status without proof

## Safety Rules

- do not mark milestones complete without verification evidence
- do not assume Supabase columns exist — always check with `scripts/apply_schema_migration.py`
- do not skip verification steps
- proof artifacts go in `runs/proofs/`

## Delegation Rules

- the controller owns execution of the role sequence
- use controller-owned role packets as the contract for delegated work
- do not write outside the declared write scope
