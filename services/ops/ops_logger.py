"""OpsLogger — structured logging for M76 Ops Enrichment Workbench steps.

Emits JSON log entries to stdout (captured by pipeline_control subprocess runner)
and optionally appends to a log file. Entries are formatted to match the existing
/admin/pipeline-log schema so the live log panel renders them correctly.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class OpsLogger:
    """Emit structured log entries for a single pipeline run."""

    def __init__(self, milestone: str = "M76", log_path: str | None = None) -> None:
        self._milestone = milestone
        self._log_path = Path(log_path) if log_path else None

    def step_start(self, action: str, message: str) -> None:
        """Emit an in-progress entry (success=None)."""
        self._emit(action, message, success=None)

    def step_progress(self, action: str, message: str) -> None:
        """Emit a live-update entry (success=None) — shown as current state in log panel."""
        self._emit(action, message, success=None)

    def step_done(self, action: str, message: str) -> None:
        """Emit a completed entry (success=True)."""
        self._emit(action, message, success=True)

    def step_error(self, action: str, message: str) -> None:
        """Emit an error entry (success=False)."""
        self._emit(action, message, success=False)

    def _emit(self, action: str, message: str, *, success: bool | None) -> None:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": "enrichment",
            "milestone": self._milestone,
            "action": action,
            "message": message,
            "success": success,
        }
        line = json.dumps(entry, ensure_ascii=False)
        print(line, flush=True)
        if self._log_path is not None:
            try:
                with self._log_path.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError:
                pass
