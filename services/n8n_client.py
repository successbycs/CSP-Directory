"""Thin n8n webhook client.

Routes Apify and other specialist tool calls through n8n workflows so the
underlying provider (Apify, Playwright, etc.) can be swapped without changing
application code.

Required env vars:
    N8N_BASE_URL  — e.g. https://successbycs.app.n8n.cloud
    N8N_API_KEY   — n8n Cloud API key (Settings → API Keys). Required for
                    import_and_activate_workflow(). Read-only webhooks work
                    without it.
    APIFY_API_TOKEN — passed through to n8n workflows at call time
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 120

# Webhook path constants
WEBHOOK_G2_ENRICHMENT = "framework-g2-enrichment"
WEBHOOK_PRICING_ENRICHMENT = "framework-pricing-enrichment"
WEBHOOK_LEAD_CAPTURE_INTAKE = "csp-lead-capture-intake"

# CSP-specific enrichment webhooks (M70 migration)
WEBHOOK_CSP_G2_ENRICHMENT = "csp-g2-enrichment"
WEBHOOK_CSP_PRICING_ENRICHMENT = "csp-pricing-enrichment"
WEBHOOK_CSP_TRACXN_ENRICHMENT = "csp-tracxn-enrichment"
WEBHOOK_CSP_FIRMOGRAPHIC_ENRICHMENT = "csp-firmographic-enrichment"
WEBHOOK_CSP_LINKEDIN_ENRICHMENT = "csp-linkedin-enrichment"
WEBHOOK_CSP_GOOGLE_DISCOVERY = "csp-google-discovery"
WEBHOOK_CSP_CRAWL_TIER1 = "csp-crawl-tier1-direct"
WEBHOOK_CSP_CRAWL_TIER2 = "csp-crawl-tier2-rag"
WEBHOOK_CSP_CRAWL_TIER3 = "csp-crawl-tier3-wcc"

# M70: Python trigger functions for enrichment steps
def trigger_g2_enrichment(vendor_name: str, website: str, rapidapi_key: str) -> dict[str, Any]:
    """Trigger G2 enrichment via n8n workflow."""
    return post_webhook(
        WEBHOOK_CSP_G2_ENRICHMENT,
        {
            "vendor_name": vendor_name,
            "website": website,
            "rapidapi_key": rapidapi_key,
        }
    )

def trigger_pricing_enrichment(vendor_name: str, website: str, apify_token: str, openai_api_key: str) -> dict[str, Any]:
    """Trigger pricing enrichment via n8n workflow."""
    return post_webhook(
        WEBHOOK_CSP_PRICING_ENRICHMENT,
        {
            "vendor_name": vendor_name,
            "website": website,
            "apify_token": apify_token,
            "openai_api_key": openai_api_key,
        }
    )

def trigger_tracxn_enrichment(vendor_name: str, website: str, apify_token: str) -> dict[str, Any]:
    """Trigger Tracxn enrichment via n8n workflow."""
    return post_webhook(
        WEBHOOK_CSP_TRACXN_ENRICHMENT,
        {
            "vendor_name": vendor_name,
            "website": website,
            "apify_token": apify_token,
        }
    )

def trigger_firmographic_enrichment(vendor_name: str, website: str, rapidapi_key: str) -> dict[str, Any]:
    """Trigger firmographic enrichment via n8n workflow."""
    return post_webhook(
        WEBHOOK_CSP_FIRMOGRAPHIC_ENRICHMENT,
        {
            "vendor_name": vendor_name,
            "website": website,
            "rapidapi_key": rapidapi_key,
        }
    )

def trigger_linkedin_enrichment(vendor_name: str, website: str, rapidapi_key: str) -> dict[str, Any]:
    """Trigger LinkedIn enrichment via n8n workflow."""
    return post_webhook(
        WEBHOOK_CSP_LINKEDIN_ENRICHMENT,
        {
            "vendor_name": vendor_name,
            "website": website,
            "rapidapi_key": rapidapi_key,
        }
    )

def trigger_google_discovery(queries: list[str], apify_token: str) -> dict[str, Any]:
    """Trigger Google discovery via n8n workflow."""
    return post_webhook(
        WEBHOOK_CSP_GOOGLE_DISCOVERY,
        {
            "queries": queries,
            "apify_token": apify_token,
        }
    )

def trigger_crawl_tier1(website: str, vendor_name: str = "") -> dict[str, Any]:
    """Trigger Tier 1 direct HTTP crawl via n8n workflow."""
    return post_webhook(
        WEBHOOK_CSP_CRAWL_TIER1,
        {
            "website": website,
            "vendor_name": vendor_name,
        }
    )

def trigger_crawl_tier2(website: str, vendor_name: str = "", apify_token: str = "") -> dict[str, Any]:
    """Trigger Tier 2 Apify RAG Web Browser crawl via n8n workflow."""
    return post_webhook(
        WEBHOOK_CSP_CRAWL_TIER2,
        {
            "website": website,
            "vendor_name": vendor_name,
            "apify_token": apify_token or get_apify_token(),
        }
    )

def trigger_crawl_tier3(website: str, vendor_name: str = "", apify_token: str = "", max_pages: int = 3) -> dict[str, Any]:
    """Trigger Tier 3 Apify Website Content Crawler crawl via n8n workflow."""
    return post_webhook(
        WEBHOOK_CSP_CRAWL_TIER3,
        {
            "website": website,
            "vendor_name": vendor_name,
            "apify_token": apify_token or get_apify_token(),
            "max_pages": max_pages,
        }
    )


def get_n8n_base_url() -> str:
    """Return the n8n base URL from env, raising if not set."""
    url = os.getenv("N8N_BASE_URL", "").strip().rstrip("/")
    if not url:
        raise RuntimeError("N8N_BASE_URL must be set to use n8n workflow integrations")
    return url


def get_n8n_api_key() -> str:
    """Return the n8n API key from env, raising if not set."""
    key = os.getenv("N8N_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "N8N_API_KEY must be set to manage workflows via the n8n REST API. "
            "Generate one in n8n Cloud → Settings → API Keys."
        )
    return key


def import_and_activate_workflow(workflow_path: "str | Path") -> dict[str, Any]:
    """Import a workflow JSON file to n8n Cloud and activate it.

    Uses the n8n REST API (v1):
        POST {N8N_BASE_URL}/api/v1/workflows          — create/import workflow
        PUT  {N8N_BASE_URL}/api/v1/workflows/{id}/activate — activate it

    Args:
        workflow_path: Path to the workflow JSON file (absolute or relative to
                       the project root).

    Returns:
        dict with keys: workflow_id, workflow_name, active, imported (bool),
        activated (bool), url (n8n Cloud editor URL).

    Raises:
        RuntimeError: If N8N_BASE_URL or N8N_API_KEY are not set, or the API
                      call fails.
    """
    import json as _json
    from pathlib import Path as _Path

    base_url = get_n8n_base_url()
    api_key = get_n8n_api_key()
    headers = {
        "X-N8N-API-KEY": api_key,
        "Content-Type": "application/json",
    }

    wf_path = _Path(workflow_path)
    if not wf_path.is_absolute():
        from pathlib import Path as _P
        import sys as _sys
        _repo_root = _P(__file__).resolve().parents[1]
        wf_path = _repo_root / wf_path

    workflow_json = _json.loads(wf_path.read_text())
    workflow_name = workflow_json.get("name", wf_path.stem)

    # n8n REST API only accepts a subset of top-level fields — strip extras that cause 400s
    _ALLOWED_WF_FIELDS = {"name", "nodes", "connections", "settings"}
    workflow_json = {k: v for k, v in workflow_json.items() if k in _ALLOWED_WF_FIELDS}

    # Check if a workflow with this name already exists
    list_resp = requests.get(f"{base_url}/api/v1/workflows", headers=headers, timeout=30)
    if list_resp.ok:
        existing = {w["name"]: w["id"] for w in list_resp.json().get("data", [])}
    else:
        existing = {}

    if workflow_name in existing:
        workflow_id = existing[workflow_name]
        logger.info("Workflow '%s' already exists (id=%s) — updating", workflow_name, workflow_id)
        put_resp = requests.put(
            f"{base_url}/api/v1/workflows/{workflow_id}",
            headers=headers,
            json=workflow_json,
            timeout=30,
        )
        put_resp.raise_for_status()
        imported = False
    else:
        logger.info("Importing workflow '%s' to n8n Cloud", workflow_name)
        post_resp = requests.post(
            f"{base_url}/api/v1/workflows",
            headers=headers,
            json=workflow_json,
            timeout=30,
        )
        post_resp.raise_for_status()
        workflow_id = post_resp.json().get("id")
        imported = True

    # Activate
    act_resp = requests.post(
        f"{base_url}/api/v1/workflows/{workflow_id}/activate",
        headers=headers,
        timeout=30,
    )
    activated = act_resp.ok
    if not activated:
        logger.warning("Workflow '%s' imported but activation failed: %s", workflow_name, act_resp.text)

    editor_url = f"{base_url}/workflow/{workflow_id}"
    logger.info(
        "Workflow '%s' %s and %s. Editor: %s",
        workflow_name,
        "imported" if imported else "updated",
        "activated" if activated else "NOT activated",
        editor_url,
    )
    return {
        "workflow_id": workflow_id,
        "workflow_name": workflow_name,
        "active": activated,
        "imported": imported,
        "activated": activated,
        "url": editor_url,
    }


def get_apify_token() -> str:
    """Return the Apify API token from env, raising if not set."""
    token = os.getenv("APIFY_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError("APIFY_API_TOKEN must be set")
    return token


def post_webhook(
    path: str,
    payload: dict[str, Any],
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """POST to an n8n webhook and return the JSON response body.

    Args:
        path: Webhook path, e.g. "framework-website-content-crawl"
        payload: JSON body to POST (apify_token is injected automatically)
        timeout_seconds: Request timeout

    Returns:
        Parsed JSON response dict

    Raises:
        RuntimeError: If N8N_BASE_URL is not set or the webhook returns an error
    """
    base_url = get_n8n_base_url()
    # Inject apify_token if available — some workflows need it, others don't
    try:
        apify_token = get_apify_token()
    except RuntimeError:
        apify_token = ""

    full_payload = {**payload}
    if apify_token and "apify_token" not in payload:
        full_payload["apify_token"] = apify_token
    url = f"{base_url}/webhook/{path}"

    logger.info("Calling n8n webhook: %s", url)
    try:
        response = requests.post(url, json=full_payload, timeout=timeout_seconds)
        response.raise_for_status()
        if not response.content or not response.content.strip():
            logger.warning("n8n webhook %s returned empty body; treating as empty JSON", url)
            return {}
        return response.json()
    except requests.Timeout:
        raise RuntimeError(f"n8n webhook timed out after {timeout_seconds}s: {url}")
    except requests.HTTPError as exc:
        raise RuntimeError(f"n8n webhook returned HTTP {exc.response.status_code}: {url}") from exc
    except Exception as exc:
        raise RuntimeError(f"n8n webhook call failed for {url}: {exc}") from exc
