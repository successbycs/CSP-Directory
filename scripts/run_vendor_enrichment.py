"""
One-shot enrichment runner for a single vendor.

Steps:
  1. Crawl vendor website via site_explorer → collect page text
  2. POST pages to Supabase vendor_pages via REST API
  3. Chunk text, embed with nomic-embed-text, upsert to vendor_page_embeddings
  4. RAG extraction via qwen2.5-coder:7b (or configured llm_model)
  5. Print enriched profile JSON

Usage:
    python scripts/run_vendor_enrichment.py abloomify.com
    python scripts/run_vendor_enrichment.py abloomify.com --llm-model qwen2.5-coder:7b
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.enrichment.vendor_fetcher import fetch_vendor_homepage
from services.enrichment.site_explorer import explore_vendor_site
from services.extraction.page_text_extractor import extract_visible_text

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://fadatnutpfnhxwctyvdt.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
OLLAMA_BASE  = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

CHUNK_SIZE   = 400   # words per chunk
CHUNK_OVERLAP = 50   # word overlap between chunks
TOP_K        = 5     # chunks per question

QUESTION_GROUPS = [
    {
        "group": "identity",
        "question": (
            "What is this company's mission? What problem do they solve and for whom? "
            "What makes them unique vs competitors? What is their core value proposition?"
        ),
        "fields": ["mission", "usp", "value_proposition"],
    },
    {
        "group": "delivery",
        "question": (
            "How does this product deliver value? What are the specific features, workflows, "
            "or capabilities that make it work? What does a customer actually do with this tool day-to-day?"
        ),
        "fields": ["how_it_works", "key_features", "workflows"],
    },
    {
        "group": "icp_outcomes",
        "question": (
            "Who is the ideal customer? What job titles buy this? What outcomes or results "
            "do customers achieve? Are there any customer names, case studies, or metrics mentioned?"
        ),
        "fields": ["icp", "icp_buyer", "outcomes", "customers", "metrics"],
    },
    {
        "group": "commercial",
        "question": (
            "What is the pricing model? Is there a free trial? What lifecycle stages does this support "
            "(e.g. onboarding, adoption, renewal, expansion)? What integrations are mentioned?"
        ),
        "fields": ["pricing", "free_trial", "lifecycle_stages", "integrations"],
    },
]

SYSTEM_PROMPT = (
    "You are a structured data extraction assistant. "
    "Respond only with valid JSON matching the requested schema. "
    "Never add markdown, code fences, or explanation. "
    "Use null for any field you cannot determine from the provided text."
)


# ── Supabase helpers ──────────────────────────────────────────────────────────

def _sb_req(method: str, path: str, body: dict | list | None = None) -> dict | list:
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "return=minimal,resolution=merge-duplicates")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        print(f"  [supabase] {method} {path} → {e.code}: {body_text[:200]}", flush=True)
        return {}


def fetch_existing_pages(domain: str) -> list[dict]:
    """Return already-crawled pages from vendor_pages for this domain."""
    encoded = urllib.parse.quote(domain, safe="")
    path = f"vendor_pages?vendor_website=eq.{encoded}&select=page_url,clean_text,title&limit=300"
    rows = _sb_req("GET", path)
    if not isinstance(rows, list):
        return []
    result = []
    for r in rows:
        text = str(r.get("clean_text") or "").strip()
        url = str(r.get("page_url") or "").strip()
        if text and url:
            result.append({"url": url, "text": text, "title": str(r.get("title") or "")})
    return result


def upsert_pages(vendor_website: str, pages: list[dict]) -> int:
    rows = []
    for p in pages:
        text = str(p.get("text") or p.get("clean_text") or "").strip()
        if len(text.split()) < 30:
            continue
        rows.append({
            "vendor_website": vendor_website,
            "page_url":       str(p.get("url") or p.get("website") or "").strip(),
            "title":          str(p.get("title") or "")[:500],
            "clean_text":     text,
            "word_count":     len(text.split()),
            "tier_used":      "tier1_direct",
        })
    if not rows:
        return 0
    _sb_req("POST", "vendor_pages", rows)
    return len(rows)


# ── Chunking ──────────────────────────────────────────────────────────────────

def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i : i + size])
        if chunk.strip():
            chunks.append(chunk)
        i += size - overlap
    return chunks


# ── Ollama helpers ────────────────────────────────────────────────────────────

def _ollama(endpoint: str, payload: dict, timeout: int = 300) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"{OLLAMA_BASE}/{endpoint}", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def embed(text: str, model: str = "nomic-embed-text") -> list[float]:
    result = _ollama("api/embeddings", {"model": model, "prompt": text})
    return result.get("embedding", [])


def _llm_ollama(prompt: str, model: str, timeout: int = 45) -> str:
    """Try local Ollama — raises on timeout or error."""
    result = _ollama("api/generate", {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 1024},
    }, timeout=timeout)
    return result.get("response", "").strip()


def _llm_openai(prompt: str) -> str:
    """Fall back to OpenAI GPT-4o."""
    from openai import OpenAI
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content.strip()


def llm_complete(prompt: str, model: str) -> str:
    """Tiered LLM: try Ollama first (45 s), fall back to GPT-4o."""
    # Force OpenAI if model flag says so
    if model in ("openai", "gpt-4o", "gpt-4"):
        print("  [llm] Using GPT-4o", flush=True)
        return _llm_openai(prompt)
    # Try Ollama with a short timeout
    try:
        result = _llm_ollama(prompt, model, timeout=45)
        print(f"  [llm] Ollama ({model}) responded", flush=True)
        return result
    except Exception as e:
        print(f"  [llm] Ollama timed out ({e.__class__.__name__}) — falling back to GPT-4o", flush=True)
        return _llm_openai(prompt)


def cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    return dot / (mag_a * mag_b + 1e-9)


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run(vendor_website: str, llm_model: str) -> dict:
    # normalise
    if not vendor_website.startswith("http"):
        vendor_website = "https://" + vendor_website
    domain = vendor_website.replace("https://", "").replace("http://", "").rstrip("/")

    print(f"\n{'─'*60}", flush=True)
    print(f"Vendor: {vendor_website}", flush=True)
    print(f"LLM model: {llm_model}", flush=True)
    print(f"{'─'*60}\n", flush=True)

    # ── Step 1: Load pages (existing crawl data preferred) ────────────────
    print("Step 1 — Loading crawled pages…", flush=True)
    normalised: list[dict] = []

    if SUPABASE_KEY:
        normalised = fetch_existing_pages(domain)
        if normalised:
            print(f"  Using {len(normalised)} existing pages from vendor_pages (no re-crawl needed)", flush=True)

    if not normalised:
        print("  No pages in vendor_pages — run the tier crawl (Step 2) for this vendor first.", flush=True)
        return {}

    print("\nStep 2 — Skipped (pages already in Supabase)", flush=True)

    # ── Step 3: Chunk + embed ──────────────────────────────────────────────
    print("\nStep 3 — Chunking and embedding…", flush=True)
    all_chunks: list[tuple[str, str, list[float]]] = []  # (url, text, embedding)
    for p in normalised:
        chunks = chunk_text(p["text"])
        for i, chunk in enumerate(chunks):
            print(f"  Embedding chunk {len(all_chunks)+1} ({p['url'][:50]}…)  ", end="\r", flush=True)
            vec = embed(chunk)
            if vec:
                all_chunks.append((p["url"], chunk, vec))
    print(f"\n  Total chunks embedded: {len(all_chunks)}", flush=True)

    if not all_chunks:
        print("ERROR: No chunks to work with.", flush=True)
        return {}

    # ── Step 4: RAG extraction ─────────────────────────────────────────────
    print(f"\nStep 4 — LLM extraction ({llm_model})…", flush=True)
    extracted: dict = {}

    for group in QUESTION_GROUPS:
        print(f"\n  [{group['group']}] {group['question'][:70]}…", flush=True)

        # embed question
        q_vec = embed(group["question"])
        if not q_vec:
            continue

        # rank chunks by cosine similarity
        ranked = sorted(
            all_chunks,
            key=lambda c: cosine_sim(q_vec, c[2]),
            reverse=True,
        )[:TOP_K]

        context = "\n\n---\n\n".join(f"[{url}]\n{chunk}" for url, chunk, _ in ranked)

        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"QUESTION: {group['question']}\n\n"
            f"CONTEXT (from vendor website):\n{context}\n\n"
            f"Respond with JSON having these keys: {group['fields']}\n"
            f"JSON:"
        )

        response = llm_complete(prompt, llm_model)
        print(f"  Raw response: {response[:200]}", flush=True)

        # parse JSON — strip any accidental markdown
        try:
            response_clean = re.sub(r"```[a-z]*\n?", "", response).strip(" `\n")
            parsed = json.loads(response_clean)
            extracted.update(parsed)
        except json.JSONDecodeError:
            print(f"  WARNING: JSON parse failed for group {group['group']}", flush=True)

    return extracted


import re

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

    parser = argparse.ArgumentParser(description="Run vendor enrichment pipeline")
    parser.add_argument("vendor", help="Vendor website domain or URL (e.g. abloomify.com)")
    parser.add_argument("--llm-model", default="mistral", help="Ollama model to try first; use 'gpt-4o' to force OpenAI")
    args = parser.parse_args()

    result = run(args.vendor, args.llm_model)
    print("\n" + "═"*60)
    print("ENRICHED PROFILE:")
    print("═"*60)
    print(json.dumps(result, indent=2))
