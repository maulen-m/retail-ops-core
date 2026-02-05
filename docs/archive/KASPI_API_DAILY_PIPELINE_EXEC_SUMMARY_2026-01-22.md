# Executive Summary: Kaspi API + Daily Pipeline (2026-01-22)

Scope: Kaspi-only order and sales automation, PO planning, and daily operations.
This document is a single, high-signal summary of the current API shape, the daily
pipeline A-to-Z, the DB tables that are written/read, and the human workflow needed
for correct outcomes.

Sources of truth referenced (read before changing behavior):
- docs/KASPI_API_INTEGRATION.md
- docs/Kaspi_API_Official_document_8.12.2025_GP.md
- docs/DAILY_SOP.md
- docs/DAILY_WORKFLOW.md
- docs/inventory/Sales_Data_Model_V16.md
- docs/ARCHITECTURE.md
- docs/protocol/active/PO_making_logic_v2.md

---

## 1) Kaspi API structure (what the system uses)

API style: JSON:API over HTTPS. Base URL:
- https://kaspi.kz/shop/api/v2

Authentication:
- X-Auth-Token header (also sent as Authorization)
- Tokens come from the Kaspi merchant portal and live in .env as KASPI_TOKEN_*.

Key constraints (from official docs + client code):
- Max date range per request: 14 days.
- Page size max: 100.
- Rate limit configured in client: 50 req/sec (conservative).
- Write operations are blocked unless ENABLE_KASPI_WRITE=1.

Order endpoints (core usage):
- GET /orders (list, filter by state/status/date)
- GET /orders/{id} (Base64 ID)
- GET /orders/{id}/entries (line items)
- POST /orders (status changes like accept/assemble/ship/cancel)

Notable implementation details:
- API order IDs are Base64 in the API, but the system often starts with numeric
  order codes and then resolves Base64 IDs when needed.
- Assemble uses a primary endpoint and a fallback endpoint for compatibility.
- Lookback is clamped to stay within the API limit.

---

## 2) Daily data flow: sources -> DB tables -> outputs

The system has two primary data streams that then converge in planning outputs.

### A) Orders stream (Kaspi API)
Source:
- Kaspi Shop API (orders, statuses, waybills).

DB targets:
- fact_orders_kaspi: authoritative order lifecycle and status tracking.
  - Created/updated by scripts/sync_kaspi_orders.py and OrderSyncEngine.
  - Used for day-complete checks and order processing/waybill build flow.

Outputs:
- order status reports and validation gates.

### B) Sales stream (CRM Excel -> DB)
Source:
- excel_ui/SALES_KSP_CRM_V3.xlsx (sheet SALES_KSP_CRM_1).

DB targets:
- sales_fact_v2: deduplicated sales records + return tracking.
  - Dedup key: (order_id, store_code, kaspi_offer_name, sku_key, my_size).
  - Returns produce RETURN events in the ledger.
- fact_sales: transaction-level economics (v8 formulas).
- stock_ledger: event-sourced stock changes (SALE/RETURN events).
- fact_sales_daily + fact_sales_daily_size: aggregates for demand/analytics.

Outputs:
- demand estimation inputs, size mixes, inventory projections, PO dashboard data.

### C) Inventory + PO stream
Sources:
- stock_ledger (events)
- fact_inventory_snapshot_size (rebuilt from ledger)
- po_header / po_line (real PO lifecycle) and inbound arrivals

DB targets / outputs:
- fact_inventory_snapshot_size (daily snapshot) used in PO engine.
- po_header / po_line for real POs and arrivals (inbound events).
- exports/po_dashboard_data.json + exports/po_dashboard.html

---

## 3) DB table roles (quick map)

Orders:
- fact_orders_kaspi: lifecycle and status of Kaspi orders (API truth).

Sales:
- sales_fact_v2: deduped sales records (DB truth for demand + ledger events).
- fact_sales: enriched sales with economics (net revenue, COGS, profit).
- fact_sales_daily: daily aggregates by sku_key.
- fact_sales_daily_size: daily aggregates by sku_id.

Inventory:
- stock_ledger: event-sourced stock changes (SALE, RETURN, INBOUND, etc).
- fact_inventory_snapshot_size: current stock snapshot (rebuilt from ledger).

PO lifecycle:
- po_header: PO metadata and lifecycle state.
- po_line: PO line items, received qty, unit cost.

Dimensions:
- dim_sku, dim_sku_size, dim_store, dim_size_synonyms.

Planning outputs:
- exports/po_dashboard_data.json + exports/po_dashboard.html
- exports/shadow_scorecard_YYYY-MM-DD.csv

---

## 4) Daily pipeline (A to Z) - run_end_of_day.py

Primary orchestration script:
- scripts/run_end_of_day.py

Key steps (current order):
0. validate_params.py --strict
1. sync_truth_workbook_to_db.py (optional; DB is default source of truth)
2. sync_crm_to_db.py (CRM sales -> sales_fact_v2 + fact_sales)
2a. sync_kaspi_orders.py (API order status sync -> fact_orders_kaspi)
2b. backfill_kaspi_order_sizes.py (backfill missing sizes)
2c. sync_po_arrivals_to_ledger.py (inbound events)
2d. clamp_negative_ledger.py
2e. rebuild_snapshot.py --mode auto
2f. validate_snapshot_vs_snapshot_z.py
2g. validate_day_complete.py (optional gate)
3. generate_po_dashboard_data.py
4. smoke_test_dashboard.py
5. update_po_dashboard.py
5a. update_cashflow_dashboard.py
6. audit_dashboard_output.py
7. generate_shadow_scorecard.py

Expected outputs:
- exports/po_dashboard_data.json
- exports/demand_diagnostics.csv
- exports/po_dashboard.html
- exports/shadow_scorecard_YYYY-MM-DD.csv

---

## 5) Human daily workflow (manual + automation)

Two paths exist: API-first (Phase 12) and Excel-based (Phase 11). Both rely
on manual size entry (MY_SIZE) before final shipping.

Typical day (condensed):
1) Download ActiveOrders from Kaspi (or API export) into excel_ui/ActiveOrders.
2) Import to CRM:
   - excel_ui/run_full_import.command (automated at scheduled times)
3) Open excel_ui/SALES_KSP_CRM_V3.xlsx and fill MY_SIZE for new orders.
4) Build waybills:
   - excel_ui/run_build_waybills_v2.command
5) Package preparation + courier handover.
6) End-of-day pipeline:
   - scripts/run_end_of_day.py (scheduled 20:30)

Manual verification steps (high risk):
- Confirm MY_SIZE is fully populated before shipping.
- Confirm waybill PDFs and manifests align with DB orders.
- Confirm CRM and DB sync completed without errors.

---

## 6) Active schedules (launchd)

Source of truth for current schedules is in these files:
- com.example.crm-db-sync.plist
- config/com.example.kaspi-import.plist
- config/com.inventory.endofday.plist

Configured schedules (Asia/Almaty local time):
- CRM -> DB sync:
  - scripts/sync_crm_to_db.py
  - Schedule: 13:00 daily
- Kaspi import (API export + CRM import):
  - excel_ui/run_full_import.command
  - Schedule: 10:30, 15:02, 20:30 daily
  - Lookback days: default 5, 14 on late run
- End-of-day pipeline:
  - scripts/run_end_of_day.py
  - Schedule: 20:30 daily

Note: docs/DAILY_WORKFLOW.md contains older schedule times. The plists above
are the live schedules.

---

## 7) Auth, tools, and unusual mechanics

- Kaspi API auth token is required and is stored in .env.
- Both X-Auth-Token and Authorization headers are used by the client.
- Base64 order IDs are required for some endpoints; numeric codes are mapped.
- API write operations are blocked unless ENABLE_KASPI_WRITE=1.
- Lookback is clamped to avoid exceeding API 14-day limit.
- Rate limiting and retry logic are enforced by the API client.

---

## 8) Pipeline example (daily execution)

Example: end-of-day run (manual):

  python3 scripts/run_end_of_day.py --verbose

Expected results:
- Fresh po_dashboard_data.json and po_dashboard.html
- demand_diagnostics.csv regenerated
- shadow_scorecard_YYYY-MM-DD.csv generated

Gate failures should be logged in .claude/ISSUES.md, then fixed before expansion.

---

## 9) Appendix: quick reference for the most critical files

Kaspi API + orders:
- core/integrations/kaspi_api_client.py
- core/sync/order_sync_engine.py
- scripts/sync_kaspi_orders.py
- scripts/manage_kaspi_orders.py

Sales ingestion:
- scripts/sync_crm_to_db.py
- core/ingest/sales_ingest.py

Planning + dashboard:
- scripts/generate_po_dashboard_data.py
- scripts/update_po_dashboard.py
- docs/protocol/active/PO_making_logic_v2.md

Schedules:
- com.example.crm-db-sync.plist
- config/com.example.kaspi-import.plist
- config/com.inventory.endofday.plist

---

## 10) Working definitions (single-source of truth)

- Inventory formulas: docs/inventory/Master_Inventory_Rules_v8.md
- PO logic: docs/protocol/active/PO_making_logic_v2.md
- Sales schema: docs/inventory/Sales_Data_Model_V16.md
- Daily SOP: docs/DAILY_SOP.md

