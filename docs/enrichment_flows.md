# Enrichment Flows — Have vs Need

**Last updated:** 2026-04-02  
**⚠️ Architectural decisions have moved to [`docs/kb.md`](kb.md) — that is the source of truth. This document tracks workflow build status only.**
**Project:** cs_vendors directory enrichment pipeline
**Context:** Both Apify and RapidAPI subscriptions are active. Datagma selected as firmographic source (single domain call → 65+ fields). Tracxn permanently dead.

---

## Flows We Have Today

### 1. Homepage Crawl + LLM Extraction
- **Type:** Python service (no n8n)
- **Files:** `services/enrichment/vendor_fetcher.py` → `services/extraction/llm_extractor.py`
- **Trigger:** Python pipeline runner (`scripts/run_pipeline.py`)
- **Fields written:** `name`, `raw_description`, `mission`, `usp`, `pricing`, `free_trial`, `use_cases`, `lifecycle_stages`, `icp`, `soc2`, `directory_fit`, `directory_category`, `include_in_directory`, `confidence`
- **Fill rates:** name 100% · mission/usp/icp 81–84% · integrations/customers/products/leadership 0–6% (LLM extracts but persistence broken)
- **Known issues:**
  - ~15% of `name` values are taglines not company names (fix: `_looks_like_tagline()` — merged M74 fix)
  - LLM extraction for `integrations`, `customers`, `products`, `value_statements`, `leadership`, `icp_buyer` returns data but fields not being written to Supabase
  - Direct HTTP fails on JS-rendered sites — no tier escalation today

### 2. Tracxn Enrichment
- **Type:** Python service + n8n workflow
- **Files:** `services/enrichment/tracxn_enricher.py` · `n8n/workflows/csp-tracxn-enrichment.workflow.json`
- **Status:** ⛔ **PERMANENTLY DEAD**
  - Tracxn changed URL scheme — `/d/companies/{slug}/` returns 404
  - Other paths return 403 (CloudFront WAF)
  - Both Python scraper and n8n workflow non-functional
- **Fields it used to write:** `founded`, `hq_address`, `company_hq`, `funding_stage`, `total_funding`
- **Current fill rates:** `founded` 92% (legacy data), `hq_address` 33%, `funding_stage` 0%, `total_funding` 0%
- **Replacement:** M75 — Datagma (RapidAPI) — see Flows We Need section

### 3. G2 Enrichment
- **Type:** n8n workflow + Python helper
- **Files:** `n8n/workflows/csp-g2-enrichment.workflow.json` · `services/enrichment/g2_enricher.py`
- **Trigger:** `pipeline_control.py` → `g2_rapidapi_enrichment` pipeline
- **API:** G2 Data API via RapidAPI (`g2-data-api.p.rapidapi.com`) — ✅ active subscription
- **Fields written:** `g2_url`, `g2_rating`, `g2_review_count`, `g2_categories`, `g2_market_segment`
- **Fill rate:** 17% (20/119 vendors) — pipeline exists but only ran on 20 vendors
- **Gap:** 99 vendors remain unenriched — just needs pipeline execution, no build work

### 4. Pricing Enrichment
- **Type:** n8n workflow + Python helper
- **Files:** `n8n/workflows/csp-pricing-enrichment.workflow.json` · `services/enrichment/pricing_enricher.py`
- **Trigger:** Python pipeline (via n8n webhook)
- **Fields written:** `pricing`, `has_public_pricing_page`, `free_trial`
- **Fill rate:** `pricing` 93% (but mostly `["$"]` signal only), `free_trial` 36%, `has_public_pricing_page` 0%
- **Known issue:** Pricing field stored as shallow signal — needs richer tier/plan data

### 5. Lead Capture Intake
- **Type:** n8n workflow
- **Files:** `n8n/workflows/csp-lead-capture-intake.workflow.json`
- **Purpose:** Not enrichment — handles inbound lead form submissions
- **Status:** Active (not relevant to vendor enrichment)

---

## Flows We Need (Build List)

### F1 — Site Crawl Tier 1: Direct HTTP
- **Milestone:** M74
- **n8n file:** `n8n/workflows/csp-crawl-tier1-direct.workflow.json`
- **Webhook path:** `csp-crawl-tier1-direct`
- **Cost:** Free (n8n HTTP Request node only)
- **What it does:** Fetches vendor homepage via plain HTTP, extracts name + visible text using `og:site_name` priority chain and tagline filter
- **Escalation condition:** `word_count < 200` OR name missing/tagline → caller escalates to Tier 2
- **Fields produced:** `name`, `word_count`, `text` (for LLM downstream), `tier_used: "tier1_direct"`
- **Status:** ✅ **BUILT** — see workflow JSON

### F2 — Site Crawl Tier 2: Apify RAG Web Browser
- **Milestone:** M74
- **n8n file:** `n8n/workflows/csp-crawl-tier2-rag.workflow.json`
- **Webhook path:** `csp-crawl-tier2-rag`
- **Cost:** ~$0.001/page
- **What it does:** Apify RAG Web Browser actor — handles JS-rendered SPAs
- **Escalation condition:** `word_count < 200` OR name missing → caller escalates to Tier 3
- **Status:** ✅ **BUILT** — see workflow JSON

### F3 — Site Crawl Tier 3: Apify WCC + Proxy
- **Milestone:** M74
- **n8n file:** `n8n/workflows/csp-crawl-tier3-wcc.workflow.json`
- **Webhook path:** `csp-crawl-tier3-wcc`
- **Cost:** ~$0.004/page
- **What it does:** Apify Website Content Crawler with Apify proxy — breaks Cloudflare/bot detection
- **Best effort:** Always returns result regardless of quality (last resort)
- **Status:** ✅ **BUILT** — see workflow JSON

### F4 — Google Discovery
- **Milestone:** M74
- **n8n file:** `n8n/workflows/csp-google-discovery.workflow.json`
- **Webhook path:** `csp-google-discovery`
- **Cost:** ~$0.0004/result (Apify Google Search Scraper)
- **What it does:** Accepts discovery queries → Apify Google Search → filters out review/directory sites → upserts candidates via `/admin/discovery-upsert`
- **Status:** ✅ **BUILT** — see workflow JSON

### F5 — Firmographic Enrichment (Datagma)
- **Milestone:** M75 (revised — Datagma replaces LinkedIn Company Scraper as primary)
- **n8n file:** `n8n/workflows/csp-firmographic-enrichment.workflow.json`
- **Webhook path:** `csp-firmographic-enrichment`
- **Cost:** Datagma on RapidAPI — flat $39–209/mo
- **API:** Datagma enrichment API (`enrichment-b2b-linkedin-crunchbase-datagma.p.rapidapi.com`)
- **What it does:** Single domain lookup → returns 65+ firmographic fields. Maps to cs_vendors safe-upsert.
- **Fields written:** `founded`, `hq_address`, `company_hq`, `funding_stage`, `total_funding`, `ceo_name`, `company_size`, `revenue` (new field)
- **Fallback:** Crunchbase API on RapidAPI (free Basic tier) for funding data if Datagma misses
- **Status:** ✅ **BUILT** — see workflow JSON
- **Pre-requisite:** Subscribe to Datagma on RapidAPI

### F6 — LinkedIn Enrichment (ceo_linkedin + executives)
- **Milestone:** M75
- **n8n file:** `n8n/workflows/csp-linkedin-enrichment.workflow.json`
- **Webhook path:** `csp-linkedin-enrichment`
- **API:** LinkedIn Data API on RapidAPI (`linkedin-data-api.p.rapidapi.com`)
- **What it does:** Company search by domain → returns executive profiles → extracts ceo_linkedin URL
- **Fields written:** `ceo_linkedin`, `linkedin_url` (new field), `leadership` array
- **Status:** ✅ **BUILT** — see workflow JSON
- **Pre-requisite:** Subscribe to LinkedIn Data API on RapidAPI

### F7 — G2 Full Run (existing workflow, all vendors)
- **Milestone:** Operational gap — no new build needed
- **What it does:** Run existing `csp-g2-enrichment` against all 99 unenriched `include_in_directory=true` vendors
- **Pipeline trigger:** `g2_rapidapi_enrichment` already in `pipeline_control.py`
- **Status:** Needs execution only

---

## Enrichment Pipeline Execution Order (M76 Workbench)

Six independent steps. Each writes to its own column — nothing overwrites another step. Merge (Step 6) is the only step that writes to main schema columns. See [`docs/kb.md §2`](kb.md#2-enrichment-architecture) for full merge priority rules.

```
Step 1  Google Discovery          → cs_vendor_candidates
Step 2  Three-Tier Crawl          → crawl_tier{1,2,3}_result + vendor_pages
Step 3  Datagma Firmographic      → crawl_datagma_result
Step 4  G2 Enrichment             → crawl_g2_result
Step 5  LLM Extraction (Ollama)   → crawl_llm_result + vendor_page_embeddings
Step 6  Clean Merge               → cs_vendors main columns + source_field_map
```

---

## Schema Changes Required

The following columns need to be added to `public.cs_vendors`:

```sql
-- Firmographic fields from Datagma/LinkedIn
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS company_size   text;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS revenue        text;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS linkedin_url   text;

-- G2 field not yet in schema
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS g2_market_segment text;
```

`VendorIntelligence` dataclass additions:
```python
company_size: str = ""
revenue: str = ""
linkedin_url: str = ""
g2_market_segment: str = ""
```

`admin_api.py` — add all four to `_SCALAR_FIELDS`.

---

## n8n Workflow Registry

| Workflow File | Webhook Path | Status | Source |
|---|---|---|---|
| `csp-g2-enrichment.workflow.json` | `csp-g2-enrichment` | ✅ Active | RapidAPI G2 |
| `csp-pricing-enrichment.workflow.json` | `csp-pricing-enrichment` | ✅ Active | Apify WCC |
| `csp-tracxn-enrichment.workflow.json` | `csp-tracxn-enrichment` | ⛔ Dead | Tracxn (404) |
| `csp-lead-capture-intake.workflow.json` | `csp-lead-capture` | ✅ Active | Lead forms |
| `csp-crawl-tier1-direct.workflow.json` | `csp-crawl-tier1-direct` | 🔧 Deploy needed | Free HTTP |
| `csp-crawl-tier2-rag.workflow.json` | `csp-crawl-tier2-rag` | 🔧 Deploy needed | Apify RAG |
| `csp-crawl-tier3-wcc.workflow.json` | `csp-crawl-tier3-wcc` | 🔧 Deploy needed | Apify WCC |
| `csp-google-discovery.workflow.json` | `csp-google-discovery` | 🔧 Deploy needed | Apify Google Search |
| `csp-firmographic-enrichment.workflow.json` | `csp-firmographic-enrichment` | 🔧 Deploy needed | Datagma (RapidAPI) |
| `csp-linkedin-enrichment.workflow.json` | `csp-linkedin-enrichment` | 🔧 Deploy needed | LinkedIn Data API (RapidAPI) |

---

## Admin Panel — Pipeline Controls

The following pipelines are / will be exposed as manual trigger buttons in `/admin`:

| Pipeline ID | Name | Trigger |
|---|---|---|
| `full_pipeline` | Full Discovery + Enrichment | Existing |
| `weekly_discovery_job` | Weekly Discovery | Existing |
| `g2_rapidapi_enrichment` | G2 Enrichment (all vendors) | Existing |
| `site_crawl_enrichment` | Site Crawl (Tiered) | Add |
| `firmographic_enrichment` | Firmographic (Datagma) | Add |
| `linkedin_enrichment` | LinkedIn Enrichment | Add |
| `google_discovery` | Google Discovery | Add |
| `full_enrichment_cycle` | **Full Enrichment Cycle** (all sources in order) | Add |
