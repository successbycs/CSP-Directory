# n8n Development Tool

This directory defines the repo-owned `n8n` tool boundary for autonomous development.

## Purpose

`n8n` may be used during development for:

- local workflow prototyping
- integration experiments
- exporting and reviewing workflow JSON
- validating development-only automation ideas before they become product code

## Out Of Scope

`n8n` may not be used through this tool contract for:

- production/runtime automation
- hosted customer workflows
- live customer data processing
- hidden background jobs outside the repo-owned milestone system
- bypassing application code, review, QA, or milestone verification

## Access Rules

- The tool is development-only.
- Roles may access it only when the current milestone explicitly declares `n8n`.
- Builder access is approval-gated for mutating operations such as importing or changing development workflows.
- Reviewer, QA, and auditors remain read-only.

## Environment Assumptions

- A local or explicitly designated development `n8n` instance may exist, but it is optional.
- Secrets and connection details must remain outside the repo and use local operator configuration only.
- Exported workflow JSON should be treated as reviewable development artifacts, not as implicit product runtime configuration.

## Boundary

The product runtime remains application-owned. `n8n` is a development support tool, not a replacement control plane for the product or autonomous milestone system.
