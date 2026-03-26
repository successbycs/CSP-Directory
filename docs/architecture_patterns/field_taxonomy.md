# Field Taxonomy Architecture

This document defines the three-tier naming convention for all columns in the `cs_vendors` table and any derivative data structures (dataclasses, export payloads, API responses).

---

## Tiers at a glance

| Tier | Prefix | Example columns | Who writes it | Survives re-enrichment? |
|------|--------|-----------------|---------------|------------------------|
| Scraped | `scraped_` | `scraped_pricing`, `scraped_founded` | Deterministic HTML extraction — no LLM | Yes — overwritten each run |
| LLM-inferred | `llm_` | `llm_directory_fit`, `llm_directory_category`, `llm_include_in_directory` | LLM pipeline pass | Yes — overwritten each run |
| Operator | _(no prefix)_ | `directory_fit`, `directory_category`, `include_in_directory` | Operator via admin UI or manual SQL | **Never overwritten by automation** |

---

## Tier 1 — `scraped_` prefix

Values that are deterministically extracted from raw HTML **without any LLM call**.  Examples include:

- `scraped_pricing` — pricing text scraped from structured HTML, JSON-LD, or OG tags.
- `scraped_founded` — founding year from JSON-LD `foundingDate` or visible page text.
- `scraped_description` — raw meta description from `<meta name="description">`.

**Rules:**
- Written on every enrichment pass; old values are overwritten.
- Never treated as a source of truth for public directory fields.
- Used as inputs to the LLM tier or as fallback display values.

---

## Tier 2 — `llm_` prefix

Values that the LLM pipeline infers from page content.  Replaces the former `auto_` prefix (renamed in M59).

Current columns:

| Column | Type | Description |
|--------|------|-------------|
| `llm_directory_fit` | `TEXT` | Fit score inferred by LLM: `high`, `medium`, `low` |
| `llm_directory_category` | `TEXT` | Directory category inferred by LLM: `cs_core`, `cs_adjacent`, etc. |
| `llm_include_in_directory` | `BOOLEAN` | Whether LLM recommends inclusion |

**Rules:**
- Written on every enrichment pass; old values are overwritten.
- **Never copied into operator-tier columns** unless the operator tier is empty and no manual override exists.
- Used by the admin UI to show "LLM suggestion" alongside operator decisions.
- `directory_decision_source` records whether the operator tier was set by `auto` (LLM suggestion accepted) or `admin_override`.

---

## Tier 3 — Operator tier (no prefix)

Values set manually by the operator — either via the admin UI, a migration script, or direct SQL.

Current columns:

| Column | Type | Description |
|--------|------|-------------|
| `directory_fit` | `TEXT` | Operator-confirmed fit: `high`, `medium`, `low` |
| `directory_category` | `TEXT` | Operator-confirmed category |
| `include_in_directory` | `BOOLEAN` | Final public directory inclusion gate |
| `directory_decision_source` | `TEXT` | `auto` or `admin_override` |
| `directory_reasoning` | `TEXT[]` | Reasoning notes captured at classification time |

**Rules:**
- **Never overwritten by LLM or scraped tiers.**  Safe-upsert code must check `directory_decision_source` before writing operator fields.
- When `directory_decision_source = 'admin_override'`, the pipeline skips all writes to `directory_fit`, `directory_category`, and `include_in_directory`.
- When `directory_decision_source = 'auto'` (or NULL), the pipeline may update operator columns using LLM suggestions — but this is an explicit promotion step, not an implicit overwrite.

---

## Safe-upsert rule

```python
# NEVER write operator-tier columns with llm_ values directly.
# The correct pattern:
if record.get("directory_decision_source") != "admin_override":
    upsert_payload["directory_fit"] = llm_directory_fit
    upsert_payload["directory_category"] = llm_directory_category
    upsert_payload["include_in_directory"] = llm_include_in_directory
    upsert_payload["directory_decision_source"] = "auto"

# Always write llm_ columns regardless of operator overrides:
upsert_payload["llm_directory_fit"] = llm_directory_fit
upsert_payload["llm_directory_category"] = llm_directory_category
upsert_payload["llm_include_in_directory"] = llm_include_in_directory
```

---

## Column naming convention

| Pattern | Meaning |
|---------|---------|
| `scraped_<field>` | Deterministic extraction from HTML — no model inference |
| `llm_<field>` | LLM inference result — may change on re-run |
| `<field>` (no prefix) | Operator-owned — survives all re-enrichment runs |

---

## Dual-write migration sequence for future renames

When renaming an existing column (e.g. `auto_X` → `llm_X`):

1. **Add new column** via `ALTER TABLE … ADD COLUMN IF NOT EXISTS llm_X …`
2. **Backfill** from old column: `UPDATE … SET llm_X = auto_X WHERE llm_X IS NULL`
3. **Deploy code** that writes to both `auto_X` (backward compat) and `llm_X` (new name) — dual-write window.
4. **Verify** all readers use the new column name.
5. **Remove dual-write** — drop the old column write path from code.
6. **Drop old column** only after all consumers are confirmed migrated.

This ensures zero-downtime renames with no data loss during the transition window.

### M59 migration (auto_ → llm_)

The M59 migration applied this sequence for all three `auto_` columns:

```sql
-- Step 1+2: Add new columns and backfill from old
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS llm_directory_fit TEXT;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS llm_directory_category TEXT;
ALTER TABLE public.cs_vendors ADD COLUMN IF NOT EXISTS llm_include_in_directory BOOLEAN;

UPDATE public.cs_vendors SET
    llm_directory_fit = auto_directory_fit,
    llm_directory_category = auto_directory_category,
    llm_include_in_directory = auto_include_in_directory
WHERE llm_directory_fit IS NULL;

-- Note: auto_ columns retained for backward compatibility.
-- Drop after verifying all code reads from llm_ columns.
```

Code writes both `auto_X` and `llm_X` during the transition window (not yet — see pending_migration.sql).  Once the migration is applied and verified, the `auto_X` write paths will be removed.

---

## History

| Milestone | Change |
|-----------|--------|
| M36 | Added `auto_directory_fit`, `auto_directory_category`, `auto_include_in_directory` columns |
| M59 | Renamed `auto_` → `llm_` via dual-write migration; documented three-tier taxonomy |
