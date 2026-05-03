# PLAN — Returns, Cancels, and Quarantine Stock Truth

Date: 2026-04-23

## Purpose

Close the post-2026-02-01 return/cancel visibility gap without relying on a manual warehouse recount yet.

The business problem is not just sales overcounting. It is three different truths being mixed:

- order/sales truth: completed, cancelled, returned
- warehouse movement truth: active stock deducted, returned-to-warehouse candidates, unprocessed return pile
- QC/restock truth: employee checked item, confirmed size/condition, and moved it back to sellable active stock

Until employee QC is performed, returned items must not be added back into active stock. They belong in a quarantine / pending-QC bucket.

## Repo And Handoff Paths

- Operating repo: `~/Docs/Autonomous_business`
- Run pack: `~/Docs/Autonomous_business/docs/parallel_runs/2026-04-23_returns-cancel-quarantine-truth`
- Shared handoff folder: `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_returns-cancel-quarantine-truth`

## Canonical Protocol

- `~/Docs/Autonomous_business/AGENTS.md`
- `~/Docs/Autonomous_business/docs/00_START_HERE.md`
- `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
- `~/Docs/Autonomous_business/docs/KASPI_ORDER_LIFECYCLE_AND_STATUS_CONTRACT.md`
- `~/Docs/Autonomous_business/docs/KASPI_API_INTEGRATION.md`
- `~/Docs/Autonomous_business/docs/inventory/Master_Inventory_Rules_v9.md`
- `~/Docs/Autonomous_business/docs/inventory/Sales_Data_Model_V16.md`

## Execution Posture

- Agent A is the only write-capable execution agent.
- Agents B and C are read-only analysts.
- B and C publish independently before reading each other.
- Agent A starts after B and C publish first-pass reports.
- Any DB mutation must be backup-first, env-gated, CLI-gated, and logged.
- Manual employee recount/QC is not available in this phase. Build the queue and contracts, but do not invent QC results.

## Business Rules For This Rollout

1. Delivered/completed orders count as sales and deduct active stock.
2. Cancelled before shipment/handover should not count as a sale and usually should not add stock, because the item should not have left active stock.
3. Cancelled after delivery movement, `CANCELLING`, `RETURN_REQUESTED`, and `RETURNED` are not automatically active stock.
4. `RETURNED` or `returnedToWarehouse=true` creates or updates quarantine stock, not active stock.
5. Only a future QC event can move quarantine stock back to active stock.
6. If SKU/size is unresolved, the row must remain an exception and must not silently affect active stock.

## Data Sources To Evaluate

Primary:

- `db/app.db`
- `fact_orders_kaspi`
- `fact_order_entries_kaspi`
- `sales_fact_v2` / sales truth views if relevant
- current WebUI/archive merged exports if present under `exports/` or Oracle packs

Scripts and code surfaces:

- `scripts/export_kaspi_archive_history.py`
- `scripts/export_sales_archive_statusdate_mapped.py`
- `scripts/validate_webui_archive_vs_current_db.py`
- `scripts/rebuild_sales_fact_v2_from_kaspi_entries.py`
- `core/integrations/kaspi_order_stage.py`
- `core/sync/order_sync_engine.py`

Docs:

- `docs/KASPI_ORDER_LIFECYCLE_AND_STATUS_CONTRACT.md`
- `docs/KASPI_API_INTEGRATION.md`
- `docs/KASPI_ORDER_CASHFLOW_TRACKING.md`
- `docs/validation/SALES_TRUTH_EXTERNAL_REFERENCE_CONTRACT.md`
- `docs/validation/SALES_OCEAN_DROP_REFERENCE_CONTRACT.md`

## Desired Deliverables

### 1. Return/Cancel Backlog Export

Produce a deterministic report for 2026-02-01 through the current as-of date.

Expected outputs:

- `exports/returns_quarantine/<as_of>/return_cancel_backlog.csv`
- `exports/returns_quarantine/<as_of>/return_cancel_summary.md`
- `exports/returns_quarantine/<as_of>/return_cancel_exceptions.csv`

Minimum columns:

- `store_code`
- `order_code`
- `order_id`
- `line_id` or stable row key
- `created_at`
- `status_change_date`
- `api_state`
- `api_status`
- `stage_code`
- `returned_to_warehouse`
- `courier_transmission_date`
- `sku_key`
- `mapped_size`
- `quantity`
- `source`
- `sales_effect`
- `active_stock_effect`
- `quarantine_effect`
- `confidence`
- `exception_reason`

### 2. Quarantine Ledger Contract

Design and, if safe, implement a canonical quarantine event surface.

Preferred event types:

- `EXPECTED_RETURN`
- `RETURN_REQUESTED`
- `RETURNED_TO_WAREHOUSE`
- `CANCELLED_BEFORE_STOCK_MOVED`
- `CANCELLED_AFTER_STOCK_MOVED`
- `QC_RESTOCK_ACTIVE`
- `QC_WRITE_OFF`
- `QC_MISSING`

DB writes, if implemented, must require both:

- env gate: `ENABLE_RETURN_QUARANTINE_WRITE=1`
- CLI flag: `--apply`

If schema or write path is not safe, Agent A should stop with a precise design-only deliverable and export-only reports.

### 3. Employee QC Queue Surface

Manual employee recount/QC is intentionally deferred. For now, produce only the processing-derived queue.

Expected output:

- `exports/returns_quarantine/<as_of>/employee_qc_queue.csv`

Minimum columns:

- `order_code`
- `store_code`
- `sku_key`
- `mapped_size`
- `quantity`
- `status_change_date`
- `suggested_action`
- `physical_bucket`
- `qc_status`
- `qc_notes`

Default `qc_status` must be blank or `PENDING_QC`. Do not mark rows as restocked.

### 4. Daily Automation Plan / Hook

Add the smallest safe daily path so this does not become manual again.

Preferred shape:

- read-only daily export first
- optional apply path only after the ledger contract is tested
- fail-closed if archive/API coverage is stale, SKU mapping is unresolved, or quarantine exceptions exceed threshold

## Validation Expectations

Minimum for Agent A:

- `python3 scripts/validate_params.py --strict`
- targeted tests for any new script/module
- `scripts/lint_docs.sh` if docs are changed
- `scripts/check_no_db_tracked.sh`
- if DB was touched: backup path, restore command, and relevant DB invariant checks

Agent A must also record exact output paths and exact commands in:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_returns-cancel-quarantine-truth/agent_a_execution_log.md`

## Agent Split

### Agent B — Archive/API Lifecycle Analyst

Read-only. Determine how reliably current Archive/API/WebUI paths identify:

- `CANCELLED`
- `CANCELLING`
- `KASPI_DELIVERY_RETURN_REQUESTED`
- `RETURNED`
- status-change dates
- line items / SKU / size
- returned-to-warehouse flags

Publish:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_returns-cancel-quarantine-truth/agent_b_report.md`

### Agent C — Inventory/Accounting Design Analyst

Read-only. Design the safest stock/accounting treatment:

- active stock vs quarantine stock
- sales counting vs stock counting
- QC queue fields
- validator stoplines
- cashflow/profit implications

Publish:

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-23_returns-cancel-quarantine-truth/agent_c_report.md`

### Agent A — Execution Agent

Write-capable after B and C publish. Implement the smallest safe version:

1. backlog CSV/report
2. quarantine contract/export
3. employee QC queue export
4. daily automation hook or explicit design stopline

Agent A must not add returned units back to active stock without QC evidence.

## Launch Order

1. Agent B and Agent C can run in parallel.
2. Agent A starts only after B and C publish first-pass reports.
3. If B/C disagree materially, Agent A writes a stopline summary before coding.

## Done Criteria

This rollout is successful when:

- cancelled and returned orders since 2026-02-01 are visible in a deterministic report
- sales overcounting risk is reduced by explicit lifecycle classification
- returned stock is represented as quarantine, not active stock
- employee QC has a queue ready for future physical processing
- daily automation has a clear safe path or a precise stopline
- all claims are traceable to source files, DB tables, commands, and output paths
