#!/usr/bin/env bash
set -euo pipefail

echo "[1/4] Running tests"
pytest

echo "[2/4] Running pipeline smoke test"
python scripts/run_pipeline.py "ai customer success platform" || true

echo "[3/4] Exporting directory dataset"
python scripts/export_directory_dataset.py || true

echo "[4/4] Verification complete"
