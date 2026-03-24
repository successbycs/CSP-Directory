# Product Design (v2.2)

This document describes the architecture for the AI Customer Success Vendor Intelligence system.

The system discovers companies offering AI-enabled products that support the Customer Success lifecycle, enriches vendor websites to collect key information, extracts structured commercial intelligence, classifies vendors against the SuccessByCS 8-stage lifecycle framework, and produces a structured dataset in Supabase and Google Sheets.

The core unit of analysis is the vendor/company, not individual web pages.

The target architecture introduces a dual-extraction model:
Level 1 deterministic extraction and Level 2 LLM-assisted extraction.

Current implementation status:
the codebase at this checkpoint runs Level 1 deterministic extraction as the baseline
and Level 2 LLM-assisted extraction as the default enrichment path for normal runs.
If Level 2 is unavailable, the MVP pipeline falls back to Level 1 without failing the run, and that fallback must be visible to operators.

Current repo snapshot:
- discovery, enrichment, deterministic extraction, LLM-default enrichment, directory scoring, and export artifacts are implemented
- public directory pages and admin pages are implemented as static pages backed by exported JSON and admin API endpoints
- run tracking and scheduler entrypoints exist
- documentation, config consolidation, schema hardening, and launch-readiness verification are still active milestones

---

# Primary Deliverable

The system produces a continuously updated dataset of AI-enabled Customer Success vendors.

The canonical dataset lives in Supabase.

Google Sheets is an ops-facing review layer used to inspect runs, discovery candidates, and enriched vendors in a readable format.

The public directory is driven by a deterministic static export built from Supabase:

`outputs/directory_dataset.json`

The pipeline also produces a slim operator review dataset and a self-contained visual report:

`outputs/vendor_review_dataset.json`  
`outputs/vendor_review.html`

---

# Source Of Truth And Serving Model

The system must be explicit about how website-derived vendor data is stored and served.

Canonical model:

- Vendor website content is fetched and analyzed by the Python pipeline
- Python converts that content into structured vendor intelligence records
- Supabase is the canonical system of record for vendor data
- Public directory pages are served from exported JSON artifacts derived from the canonical dataset
- Internal admin and review surfaces may read Supabase through a thin API layer and may fall back to local artifacts when persistence is unavailable

This means the system is not choosing between JSON files and Supabase.
It uses both, with different responsibilities:

- Supabase = source of truth
- exported JSON files = public serving layer and review artifacts
- admin API = internal operator layer

Public v1 serving rules:

- The public website does not query Supabase directly from the browser
- The public listing and vendor detail pages use exported JSON artifacts, primarily `outputs/directory_dataset.json`
- Review artifacts such as `outputs/vendor_review_dataset.json` and `outputs/vendor_review.html` are derived outputs, not the canonical record

Fallback rules:

- Fallback JSON artifacts are allowed to keep internal/operator views usable when persistence is unavailable or schema-drifted
- Fallback artifacts do not replace the requirement for healthy canonical persistence in Supabase

Each vendor row contains fields such as:

vendor_name  
website  
source  
mission  
usp  
icp  
icp_buyer  
use_cases  
lifecycle_stages  
pricing  
free_trial  
soc2  
founded  
products  
leadership  
company_hq  
contact_email  
contact_page_url  
demo_url  
help_center_url  
support_url  
about_url  
team_url  
integration_categories  
integrations  
support_signals  
case_studies  
case_study_details  
customers  
value_statements  
confidence  
evidence_urls  
directory_fit  
directory_category  
include_in_directory  

The proof model is intentionally split:

- `value_statements` are vendor-level marketing or positioning claims
- `case_study_details` store structured customer-story outcomes such as client, use case, value realized, optional metric, and source URL

Canonical formatting rules also apply before persistence:

- websites and page URLs are normalized to a canonical URL format
- contact emails are validated and lowercased before write-time storage

---

# The SuccessByCS 8-Stage Lifecycle Framework

Every vendor in the system is classified against this framework.

Stage names are canonical and must not be altered.

A vendor may belong to multiple stages.

Sign  
Conversational intelligence, AI notetakers, meeting summaries, sales-to-CS handoff tools

Onboard  
Implementation portals, PSA tools, onboarding automation, time-to-value acceleration

Activate  
In-app guidance, user education, product walkthroughs, adoption nudges

Adopt  
Health scoring, usage analytics, sentiment analysis, signal-to-playbook automation

Support  
Support automation, ticket triage, agent assist, help desk copilots, knowledge base tooling

Expand  
Upsell detection, cross-sell intelligence, expansion revenue tools, stakeholder mapping

Renew  
Churn prediction, renewal automation, risk alerts, forecasting

Advocate  
NPS, Voice of Customer programs, reference management, case study tools

Lifecycle stage classification is performed by Python, not the LLM.

---

# Architecture Overview

Python is the controller, scheduler, and decision-maker for the entire system.

Apify is used only as a crawling utility.

Apify fetches pages and returns raw content. It never touches the database, never calls an LLM, and never makes business decisions.

Python process (Railway / Render)

APScheduler  
owns daily and weekly scheduling

services/discovery  
calls Apify actors and returns normalised vendor candidates

services/enrichment  
fetches homepage content, explores vendor pages, and extracts visible text

services/extraction  
performs vendor intelligence extraction (Level 1 deterministic + Level 2 LLM)

services/classification  
maps extracted signals to lifecycle stages

services/persistence  
deduplication checks and upserts into Supabase

services/export  
writes rows to Google Sheets and sends Slack digest

services/pipeline  
orchestrator controlling the full pipeline

Current configuration status:

The repo is still in a transitional config state.

- `config/pipeline_config.json` is the active runtime source of truth for most pipeline behavior
- `config/scheduler.toml` is the active source of truth for scheduler timing
- additional split TOML files exist in `config/`, but config consolidation is not yet complete and they should not automatically be treated as the primary runtime source without checking the code

If Apify were replaced with another crawling provider tomorrow, only services/discovery/apify_sources.py would change.

---

# System Pipeline

The crawl model is now explicit:

Phase 1 = discovery crawl  
Phase 2 = vendor enrichment crawl  

Daily pipeline

Pipeline stages

Vendor Discovery  
Homepage Fetch  
Website Exploration  
Page Text Extraction  
Vendor Intelligence Extraction  
Vendor Profile Builder  
Dataset Export  

Python APScheduler fires using the configured discovery schedule in `config/scheduler.toml`  
↓  
Python orchestrator triggers discovery  
↓  
Python loads crawl/runtime settings from `config/pipeline_config.json` and calls Apify actors for discovery sources  
↓  
Apify returns candidate URLs and metadata  
↓  
Python normalises candidates into candidate-domain records and deduplicates by domain across all configured queries  
↓  
Python marks accepted domains as queued for enrichment and skips already-enriched domains  
↓  
Phase 2 enrichment proceeds only on queued domains  
↓  
Python fetches homepage text (3000-5000 characters)  
↓  
Python explores a bounded set of high-signal internal pages from `config/pipeline_config.json`  
↓  
Python extracts clean visible text from those pages  
↓  
Level 1 deterministic extraction runs  
↓  
Level 2 LLM extraction runs when configured in `config/pipeline_config.json`  
↓  
Python merges deterministic and LLM signals into one vendor profile record  
↓  
Python classifies lifecycle stages  
↓  
Python assigns directory relevance labels and include/exclude decisions  
↓  
Vendors marked non-relevant or low-confidence are dropped with explicit drop statuses  
↓  
Python upserts included vendor intelligence into Supabase  
↓  
Python persists pipeline run tracking and candidate status updates  
↓  
Python updates Google Sheets review tabs for runs, candidates, and enriched vendors  
↓  
Python exports `outputs/directory_dataset.json`
↓
Python exports `outputs/vendor_review_dataset.json` and `outputs/vendor_review.html`
↓
Python exports `outputs/search_visibility_report.json` and `outputs/search_visibility_report.html`

Current operational note:

When Supabase persistence is unavailable or schema-drifted, some operator surfaces can fall back to local JSON artifacts so the admin and review views remain usable. This is a resilience measure, not evidence that persistence is fully healthy.

---

# Definition Of Done

The project is only considered done for internal launch when all of the following are true:

- A real pipeline run completes successfully from the current repo state
- The pipeline persists the canonical vendor records to Supabase for the required paths
- `outputs/directory_dataset.json` is generated from the canonical dataset
- `outputs/vendor_review_dataset.json` and `outputs/vendor_review.html` are generated as vendor review artifacts, including structured case-study rows when available
- `outputs/search_visibility_report.json` and `outputs/search_visibility_report.html` are generated as buyer-role search visibility artifacts

The review path stays separated by responsibility:
- vendor website enrichment turns site evidence into normalized vendor intelligence
- buyer-intent query generation expands `icp_buyer` personas into Google and GEO prompts
- role-based search ranking observation stores ranked surfaced vendors per query so operators can compare visibility by role, query, channel, and vendor
- The public landing page and vendor detail page render from generated data
- The admin surface can inspect candidates, vendors, and runs
- Operator actions for include, exclude, and rerun are functional and logged
- Scheduler discovery and digest jobs are smoke-tested successfully
- Containerized and devcontainer-oriented execution paths are verified or explicitly deferred and tracked
- Documentation matches the real runtime behavior and configuration model
- Verification scripts and milestone checks pass
- No unresolved launch blocker remains hidden behind fallback behavior

Weekly digest

Python APScheduler fires using the configured digest schedule in `config/scheduler.toml`  
↓  
Python queries vendors added in last 7 days  
↓  
Python groups vendors by lifecycle stage  
↓  
Python posts summary to Slack  
↓  
Python marks vendors as no longer new

---

# Scheduling

Python owns its own scheduling.

The pipeline is triggered by the Python service itself, not by GitHub Actions.

No external cron or GitHub Actions are part of the target design.

APScheduler is used.

The active scheduler times, digest lookback window, and Slack timeout are repo-configured in:

`config/scheduler.toml`

Example:

from apscheduler.schedulers.blocking import BlockingScheduler

scheduler = BlockingScheduler()

scheduler.add_job(run_daily_pipeline, 'cron', hour=7, minute=0)
scheduler.add_job(run_weekly_digest, 'cron', day_of_week='mon', hour=8)

scheduler.start()

The Python service must run continuously.  
Railway or Render must auto-restart the service if it crashes.

Manual runs can be triggered with:

python -m services.pipeline.scheduler --run-now discovery  
python -m services.pipeline.scheduler --run-now digest  

---

# Vendor Discovery

Goal

Identify companies building AI tools that support Customer Success teams.

Apify is used as the crawling utility.

Python instructs Apify which actors to run and retrieves the dataset results.

Discovery sources include:

ProductHunt  
Google search queries  
G2 category pages  
RAG web browser discovery

Each source function returns a normalised candidate structure:

company_name  
website  
raw_description  
discovery_source  

Python deduplicates candidates by domain before processing.

Google Search discovery and pipeline runtime settings are operator-configured in:

`config/pipeline_config.json`

The pipeline config controls:

queries  
Apify actor ID  
pages per query  
results per page  
max candidate domains per run  
Google result filtering and denylist heuristics  
max internal pages per vendor  
page matching and priority  
directory relevance thresholds and hints  
LLM enable flag and model  
Google Sheets worksheet name and columns  

Phase 1 discovery returns candidate records with fields such as:

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

These candidate records are persisted for operations visibility and reruns.

Candidate status values remain simple and operator-friendly:

new  
filtered_out  
queued_for_enrichment  
enriched  
dropped  
failed  

Phase 2 enrichment uses more explicit result statuses internally so the system can distinguish policy drops from technical failures:

enriched  
dropped_low_confidence  
dropped_non_cs_relevant  
failed_fetch  
failed_enrichment  

---

# Deduplication

Before enrichment, Python checks whether the website already exists in Supabase.

Known vendors are skipped.

Function:

is_known_vendor(website)

---

# Vendor Enrichment

Goal

Collect homepage content containing commercial intelligence.

Process

Python fetches homepage via requests  
configurable request timeout  
configurable cap of up to 5 non-homepage pages per vendor  
configurable page matching and priority for pricing, product, case studies, security, about, and integrations  
unreachable pages skipped safely  
same-domain links only  
obvious junk pages such as privacy, terms, careers, login, and docs are deprioritised or skipped  

Returned page payloads include cleaned visible text suitable for deterministic extraction.

Output structure

homepage  
pricing_page  
product_page  
case_studies_page  
about_page  
security_page  
integrations_page  
extra_pages  

---

# Page Text Extraction

Goal

Extract clean visible text from fetched vendor HTML pages.

Process

Remove scripts  
Remove navigation and footer noise  
Remove cookie-banner and consent noise where practical  
Normalise whitespace  
Support deterministic per-page truncation when needed  
Return clean readable text for rule extraction  

---

# Extraction Strategy

The target system uses two independent extraction methods.

Both operate on the same vendor page dataset.

Current checkpoint:
Level 1 deterministic extraction is active across homepage plus explored high-signal pages.
Level 2 LLM extraction is also active when OpenAI configuration is available.

Level 2 runtime knobs are repo-configured in:

`config/pipeline_config.json`

That config controls:

default OpenAI model  
request timeout  
per-page text cap  
total site-text cap  
error body truncation for logs  

Current deterministic fields include:

mission  
usp  
icp  
use_cases  
lifecycle_stages  
pricing  
free_trial  
soc2  
founded  
case_studies  
customers  
value_statements  
confidence  
directory_fit  
directory_category  
include_in_directory  

---

# Vendor Profile Builder

Goal

Merge discovery metadata, explored pages, and extracted signals into a single directory-ready vendor intelligence record.

Directory-compatible profile fields:

vendor_name  
website  
mission  
usp  
icp  
use_cases  
lifecycle_stages  
pricing  
free_trial  
soc2  
founded  
case_studies  
customers  
value_statements  
confidence  
evidence_urls  
source  
directory_fit  
directory_category  
include_in_directory  

Level 1 deterministic extraction is implemented and remains the baseline extraction layer.
Level 2 semantic extraction via LLM is active as an optional enrichment pass.

Level 1 guarantees baseline structured output even if Level 2 fails or is unavailable.

---

# Level 1 Extraction (Deterministic)

Goal

Provide reliable baseline signal extraction.

Implementation

services/extraction/vendor_intel.py

Rule-based keyword detection identifies:

use cases  
product capabilities  
value signals  

Example keyword groups:

onboarding  
churn  
retention  
support  
automation  
health  
adoption  
renewal  
expansion  
NPS  

Example value statements:

reduce churn  
increase retention  
improve adoption  
automate workflows  
improve customer health  
speed time to value  

Output structure

mission  
usp  
icp  
use_cases  
lifecycle_stages  
pricing  
free_trial  
soc2  
founded  
case_studies  
customers  
value_statements  
confidence  

This extraction method is deterministic and fully testable.

---

# Level 2 Extraction (LLM)

Goal

Generate richer commercial intelligence signals.

Implementation

services/extraction/llm_extractor.py

Python calls the OpenAI Responses API with vendor website text compiled from homepage plus explored pages.
Input size is bounded deterministically using the configured per-page and total site-text caps.

The LLM returns structured JSON containing:

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
confidence  

Example structure

{
  "is_cs_relevant": true,
  "mission": "...",
  "usp": "...",
  "icp": [],
  "use_cases": [],
  "pricing": [],
  "free_trial": true,
  "soc2": false,
  "founded": "...",
  "case_studies": [],
  "customers": [],
  "value_statements": [],
  "confidence": "high"
}

If:

is_cs_relevant = false  
confidence = low  

the vendor is dropped.

Lifecycle stage classification is handled by Python using the extracted signals.
The LLM acts as a second-pass reviewer/enricher across the same core vendor fields as deterministic extraction, but vendor identity, lifecycle stages, and evidence URLs remain Python-owned.
If the LLM call fails, deterministic extraction still produces the vendor profile.

---

# Lifecycle Classification

Python maps extracted signals to lifecycle stages.

Example mapping

health score → Adopt  
support automation → Support  
churn prediction → Renew  
NPS → Advocate  
upsell detection → Expand  
onboarding automation → Onboard  

Multiple stages may apply.

---

# Storage (Supabase)

Supabase is the canonical datastore.

The repo-owned core persistence schema now lives in:

`supabase/core_persistence_schema.sql`

That SQL file is the canonical reference for the required `cs_vendors`, `discovery_candidates`, and `pipeline_runs` tables used by the live pipeline, exports, and operator views.

Upserts use:

ON CONFLICT (website) DO UPDATE

The running system now distinguishes:

Phase 1 discovery candidates persisted for review and reruns  
Phase 2 enriched vendor profiles persisted for the canonical dataset  

Manual directory overrides can be applied with:

`scripts/admin_update_vendor.py`

---

# Directory Dataset Export

The public directory uses a deterministic export built from Supabase.

Implementation

services/export/directory_dataset.py  
scripts/export_directory_dataset.py  

Only vendors where:

include_in_directory = true  

are exported.

Output file

`outputs/directory_dataset.json`

Export fields

vendor_name  
website  
mission  
usp  
icp  
use_cases  
lifecycle_stages  
pricing  
free_trial  
soc2  
founded  
case_studies  
customers  
value_statements  
confidence  
evidence_urls  
directory_fit  
directory_category  

The export is sorted alphabetically by vendor_name and written deterministically.

---

# Google Sheets Export

Google Sheets is the ops-facing review layer, not the public directory dataset.

The worksheet names and export behavior are repo-configured in:

`config/pipeline_config.json`

The primary operator-facing tabs are:

Runs  
shows one compact row per pipeline run with counts, run status, and error summary

Candidates  
shows discovery candidates with source query, status, and drop reason

Vendors  
shows enriched vendor summaries with lifecycle stages, directory fit, include flag, pricing summary, mission summary, and evidence count

Python authenticates using a service account.

Google Sheets remains the ops-facing review layer.
The public directory reads `outputs/directory_dataset.json`.

---

# Static Directory Pages

The near-launch directory experience is implemented as a static site in:

`docs/website/landing.html`  
`docs/website/directory.js`  
`docs/website/vendor.html`  
`docs/website/vendor.js`  

The listing page loads `outputs/directory_dataset.json`, renders real vendor cards, and supports client-side:

search by vendor name  
filter by lifecycle stage  
filter by directory category  
filter by free trial  
filter by SOC2  

Vendor profile pages load the same dataset and render a detailed per-vendor view.

---

# Thin Admin Operations Layer

The system now includes lightweight internal operations tooling without a full admin panel.

Manual override script

`scripts/admin_update_vendor.py`

Supports manual updates for:

include_in_directory  
directory_fit  
directory_category  

Read-only admin API

`services/admin/admin_api.py`

Endpoints:

/admin/candidates  
/admin/vendors  
/admin/runs  

Static admin dashboard

`docs/website/admin.html`

This dashboard visualises:

discovery candidates  
enriched vendors  
pipeline runs  

and can trigger lightweight include, exclude, and rerun-enrichment actions through the admin API.

---

# Container Compatibility

The project now includes a simple container path for consistent development and deployment:

`Dockerfile`  
`.dockerignore`

The container serves the admin API and static admin dashboard from one process so internal operations can be accessed on a single port.

---

# Weekly Slack Digest

Every Monday the system summarises vendors discovered in the past week.

Process

Query vendors using the configured digest lookback window from `config/scheduler.toml`  
Flatten lifecycle_stages array  
Group vendors by stage  
Post grouped digest to Slack  

Example

CS AI Vendor Weekly Digest

SIGN  
Vendor | website  

ONBOARD  
Vendor | website  

SUPPORT  
Vendor | website  

ADVOCATE  
Vendor | website  

After posting the digest, vendors are marked is_new = FALSE.

---

# External API Resilience

All external API calls implement retry logic.

Apify  
OpenAI  
Supabase  
Google Sheets  
Slack  

Retry policy

3 retries  
exponential backoff  
timeout handling  

---

# Environment Variables

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

Pipeline logs include:

vendors discovered  
vendors skipped as duplicates  
vendors enriched  
vendors classified  
vendors dropped  
rows written to Sheets  
weekly digest posted  

---

# Tests

All external services are mocked.

Test coverage includes:

discovery adapters  
enrichment HTML extraction  
rule extractor  
LLM extraction parser  
classification mapping  
Supabase upsert logic  
Google Sheets export  
Slack digest formatting  
full pipeline orchestration

Run tests with:

python -m pytest

---

# Repository Structure

AI_CustomerSuccess

services  
 discovery  
 enrichment  
 extraction  
 classification  
 persistence  
 export  
 pipeline  

tests  

docs  
 product_design.md  

requirements.txt  
.env.example  
docker-compose.yml  

---

# Design Decisions

Python owns scheduling and orchestration.

Apify is used only as a crawling utility.

Supabase is the canonical datastore.

Google Sheets is an export layer.

Dual extraction architecture ensures reliability and flexibility.

Flat schema retained for MVP simplicity.

---

# Deferred Features

Deep crawl for pricing and customer pages  
Multi-table analytics schema  
LinkedIn discovery sources  
Crunchbase enrichment  
ICP extraction  
Case study extraction  
Public vendor directory frontend  
Lead capture backend
