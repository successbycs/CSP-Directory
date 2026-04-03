# Enrichment Source Map — cs_vendors Field Coverage

**Dataset:** 119 vendors · Last updated: 2026-03-30
**Purpose:** For each schema field — current delivery method, success rate, and proposed alternative source.

---

## Key Findings

- **100% filled today:** `name`, `website` — identity fields set at discovery
- **Well-covered (74–92%):** `use_cases`, `lifecycle_stages`, `icp`, `mission`, `usp`, `pricing`, `founded` — LLM pipeline working
- **Critical gaps (0–5%):** `integrations`, `customers`, `value_statements`, `leadership`, `icp_buyer`, `products`, `case_study_details` — fields exist but pipeline not populating them reliably
- **Never filled (0%):** `ceo_linkedin`, `youtube_channel_url`, `funding_stage`, `total_funding`, `has_public_pricing_page`, `icp_buyer` — no pipeline built yet
- **G2 sparse (17%):** Only 20/119 vendors have G2 data — pipeline runs manually, not on all vendors

---

## Platform Subscription Status

| Platform | Status | Used For |
|---|---|---|
| Apify | ✅ Active (`APIFY_API_TOKEN`) | Site crawl (WCC, RAG Browser), Google Search, LinkedIn scraper |
| RapidAPI | ✅ Active (unified key covers all subscribed APIs) | G2 Data API (live) · LinkedIn Data API (key added, subscription needed) · Crunchbase free tier available · BlitzAPI 100 free credits/mo |
| Datagma | ❌ Not subscribed (on RapidAPI) | Single-call firmographic enrichment (65+ fields including funding, CEO, HQ) |

---

## Field-by-Field Coverage Table

| Field | Current Value | Delivered By (Today) | Workflow | Fill Rate | Proposed Alt 1 (Apify) | Proposed Alt 2 (RapidAPI) |
|---|---|---|---|---|---|---|
| `name` | Company name | Python `vendor_fetcher.py` — `og:site_name` / `<title>` extraction | Direct HTTP + HTML parse | **100%** but ~15% are taglines (known bug) | `apify/website-content-crawler` — og:site_name with tagline filter | [linkedin-data-api.p.rapidapi.com](https://rapidapi.com/rockapis-rockapis-default/api/linkedin-data-api) — `name` field |
| `website` | Vendor URL | Discovery pipeline input | `web_search.py` / manual | **100%** | N/A | N/A |
| `mission` | Company mission statement | LLM extraction from crawled homepage | `llm_extractor.py` + `vendor_fetcher.py` | **84%** | `apify/website-content-crawler` → LLM | No structured source |
| `usp` | Unique selling proposition | LLM extraction from homepage copy | `llm_extractor.py` | **84%** | `apify/website-content-crawler` → LLM | No structured source |
| `raw_description` | Meta description | `vendor_fetcher.py` — `<meta name="description">` | Direct HTTP | **83%** | `apify/website-content-crawler` — `description` field | [Datagma](https://rapidapi.com/raphael-0lpOSWjHK34/api/enrichment-b2b-linkedin-crunchbase-datagma) — LinkedIn `about` |
| `pricing` | Pricing signals | LLM extraction + deterministic patterns | `llm_extractor.py` + `pricing_enricher.py` | **93%** (but mostly just `["$"]`) | `apify/website-content-crawler` — pricing page | No structured source |
| `free_trial` | Has free trial boolean | LLM extraction | `llm_extractor.py` | **36%** | `apify/website-content-crawler` — detect "free trial" text | No structured source |
| `has_public_pricing_page` | Pricing page exists | Not built | — | **0%** | `apify/website-content-crawler` — check `/pricing` URL returns 200 | No structured source |
| `founded` | Founding year | Direct HTTP scrape of `tracxn.com/d/companies/{slug}/` | `tracxn_enricher.py` (**BROKEN** — 404) | **92%** (populated before Tracxn broke) | [0x33/crunchbase-company-scraper](https://apify.com/0x33/crunchbase-company-scraper) — `foundedOn` (104 fields, no auth) | [Datagma](https://rapidapi.com/raphael-0lpOSWjHK34/api/enrichment-b2b-linkedin-crunchbase-datagma) — `yearFounded` |
| `hq_address` | HQ city/country | `tracxn_enricher.py` (**BROKEN**) | Direct HTTP scrape | **33%** | [data-slayer/linkedin-company-scraper](https://apify.com/data-slayer/linkedin-company-scraper) — `headquarter` object | [Datagma](https://rapidapi.com/raphael-0lpOSWjHK34/api/enrichment-b2b-linkedin-crunchbase-datagma) — `locality/region/country` |
| `company_hq` | HQ shortform | `tracxn_enricher.py` (**BROKEN**) | Direct HTTP scrape | **33%** | [data-slayer/linkedin-company-scraper](https://apify.com/data-slayer/linkedin-company-scraper) | [Datagma](https://rapidapi.com/raphael-0lpOSWjHK34/api/enrichment-b2b-linkedin-crunchbase-datagma) |
| `funding_stage` | e.g. "Series B" | `tracxn_enricher.py` (**BROKEN**) | Direct HTTP scrape | **0%** | [0x33/crunchbase-company-scraper](https://apify.com/0x33/crunchbase-company-scraper) — `lastFundingType` | [Datagma](https://rapidapi.com/raphael-0lpOSWjHK34/api/enrichment-b2b-linkedin-crunchbase-datagma) — `lastFundingType` |
| `total_funding` | Total raised e.g. "$12M" | `tracxn_enricher.py` (**BROKEN**) | Direct HTTP scrape | **0%** | [0x33/crunchbase-company-scraper](https://apify.com/0x33/crunchbase-company-scraper) — `totalFundingAmount` | [Datagma](https://rapidapi.com/raphael-0lpOSWjHK34/api/enrichment-b2b-linkedin-crunchbase-datagma) — `totalFunding` |
| `ceo_name` | CEO full name | LLM extraction from about/team pages | `llm_extractor.py` | **3%** | [0x33/crunchbase-company-scraper](https://apify.com/0x33/crunchbase-company-scraper) — `founders`/`keyPeople` | [Datagma](https://rapidapi.com/raphael-0lpOSWjHK34/api/enrichment-b2b-linkedin-crunchbase-datagma) — LinkedIn executives |
| `ceo_linkedin` | CEO LinkedIn URL | Not built | — | **0%** | [data-slayer/linkedin-company-scraper](https://apify.com/data-slayer/linkedin-company-scraper) — executive profiles | [linkedin-data-api.p.rapidapi.com](https://rapidapi.com/rockapis-rockapis-default/api/linkedin-data-api) — company executives |
| `leadership` | Executives array | LLM extraction | `llm_extractor.py` | **3%** non-empty | [data-slayer/linkedin-company-scraper](https://apify.com/data-slayer/linkedin-company-scraper) — executives list | [linkedin-data-api.p.rapidapi.com](https://rapidapi.com/rockapis-rockapis-default/api/linkedin-data-api) |
| `use_cases` | Use case strings | LLM extraction from homepage | `llm_extractor.py` | **74%** non-empty | `apify/website-content-crawler` → LLM | No structured source |
| `lifecycle_stages` | CS lifecycle mapping | LLM extraction | `llm_extractor.py` | **77%** non-empty | `apify/website-content-crawler` → LLM | No structured source |
| `icp` | Ideal customer strings | LLM extraction | `llm_extractor.py` | **81%** non-empty | `apify/website-content-crawler` → LLM | No structured source |
| `icp_buyer` | Buyer personas (jsonb) | LLM extraction | `llm_extractor.py` | **0%** non-empty | `apify/website-content-crawler` → LLM | No structured source |
| `products` | Product list (jsonb) | LLM extraction | `llm_extractor.py` | **3%** non-empty | `apify/website-content-crawler` → LLM | No structured source |
| `value_statements` | Marketing claims | LLM extraction | `llm_extractor.py` | **6%** non-empty | `apify/website-content-crawler` → LLM | No structured source |
| `customers` | Customer names | LLM extraction from logo walls | `llm_extractor.py` | **3%** non-empty | `apify/website-content-crawler` → LLM | No structured source |
| `case_studies` | Case study URLs | LLM extraction | `llm_extractor.py` | **4%** non-empty | `apify/website-content-crawler` → LLM | No structured source |
| `case_study_details` | Structured case data | LLM extraction | `llm_extractor.py` | **3%** non-empty | `apify/website-content-crawler` → LLM | No structured source |
| `testimonials` | Customer quotes | LLM extraction | `llm_extractor.py` | **3%** non-empty | `apify/website-content-crawler` → LLM | No structured source |
| `blog_posts` | Blog post list | LLM extraction | `llm_extractor.py` | **3%** non-empty | `apify/website-content-crawler` → LLM | No structured source |
| `integrations` | Integration names | LLM extraction | `llm_extractor.py` | **5%** non-empty | `apify/website-content-crawler` — integrations/marketplace pages | [Datagma](https://rapidapi.com/raphael-0lpOSWjHK34/api/enrichment-b2b-linkedin-crunchbase-datagma) — `technologies` (partial) |
| `integration_categories` | Integration categories | LLM extraction | `llm_extractor.py` | **5%** non-empty | `apify/website-content-crawler` → LLM | No structured source |
| `integration_taxonomy` | Taxonomy (jsonb) | LLM extraction | `llm_extractor.py` | **5%** non-empty | `apify/website-content-crawler` → LLM | No structured source |
| `soc2` | SOC2 boolean | LLM extraction | `llm_extractor.py` | **44%** | `apify/website-content-crawler` — detect "SOC 2" mentions | No structured source |
| `compliance` | Cert strings | LLM extraction | `llm_extractor.py` | **3%** non-empty | `apify/website-content-crawler` → LLM | No structured source |
| `contact_email` | Primary contact email | LLM extraction | `llm_extractor.py` | **2%** | `apify/website-content-crawler` — `mailto:` extraction | [Datagma](https://rapidapi.com/raphael-0lpOSWjHK34/api/enrichment-b2b-linkedin-crunchbase-datagma) — work email |
| `contact_emails` | All contact emails | LLM extraction | `llm_extractor.py` | **2%** non-empty | `apify/website-content-crawler` — all `mailto:` links | No bulk source |
| `contact_page_url` | Contact page URL | LLM extraction | `llm_extractor.py` | **3%** | `apify/website-content-crawler` — `/contact` link detection | No structured source |
| `phone_numbers` | Phone numbers | LLM extraction | `llm_extractor.py` | **0%** non-empty | `apify/website-content-crawler` — regex phone extraction | [Datagma](https://rapidapi.com/raphael-0lpOSWjHK34/api/enrichment-b2b-linkedin-crunchbase-datagma) — `phoneNumber` |
| `demo_url` | Demo/booking URL | LLM extraction | `llm_extractor.py` | **3%** | `apify/website-content-crawler` — "request demo" link | No structured source |
| `help_center_url` | Help center URL | LLM extraction | `llm_extractor.py` | **3%** | `apify/website-content-crawler` — `/help` link | No structured source |
| `support_url` | Support portal URL | LLM extraction | `llm_extractor.py` | **4%** | `apify/website-content-crawler` — `/support` link | No structured source |
| `about_url` | About page URL | LLM extraction | `llm_extractor.py` | **5%** | `apify/website-content-crawler` — `/about` link | No structured source |
| `team_url` | Team page URL | LLM extraction | `llm_extractor.py` | **3%** | `apify/website-content-crawler` — `/team` link | No structured source |
| `developer_docs_url` | Dev docs URL | LLM extraction | `llm_extractor.py` | **3%** | `apify/website-content-crawler` — `/docs` `/api` link | No structured source |
| `youtube_channel_url` | YouTube channel | Not built | — | **0%** | `apify/website-content-crawler` — extract `youtube.com/@` links | [linkedin-data-api.p.rapidapi.com](https://rapidapi.com/rockapis-rockapis-default/api/linkedin-data-api) — social links |
| `g2_url` | G2 profile URL | G2 Data API via n8n | `csp-g2-enrichment` workflow | **17%** (20/119) | [apify/0x33/g2-scraper](https://apify.com) — Google search `site:g2.com {name}` | [g2-data-api.p.rapidapi.com](https://rapidapi.com/Chetan11-dev/api/g2-data-api) ✅ Already live |
| `g2_rating` | G2 star rating | G2 Data API via n8n | `csp-g2-enrichment` workflow | **17%** | Apify G2 scraper | [g2-data-api.p.rapidapi.com](https://rapidapi.com/Chetan11-dev/api/g2-data-api) ✅ Already live |
| `g2_review_count` | G2 review count | G2 Data API via n8n | `csp-g2-enrichment` workflow | **17%** | Apify G2 scraper | [g2-data-api.p.rapidapi.com](https://rapidapi.com/Chetan11-dev/api/g2-data-api) ✅ Already live |
| `g2_market_segment` | SMB/Mid-Market/Enterprise | Not built (field exists) | — | **0%** | Apify G2 scraper | [g2-data-api.p.rapidapi.com](https://rapidapi.com/Chetan11-dev/api/g2-data-api) |
| `g2_categories` | G2 category tags | G2 Data API via n8n | `csp-g2-enrichment` workflow | **17%** non-empty | Apify G2 scraper | [g2-data-api.p.rapidapi.com](https://rapidapi.com/Chetan11-dev/api/g2-data-api) ✅ Already live |
| `directory_fit` | high/medium/low | LLM + operator decision | `llm_extractor.py` + admin | **84%** | N/A — editorial | N/A — editorial |
| `directory_category` | cs_core / cs_adjacent / etc. | LLM + operator decision | `llm_extractor.py` + admin | **84%** | N/A — editorial | N/A — editorial |
| `include_in_directory` | Boolean | LLM + operator decision | `llm_extractor.py` + admin | **84%** | N/A — editorial | N/A — editorial |
| `confidence` | low/medium/high | LLM extraction | `llm_extractor.py` | **84%** | N/A — LLM signal | N/A |
| `external_enrichment` | Raw enrichment data | G2 + Tracxn payloads | `csp-g2-enrichment` / `tracxn_enricher.py` | **19%** | N/A — container field | N/A |

---

## Priority Fix List (by impact × fill rate gap)

| Priority | Field(s) | Gap | Root Cause | Fix |
|---|---|---|---|---|
| 🔴 Critical | `integrations`, `customers`, `value_statements`, `products`, `leadership`, `icp_buyer` | 94–100% empty | LLM extracts but pipeline not writing to Supabase or crawl too shallow | Fix LLM persistence + multi-page crawl (M74) |
| 🔴 Critical | `funding_stage`, `total_funding` | 100% empty | Tracxn broken | M74/M75: Crunchbase scraper OR Datagma |
| 🔴 Critical | `ceo_name`, `ceo_linkedin` | 97–100% empty | No pipeline | M75: LinkedIn Company Scraper |
| 🟠 High | `g2_url/rating/count` | 83% empty | Pipeline exists but only ran on 20 vendors | Run G2 pipeline against all 99 remaining vendors |
| 🟠 High | `hq_address` | 67% empty | Tracxn broken | M75: LinkedIn/Datagma |
| 🟡 Medium | `free_trial` | 64% empty | LLM extraction unreliable | Improve WCC crawl → pricing page |
| 🟡 Medium | `demo_url`, `help_center_url`, `support_url` | 95–97% empty | LLM not extracting consistently | WCC crawl + deterministic URL detection |
| 🟢 Low | `youtube_channel_url` | 100% empty | No pipeline | WCC extract `youtube.com` links from site |
| 🟢 Low | `has_public_pricing_page` | 100% empty | No pipeline | WCC — check `/pricing` URL |

---

## Recommended Single-Subscription Decision

| Scenario | Platform | Reasoning |
|---|---|---|
| **Best overall coverage** | Apify + RapidAPI (but one account each) | Apify for site crawl (irreplaceable) · Datagma or Apollo on RapidAPI for firmographics. RapidAPI unified billing: G2 + Crunchbase + LinkedIn + BlitzAPI all under one account/key. |
| **If truly one subscription** | **Apify** | WCC covers all product/content fields (irreplaceable) · Crunchbase scraper covers funding/founding · LinkedIn Company Scraper covers CEO/HQ. G2 API lost (can scrape instead). |
| **Recommended minimum** | Apify (active) + Crunchbase free tier on RapidAPI | Crunchbase free tier costs $0 — no subscription required. BlitzAPI adds 100 free credits/mo. Datagma adds firmographic depth at $39/mo if needed. |
| **If RapidAPI only** | Not viable | No site crawl capability → loses 30+ product/content fields permanently |

---

## Apify Actor Reference (Updated from Research)

| Actor | Apify URL | Key Fields Covered | Estimated Cost |
|---|---|---|---|
| Website Content Crawler | [apify/website-content-crawler](https://apify.com/apify/website-content-crawler) | mission, usp, pricing, use_cases, integrations, URLs, contact_email, compliance, testimonials, blog_posts | ~$0.004/page |
| RAG Web Browser | [apify/rag-web-browser](https://apify.com/apify/rag-web-browser) | Same as WCC, lighter/faster | ~$0.001/page |
| **Multi-Provider Lead Enricher** ⭐ | [alizarin_refrigerator-owner/lead-enricher](https://apify.com/alizarin_refrigerator-owner/lead-enricher) | Queries Apollo, Clearbit, ZoomInfo, Hunter, Lusha, FullContact, RocketReach, PDL — auto-fallback across all | Varies per provider |
| Crunchbase Scraper 104 Fields | [0x33/crunchbase-company-scraper](https://apify.com/0x33/crunchbase-company-scraper) | founded, funding_stage, total_funding, ceo_name, investors, acquisitions | ~$0.001/company |
| LinkedIn Bulk Scraper | [bebity/linkedin-premium-actor](https://apify.com/bebity/linkedin-premium-actor) | hq_address, company_size, founded, executives | Varies |
| LinkedIn Company Scraper (900+ fields) | [data-slayer/linkedin-company-scraper](https://apify.com/data-slayer/linkedin-company-scraper) | ceo_name, ceo_linkedin, hq_address, company_size, funding | ~$0.005/company |
| **SaaS Pricing Scraper** ⭐ | [datahq/saas-pricing-scraper](https://apify.com/datahq/saas-pricing-scraper) | pricing tiers, plan names, features, free_trial, has_public_pricing_page | Varies |
| G2 Reviews Scraper | [zen-studio/g2-reviews-scraper](https://apify.com/zen-studio/g2-reviews-scraper) | g2_rating, g2_review_count, testimonials | ~$0.007/company |
| G2 Product Scraper | [omkar-cloud/g2-product-scraper](https://apify.com/omkar-cloud/g2-product-scraper) | g2_rating, g2_categories, descriptions | Varies |
| Hunter.io Alternative | [consummate_mandala/hunter-io-alternative](https://apify.com/consummate_mandala/hunter-io-alternative) | contact_email, contact_emails | ~$0.003/email |
| Website Contact Scraper | [consummate_mandala/website-contact-scraper](https://apify.com/consummate_mandala/website-contact-scraper) | contact_email, phone_numbers | ~$0.005/company |
| BuiltWith Scraper | [supreme_coder/builtwith-scraper](https://apify.com/supreme_coder/builtwith-scraper) | integrations (tech stack), integration_categories | Varies |
| YouTube Channel Scraper | [streamers/youtube-channel-scraper](https://apify.com/streamers/youtube-channel-scraper) | youtube_channel_url, channel stats | Pay-per-result |
| Google Search Scraper | [apify/google-search-scraper](https://apify.com/apify/google-search-scraper) | vendor discovery, g2_url lookup | ~$0.0004/result |

## RapidAPI Reference

> **Billing note:** RapidAPI unified billing — one account, one API key covers all APIs. Subscribing to multiple APIs does NOT require separate accounts or keys. This changes the calculus on "one subscription" decisions — G2 + Crunchbase + Datagma + LinkedIn can all be accessed via the same key.

| API | RapidAPI URL | Key Fields Covered | Cost |
|---|---|---|---|
| **Datagma** ⭐ | [enrichment-b2b-linkedin-crunchbase-datagma](https://rapidapi.com/raphael-0lpOSWjHK34/api/enrichment-b2b-linkedin-crunchbase-datagma) | founded, hq_address, funding_stage, total_funding, ceo_name, company_size, revenue — single domain call covers 65+ firmographic fields | $39–209/mo flat |
| **Crunchbase (Official)** ⭐ | [crunchbase-team1-crunchbase](https://rapidapi.com/crunchbase-team1-crunchbase/api/crunchbase4) | founded, funding_stage, total_funding, investors, acquisitions, headquarters | **Free Basic tier** available — no cost for low-volume use |
| **Apollo Enrichment API** | [apollo2](https://rapidapi.com/apollo-io-apollo-io-default/api/apollo2) | 65+ fields: ceo_name, company_size, founded, hq_address, funding_stage, revenue, technologies, social links | Pay-per-enrichment, freemium |
| **BlitzAPI** | [blitzapi](https://rapidapi.com/blitz-data-blitz-data-default/api/blitzapi) | ceo_name, company size, founded, funding, technologies, contact emails | 100 free credits/month · **n8n native integration** available |
| LinkedIn Data API | [linkedin-data-api](https://rapidapi.com/rockapis-rockapis-default/api/linkedin-data-api) | ceo_name, ceo_linkedin, executives, company profile, social links | Subscribe needed on RapidAPI |
| G2 Data API | [g2-data-api](https://rapidapi.com/Chetan11-dev/api/g2-data-api) | g2_url, g2_rating, g2_review_count, g2_market_segment, g2_categories | ✅ Already live |

**Note:** Clearbit free tier was killed April 2025 — no longer viable as a free firmographic source.

---

## ⭐ Key New Finding: Multi-Provider Lead Enricher

[alizarin_refrigerator-owner/lead-enricher](https://apify.com/alizarin_refrigerator-owner/lead-enricher) queries **10 providers in one actor** with automatic fallback:

Apollo → Clearbit → ZoomInfo → IPinfo → FullContact → Hunter → Lusha → Snov → RocketReach → People Data Labs

This could replace the need for a separate Datagma/LinkedIn subscription for firmographics. **Needs evaluation** against our specific fields before committing to M75 approach.

