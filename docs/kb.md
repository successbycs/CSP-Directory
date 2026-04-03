# CSP Directory — Knowledge Base & Architectural Decisions

**Source of truth for all design decisions, rejected alternatives, and rationale.**  
**Last updated:** 2026-04-03  
**Maintainer:** Updated at the end of every significant decision conversation.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Enrichment Architecture](#2-enrichment-architecture)
3. [Data Sources — Selected & Rejected](#3-data-sources--selected--rejected)
4. [LLM & Embedding Architecture](#4-llm--embedding-architecture)
5. [Storage Architecture](#5-storage-architecture)
6. [n8n Workflow Registry](#6-n8n-workflow-registry)
7. [Schema Decisions](#7-schema-decisions)
8. [Ops & Logging](#8-ops--logging)
9. [Milestone Map](#9-milestone-map)
10. [Environment & Infrastructure](#10-environment--infrastructure)
11. [M76 Build Record — Decisions & Execution](#11-m76-build-record--decisions--execution)

---

## 1. System Overview

CSP Directory is a vendor intelligence pipeline for the Customer Success software market. It discovers vendors, crawls their websites, enriches firmographic and product data from external sources, applies LLM extraction, and produces a curated public vendor directory.

**Core pipeline stages:**

```
Discovery → Crawl → External Enrichment → LLM Extraction → Merge → Directory
```

**Execution model:**  
- Operator-driven via admin ops page (manual, step-by-step)
- No automated scheduling until each step is validated individually
- n8n handles external API calls (crawl, Datagma, G2)
- Python handles LLM reasoning (local Ollama), merge logic, and persistence

---

## 2. Enrichment Architecture

### 2.1 Six-Step Workbench (M76)

Each step runs independently and writes to its own isolated column. The merge module (Step 6) is the only thing that writes to main schema columns.

| Step | What runs | Writes to | Technology |
|---|---|---|---|
| 1 | Google Discovery | `cs_vendor_candidates` | n8n → Apify Google Search |
| 2 | Three-tier website crawl | `crawl_tier{1,2,3}_result`, `vendor_pages` | n8n → HTTP / Apify RAG / Apify WCC |
| 3 | Datagma firmographic | `crawl_datagma_result` | n8n → RapidAPI Datagma |
| 4 | G2 enrichment | `crawl_g2_result` | n8n → RapidAPI G2 |
| 5 | LLM extraction | `crawl_llm_result`, `vendor_page_embeddings` | Python → Ollama (local) |
| 6 | Clean merge | main `cs_vendors` columns, `source_field_map` | Python merge_module.py |

### 2.2 Three-Tier Crawl

Tiers run cheapest-first. Escalation threshold: `word_count < 200` or name unresolved.

| Tier | Method | Cost | Best for |
|---|---|---|---|
| Tier 1 | Direct HTTP | Free | ~60% of static/SSR sites |
| Tier 2 | Apify RAG Web Browser | ~$0.001/page | JS-rendered SPAs |
| Tier 3 | Apify WCC + proxy | ~$0.004/page | Cloudflare-protected, bot-detected sites |

**Depth:** 100 pages per vendor (default). Configurable up to 300 from the ops page.  
**Rationale for 100 not 300:** First-run reliability — recrawl cadence is approximately monthly so the first run must succeed.

### 2.3 Merge Priority Rules

The merge module applies these rules per field. First non-null value from the priority chain wins.

| Field | Priority order |
|---|---|
| `name` | tier1 › tier2 › tier3 › datagma |
| `mission`, `usp` | llm › tier3 › tier2 |
| `icp`, `icp_buyer` | llm only |
| `use_cases`, `lifecycle_stages` | llm only |
| `founded` | datagma › g2 › llm |
| `hq_address`, `company_hq` | datagma › llm |
| `company_size`, `revenue` | datagma only |
| `funding_stage`, `total_funding` | datagma only |
| `ceo_name` | datagma › llm |
| `g2_*` fields | g2 only |
| `pricing` | tier3 › tier2 › llm |
| `has_public_pricing_page` | tier3 › tier2 › tier1 |
| `free_trial` | tier3 › tier2 › llm |
| `soc2`, `compliance` | llm › tier3 |
| `contact_page_url`, `demo_url`, `about_url` | tier3 › tier2 › tier1 |
| `integrations`, `integration_categories` | llm › tier3 |
| `customers`, `testimonials`, `case_studies` | llm › tier3 |

---

## 3. Data Sources — Selected & Rejected

### 3.1 Firmographic

**Selected: Datagma (RapidAPI)**  
- Single domain call returns 65+ fields: founded, HQ, company_size, funding_stage, total_funding, ceo_name, revenue  
- Flat pricing ($39–209/mo) vs per-call pricing  
- Hit rate: ~65% for SaaS companies — acceptable gap covered by LLM extraction from crawl

**Rejected: Tracxn**  
- PERMANENTLY DEAD. URL scheme `/d/companies/{slug}/` returns 404. CloudFront WAF returns 403 on all other paths. Both Python scraper and n8n workflow non-functional.  
- Decision date: 2026-03-xx. Not revisitable without a fundamentally new access method.

**Rejected: Lusha API**  
- Enterprise plan required (~$37k+/year). Not viable.

**Rejected: Apollo.io API**  
- Professional plan ($99+/month with per-enrichment credits). Possible future fallback but not selected.

**Rejected: LinkedIn Company Scraper (Apify — data-slayer actor)**  
- Original M75 plan used this. Switched to LinkedIn Data API on RapidAPI for reliability.
- Apify actor approach requires finding LinkedIn URL first (two-step), adds failure mode.

### 3.2 G2

**Selected: G2 Data API via RapidAPI (Chetan11-dev, `g2-data-api.p.rapidapi.com`)**  
- Rationale: G2 site uses Cloudflare Bot Management v2/v3 + JS rendering — cannot be scraped directly.  
- RapidAPI free tier covers ~100 vendors enriched once.  
- Hit rate: 33% (20/60 vendors in proof run). Gap due to vendors not having G2 listings.
- Fallback: `biegehydra/Advanced-G2-Scraper` on RapidAPI if Chetan11-dev degrades.

### 3.3 LLM

**Selected: Ollama (local, WSL) — mistral:latest**  
- Reasons: free, no API cost, 4.4GB fits within 11GB available RAM, 32k context sufficient when combined with RAG page selection  
- Model installed: `mistral:latest` (4.4GB)  
- **Context window limitation (32k):** Solved by RAG — only top 5 relevant chunks sent per question, not full 100-page corpus

**Rejected: OpenAI GPT-4o-mini for LLM extraction**  
- Cost: ~$0.15/1M input tokens — acceptable but unnecessary when Ollama is free  
- Kept as fallback env-var option in config

**Rejected: BigQuery + Vertex AI Gemini**  
- Considered for embeddings + LLM. Rejected because Supabase pgvector provides equivalent embedding/search at zero additional cost.

**Rejected: n8n Cloud for LLM steps**  
- n8n Cloud cannot reach Ollama on WSL localhost without an inbound tunnel (ngrok/Cloudflare tunnel)  
- Python service handles LLM steps instead — calls Ollama at localhost, writes to Supabase over outbound HTTPS. No tunnel required.

### 3.4 Embeddings

**Selected: nomic-embed-text (Ollama local)**  
- Size: 274MB  
- Output dimension: vector(768)  
- Purpose-built for text embedding (not code generation — `qwen2.5-coder` rejected for this reason)  
- Install: `ollama pull nomic-embed-text`

**Selected: Supabase pgvector for vector storage**  
- Already on Supabase — zero additional cost  
- ivfflat index for cosine similarity search  
- Extension: `CREATE EXTENSION IF NOT EXISTS vector`

### 3.5 Web Scraping Infrastructure

**Selected: Apify (Tier 2 RAG + Tier 3 WCC)**  
- `apify/rag-web-browser` — Tier 2, JS rendering, ~$0.001/page  
- `apify/website-content-crawler` — Tier 3, full anti-bot with proxy, ~$0.004/page

**Considered but not adopted: Scrapfly**  
- Scrapfly achieves 99% crawl success and is a direct Apify alternative  
- Provides anti-bot bypass, JS rendering, residential proxies  
- Does NOT provide firmographic data (founded, funding, CEO) — only improves crawl reliability  
- Not adopted for M76 — revisit if Apify tier hit rates prove insufficient post-M76

**Considered but not adopted: Clay**  
- Waterfall enrichment across 75+ providers — highest possible field coverage  
- Cost per record is high — not appropriate for bulk vendor directory enrichment  
- Future consideration if Datagma + G2 + LLM coverage proves inadequate

### 3.6 LinkedIn

**Excluded from M76 by design**  
- LinkedIn Data API (RapidAPI) produces: `linkedin_url`, `ceo_linkedin`, `ceo_name`, `leadership`  
- The 100-page website crawl surfaces `ceo_name` and `leadership` from /about and /team pages without API cost  
- The only unique LinkedIn value is personal profile URLs (`ceo_linkedin`) — not required for the directory at this stage  
- **Decision: Exclude from M76. Add as M78 only if website crawl miss rate on `ceo_name`/`leadership` proves unacceptably high after M76 proof run.**

---

## 4. LLM & Embedding Architecture

### 4.1 RAG Pattern

```
vendor_pages.clean_text (100 pages per vendor)
    │
    ├─ chunk: 400-word segments, 50-word overlap
    │
    ├─ nomic-embed-text → vector(768) per chunk
    │
    ├─ upsert → vendor_page_embeddings (Supabase pgvector)
    │
    └─ per question group:
          embed question → pgvector cosine search → top 5 chunks
          → Mistral prompt → strict JSON output → crawl_llm_result
```

### 4.2 LLM Prompt Groups (4 calls per vendor)

All prompts share system instruction: *"You are a data extraction assistant. You respond only with valid JSON. Never add explanation, preamble, or markdown. If a value cannot be determined from the provided text, use null."*

| Group | Fields extracted |
|---|---|
| A — Identity | `mission`, `usp`, `icp`, `icp_buyer` |
| B — Lifecycle | `lifecycle_stages`, `use_cases`, `products` |
| C — Pricing & compliance | `pricing`, `has_public_pricing_page`, `free_trial`, `soc2`, `compliance` |
| D — Integrations & social proof | `integrations`, `customers`, `case_studies` |

### 4.3 Connectivity

```
Python service (local)
    ├── Ollama (localhost:11434)        — local socket, never hits network
    └── Supabase (outbound HTTPS 443)  — standard egress, no firewall issues
```

No tunnel required. Python is the bridge between local Ollama and cloud Supabase.

---

## 5. Storage Architecture

### 5.1 Tables

| Table | Purpose |
|---|---|
| `cs_vendors` | Main vendor record — all schema fields + per-source result columns |
| `cs_vendor_candidates` | Discovery staging — candidates before promotion to cs_vendors |
| `vendor_pages` | Raw crawl output — one row per page per vendor (clean_text, no HTML) |
| `vendor_page_embeddings` | Vector chunks for RAG — one row per 400-word chunk |
| `integration_catalog` | Canonical integration name → category mapping |

### 5.2 Per-Source Result Columns on `cs_vendors`

Each column is JSONB, written exclusively by its step, never overwritten by another step.

| Column | Written by |
|---|---|
| `crawl_tier1_result` | Step 2 — Tier 1 crawl |
| `crawl_tier2_result` | Step 2 — Tier 2 crawl |
| `crawl_tier3_result` | Step 2 — Tier 3 crawl |
| `crawl_datagma_result` | Step 3 — Datagma |
| `crawl_g2_result` | Step 4 — G2 |
| `crawl_llm_result` | Step 5 — LLM extraction |
| `source_field_map` | Step 6 — Merge module output |

### 5.3 Storage Principles

- **No raw HTML stored** — `vendor_pages` stores `clean_text` only (HTML stripped, whitespace collapsed). Raw HTML would bloat storage 5–10x with no LLM benefit.
- **Upsert on re-crawl** — `UNIQUE (vendor_website, page_url)` on `vendor_pages` and `UNIQUE (vendor_website, page_url, chunk_index)` on `vendor_page_embeddings` mean re-running updates rows in place.
- **Main schema columns are merge-only** — only `merge_module.py` (Step 6) writes to `name`, `mission`, `founded`, etc. All other steps write to their `crawl_*_result` column.

---

## 6. n8n Workflow Registry

| File | Webhook path | Status | Source | Milestone |
|---|---|---|---|---|
| `csp-g2-enrichment.workflow.json` | `csp-g2-enrichment` | ✅ Active | RapidAPI G2 | M72 ✓ |
| `csp-pricing-enrichment.workflow.json` | `csp-pricing-enrichment` | ✅ Active | Apify WCC | Pre-M70 |
| `csp-tracxn-enrichment.workflow.json` | `csp-tracxn-enrichment` | ⛔ Dead | Tracxn (404/403) | Deprecated M74 |
| `csp-lead-capture-intake.workflow.json` | `csp-lead-capture` | ✅ Active | Lead forms | — |
| `csp-crawl-tier1-direct.workflow.json` | `csp-crawl-tier1-direct` | 🔧 Built, deploy needed | Free HTTP | M74 |
| `csp-crawl-tier2-rag.workflow.json` | `csp-crawl-tier2-rag` | 🔧 Built, deploy needed | Apify RAG | M74 |
| `csp-crawl-tier3-wcc.workflow.json` | `csp-crawl-tier3-wcc` | 🔧 Built, deploy needed | Apify WCC | M74 |
| `csp-google-discovery.workflow.json` | `csp-google-discovery` | 🔧 Built, deploy needed | Apify Google Search | M74 |
| `csp-firmographic-enrichment.workflow.json` | `csp-firmographic-enrichment` | 🔧 Built, deploy needed | Datagma (RapidAPI) | M75 |
| `csp-linkedin-enrichment.workflow.json` | `csp-linkedin-enrichment` | 🔧 Built, excluded M76 | LinkedIn Data API | Deferred to M78 |

**M76 workflow updates required (not new builds):**
- Tier 1/2/3: add `store-pages` write node + configurable `max_pages`
- Datagma: write to `crawl_datagma_result` (currently writes direct to main columns)
- G2: write to `crawl_g2_result` (currently writes direct to main columns)

---

## 7. Schema Decisions

### 7.1 Current pending migrations (`supabase/pending_migration.sql`)

```sql
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS company_size text;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS revenue      text;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS linkedin_url text;
```

### 7.2 M76 migrations (not yet applied)

```sql
-- Per-source result columns
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS crawl_tier1_result   jsonb;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS crawl_tier2_result   jsonb;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS crawl_tier3_result   jsonb;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS crawl_datagma_result jsonb;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS crawl_g2_result      jsonb;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS crawl_llm_result     jsonb;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS source_field_map     jsonb;

-- vendor_pages table
CREATE TABLE IF NOT EXISTS vendor_pages (
  id             bigserial    PRIMARY KEY,
  vendor_website text         NOT NULL,
  page_url       text         NOT NULL,
  title          text,
  clean_text     text,
  word_count     int,
  page_depth     int,
  tier_used      text,
  crawled_at     timestamptz  DEFAULT now(),
  UNIQUE (vendor_website, page_url)
);

-- vendor_page_embeddings table (requires pgvector extension)
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS vendor_page_embeddings (
  id             bigserial  PRIMARY KEY,
  vendor_website text       NOT NULL,
  page_url       text       NOT NULL,
  chunk_index    int        NOT NULL,
  chunk_text     text,
  embedding      vector(768),
  crawled_at     timestamptz DEFAULT now(),
  UNIQUE (vendor_website, page_url, chunk_index)
);

CREATE INDEX IF NOT EXISTS vendor_page_embeddings_vector_idx
  ON vendor_page_embeddings
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);
```

### 7.3 VendorIntelligence fields (services/extraction/vendor_intel.py)

All new fields added: `company_size`, `revenue`, `linkedin_url`, `funding_stage`, `total_funding`, `ceo_name`, `ceo_linkedin`, `leadership`.

### 7.4 admin_api.py _SCALAR_FIELDS

`company_size`, `revenue`, `linkedin_url`, `ceo_linkedin` confirmed added to `_SCALAR_FIELDS`.

### 7.5 Migration strategy

All M76 SQL uses `IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS` — idempotent and safe to re-run. Migration files accumulate in `supabase/pending_migration.sql` and are applied via `scripts/apply_schema_migration.py`.

**Convention:**
- Each milestone adds its SQL block to `pending_migration.sql` with a comment header (`-- M76 additions`)
- `apply_schema_migration.py` runs the full file against Supabase — idempotence means re-runs are safe
- After a migration is applied and verified, the block is NOT removed from the file — it serves as the migration history
- Never split migrations across multiple files; keep all pending SQL in the single `pending_migration.sql` file

---

## 8. Ops & Logging

### 8.0 AF Architectural Separation Exception

The Autonomous Framework (AF) convention separates research/planning agents from build agents. M76 is an exception: the AF triad was used to *review and improve milestone documents* (approach_assessor → architecture_reviewer → builder_risk_assessor), but all build execution happens in Claude Code directly (not via AF subagents). This is because M76 requires tight feedback loops between the ops page UI, admin API, and Python services — sequential subagent handoffs would introduce friction without benefit.

**Rule:** AF triad review → milestone doc updates → Claude Code builds. Not AF triad → AF build agent.

---

### 8.1 Pipeline execution model

- Pipelines are registered in `services/admin/pipeline_control.py` as `_PIPELINE_SPECS`
- Each spec has a `command` that runs as a subprocess with stdout/stderr piped to a log file
- `_tail_log()` reads last 12 lines, exposed via `/admin/pipelines` as `progress`
- Pipeline state persisted in `runs/pipeline_control_state.json`
- Log files stored in `runs/pipeline_logs/`

### 8.2 Live log panel

- Endpoint: `GET /admin/pipeline-log`
- Poll interval: 3 seconds (from ops page JS)
- Entry schema: `{timestamp, phase, milestone, action, message, success}`
- Colour coding: timestamp=grey, phase=blue, action=light blue, message=white, ✓=green, ✗=red

### 8.3 M76 logging additions

New service: `services/ops/ops_logger.py` — `OpsLogger` class with:
- `step_start(action, message)`
- `step_progress(action, message)` — shown as live update
- `step_done(action, message)`
- `step_error(action, message)`

All M76 Python services (llm_extractor_ollama.py, merge_module.py) use OpsLogger. Progress includes:
- Embedding: `chunk N/M`
- LLM: field-by-field extraction results
- Merge: every field decision with winning source

### 8.4 Timestamp convention

- **Storage:** UTC ISO 8601 in all database columns and JSONB fields
- **Display:** NZST (Pacific/Auckland) via existing `formatNzDateTime()` in admin.js

---

## 9. Milestone Map

| ID | Title | Status | Key decision |
|---|---|---|---|
| M72 | G2 via RapidAPI | ✅ Complete | Direct G2 scrape impossible (Cloudflare) — use RapidAPI |
| M74 | Three-tier crawl n8n workflows | 🔧 In progress | Workflows built; Python dispatch + vendor_pages write not yet done |
| M75 | Firmographic enrichment (Datagma) | 🔧 In progress | Tracxn dead → Datagma; LinkedIn deferred to M78 |
| M76 | Ops Enrichment Workbench | ✅ Built — proof run pending | All code built, schema migrated, Ollama ready. Gainsight proof run is next. |
| M77 | Architecture diagram | ⬜ Not started | Mermaid/PNG system diagram as repo artifact (depends on M76 proof) |
| M78 | LinkedIn enrichment | ⬜ Deferred | Only if M76 proves website crawl misses leadership consistently |

### M76 execution sequence — completed 2026-04-03

1. ✅ Enable pgvector on Supabase (vector 0.8.0)
2. ✅ Apply schema migration — all 38 columns confirmed present
3. ✅ Add `/admin/ops/store-crawl-result`, `/admin/ops/store-pages`, `GET /admin/ops/field-coverage` endpoints
4. ✅ Update Tier 1/2/3 n8n workflows (store-pages + store-crawl-result nodes added)
5. ✅ Update Datagma + G2 n8n workflows (replaced enrich-write with store-crawl-result)
6. ✅ `ollama pull nomic-embed-text` (pulled via AF ollama_client adapter)
7. ✅ Build `services/ops/ops_logger.py`
8. ✅ Build `services/enrichment/llm_extractor_ollama.py`
9. ✅ Build `services/enrichment/merge_module.py`
10. ✅ Register 8 M76 pipeline specs in `pipeline_control.py`
11. ✅ Build ops page UI — 6 step panels, Step 5 pre-run guard, field coverage report
12. ✅ Build verify scripts — `check_ollama_models.py`, `check_supabase_pgvector.py`, `check_admin_endpoints.py`
13. ✅ Build tests — 30 new M76 tests, 548 total passing (0 failures)
14. ⬜ **Next: single-vendor proof run — Gainsight, all 6 steps**

---

## 10. Environment & Infrastructure

### 10.1 Local environment (WSL — Piwakawaka)

| Component | Location | Notes |
|---|---|---|
| Python venv | `/home/chris/projects/CSP-Directory/.venv` | |
| Ollama | `localhost:11434` | WSL process |
| `mistral:latest` | Ollama | 4.4GB, installed |
| `nomic-embed-text` | Ollama | 274MB, **installed 2026-04-03** via AF ollama_client adapter |
| `qwen2.5-coder:7b` | Ollama | 4.7GB, also installed (AF use — not used by M76) |
| Admin API | `localhost:8787` | Served by `services/admin/admin_api.py` |
| RAM | 11GB available | mistral(4.4) + nomic(0.3) + services ≈ 8GB total |

### 10.2 Cloud services

| Service | Purpose | Auth |
|---|---|---|
| Supabase | PostgreSQL + pgvector + auth | `SUPABASE_URL`, `SUPABASE_KEY` in `.env` |
| n8n Cloud | Workflow execution (crawl/enrichment API calls) | n8n Cloud account |
| RapidAPI | Datagma + G2 + LinkedIn Data API | `RAPIDAPI_KEY` in `.env` |
| Apify | Google Search + RAG Browser + WCC | `APIFY_API_TOKEN` in `.env` |

### 10.3 Required env vars

```bash
# Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=xxx

# n8n webhook URLs (set once workflows are deployed)
N8N_CRAWL_TIER1_WEBHOOK=https://<n8n>/webhook/csp-crawl-tier1-direct
N8N_CRAWL_TIER2_WEBHOOK=https://<n8n>/webhook/csp-crawl-tier2-rag
N8N_CRAWL_TIER3_WEBHOOK=https://<n8n>/webhook/csp-crawl-tier3-wcc
N8N_DISCOVERY_WEBHOOK=https://<n8n>/webhook/csp-google-discovery
N8N_FIRMOGRAPHIC_WEBHOOK=https://<n8n>/webhook/csp-firmographic-enrichment
N8N_G2_WEBHOOK=https://<n8n>/webhook/csp-g2-enrichment

# External APIs
RAPIDAPI_KEY=xxx
APIFY_API_TOKEN=xxx

# Ollama (local — defaults are correct for WSL)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=mistral:latest
OLLAMA_EMBED_MODEL=nomic-embed-text

# Admin API
ADMIN_BASE_URL=http://127.0.0.1:8787
```

### 10.4 Supabase project details

| Field | Value |
|---|---|
| Project name | AI_CustomerSuccess |
| Project ID | `fadatnutpfnhxwctyvdt` |
| Region | ap-southeast-2 |
| Dashboard | `https://supabase.com/dashboard/project/fadatnutpfnhxwctyvdt` |
| SQL Editor | `https://supabase.com/dashboard/project/fadatnutpfnhxwctyvdt/sql/new` |
| pgvector version | 0.8.0 (enabled 2026-04-03) |

**Note on the Supabase MCP connection:** The Claude MCP Supabase connector is authenticated to a different Supabase account (shows projects `AI_CustomerSuccess` AF project + `tradify_kb`). It does **not** have access to the CSP Directory project (`fadatnutpfnhxwctyvdt`). DDL for this project must be applied via the SQL Editor dashboard or via `supabase login` + CLI.

### 10.5 Migration tooling — important gotcha

`scripts/apply_schema_migration.py` maintains its own `REQUIRED_COLUMNS` list and **writes** to `supabase/pending_migration.sql` when columns are missing (it does not read from that file). If M76+ columns are added to the script, it will overwrite the file with only those columns.

**Correct workflow for new migrations:**
1. Add new columns to `REQUIRED_COLUMNS` in `scripts/apply_schema_migration.py`
2. For new tables, functions, and indexes: write to `supabase/m<N>_migration.sql` (separate numbered file per milestone)
3. Apply via Supabase SQL Editor (paste and run)
4. Run `python3 scripts/apply_schema_migration.py` to confirm column presence

The file `supabase/pending_migration.sql` is generated output from the script — do not maintain it manually. Use named `m<N>_migration.sql` files for all DDL beyond `ALTER TABLE ADD COLUMN`.

**Applied migrations:**
| File | Applied | Contents |
|---|---|---|
| `supabase/pending_migration.sql` | Auto-generated | ALTER TABLE ADD COLUMN statements only |
| `supabase/m76_migration.sql` | 2026-04-03 | M76 full DDL: 7 columns, vendor_pages, vendor_page_embeddings, ivfflat index, match_vendor_page_chunks RPC |

### 10.6 Operational commands

```bash
# Start admin API
cd /home/chris/projects/CSP-Directory
source .venv/bin/activate
python3 -m services.admin.admin_api

# Apply schema migration (ALTER TABLE ADD COLUMN only)
python3 scripts/apply_schema_migration.py

# Verify full M76 schema (tables + columns + pgvector)
python3 scripts/check_supabase_pgvector.py

# Verify Ollama models installed
python3 scripts/check_ollama_models.py

# Verify admin ops endpoints responding
python3 scripts/check_admin_endpoints.py   # (requires admin API running)

# Check Ollama models
ollama list

# Pull embedding model (already done — kept for reference)
ollama pull nomic-embed-text

# Pull model via AF adapter (alternative to ollama CLI)
cd /home/chris/SuccessByCS-Builder/Autonomous-Framework
python3 -c "from tools.agent_cli.ollama_client import pull_model; pull_model('nomic-embed-text')"

# Run tests
python3 -m pytest tests/ -v

# Run autonomous audit
python3 scripts/autonomous_audit.py
```

---

## 11. M76 Build Record — Decisions & Execution

### 11.1 What was built (2026-04-03)

All M76 code was built in a single session. Nothing was pre-existing. Full list:

| File | What it does |
|---|---|
| `services/ops/__init__.py` | Package init |
| `services/ops/ops_logger.py` | OpsLogger — structured JSON log entries to stdout + optional file |
| `services/enrichment/llm_extractor_ollama.py` | Full RAG pipeline: vendor_pages → chunk → embed → pgvector search → Mistral → crawl_llm_result |
| `services/enrichment/merge_module.py` | COALESCE priority merge: all crawl_*_result → main cs_vendors columns + source_field_map |
| `services/admin/admin_api.py` | Added 3 new endpoints: store-crawl-result, store-pages, field-coverage |
| `services/admin/pipeline_control.py` | Added 8 M76 pipeline specs (ops_discovery_run through ops_merge) |
| `scripts/check_ollama_models.py` | Verify mistral:latest + nomic-embed-text installed |
| `scripts/check_supabase_pgvector.py` | Verify pgvector, vendor_pages, vendor_page_embeddings, crawl_*_result columns |
| `scripts/check_admin_endpoints.py` | Verify all /admin/ops/* endpoints respond + 8 pipeline specs registered |
| `scripts/apply_schema_migration.py` | Added M76 columns to REQUIRED_COLUMNS list |
| `supabase/m76_migration.sql` | Complete M76 DDL — applied 2026-04-03 |
| `n8n/workflows/csp-crawl-tier1-direct.workflow.json` | Added Store Pages + Store Crawl Result nodes |
| `n8n/workflows/csp-crawl-tier3-wcc.workflow.json` | Added Store Pages + Store Crawl Result nodes |
| `n8n/workflows/csp-firmographic-enrichment.workflow.json` | Replaced Enrich Write node with Store Crawl Result |
| `n8n/workflows/csp-g2-enrichment.workflow.json` | Replaced Upsert to Supabase node with Store Crawl Result |
| `docs/website/admin.html` | Added M76 Enrichment Workbench section with 6 step panels |
| `docs/website/admin.js` | Added opsSetVendor, opsRunStep, opsRunCrawlStep, opsLoadFieldCoverage functions |
| `docs/website/admin.css` | Added ops-step-card styles + source colour classes |
| `tests/test_merge_module.py` | 20 tests — _is_empty edge cases + run_merge priority/null/boolean rules |
| `tests/test_ops_endpoints.py` | 10 tests — store-crawl-result, store-pages, field-coverage endpoints |

### 11.2 Key design decisions made during build

**store-crawl-result is a new endpoint, not a modification of enrich-write**  
`/admin/enrich-write` was preserved unchanged. A new `/admin/ops/store-crawl-result` handles all writes to `crawl_*_result` columns. This was the highest-risk item identified in the AF triad review (95% stall likelihood if left ambiguous). Resolution: explicit new endpoint, column whitelist enforced server-side.

**boolean false is a valid value — not empty**  
`merge_module._is_empty()` explicitly returns `False` for `bool` values. `None`, `""`, `[]`, `{}` are all treated as empty. `False` is not — it must be written (e.g. `has_public_pricing_page: False` is meaningful data). This was documented as a critical edge case in the milestone spec.

**COALESCE pattern — Python-side, not SQL-side**  
The merge module builds an `updates` dict containing only non-null winning values and passes it to a single `.update()` call. It does NOT use `COALESCE()` in SQL. The Python-side filtering achieves the same effect: fields with no winning value are simply excluded from the update dict, leaving existing `cs_vendors` values unchanged.

**LLM prompt groups — 4 Mistral calls per vendor, not 1**  
A single prompt with all fields would exceed Mistral's 32k context when combined with 5 RAG chunks. Splitting into 4 groups (Identity / Lifecycle / Pricing / Integrations) keeps each call under ~4k tokens and allows more targeted vector search per group.

**ivfflat index underperforms below ~500 vectors — expected, not a bug**  
The proof run with a single vendor (~250 chunks) will show ~15ms query latency instead of ~0.5ms. This is normal ivfflat behaviour — the index only outperforms sequential scan above ~500 vectors. Do not remove or modify the index. It will improve automatically as more vendors are crawled.

**n8n tier workflows output format**  
Tier 1 produces a single page object. Tier 3 produces a `pages[]` array. The Store Pages node in each workflow was written to handle each format specifically — tier1 wraps the single object in an array; tier3 maps the `pages[]` array directly. The `page_url` field in tier3 maps from `item.url || item.loadedUrl`.

**G2 workflow was writing directly to Supabase REST, not via admin API**  
The original G2 workflow called `https://fadatnutpfnhxwctyvdt.supabase.co/rest/v1/cs_vendors` directly with a hardcoded API key. This bypassed the admin API entirely. Replaced with a Store Crawl Result node pointing to `/admin/ops/store-crawl-result` with `column: "crawl_g2_result"`. The direct Supabase write was the old approach pre-M76.

**Datagma workflow was writing to main columns via enrich-write**  
The `csp-firmographic-enrichment` workflow previously called `/admin/enrich-write`, which writes directly to main `cs_vendors` columns (name, founded, hq_address, etc.). M76 replaces this with a Store Crawl Result write to `crawl_datagma_result`. The merge module (Step 6) is now the only thing that writes to main columns from Datagma data.

### 11.3 AF triad review outcomes (applied before build)

The AF triad (approach_assessor → architecture_reviewer → builder_risk_assessor) reviewed the M76 milestone and identified 5 risks. All were fixed in the milestone doc before code was written:

| Risk | Likelihood | Resolution |
|---|---|---|
| enrich-write ambiguity | 95% stall | New `/admin/ops/store-crawl-result` endpoint spec added |
| Merge null-preservation underspecified | 70% bug | Full COALESCE pseudocode + Python pattern + edge cases documented |
| pgvector false performance alarm | 60% confusion | Explicit ivfflat warning added to milestone and schema docs |
| store-pages endpoint missing from spec | 50% gap | Full endpoint spec with request JSON added |
| Subjective acceptance criteria | — | Replaced with quantitative thresholds throughout |

Additional triad finding: M75 was incorrectly listed as M76 dependency. M76 explicitly excludes LinkedIn. Removed M75 from dependency array.

### 11.4 Schema migration execution record

| Date | Action | Result |
|---|---|---|
| 2026-04-03 | pgvector enabled via Supabase dashboard | vector 0.8.0 active |
| 2026-04-03 | `supabase/m76_migration.sql` applied via SQL Editor | vendor_pages, vendor_page_embeddings created; 7 crawl_*_result columns added; match_vendor_page_chunks RPC created |
| 2026-04-03 | `scripts/apply_schema_migration.py` | Confirmed 38/38 columns present |
| 2026-04-03 | `scripts/check_supabase_pgvector.py` | All checks passed |

### 11.5 Ollama model setup record

| Date | Action | Method |
|---|---|---|
| Pre-existing | `mistral:latest` (4.4GB) | Already installed |
| Pre-existing | `qwen2.5-coder:7b` (4.7GB) | Already installed (AF use) |
| 2026-04-03 | `nomic-embed-text` (274MB) | Pulled via AF `tools.agent_cli.ollama_client.pull_model()` |

The AF `ollama_client.py` at `/home/chris/SuccessByCS-Builder/Autonomous-Framework/tools/agent_cli/ollama_client.py` is the canonical adapter for all Ollama operations in this environment. It exposes `pull_model()`, `complete()`, `embed()`, `health_check()`, `list_models()` and is reusable across projects.

### 11.6 Test suite state post-M76 build

- **Total tests:** 548 passing, 3 deselected
- **New M76 tests:** 30 (test_merge_module.py × 20 + test_ops_endpoints.py × 10)
- **Regressions introduced:** 0
- **Test run time:** ~27–30 minutes (full suite)
- **Run date:** 2026-04-03

### 11.7 Pending before Gainsight proof run

1. Deploy updated n8n workflows to n8n Cloud (tier1, tier3, datagma, g2 — all modified locally)
2. Confirm `N8N_FIRMOGRAPHIC_WEBHOOK` and `N8N_G2_WEBHOOK` env vars point to deployed workflows
3. Start admin API: `python3 -m services.admin.admin_api`
4. Run `python3 scripts/check_admin_endpoints.py` — all 8 pipeline specs must appear
5. Open `http://127.0.0.1:8787` → Enrichment Workbench → set vendor to `https://gainsight.com`
6. Run steps 2 → 3 → 4 → 5 → 6 in order, watching Pipeline Log
7. Write proof artifact to `runs/proofs/M76_ops_enrichment_workbench.json`
