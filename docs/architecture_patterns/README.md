# Architecture Patterns

## Overview

This project uses a single architecture pattern: **Python Pipeline**.

## Python Pipeline Pattern

All milestones follow this pattern:
- scripts in `scripts/` orchestrate the pipeline phases
- services in `services/` contain reusable business logic
- config in `config/` drives runtime behaviour
- proofs in `runs/proofs/` document milestone completion

## Pattern Name For Approach Assessor

When the approach_assessor selects an architecture pattern for any milestone in this project, use:

```json
{
  "pattern_name": "python_pipeline",
  "description": "Python scripts orchestrate discovery, enrichment, and persistence phases"
}
```
