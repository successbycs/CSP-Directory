# Project Brain

This file is a short operational memory for the repository. It should stay concise and current.

## System Identity

- repository: `AI_CustomerSuccess`
- product type: vendor-first AI Customer Success intelligence pipeline
- canonical persistence: Supabase
- public serving layer: exported JSON artifacts
- internal operator layer: admin/API plus fallback artifacts when persistence is unavailable

## Active Runtime Surfaces

- primary pipeline config: `config/pipeline_config.json`
- scheduler config: `config/scheduler.toml`
- milestone plan: `docs/implementation_plan.md`
- autonomous loop definition: `docs/autonomous_dev_loop.md`
- latest session context: `docs/session_context_2026-03-21.md`
- local controller state: `project_state.json`, `milestone_registry.json`, `runs/run_history.json`

## Autonomous Control Plane

- controller CLI: `scripts/autonomous_controller.py`
- cycle wrapper: `scripts/run_autonomous_cycle.sh`
- repo-native role runner: `scripts/local_agent_runner.py`
- verification script: `scripts/verify_project.sh`
- container proof script: `scripts/prove_container_autonomous_loop.sh`
- audit script: `scripts/autonomous_audit.py`
- milestone audit runner: `scripts/milestone_auditor.py`
- role CLI adapter: `tools/agent_cli/cli.py`
- tool registry: `tools/tool_registry.json`

## Current Operating Assumptions

- current active milestone is `M42` (expand vendor catalog to 50+ vendors)
- as of 2026-03-26: 48 vendors included, 2 short of 50+ target
- production deployment live at vendors.successbycs.com (Vercel, auto-deploy from GitHub main)
- pipeline runs via `python3 scripts/discover_vendors.py` (4-step: discover → enrich → health check → export)
- all pipeline and export tests pass (50 tests green)
- three-tier field taxonomy in effect: `scraped_` / `llm_` / `operator_` (M59)
- confidence gate: medium + high included; low excluded (except admin_override)
- lifecycle stage gate: vendors in directory must have at least one lifecycle stage
- directory_category='other' excluded from public export (M69)
- n8n routes all Apify calls (Google Search + Website Content Crawler) via webhook
- Supabase table: `cs_vendors` — apply_schema_migration.py is the safe migration path
- next pending milestones in priority order: M42, M48, M49, M50, M51, M52, M60–M68

























- milestone order is controlled by `milestone_registry.json`
- `current_focus` in `project_state.json` is the active milestone for controller commands
- `controller_policy` in `project_state.json` controls same-milestone retry limits, stop conditions, and whether milestone closure is blocked until the closeout-audit backend is available
- `delegation_policy` in `project_state.json` controls delegated task contracts, write-scope requirements, and default serial execution
- milestone closure requires verification plus recorded review and QA outcomes
- milestone completion should trigger the `Closeout Auditor`; when an audit backend is available, completion should stand only if the closeout audit succeeds
- historical audit gaps are filled by the manual `Backfill Auditor`
- `AUTONOMOUS_AGENT_RUNNER` is optional; without it, `scripts/local_agent_runner.py` still generates structured local role packets, but those packets are blocked evidence until a real role backend or human follow-up completes the step
- `project_state.json` now carries the canonical repo-owned `agent_runner.cli_command`, and `.env` plus shell exports act as overrides rather than the only source of truth for `AUTONOMOUS_AGENT_CLI`
- `AUTONOMOUS_AGENT_CLI` can still point at a local AI CLI that reads JSON from stdin and returns JSON on stdout; the repo-native runner will capture that structured result
- `tools/agent_cli/cli.py` is the canonical repo-native role CLI; for `builder` packets it invokes `codex exec` so the builder is agentic and can actually change the repo
- `AUTONOMOUS_BUILDER_CLI` may override the mutating builder backend separately from the read-only evaluator roles
- `scripts/openai_agent_cli.py` remains as a compatibility path while the tool entrypoint is adopted
- `M13B`, `M13C`, `M13D`, and `M13E` are complete
- `supabase/core_persistence_schema.sql` is now the repo-owned schema contract for the core Supabase tables used by exports, candidate persistence, and run tracking
- `M13C` defines the reusable repo pattern for `tools/`, tool registry schema, role-based tool access, and the first `tools/supabase/` capability layer
- `M13D` is the follow-on capability milestone that makes the Supabase tool executable through direct repo-owned access
- `M13E` adds a read-only prework phase ahead of planner/builder so each iteration starts with a current gap map and verification-focused prep summary
- role packets should include declared tools for the current milestone and role when the registry is present
- normal product runs are expected to use LLM extraction by default when configuration is valid; deterministic extraction is the resilience fallback and should remain visible to operators when used

## Known Gaps

- several milestone verification steps still require manual/runtime checks
- container and devcontainer parity are now proven through the rebuilt Docker image and a devcontainer-equivalent workspace run
- `M07` is complete again, and the live persistence schema is now aligned through `M15`
- the repo now has a tool registry and executable `tools/supabase/` capability layer, and direct schema-admin access is available through the configured database URL
- `M15` is complete; focus has returned to the product milestones starting with `M08`
- `M08` is complete; the public directory dataset is non-empty again under live Supabase-backed runs, and focus has advanced to `M09`
- `M09` is complete; the admin UI, JSON visibility endpoints, and include/exclude operator actions are all proven against the live stack
- `M10` is complete; run tracking and both scheduler smoke paths are now proven from the current environment
- `M14` is complete; the container image and devcontainer-equivalent workspace both pass the full test suite
- `M16` is complete; a fresh runtime pass regenerated outputs, served the preview surfaces, and kept warnings visible instead of silent
- `M30` is complete; staged external enrichment now has a repo-owned tool contract, connector registry, provenance fields, and review/export summaries
- `M31` is complete; help, support, and developer-docs surfaces are explicitly discovered and stored separately from general contact pages
- `M20` through `M31` now capture the next product expansion arc: structured case studies, leadership/contact intelligence, canonical identity validation, buyer search intent, lead-magnet conversion, lead capture and follow-up operations, code-owned editorial governance, multi-product modeling, integration taxonomy, render proof, proof artifact persistence, external enrichment connectors, and help-center detection
- `M35` is the active milestone for a human-operated validation pass of the autonomous workflow and operator experience
- the controller now distinguishes actionable retryable failures from external blockers instead of stopping at generic verification failure
