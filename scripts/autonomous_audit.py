"""CSP Directory repo readiness audit for the Autonomous Framework."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "README.md",
    "requirements.txt",
    "milestone_registry.json",
    "project_state.json",
    "runs/proofs",
    "config/pipeline_config.json",
    "config/llm.toml",
    "services/pipeline/orchestrator.py",
    "services/persistence/supabase_client.py",
    "services/extraction/llm_extractor.py",
    "services/discovery/apify_sources.py",
    "scripts/run_pipeline.py",
    "scripts/check_supabase.py",
    "scripts/apply_schema_migration.py",
    "docs/architecture.md",
    "docs/pipeline_design.md",
    "docs/vendor_schema.md",
)

REQUIRED_MILESTONE_FIELDS_BY_TYPE = {
    "capability_delivering": ["proof_description", "proof_artifact", "interaction_targets"],
}


def audit_files() -> list[str]:
    errors = []
    for path in REQUIRED_FILES:
        if not (PROJECT_ROOT / path).exists():
            errors.append(f"Missing required file: {path}")
    return errors


def audit_milestone_registry() -> list[str]:
    errors = []
    registry_path = PROJECT_ROOT / "milestone_registry.json"
    if not registry_path.exists():
        return ["milestone_registry.json not found"]

    try:
        registry = json.loads(registry_path.read_text())
    except json.JSONDecodeError as e:
        return [f"milestone_registry.json is invalid JSON: {e}"]

    milestones = registry.get("milestones", [])
    if not milestones:
        errors.append("milestone_registry.json has no milestones")

    for m in milestones:
        mid = m.get("id", "<unknown>")
        delivery_type = m.get("delivery_type", "")
        required_fields = REQUIRED_MILESTONE_FIELDS_BY_TYPE.get(delivery_type, [])
        for field in required_fields:
            if not m.get(field):
                errors.append(f"{mid}: missing required field '{field}' for {delivery_type}")
        artifact = m.get("proof_artifact", "")
        if artifact and not artifact.startswith("runs/proofs/"):
            errors.append(f"{mid}: proof_artifact must be under runs/proofs/, got: {artifact}")

    return errors


def main() -> int:
    file_errors = audit_files()
    milestone_errors = audit_milestone_registry()
    all_errors = file_errors + milestone_errors

    if all_errors:
        for error in all_errors:
            print(f"ERROR: {error}")
        print(f"\nAudit FAILED: {len(all_errors)} error(s)")
        return 1

    print("Audit PASSED: all required files present and milestone registry is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
