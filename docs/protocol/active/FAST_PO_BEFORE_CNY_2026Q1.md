# FAST_PO_BEFORE_CNY_2026Q1
Last updated: 2026-01-03

## 1) Objective (Non-negotiable)
We must generate a supplier-ready PO ASAP (CNY supplier cutoff pressure) while keeping:
- DB as the ONLY system of record (“truth”)
- Excel as UI input only (manual/ops convenience), never a dependency that can break the system
- Capital protection gates intact (ROIC gates, validation, audit)

## 2) Current Reality (as of 2026-01-03)
- End-of-day pipeline passes Steps 0–6.
- Audit now passes with effective-dated demand overrides applied.
- EOD fails at Step 7 due to ImportError:
  `cannot import name 'send_run_success_alert' from core.alerts.error_alerts`

Operational constraint:
- Shipping workflow requires MY_SIZE filled because clothing size determines SKU_ID.
- Today’s human-in-the-loop sizing still uses SALES_KSP_CRM_V3.xlsx.
- WhatsApp API automation is blocked by Meta business verification.

## 3) Time-Boxed Demand Override Policy (Line52 / Line51)
We will keep overrides until March 1, then revert to data.

Policy:
- LINE52 daily demand override: D = 50
- LINE51 daily demand override: D = 12
- Effective window: [2026-01-01, 2026-03-01)
  - Meaning: applies through 2026-02-28
  - On 2026-03-01, system automatically reverts to model/data

Implementation requirements:
- Overrides stored in DB (effective-dated)
- Idempotent seed/upsert script
- Audit gate:
  - Fails fast if required overrides are missing
  - Prints exact command to seed them
- Dashboard output must show override notes (e.g., `D_OVERRIDE=50`) so it’s never “silent”

## 4) Deadline Logic (why this is urgent)
Inputs:
- Supplier prep time estimate: ~20 days
- Supplier shutdown/cutoff: 2026-01-26 (ops constraint)

Implication:
- PO must be finalized and sent to supplier by ~2026-01-06 (latest safe date).

This is a capital-protection issue:
delays force either stockouts (lost profit) or rushed over-ordering (capital burn).

## 5) Plan — Track A: Make EOD GREEN (fastest ROI)
A1) Fix Step 7 alerts import (must not block pipeline)
- Restore `send_run_success_alert` (and any paired failure alert) in `core.alerts.error_alerts`
- Add env-guarded behavior:
  - If Telegram env missing → log + skip safely
- Add regression tests:
  - Import does not fail
  - Function is callable without Telegram configured

A2) Keep validation strict
- `validate_params.py --strict` must PASS
- FX must be seeded and not future-only
- Overrides must be active (Line52/Line51 visible in validation output)

A3) Run end-of-day green loop
- `python scripts/run_end_of_day.py --verbose`
- Capture outputs used for PO decision + operational dashboards

A4) Produce supplier-ready PO export
Outputs (minimum):
- CSV export with SKU_ID, MY_SIZE, qty, cost, weight
- Summary file with:
  - Total units
  - Total COGS (KZT)
  - Total weight (kg)
  - Top 10 spend SKUs
  - Explicit mention that LINE52/LINE51 are overridden (and until when)

## 6) Plan — Track B: Close the Sizing Bottleneck (stop bleeding time)
Problem (today):
- MY_SIZE assignment requires manual customer chat + manual entry into Excel.
- Excel files can be lost/corrupted; workflow becomes fragile.
- Pipeline depends on “a person did the spreadsheet correctly”.

Goal:
- Keep “manual input” possible, but move the write target to DB (not Excel).

B1) Interim solution (this week):
- Provide a DB-first “Sizing Queue” tool:
  - Lists orders missing MY_SIZE
  - Operator inputs HEIGHT/WEIGHT and/or MY_SIZE
  - System stores in DB
  - Optional export back to Excel for convenience (never required)

B2) WhatsApp API solution (once verified):
- Automated message to request HEIGHT/WEIGHT
- Webhook/ingestion stores customer params into DB
- Size engine assigns MY_SIZE automatically
- Excel CRM becomes optional/legacy

Target date to remove Excel dependency for sizing:
- “DB-first manual sizing tool” live: 2026-01-10
- “WhatsApp API automated capture” live (depends on verification): target 2026-02-10
- “Excel CRM not required for pipeline”: target 2026-03-01

## 7) Guardrails (do not relax)
- ROIC gate thresholds remain unchanged:
  - ≥20% ORDER_FULL
  - 10–20% ORDER_WITH_FLAG
  - <10% REVIEW_REQUIRED
- Size mix floor/cap stays enforced for clothing
- New SKU capital limit remains enforced (20% cap)

## 8) Definition of Done (for this sprint)
- EOD pipeline completes successfully with `--verbose` (no Step 7 crash)
- Demand overrides active and audited until 2026-03-01
- PO export produced + supplier-ready summary generated
- No Excel file is required as “truth”; DB is authoritative

## 9) Operator Checklist (single source of boring truth)
1) Seed FX (if needed) and seed overrides
2) `python scripts/validate_params.py --strict`
3) `python scripts/run_end_of_day.py --verbose`
4) Review exports: confirm LINE52 D=50 and LINE51 D=12 appear with override note
5) Send PO to supplier with attached CSV + summary
