# Autonomous Development Loop

## The three-agent pattern
Use three agent roles in sequence.

### 1. Builder Agent
Prompt:
- Read product design, architecture, guardrails, implementation plan, and config
- Complete the highest unfinished milestone
- Run verification and tests
- Report changed files, risks, and next step

### 2. Reviewer Agent
Prompt:
- Inspect the implementation for the completed milestone
- Review against architecture and guardrails
- Identify doc vs implementation mismatches
- Identify launch blockers or hidden risks

### 3. QA Agent
Prompt:
- Check runtime behavior, failure paths, tests, and artifacts
- Validate acceptance criteria
- Confirm milestone can be marked complete or explain why not

## Standard execution prompt
Read:
- docs/product_design.md
- docs/architecture.md
- docs/codex_guardrails.md
- docs/implementation_plan.md
- config/pipeline_config.json

Task:
Complete the highest unfinished milestone in docs/implementation_plan.md.
Inspect the current repo first.
Respect codex_guardrails.md.
Run relevant tests and milestone verification.
Return:
- summary of changes
- changed files
- test and verification results
- milestone status
- next recommended milestone

## Milestone completion rule
A milestone is complete only when:
- acceptance criteria are met
- verification commands succeed
- relevant tests pass
- the implementation does not violate guardrails

## Human role
Human review happens at milestone boundaries, not every code change.
