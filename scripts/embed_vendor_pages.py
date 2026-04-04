"""
Embed vendor_pages → vendor_page_embeddings.

Reads clean_text from vendor_pages, chunks into ~400-word segments,
embeds each chunk with nomic-embed-text via Ollama, upserts to
vendor_page_embeddings (conflict: vendor_website, page_url, chunk_index).

Usage:
    python scripts/embed_vendor_pages.py [--vendor DOMAIN] [--limit N] [--force]

By default skips vendors that already have embeddings.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
OLLAMA_BASE   = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL   = "nomic-embed-text"

CHUNK_SIZE    = 400   # words per chunk
CHUNK_OVERLAP = 50    # word overlap


def _sb_req(method: str, path: str, body=None):
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "resolution=merge-duplicates")
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def get_vendors_with_pages() -> list[str]:
    rows = _sb_req("GET", "vendor_pages?select=vendor_website&limit=2000")
    seen = set()
    out = []
    for r in rows:
        d = r.get("vendor_website", "")
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def get_embedded_vendors() -> set[str]:
    rows = _sb_req("GET", "vendor_page_embeddings?select=vendor_website&limit=2000")
    return {r.get("vendor_website", "") for r in rows}


def get_pages(vendor_website: str) -> list[dict]:
    encoded = urllib.parse.quote(vendor_website, safe="")
    rows = _sb_req("GET", f"vendor_pages?vendor_website=eq.{encoded}&select=page_url,clean_text&limit=200")
    return [r for r in rows if r.get("clean_text") and len(r["clean_text"].split()) >= 30]


def chunk_text(text: str) -> list[str]:
    words = text.split()
    chunks, i = [], 0
    while i < len(words):
        chunks.append(" ".join(words[i: i + CHUNK_SIZE]))
        i += CHUNK_SIZE - CHUNK_OVERLAP
    return [c for c in chunks if c.strip()]


def embed(text: str) -> list[float]:
    data = json.dumps({"model": EMBED_MODEL, "prompt": text}).encode()
    req = urllib.request.Request(f"{OLLAMA_BASE}/api/embeddings", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read()).get("embedding", [])


def upsert_embeddings(rows: list[dict]) -> None:
    if not rows:
        return
    _sb_req("POST", "vendor_page_embeddings", rows)


def process_vendor(vendor_website: str) -> int:
    pages = get_pages(vendor_website)
    if not pages:
        return 0

    rows = []
    for page in pages:
        chunks = chunk_text(page["clean_text"])
        for idx, chunk in enumerate(chunks):
            vec = embed(chunk)
            if not vec:
                continue
            rows.append({
                "vendor_website": vendor_website,
                "page_url":       page["page_url"],
                "chunk_index":    idx,
                "chunk_text":     chunk,
                "embedding":      vec,
            })

    upsert_embeddings(rows)
    return len(rows)


def main(vendor_filter: str = "", limit: int = 0, force: bool = False) -> int:
    if not SUPABASE_KEY:
        print("ERROR: SUPABASE_KEY not set", flush=True)
        return 1

    all_vendors = get_vendors_with_pages()

    if vendor_filter:
        all_vendors = [v for v in all_vendors if vendor_filter.lower() in v.lower()]

    if not force:
        already = get_embedded_vendors()
        to_embed = [v for v in all_vendors if v not in already]
        print(f"Skipping {len(all_vendors) - len(to_embed)} vendors already embedded", flush=True)
    else:
        to_embed = all_vendors

    if limit:
        to_embed = to_embed[:limit]

    total = len(to_embed)
    if total == 0:
        print("Nothing to embed. Use --force to re-embed.", flush=True)
        return 0

    print(f"\nEmbedding {total} vendors with {EMBED_MODEL}\n", flush=True)

    for i, vendor in enumerate(to_embed, 1):
        print(f"[{i}/{total}] {vendor}…", end=" ", flush=True)
        try:
            n = process_vendor(vendor)
            print(f"{n} chunks", flush=True)
        except Exception as exc:
            print(f"ERROR: {exc}", flush=True)
        if i < total:
            time.sleep(0.2)

    print("\nDone.", flush=True)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Embed vendor_pages into vendor_page_embeddings")
    parser.add_argument("--vendor", default="", help="Filter to one vendor domain")
    parser.add_argument("--limit", type=int, default=0, help="Max vendors to process")
    parser.add_argument("--force", action="store_true", help="Re-embed vendors that already have embeddings")
    args = parser.parse_args()
    raise SystemExit(main(vendor_filter=args.vendor, limit=args.limit, force=args.force))
