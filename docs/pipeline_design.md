# Pipeline Design

## Overview

The CSP Directory pipeline has three distinct phases:

1. **URL Acquisition** — build a deduplicated seed list of vendor URLs from multiple sources
2. **Enrichment** — populate the vendor schema fields for each URL using the best available tool per field
3. **Persistence** — Supabase is the source of truth; all updates write there

These phases are independent. URL acquisition runs on a discovery cadence. Enrichment runs against the seed list. The schema defines what enrichment needs to produce.

---

## Phase 1 — URL Acquisition

### Goal
Produce a deduplicated list of vendor URLs with a minimum viable identity record (name, website, source).

### Current sources
- **Apify Google Search** — queries like "AI customer success platform" return search result URLs and snippets

### Planned sources (future versions)
- **G2** — structured vendor listings with category tags, reviews, and ratings
- **LinkedIn** — company pages for CS tooling vendors
- **ProductHunt** — new entrant discovery
- **Direct submission** — operator-curated additions

### Source registry
Each source is declared in a governed source registry with:
- `source_id` — unique identifier
- `reliability_tier` — primary (vendor's own site), aggregator (G2, review sites), inferred (LLM, search snippets)
- `fields_provided` — which schema fields this source can populate
- `dedup_key` — how to match against existing records (normalised domain)

### Deduplication
- Normalise all URLs to root domain before comparison
- Strip tracking params, www prefix variations, trailing slashes
- Discard non-vendor results: blog posts, Reddit threads, review articles, "403 Forbidden" pages
- A vendor quality filter must run before any URL enters the seed list

---

## Phase 2 — Enrichment

### Goal
For each vendor URL, populate all schema fields defined in `docs/vendor_schema.md`.

### Enrichment strategies

Different fields require different tools. The enrichment layer is strategy-based — each field has a preferred source and a fallback.

| Field group | Preferred strategy | Fallback |
|---|---|---|
| Basic identity (name, website, mission, USP) | JS-capable web scraper | Plain HTTP scrape |
| Pricing model | JS-capable web scraper (pricing page) | LLM direct query |
| Products / features | JS-capable web scraper | LLM direct query |
| Leadership / team | LinkedIn scrape or web scraper (team page) | LLM direct query |
| Integrations | Web scraper (integrations page) | LLM direct query |
| CS lifecycle stage fit | LLM classification | Rule-based keyword match |
| ICP / target buyer | LLM classification from scraped content | — |
| Customers / case studies | Web scraper | LLM direct query |
| Company HQ / founded | Web scraper (about page) | External company DB |
| Use cases | LLM classification from scraped content | Web scraper |

### Enrichment tools (current and planned)

**Web scraping — JS-capable (required for modern SaaS sites)**
- Apify Web Scraper or Apify Website Content Crawler
- Required for sites like Gainsight, Totango, Salesforce that block plain HTTP

**Web scraping — plain HTTP**
- Python `requests` + BeautifulSoup
- Works only for static or server-rendered pages
- Should be a fallback only, not the primary path

**LLM direct query**
- Ask a language model a targeted question about the vendor
- Best for classification fields (lifecycle stage, ICP, use cases)
- Cheap models (GPT-4o-mini, Claude Haiku) are sufficient for most classification tasks
- Requires confidence scoring — LLM-inferred data is lower confidence than scraped data
- Future: AF LLM selection capability will govern which model is used per task

**Structured data sources (future)**
- G2 API — ratings, category tags, integration lists
- Crunchbase / PitchBook — founding date, HQ, funding, leadership
- LinkedIn API — leadership, company size, HQ

### Confidence scoring

When multiple sources provide a value for the same field, a confidence hierarchy determines which wins:

1. Primary source scrape (vendor's own website) — highest
2. Structured aggregator (G2, Crunchbase) — high
3. LLM extraction from scraped content — medium
4. LLM direct query (no scraped content) — low
5. Search snippet (Google result text) — lowest

Lower-confidence values are stored but flagged. Higher-confidence values overwrite lower-confidence ones on re-enrichment.

### Re-enrichment policy
- Full re-enrichment runs weekly (scheduled pipeline run)
- Targeted re-enrichment runs when a field is flagged as stale or low-confidence
- New vendors from URL acquisition trigger enrichment on next scheduled run

---

## Phase 3 — Persistence

### Supabase as source of truth
- All enriched vendor data writes to the `cs_vendors` table
- The schema in `docs/vendor_schema.md` is the canonical field definition
- `supabase/core_persistence_schema.sql` is the live schema migration file — must stay in sync with the schema doc

### Write rules
- Upsert by normalised domain (not vendor name — names change)
- Only overwrite a field if the new value has equal or higher confidence than the existing value
- `last_updated` always reflects the most recent enrichment run
- `confidence` field on the record reflects the lowest-confidence populated field

### Export layer
- `outputs/directory_dataset.json` — public-facing export, includes only `include_in_directory = true` vendors
- Rebuilt on each pipeline run from Supabase
- Frontend reads from this export, not directly from Supabase

---

## What Needs to Change (Rearchitect Scope)

The current implementation has the following gaps against this design:

1. **No vendor quality filter at discovery** — blog posts, Reddit threads, and "403 Forbidden" pages enter the seed list
2. **Enrichment uses plain HTTP** — `vendor_fetcher.py` and `site_explorer.py` use `requests.get()`, which fails on JS-rendered SaaS sites. Apify Web Scraper must replace this as the primary path
3. **No field-to-source mapping** — enrichment runs the same process on every vendor regardless of what's already populated or which tool is best for each field
4. **LLM results not writing to Supabase** — the LLM extractor runs but structured fields (products, leadership, integrations, use_cases, lifecycle_stages) are empty in the database, indicating a persistence gap in `upsert_vendor_result`
5. **No source registry** — sources are hardcoded rather than governed
6. **Schema drift** — `core_persistence_schema.sql` references columns that don't exist in the live database (e.g. `ceo_name`)

These gaps are the basis for the fix milestones defined in `milestone_registry.json`.
