# Architecture

The CSP Directory is a three-phase pipeline. The detailed pipeline design is in `docs/pipeline_design.md`. The vendor field schema is in `docs/vendor_schema.md`.

## Three Phases

**Phase 1 — URL Acquisition**
Build a deduplicated seed list of vendor URLs from governed sources. Current source: Apify Google Search. Planned: G2, LinkedIn, ProductHunt, direct submission. A quality filter must discard non-vendor results (blog posts, review articles, error pages) before any URL enters the seed list.

**Phase 2 — Enrichment**
For each vendor URL, populate the fields defined in `docs/vendor_schema.md` using the best available tool per field. The primary enrichment path is a JS-capable web scraper (Apify Web Scraper or Website Content Crawler). LLM classification is used for fields that require interpretation (lifecycle stage, ICP, use cases, directory fit). Plain HTTP scraping is a fallback only.

**Phase 3 — Persistence**
Supabase is the source of truth. All enrichment writes to `cs_vendors` via upsert on normalised domain. The export layer builds `outputs/directory_dataset.json` from Supabase for the public frontend.

## Phase-to-runtime map

Runtime source of truth is `services/pipeline/orchestrator.py` in `run_mvp_pipeline(...)`, which calls each phase in order:

1. Phase 1 entrypoint: `services/pipeline/discovery_runner.py` -> `run_discovery_phase(...)`
2. Phase 2 entrypoint: `services/pipeline/enrichment_runner.py` -> `run_enrichment_phase(...)`
3. Phase 3 persistence/export in orchestrator helpers:
   - `_persist_run_record(...)`
   - `_persist_candidate_records(...)`
   - `_export_directory_dataset(...)`
   - `_export_vendor_review_dataset(...)`
   - `_persist_search_visibility_queries(...)`
   - `_export_search_visibility_artifacts(...)`

Operational trigger paths:

- Ad-hoc/manual: `scripts/run_pipeline.py` (invokes orchestrator)
- Admin control panel: `POST /admin/pipelines/run` in `services/admin/admin_api.py`, delegated to `services/admin/pipeline_control.py`
- Scheduled run: GitHub Actions weekly schedule (repository workflow), invoking the same pipeline entry path

## Key Design Rules

- The schema defines what enrichment needs to produce — see `docs/vendor_schema.md`
- Enrichment is field-targeted and source-governed — each field has a preferred source and a confidence tier
- Higher-confidence values overwrite lower-confidence ones on re-enrichment
- The frontend reads from exported JSON, not directly from Supabase
- Python owns orchestration; Apify owns JS-capable crawling; LLMs own classification

## Known Gaps (Current Implementation)

The current codebase does not match this design. See `docs/pipeline_design.md` — "What Needs to Change" — for the full gap list. Key issues: enrichment uses plain HTTP instead of Apify web scraper; LLM extraction results are not writing structured fields to Supabase; no vendor quality filter at discovery.

---

# Module Boundaries

End-to-end pipeline stages:

Vendor Discovery  
Homepage Fetch  
Website Exploration  
Page Text Extraction  
Vendor Intelligence Extraction  
Vendor Profile Builder  
Dataset Export  

The active crawl model is split into two phases:

Phase 1 discovery crawl  
Phase 2 vendor enrichment crawl  

services/discovery/

Instructs Apify to crawl discovery sources and returns normalised vendor candidates to the orchestrator.

Phase 1 returns candidate-domain records which are deduplicated, status-tracked, and queued for enrichment before any homepage fetching begins.

Contains `apify_sources.py` with four functions:

fetch_producthunt()  
fetch_google_search(queries)  
fetch_g2_categories(urls)  
fetch_rag_browser(query)

Each function:

1. Calls the Apify API
2. Waits for the actor run to complete
3. Pulls the output dataset
4. Normalises the results into candidate objects

Discovery contains no business logic.

Candidate normalisation is handled via `normalise_candidates.py` to ensure consistent structure across discovery sources.

Normalised candidate schema:

company_name  
website  
raw_description  
source  

Discovery candidate record schema:

candidate_domain  
candidate_title  
candidate_description  
source_query  
source_engine  
source_rank  
discovered_at  
candidate_status  
status  
discovery_notes  
drop_reason  

---

Candidate status values remain simple at the persisted candidate layer:

new  
filtered_out  
queued_for_enrichment  
enriched  
dropped  
failed  

Phase 2 enrichment uses more explicit result statuses internally:

enriched  
dropped_low_confidence  
dropped_non_cs_relevant  
failed_fetch  
failed_enrichment

Current persistence and fallback note:

The repo can surface local fallback artifacts for candidates, vendors, and run history when persistence is unavailable or schema-misaligned. That fallback keeps operator visibility alive, but it does not replace the requirement for stable Supabase schema alignment.

---

# Data Serving Model

The architecture uses a layered data-serving model rather than a single storage/serving mechanism.

Canonical persistence:

- The pipeline extracts structured vendor intelligence from vendor websites
- The structured vendor record is persisted to Supabase
- Supabase remains the canonical system of record

Derived serving artifacts:

- Public directory pages use exported JSON artifacts derived from the canonical dataset
- The primary public serving artifact is `outputs/directory_dataset.json`
- Review-oriented derived artifacts include `outputs/vendor_review_dataset.json`, `outputs/vendor_review.html`, `outputs/search_visibility_report.json`, and `outputs/search_visibility_report.html`

Review/export responsibilities remain split:
- vendor website enrichment populates the canonical vendor record in Supabase
- buyer-intent query generation persists buyer-role prompts in `buyer_search_queries`
- role-based search ranking observation persists ranked result rows in `buyer_search_results` and feeds the visibility report surfaces

Internal surfaces:

- Internal/admin pages use a thin admin/API layer
- That layer should read canonical persisted data first
- It may fall back to local artifacts when persistence is unavailable or schema-drifted

Explicit v1 rule:

- Public browser pages do not hit Supabase directly
- If a dynamic public serving model is introduced later, it should go through a backend/API layer rather than direct browser-to-Supabase access

---

services/enrichment/

Fetches vendor homepage content and explores high-signal vendor pages using Python requests.

Responsibilities:

- Fetch homepage HTML
- Explore the configured set of high-signal pages per vendor
- Skip unreachable pages safely
- Return structured page payloads ready for extraction

Apify is not used for enrichment.

site_explorer.py

Discovers and fetches a bounded set of high-signal vendor pages such as pricing, product, case studies, security, about, and integrations.
Exploration stays on the vendor domain, uses the limits and page patterns from `config/pipeline_config.json`, skips obvious junk pages, and returns a structured page bundle with named pages plus `extra_pages` when useful.

---

services/extraction/

Implements the deterministic extraction layer plus the active LLM-default enrichment layer.

page_text_extractor.py

Extracts clean visible text from HTML while removing scripts, navigation blocks, footer noise, and cookie-banner style chrome. Supports deterministic truncation when callers need bounded text.

vendor_intel.py

Level 1 deterministic extraction using rule-based keyword detection across homepage and explored pages. Extracts structured vendor signals such as:

mission  
usp  
icp  
use_cases  
pricing  
free_trial  
soc2  
founded  
case_studies  
customers  
value_statements  
lifecycle_stages  
confidence  

This extractor guarantees structured output even if LLM extraction fails.

vendor_profile_builder.py

Merges discovery metadata, explored pages, and extracted intelligence into a single `VendorIntelligence` record ready for export.
This layer also applies deterministic directory relevance scoring:

directory_fit = high | medium | low  
directory_category = cs_core | cs_adjacent | support_only | generic_cx | infra  
include_in_directory = bool  

llm_extractor.py

Level 2 semantic extraction using the OpenAI Responses API.

Runtime settings such as enable flag, default model, request timeout, and payload bounds are loaded from `config/pipeline_config.json`.
The intended operating mode is that LLM extraction runs on every normal pipeline execution when configuration is valid. Deterministic extraction remains the resilience fallback when the LLM layer is unavailable.

Python sends vendor website text to the OpenAI API and receives structured JSON containing richer commercial intelligence including:

mission  
unique selling proposition  
icp  
expanded use cases  
pricing signals  
free trial signals  
SOC2 mentions  
founded information  
case studies  
customers  
value statements  
confidence score  

merge_results.py

Combines the deterministic extraction results and the LLM extraction results into a single `VendorIntelligence` object.

If the LLM call fails, deterministic results are still used and the fallback must remain visible at the operator/run-summary layer.
LLM output is used to review and enrich the same core vendor fields as deterministic extraction, but vendor identity, lifecycle stages, and evidence URLs remain deterministic and system-owned.
The merge keeps deterministic non-empty values unless the LLM clearly improves them, and it never replaces stronger deterministic signals with empty or weaker values.

Vendors where:

is_cs_relevant = false  
confidence = low  

are dropped before persistence.

---

services/classification/

Contains `lifecycle_classifier.py`.

Lifecycle classification is deterministic and handled by Python, not the LLM.

Extracted signals are mapped to the SuccessByCS 8-stage lifecycle framework:

Sign  
Onboard  
Activate  
Adopt  
Support  
Expand  
Renew  
Advocate  

Multiple lifecycle stages may be assigned to a vendor.

Example signal mappings:

health score → Adopt  
support automation → Support  
churn prediction → Renew  
NPS → Advocate  
upsell detection → Expand  
onboarding automation → Onboard

---

# Configuration Reality

The configuration story is currently mixed and should be treated carefully during autonomous development.

- `config/pipeline_config.json` is the active runtime source of truth for discovery, enrichment, directory relevance, LLM behavior, and export behavior
- `config/scheduler.toml` is the active runtime source of truth for scheduling
- split TOML config files under `config/` exist, but documentation and runtime are not yet fully consolidated around them

Milestone work must keep docs honest about this state rather than assuming config consolidation is already complete.

---

services/persistence/

Contains `supabase_client.py` and `run_store.py`.

Provides:

is_known_vendor(website)  
Checks whether the vendor domain already exists in Supabase.

upsert_vendor(vendor)

Writes vendor intelligence into the `cs_vendors` table using:

ON CONFLICT (website) DO UPDATE

Domain normalisation ensures the following map to the same record:

gainsight.com  
www.gainsight.com  
https://gainsight.com  

`run_store.py` persists pipeline run records with explicit run status and error summary fields, and the local `outputs/pipeline_runs.json` file remains a fallback artifact for local/admin visibility.

---

services/discovery/discovery_store.py

Persists Phase 1 discovery candidate records to Supabase so candidates and their statuses can be inspected later and rerun without treating them as enriched vendor profiles.

---

services/export/

Handles human-facing outputs.

google_sheets.py

Publishes review-friendly Google Sheets tabs for operators.

Worksheet names and export settings are loaded from `config/pipeline_config.json`.

The main review tabs are:

Runs  
Candidates  
Vendors  

directory_dataset.py

Builds the deterministic public directory export from Supabase and writes:

`outputs/directory_dataset.json`

Only vendors with `include_in_directory = true` are included.

vendor_review_dataset.py

Builds a slim vendor review dataset from Supabase and current-run fallbacks and writes:

`outputs/vendor_review_dataset.json`  
`outputs/vendor_review.html`

This keeps the public directory dataset separate from the operator-facing review output.

---

services/admin/

admin_api.py

Provides a thin read-only WSGI app exposing:

/admin/candidates  
/admin/vendors  
/admin/runs  

This is intended to support a later internal admin UI without requiring a full backend redesign first.

services/admin/admin_actions.py

Provides lightweight POST actions for:

include vendor  
exclude vendor  
rerun enrichment  

These actions are intentionally thin and operate on the existing persistence and enrichment flow.

slack.py

Builds and posts the weekly Slack digest summarising vendors discovered in the past week grouped by lifecycle stage.

---

services/pipeline/

orchestrator.py

Runs the end-to-end flow:

Phase 1 discovery crawl  
candidate normalisation  
domain deduplication  
queue accepted domains for enrichment  
Phase 2 vendor enrichment crawl  
homepage enrichment  
website exploration  
page text extraction  
deterministic extraction  
LLM extraction  
merge results  
vendor profile building  
lifecycle classification  
drop low-confidence or non-relevant vendors  
persistence  
Google Sheets export

scheduler.py

APScheduler entry point.

Runs:

run_discovery() on the schedule configured in `config/scheduler.toml`  
run_digest() on the schedule configured in `config/scheduler.toml`

---

services/utils/

retry.py

Provides retry logic with exponential backoff for external API calls.

Used by:

Apify client  
OpenAI client  
Supabase client  
Google Sheets client  
Slack client

Retry policy:

3 retries  
exponential backoff  
timeout handling

domain.py

Handles domain normalisation to ensure consistent vendor deduplication.

Example normalisation:

https://www.gainsight.com  
http://gainsight.com  
gainsight.com

→ gainsight.com

---

scripts/run_pipeline.py

CLI wrapper for running the pipeline manually.

Examples:

python scripts/run_pipeline.py "ai customer success platform"  
python -m services.pipeline.scheduler --run-now discovery  
python -m services.pipeline.scheduler --run-now digest

---

# Current Pipeline Flow

1. Python scheduler fires using the configured discovery schedule and calls `orchestrator.run_discovery()`.

2. The orchestrator calls each discovery source in `services/discovery/apify_sources.py`, which instructs Apify to crawl and returns candidate vendors.

3. Candidate records are normalised and deduplicated by domain within the batch.

4. Each candidate website is checked against Supabase using `is_known_vendor(website)`. Known vendors are marked as already enriched and skipped from the Phase 2 queue.

5. Each queued vendor domain enters Phase 2 and the homepage is fetched via `fetch_vendor_homepage()`.

6. Site exploration discovers and fetches a bounded set of high-signal pages for each vendor.

7. Clean visible text is extracted from homepage and explored pages into a small page bundle for downstream extraction.

8. Deterministic extraction runs via `vendor_intel.py`.

9. LLM enrichment runs by default when valid runtime configuration is present.

10. Deterministic and LLM signals are merged into one `VendorIntelligence` profile.

11. Directory relevance scoring assigns fit, category, and include/exclude decisions.

12. Discovery candidate records are persisted for operations visibility and reruns.

13. Lifecycle stages remain deterministic and are preserved in the enriched profile.

14. Each vendor object is persisted via `upsert_vendor()`.

15. Each vendor row is appended to Google Sheets.

16. The public directory dataset is exported to `outputs/directory_dataset.json`, using Supabase as the primary source and current-run included profiles as a fallback when persistence is unavailable.

17. `run_digest()` queries vendors using the configured lookback window and posts a Slack digest grouped by lifecycle stage.

18. Vendors included in the digest have `is_new = FALSE`.

19. The admin dashboard reads `/admin/candidates`, `/admin/vendors`, `/admin/runs`, and `/admin/pipelines`, and POSTs lightweight quality-control actions back to the same admin service.

---

# Apify Integration Notes

Apify is used exclusively as a crawling utility.

The Google Search actor, query list, crawl depth, result-filter heuristics, enrichment page rules, LLM runtime knobs, directory relevance hints, and Google Sheets export columns are loaded from `config/pipeline_config.json`.

The scheduler still reads cron timing from `config/scheduler.toml`, but scheduled discovery queries now resolve from `config/pipeline_config.json` so scheduled and manual runs share the same discovery query surface.

Apify does not:

control pipeline execution  
perform classification  
write to databases  
call LLM APIs  

Python instructs Apify which actors to run. Apify returns crawl results. Python immediately resumes control.

If Apify is replaced with another crawling provider, only `services/discovery/apify_sources.py` changes.

The four Apify actors currently used:

apify/product-hunt-scraper — ProductHunt AI launches (daily)

apify/google-search-scraper — targeted Customer Success AI search queries (daily)

apify/website-content-crawler — G2 category pages (weekly)

apify/rag-web-browser — newsletter and blog discovery (daily)

---

# Scheduling Notes

The Python process runs continuously as a persistent service deployed on Railway or Render.

APScheduler manages the schedule internally.

No GitHub Actions, no external cron, and no n8n are required.

The process must remain alive between scheduled runs.

---

# Environment Variables

All credentials are read from environment variables.

SUPABASE_URL  
SUPABASE_KEY  
OPENAI_API_KEY  
APIFY_API_TOKEN  
GOOGLE_SHEETS_ID  
GOOGLE_SHEETS_CREDENTIALS  
SLACK_BOT_TOKEN  
SLACK_CHANNEL_ID  

---

# Observability

The pipeline logs the following operational metrics:

vendors discovered  
vendors skipped as duplicates  
vendors enriched  
vendors extracted  
vendors dropped  
vendors persisted  
rows exported to Sheets  
weekly digest posted  

Structured logging enables debugging and pipeline monitoring.

---

# Tests

All services have corresponding test files in `tests/`.

External services are mocked:

Apify  
Supabase  
Google Sheets  
Slack

No live API calls occur during tests.

Run tests:

python3 -m venv .venv  
.venv/bin/pip install -r requirements.txt  
.venv/bin/python -m pytest

Test files:

tests/test_discovery.py  
tests/test_vendor_fetcher.py  
tests/test_site_explorer.py  
tests/test_vendor_intel_extraction.py  
tests/test_vendor_profile_builder.py  
tests/test_supabase_client.py  
tests/test_google_sheets.py  
tests/test_mvp_pipeline.py

---

# MVP Notes

Vendor is the core entity, not individual pages.

Apify is used for discovery crawling only.

Homepage enrichment uses Python requests.

Extraction is currently deterministic-first:

Level 1 deterministic rules  
Level 2 OpenAI semantic extraction with deterministic, operator-visible fallback

Lifecycle classification is deterministic and handled by Python.

Supabase is the canonical datastore.

Google Sheets is a human-readable export layer.

Repo-level config files currently used by the running system:

`config/pipeline_config.json`  
`config/scheduler.toml`  

Container entrypoint:

`Dockerfile` runs `python -m services.admin.admin_api --host 0.0.0.0 --port 8000`

This makes the admin API and static admin dashboard available from the same container port.
