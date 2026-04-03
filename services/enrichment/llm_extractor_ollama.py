"""LLM extraction via Ollama — RAG pipeline over vendor_pages for structured field extraction.

Architecture:
  1. Fetch vendor_pages.clean_text rows from Supabase for the target vendor.
  2. Chunk each page into 400-word segments with 50-word overlap.
  3. Embed each chunk with nomic-embed-text via Ollama.
  4. Upsert chunk vectors into vendor_page_embeddings (Supabase pgvector).
  5. For each of 4 question groups: embed question → pgvector cosine search → top-k chunks.
  6. Send chunks + prompt to Mistral via Ollama → parse strict JSON response.
  7. Return a crawl_llm_result payload dict (caller is responsible for writing to Supabase).

Raises:
  ValueError  — vendor_pages has < 10 rows (Step 2 not run)
  ConnectionError — Ollama unreachable at ollama_base_url
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from services.ops.ops_logger import OpsLogger

if TYPE_CHECKING:
    from supabase import Client


# ---------------------------------------------------------------------------
# LLM prompt groups — 4 Mistral calls per vendor
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a data extraction assistant. "
    "You respond only with valid JSON. "
    "Never add explanation, preamble, markdown, or code fences. "
    "If a value cannot be determined from the provided text, use null."
)

_QUESTION_GROUPS: list[dict[str, Any]] = [
    {
        "group": "A_identity",
        "question": "What is this company's mission, unique selling proposition, ideal customer profile, and primary buyer persona?",
        "fields": ["mission", "usp", "icp", "icp_buyer"],
        "schema": {
            "mission": "string — one sentence describing what the company does and for whom",
            "usp": "string — what makes them different from competitors",
            "icp": "list of strings — industries or company types that are ideal customers",
            "icp_buyer": "string — job title and company context of the primary buyer",
        },
    },
    {
        "group": "B_lifecycle",
        "question": "What lifecycle stages, use cases, and products does this company offer?",
        "fields": ["lifecycle_stages", "use_cases", "products"],
        "schema": {
            "lifecycle_stages": "list of strings — customer lifecycle stages supported (e.g. onboarding, adoption, renewal, expansion)",
            "use_cases": "list of strings — specific problems or jobs the product solves",
            "products": "list of strings — named product lines or modules",
        },
    },
    {
        "group": "C_pricing",
        "question": "What is the pricing model, is there a free trial, does the site have a public pricing page, and what compliance certifications are mentioned?",
        "fields": ["pricing", "has_public_pricing_page", "free_trial", "soc2", "compliance"],
        "schema": {
            "pricing": "list of strings — pricing tiers or model description (e.g. per seat, usage-based)",
            "has_public_pricing_page": "boolean — true if a pricing page with actual prices is linked",
            "free_trial": "boolean — true if a free trial is explicitly offered",
            "soc2": "boolean — true if SOC 2 compliance is mentioned",
            "compliance": "list of strings — compliance certifications mentioned (e.g. SOC2, GDPR, ISO27001)",
        },
    },
    {
        "group": "D_integrations",
        "question": "What software integrations does this company support, who are their notable customers, and do they have case studies?",
        "fields": ["integrations", "customers", "case_studies"],
        "schema": {
            "integrations": "list of strings — named software tools this product integrates with",
            "customers": "list of strings — named companies that are customers",
            "case_studies": "list of strings — URLs or titles of case studies mentioned",
        },
    },
]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_llm_extraction(
    vendor_website: str,
    *,
    ollama_base_url: str = "http://localhost:11434",
    llm_model: str = "mistral:latest",
    embed_model: str = "nomic-embed-text",
    top_k_chunks: int = 5,
    supabase_client: "Client | None" = None,
    logger: OpsLogger | None = None,
) -> dict[str, Any]:
    """Full RAG pipeline for one vendor. Returns crawl_llm_result payload dict."""
    log = logger or OpsLogger()

    # --- Resolve Supabase client ---
    if supabase_client is None:
        from services.persistence import supabase_client as sc_module
        supabase_client = sc_module.get_supabase_client()

    # --- Pre-run guard: vendor_pages must exist ---
    log.step_start("llm_extract", f"Loading vendor_pages for {vendor_website}")
    pages_result = supabase_client.table("vendor_pages").select("page_url,clean_text,word_count").eq("vendor_website", vendor_website).execute()
    pages = [p for p in (pages_result.data or []) if p.get("clean_text")]
    if len(pages) < 10:
        raise ValueError(
            f"vendor_pages has only {len(pages)} rows for {vendor_website} — run Step 2 (Tier Crawl) first"
        )
    log.step_progress("llm_extract", f"Loaded {len(pages)} pages from vendor_pages")

    # --- Verify Ollama connectivity ---
    _check_ollama(ollama_base_url)

    # --- Chunk + embed ---
    all_chunks = _chunk_pages(pages)
    log.step_progress("embed_chunks", f"Chunking → {len(all_chunks)} chunks (400w, 50w overlap)")

    embeddings_created = _embed_and_upsert(
        all_chunks,
        vendor_website=vendor_website,
        ollama_base_url=ollama_base_url,
        embed_model=embed_model,
        supabase_client=supabase_client,
        log=log,
    )
    log.step_done("embed_chunks", f"✓ {embeddings_created} embeddings written to vendor_page_embeddings")

    # --- RAG + LLM extraction ---
    all_fields: dict[str, Any] = {}
    llm_calls = 0
    for group in _QUESTION_GROUPS:
        log.step_progress("llm_extract", f"Group {group['group']}: pgvector search → {top_k_chunks} chunks → Mistral...")
        top_chunks = _vector_search(
            group["question"],
            vendor_website=vendor_website,
            ollama_base_url=ollama_base_url,
            embed_model=embed_model,
            top_k=top_k_chunks,
            supabase_client=supabase_client,
        )
        extracted = _call_mistral(
            group,
            context_chunks=top_chunks,
            ollama_base_url=ollama_base_url,
            llm_model=llm_model,
        )
        llm_calls += 1
        all_fields.update(extracted)
        for field, value in extracted.items():
            if value is not None:
                log.step_progress("llm_extract", f"  ✓ {field}: {_truncate(value)}")

    log.step_done("llm_extract", f"✓ crawl_llm_result ready — {sum(1 for v in all_fields.values() if v is not None)} fields extracted")

    return {
        "ok": True,
        "pipeline": "csp-llm-extraction",
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "embeddings_created": embeddings_created,
        "llm_calls": llm_calls,
        "fields": all_fields,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check_ollama(base_url: str) -> None:
    """Verify Ollama is reachable. Raises ConnectionError if not."""
    try:
        req = urllib.request.Request(f"{base_url}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=5):
            pass
    except (urllib.error.URLError, OSError) as exc:
        raise ConnectionError(f"Ollama not reachable at {base_url}: {exc}") from exc


def _chunk_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Split page clean_text into 400-word chunks with 50-word overlap."""
    chunks: list[dict[str, Any]] = []
    for page in pages:
        text = str(page.get("clean_text") or "")
        words = text.split()
        step = 400 - 50  # 350-word steps to achieve 50-word overlap
        for i in range(0, max(len(words), 1), step):
            segment = words[i : i + 400]
            if not segment:
                break
            chunks.append({
                "page_url": page.get("page_url", ""),
                "chunk_index": len([c for c in chunks if c.get("page_url") == page.get("page_url")]),
                "chunk_text": " ".join(segment),
            })
    return chunks


def _embed_and_upsert(
    chunks: list[dict[str, Any]],
    *,
    vendor_website: str,
    ollama_base_url: str,
    embed_model: str,
    supabase_client: "Client",
    log: OpsLogger,
) -> int:
    """Embed each chunk with nomic-embed-text and upsert into vendor_page_embeddings."""
    rows = []
    for idx, chunk in enumerate(chunks, 1):
        if idx % 20 == 0 or idx == len(chunks):
            log.step_progress("embed_chunks", f"Embedding chunk {idx}/{len(chunks)}...")
        vector = _embed_text(chunk["chunk_text"], ollama_base_url=ollama_base_url, model=embed_model)
        rows.append({
            "vendor_website": vendor_website,
            "page_url": chunk["page_url"],
            "chunk_index": chunk["chunk_index"],
            "chunk_text": chunk["chunk_text"],
            "embedding": vector,
        })

    if rows:
        supabase_client.table("vendor_page_embeddings").upsert(
            rows,
            on_conflict="vendor_website,page_url,chunk_index",
        ).execute()

    return len(rows)


def _embed_text(text: str, *, ollama_base_url: str, model: str) -> list[float]:
    """Call Ollama embeddings API. Returns vector as list of floats."""
    payload = json.dumps({"model": model, "prompt": text}).encode("utf-8")
    req = urllib.request.Request(
        f"{ollama_base_url}/api/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError) as exc:
        raise ConnectionError(f"Ollama embed failed: {exc}") from exc
    return body.get("embedding", [])


def _vector_search(
    question: str,
    *,
    vendor_website: str,
    ollama_base_url: str,
    embed_model: str,
    top_k: int,
    supabase_client: "Client",
) -> list[str]:
    """Embed question, query pgvector for top-k similar chunks, return chunk texts."""
    question_vector = _embed_text(question, ollama_base_url=ollama_base_url, model=embed_model)
    # Use Supabase RPC for pgvector cosine similarity search
    result = supabase_client.rpc(
        "match_vendor_page_chunks",
        {
            "query_embedding": question_vector,
            "match_vendor_website": vendor_website,
            "match_count": top_k,
        },
    ).execute()
    chunks = result.data or []
    return [str(c.get("chunk_text") or "") for c in chunks if c.get("chunk_text")]


def _call_mistral(
    group: dict[str, Any],
    *,
    context_chunks: list[str],
    ollama_base_url: str,
    llm_model: str,
) -> dict[str, Any]:
    """Send context + schema prompt to Mistral. Parse and return field dict."""
    context = "\n\n---\n\n".join(context_chunks)
    schema_lines = "\n".join(f'  "{k}": {v}' for k, v in group["schema"].items())
    user_prompt = (
        f"Based only on the following text from a company's website, extract these fields as JSON:\n\n"
        f"{{\n{schema_lines}\n}}\n\n"
        f"Use null for any field you cannot determine from the text.\n\n"
        f"TEXT:\n{context}"
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    payload = json.dumps({
        "model": llm_model,
        "messages": messages,
        "stream": False,
        "format": "json",
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{ollama_base_url}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError) as exc:
        raise ConnectionError(f"Ollama chat failed: {exc}") from exc

    raw_content = (body.get("message") or {}).get("content") or ""
    return _parse_json_response(raw_content, expected_fields=group["fields"])


def _parse_json_response(raw: str, *, expected_fields: list[str]) -> dict[str, Any]:
    """Parse Mistral JSON output. Return dict with expected_fields keys (null for missing)."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return {f: None for f in expected_fields}
    if not isinstance(parsed, dict):
        return {f: None for f in expected_fields}
    return {f: parsed.get(f) for f in expected_fields}


def _truncate(value: Any, max_len: int = 80) -> str:
    text = str(value)
    return text[:max_len] + "..." if len(text) > max_len else text
