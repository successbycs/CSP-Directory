# Vendor Schema

This document is the canonical definition of the vendor intelligence record. It defines every field, its purpose, the best source to populate it, and its confidence tier.

The live database schema is `supabase/core_persistence_schema.sql`. That file must stay in sync with this document.

---

## Identity

| Field | Type | Description | Best source | Confidence tier |
|---|---|---|---|---|
| `name` | text | Vendor/product name | Web scrape (homepage title) | Primary |
| `website` | text | Canonical root domain (dedup key) | URL acquisition | Primary |
| `source` | text | Which source first discovered this vendor | Source registry | — |
| `founded` | text | Year founded | Web scrape (about page), Crunchbase | Aggregator |
| `company_hq` | text | Headquarters location | Web scrape (about/contact page), Crunchbase | Aggregator |
| `confidence` | text | Overall record confidence (high/medium/low) | Derived | — |
| `first_seen` | date | Date first entered the directory | System | — |
| `last_updated` | timestamptz | Last enrichment run | System | — |

---

## Positioning

| Field | Type | Description | Best source | Confidence tier |
|---|---|---|---|---|
| `mission` | text | Company mission or tagline | Web scrape (homepage) | Primary |
| `usp` | text | Unique selling proposition | Web scrape (homepage hero) | Primary |
| `raw_description` | text | Raw text from discovery source (search snippet etc.) | URL acquisition | Lowest |
| `directory_fit` | text | Assessment of fit for this directory | LLM classification | Medium |
| `directory_category` | text | Primary category in the directory | LLM classification | Medium |
| `directory_reasoning` | text[] | Reasoning for directory fit decision | LLM classification | Medium |
| `include_in_directory` | boolean | Whether to show in public directory | Operator review or auto | — |
| `llm_directory_fit` | text | LLM-inferred fit (before operator review) | LLM classification | Medium |
| `llm_directory_category` | text | LLM-inferred category | LLM classification | Medium |
| `llm_include_in_directory` | boolean | LLM-recommended inclusion flag | LLM classification | Medium |
| `directory_decision_source` | text | Who made the include/exclude decision | System | — |

---

## Commercial

| Field | Type | Description | Best source | Confidence tier |
|---|---|---|---|---|
| `pricing` | text | Pricing model description | Web scrape (pricing page) | Primary |
| `free_trial` | boolean | Whether a free trial is available | Web scrape (pricing page) | Primary |
| `icp` | text[] | Ideal customer profile tags | LLM classification | Medium |
| `icp_buyer` | jsonb | Structured ICP buyer persona objects | LLM classification | Medium |

---

## Product

| Field | Type | Description | Best source | Confidence tier |
|---|---|---|---|---|
| `products` | jsonb | Product/module list with descriptions | Web scrape (product pages) | Primary |
| `use_cases` | text[] | Key use cases | Web scrape + LLM | Medium |
| `lifecycle_stages` | text[] | SuccessByCS 8-stage lifecycle tags | LLM classification | Medium |
| `integration_categories` | text[] | Categories of integrations (CRM, BI, etc.) | Web scrape (integrations page) | Primary |
| `integrations` | text[] | Named integration partners | Web scrape (integrations page) | Primary |
| `integration_taxonomy` | jsonb | Structured integration taxonomy | Web scrape + LLM | Medium |

---

## Social Proof

| Field | Type | Description | Best source | Confidence tier |
|---|---|---|---|---|
| `customers` | text[] | Named customer logos or references | Web scrape (customers page) | Primary |
| `case_studies` | text[] | Case study titles or URLs | Web scrape | Primary |
| `case_study_details` | jsonb | Structured case study objects | Web scrape + LLM | Medium |
| `testimonials` | jsonb | Testimonial objects | Web scrape | Primary |
| `value_statements` | text[] | Quantified value claims ("20% churn reduction") | Web scrape + LLM | Medium |
| `evidence_urls` | text[] | URLs that evidence the above claims | Web scrape | Primary |
| `support_signals` | text[] | Support tier indicators | Web scrape | Primary |

---

## Team

| Field | Type | Description | Best source | Confidence tier |
|---|---|---|---|---|
| `leadership` | jsonb | Leadership team objects (name, title, LinkedIn) | Web scrape (team page) | Primary |

---

## Contact and URLs

| Field | Type | Description | Best source | Confidence tier |
|---|---|---|---|---|
| `contact_email` | text | Primary contact email | Web scrape (contact page) | Primary |
| `contact_page_url` | text | Contact page URL | Web scrape | Primary |
| `demo_url` | text | Demo/trial booking URL | Web scrape (homepage/nav) | Primary |
| `help_center_url` | text | Help centre or knowledge base URL | Web scrape | Primary |
| `support_url` | text | Support portal URL | Web scrape | Primary |
| `about_url` | text | About page URL | Web scrape | Primary |
| `team_url` | text | Team page URL | Web scrape | Primary |
| `developer_docs_url` | text | Developer docs URL | Web scrape | Primary |
| `phone_numbers` | text[] | Contact phone numbers | Web scrape (contact page) | Primary |
| `contact_emails` | text[] | All discovered contact emails | Web scrape | Primary |

---

## External Enrichment

| Field | Type | Description | Best source | Confidence tier |
|---|---|---|---|---|
| `external_enrichment` | jsonb | Raw payloads from external enrichment sources (G2, Crunchbase etc.) | External sources | Aggregator |
| `blog_posts` | jsonb | Recent blog post metadata | Web scrape (blog) | Primary |
| `soc2` | boolean | SOC2 compliance flag | Web scrape (security/trust page) | Primary |
| `compliance` | text[] | Other compliance certifications | Web scrape | Primary |

---

## Schema Gaps and Known Issues

The following fields are in the schema but empty across all 81 current vendors, indicating an enrichment pipeline failure rather than missing data:

- `company_hq`, `founded`, `leadership`, `products`, `integrations`, `icp_buyer`, `customers`, `case_studies`, `value_statements`, `icp`

The following field exists in `core_persistence_schema.sql` but does not exist in the live Supabase database (schema drift):

- `ceo_name` — referenced in repo schema but not in live DB; either add it to the live DB or remove from the schema file

---

## Field Population Priority

When planning enrichment runs, populate fields in this order:

1. **Identity** — name, website, source (from URL acquisition)
2. **Positioning** — mission, usp, raw_description (from homepage scrape)
3. **Directory classification** — lifecycle_stages, directory_fit, directory_category (from LLM)
4. **Commercial** — pricing, free_trial, icp (from pricing page scrape + LLM)
5. **Product** — products, use_cases, integrations (from product/integrations pages)
6. **Social proof** — customers, case_studies, value_statements (from customers/case-study pages)
7. **Team** — leadership (from team page)
8. **Contact** — all URL fields (from site crawl)
