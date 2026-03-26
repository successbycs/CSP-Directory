# CSP Directory Runbook

Quick-reference commands for running and monitoring the pipeline.

---

## Start the admin panel

```bash
cd /home/chris/projects/CSP-Directory && source .venv/bin/activate && python3 -m services.admin.admin_api
```

Open `http://127.0.0.1:8787` in your browser.

---

## Restart the admin panel (pick up code changes)

The admin panel serves static files (including `admin.js`) directly from disk. If you've pulled new code or made local edits, the running process must be restarted to serve the updated files — a browser refresh alone is not enough.

```bash
pkill -f "services.admin.admin_api" && \
cd /home/chris/projects/CSP-Directory && \
source .venv/bin/activate && \
python3 -m services.admin.admin_api
```

Then hard-refresh the browser (`Ctrl+Shift+R` / `Cmd+Shift+R`).

**When to restart:**
- After pulling changes from GitHub that include `admin.js`, `admin.css`, or `admin.html`
- After any local edit to the admin UI files
- If buttons or features described in the docs are not appearing on the page

---

## Run the full pipeline (discover → enrich → health check → export)

```bash
cd /home/chris/projects/CSP-Directory && source .venv/bin/activate && python3 scripts/discover_vendors.py
```

**Flags:**
- `--skip-discover` — skip Google Search, go straight to enrich (use when vendors already exist)
- `--enrich-all` — re-enrich all vendors, not just new/unenriched ones
- `--dry-run` — print discovered candidates without writing to Supabase

Re-enrich all without discovering new vendors:
```bash
cd /home/chris/projects/CSP-Directory && source .venv/bin/activate && python3 scripts/discover_vendors.py --skip-discover --enrich-all
```

---

## Check vendor count

```bash
cd /home/chris/projects/CSP-Directory && source .venv/bin/activate && python3 -c "
from dotenv import load_dotenv; load_dotenv('.env')
import os
from supabase import create_client
client = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])
rows = client.table('cs_vendors').select('include_in_directory').execute().data
included = sum(1 for r in rows if r.get('include_in_directory') is True)
print(f'Total: {len(rows)} | Included: {included}')
"
```

---

## Run pipeline health check only

```bash
cd /home/chris/projects/CSP-Directory && source .venv/bin/activate && python3 scripts/pipeline_health_check.py
```

Exits 0 if all checks pass, 1 if violations found.

---

## Export directory dataset only

```bash
cd /home/chris/projects/CSP-Directory && source .venv/bin/activate && python3 scripts/export_directory_dataset.py
```

---

## Run the pipeline directly (with live logs) [legacy]

```bash
cd /home/chris/projects/CSP-Directory && \
source .venv/bin/activate && \
PYTHONUNBUFFERED=1 python3 scripts/run_pipeline.py --no-serve-preview 2>&1 | tee /tmp/csp_pipeline.log
```

---

## Run the AF autonomous cycle

```bash
cd /home/chris/projects/CSP-Directory && \
OPENAI_API_KEY=$(grep OPENAI_API_KEY .env | cut -d= -f2) \
AUTONOMOUS_AGENT_CLI="/home/chris/SuccessByCS-Builder/Autonomous-Framework/.venv/bin/python3 /home/chris/SuccessByCS-Builder/Autonomous-Framework/tools/agent_cli/router_cli.py --model auto" \
/home/chris/SuccessByCS-Builder/Autonomous-Framework/.venv/bin/python3 \
/home/chris/SuccessByCS-Builder/Autonomous-Framework/scripts/autonomous_controller.py \
--root /home/chris/projects/CSP-Directory run-cycle
```

---

## Check AF status

```bash
cd /home/chris/projects/CSP-Directory && \
/home/chris/SuccessByCS-Builder/Autonomous-Framework/.venv/bin/python3 \
/home/chris/SuccessByCS-Builder/Autonomous-Framework/scripts/autonomous_controller.py \
--root /home/chris/projects/CSP-Directory status
```

---

## Verify schema and health

```bash
cd /home/chris/projects/CSP-Directory && source .venv/bin/activate

# Check all Supabase tables and columns are present
python3 scripts/check_supabase.py

# Check for missing columns and apply if needed
python3 scripts/apply_schema_migration.py

# Full project audit
python3 scripts/autonomous_audit.py
```

---

## Clear stale AF context (when cycle gets stuck in repair loop)

1. Reset the stuck milestone in `milestone_registry.json` — change `"status": "in_progress"` → `"not_started"`
2. Remove stale repair entries from `runs/run_history.json`:

```bash
cd /home/chris/projects/CSP-Directory && python3 -c "
import json
with open('runs/run_history.json') as f:
    history = json.load(f)
milestone = 'M37'  # change to the stuck milestone
to_keep = [e for e in history if not (
    e.get('milestone') == milestone and
    e.get('role') in ('fixer_engineer',) and
    e.get('phase') in ('repair', 'fixer_engineer')
)]
print(f'Removed {len(history) - len(to_keep)} stale entries')
with open('runs/run_history.json', 'w') as f:
    json.dump(to_keep, f, indent=2)
"
```

3. Re-run the AF cycle.
