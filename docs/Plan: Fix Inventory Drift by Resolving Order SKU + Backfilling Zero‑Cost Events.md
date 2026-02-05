Plan: Fix Inventory Drift by Resolving Order SKU + Backfilling Zero‑Cost Events
Summary
We will stop zero‑cost inventory events by resolving missing SKU identity from API order entries and the article map. The translator will refuse to proceed if SKU resolution fails, preventing silent drift. We will also allow backfill when existing zero‑amount inventory events exist, so corrected events can be inserted without deleting history.

Public Interface / Behavior Changes
translate_orders_to_cashflow_events.py
New behavior: when fact_orders_kaspi.sku_key is missing, resolve using fact_order_entries_kaspi joined to dim_kaspi_article_map.
New behavior: if SKU resolution or unit cost remains missing, translation fails with a clear actionable error (no silent zero‑cost events).
New behavior: zero‑amount inventory events do not block corrected non‑zero backfill.
Tests (Write First, Fail First)
Add to test_cashflow_translator.py and update its DB fixture.

test_translate_orders_resolves_entries_when_sku_missing

Create fact_orders_kaspi row with missing sku_key.
Create fact_order_entries_kaspi row with offer_id.
Create dim_kaspi_article_map mapping offer_id → sku_key + sku_id.
Create dim_sku with valid costs.
Assert non‑zero COGS + inventory move events are inserted.
test_translate_orders_errors_when_sku_unresolved

Create order row missing sku_key.
Do not insert entries or mapping.
Expect translate_orders to raise a RuntimeError with a message pointing to enrichment and mapping requirements.
test_translate_orders_backfills_zero_cost_events

Seed zero‑amount COGS + inventory move events for an order.
Insert entries + mapping so SKU resolves.
Re‑run translator and assert new non‑zero events are inserted (counts increase).
Implementation Steps
Extend test DB setup in test_cashflow_translator.py
Add tables:

fact_order_entries_kaspi
dim_kaspi_article_map
Keep existing schema for fact_orders_kaspi, fact_cashflow_events, dim_sku.
Add entry‑based SKU resolution in translate_orders_to_cashflow_events.py

Add helper to check for table existence and load entry lines:
Query fact_order_entries_kaspi joined to dim_kaspi_article_map on (store_code, offer_id = kaspi_article).
Build entries_by_order[(order_id, store_code)] = [line...].
In the main loop:
If sku_key present on order row: build a single line as current behavior.
Else, if entries exist: build per‑entry lines with sku_key, sku_id, quantity, unit_price_kzt.
Else: record as missing.
Enforce strict missing‑SKU guard

Accumulate unresolved orders and orders with unit_cost <= 0.
If any unresolved, raise RuntimeError before writing events.
Error message must point to: enable order enrichment and ensure dim_kaspi_article_map coverage.
Allow backfill when existing events are zero

Update the existing‑event loaders in translate_orders_to_cashflow_events.py to ignore events where ABS(amount_kzt) = 0 so corrected non‑zero events can be inserted.
Keep cash‑in idempotency unchanged.
Optional documentation update (only if needed)

Add a short note in KASPI_ORDER_CASHFLOW_TRACKING.md that order entries + article map are required for inventory cost; missing SKU now hard‑fails translation.
Data Remediation (Operational Runbook)
This is required after code change to actually fix drift:

Ensure enrichment is enabled:
kaspi_enrichment.yaml has enabled: true.
ENABLE_KASPI_ENRICHMENT=1 is set in the environment.
Run a lookback enrichment for the drift window.
Re‑run translate_orders_to_cashflow_events.py --apply for the same window.
Rebuild cashflow calendar and rerun validate_inventory_cost_drift.py.
Test Cases / Scenarios
Missing SKU resolution via entries produces non‑zero COGS.
Missing SKU with no entries fails fast (no writes).
Zero‑amount inventory events allow corrected backfill insertion.
Assumptions / Defaults
Order entries + article map are the canonical path to resolve missing SKU for API orders.
Zero‑amount inventory events are considered invalid and do not block corrected backfill.