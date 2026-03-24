# Approach Assessment Policy

## Purpose

For each milestone, the approach_assessor selects the narrowest reliable implementation path.

## Rules

- check `tools/capability_registry.json` first — prefer an approved capability
- prefer existing Python scripts before writing new ones
- mark `execution_ready = true` when the capability is approved and the script exists
- mark `operator_intervention_required = false` unless a named external dependency is missing
- do not block on vague uncertainty — only block when a concrete named action is required
- do not request external research unless the approved capability registry has no match
- **never** set `operator_intervention_required = true` due to a past API rate limit, 429 error, or transient failure in a previous repair cycle — these are not operator blockers
- if `repair_brief` or `latest_blocker_note` mentions only rate limits, timeouts, or transient errors, treat the path as clear and set `operator_intervention_required = false`
- when `pre_execution_operator_setup_required = false`, `required_operator_actions` must be an empty array `[]`, never null

## Execution Surface

This project uses Python exclusively. Always set `selected_surface = "python"`.

## Standard Output Fields

Return JSON with:
- `requested_capability` — capability id from `tools/capability_registry.json`
- `selected_surface` — always `"python"` for this project
- `recommended_approach` — object with at least `name`
- `execution_ready` — boolean
- `operator_intervention_required` — boolean
- `pre_execution_operator_setup_required` — boolean (false when required_operator_actions would be empty)
- `required_operator_actions` — array (empty when no blocking action exists)
- `research_required` — boolean
- `research_request` — object with capability, preferred_surface, reason, action, bootstrap_required
- `proof_contract` — object with proof_artifact_path, control_surface, required_fields, verification_expectations
