# Deployment Architecture Decision

**Date:** 2026-03-26
**Status:** Decided

---

## Context

CSP Directory needs to be publicly accessible at vendors.successbycs.com. The system has two distinct surfaces:

1. **Public directory** — static HTML/JS reading vendor JSON, plus a lead capture form
2. **Admin/pipeline** — enrichment pipeline, admin panel, n8n workflows, Supabase persistence

The admin surface does not need to be public-facing. Only the directory and lead capture need to be reachable by visitors.

---

## Decision

**Public site → Vercel static deployment**

- `docs/website/` is the deployment root
- `docs/website/data/directory_dataset.json` holds the vendor data, committed to the repo
- Vercel deploys on every git push — no server required
- `vercel.json` at project root sets `outputDirectory: docs/website`

**Lead capture → Vercel serverless function**

- `api/lead-capture.py` is a self-contained Python handler
- No imports from `services/` — all logic inlined to avoid runtime path issues
- Calls Supabase REST API directly via `urllib.request` (stdlib only, no extra dependencies)
- Requires `SUPABASE_URL` and `SUPABASE_KEY` set as Vercel environment variables

**Admin panel + pipeline + n8n → Docker on private laptop**

- Runs locally, not public-facing
- Admin API serves the admin panel at `http://127.0.0.1:8787`
- Pipeline enrichment, Apify calls, and Supabase writes all happen here

**Data update workflow**

```
Run pipeline (laptop)
  → Click Publish in admin panel (POST /admin/publish)
  → Writes outputs/directory_dataset.json + docs/website/data/directory_dataset.json
  → git commit + push
  → Vercel auto-deploys updated dataset
```

---

## Alternatives Considered

**Docker on public VPS (rejected)**
Would work but adds hosting cost, maintenance overhead, and requires securing the admin API. No benefit over Vercel static for the public surface.

**Single Docker deployment serving everything (rejected)**
The Dockerfile exists and the admin_api.py can serve static files, but this couples the public site availability to the pipeline host. Static Vercel is more reliable and free.

**Supabase as the primary data source for the directory (deferred)**
The directory could fetch vendor data directly from Supabase at runtime instead of using a committed JSON file. This would allow real-time updates without a git push. Deferred — current volume (50 vendors) doesn't justify the added complexity, and the git-push workflow gives an explicit review gate before publishing.

---

## Consequences

- To update live data, you must run the pipeline, click Publish, and push to git. There is no automatic sync.
- Lead capture is the only live API call from the public site. Everything else is static.
- The admin panel is never exposed publicly — access requires being on the same network as the Docker host.
- `docs/website/data/directory_dataset.json` is tracked in git. It will grow as the vendor count grows. At current size (50 vendors, ~48KB) this is not a concern.
