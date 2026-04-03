# M74 Implementation Plan — Three-Tier Vendor Site Crawl as n8n/Apify Pipeline

## Problem Statement

1. **Vendor site crawl** (`vendor_fetcher.py`) — direct HTTP fails on JS-rendered sites, bot detection, CAPTCHAs. No observable retry, no tier escalation.
2. **Tracxn enrichment** — `/d/companies/` URL scheme returns 404; site now behind CloudFront (403). Both Python scraper and n8n workflow dead.
3. **Name extraction** — page `<title>` taglines accepted as vendor names (e.g. "AI-Powered Text Feedback Analytics" for Thematic). Fixed deterministically in M74 via tagline filter + domain prefix stripping.

---

## Three-Tier Crawl Architecture

Each tier is a **separate n8n workflow** with an identical response contract. Python dispatch logic calls Tier 1 first and escalates only when quality thresholds fail.

```
Python (vendor_fetcher.py)
  │
  ├─ N8N_CRAWL_TIER1_WEBHOOK set?
  │    └─ POST csp-crawl-tier1-direct
  │         ├─ word_count >= 200 AND name resolved? → DONE ✓
  │         └─ below threshold → escalate to Tier 2
  │
  ├─ N8N_CRAWL_TIER2_WEBHOOK set?
  │    └─ POST csp-crawl-tier2-rag
  │         ├─ word_count >= 200 AND name resolved? → DONE ✓
  │         └─ below threshold → escalate to Tier 3
  │
  └─ N8N_CRAWL_TIER3_WEBHOOK set?
       └─ POST csp-crawl-tier3-wcc
            └─ return result regardless (best effort)

  Fallback: if no webhooks configured → existing direct HTTP in vendor_fetcher.py (unchanged)
```

### Escalation thresholds

| Condition | Action |
|---|---|
| `word_count < 200` | Escalate to next tier |
| `name` is empty or looks like tagline | Escalate to next tier |
| HTTP error / timeout from n8n | Escalate to next tier |
| Both Tier 1 + 2 fail | Always attempt Tier 3 |

---

## Tier 1 — `csp-crawl-tier1-direct`

**File:** `n8n/workflows/csp-crawl-tier1-direct.workflow.json`
**Cost:** Free (n8n HTTP Request node only — no Apify)
**Best for:** ~60% of static/SSR sites

### Flow

```
Webhook
  → Validate Input (Code)
  → HTTP Request node (GET {website})
      headers: User-Agent Mozilla/5.0, Accept text/html
      timeout: 15s
  → Extract Name + Text (Code)
      Priority: og:site_name → application-name → apple-mobile-web-app-title → <title> (cleaned)
      Text: strip HTML tags, collapse whitespace
  → Respond { vendor_name, website, name, word_count, tier_used: "tier1_direct", ok, pages }
```

### Name cleaning rules (applied in all tiers)

1. Split on ` | `, ` - `, ` – `, ` — `, `: ` — take first passing segment
2. Reject if ends with: `analytics`, `platform`, `software`, `intelligence`, `automation`, `management`, `solution`, `solutions`, `monitoring`, `reporting`, `tracking`, `dashboard`, `insights`
3. Reject if matches `\w+-powered` pattern
4. Reject if word count > 5 or char length > 40
5. **Domain fallback**: strip `get`, `try`, `use`, `my`, `the` prefixes if remaining stem ≥ 4 chars → `.title()`
   `getthematic` → `Thematic` | `trygainsight` → `Gainsight` | `useintercom` → `Intercom`

---

## Tier 2 — `csp-crawl-tier2-rag`

**File:** `n8n/workflows/csp-crawl-tier2-rag.workflow.json`
**Cost:** ~$0.001/page (Apify RAG Web Browser — `apify/rag-web-browser`)
**Best for:** JS-rendered SPAs, lazy-loaded content

### Flow

```
Webhook
  → Validate Input (Code) — reads apify_token from payload or n8n var APIFY_TOKEN
  → POST https://api.apify.com/v2/acts/apify~rag-web-browser/run-sync-get-dataset-items
      body: { startUrls: [{url}], maxCrawlPages: 1 }
  → Extract Name + Text (Code) — same name cleaning rules as Tier 1
  → Respond { ..., tier_used: "tier2_rag" }
```

---

## Tier 3 — `csp-crawl-tier3-wcc`

**File:** `n8n/workflows/csp-crawl-tier3-wcc.workflow.json`
**Cost:** ~$0.004/page (Apify Website Content Crawler — `apify/website-content-crawler`)
**Best for:** Cloudflare-protected, heavy anti-bot sites; multi-page crawls

### Flow

```
Webhook
  → Validate Input (Code)
  → POST https://api.apify.com/v2/acts/apify~website-content-crawler/run-sync-get-dataset-items
      body: {
        startUrls: [{url}],
        maxCrawlPages: {{ max_pages || 5 }},
        proxyConfiguration: { useApifyProxy: true }
      }
  → Normalize Pages (Code) — title, text, url per page
  → Extract Name (Code) — same cleaning rules; checks all pages for og:site_name
  → Respond { ..., tier_used: "tier3_wcc", pages: [...] }
```

---

## Shared Response Contract (all three tiers)

```json
{
  "ok": true,
  "vendor_name": "Thematic",
  "website": "https://getthematic.com",
  "name": "Thematic",
  "word_count": 1842,
  "tier_used": "tier1_direct",
  "pages": [
    { "url": "https://getthematic.com", "title": "Thematic", "text": "..." }
  ]
}
```

---

## Deliverable 4 — `csp-google-discovery` Workflow

**File:** `n8n/workflows/csp-google-discovery.workflow.json`

```
Webhook POST /csp-google-discovery
  → Split Queries (Code)
  → POST apify/google-search-scraper per query
      { query, maxPagesPerQuery: 1, resultsPerPage: 10 }
  → Filter Candidates (Code)
      Reject: reddit, g2, capterra, trustradius, getapp, producthunt, wikipedia, linkedin
  → POST /admin/discovery-upsert (Admin API)
  → Respond { ok, queued: N, skipped: N }
```

---

## Python Integration — `vendor_fetcher.py`

```python
N8N_CRAWL_TIER1_WEBHOOK = os.environ.get("N8N_CRAWL_TIER1_WEBHOOK")
N8N_CRAWL_TIER2_WEBHOOK = os.environ.get("N8N_CRAWL_TIER2_WEBHOOK")
N8N_CRAWL_TIER3_WEBHOOK = os.environ.get("N8N_CRAWL_TIER3_WEBHOOK")

ESCALATION_WORD_COUNT_THRESHOLD = 200

def fetch_via_n8n_tiered(vendor: dict) -> dict | None:
    for webhook, tier in [
        (N8N_CRAWL_TIER1_WEBHOOK, "tier1"),
        (N8N_CRAWL_TIER2_WEBHOOK, "tier2"),
        (N8N_CRAWL_TIER3_WEBHOOK, "tier3"),
    ]:
        if not webhook:
            continue
        result = _call_n8n_crawl(webhook, vendor)
        if result and result.get("ok"):
            wc = result.get("word_count", 0)
            name = result.get("name", "")
            if wc >= ESCALATION_WORD_COUNT_THRESHOLD and name:
                return result  # good enough — stop escalating
            # else: escalate to next tier
    return None  # all tiers exhausted or unconfigured → caller uses direct HTTP fallback
```

### `.env` additions

```
N8N_CRAWL_TIER1_WEBHOOK=https://<n8n>/webhook/csp-crawl-tier1-direct
N8N_CRAWL_TIER2_WEBHOOK=https://<n8n>/webhook/csp-crawl-tier2-rag
N8N_CRAWL_TIER3_WEBHOOK=https://<n8n>/webhook/csp-crawl-tier3-wcc
N8N_DISCOVERY_WEBHOOK=https://<n8n>/webhook/csp-google-discovery
```

---

## Deliverable — Tracxn Deprecation

- `services/enrichment/tracxn_enricher.py` — add `# DEPRECATED: Tracxn URL scheme dead (404). See M74/M75.` at module top
- `n8n/workflows/csp-tracxn-enrichment.workflow.json` — set `"active": false`
- Funding/founder data now handled by M75 (LinkedIn Company Scraper)

---

## Execution Order

1. Build + deploy `csp-crawl-tier1-direct` → test on 5 static sites
2. Build + deploy `csp-crawl-tier2-rag` → test on 5 JS-rendered sites
3. Build + deploy `csp-crawl-tier3-wcc` → test on 5 Cloudflare-protected sites
4. Add `fetch_via_n8n_tiered()` to `vendor_fetcher.py`; keep direct HTTP fallback
5. Build + deploy `csp-google-discovery`; add `N8N_DISCOVERY_WEBHOOK` to `web_search.py`
6. Run end-to-end proof on 10 vendors; record `tier_used` distribution
7. Deprecate Tracxn

## Proof Artifact

`runs/proofs/M74_n8n_crawl_pipeline.json` must contain:
- n8n workflow IDs for all 4 workflows
- 10 vendor sample with `tier_used`, `word_count`, `name`
- Tier distribution (how many needed Tier 2/3)
- Discovery run: queries → candidates upserted
