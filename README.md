# AI_CustomerSuccess

Vendor-first MVP for discovering AI-enabled Customer Success vendors, fetching their homepages, extracting lightweight vendor intelligence, and shaping the result into Google Sheets-ready rows.

## Python Setup

This project requires Python 3.12+.

Create a virtual environment and install dependencies:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

The CLI loads environment variables from a local `.env` file automatically.
Google Sheets output is optional and uses `GOOGLE_SHEETS_ID` plus
`GOOGLE_SHEETS_CREDENTIALS_JSON`.

Operator-tunable settings are currently split across two active runtime surfaces:
- `config/pipeline_config.json` is the primary runtime source of truth for discovery, enrichment, directory relevance, LLM, and Google Sheets behavior
- `config/scheduler.toml` controls APScheduler timing and digest cadence

Additional TOML files currently exist under `config/` as transitional or reference artifacts. Config consolidation is still an active milestone rather than a completed part of the system.

The current default discovery depth is `max_pages_per_query = 5`.

LLM extraction is expected to run on normal pipeline executions when valid OpenAI configuration is present. If the LLM layer is unavailable, the pipeline falls back to deterministic extraction and that fallback should be visible in operator-facing run outputs.

## Run Tests

Use the local virtual environment for deterministic test runs:

```sh
.venv/bin/python -m pytest
```

## Run the Pipeline

Write Google Sheets-ready CSV output to `outputs/vendor_rows.csv`:

```sh
.venv/bin/python scripts/run_pipeline.py "ai customer success platform"
```

Run the Python-owned scheduler:

```sh
.venv/bin/python -m services.pipeline.scheduler
```

Run one scheduled job manually:

```sh
.venv/bin/python -m services.pipeline.scheduler --run-now discovery
.venv/bin/python -m services.pipeline.scheduler --run-now digest
```

Supabase schema and connectivity check:

```sh
.venv/bin/python scripts/check_supabase.py
```

This check verifies the core persistence tables and columns used by vendor upserts, vendor exports, discovery candidate storage, and pipeline run tracking. It will fail clearly when required Supabase schema elements are missing.

The repo-owned schema fix lives at:

```sh
supabase/core_persistence_schema.sql
```

Apply that SQL in the Supabase SQL editor or through your normal Postgres migration path before expecting live persistence-backed exports to pass.

Integration diagnostics:

```sh
.venv/bin/python scripts/check_integrations.py
```

Search visibility reporting artifacts:

```sh
.venv/bin/python scripts/export_search_visibility_report.py
outputs/search_visibility_report.json
outputs/search_visibility_report.html
```

These artifacts summarize the role-based search visibility workflow in three distinct layers:
- vendor website enrichment persists normalized vendor intelligence and `icp_buyer` personas
- buyer-intent query generation persists Google-style and GEO-style prompts in `buyer_search_queries`
- role-based search ranking observation persists ranked vendor rows in `buyer_search_results` and renders query-centric plus vendor-centric review outputs

## MVP Flow

The current codebase follows the MVP pipeline described in `docs/product_design.md`:

1. `services/discovery/` finds vendor candidates from web search
2. `services/enrichment/` fetches vendor homepage content
3. `services/extraction/` converts homepage payloads into `VendorIntelligence`
4. `services/export/` converts vendor intelligence into Google Sheets-ready rows
5. `services/pipeline/` orchestrates the end-to-end flow

`docker-compose.yml` remains in the repo for future infrastructure work, but Docker is not required for the current Python MVP or test suite.

## Autonomous Development Docs

The repo now includes an autonomous milestone-control doc set:

- `docs/implementation_plan.md` tracks current progress and remaining milestones
- `docs/autonomous_dev_loop.md` defines the controller -> prework -> planner -> builder -> reviewer -> QA milestone loop
- `docs/autonomous_kickoff_prompt.md` provides the reusable kickoff prompt for each milestone cycle
- `docs/session_context_2026-03-21.md` captures the latest operator and engineering context from the March 21, 2026 working session
- `docs/agents/` contains reusable prompts for the controller, prework, planner, builder, reviewer, QA, closeout-auditor, and backfill-auditor roles
- `docs/codex_guardrails.md` defines implementation constraints for autonomous work
- `docs/audit/audit.md` is the persistent audit log for milestone closeout and backfill reviews
- `project_state.json`, `milestone_registry.json`, and `runs/run_history.json` provide local cycle state
- `scripts/autonomous_controller.py`, `scripts/run_autonomous_cycle.sh`, `scripts/local_agent_runner.py`, `scripts/milestone_auditor.py`, and `scripts/verify_project.sh` provide local execution, verification, and audit entrypoints

Common local controller commands:

```sh
.venv/bin/python scripts/autonomous_controller.py status
.venv/bin/python scripts/autonomous_controller.py next
.venv/bin/python scripts/autonomous_controller.py next-action
.venv/bin/python scripts/autonomous_controller.py verify
.venv/bin/python scripts/autonomous_controller.py assert-artifacts
.venv/bin/python scripts/autonomous_controller.py audit-closeout M08
.venv/bin/python scripts/autonomous_controller.py audit-backfill --all-unaudited
.venv/bin/python scripts/autonomous_controller.py review M08 --status pass --note "review complete"
.venv/bin/python scripts/autonomous_controller.py qa M08 --status pass --note "qa complete" --manual-checks-complete --artifact outputs/directory_dataset.json
.venv/bin/python scripts/autonomous_controller.py complete M08
bash scripts/run_autonomous_cycle.sh
```

Repo-native runner options:

- `scripts/local_agent_runner.py` always generates structured role packets under `runs/agent_outputs/`
- set `AUTONOMOUS_AGENT_CLI` to a local executable that reads one JSON payload from stdin and returns one JSON result on stdout if you want the runner to capture real local AI output
- `tools/agent_cli/cli.py` is the canonical repo-owned role CLI for `AUTONOMOUS_AGENT_CLI`
- `project_state.json -> agent_runner.cli_command` now persists the canonical repo-owned CLI wiring, and `scripts/run_autonomous_cycle.sh` plus the autonomy Python entrypoints load `.env` automatically so shell resets do not drop the backend hookup
- for `builder` packets that CLI is agentic: it invokes `codex exec` so the builder can actually modify the repo instead of only grading a packet
- set `AUTONOMOUS_BUILDER_CLI` if you want the mutating builder role to use a different backend from the read-only evaluator roles
- `scripts/openai_agent_cli.py` remains as the implementation source and compatibility path while the tool entrypoint is adopted
- `M13B` is the milestone that tracks completion of the real local AI backend hookup and proof through the controller loop

Example OpenAI backend setup:

```sh
export OPENAI_API_KEY=your_api_key
export AUTONOMOUS_AGENT_CLI=".venv/bin/python tools/agent_cli/cli.py --model gpt-5.4"
```

Optional explicit builder override:

```sh
export AUTONOMOUS_AGENT_CLI=".venv/bin/python tools/agent_cli/cli.py --model gpt-5.4"
export AUTONOMOUS_BUILDER_CLI="codex -a never exec -s workspace-write"
```

Operator-facing control-plane summary:

- `scripts/autonomous_controller.py` is the controller. It selects the active milestone, records verification/review/QA state, and decides whether completion is allowed.
- after `complete`, the controller now triggers the `Closeout Auditor` automatically and appends its entry to `docs/audit/audit.md` when an OpenAI audit backend is available
- when an audit backend is available, a failed closeout audit now reverts milestone completion instead of leaving the milestone closed with a failed audit
- the `Backfill Auditor` is a manual controller command for completed milestones that do not yet have an audit entry
- `scripts/autonomous_controller.py next-action` tells you whether the milestone should retry, move to review/QA, stop on an external blocker, or complete.
- the controller now reports datastore capability state in `status` and hard-blocks schema-admin milestones like `M15` when no DB-admin path is configured
- `prework`, `planner`, `builder`, `reviewer`, and `qa` are separate role phases. Their prompt files live under `docs/agents/`.
- `scripts/local_agent_runner.py` creates one role packet per phase and sends that packet to the configured backend when `AUTONOMOUS_AGENT_CLI` is set.
- after a successful builder run, the local runner refreshes the changed-file snapshot so the saved packet reflects what the agent actually changed.
- A role packet is the saved JSON handoff for one phase. It contains the milestone context, changed files, artifact checks, recent history evidence, and the role result.
- Role packets now also include a delegated task contract with `task_id`, execution mode, bounded write scope, and allowed tool ids.
- Role packets now also include the controller’s retry state so planner/builder can see whether the current iteration is a fresh pass, a retry, or an externally blocked stop condition.
- The `prework` role is read-only and exists to accelerate the next implementation pass with a current gap map, likely file-touch list, and verification-focused prep summary.
- Role packets are written to `runs/agent_outputs/` and run-history events are written to `runs/run_history.json`.
- Attribution is explicit in both places. Packets and history entries now include `producer_role`, `phase`, `backend`, `model`, and `cycle_id`.
- Delegated execution is serial by default through `project_state.json` delegation policy; parallel work should remain opt-in and read-only unless write-scope isolation is explicit.
- `scripts/run_autonomous_cycle.sh` creates one `cycle_id` for the whole run so related planner/builder/reviewer/qa packets can be grouped together.
- `scripts/milestone_auditor.py` is the repo-native audit runner used for post-completion closeout audits and historical backfill audits.

Container proof command:

```sh
bash scripts/prove_container_autonomous_loop.sh
```

Before using the autonomous loop, read:

```sh
docs/product_design.md
docs/architecture.md
docs/codex_guardrails.md
docs/implementation_plan.md
docs/session_context_2026-03-21.md
README.md
config/pipeline_config.json
config/scheduler.toml
```

## Tool Registry

The repo now defines a reusable tool pattern under `tools/`.

- `tools/tool_registry.json` is the registry of declared project tools
- `tools/supabase/tool_spec.json` is the first concrete tool spec
- roles may use declared tools only when the controller exposes them for the current milestone and role
- tool specs define allowed operations, write access, and approval requirements
- direct repo-owned access is preferred
- direct repo-owned Supabase access is the active development path for schema admin and CRUD work
- `supabase/core_persistence_schema.sql` remains the schema source of truth even when a tool backend is used
- The Supabase tool must support both schema-admin operations and data CRUD for vendors, candidates, and pipeline runs
