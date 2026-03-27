"""Publish directory_dataset.json to GitHub via the Contents API.

Usage:
    python3 scripts/publish_to_github.py [--dry-run] [--repo owner/name] [--branch main]

Environment variables:
    GITHUB_TOKEN   Required. Personal access token with repo write scope.
    GITHUB_REPO    Optional. Defaults to successbycs/CSP-Directory.
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
from pathlib import Path
from typing import Any, Callable

import requests

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
DEFAULT_REPO = "successbycs/CSP-Directory"
DEFAULT_FILE_PATH = "docs/website/data/directory_dataset.json"
DEFAULT_BRANCH = "main"
DEFAULT_COMMIT_MESSAGE = "chore: publish directory_dataset.json [automated]"

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_LOCAL_FILE = PROJECT_ROOT / "docs" / "website" / "data" / "directory_dataset.json"


def publish_to_github(
    local_file: Path = DEFAULT_LOCAL_FILE,
    repo: str | None = None,
    file_path: str = DEFAULT_FILE_PATH,
    branch: str = DEFAULT_BRANCH,
    commit_message: str = DEFAULT_COMMIT_MESSAGE,
    token: str | None = None,
    *,
    dry_run: bool = False,
    request_get: Callable[..., Any] | None = None,
    request_put: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Commit local_file to the GitHub repo via the Contents API.

    Returns a dict with: ok, vendor_count, commit_url (or dry_run flag).
    Raises ValueError if GITHUB_TOKEN is missing.
    Raises requests.HTTPError on API failures.
    """
    token = token or os.environ.get("GITHUB_TOKEN", "")
    repo = repo or os.environ.get("GITHUB_REPO", DEFAULT_REPO)

    if not token:
        raise ValueError("GITHUB_TOKEN env var is required")

    content = local_file.read_bytes()
    vendor_count = _count_vendors(content)
    encoded = base64.b64encode(content).decode()

    if dry_run:
        logger.info(
            "Dry run: would commit %s (%d vendors) to %s/%s on branch %s",
            local_file.name,
            vendor_count,
            repo,
            file_path,
            branch,
        )
        return {"ok": True, "dry_run": True, "vendor_count": vendor_count}

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    api_url = f"{GITHUB_API_BASE}/repos/{repo}/contents/{file_path}"

    # Fetch current file SHA (required for updates; absent for new files).
    get_fn = request_get or requests.get
    get_resp = get_fn(api_url, headers=headers, params={"ref": branch})
    current_sha: str | None = None
    if get_resp.status_code == 200:
        current_sha = get_resp.json().get("sha")
    elif get_resp.status_code != 404:
        get_resp.raise_for_status()

    body: dict[str, Any] = {
        "message": commit_message,
        "content": encoded,
        "branch": branch,
    }
    if current_sha:
        body["sha"] = current_sha

    put_fn = request_put or requests.put
    put_resp = put_fn(api_url, headers=headers, json=body)
    put_resp.raise_for_status()

    result = put_resp.json()
    commit_url = result.get("commit", {}).get("html_url", "")

    logger.info("Published %d vendors to GitHub: %s", vendor_count, commit_url)
    return {"ok": True, "vendor_count": vendor_count, "commit_url": commit_url}


def _count_vendors(content: bytes) -> int:
    try:
        data = json.loads(content)
        return len(data) if isinstance(data, list) else 0
    except Exception:
        return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Publish directory_dataset.json to GitHub")
    parser.add_argument("--dry-run", action="store_true", help="Preview without pushing")
    parser.add_argument("--repo", default=None, help="GitHub repo (owner/name)")
    parser.add_argument("--branch", default=DEFAULT_BRANCH, help="Target branch")
    parser.add_argument("--message", default=DEFAULT_COMMIT_MESSAGE, help="Commit message")
    args = parser.parse_args()

    result = publish_to_github(
        dry_run=args.dry_run,
        repo=args.repo,
        branch=args.branch,
        commit_message=args.message,
    )
    print(json.dumps(result, indent=2))
