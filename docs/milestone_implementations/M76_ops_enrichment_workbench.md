# M76 Implementation Plan — Ops Enrichment Workbench

**Status:** not_started  
**Depends on:** M72 ✓, M74 (must be complete before M76 starts)  
**M75 removed from dependencies** — LinkedIn excluded from this milestone; M75 workflows are in progress but not required here.  
**Proof artifact:** `runs/proofs/M76_ops_enrichment_workbench.json`

---

## Problem Statement

Enrichment today is opaque — the operator triggers a full pipeline and cannot see what each source produced, which fields each technique filled, or why a particular value ended up in the final record. There is no way to validate one enrichment step before chaining others. The ops page has Run buttons but no per-step transparency.

This milestone builds a structured, operator-driven **Enrichment Workbench**: six step panels running independently, each source writing to its own isolated column, with a merge module making the final decisions and an enhanced live log showing exactly what is happening at every stage.

---

## Human Approval Gates — REQUIRED BEFORE AF EXECUTION STARTS

All four gates must be confirmed by the operator before AF begins any build work.

```
GATE 1 — M74 Complete
  M74 (Three-Tier Crawl) must be complete and all three tier crawl workflows
  deployed and tested on n8n Cloud before M76 starts.
  
  Verify: Run a Tier 3 crawl on gainsight.com, then:
    SELECT COUNT(*) FROM vendor_pages WHERE vendor_website='https://gainsight.com'
  Result must be >= 50 rows. If 0 or < 20: M74 is not writing correctly. Stop.

GATE 2 — n8n Webhook URLs Configured
  All six webhook env vars must be set and tested before ops page can run steps 2–4.
  Test each with a dummy POST and verify 2xx response:
    N8N_CRAWL_TIER1_WEBHOOK
    N8N_CRAWL_TIER2_WEBHOOK
    N8N_CRAWL_TIER3_WEBHOOK
    N8N_DISCOVERY_WEBHOOK
    N8N_FIRMOGRAPHIC_WEBHOOK
    N8N_G2_WEBHOOK

GATE 3 — Ollama Models Installed
  Run: ollama list
  Must show both:
    mistral:latest        (4.4GB — already installed)
    nomic-embed-text      (274MB — if missing: ollama pull nomic-embed-text)

GATE 4 — pgvector Enabled on Supabase
  Option A: Supabase dashboard → Database → Extensions → search "vector" → Enable
  Option B: Run in Supabase SQL editor: CREATE EXTENSION IF NOT EXISTS vector;
  Verify: SELECT * FROM pg_extension WHERE extname='vector'; (must return 1 row)
```

---

## Confirmed Architecture

```
Ops Page (browser)
    │
    ├─ Step 1: Google Discovery       → n8n webhook → Apify Google Search
    ├─ Step 2: Three-Tier Crawl       → n8n webhooks (Tier 1 / 2 / 3)
    │                                      ├─ pages → /admin/ops/store-pages → vendor_pages
    │                                      └─ result → /admin/ops/store-crawl-result → crawl_tier{N}_result
    ├─ Step 3: Datagma Enrichment     → n8n webhook → RapidAPI Datagma
    │                                      └─ result → /admin/ops/store-crawl-result → crawl_datagma_result
    ├─ Step 4: G2 Enrichment          → n8n webhook → RapidAPI G2
    │                                      └─ result → /admin/ops/store-crawl-result → crawl_g2_result
    ├─ Step 5: LLM Extraction         → Python service (local, subprocess)
    │               ├─ reads vendor_pages.clean_text from Supabase (outbound HTTPS)
    │               ├─ chunks text → nomic-embed-text at localhost:11434
    │               ├─ writes vectors → vendor_page_embeddings (Supabase pgvector)
    │               ├─ per field group: embed question → pgvector search → top 5 chunks
    │               └─ Mistral at localhost:11434 → JSON → crawl_llm_result
    └─ Step 6: Clean Merge            → Python service (local, subprocess)
                    ├─ reads all crawl_*_result JSONB columns from Supabase
                    ├─ applies COALESCE-based priority rules per field
                    ├─ writes only non-null winning values to main cs_vendors columns
                    └─ writes source_field_map
```

### AF Architectural Note

Steps 2–4 have Python admin API calling n8n webhooks — this is a pragmatic exception to the AF control-plane/integration-surface separation rule. The admin API here is a local operator-facing control surface, not AF framework orchestration. n8n is called as a managed side-effect, not a governed integration surface. This exception is acceptable for a local operator tool and is documented in `docs/kb.md §8`.

### Critical: enrich-write is NOT modified

The existing `/admin/enrich-write` endpoint is **not touched**. A new endpoint `/admin/ops/store-crawl-result` handles all writes to `crawl_*_result` columns. The merge module (Step 6) continues to use the existing upsert path for main column writes. This preserves backward compatibility with all existing workflows.

---

## Deliverable 1 — Supabase Schema Changes

All SQL in `supabase/pending_migration.sql`, applied via `scripts/apply_schema_migration.py`. All statements use `IF NOT EXISTS` — safe to re-run.

### 1a. New columns on `cs_vendors`

```sql
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS crawl_tier1_result   jsonb;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS crawl_tier2_result   jsonb;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS crawl_tier3_result   jsonb;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS crawl_datagma_result jsonb;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS crawl_g2_result      jsonb;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS crawl_llm_result     jsonb;
ALTER TABLE cs_vendors ADD COLUMN IF NOT EXISTS source_field_map     jsonb;
```

**`crawl_*_result` column contract (all sources share this shape):**

```json
{
  "ok": true,
  "pipeline": "csp-crawl-tier3-wcc",
  "crawled_at": "2026-04-02T10:30:00+00:00",
  "pages_fetched": 87,
  "word_count": 42000,
  "fields": {
    "name": "Gainsight",
    "mission": "The leading customer success platform",
    "contact_page_url": "https://gainsight.com/contact",
    "has_public_pricing_page": false
  }
}
```

**`source_field_map` contract:**

```json
{
  "name":       "tier1",
  "mission":    "llm",
  "founded":    "datagma",
  "g2_rating":  "g2",
  "icp_buyer":  "llm"
}
```

### 1b. New table: `vendor_pages`

```sql
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

CREATE INDEX IF NOT EXISTS vendor_pages_website_idx    ON vendor_pages (vendor_website);
CREATE INDEX IF NOT EXISTS vendor_pages_crawled_at_idx ON vendor_pages (crawled_at DESC);
```

No raw HTML. `clean_text` only (HTML stripped, whitespace collapsed). `UNIQUE` constraint means re-crawls upsert, not duplicate.

### 1c. New table: `vendor_page_embeddings`

```sql
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

CREATE INDEX IF NOT EXISTS vendor_page_embeddings_website_idx
  ON vendor_page_embeddings (vendor_website);

CREATE INDEX IF NOT EXISTS vendor_page_embeddings_vector_idx
  ON vendor_page_embeddings
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);
```

**⚠️ ivfflat index performance note for builder:**
The ivfflat index underperforms sequential scan below ~500 vectors. During the proof run (single vendor, ~250 vectors), query latency will be ~15ms instead of ~0.5ms. This is **expected and correct** — do not modify the index. Performance improves automatically as more vendors are crawled. Do not spend time optimising the index during proof run.

### 1d. Migration safety

`scripts/apply_schema_migration.py` must use `IF NOT EXISTS` on all `CREATE` and `ADD COLUMN` statements. Verify this before running. The script must be safe to re-run without error if tables/columns already exist.

---

## Deliverable 2 — New Admin API Endpoint: `/admin/ops/store-crawl-result`

**This is a new endpoint, separate from `/admin/enrich-write`.** It writes JSONB directly to a named `crawl_*_result` column. It does not create a VendorIntelligence object. It does not touch main schema columns.

### Request

```json
{
  "vendor_website": "https://gainsight.com",
  "column": "crawl_datagma_result",
  "payload": {
    "ok": true,
    "pipeline": "csp-firmographic-enrichment",
    "crawled_at": "2026-04-02T10:31:00+00:00",
    "fields": {
      "founded": "2013",
      "hq_address": "San Francisco, CA, USA",
      "company_size": "501-1000"
    }
  }
}
```

### Response

```json
{ "ok": true, "vendor_website": "https://gainsight.com", "column": "crawl_datagma_result" }
```

### Implementation pattern (follow existing admin_api.py style)

```python
if method == "POST" and path == "/admin/ops/store-crawl-result":
    payload = _parse_json_body(environ)
    return _store_crawl_result_response(start_response, payload)

def _store_crawl_result_response(start_response, payload):
    allowed_columns = {
        "crawl_tier1_result", "crawl_tier2_result", "crawl_tier3_result",
        "crawl_datagma_result", "crawl_g2_result", "crawl_llm_result",
    }
    column = payload.get("column", "")
    if column not in allowed_columns:
        return _error_response(start_response, f"Unknown column: {column}")
    supabase.table("cs_vendors").update(
        {column: payload["payload"]}
    ).eq("website", payload["vendor_website"]).execute()
    return _json_response(start_response, {"ok": True, "column": column})
```

---

## Deliverable 3 — All Admin API Endpoints

All eight endpoints registered as **pipeline specs in `pipeline_control.py`** so they run as subprocesses and stream logs to `/admin/pipeline-log`. The ops page Run buttons call `POST /admin/pipelines/run` with the `pipeline_id`, not the endpoint directly.

| pipeline_id | Endpoint | Purpose |
|---|---|---|
| `ops_discovery_run` | `/admin/ops/discovery-run` | Google Discovery with configurable page depth |
| `ops_crawl_tier1` | `/admin/ops/crawl-tier` (tier=1) | Tier 1 HTTP crawl for one vendor |
| `ops_crawl_tier2` | `/admin/ops/crawl-tier` (tier=2) | Tier 2 Apify RAG crawl |
| `ops_crawl_tier3` | `/admin/ops/crawl-tier` (tier=3) | Tier 3 Apify WCC crawl |
| `ops_store_pages` | `/admin/ops/store-pages` | Called by n8n: write pages to vendor_pages |
| `ops_store_crawl_result` | `/admin/ops/store-crawl-result` | Called by n8n: write to crawl_*_result column |
| `ops_crawl_datagma` | `/admin/ops/crawl-datagma` | Datagma enrichment for one vendor |
| `ops_crawl_g2` | `/admin/ops/crawl-g2` | G2 enrichment for one vendor |
| `ops_crawl_llm` | `/admin/ops/crawl-llm` | LLM extraction for one vendor |
| `ops_merge` | `/admin/ops/merge` | Clean merge for one vendor |
| `ops_field_coverage` | `GET /admin/ops/field-coverage` | Per-vendor per-field coverage report |

### `/admin/ops/store-pages` — called by n8n workflows

```json
{
  "vendor_website": "https://gainsight.com",
  "tier_used": "tier3_wcc",
  "pages": [
    {
      "page_url": "https://gainsight.com/about",
      "title": "About Gainsight",
      "clean_text": "Gainsight is the leading...",
      "word_count": 820,
      "page_depth": 1
    }
  ]
}
```

Performs `UPSERT` on `(vendor_website, page_url)` — safe to call multiple times.

---

## Deliverable 4 — n8n Workflow Updates

### Tier 1/2/3 workflows — two new nodes added after extraction

**Node A — Store Pages:**
POST to `N8N_ADMIN_BASE_URL/admin/ops/store-pages` with all extracted pages.

**Node B — Store Crawl Result:**
POST to `N8N_ADMIN_BASE_URL/admin/ops/store-crawl-result` with:
```json
{
  "vendor_website": "{{ $json.website }}",
  "column": "crawl_tier1_result",
  "payload": { "ok": true, "pipeline": "csp-crawl-tier1-direct", "crawled_at": "...", "pages_fetched": 1, "word_count": 4200, "fields": { "name": "Gainsight", ... } }
}
```

**Tier 3 — make `max_pages` configurable:**
Input field `max_pages` (default: 100, max: 300). Ops page passes this per-run.

### Datagma workflow — replace enrich-write node

Remove the existing "Enrich Write" node (which calls `/admin/enrich-write`). Replace with "Store Crawl Result" node calling `/admin/ops/store-crawl-result` with `column: "crawl_datagma_result"`.

### G2 workflow — same change

Replace existing enrich-write node with store-crawl-result node targeting `crawl_g2_result`.

---

## Deliverable 5 — Python Service Entry Points

All three services are **importable Python modules** called from admin API subprocess scripts. Entry point is always a single function.

### `services/ops/ops_logger.py`

```python
class OpsLogger:
    def __init__(self, milestone: str = "M76", log_path: str | None = None):
        """Log to existing pipeline log file + stdout (captured by subprocess runner)."""
    
    def step_start(self, action: str, message: str) -> None:
        """Emit entry with success=None (in progress)."""
    
    def step_progress(self, action: str, message: str) -> None:
        """Emit entry with success=None — shown as live update in log panel."""
    
    def step_done(self, action: str, message: str) -> None:
        """Emit entry with success=True."""
    
    def step_error(self, action: str, message: str) -> None:
        """Emit entry with success=False."""
```

Log entry format matches existing `/admin/pipeline-log` schema:
```python
{"timestamp": "ISO8601", "phase": "enrichment", "milestone": "M76", "action": action, "message": message, "success": True|False|None}
```

### `services/enrichment/llm_extractor_ollama.py`

```python
def run_llm_extraction(
    vendor_website: str,
    *,
    ollama_base_url: str = "http://localhost:11434",
    llm_model: str = "mistral:latest",
    embed_model: str = "nomic-embed-text",
    top_k_chunks: int = 5,
    supabase_client=None,
    logger: OpsLogger | None = None,
) -> dict:
    """
    Full RAG pipeline for one vendor.
    
    1. Fetch all vendor_pages.clean_text rows for vendor_website from Supabase.
    2. Chunk each page into 400-word segments with 50-word overlap.
    3. Embed each chunk with nomic-embed-text at ollama_base_url.
    4. Upsert chunks into vendor_page_embeddings.
    5. For each of 4 question groups: embed question → pgvector cosine search → top_k_chunks.
    6. Send chunks + prompt to Mistral → parse JSON response.
    7. Return crawl_*_result payload dict (does not write to Supabase — caller writes).
    
    Returns:
        {
            "ok": True,
            "pipeline": "csp-llm-extraction",
            "crawled_at": "ISO8601",
            "embeddings_created": 312,
            "llm_calls": 4,
            "fields": { "mission": "...", "icp_buyer": "...", ... }
        }
    
    Raises:
        ValueError: if vendor_pages has < 10 rows for vendor_website (Step 2 not run)
        ConnectionError: if ollama is not reachable at ollama_base_url
    """
```

### `services/enrichment/merge_module.py`

```python
def run_merge(
    vendor_website: str,
    *,
    supabase_client=None,
    logger: OpsLogger | None = None,
) -> dict:
    """
    Read all crawl_*_result columns for vendor_website.
    Apply per-field priority rules.
    Write winning values to main cs_vendors columns.
    Write source_field_map.
    
    Null-preservation rule (COALESCE pattern):
        For each field:
            1. Walk priority order for that field (e.g. datagma > g2 > llm)
            2. Take first non-null, non-empty value from crawl_*_result.fields
            3. Write to cs_vendors ONLY if winning value is non-null
            4. If no source has a value: leave existing cs_vendors value unchanged
            5. NEVER write null to cs_vendors — use COALESCE(new_value, existing_value)
        
        SQL pattern:
            UPDATE cs_vendors
            SET founded = COALESCE($new_founded, founded)
            WHERE website = $vendor_website
        
        Python pattern:
            updates = {}
            for field, sources in PRIORITY_RULES.items():
                for source in sources:
                    value = crawl_results[source].get("fields", {}).get(field)
                    if value is not None and value != "" and value != []:
                        updates[field] = value
                        break
                # if no source has value: field not added to updates dict
                # upsert with only non-null updates — existing value preserved
    
    Returns:
        {
            "ok": True,
            "fields_merged": 23,
            "source_field_map": {"name": "tier1", "mission": "llm", ...},
            "fields_unchanged": ["soc2", "compliance", ...]
        }
    """
```

---

## Deliverable 6 — Enhanced Logging

### `services/ops/ops_logger.py` log examples per step

**Step 2 — Tier 3 crawl:**
```
[enrichment][M76] tier3_crawl  Fetching gainsight.com via Apify WCC (max_pages=100)...
[enrichment][M76] tier3_crawl  Crawled 47/100 pages — 38,200 words extracted
[enrichment][M76] tier3_crawl  ✓ Writing 47 pages to vendor_pages...
[enrichment][M76] tier3_crawl  ✓ crawl_tier3_result written — name: Gainsight, word_count: 38200
```

**Step 5 — LLM extraction:**
```
[enrichment][M76] embed_chunks  Loading 47 pages from vendor_pages for gainsight.com
[enrichment][M76] embed_chunks  Chunking → 183 chunks (400w, 50w overlap)
[enrichment][M76] embed_chunks  Embedding chunk 1/183...
[enrichment][M76] embed_chunks  Embedding chunk 183/183 ✓ — writing to vendor_page_embeddings
[enrichment][M76] llm_extract   Group A (identity): pgvector search → 5 chunks → Mistral...
[enrichment][M76] llm_extract   ✓ mission: "The leading customer success platform..."
[enrichment][M76] llm_extract   ✓ icp_buyer: "VP of Customer Success at B2B SaaS (51-500 employees)"
[enrichment][M76] llm_extract   Group B (lifecycle): pgvector search → 5 chunks → Mistral...
[enrichment][M76] llm_extract   ✓ lifecycle_stages: ["onboarding", "adoption", "renewal", "expansion"]
[enrichment][M76] llm_extract   ✓ crawl_llm_result written — 7 fields extracted
```

**Step 6 — Merge:**
```
[enrichment][M76] merge  Reading all crawl_*_result columns for gainsight.com
[enrichment][M76] merge  founded: datagma="2013" | tier3=null → winner: datagma
[enrichment][M76] merge  mission: llm="The leading CS platform..." | tier3="..." → winner: llm
[enrichment][M76] merge  g2_rating: g2=4.6 → winner: g2 (only source)
[enrichment][M76] merge  soc2: all sources null → field unchanged (not written)
[enrichment][M76] merge  ✓ 23 fields written to cs_vendors
[enrichment][M76] merge  ✓ source_field_map written
```

---

## Deliverable 7 — Merge Module Priority Rules

| Field | Priority order |
|---|---|
| `name` | tier1 › tier2 › tier3 › datagma |
| `mission`, `usp` | llm › tier3 › tier2 |
| `icp`, `icp_buyer` | llm |
| `use_cases`, `lifecycle_stages` | llm |
| `products` | llm › tier3 |
| `founded` | datagma › g2 › llm |
| `hq_address`, `company_hq` | datagma › llm |
| `company_size` | datagma |
| `funding_stage`, `total_funding` | datagma |
| `ceo_name` | datagma › llm |
| `revenue` | datagma |
| `g2_rating`, `g2_review_count`, `g2_market_segment`, `g2_categories` | g2 |
| `pricing` | tier3 › tier2 › llm |
| `has_public_pricing_page` | tier3 › tier2 › tier1 |
| `free_trial` | tier3 › tier2 › llm |
| `soc2`, `compliance` | llm › tier3 |
| `contact_page_url`, `demo_url`, `about_url` | tier3 › tier2 › tier1 |
| `contact_emails`, `phone_numbers` | tier3 › tier2 |
| `integrations`, `integration_categories` | llm › tier3 |
| `customers`, `testimonials`, `case_studies` | llm › tier3 |

**Edge cases — all must be handled correctly:**
- All sources return null for a field → field not written, existing cs_vendors value preserved
- Source returns explicit `null` in JSON → treated same as missing (not written)
- Source returns empty string `""` or empty list `[]` → treated as no value (not written)
- Source returns `false` (boolean) → this IS a value and must be written (e.g. `has_public_pricing_page: false`)
- Two sources at same priority level → first in priority list wins (no tie-breaking)

---

## Deliverable 8 — Ops Page UI

Six step panels in `admin.js` / `admin.html`. Each panel registered as a pipeline spec — Run buttons call `POST /admin/pipelines/run` with the step's `pipeline_id`.

### Step 5 — Pre-run guard

Before enabling the Step 5 Run button, fetch:
```
GET /admin/ops/field-coverage?vendor_website=https://gainsight.com&check=vendor_pages_count
```
If `vendor_pages_count < 10`: disable Step 5 Run button, show inline warning:
> "Run Step 2 (Tier Crawl) first — vendor_pages has 0 rows for this vendor."

### Field coverage report (Step 6 output)

Colour-coded by source — **only CSS classes, no inline styles:**
- `.source-tier` — blue (tier1/2/3)
- `.source-datagma` — green
- `.source-g2` — orange
- `.source-llm` — purple
- `.source-null` — grey (field not populated by any source)

---

## Deliverable 9 — Verify Scripts (must be created before M76 completes)

### `scripts/check_ollama_models.py`
```python
# Asserts:
# 1. GET http://localhost:11434/api/tags returns 200
# 2. Response contains both "mistral:latest" and "nomic-embed-text"
# Exits with code 1 and descriptive message if either check fails
```

### `scripts/check_supabase_pgvector.py`
```python
# Asserts:
# 1. SELECT extname FROM pg_extension WHERE extname='vector' returns 1 row
# 2. vendor_pages table exists (SELECT 1 FROM vendor_pages LIMIT 1 succeeds)
# 3. vendor_page_embeddings table exists
# 4. Can INSERT and DELETE a test embedding row
# Exits with code 1 and descriptive message if any check fails
```

### `scripts/check_admin_endpoints.py`
```python
# For each /admin/ops/* endpoint:
# POST with minimal valid payload, assert 2xx response (or 400 with valid JSON error)
# Exits with code 1 listing any endpoints that fail
```

---

## Execution Order

Each step gates the next. Do not proceed until the prior step passes.

1. **Operator: Complete all four Human Approval Gates above**
2. Apply schema migration — `python3 scripts/apply_schema_migration.py`
3. Verify migration — `python3 scripts/check_supabase_pgvector.py`
4. Add `/admin/ops/store-crawl-result` endpoint to `admin_api.py`
5. Add `/admin/ops/store-pages` endpoint to `admin_api.py`
6. Register all ops pipeline specs in `pipeline_control.py`
7. Build `services/ops/ops_logger.py`
8. Update Tier 1/2/3 n8n workflows — add store-pages + store-crawl-result nodes + configurable max_pages
9. Update Datagma n8n workflow — replace enrich-write node with store-crawl-result node
10. Update G2 n8n workflow — replace enrich-write node with store-crawl-result node
11. Build `services/enrichment/llm_extractor_ollama.py`
12. Build `services/enrichment/merge_module.py`
13. Build three verify scripts (`check_ollama_models.py`, `check_supabase_pgvector.py`, `check_admin_endpoints.py`)
14. Build ops page UI — 6 step panels, Step 5 pre-run guard
15. Build unit tests — `tests/test_merge_module.py`, `tests/test_llm_extractor_ollama.py`, `tests/test_ops_endpoints.py`
16. Run verify suite — all six verify commands must pass
17. **Single-vendor proof: Gainsight, all 6 steps, write proof artifact**

---

## Acceptance Criteria

- [ ] pgvector extension enabled — `SELECT * FROM pg_extension WHERE extname='vector'` returns 1 row
- [ ] Schema migration idempotent — `python3 scripts/apply_schema_migration.py` runs twice without error
- [ ] All seven JSONB columns exist on cs_vendors (verified by `check_supabase_pgvector.py`)
- [ ] `vendor_pages` table exists with `UNIQUE(vendor_website, page_url)`
- [ ] `vendor_page_embeddings` table exists with `UNIQUE(vendor_website, page_url, chunk_index)` and ivfflat index
- [ ] `/admin/ops/store-crawl-result` accepts `{vendor_website, column, payload}` and writes ONLY to the named `crawl_*_result` column — verified by inspecting cs_vendors before/after
- [ ] `/admin/ops/store-crawl-result` rejects unknown column names with 400
- [ ] Datagma workflow does NOT call `/admin/enrich-write` — verified by inspecting workflow nodes
- [ ] G2 workflow does NOT call `/admin/enrich-write` — verified by inspecting workflow nodes
- [ ] No crawl step's result appears in another step's `crawl_*_result` column
- [ ] Tier 3 `max_pages` configurable from ops page (default 100, max 300)
- [ ] All eight ops endpoints registered as pipeline_control specs — appear in pipelines list in admin page
- [ ] `OpsLogger.step_progress()` entries appear in `/admin/pipeline-log` within 3 seconds of emission
- [ ] `run_llm_extraction()` raises `ValueError` when `vendor_pages` has < 10 rows for vendor
- [ ] `run_llm_extraction()` raises `ConnectionError` when Ollama unreachable
- [ ] `run_merge()` never writes null to any cs_vendors column — verified with a vendor that has some null source results
- [ ] `run_merge()` leaves existing cs_vendors field unchanged when all sources return null — verified by checking value before and after merge with all-null sources
- [ ] `run_merge()` correctly writes boolean `false` (e.g. `has_public_pricing_page: false`) — not treated as empty
- [ ] Step 5 ops panel Run button disabled + warning shown when `vendor_pages` count < 10 for selected vendor
- [ ] Field coverage report colour-coded by source using CSS classes (not inline styles)
- [ ] All timestamps in ops page displayed in NZST via `formatNzDateTime()`
- [ ] `scripts/check_ollama_models.py` exits 0 when both models installed, exits 1 with message when missing
- [ ] `scripts/check_supabase_pgvector.py` exits 0 when pgvector enabled and tables exist, exits 1 otherwise
- [ ] `scripts/check_admin_endpoints.py` exits 0 when all ops endpoints respond 2xx, exits 1 with failing endpoints listed
- [ ] Proof artifact written to `runs/proofs/M76_ops_enrichment_workbench.json` with all required keys
- [ ] Gainsight Step 2 proof: `vendor_pages` has >= 50 rows for `https://gainsight.com`
- [ ] Gainsight Step 5 proof: `vendor_page_embeddings` has >= 100 rows, `crawl_llm_result.fields` has >= 5 non-null fields
- [ ] Gainsight Step 6 proof: `source_field_map` written, >= 10 fields in main cs_vendors updated
- [ ] LinkedIn enrichment absent from all code, workflows, and UI

## Proof Artifact Schema

```json
{
  "milestone_id": "M76",
  "status": "pass",
  "completed_at": "2026-04-02T10:30:00+00:00",
  "vendor_tested": "Gainsight",
  "step_configs": {
    "discovery": { "pages_per_query": 20 },
    "tier_crawl": { "max_pages": 100, "tier_used": "tier3_wcc" },
    "ollama": { "model": "mistral:latest", "embedding_model": "nomic-embed-text", "top_k_chunks": 5 }
  },
  "step_results": {
    "step_1": { "status": "complete", "candidates_found": 0, "note": "Gainsight already in system — discovery step validated separately" },
    "step_2": { "status": "complete", "tier_used": "tier3_wcc", "pages_fetched": 87, "word_count": 42000, "vendor_pages_rows": 87 },
    "step_3": { "status": "complete", "fields_populated": ["founded", "hq_address", "company_size", "funding_stage", "ceo_name"] },
    "step_4": { "status": "complete", "g2_rating": 4.6, "g2_review_count": 1072 },
    "step_5": { "status": "complete", "embeddings_created": 312, "llm_calls": 4, "fields_extracted": 7 },
    "step_6": { "status": "complete", "fields_merged": 23, "fields_unchanged": ["soc2", "compliance"] }
  },
  "field_coverage_sample": [
    { "field": "name",       "value": "Gainsight",                   "source": "tier1"   },
    { "field": "mission",    "value": "The leading CS platform...",   "source": "llm"     },
    { "field": "founded",    "value": "2013",                         "source": "datagma" },
    { "field": "g2_rating",  "value": 4.6,                           "source": "g2"      },
    { "field": "icp_buyer",  "value": "VP of Customer Success...",   "source": "llm"     },
    { "field": "soc2",       "value": null,                          "source": null      }
  ],
  "source_field_map": {
    "name": "tier1", "mission": "llm", "founded": "datagma", "g2_rating": "g2"
  },
  "acceptance_criteria_met": []
}
```

## Not In Scope

- LinkedIn enrichment (excluded by design — M78 candidate)
- Automated scheduling or cron runs
- Bulk batch runs across all vendors (single-vendor proof first)
- Scrapfly (revisit if Apify tier hit rates prove insufficient)
- BigQuery (Supabase pgvector covers requirement at zero extra cost)
- Modifying `/admin/enrich-write` (preserved unchanged for backward compatibility)
