# FX Rates Mechanism V1

This document is the **single source of truth** for how Project 3 stores, validates, and consumes FX rates.

## Why we track FX this way

Operational reality:

- Supplier payments are funded via: **KZT → USDT (Binance P2P) → CNY (exchangers/BestChange) → supplier WeChat**.
- Freight / logistics payments are effectively **USD-denominated**.

System goal:

- Make **landed-cost**, **budget**, and **PO sizing** calculations deterministic and auditable.
- Avoid silent fallbacks that can burn capital (wrong FX = wrong ROIC).

Non-goals (for now):

- No web scraping inside the engine. FX inputs are **manual/external** today.
- No financial advice. This is internal bookkeeping + automation.

---

## Canonical storage: `dim_fx_rates`

We store **one canonical rate row per day** (local Almaty date). If we later ingest multiple providers, we still keep **one chosen/canonical** row per day in this table.

### Schema (SQLite)

`db/schema.sql` defines:

```sql
CREATE TABLE IF NOT EXISTS dim_fx_rates (
    effective_date TEXT PRIMARY KEY,         -- Local date (Asia/Almaty), YYYY-MM-DD
    -- Supplier funding path: KZT -> USDT -> CNY
    usdt_kzt REAL NOT NULL,                  -- KZT per 1 USDT (Binance P2P reference)
    usdt_cny REAL NOT NULL,                  -- CNY per 1 USDT (exchanger/BestChange reference)
    cny_kzt REAL NOT NULL,                   -- KZT per 1 CNY (derived: usdt_kzt / usdt_cny)
    -- Freight / logistics payments
    usd_kzt REAL NOT NULL,                   -- KZT per 1 USD (freight payments)
    dlv_rate_usd_kg REAL NOT NULL,           -- Delivery rate USD per kg
    -- Provenance
    provider TEXT NOT NULL DEFAULT 'MANUAL',
    source TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);
```

### Field definitions

- `effective_date` — **Almaty local date** (YYYY-MM-DD). This is what the pipeline uses to decide which row applies.
- `usdt_kzt` — how many KZT you pay for **1 USDT** (Binance P2P reference).
- `usdt_cny` — how many CNY you get for **1 USDT** via exchanger/BestChange.
- `cny_kzt` — derived conversion **KZT per 1 CNY**:
  - default rule: `cny_kzt = usdt_kzt / usdt_cny`
  - we **store** it for auditability + fast downstream use.
- `usd_kzt` — KZT per 1 USD used for freight payments.
- `dlv_rate_usd_kg` — delivery cost in USD per kg.
- `provider` — provenance label (`MANUAL`, `API:<name>`, `IMPORT`, ...).
- `source` — free-text notes (e.g., “Binance P2P median-bottom + BestChange + Google”).

---

## Read path (how the system uses FX each run)

Single read interface:

- `core/config/business_params.py:get_fx_rates(as_of_date=...)`

Semantics:

1. **Requested date** defaults to “today in Asia/Almaty”.
2. The system selects the most recent row where `effective_date <= as_of_date`.
3. If the row is older than today, this is treated as **stale FX**:
   - The pipeline continues.
   - Validation and Telegram outputs should surface the staleness.
4. If **no usable row exists** (table missing/empty, or only future-dated rows): **fail fast**.

---

## Write path (how rates get inserted/updated)

Canonical writer:

- `scripts/upsert_fx_rates.py`

Properties:

- **Idempotent**: uses `INSERT OR REPLACE` keyed on `effective_date`.
- Computes `cny_kzt` automatically if not provided.
- Defends against typos with sanity checks (use `--force` to override).
- Can add missing columns if the DB is behind (explicit migration inside the script).

### Example daily update

```bash
# Example values — replace with today’s observed rates
python scripts/upsert_fx_rates.py \
  --effective-date 2025-12-27 \
  --usdt-kzt 510 \
  --usdt-cny 6.813 \
  --usd-kzt 514 \
  --dlv-rate-usd-kg 2.66 \
  --provider MANUAL \
  --source "Binance P2P (median-bottom) + BestChange + Google"
```

---

## Validation (what fails hard vs what only surfaces)

Validation script:

- `scripts/validate_params.py --strict`

### Hard failures (exit code 1)

- `dim_fx_rates` table missing.
- Schema missing required columns.
- No rows in `dim_fx_rates`.
- No row with `effective_date <= run_date` (future-only data).
- Any non-positive FX numbers.

### Soft signals (should NOT block the pipeline)

- **Stale FX**: latest usable row is older than today.
  - This is surfaced as info (and should be visible in Telegram digest / logs).

---

## How FX flows into downstream calculations

The PO engine uses FX for landed cost estimation:

- Supplier cost: `base_cost_cny * cny_kzt`
- Freight cost: `weight_kg * dlv_rate_usd_kg * usd_kzt`

Key consumers (non-exhaustive):

- `core/automation/po_generator.py` (uses `get_fx_rates()`)
- Any landed-cost / ROIC calculations that need CNY→KZT or USD→KZT conversions

Rule: **No module should directly query `dim_fx_rates`**. Always go through `get_fx_rates()`.

---

## Upgrade path: API-based FX syncing (no re-architecture)

When we add an API provider later:

1. Implement a provider module (e.g., `core/fx/providers/<provider>.py`) with a function:
   - `fetch_fx_rates(as_of_date) -> FXRatesInput`
2. Create a sync script (e.g., `scripts/sync_fx_rates.py`) that:
   - fetches from provider
   - calls the same upsert logic (either via `scripts/upsert_fx_rates.py` internals or by importing `core/config/business_params.py`)
3. Store provenance:
   - `provider = "API:<provider>"`
   - `source = "<provider details>"`

`dim_fx_rates` remains the canonical daily row: consumers don’t change.

---

## Operational notes (context, not code)

These are business process constraints that **inform** why FX must be explicit and auditable:

- USDT transfers must use **TRC-20** network (wrong network can lose funds).
- Risk rule: do not send more than **5,000 CNY per transfer** with a single exchanger.

The FX mechanism does not execute payments — it only provides consistent accounting inputs.

---

## Reusable Opus prompt (for future sessions)

Copy-paste this into Opus/Claude when you want FX work extended without drifting docs:

```text
You are working on Project 3 (Autonomous Inventory/PO). Follow protocol:
1) Read .claude/TASKS.md (claim next task)
2) Read .claude/DECISIONS.md (avoid re-deciding)
3) Read .claude/ISSUES.md (don’t repeat mistakes)

Goal: maintain the single FX source-of-truth in docs/protocol/FX_RATES_MECHANISM_V1.md. Do NOT create additional FX docs.

Tasks:
- Ensure dim_fx_rates schema matches db/schema.sql.
- Ensure scripts/upsert_fx_rates.py is idempotent and defends against nonsense inputs.
- Ensure scripts/validate_params.py --strict passes when FX exists, and fails with an actionable message when it doesn’t.
- Ensure core/config/business_params.py:get_fx_rates() is the only reader used by downstream modules.

Steps:
1) Run: python scripts/validate_params.py --strict
2) If FX missing: run scripts/upsert_fx_rates.py (compute cny_kzt if needed) and re-run validation.
3) Confirm stale-rate behavior: if today missing but older exists, pipeline continues and surfaces the effective_date.

Constraints: Python 3.11+, type hints, fail-fast, no hidden migrations inside validation, no scraping. Log any ambiguity (e.g., param naming) in .claude/ISSUES.md. Update .claude/SESSION_LOG.md with what changed.
```
