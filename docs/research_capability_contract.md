# Research Capability Contract

## Overview

Research capability is not needed for standard pipeline milestones in this project.

## When Research Is Required

Only set `research_required = true` when:
- the milestone explicitly names a new external vendor or API that is not in `tools/capability_registry.json`
- no existing Python script covers the required behaviour

## Standard Setting For Pipeline Milestones

For milestones targeting `database_persistence`, `data_pipeline`, or `llm_extraction`:
- `research_required = false`
- `research_request.action = "none"`
- `research_request.bootstrap_required = false`

## Research Request Object

Always return a research_request object even when research is not required:

```json
{
  "capability": "",
  "preferred_surface": "python",
  "reason": "",
  "action": "none",
  "bootstrap_required": false,
  "bootstrap_recipe_id": "",
  "bootstrap_artifact_path": ""
}
```
