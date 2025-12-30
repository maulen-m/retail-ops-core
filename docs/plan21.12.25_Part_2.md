# plan21.12.25_Part_2.md

**Project:** Autonomous Inventory/PO System  
**Date:** 2025-12-21  
**Scope:** Part 2 (Post P0/P1) — move from “working dashboard + draft PO” → “safe daily autonomous loop with capital guardrails”  

---

## 0) Prime directive
Build the most efficient autonomous e-commerce system that **maximizes profit growth** while **protecting capital** from architectural and operational errors.

**Priority stack (never violate):**
1) Protect capital  
2) Build data (see clearly)  
3) Automate (reduce manual ops)  
4) Scale (growth last)

---

## 1) Where we are now (end of Part 1)
✅ **P0/P1 are complete**:
- DemandEstimator integrated and persisted to `fact_demand_estimates`
- Size allocation fallback fixed when `total_base_qty == 0` (demand-proportions fallback)
- Supplier blackout semantics fixed + tests
- Smoke tests added (fail fast on invariants)
- End-of-day orchestration script added (`run_end_of_day.py`)
- PO blackout scenario export script added (`export_po_scenario.py`)

**Result:** We have a stable “Sense → Think → Recommend” pipeline.

**Missing:** We are not yet at “Act autonomously with capital safety.”

---

## 2) Part 2 outcomes (what “done” means)

### 2.1 Reliability outcome
- End-of-day pipeline runs unattended **7 consecutive days** (20:30 Asia/Almaty) with:
  - `generate_po_dashboard_data.py` success
  - `smoke_test_dashboard.py` success
  - dashboard output updated
  - Telegram/WhatsApp/Email alert on failure (pick one existing channel)

### 2.2 Decision quality outcome
- **No silent demand suppression:** When `d_data << d_anchor`, system must either:
  - correctly infer stock suppression (and weight anchor higher), **or**
  - clearly flag the SKU as “real decline likely” (high availability score)

### 2.3 Capital protection outcome
- Every PO recommendation (dashboard + auto-PO draft) shows:
  - total COGS KZT
  - % of available capital
  - “new/untested SKU” cap status (20% rule)
  - ROIC action (ORDER_FULL / ORDER_WITH_FLAG / REVIEW_REQUIRED)
- Auto-PO draft generation must **block** or require explicit approval for:
  - ROIC < 10%
  - new SKU > 20% of capital
  - missing critical inputs (cost, weight, price)

### 2.4 Single-source-of-truth outcome
- No hardcoded business parameters in code:
  - VAT rate (3% → 4% on 2026-01-01)
  - FX rates
  - “demand overrides”

All must live in **DB/config with audit + effective dates**.

---

## 3) Workstreams and tasks

### P2-A — Parameter governance (NOW)
**Goal:** remove time-bombs (VAT/FX) and prevent silent drift.

**P2-A1 — VAT effective-date support (URGENT; Jan 1 is close)**
- Implement `get_vat_rate(as_of_date)` (or equivalent) used by all unit economics.
- Rules:
  - VAT = 0.03 through 2025-12-31
  - VAT = 0.04 starting 2026-01-01
- Update economics functions to accept/use `as_of_date` where needed.
- Add tests (boundary date 2025-12-31 vs 2026-01-01).

**P2-A2 — FX rates as data (not code)**
- Create table (recommended): `dim_fx_rates(effective_date, cny_kzt, usd_kzt, dlv_rate_usd_kg, updated_at, source)`.
- Add helper `get_fx_rates(as_of_date)`.
- Update:
  - `scripts/generate_po_dashboard_data.py`
  - `core/automation/po_generator.py`
  - any cost modules using fixed FX

Definition of done:
- No `FX_RATES = {...}` left in scripts (except as fallback default).

---

### P2-B — One PO engine (NOW)
**Goal:** dashboard and auto-PO must use the same math. Divergence is a capital-loss machine.

**P2-B1 — Converge PO logic (dashboard vs auto draft)**
- Create a shared “PO recommendation” module (recommended): `core/po/recommender.py`.
- Inputs:
  - latest `cutoff_date`
  - `fact_demand_estimates` (d_final, sigma_final, confidence, availability)
  - current + inbound stock (size-level)
  - master params (L,R,B,z,TV)
- Outputs:
  - SKU-level recommendation
  - size-level allocations
  - audit notes

- Update both:
  - `scripts/generate_po_dashboard_data.py`
  - `core/automation/po_generator.py`

…to call the shared module.

**P2-B2 — Use `sigma_final` and confidence in ordering**
- Ensure safety stock / ROP use volatility consistent with `sigma_final`.
- If `confidence` is LOW/ANCHOR_ONLY, enforce stricter approval:
  - downgrade to ORDER_WITH_FLAG or REVIEW_REQUIRED unless SKU is “strategic exception”.

Definition of done:
- For the same cutoff_date, dashboard and auto-PO draft produce **matching total qty per SKU** (tolerance: ±1 unit).

---

### P2-C — Demand/anchor governance (NEXT)
**Goal:** stop hardcoding reality into Python.

**P2-C1 — Replace hardcoded demand overrides**
- Remove `DEMAND_OVERRIDES = {...}` from code.
- Replace with DB-backed overrides:
  - Table: `dim_demand_overrides(sku_key, effective_date, d_override, reason, created_at)`
  - Join logic in dashboard + auto-PO.
- Overrides must be surfaced in output as `d_source = OVERRIDE` and show `reason`.

**P2-C2 — Anchor data lifecycle**
- Define how anchors are maintained:
  - either in DB (recommended), synced from the Excel reference file, or
  - explicitly versioned Excel input with a “last updated” stamp.

Definition of done:
- Updating a demand override requires **no code changes**.

---

### P2-D — Capital protection gates (NOW/NEXT)
**Goal:** prevent big irreversible mistakes.

**P2-D1 — Implement the 20% rule and PO budget caps**
- Add a “capital guard” module:
  - available capital input (config or DB)
  - compute PO_cost_kzt per SKU and per draft
  - classify SKU as “untested/new” (age < 90 days or low sales history)
- Rules:
  - Any untested SKU cannot exceed 20% of available capital
  - Any single PO draft cannot exceed a configurable % cap without approval

**P2-D2 — Explainable blocking**
If a line is blocked, record:
- `block_reason`
- `block_rule_id`
- suggested fix (e.g., “missing weight_kg” → “update dim_sku.weight_kg”)

Definition of done:
- System can’t generate an auto-PO that violates the 20% rule.

---

### P2-E — Ops monitoring + run history (NEXT)
**Goal:** “autonomous” means it runs, fails loudly, and is easy to debug.

**P2-E1 — Run history table + artifacts**
- Add `fact_runs` (run_id, started_at, finished_at, status, cutoff_date, outputs, error_summary).
- Each end-of-day run persists:
  - demand_diagnostics.csv
  - dashboard JSON
  - smoke test results

**P2-E2 — Alerts**
- On failure: alert with failure step + error summary + path to logs.
- On success: alert with headline KPIs (SKUs ordered, total COGS, top 5 POs by ROIC).

Definition of done:
- “What happened last night?” is answerable in 30 seconds from `fact_runs`.

---

## 4) Definition of done for Part 2
Part 2 is complete when:
1) VAT + FX are data-driven with effective dates
2) Demand overrides are data-driven (no code changes required)
3) Dashboard and auto-PO use the same recommendation engine
4) Capital guardrails block unsafe orders by default
5) End-of-day pipeline is stable for 7 days with run history + alerts

---

## 5) Rollback plan (capital protection)
- Keep manual PO workflow as fallback.
- If smoke tests fail or guardrails block too much, auto-PO remains “draft-only” (no sending).
- Any parameter table change must be versioned (effective_date) so rollback = insert older row.

---

## 6) Commands (current + new)

### Current (from Part 1)
```bash
# End-of-day orchestrator
python scripts/run_end_of_day.py

# Regenerate dashboard JSON
python scripts/generate_po_dashboard_data.py

# Smoke test validation
python scripts/smoke_test_dashboard.py

# Demand harness export
python scripts/report_demand_top_skus.py

# PO blackout scenario export
python scripts/export_po_scenario.py --all-pos

# Blackout tests
pytest tests/test_blackout.py -v
```

### New (Part 2 additions)
```bash
# Validate parameter tables exist + have effective rows
python scripts/validate_params.py

# Backfill / seed FX + VAT (one-time)
python scripts/seed_params.py
```

---

## 7) Notes for implementation
- Keep formula constants **L=21, R=10, B=14, z=1.65, TV=0.23** frozen.
- Prefer DB tables with `(effective_date, value)` over hardcoded constants.
- Any new automation that can spend money must be behind an explicit env guard, e.g. `ENABLE_PO_WRITE=1`.
- No duplicated business logic between dashboard and auto-PO (one engine).
