# CSP Directory — Implementation Plan

This is the operator-readable milestone plan. The machine-readable source of truth is `milestone_registry.json`.

**Current focus:** M109 — Production bug fix for lead capture backend across Vercel, Supabase, and n8n

**Blocked:** M110 — LinkedIn enrichment removed from the admin flow pending replacement API selection

---

## Completed

### M35 Human test and operator validation
Status: `complete`

Operator ran the full pipeline end-to-end and recorded a structured validation outcome with pass/fail notes per area.

---

### M36 Supabase schema baseline and migration tool
Status: `complete`

Fixed `auto_directory_category` schema drift causing every Supabase upsert to fail with PGRST204. Applied all missing columns to the live `cs_vendors` table using `scripts/apply_schema_migration.py`.

---

### M37 LLM extraction persistence fix
Status: `complete`

Fixed the gap where LLM extraction ran but structured fields never wrote to Supabase. Pipeline confirmed writing `lifecycle_stages`, `use_cases`, `icp_buyer`, and `pricing` for real vendors.

---

### M38 Discovery quality filter
Status: `complete`

Added a vendor quality filter at discovery that rejects non-vendor URLs (blog posts, Reddit threads, aggregator sites, error pages). Expanded denylist to 45 domains, 13 aggregator/review/job-board sites. 17/17 test cases pass.

Changed files: `config/pipeline_config.json`, `config/discovery.toml`, `scripts/validate_discovery_filter.py`

---

### M39 Apify web scraper enrichment
Status: `complete`

Replaced plain HTTP enrichment with Apify Website Content Crawler as the primary enrichment path. JS-heavy SaaS sites (e.g. Gainsight) that previously returned empty fields now return rendered content.

Changed files: `services/enrichment/vendor_fetcher.py`, `scripts/prove_m39_apify_enrichment.py`

---

### M39B n8n architecture: route all Apify calls through n8n webhooks
Status: `complete`

Replaced direct `apify_client` Python calls with n8n webhook calls. All discovery (Google Search) and enrichment (Website Content Crawler) now route through n8n workflows so providers are swappable.

Changed files: `services/discovery/apify_sources.py`, `services/n8n_client.py`

---

### M39C ICP extraction n8n workflow: deploy and verify
Status: `complete` (2026-03-25)

Deployed Framework ICP Extraction n8n workflow. Accepts URL + optional pre-fetched `page_text`, returns structured buyer personas via GPT-4o-mini. Fixed empty-response bug (node ID vs display name in `$()` reference).

Webhook: `framework-icp-extraction` | Workflow ID: `vLLRqzmr5peR9Jtu`

---

### M39D Deterministic structured page extraction (no LLM for core fields)
Status: `complete` (2026-03-25)

Built `services/extraction/structured_page_extractor.py` — extracts mission/description from meta tags and JSON-LD schema without LLM. Priority order: `<meta name=description>` → `og:description` → `twitter:description` → JSON-LD description. Rejects JS artifacts. Tested against Gainsight, ChurnZero, Vitally, Totango, Planhat, Userpilot — all return clean human-readable descriptions.

Key function: `extract_structured_fields(html) -> {description, name, founded, url, og_image}`

---

### M39E Deterministic batch enrichment script: clean fields for all vendors
Status: `complete` (2026-03-25)

Built `scripts/enrich_vendors_deterministic.py` — replaces LLM-heavy enrichment with: (1) plain HTTP GET + meta tag extraction for mission/founded/name, (2) n8n WCC for markdown text → keyword classifiers for `lifecycle_stages`/`use_cases`/`icp`, (3) `directory_relevance` for fit/category/include flag.

Bug fixes: Supabase array columns (`icp`, `use_cases`, `lifecycle_stages`, `directory_reasoning`) must receive Python lists, not `json.dumps()` strings.

---

### M39F n8n self-hosted Docker scaffold
Status: `complete` (2026-03-25)

Created `/home/chris/n8n-Workflow-Builder/docker/` scaffold: `docker-compose.yml` (n8n latest, SQLite, configurable webhook URL, basic auth), `.env.docker.example` config template, `migrate_workflows.py` (exports 21 workflows from n8n cloud, imports to self-hosted, re-activates active ones).

Usage: `cd docker && cp .env.docker.example .env.docker && docker compose up -d && python3 migrate_workflows.py`

---

### M40 Full pipeline operational proof
Status: `complete` (2026-03-25)

Deterministic enrichment ran on 77 vendors. 75 updated, 3 deleted. Mission 98%, `directory_fit` 97%, 37 vendors with `include_in_directory=True`.

---

### M-AF17 AF framework fixes applied to CSP
Status: `complete`
Type: `framework_fix`

AF closeout audit root bug fixed (`milestone_auditor.py`) and `inspect_cli.py` created to give analysis roles live Supabase inspection capability. Both fixes propagated to CSP pipeline.

---

### M41 Single vendor complete field verification
Status: `complete` (2026-03-25)

Ran enrichment on Vitally.io end-to-end and proved ALL 19 Supabase fields populated: `vendor_name`, `website`, `source`, `mission`, `usp`, `icp`, `use_cases`, `lifecycle_stages`, `pricing`, `free_trial`, `soc2`, `founded`, `case_studies`, `customers`, `value_statements`, `confidence`, `evidence_urls`, `directory_fit`, `directory_category`, `include_in_directory`.

---

## In Progress

### M43 Canonical vendor name enforcement
Status: `in_progress`
Depends on: M41

**Objective:** Ensure every vendor in `cs_vendors` has a clean, canonical name. Names that fail quality checks (contain title separators like `|`, `—`, `-`, `>`; are longer than 60 chars; or start with article words like "what", "how", "best", "top", "guide", "the", "a", "an") must be overwritten with the canonical form derived from `og:site_name` or domain-name fallback.

**Acceptance criteria:**
- Zero vendors in `cs_vendors` where name contains `|` or `—` or starts with article words
- Gainsight row name = `'Gainsight'`
- Outreach row name = `'Outreach'`
- Unit tests pass: feed 10 known-bad names, assert all overwritten with clean name

**Verification:**
```
python3 scripts/enrich_vendors_deterministic.py --vendor-id <gainsight_id>
python3 scripts/enrich_vendors_deterministic.py --vendor-id <outreach_id>
python3 -m pytest tests/test_canonical_name.py -v
python3 scripts/autonomous_audit.py
```

---

### M109 Production bug fix — lead capture backend hardening across Vercel, Supabase, and n8n
Status: `in_progress`
Depends on: M53

**Objective:** Fix the live lead capture outage on `vendors.successbycs.com`. The public popup currently falls through a broken `/api/lead-capture` path because the Vercel backend is configured with an invalid or under-privileged Supabase key and/or a target project missing the `lead_captures` schema. The n8n webhook also shipped with a broken response mode and must remain aligned with its `Respond to Webhook` nodes.

**Bug-fix status:** n8n root cause already identified and corrected live. Execution `2445` failed with `Unused Respond to Webhook node found in the workflow`; the live `CSP Lead Capture Intake` workflow was updated from `onReceived` to `responseNode` and verified with a real Discord delivery. Remaining production issue: `https://vendors.successbycs.com/api/lead-capture` still returns `500` with `HTTP Error 404: Not Found`, reproduced against the configured Supabase REST endpoint for `lead_captures`.

**Acceptance criteria:**
- Live n8n workflow `CSP Lead Capture Intake` uses `Webhook.responseMode=responseNode` and responds `200` to POST `/webhook/csp-lead-capture-intake`
- Vercel project has a valid server-side Supabase credential configured via `SUPABASE_SERVICE_ROLE_KEY` or equivalent trusted key alias
- Target Supabase project contains `public.lead_captures` with the repo-owned schema applied
- `POST https://vendors.successbycs.com/api/lead-capture` with a valid payload returns `ok:true`
- Landing page lead capture popup succeeds end-to-end from the browser and triggers Discord notification
- `scripts/check_supabase.py` explicitly validates `lead_captures` so future deploys catch this class of failure before release

**Verification:**
```sh
python3 scripts/check_supabase.py
curl -f -X POST https://successbycs.app.n8n.cloud/webhook/csp-lead-capture-intake -H 'Content-Type: application/json' -d '{"lead_name":"Test User","lead_email":"chris@successbycs.com","company_name":"SuccessByCS","lead_intent":"browse_directory"}'
python3 scripts/autonomous_audit.py
```

---

## Future / Non-Critical

### M-BP1 CSP→AF backport: web_page_fetch, site_explorer, health_check ported to AF recipes
Status: `deferred`
Depends on: M46, M47

This is future backport work for the Autonomous Framework. It is useful for reuse across products, but it is non-critical for the current CSP delivery path and stays paused until active CSP milestones are complete.

---

## Not Started

### M44 Junk domain enforcement: config-driven denylist with subdomain matching
Status: `not_started`
Depends on: M43

**Objective:** Junk domain filtering must be driven entirely from `pipeline_config.json junk_domain_denylist`. The `_is_junk_domain()` function must match both apex domains (`hubspot.com`) and any subdomain (`academy.hubspot.com`). Filtering must run at discovery (block insert) and enrichment (delete if slipped through).

**Acceptance criteria:**
- Zero rows in `cs_vendors` where website matches any junk domain or subdomain
- Unit tests pass: `forbes.com`, `academy.hubspot.com`, `support.gainsight.com` → all blocked
- `pipeline_config.json junk_domain_denylist` is the single source of truth — no hardcoded lists in Python

---

### M45 Lifecycle stage enforcement: no vendor in directory without lifecycle stages
Status: `not_started`
Depends on: M43

**Objective:** Enforce that `include_in_directory` is always false for any vendor with null or empty `lifecycle_stages`. Applied as a post-enrichment rule automatically — not a manual SQL fix.

**Acceptance criteria:**
- Zero rows where `include_in_directory=true` AND `lifecycle_stages` is null or empty
- Rule applied automatically at end of every enrichment run
- Unit test: create vendor with `lifecycle_stages=null`, run enforcement, assert `include_in_directory=false`

---

### M46 Pipeline health check report: post-cycle quality gate
Status: `not_started`
Depends on: M44, M45

**Objective:** A health check script runs automatically after every enrichment cycle and asserts four zero-violation conditions: (1) no directory vendors with empty lifecycle stages, (2) no article-title names, (3) no junk domain matches, (4) no vendors enriched with null `directory_decision_source`. Script exits non-zero and logs each violation on failure.

**Acceptance criteria:**
- Exits 0 when all conditions are zero-violation
- Exits 1 and logs each violation when any condition fails
- Runs automatically as the final step of the pipeline chain
- Unit tests cover all four check conditions with pass and fail cases

---

### M47 Discover → enrich → export: single entry point pipeline
Status: `not_started`
Depends on: M46

**Objective:** `python3 scripts/discover_vendors.py` executes the full pipeline chain without any manual steps: (1) discover, (2) enrich, (3) enforce name quality and lifecycle rules, (4) run health check, (5) export `directory_dataset.json`. Pipeline exits non-zero if health check fails — export does not run on a failed check.

**Acceptance criteria:**
- Single command runs full chain end-to-end
- `directory_dataset.json` always regenerated after a successful cycle
- Unit test: mock all external calls, assert all five steps execute in order

---

### M48 ICP field: always populated for every vendor
Status: `not_started`
Depends on: M46

**Objective:** The ICP field must be populated for every vendor via LLM review of scraped website content using the n8n ICP extraction workflow (GPT-4o-mini). If WCC times out, retry with plain HTTP text. Vendors where ICP extraction fails after retry are excluded from directory until fixed.

**Acceptance criteria:**
- Zero vendors where `include_in_directory=true` AND `icp` is null or empty
- Retries with plain HTTP text if WCC fails
- Unit tests: mock LLM response (assert ICP populated); mock LLM failure (assert vendor excluded from directory)

---

### M49 Case studies extraction: populate case_studies and customers fields
Status: `not_started`
Depends on: M46

**Objective:** Crawl `/customers`, `/case-studies`, or `/customer-stories` pages for each vendor. Extract customer company names into `customers` and outcome statements into `case_studies`. These fields are currently 100% blank. Extraction is deterministic — no LLM required for company name detection.

**Acceptance criteria:**
- `case_studies` populated for all vendors where a customer/case-study page exists
- `customers` populated with at least one company name where detectable
- Unit tests: feed known case study HTML, assert customer names and outcomes extracted correctly

---

### M50 G2 enrichment: augment all vendors with G2 profile data
Status: `not_started`
Depends on: M46

**Objective:** Add a G2 enrichment step. For each vendor, find their G2 product page via Google Search (`'{vendor_name} site:g2.com'`), scrape via Apify WCC, and extract structured data. G2 must remain in `junk_domain_denylist` for discovery — it is an enrichment source only, never a vendor entry.

**New schema fields:** `g2_url`, `g2_rating`, `g2_review_count`, `g2_market_segment`, `g2_categories`

**Existing fields augmented:** `testimonials`, `value_statements`, `icp`, `icp_buyer`, `free_trial`, `integrations`, `integration_categories`, `pricing`, `soc2`, `compliance`

**Acceptance criteria:**
- `g2_url` populated for all vendors where a G2 profile exists
- `g2_rating` and `g2_review_count` populated wherever `g2_url` is set
- `testimonials` populated for all vendors with G2 reviews
- G2 enrichment runs as a separate step after primary enrichment — does not replace it

---

### M51 Deep crawl: async Apify job up to 100 pages per vendor
Status: `not_started`
Depends on: M46

**Objective:** Replace the synchronous n8n WCC webhook call (max 3 pages, 100s Cloudflare limit) with a direct async Apify job crawling up to 100 pages per vendor. The n8n webhook path remains as a fast fallback.

**New schema fields:** `raw_crawl_blob`, `crawl_page_count`, `crawl_completed_at`

**Acceptance criteria:**
- Apify job submitted async — does not block enrichment pipeline beyond submission
- Polling retries up to 15 minutes before timeout
- Falls back to n8n WCC (3 pages) if Apify async job fails
- Unit tests: mock Apify API, assert job submitted, polled, and blob stored correctly

---

### M52 LLM structured extraction from deep crawl blob
Status: `not_started`
Depends on: M51

**Objective:** Run structured LLM extraction (GPT-4o, 128k context) against `raw_crawl_blob` for each vendor. Blobs exceeding context must be chunked: extract per chunk then merge deduplicated results.

**Fields extracted:** `customers`, `products`, `icp_buyer`, `lifecycle_stages`, `icp`, `value_statements`, `integrations`, `case_studies`

**Acceptance criteria:**
- All target fields populated for vendors with a deep crawl blob
- Chunking handles blobs of any size without truncation or data loss
- Extraction cost tracked per vendor — log token usage
- Unit tests: feed known blob, assert all fields extracted correctly

---

### M42 Expand vendor catalog to 50+ vendors
Status: `not_started`
Depends on: M41

**Objective:** Run full discovery + enrichment pipeline across all configured queries. Prove 50+ real vendor records in `cs_vendors` with an average fewer than 5 empty enrichment fields. Produce `directory_dataset.json` export ready for the public frontend.

**Acceptance criteria:**
- 50+ vendors in `cs_vendors` with quality enrichment data
- `directory_dataset.json` export valid and ready for frontend consumption

---

## Verification commands

```bash
# Check current milestone status
python3 /home/chris/SuccessByCS-Builder/Autonomous-Framework/scripts/autonomous_controller.py \
  --root /home/chris/projects/CSP-Directory status

# Run a controller cycle (advances current milestone)
python3 /home/chris/SuccessByCS-Builder/Autonomous-Framework/scripts/autonomous_controller.py \
  --root /home/chris/projects/CSP-Directory run-cycle

# Audit current milestone evidence
python3 scripts/autonomous_audit.py

# Check Supabase state
python3 scripts/check_supabase.py
```
