# Enrichment Data Sources Decision

**Date:** 2026-03-29
**Status:** In progress — G2 source pending credential setup

---

## Context

The CSP Directory enriches each vendor profile with third-party signals: ratings, review counts, market segment, company metadata (founded, HQ, funding). These fields make the directory useful to buyers comparing tools and give SuccessByCS credibility as a curated source rather than a simple list.

We need to decide which external data sources to use for each field category, based on what is technically accessible, what the cost model is, and what the data quality is for B2B SaaS / Customer Success tooling specifically.

---

## Fields we are trying to populate

| Field | Purpose |
|---|---|
| `g2_rating` | Buyer trust signal — most CS tools are primarily reviewed on G2 |
| `g2_review_count` | Signals maturity and adoption |
| `g2_market_segment` | SMB / Mid-Market / Enterprise split — critical for ICP matching |
| `g2_categories` | G2's own category taxonomy — useful for cross-referencing |
| `founded` | Company context |
| `hq_address` | Company context |
| `funding_stage` | Signals company stage (Seed vs Series E vs Bootstrapped) |
| `total_funding` | Signals scale |

---

## Decision 1: G2 ratings — cannot scrape G2 directly

### What we tried

G2.com is fully JS-rendered and protected by Cloudflare Bot Management v2/v3. A plain HTTP GET returns a Cloudflare challenge page with no rating data:

```html
<p id="cmsg">Please enable JS and disable any ad blocker</p>
```

There is no JSON-LD `AggregateRating`, no `og:rating` meta tag, and no static rating data in the response. The Apify website-content-crawler (WCC) actor — our standard JS-rendering adapter — OOM-kills on the Starter plan (exit code 137, requires >256MB) and would require an Apify plan upgrade even if Cloudflare allowed it through.

**Decision: Do not attempt to scrape G2 directly.**

### Why not upgrade Apify?

Even with more memory, Cloudflare Bot Management blocks Apify's datacenter IPs. Reliable G2 scraping requires residential proxy rotation + headless browser with fingerprint spoofing. That infrastructure cost is not justified for a directory of ~100 vendors.

### Chosen approach: RapidAPI G2 scraper (free tier)

Two RapidAPI-hosted G2 scrapers offer a free tier that returns G2-native ratings without us needing to scrape G2 ourselves:

- **biegehydra/Advanced-G2-Scraper** — returns product rating, review count, market segment, competitor listings
- **g2scraper.com** — returns product ratings, review counts, vendor data

**Why RapidAPI over other options:**
- Free tier is sufficient for our catalog size (~100 vendors, enriched once)
- No infrastructure to manage — it's a REST call
- Returns the same data fields we need: `g2_rating`, `g2_review_count`, `g2_market_segment`, `g2_categories`
- RapidAPI standardises auth (one `X-RapidAPI-Key` header) and rate-limit handling

**Setup:** See [RapidAPI Credential Setup](#rapidapi-credential-setup) below.

### Fallback considered: Trustpilot

Trustpilot serves fully static HTML with a proper schema.org `AggregateRating` JSON-LD block — extractable with a plain HTTP GET and a regex. No Cloudflare, no JS execution needed:

```json
{
  "@type": "AggregateRating",
  "ratingValue": "2.8",
  "reviewCount": "3"
}
```

**Why Trustpilot is not our primary source:**
B2B SaaS / Customer Success tools are reviewed almost exclusively on G2. Gainsight has 1,200+ G2 reviews and only 3 on Trustpilot. The Trustpilot signal is too thin to be meaningful for this directory. We will keep Trustpilot as a secondary fallback field if G2 data is unavailable.

### Other sources evaluated

| Source | Verdict | Reason |
|---|---|---|
| Capterra | ❌ Blocked | Cloudflare 403 on all requests |
| GetApp | ❌ Blocked | Same Gartner infrastructure as Capterra |
| Software Advice | ❌ Blocked | Same |
| ProductHunt | ❌ Blocked | Cloudflare managed challenge |
| Google SERP snippet | ❌ Not viable | G2 doesn't emit `AggregateRating` JSON-LD, so Google has no rating to show |
| Piloterr API | ⚠️ Under maintenance | Returns G2-native data — worth revisiting if RapidAPI scrapers degrade |
| Bright Data G2 dataset | 💰 Bulk only | $250 minimum — appropriate if we scale to 10K+ vendors |

---

## Decision 2: Company metadata (founded, HQ, funding) — Tracxn blocked, need alternative

### What we tried

M66 built `services/enrichment/tracxn_enricher.py` targeting `tracxn.com/d/companies/{slug}/`. This worked at the time the milestone was written but Tracxn has since changed their URL scheme and now serves a JS cookie-challenge page to all non-browser clients:

```
Title: 404 Page not found - Tracxn
Body: try{"visible"===document.visibilityState&&(document.cookie="AID=...
```

The Apify WCC actor (our standard JS-rendering path) OOM-kills on Starter plan before it can process Tracxn's bot-detection challenge.

**Decision: Tracxn direct scraping is not viable on current infrastructure.**

### Current status

11 of 118 vendors have `founded` populated (from earlier web crawls, not Tracxn). `hq_address`, `funding_stage`, and `total_funding` are empty across the board.

### Chosen approach: Internal rating system (M70)

Rather than sourcing company metadata from Tracxn (which is gated) or Crunchbase (API is expensive), we are pivoting to build a **first-party feature-depth score** derived from each vendor's own help/documentation site. This produces signal that is:

1. Unique to SuccessByCS — not available anywhere else
2. More relevant to CS buyers than a funding stage
3. Derivable from infrastructure we already have (`help_center_url`, `Framework Website Content Crawl`)

See M70 milestone for specification.

For `founded`/`hq_address` we will use Google Search as a plain-text fallback (search `"{vendor_name}" founded site:crunchbase.com` and extract the year from the snippet text) — no Crunchbase API required.

---

## Decision 3: Internal feature-depth score (M70)

### Why we are building this

G2's star rating is a lagging indicator — it reflects historical customer satisfaction, not current feature breadth. For a directory used by CS leaders evaluating tools, knowing that Vendor A has 47 documented help articles on integrations while Vendor B has 3 is more actionable than knowing one has 4.2 stars and the other 4.1.

### How it works

1. Crawl `help_center_url` for each vendor using `Framework Website Content Crawl`
2. Extract feature taxonomy: integration coverage, automation capabilities, reporting depth, onboarding tooling, etc.
3. Score each vendor relative to others in the same `directory_category`
4. Expose as `feature_depth_score` (0–100, category-relative) and `feature_signals` (list of detected capabilities)

### What this enables

- Category-level comparison tables on the public directory
- Buyer-role filtering ("show me tools with strong reporting for enterprise CS teams")
- A defensible editorial position for SuccessByCS that goes beyond aggregating existing data

---

## RapidAPI Credential Setup

To start using the G2 scrapers via RapidAPI:

### Step 1 — Create a RapidAPI account
1. Go to [rapidapi.com](https://rapidapi.com) and sign up (free, no card required)
2. You are automatically assigned an API key visible at [rapidapi.com/developer/apps](https://rapidapi.com/developer/apps)
3. Copy the key — it goes in `.env` as `RAPIDAPI_KEY`

### Step 2 — Subscribe to G2 scraper APIs (free tier)
Subscribe to both — try whichever works better for our vendor list:

- [Advanced G2 Scraper by biegehydra](https://rapidapi.com/search/Advanced%20G2%20Scraper) — search RapidAPI for "Advanced G2 Scraper"
- [G2 Scraper](https://rapidapi.com/search/g2%20scraper) — search for "g2 scraper"

Click **Subscribe to Test** on the free tier for each.

### Step 3 — Add to .env
```
RAPIDAPI_KEY=your_key_here
RAPIDAPI_G2_HOST=advanced-g2-scraper.p.rapidapi.com   # or whichever you subscribe to
```

### Step 4 — We build the n8n workflow / Python enricher
Once credentials are in `.env`, the G2 enrichment workflow (`CSP G2 Enrichment` in n8n) needs a node updated to call the RapidAPI endpoint instead of the direct G2 URL. The extraction logic stays the same — only the data source changes.

---

## Summary of active decisions

| Field group | Source | Status |
|---|---|---|
| G2 rating, reviews, segment | RapidAPI G2 scraper | Pending RapidAPI signup |
| Trustpilot rating | Direct HTTP + JSON-LD | Available now, low B2B coverage |
| founded, hq_address | Google Search snippet fallback | To be built |
| funding_stage, total_funding | Tracxn blocked — deprioritised | Blocked |
| Feature depth score | Internal crawl of help_center_url | M70 — to be specced |
