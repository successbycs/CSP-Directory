"""
M96 — Vendor AI Summary (per-vendor).

Fetches the vendor website, extracts clean text, and uses GPT-4o mini to
generate a 400-word summary covering what the vendor does, who it's for,
key features, and where it fits in the Customer Success tech stack.

Stores the result in the ai_summary column of cs_vendors.

Usage (via pipeline_control):
    python -m services.ops.run_ai_summary --vendor https://gainsight.com
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from services.ops.ops_logger import OpsLogger

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

log = OpsLogger(milestone="M96")

SUMMARY_PROMPT = """You are writing a vendor profile summary for a Customer Success technology directory.

Write a clear, factual 400-word summary covering:
1. What the vendor does and the core problem it solves
2. Who it is for (ICP, target buyer, company size)
3. Key features and differentiators
4. Where it fits in the Customer Success tech stack (e.g. health scoring, onboarding, feedback analytics, etc.)
5. Any notable customers, outcomes, or proof points mentioned on the site

Write in third person, present tense. Be specific — use actual product names, features, and customer names from the content.
Do not use filler phrases like "In conclusion" or "Overall". Do not use em dashes.
Aim for exactly 400 words.

VENDOR WEBSITE CONTENT:
{content}

SUMMARY:"""


def _fetch_page(url: str) -> str:
    """Fetch a URL and return clean visible text."""
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0 (compatible; CSP-Directory/1.0)")
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", errors="replace")
        # Strip tags, scripts, styles
        import re
        html = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", " ", html, flags=re.S | re.I)
        html = re.sub(r"<[^>]+>", " ", html)
        html = re.sub(r"\s+", " ", html)
        return html.strip()[:8000]
    except Exception as e:
        log.step_progress("ai_summary", f"Fetch failed for {url}: {e}")
        return ""


def _load_vendor_pages(vendor_website: str) -> str:
    """Load clean text from vendor_pages table as fallback."""
    url = (
        f"{SUPABASE_URL}/rest/v1/vendor_pages"
        f"?vendor_website=eq.{urllib.parse.quote(vendor_website, safe='')}"
        f"&select=clean_text&limit=10"
    )
    req = urllib.request.Request(url)
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            rows = json.loads(r.read()) or []
            return " ".join(str(row.get("clean_text") or "") for row in rows)[:8000]
    except Exception:
        return ""


def _generate_summary(content: str) -> str:
    """Call GPT-4o mini to generate the vendor summary."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    payload = json.dumps({
        "model": "gpt-4o-mini",
        "temperature": 0.3,
        "max_tokens": 700,
        "messages": [
            {"role": "user", "content": SUMMARY_PROMPT.format(content=content)}
        ]
    }).encode()

    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=payload)
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")

    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"].strip()


def _sb_patch(vendor_website: str, fields: dict) -> None:
    url = f"{SUPABASE_URL}/rest/v1/cs_vendors?website=eq.{urllib.parse.quote(vendor_website, safe='')}"
    data = json.dumps(fields).encode()
    req = urllib.request.Request(url, data=data, method="PATCH")
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "return=minimal")
    with urllib.request.urlopen(req, timeout=15) as r:
        r.read()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vendor", required=True, help="Vendor website URL")
    parser.add_argument("--force", action="store_true", help="Regenerate even if ai_summary already exists")
    args = parser.parse_args()

    vendor_website = args.vendor.strip()
    if not vendor_website.startswith("http"):
        vendor_website = "https://" + vendor_website

    if not SUPABASE_KEY:
        log.step_error("ai_summary", "SUPABASE_KEY not set")
        return 1

    log.step_start("ai_summary", f"Generating AI summary for {vendor_website}")

    # Check if already exists (unless --force)
    if not args.force:
        check_url = (
            f"{SUPABASE_URL}/rest/v1/cs_vendors"
            f"?website=eq.{urllib.parse.quote(vendor_website, safe='')}"
            f"&select=ai_summary&limit=1"
        )
        req = urllib.request.Request(check_url)
        req.add_header("apikey", SUPABASE_KEY)
        req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                rows = json.loads(r.read())
                if rows and rows[0].get("ai_summary"):
                    log.step_done("ai_summary", "Already has ai_summary — skipping (use --force to regenerate)")
                    return 0
        except Exception:
            pass

    # Get content — try live fetch first, fall back to stored vendor_pages
    content = _fetch_page(vendor_website)
    if len(content.split()) < 200:
        log.step_progress("ai_summary", "Live fetch thin — supplementing with vendor_pages")
        stored = _load_vendor_pages(vendor_website)
        content = (content + " " + stored).strip()

    if len(content.split()) < 50:
        log.step_error("ai_summary", "Insufficient content to generate summary")
        return 1

    try:
        summary = _generate_summary(content)
    except Exception as e:
        log.step_error("ai_summary", f"GPT-4o mini failed: {e}")
        return 1

    _sb_patch(vendor_website, {"ai_summary": summary})
    word_count = len(summary.split())
    log.step_done("ai_summary", f"Stored {word_count}-word AI summary for {vendor_website}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
