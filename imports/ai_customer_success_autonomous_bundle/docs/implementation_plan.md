# Implementation Plan

## Status legend
- not_started
- in_progress
- blocked
- complete

## M01 Config-driven runtime foundation
Status: not_started
Objective: Ensure manual and scheduled runs share one config surface.
Acceptance criteria:
- Config loader validates `config/pipeline_config.json`
- Manual and scheduled runs use same config loader
Verification:
- `pytest`
- run pipeline manually with config

## M02 Two-phase crawl made explicit
Status: not_started
Objective: Clear separation between discovery and enrichment.
Acceptance criteria:
- Discovery candidates are persisted with statuses
- Enrichment consumes queued candidates
Verification:
- `pytest`
- inspect candidate statuses in Supabase or snapshot

## M03 Bounded website exploration
Status: not_started
Objective: Crawl a small set of high-value internal pages per vendor.
Acceptance criteria:
- Site explorer discovers key page types
- Page bundle built with bounded page count
Verification:
- `pytest`
- run pipeline and inspect evidence URLs

## M04 Deterministic vendor profile baseline
Status: not_started
Objective: Build rich vendor profiles without LLM dependency.
Acceptance criteria:
- Vendor profiles contain deterministic fields for lifecycle, ICP hints, pricing hints, etc.
Verification:
- `pytest`
- inspect exported sample vendor profile

## M05 Level 2 LLM enrichment
Status: not_started
Objective: Add optional LLM enrichment safely.
Acceptance criteria:
- LLM fields parsed safely
- fallback path works
- low-confidence or irrelevant vendors can be dropped
Verification:
- `pytest`
- run pipeline with and without LLM config

## M06 Directory relevance scoring
Status: not_started
Objective: Distinguish cs_core vendors from adjacent vendors.
Acceptance criteria:
- `directory_fit`, `directory_category`, and `include_in_directory` are populated
Verification:
- `pytest`
- inspect dataset records

## M07 Directory dataset export
Status: not_started
Objective: Export only includable vendors in a stable JSON format.
Acceptance criteria:
- `outputs/directory_dataset.json` produced
- records sorted and normalized
Verification:
- `pytest`
- `python scripts/export_directory_dataset.py`

## M08 Public directory listing page
Status: not_started
Objective: Render real vendor cards from exported dataset.
Acceptance criteria:
- Listing page loads JSON and renders cards
- basic search/filter works
Verification:
- static site preview opens and shows data

## M09 Vendor profile page
Status: not_started
Objective: Render a detailed vendor page from the exported dataset.
Acceptance criteria:
- `vendor.html` resolves and renders vendor profile
Verification:
- static site preview opens profile page from data

## M10 Admin visibility
Status: not_started
Objective: Provide operator visibility into candidates, vendors, and runs.
Acceptance criteria:
- Read-only admin API exists
- Static admin dashboard renders tables from API
Verification:
- API smoke test
- open `admin.html`

## M11 Admin actions
Status: not_started
Objective: Allow safe include/exclude and rerun enrichment actions.
Acceptance criteria:
- admin actions log changes
- include/exclude updates persistence
Verification:
- `pytest`
- run admin action script

## M12 Containerized runtime
Status: not_started
Objective: Run the core system consistently in Docker/devcontainer.
Acceptance criteria:
- Dockerfile works
- devcontainer opens in VS Code
- core commands run inside container
Verification:
- `docker build`
- `docker run`

## M13 Scheduled runs
Status: not_started
Objective: Repeated execution using same config surface.
Acceptance criteria:
- scheduler uses config loader
- run snapshots persisted
Verification:
- scheduler smoke test or manual invocation

## M14 Launch readiness
Status: not_started
Objective: Reach internal-launch readiness.
Acceptance criteria:
- all critical milestones complete
- verification script passes
- internal operators can inspect and override data
Verification:
- `scripts/verify_project.sh`
