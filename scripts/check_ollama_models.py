#!/usr/bin/env python3
"""Verify Ollama is running and both M76 required models are installed.

Exit 0 — both models present
Exit 1 — Ollama unreachable or a model is missing
"""
import json
import sys
import urllib.error
import urllib.request

REQUIRED_MODELS = {"mistral:latest", "nomic-embed-text"}
OLLAMA_BASE_URL = "http://localhost:11434"


def main() -> int:
    # Check connectivity
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError) as exc:
        print(f"FAIL: Ollama not reachable at {OLLAMA_BASE_URL}: {exc}")
        print("      Start Ollama with: ollama serve")
        return 1

    installed = {m.get("name", "") for m in body.get("models", [])}
    missing = REQUIRED_MODELS - installed

    if missing:
        print(f"FAIL: Missing Ollama models: {', '.join(sorted(missing))}")
        for m in sorted(missing):
            print(f"      Install with: ollama pull {m}")
        return 1

    print(f"OK: Ollama reachable at {OLLAMA_BASE_URL}")
    for m in sorted(REQUIRED_MODELS):
        print(f"  ✓ {m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
