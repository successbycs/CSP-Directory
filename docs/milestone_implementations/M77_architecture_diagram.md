# M77 Implementation Plan — System Architecture Diagram

**Status:** not_started  
**Depends on:** M76 (so the diagram reflects the fully confirmed architecture)  
**Proof artifact:** `docs/architecture/system_architecture.png`

---

## Problem Statement

There is no visual representation of the CSP Directory system architecture. New contributors, the operator, and any future agents working on this codebase have to reconstruct the system from code and docs. A single accurate diagram would eliminate this overhead and serve as a reference for all architectural decisions.

---

## Deliverable

A single high-resolution PNG (`docs/architecture/system_architecture.png`) generated from a Mermaid source file (`docs/architecture/system_architecture.mmd`). The Mermaid source is version-controlled so the diagram can be regenerated whenever the architecture changes.

The diagram must be accurate to the M76 confirmed architecture — not aspirational.

---

## Diagram Scope

The diagram covers all layers of the system in a single view:

### Layer 1 — Operator & UI
- Admin ops page (browser)
- Six step panels (Discovery, Tier Crawl, Datagma, G2, LLM, Merge)
- Pipeline log panel (3-second live poll)

### Layer 2 — Local Python Services (WSL — Piwakawaka)
- `services/admin/admin_api.py` — WSGI server, all `/admin/*` endpoints
- `services/admin/pipeline_control.py` — subprocess runner, log tailing
- `services/enrichment/llm_extractor_ollama.py` — RAG pipeline
- `services/enrichment/merge_module.py` — field merge with priority rules
- `services/ops/ops_logger.py` — structured log emitter

### Layer 3 — Local AI (WSL — Piwakawaka)
- Ollama at `localhost:11434`
  - `mistral:latest` (LLM extraction, 4 calls/vendor)
  - `nomic-embed-text` (chunk embedding, vector(768))

### Layer 4 — n8n Cloud Workflows
- `csp-google-discovery` → Apify Google Search Scraper
- `csp-crawl-tier1-direct` → Direct HTTP
- `csp-crawl-tier2-rag` → Apify RAG Web Browser
- `csp-crawl-tier3-wcc` → Apify WCC + proxy
- `csp-firmographic-enrichment` → RapidAPI Datagma
- `csp-g2-enrichment` → RapidAPI G2 Data API

### Layer 5 — External APIs
- Apify (Google Search, RAG Browser, WCC)
- RapidAPI Datagma (`enrichment-b2b-linkedin-crunchbase-datagma.p.rapidapi.com`)
- RapidAPI G2 (`g2-data-api.p.rapidapi.com`)

### Layer 6 — Supabase Cloud (PostgreSQL + pgvector)
- `cs_vendor_candidates` — discovery staging
- `cs_vendors` — main vendor records + all `crawl_*_result` JSONB columns + `source_field_map`
- `vendor_pages` — crawled page content (clean_text, one row per page)
- `vendor_page_embeddings` — RAG vector store (vector(768), ivfflat index)
- `integration_catalog` — canonical integration taxonomy

### Data flows shown
- Operator trigger → admin API → n8n webhook (for crawl/enrichment steps)
- n8n → external API → response → `/admin/ops/store-pages` → Supabase
- n8n → result → `crawl_*_result` column on `cs_vendors`
- Admin API → Python LLM service → Ollama (localhost) → Supabase pgvector (write embeddings)
- Python LLM service → pgvector similarity search → Supabase → top 5 chunks → Ollama → crawl_llm_result
- Merge module → reads all `crawl_*_result` → writes main schema columns + `source_field_map`
- Log emitter → `/admin/pipeline-log` → ops page (3s poll)

---

## Mermaid Source Location

`docs/architecture/system_architecture.mmd`

The Mermaid diagram uses `flowchart TD` (top-down) with subgraphs per layer. Nodes are grouped and colour-coded by layer:

- Operator/UI: light blue
- Local Python: dark blue
- Local Ollama: purple
- n8n Cloud: orange
- External APIs: grey
- Supabase: green

---

## PNG Generation

```bash
# One-time install of Mermaid CLI
npm install -g @mermaid-js/mermaid-cli

# Generate PNG from source
mmdc -i docs/architecture/system_architecture.mmd \
     -o docs/architecture/system_architecture.png \
     -w 2400 -H 1800 \
     --backgroundColor white
```

The PNG is committed to the repo at `docs/architecture/system_architecture.png`.

---

## Acceptance Criteria

- [ ] `docs/architecture/system_architecture.mmd` committed and valid Mermaid syntax
- [ ] `docs/architecture/system_architecture.png` committed at 2400×1800px minimum
- [ ] All 6 layers present in the diagram
- [ ] All data flows accurately shown (no aspirational flows)
- [ ] n8n workflows listed by name, not generic "n8n"
- [ ] Supabase tables listed individually
- [ ] Ollama models named explicitly (mistral:latest, nomic-embed-text)
- [ ] `docs/kb.md` references the diagram location
- [ ] Diagram regenerates cleanly from `.mmd` source via `mmdc`

## Not In Scope

- Interactive diagrams
- Separate diagrams per layer (single unified view only)
- Sequence diagrams (data flow is shown on the architecture diagram with labelled arrows)
