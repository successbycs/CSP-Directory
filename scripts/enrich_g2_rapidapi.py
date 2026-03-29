"""
G2 enrichment via RapidAPI G2 Data Api (Chetan11-dev).

Usage:
    python3 scripts/enrich_g2_rapidapi.py [--dry-run] [--limit N] [--vendor NAME]

Calls GET /g2-products for each vendor, writes results via admin_api enrich-write.
Slug strategy: try vendor name variants until a hit or exhausted.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

import requests
from services.admin.admin_api import _run_enrich_write as run_enrich_write
from services.persistence import supabase_client

RAPIDAPI_KEY = os.environ["RAPIDAPI_KEY"]
RAPIDAPI_HOST = "g2-data-api.p.rapidapi.com"
HEADERS = {
    "x-rapidapi-key": RAPIDAPI_KEY,
    "x-rapidapi-host": RAPIDAPI_HOST,
    "Content-Type": "application/json",
}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _slug_variants(vendor_name: str, website: str) -> list[str]:
    """Return candidate G2 slugs to try, most likely first."""
    # Strip common company suffixes before slugifying
    clean = re.sub(
        r"\s+(Software|Inc\.?|LLC|Ltd\.?|Corp\.?|Group|Technologies|Tech|Solutions|Platform|Systems)$",
        "", vendor_name, flags=re.I
    ).strip()
    base = _slug(vendor_name)
    clean_base = _slug(clean)

    seen: set[str] = set()
    variants: list[str] = []
    for s in [clean_base, base]:
        if s and s not in seen:
            variants.append(s)
            seen.add(s)

    # Domain-based slug (often matches G2 slug exactly)
    domain = re.sub(r"^https?://(www\.)?", "", website).split("/")[0].split(".")[0]
    domain_slug = re.sub(r"[^a-z0-9]+", "-", domain.lower()).strip("-")
    if domain_slug and domain_slug not in seen:
        variants.insert(1, domain_slug)
        seen.add(domain_slug)

    # Common G2 suffix patterns for CS tools
    for suffix in ["customer-success", "cs", "platform", "crm", "software", "app"]:
        candidate = f"{clean_base}-{suffix}"
        if candidate not in seen:
            variants.append(candidate)
            seen.add(candidate)

    return variants


def fetch_g2(slug: str) -> dict | None:
    try:
        r = requests.get(
            f"https://{RAPIDAPI_HOST}/g2-products",
            params={"product": slug, "max_reviews": 1},
            headers=HEADERS,
            timeout=20,
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("product_name"):
                return data
        return None
    except Exception as e:
        print(f"    API error for {slug!r}: {e}")
        return None


def _match_is_plausible(vendor_name: str, g2_product_name: str) -> bool:
    """Sanity check: at least one significant word from vendor name appears in G2 product name."""
    stopwords = {"software", "inc", "llc", "ltd", "corp", "platform", "solutions",
                 "technologies", "group", "customer", "success", "the", "and", "for"}
    vendor_words = {w for w in re.split(r"\W+", vendor_name.lower()) if len(w) > 2 and w not in stopwords}
    g2_words = {w for w in re.split(r"\W+", g2_product_name.lower()) if len(w) > 2}
    return bool(vendor_words & g2_words)


def map_to_enrich_payload(vendor_name: str, website: str, data: dict) -> dict[str, Any]:
    cats = data.get("categories") or []
    g2_categories = [c["name"] for c in cats if isinstance(c, dict) and c.get("name")]
    if not g2_categories and data.get("category"):
        cat = data["category"]
        g2_categories = [cat["name"]] if isinstance(cat, dict) else []

    # Features for later M73 use
    features_flat: list[str] = []
    for group in data.get("features") or []:
        features_flat.extend(group.get("features") or [])

    pricing_plans = data.get("pricing_plans") or []
    pricing = [
        ": ".join(filter(None, [p.get("plan_name"), p.get("plan_price")]))
        for p in pricing_plans
        if p.get("plan_name")
    ]
    free_trial = any(
        re.search(r"free", (p.get("plan_name") or "") + (p.get("plan_price") or ""), re.I)
        for p in pricing_plans
    )

    # Compliance from features text
    features_text = json.dumps(data.get("features") or "")
    soc2 = bool(re.search(r"SOC\s*2", features_text))
    gdpr = bool(re.search(r"\bGDPR\b", features_text))
    compliance = [x for x in ["SOC 2" if soc2 else None, "GDPR" if gdpr else None] if x]

    payload: dict[str, Any] = {
        "website": website,
        "vendor_name": vendor_name,
        "pipeline_name": "g2_rapidapi",
        "g2_url": data.get("g2_link") or data.get("g2_reviews_link") or "",
        "g2_rating": data.get("rating"),
        "g2_review_count": data.get("reviews"),
        "g2_market_segment": "",
        "g2_categories": g2_categories,
        "soc2": soc2,
        "compliance": compliance,
    }

    # Bonus fields — only write if non-empty (safe-upsert protects existing values)
    founded_year = data.get("company_founded_year")
    if founded_year:
        payload["founded"] = str(founded_year)
    location = data.get("company_location") or ""
    if location:
        payload["hq_address"] = location
    if pricing:
        payload["pricing"] = pricing
        payload["free_trial"] = free_trial
        payload["pricing_source"] = "g2"

    return payload


def enrich_vendor(vendor_name: str, website: str, dry_run: bool) -> dict:
    variants = _slug_variants(vendor_name, website)
    data = None
    hit_slug = None
    for slug in variants:
        data = fetch_g2(slug)
        if data:
            hit_slug = slug
            break
        time.sleep(0.3)

    if not data:
        return {"vendor": vendor_name, "hit": False, "slugs_tried": variants[:3]}

    # Sanity check: G2 product name should plausibly match our vendor name
    g2_name = data.get("product_name", "")
    if not _match_is_plausible(vendor_name, g2_name):
        print(f"    ⚠ plausibility fail: {vendor_name!r} vs G2 {g2_name!r} — skipping")
        return {"vendor": vendor_name, "hit": False, "slugs_tried": variants[:3], "plausibility_fail": g2_name}

    payload = map_to_enrich_payload(vendor_name, website, data)

    if dry_run:
        return {
            "vendor": vendor_name,
            "hit": True,
            "slug": hit_slug,
            "g2_rating": payload.get("g2_rating"),
            "g2_review_count": payload.get("g2_review_count"),
            "g2_categories": payload.get("g2_categories"),
            "bonus_founded": payload.get("founded"),
            "bonus_hq": payload.get("hq_address"),
            "dry_run": True,
        }

    result = run_enrich_write(payload)
    return {
        "vendor": vendor_name,
        "hit": True,
        "slug": hit_slug,
        "g2_rating": payload.get("g2_rating"),
        "g2_review_count": payload.get("g2_review_count"),
        "write_result": result,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Fetch only, don't write to Supabase")
    parser.add_argument("--limit", type=int, default=0, help="Max vendors to process (0=all)")
    parser.add_argument("--vendor", help="Run for a single vendor name")
    args = parser.parse_args()

    client = supabase_client.get_supabase_client()

    if args.vendor:
        result = client.table("cs_vendors").select("name, website").ilike("name", f"%{args.vendor}%").limit(5).execute()
        vendors = result.data
    else:
        result = client.table("cs_vendors").select("name, website").eq("include_in_directory", True).execute()
        vendors = result.data

    if args.limit:
        vendors = vendors[: args.limit]

    print(f"Processing {len(vendors)} vendors {'(dry run)' if args.dry_run else ''}")

    hits, misses = 0, 0
    results = []
    for i, v in enumerate(vendors, 1):
        name = v["name"]
        website = v.get("website") or ""
        print(f"[{i}/{len(vendors)}] {name}")
        outcome = enrich_vendor(name, website, args.dry_run)
        if outcome["hit"]:
            hits += 1
            print(f"    ✓ slug={outcome['slug']} rating={outcome.get('g2_rating')} reviews={outcome.get('g2_review_count')}")
        else:
            misses += 1
            print(f"    ✗ miss (tried: {outcome.get('slugs_tried', [])})")
        results.append(outcome)
        time.sleep(0.5)  # rate limit courtesy

    print(f"\nDone. Hits: {hits}/{len(vendors)}, Misses: {misses}")

    out = PROJECT_ROOT / "runs" / "proofs" / "M72_g2_rapidapi_enrichment.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"hits": hits, "misses": misses, "total": len(vendors), "results": results}, indent=2))
    print(f"Proof written to {out}")


if __name__ == "__main__":
    main()
