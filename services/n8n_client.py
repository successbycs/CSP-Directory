"""Thin n8n webhook client.

Routes Apify and other specialist tool calls through n8n workflows so the
underlying provider (Apify, Playwright, etc.) can be swapped without changing
application code.

Required env vars:
    N8N_BASE_URL  — e.g. http://localhost:5678
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


def get_n8n_base_url() -> str:
    """Return the n8n base URL from env, raising if not set."""
    url = os.getenv("N8N_BASE_URL", "").strip().rstrip("/")
    if not url:
        raise RuntimeError("N8N_BASE_URL must be set to use n8n workflow integrations")
    return url


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
        return response.json()
    except requests.Timeout:
        raise RuntimeError(f"n8n webhook timed out after {timeout_seconds}s: {url}")
    except requests.HTTPError as exc:
        raise RuntimeError(f"n8n webhook returned HTTP {exc.response.status_code}: {url}") from exc
    except Exception as exc:
        raise RuntimeError(f"n8n webhook call failed for {url}: {exc}") from exc
