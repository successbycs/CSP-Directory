"""Pricing enrichment: trigger n8n workflow to populate pricing fields.

n8n workflow (framework-pricing-enrichment) handles the two-stage process:
  Stage 1 — crawl /pricing page; accept only if >= 200 visible-text words.
  Stage 2 — LLM extraction with nullable tier fields and no URL citation required.

Output fields written back via POST /admin/enrich-write:
  pricing              — text[] of pricing tier signals
  has_public_pricing_page — bool
  free_trial           — bool
  pricing_source       — "scraped" | "llm_inferred"
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def enrich_vendors_pricing(
    vendor_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Trigger n8n pricing enrichment workflow for a list of vendors.

    n8n crawls each vendor's /pricing page, applies a content-quality gate,
    falls back to LLM extraction, and writes results via POST /admin/enrich-write.

    Returns the n8n webhook response or an error summary.
    """
    from services import n8n_client

    vendors_payload = [
        {
            "vendor_name": v.get("vendor_name", ""),
            "website": v.get("website", ""),
        }
        for v in vendor_rows
        if v.get("vendor_name") or v.get("website")
    ]

    if not vendors_payload:
        return {"attempted": 0, "triggered": False, "error": "no_vendors"}

    logger.info("Triggering n8n pricing enrichment for %d vendors", len(vendors_payload))
    try:
        response = n8n_client.post_webhook(
            n8n_client.WEBHOOK_PRICING_ENRICHMENT,
            {"vendors": vendors_payload},
        )
        return {"attempted": len(vendors_payload), "triggered": True, "n8n_response": response}
    except Exception as exc:
        logger.error("Pricing n8n trigger failed: %s", exc)
        return {"attempted": len(vendors_payload), "triggered": False, "error": str(exc)}
