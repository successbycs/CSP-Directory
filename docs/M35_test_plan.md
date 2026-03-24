# M35 — Human Validation Test Plan

This is the operator test plan for M35. Run each step in order, record results in `runs/proofs/M35_human_validation.json`.

---

## Prerequisites

```bash
cd /home/chris/projects/CSP-Directory
source .venv/bin/activate   # or: python3 -m venv .venv && pip install -r requirements.txt
```

Confirm `.env` has `SUPABASE_URL`, `SUPABASE_KEY`, `OPENAI_API_KEY`, `APIFY_API_TOKEN` set.

---

## Step 1 — Supabase schema check

```bash
python3 scripts/check_supabase.py
```

**Record in proof:**
- Did it pass or fail?
- Any missing tables?
- Any missing columns? (Known expected failure: `ceo_name` drift)

---

## Step 2 — Pipeline run (small query, 3–5 vendors)

```bash
python3 scripts/run_pipeline.py "AI customer success platform" --no-serve-preview --pretty 2>&1 | tee /tmp/csp_pipeline_run.log
```

**Watch for and record:**
- Did discovery return vendor URLs? (Apify Google Search)
- Did enrichment fetch homepage content? (any HTTP errors / empty content?)
- Did LLM extraction run? (look for `llm_extractor` log lines)
- Did upsert succeed? (look for `upsert_vendor_result` log lines)
- Any exceptions or tracebacks?

---

## Step 3 — Check Supabase vendor records post-run

After the pipeline run, check what actually landed in Supabase. Run:

```bash
python3 - <<'EOF'
from pathlib import Path
import sys
sys.path.insert(0, str(Path('.').resolve()))
from dotenv import load_dotenv
load_dotenv('.env')
from services.persistence.supabase_client import get_supabase_client

client = get_supabase_client()
fields = ['website','name','mission','usp','pricing','lifecycle_stages','use_cases','icp_buyer','customers','case_studies','value_statements']
result = client.table('cs_vendors').select(','.join(fields)).order('last_updated', desc=True).limit(5).execute()
import json
print(json.dumps(result.data, indent=2))
EOF
```

**Record for each of the 5 most recent vendors:**
- Which of these fields are populated: `mission`, `usp`, `pricing`, `lifecycle_stages`, `use_cases`, `icp_buyer`
- Which are empty

---

## Step 4 — Check outputs/directory_dataset.json

```bash
python3 scripts/export_directory_dataset.py
python3 -c "import json; d=json.load(open('outputs/directory_dataset.json')); print(f'{len(d)} vendors in export'); print(json.dumps(d[:2], indent=2))"
```

**Record:**
- How many vendors in the export?
- Are `lifecycle_stages`, `use_cases`, `pricing` populated in the exported records?

---

## Step 5 — Discovery quality check (manual review)

From the pipeline log (`/tmp/csp_pipeline_run.log`), find the list of candidate URLs returned by discovery.

**Record:**
- How many candidates were returned?
- Are any obviously non-vendor? (blog posts, Reddit, review articles, error pages)
- Approximate ratio: real vendor domains vs noise

---

## Completing M35

Fill in `runs/proofs/M35_human_validation.json` with your findings from each step.
Mark each area as `pass`, `fail`, or `partial`.
Commit and push — this unlocks M36 for AF execution.

```bash
git add runs/proofs/M35_human_validation.json
git commit -m "M35: human validation proof"
git push
```
