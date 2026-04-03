# M75 Implementation Plan — LinkedIn Company Enrichment via Apify n8n Pipeline

## Problem Statement

Tracxn is dead (see M74). No current source for `founded`, `hq_address`, `funding_stage`, `total_funding`, `ceo_name`, `company_size`.

**Lusha API**: Requires Enterprise plan (~$37k+/year) — not viable.
**Apollo.io API**: Requires Professional plan ($99+/month) — possible future fallback, not selected for M75.

**Selected approach**: Apify LinkedIn Company Scraper — scrapes public LinkedIn company pages, cookieless, ~$0.003–0.01/company. Returns 900+ fields including executives, founded, HQ, funding rounds, headcount.

---

## Recommended Apify Actor

**Primary:** `data-slayer/linkedin-company-scraper`
- Actively maintained (responses within 24h)
- 900+ data points per company
- Returns: description, industry, headcount, funding history, investors, office locations, executives
- Completely cookieless — LinkedIn account never touched

**Fallback:** `dev_fusion/linkedin-company-scraper`
- No cookies required, bulk-optimised
- Fewer fields than data-slayer but faster

---

## Flow

```
csp-linkedin-company-enrichment (n8n webhook)
  │
  ├─ Split Vendors (Code)
  │
  ├─ For each vendor:
  │    │
  │    ├─ Step 1: Find LinkedIn Company URL
  │    │    Option A: ceo_linkedin or stored linkedin_url already in cs_vendors → extract company slug
  │    │    Option B: Apify Google Search — query: "site:linkedin.com/company {vendor_name}"
  │    │              → take first linkedin.com/company/* result
  │    │    Option C: skip vendor if LinkedIn URL cannot be found (log miss)
  │    │
  │    ├─ Step 2: Scrape LinkedIn Company Page
  │    │    POST apify/data-slayer~linkedin-company-scraper
  │    │    input: { startUrls: [{ url: linkedin_company_url }] }
  │    │
  │    ├─ Step 3: Extract + Map Fields (Code)
  │    │    founded         ← data.foundedOn or data.founded
  │    │    hq_address      ← data.headquarter.{city, geographicArea, country} joined
  │    │    company_size    ← data.staffCount range (e.g. "51-200")
  │    │    funding_stage   ← data.funding.fundingRounds[-1].fundingType
  │    │    total_funding   ← sum(data.funding.fundingRounds[].moneyRaised) formatted "$XM"
  │    │    ceo_name        ← first executive with title matching /CEO|Founder|Co-Founder/i
  │    │    ceo_linkedin    ← LinkedIn profile URL of that executive
  │    │
  │    └─ Step 4: POST /admin/enrich-write (safe-upsert — skip already-populated fields)
  │
  └─ Respond { ok, enriched: N, missed: N, skipped: N }
```

---

## Input Schema

```json
{
  "vendors": [
    { "vendor_name": "Thematic", "website": "https://getthematic.com" }
  ],
  "apify_token": "..."
}
```

---

## Fields Mapped to cs_vendors

| Lusha Field (rejected) | LinkedIn Source | cs_vendors Column |
|---|---|---|
| `data.founded` | `company.foundedOn` | `founded` |
| `data.location` | `company.headquarter.city/region/country` | `hq_address` |
| `data.companySize` | `company.staffCount` | `company_size` *(new)* |
| `data.funding.rounds[-1].type` | `funding.fundingRounds[-1].fundingType` | `funding_stage` |
| `sum(funding.rounds[].amount)` | `sum(funding.fundingRounds[].moneyRaised)` | `total_funding` |
| N/A | first exec with CEO/Founder title | `ceo_name` |
| N/A | exec LinkedIn profile URL | `ceo_linkedin` |

---

## Schema Changes Required

### Supabase `cs_vendors`
```sql
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS company_size text;
```

### `VendorIntelligence` dataclass
```python
company_size: str = ""
```

### `admin_api.py`
Add `company_size` to `_SCALAR_FIELDS`.

---

## Python Service — `linkedin_company_enricher.py`

Located at `services/enrichment/linkedin_company_enricher.py`.

Mirrors the n8n workflow extraction logic for direct Python use (e.g. one-off backfill scripts). Callable independently of n8n.

Key functions:
- `find_linkedin_company_url(vendor_name, website) -> str | None`
- `scrape_linkedin_company(linkedin_url, apify_token) -> dict | None`
- `extract_enrichment_fields(scraped_data) -> dict`
- `enrich_vendor_batch(vendors, apify_token, supabase_client) -> EnrichmentRunResult`

---

## Safe-Upsert Rules

```python
# Only write fields currently null/empty in cs_vendors
fields_to_update = {}
if not existing.get("founded") and extracted.get("founded"):
    fields_to_update["founded"] = extracted["founded"]
if not existing.get("hq_address") and extracted.get("hq_address"):
    fields_to_update["hq_address"] = extracted["hq_address"]
# ... same pattern for all fields
```

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| LinkedIn URL not found | Log miss, skip vendor, continue batch |
| Apify actor 404/failed run | Log error, mark vendor as `linkedin_miss`, continue |
| Rate limit (429) | Exponential backoff, max 3 retries |
| `ceo_name` extraction fails | Leave field null — do not guess |
| Funding data absent | Leave `funding_stage`/`total_funding` null |

---

## ToS Note

Scraping public LinkedIn company pages is legally grey. Apify's LinkedIn actors scrape **public pages only** (no login, no cookies). LinkedIn's ToS prohibits automated scraping, but public company profile data is widely scraped for B2B enrichment. Risk is low for low-volume enrichment of a vendor directory. Do not scrape employee lists or personal profiles.

---

## Execution Order

1. Add `company_size` column to Supabase via `apply_schema_migration.py`
2. Update `VendorIntelligence` and `admin_api.py`
3. Build + deploy `csp-linkedin-company-enrichment` workflow
4. Write `linkedin_company_enricher.py`
5. Run backfill against `include_in_directory=true` vendors
6. Record proof: 20 vendors, before/after for all 6 fields

## Proof Artifact

`runs/proofs/M75_linkedin_enrichment.json` must contain:
- n8n workflow ID
- 20 vendor sample with before/after field values
- Miss rate (vendors where LinkedIn URL not found)
- Apify credits consumed per vendor
- Distribution of fields populated (how many got founded vs funding_stage etc.)
