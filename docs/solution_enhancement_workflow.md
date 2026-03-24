# Solution Enhancement Workflow

This document defines how change requests, enhancements, and product updates enter the autonomous milestone system.

## Goal

Enhancement intake must stay inside the same controller-owned milestone contract as normal autonomous work. Requests should not become ad hoc repo edits without an explicit routing decision.

## Inputs

An enhancement request should capture:

- a short title
- a concrete summary of the requested change
- optional implementation notes, proof expectations, or urgency context

Requests are recorded in `enhancement_requests.json`.

## Routing Outcomes

Every enhancement request must end in exactly one of these routes:

1. `active_milestone`
   The request is small and aligned enough to be absorbed into the current focus milestone without changing milestone order.
2. `new_milestone`
   The request needs its own scoped milestone, acceptance criteria, and verification contract.
3. `deferred`
   The request is worth keeping, but it should not change the active milestone plan yet.

## Control Plane Rule

The `solution_enhancement` role is read-only. It may analyze a request and recommend a route, but it does not mutate repo state by itself.

Only the controller may:

- record the enhancement route
- append a deferred enhancement record
- add a new milestone to `milestone_registry.json`
- append a new milestone section to `docs/implementation_plan.md`

## Controller Entry Point

Use:

```bash
.venv/bin/python scripts/autonomous_controller.py enhancement-request \
  --title "..." \
  --summary "..." \
  --route active_milestone|new_milestone|deferred
```

For `new_milestone`, also provide:

- `--new-milestone-id`
- `--new-milestone-title`

Optional fields:

- `--objective`
- repeated `--acceptance`
- repeated `--verify`
- repeated `--dependency`
- `--note`

## Expected Behavior

- Active-milestone routing records the request against the current focus milestone without bypassing review, QA, or completion gates.
- New-milestone routing creates a new `not_started` milestone in `milestone_registry.json`, appends a matching section to `docs/implementation_plan.md`, and records the request in `enhancement_requests.json`.
- Deferred routing records the request without mutating the active milestone plan.

## Role Packet Expectations

The `solution_enhancement` agent prompt should produce:

- a recommended route
- the reasoning for that route
- the likely affected files or systems
- proof expectations if the request becomes milestone work
