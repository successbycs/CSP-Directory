# Product Design

## Product
AI Customer Success Vendor Intelligence is a system that discovers software vendors relevant to the Customer Success lifecycle, enriches them by exploring their websites, extracts structured intelligence, scores directory relevance, and publishes a directory-ready dataset for `directory.successbycs.com`.

## Primary users
- Customer Success leaders
- CS Ops / RevOps leaders
- Founders evaluating CS tooling
- Internal operators curating the directory

## Core outcomes
- Discover relevant vendors across the CS lifecycle
- Build trustworthy vendor profiles with evidence
- Maintain an internal ops layer for review and overrides
- Publish a static, browsable public directory

## Core entities
- Discovery Candidate
- Vendor Profile
- Directory Dataset Record
- Pipeline Run

## Canonical lifecycle stages
- Sign
- Onboard
- Activate
- Adopt
- Support
- Expand
- Renew
- Advocate

## Directory-ready vendor profile fields
- vendor_name
- website
- source
- mission
- usp
- icp
- use_cases
- lifecycle_stages
- pricing
- free_trial
- soc2
- founded
- case_studies
- customers
- value_statements
- confidence
- evidence_urls
- directory_fit
- directory_category
- include_in_directory

## Product boundaries for v1
In scope:
- Config-driven multi-query discovery
- Two-phase crawl: discovery and enrichment
- Deterministic extraction as baseline
- Optional Level 2 LLM enrichment
- Directory relevance scoring
- Supabase as source of truth
- Google Sheets as ops/export layer
- Static directory pages
- Thin admin API and dashboard
- Thin admin override actions

Out of scope for v1:
- Full auth system
- Full admin SPA
- Queue infrastructure
- Real-time search backend
- Billing / monetization
- Advanced analytics

## Acceptance criteria for a running product
The system should:
1. Run repeatedly from config without code edits
2. Persist discovery candidates and enriched vendor profiles
3. Produce a trustworthy directory dataset export
4. Provide operator visibility and simple override controls
5. Serve a public static directory from real data
6. Run consistently locally and in a container
