"""
M76 Ops Workbench — Step 5: LLM Extraction (per-vendor).

Reads vendor_pages rows from Supabase for the target vendor, chunks the text,
optionally embeds with Ollama nomic-embed-text for RAG retrieval, then extracts
structured fields using GPT-4o (with Ollama as fast local fallback).

Writes result to crawl_llm_result in cs_vendors. Run Step 6 (merge) after.

Usage (via pipeline_control):
    python -m services.ops.run_llm_extraction --vendor https://gainsight.com
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
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
OLLAMA_BASE = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

CHUNK_SIZE = 400
CHUNK_OVERLAP = 50
TOP_K = 5

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

log = OpsLogger(milestone="M76")


def _chunk_text(text: str) -> list[str]:
    words = text.split()
    chunks, i = [], 0
    while i < len(words):
        chunk = " ".join(words[i: i + CHUNK_SIZE])
        if chunk.strip():
            chunks.append(chunk)
        i += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(x * x for x in b))
    return dot / (mag + 1e-9)


def _embed_ollama(text: str) -> list[float]:
    data = json.dumps({"model": "nomic-embed-text", "prompt": text}).encode()
    req = urllib.request.Request(f"{OLLAMA_BASE}/api/embeddings", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read()).get("embedding", [])


def _llm_ollama(prompt: str, model: str = "mistral") -> str:
    data = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": {"temperature": 0.1, "num_predict": 1024}}).encode()
    req = urllib.request.Request(f"{OLLAMA_BASE}/api/generate", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read()).get("response", "").strip()


def _llm_openai(prompt: str) -> str:
    from openai import OpenAI
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content.strip()


def llm_complete(prompt: str) -> str:
    try:
        result = _llm_openai(prompt)
        log.step_progress("llm_extraction", "GPT-4o mini responded")
        return result
    except Exception as e:
        log.step_progress("llm_extraction", f"OpenAI unavailable ({type(e).__name__}) — falling back to Mistral local")
        return _llm_ollama(prompt)


def _load_pages(vendor_website: str) -> list[dict]:
    url = (
        f"{SUPABASE_URL}/rest/v1/vendor_pages"
        f"?vendor_website=eq.{urllib.parse.quote(vendor_website, safe='')}"
        f"&select=page_url,title,clean_text&limit=200"
    )
    req = urllib.request.Request(url)
    req.add_header("apikey", SUPABASE_KEY)
    req.add_header("Authorization", f"Bearer {SUPABASE_KEY}")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read()) or []


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
    parser.add_argument("--vendor", required=True)
    args = parser.parse_args()

    vendor_website = args.vendor.strip()
    if not vendor_website.startswith("http"):
        vendor_website = "https://" + vendor_website

    if not SUPABASE_KEY:
        log.step_error("llm_extraction", "SUPABASE_KEY not set")
        return 1

    log.step_start("llm_extraction", f"Loading vendor_pages for {vendor_website}")
    pages = _load_pages(vendor_website)
    if not pages:
        log.step_error("llm_extraction", "No vendor_pages found — run Step 2 (crawl) first")
        return 1

    log.step_progress("llm_extraction", f"{len(pages)} pages loaded — building chunks")

    # Build chunks from all pages
    all_chunks: list[tuple[str, str]] = []  # (page_url, chunk_text)
    for p in pages:
        text = str(p.get("clean_text") or "")
        url = str(p.get("page_url") or "")
        for chunk in _chunk_text(text):
            all_chunks.append((url, chunk))

    log.step_progress("llm_extraction", f"{len(all_chunks)} chunks — attempting RAG with embeddings")

    # Try to embed with Ollama; fall back to no-embed (use first N chunks)
    use_rag = False
    chunk_vecs: list[tuple[str, str, list[float]]] = []
    try:
        for page_url, chunk in all_chunks[:100]:  # cap to avoid OOM
            vec = _embed_ollama(chunk)
            if vec:
                chunk_vecs.append((page_url, chunk, vec))
        use_rag = bool(chunk_vecs)
        log.step_progress("llm_extraction", f"Embedded {len(chunk_vecs)} chunks with Ollama")
    except Exception as e:
        log.step_progress("llm_extraction", f"Ollama embed unavailable ({e}) — using full-text mode")

    extracted: dict = {}

    for group in QUESTION_GROUPS:
        log.step_progress("llm_extraction", f"Extracting group: {group['group']}")

        if use_rag and chunk_vecs:
            try:
                q_vec = _embed_ollama(group["question"])
                ranked = sorted(chunk_vecs, key=lambda c: _cosine(q_vec, c[2]), reverse=True)[:TOP_K]
                context = "\n\n---\n\n".join(f"[{url}]\n{chunk}" for url, chunk, _ in ranked)
            except Exception:
                context = "\n\n---\n\n".join(chunk for _, chunk in all_chunks[:TOP_K])
        else:
            # No embeddings — use first TOP_K chunks as context
            context = "\n\n---\n\n".join(chunk for _, chunk in all_chunks[:TOP_K])

        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"QUESTION: {group['question']}\n\n"
            f"CONTEXT:\n{context}\n\n"
            f"Respond with JSON having these keys: {group['fields']}\n"
            f"JSON:"
        )

        try:
            response = llm_complete(prompt)
            clean = re.sub(r"```[a-z]*\n?", "", response).strip(" `\n")
            parsed = json.loads(clean)
            extracted.update(parsed)
        except Exception as e:
            log.step_progress("llm_extraction", f"Parse error for {group['group']}: {e}")

    if not extracted:
        log.step_error("llm_extraction", "No fields extracted")
        return 1

    result = {"source": "llm_gpt4o", "fields": extracted}
    _sb_patch(vendor_website, {"crawl_llm_result": result})
    log.step_done("llm_extraction", f"Stored LLM result for {vendor_website} — {len(extracted)} fields")
    return 0


if __name__ == "__main__":
    sys.exit(main())
