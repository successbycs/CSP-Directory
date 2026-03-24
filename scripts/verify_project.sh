#!/usr/bin/env bash
# CSP Directory project-level verification entry point.
# Called by the Autonomous Framework controller before milestone-specific verify steps.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# Use venv python if available, otherwise system python3
if [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
else
    PYTHON="python3"
fi

echo "[verify_project] Running CSP Directory audit..."
$PYTHON scripts/autonomous_audit.py
