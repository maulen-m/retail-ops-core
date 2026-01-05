# CLOSE_SIZING_BOTTLENECK_V2
Last updated: 2026-01-03

## 0) Executive Summary
We sell clothing where size == SKU_ID. That means **MY_SIZE is not optional** for shipping, waybill grouping, and accurate inventory math.
Today, MY_SIZE is still being assigned via a fragile Excel workflow (SALES_KSP_CRM_V3.xlsx) because WhatsApp API automation is blocked by Meta verification.

This document defines the **fastest, safest** path to:
1) Keep end-of-day pipeline green and generate supplier-ready POs immediately (CNY timing), and
2) Remove Excel as a single point of failure for sizing (DB-first sizing system).

## 1) Non-Negotiables (Capital Protection + Operational Safety)
1. DB is the ONLY system of record for: orders, measurements, size decisions, SKU assignment.
2. Excel is allowed only as an optional UI surface / operator convenience — never a critical dependency.
3. Shipping write operations must remain guarded by explicit ENABLE_KASPI_WRITE=1.
4. Idempotency everywhere: safe re-runs, deterministic outputs, no “double writes”.
5. Fail-fast with actionable messages (“run this exact command”).

## 2) Current Workflow (Reality Today)
### 2.1 What’s happening now
1) Orders come from Kaspi.
2) Orders are loaded into CRM workbook (SALES_KSP_CRM_V3.xlsx).
3) Operator collects height/weight from WhatsApp manually.
4) Operator writes MY_SIZE into Excel.
5) Shipping + waybill grouping scripts assume MY_SIZE is filled.
6) End-of-day pipeline uses the day’s data to produce PO outputs.

### 2.2 Why this is a bottleneck
- Daily human time sink (manual extraction + manual data entry).
- High error cost: wrong MY_SIZE => wrong SKU shipped => returns/refunds.
- Fragility: Excel files can be lost/corrupted or wiped by repo hygiene actions.
- “Exact-date” filters and missing sizing inputs cause frequent operational failures.

## 3) Time-Boxed Demand Override Policy (Line52 / Line51)
We will keep overrides until March 1, then revert to data automatically.

Policy:
- LINE52 daily demand override: D = 50
- LINE51 daily demand override: D = 12
- Effective window: [2026-01-01, 2026-03-01)
  - Applies through 2026-02-28
  - On 2026-03-01, system reverts to model/data

Requirements:
- Overrides stored in DB (effective-dated)
- Idempotent upsert/seed script
- Validation/audit fails fast if required overrides are missing, and prints exact seed command
- Dashboard output must emit explicit notes (example: D_OVERRIDE=50) so this can never be “silent”

## 4) Why this is urgent (CNY timing)
Inputs:
- Supplier prep time (estimate): 20 days
- Supplier shutdown / cutoff (ops constraint): 2026-01-26

Implication:
- PO must be finalized and sent by ~2026-01-06 (latest safe date)

If we miss the window:
- We get stockouts (lost profit) OR panic over-ordering (capital burn)

## 5) Target Architecture (What “Good” Looks Like)
### 5.1 DB tables (minimum viable)
- fact_orders_kaspi
  - order_id, store_code, phone, kaspi_status/state, planned_shipment_date, item lines
- fact_order_measurements
  - order_id, phone/customer_id, height_cm, weight_kg, source, captured_at
- fact_order_size_decisions
  - order_id, my_size, method, confidence, decided_at, decided_by
- dim_demand_overrides (effective-dated)
  - sku_key, d_override, start_date, end_date, reason

### 5.2 Services / Scripts (minimum viable)
A) Intake:
- Kaspi API sync -> DB orders (always)

B) Manual sizing (DB-first):
- “Sizing Queue” exporter: lists orders that need sizing (planned_ship_date <= today AND my_size is NULL)
- “Sizing Queue” importer: applies sizing decisions into DB with audit fields
- Optional: export back to Excel for operator comfort (never required)

C) Shipping:
- ship_orders reads DB orders + DB size decisions
- During migration only: allow CRM fallback, but DB wins if both exist

D) Waybills:
- download_waybills + build_daily_waybills select orders from DB first
- Grouping logic unchanged (don’t touch shipping semantics)

## 6) Implementation Plan + Deadlines (ROI-ordered)
### Phase 0 — Protect operational data from git + make failures actionable (Deadline: 2026-01-04)
Goal: never lose SALES_KSP_CRM_V3.xlsx / Inventory_Core workbook again due to repo operations.

Actions:
- Move operational files outside repo into DATA_DIR/AB_DATA_DIR:
  - CRM workbook, inventory workbook, app.db, waybills, exports
- Add preflight check that:
  - verifies required files exist
  - prints exact fix steps
  - optionally restores from backups if configured

Exit criteria:
- Pipeline never fails due to “missing workbook filename” surprises.
- Preflight provides deterministic operator actions.

### Phase 1 — DB-first Manual Sizing Queue (Deadline: 2026-01-10)
Goal: daily shipping can run without opening Excel.

Actions:
- Implement:
  - scripts/export_sizing_queue.py (CSV output)
  - scripts/import_sizing_queue.py (CSV input, dry-run supported)
- Store decisions in fact_order_size_decisions.
- Update shipping/waybill scripts to use DB size decisions as primary source.

Exit criteria:
- Every shipped order has a DB-recorded size decision.
- Excel is optional (UI only).

### Phase 2 — “No-API” Customer Capture via Web Form (Deadline: 2026-01-20)
Goal: reduce manual copy/paste from WhatsApp without needing WhatsApp API approval.

Actions:
- Create a minimal “size capture” web form (acmewear_web repo) that:
  - captures height/weight and order_id/phone
  - writes into DB via a small authenticated endpoint OR dropbox-style CSV import
- Operator sends link manually (not automated spam).

Exit criteria:
- 50%+ orders capture measurements without manual transcription.

### Phase 3 — WhatsApp API Automation (Target: 2026-02-10, dependent on Meta verification)
Goal: automatic measurement capture + auto size assignment.

Actions:
- Automated message templates + webhook ingestion.
- Auto-run size_engine to propose my_size with confidence.
- Human handles low-confidence exceptions only.

Exit criteria:
- Majority of orders receive auto size decisions, human only handles exceptions.

## 7) Operational SOP (Today)
### Generate supplier PO (daily)
1) python scripts/validate_params.py --strict
2) Ensure FX and demand overrides are active (LINE52/LINE51 until 2026-03-01)
3) python scripts/run_end_of_day.py --verbose
4) Use supplier export artifacts in exports/ (CSV + summary)

### Ship + build waybills (daily)
1) Ensure MY_SIZE is present (DB-first; Excel fallback only during migration)
2) ENABLE_KASPI_WRITE=1 only when ready to ship
3) run_build_waybills.command
4) Verify manifests + PDFs count matches

## 8) KPI Tracking (so this doesn’t “fade away”)
- Orders shipped with DB size decision: target 100%
- Daily operator time spent on sizing: baseline now, target -70% by 2026-02-10
- Return rate due to wrong size: track weekly
- “Failed run_build_waybills.command” incidents: target near-zero
