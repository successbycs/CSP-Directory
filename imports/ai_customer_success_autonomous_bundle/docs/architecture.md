# Architecture

## Overview
The system uses a two-phase crawl architecture.

Phase 1: Discovery
- Run configured search queries
- Normalize and filter candidate domains
- Persist discovery candidates and statuses

Phase 2: Enrichment
- Fetch vendor homepage
- Explore key internal pages
- Extract deterministic signals
- Optionally enrich with LLM
- Merge results
- Score directory relevance
- Persist vendor profiles
- Export directory dataset and ops views

## Flow
Discovery Query Set
→ Search Results
→ Candidate Filtering
→ Candidate Persistence
→ Queued for Enrichment
→ Homepage Fetch
→ Site Exploration
→ Page Text Extraction
→ Deterministic Extraction
→ Optional LLM Enrichment
→ Merge Results
→ Directory Relevance Scoring
→ Vendor Profile Persistence
→ Google Sheets Export
→ Directory Dataset Export
→ Static Public Directory

## Layers
### Config
- `config/pipeline_config.json`
- Single configuration surface for manual and scheduled runs

### Discovery
- `services/discovery/*`
- Search adapters, normalization, filtering, candidate persistence

### Enrichment
- `services/enrichment/*`
- Homepage fetch, site exploration, bounded page crawling

### Extraction
- `services/extraction/*`
- Deterministic extraction baseline
- Optional LLM enrichment
- Merge logic
- Directory relevance scoring
- Vendor profile builder

### Persistence
- `services/persistence/*`
- Supabase storage for candidates, vendors, and run-level data

### Export
- `services/export/*`
- Google Sheets export
- Static directory dataset export

### Admin / Ops
- `services/admin/*`
- Thin read-only API and limited admin actions

### Frontend
- `docs/website/*`
- Static listing page, vendor page, admin dashboard

## Source of truth
- Supabase is the canonical store for vendor data
- Google Sheets is an operator-facing export layer
- `outputs/` contains local artifacts and snapshots, not canonical truth

## Runtime model
- Local development via VS Code + WSL
- Reproducible runtime via Docker / devcontainer
- Manual and scheduled runs must use the same config surface
