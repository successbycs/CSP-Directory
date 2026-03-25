# AF Milestone Execution Architecture Decision

**Date:** 2026-03-26
**Status:** Decided — implementation deferred until after CSP ships

---

## Context

The AF builder agent operates within a 40-round tool limit. Milestones with 4+ acceptance criteria (e.g. M43B: endpoint + UI + tests + proof artifact) regularly exhaust the budget before completion. This produces partial work that the repair triad flags, triggering additional repair cycles — compounding the cost rather than resolving it.

Two solutions were triaded:

---

## Solution A — Controller auto-split (rejected)

Controller detects a complex milestone, splits it into sub-milestones, and writes them into `milestone_registry.json` before running the builder.

**Why rejected:**
- `milestone_registry.json` is a product artifact (human-authored, stable). Auto-generated entries corrupt its integrity as a readable product roadmap.
- A crash mid-split leaves orphaned entries with no rollback path.
- Auto-generating valid `verify` commands for partial work is non-trivial and error-prone.
- No way to distinguish human-authored milestones from generated ones without provenance tracking.

---

## Solution B — Execution sub-pipeline (decided)

Milestone registry stays as written. AF generates an ephemeral execution plan at runtime.

**How it works:**
1. Prework agent outputs `complexity_class`: `simple` / `moderate` / `complex`
   - Heuristic: acceptance criteria count is the best proxy. Cap: 3 criteria = simple/moderate, 4+ = complex
2. For complex milestones, a **decomposer** role generates `runs/execution_plans/<milestone_id>_plan.json`
   - Ordered list of sub-tasks, each with scoped acceptance criteria and declared file write scope
3. Controller runs the builder once per sub-task
   - Passes prior sub-task outputs as `prior_work_summary` context into the next builder packet
4. Parent milestone marked complete when all sub-tasks pass verification
5. Execution plan is cached with a milestone definition hash — invalidated if the milestone changes

**What stays the same:**
- `milestone_registry.json` — unchanged, human-authored only
- Builder, reviewer, qa prompts — no changes
- Operator sees milestone-level progress, not sub-task noise

**Non-negotiable constraints:**
- Execution plan stored with timestamp + milestone definition hash
- Sub-task outputs logged individually in `runs/execution_plans/`
- Operator reports include sub-task ID and builder round count at failure point
- Controller gates sub-task N on sub-task N-1 proof of completion

---

## Cost Model

| Role | Recommended model | Reason |
|---|---|---|
| prework, planner, approach_assessor | Ollama/Qwen (local) | Read-only text reasoning, no code output required |
| builder, reviewer, qa, fixer | GPT-4o or Claude | Must produce correct, testable code |

Analysis roles run on every cycle. Moving them to local Ollama models cuts cost-per-milestone meaningfully without affecting output quality. Builder keeps frontier model capability.

The "AF is cheaper than Claude Code" assumption only holds when agents complete tasks within budget. At the 40-round limit, a failed build + repair cycle costs more than Claude Code completing the same task directly. Solution B restores the cost advantage by ensuring builders complete within budget.

---

## Implementation Plan

Implement as AF milestones on the framework itself (self-referential):
1. Prework complexity assessment output (`complexity_class` + `acceptance_criteria_count`)
2. Decomposer role + execution plan schema
3. Controller sub-pipeline state machine
4. Ollama model tier routing in `model_router.py` and `agentic_cli.py`
