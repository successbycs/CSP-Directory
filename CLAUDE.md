# CSP Directory — Claude Instructions

## Architecture Source of Truth

**All development decisions must comply with `architecture.json` at the project root.**

Read `architecture.json` at the start of any session involving code changes. Do not implement anything that contradicts it. If a decision is not in `architecture.json`, clarify with the user before proceeding and update the file after agreement.

## Critical Rules (summary — full detail in architecture.json)

1. **n8n owns all third-party API calls.** Python scripts are batch orchestrators only — they query Supabase and POST to n8n webhooks. Never write Python that calls RapidAPI, Apify, LinkedIn etc. directly.

2. **LLM tier order: gpt-4o-mini first, Mistral (Ollama) fallback.** Never use gpt-4o as primary. Never use Mistral as primary — it hallucinates vendor-specific facts.

3. **RAG must be wired.** The design is: crawl → embed with nomic-embed-text → store in `vendor_page_embeddings` → retrieve relevant chunks per question → send to LLM. This is not optional and not yet fully implemented.

4. **Safe-upsert always.** Never overwrite existing non-null values in `cs_vendors` without explicit operator instruction.

5. **Frontend reads JSON, never Supabase.** The public directory dataset is `docs/website/data/directory_dataset.json`. Re-export after every enrichment cycle.

6. **Crawl tiers: cheapest first.** Tier 1 (HTTP, free) → Tier 2 (Apify RAG, ~$0.001) → Tier 3 (Apify WCC, ~$0.004). Escalate only on failure signal (word_count < 200).

7. **Update architecture.json before implementing new decisions.** Not after. The file is the contract.

## Project Context

- Product: CSP vendor directory at vendors.successbycs.com
- Stack: Python pipeline, n8n workflows, Supabase, Vercel static site
- Admin panel: localhost:8787 (services/admin/admin_api.py)
- 81 vendors currently in directory
- Milestone registry: milestone_registry.json

## Memory

Additional session context is in `/home/chris/.claude/projects/-home-chris-projects-CSP-Directory/memory/`.
