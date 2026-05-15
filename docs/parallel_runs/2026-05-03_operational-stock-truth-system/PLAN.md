# Operational Stock Truth System Implementation Plan

Status: canonical rollout plan for integrating the external Code Captain review into repo execution.

Source review:

- `~/Docs/Oracle/Autonomous_business/2026-05-03/101657_TASK-000_operational-stock-orders-sales-system-review/Answer/Code_Captain_answer_2026-05-03_12_05_00.md`

Repo:

- `~/Docs/Autonomous_business`

Canonical protocol:

- `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`

Shared handoff folder:

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-03_operational-stock-truth-system`

## Authority Decision

The external answer should not be pasted into every owning doc. That would create another stale mega-doc.

The efficient integration path is:

1. Preserve the external answer as evidence.
2. Create this single authoritative rollout plan in the repo.
3. Treat existing owning docs as formula/schema/business-rule authority.
4. Make Agent 5 update owning docs only where the rollout requires a formula, schema, or contract change.
5. Implement code only after the owning doc and tests define the expected behavior.

This plan is authoritative for rollout sequencing, agent split, gates, and acceptance criteria. It does not override:

- Inventory formulas: `docs/inventory/Master_Inventory_Rules_v9.md`
- PO logic: `docs/protocol/active/PO_making_logic_v3.md`
- Sales/data model: `docs/inventory/Sales_Data_Model_V16.md`
- Excel/CRM contract: `docs/inventory/Excel_UI_Contract_for_CRM_V1.md`
- Architecture: `docs/ARCHITECTURE.md`
- Daily ops: `docs/DAILY_SOP.md`

If a rule/spec changes, update the owning doc first, then tests, then code.

## Integration Options

### Option A: Minimal Deployable Stock-Only

How it works:

- Implement authority/schema gates.
- Load an approved stock anchor.
- Apply the one-time 20% stock decrease as audited ledger adjustment events.
- Rebuild daily stock by SKU-size.
- Publish stock report with red/green trust banner.

Pros:

- Fastest path to decision-grade warehouse stock.
- Lowest merge and DB risk.
- Immediately addresses the owner need for current stock by item/size.

Cons:

- Does not fully solve order/cash/ads/PO automation.
- Profit and product-test decisions still need separate gates.

Estimated complexity: medium.

When to use: if the business needs a reliable daily stock snapshot before all finance/ads/cash modules are repaired.

### Option B: Recommended Staged Operating Kernel

How it works:

- Run four read-only analysts in parallel.
- Then execute four write-capable implementation stages sequentially.
- P0 gates land first, then stock ledger/rebuild, then order/return/PO/ads/cash integrations, then daily runner/report publication.

Pros:

- Fast without unsafe concurrent writes.
- Preserves repo protocol: parallel read-only discovery, serialized writes.
- Converts the external answer into durable repo implementation with tests-first gates.
- Keeps stock, orders, PO, ads, and cashflow harmonized instead of patched independently.

Cons:

- More coordination than Option A.
- Requires strict closeouts before each write stage begins.

Estimated complexity: high.

When to use: recommended default for complete implementation.

### Option C: Robust Autonomous System

How it works:

- Complete Option B.
- Add scheduler hardening, exception queues, run-status lineage, owner dashboards, cashflow/cargo/PO/payment decision integration, and automated daily publish.
- Add final release audit and rollback rehearsals.

Pros:

- Most durable autonomous operating system.
- Best protection against false-green stock, cash, ads, and PO decisions.

Cons:

- Highest implementation time.
- Should not start until Option B gates are green.

Estimated complexity: very high.

When to use: after the stock kernel is green and the business wants fully automated daily operations without manual agent recalculation.

Recommended path: Option B first, then Option C.

## Agent Topology

Recommended total agents: 8.

Parallel wave:

- Agent 1: read-only authority/schema/contracts analyst.
- Agent 2: read-only stock anchor, 20% adjustment, ledger/snapshot analyst.
- Agent 3: read-only orders, sales, returns, cancellations, QC analyst.
- Agent 4: read-only PO/inbound, ads, cashflow analyst.

Sequential implementation wave:

- Agent 5: write-capable P0 authority/schema/gate executor, after Agents 1-4.
- Agent 6: write-capable stock anchor/20%/snapshot executor, after Agent 5.
- Agent 7: write-capable orders/returns/PO/ads/cashflow integration executor, after Agent 6.
- Agent 8: write-capable daily runner/report/release gate executor, after Agent 7.

Why this is most efficient:

- The four analysts can work in parallel without touching shared repo state.
- Only one implementation agent writes at a time.
- DB, `.claude/*`, config, migrations, and exports stay serialized.
- Each sequential implementation agent inherits exact closeouts and gates from prior agents.

Do not run Agents 5-8 in parallel unless the owner explicitly accepts higher merge/DB risk and isolated worktrees with disjoint write scopes are defined.

## Implementation Phases

### Phase 0: Authority Ingress

Goal:

- Convert the external answer into repo-governed work without creating stale duplicate doctrine.

Already created by this orchestrator:

- This plan.
- Agent starter prompts.
- Shared handoff folder.

Gate:

- Plan and launch order exist.
- Each agent prompt has absolute bootstrap paths.

### Phase 1: P0 Authority And Schema Gates

Owner: Agent 5.

Inputs:

- Agent 1 report.
- Agent 2 report.
- Agent 3 report.
- Agent 4 report.

Required outcomes:

- Tests fail if new PO/inventory math uses v8/v2/v6/V15 authority.
- Tests fail if required runtime tables are missing from live schema/migrations.
- Any stale doc pointer required by the implementation is corrected in the owning doc.
- `scripts/reconcile_ledger_to_snapshot.py` idempotency risk is fixed or quarantined before any 20% adjustment path can use it.

Required tests first:

- Authority ladder validator fixture.
- Required-table schema fixture.
- Reconcile adjustment idempotency fixture.

Required gates:

- Focused pytest for new validators/fixtures.
- `python3 scripts/validate_params.py --strict`
- `scripts/check_no_db_tracked.sh`
- `scripts/lint_docs.sh` if docs are touched.

Stop if:

- Existing migration state cannot be safely understood.
- The implementation requires formula changes but owning docs are not updated first.

### Phase 2: Stock Anchor, 20% Adjustment, Ledger Snapshot

Owner: Agent 6.

Required outcomes:

- `stock_anchor` and `stock_adjustment_batch` semantics are documented and implemented or mapped to existing equivalent tables.
- The one-time 20% decrease is generated as audited `stock_ledger` adjustment events, not destructive anchor edits.
- Adjustment is dry-run first.
- Adjustment idempotency prevents duplicate application.
- Rebuilt current stock is generated from ledger mode only.
- Snapshot output separates physical warehouse stock from offer availability.

20% adjustment policy:

- Event type: `ADJUSTMENT`.
- Reference type: `BASELINE_20PCT_DECREASE`.
- Business effect: after approved anchor, before post-anchor movements.
- Rounding: floor per row, then allocate remaining units by largest fractional remainder, deterministic tie-break by SKU-size key.
- Rollback: reversal events only; no deletion of ledger history.

Required tests first:

- 20% proportional rounding fixture.
- Idempotency fixture.
- No-negative-stock fixture.
- Ledger-to-snapshot fixture.
- High-risk family exception fixture for `LINE52 4XL` and `T-SHIRT BLACK S/M/L`.

Required gates:

- Focused stock tests.
- Ledger duplicate check.
- No negative balance check.
- Snapshot lineage report.
- `scripts/check_no_db_tracked.sh`

Stop if:

- Anchor is not approved.
- Adjustment was already applied.
- Any SKU-size goes negative.
- High-risk family review is missing.

### Phase 3: Orders, Sales, Returns, PO, Ads, Cashflow Integration

Owner: Agent 7.

Required outcomes:

- Order status events become the lifecycle spine.
- Sales truth derives from canonical order entries/status events, not overlapping Excel/API/archive sources.
- Returned/cancelled goods are not active stock until QC/acceptance event exists.
- PO/inbound sync uses PO part/line grain and writes idempotent inbound events.
- Ads coverage gaps, especially STOREB, block profit/product-test decisions instead of becoming zero spend.
- Cashflow uses D1 Kaspi Pay delivered-order semantics unless a separate modeled scenario is explicitly requested.

Required tests first:

- Sales/order dedup fixture.
- Return/QC restock fixture.
- PO/inbound reconciliation fixture.
- Ads coverage fixture with missing active-source credentials.
- D1 cashflow fixture.
- Cashflow roll-forward invariant fixture.

Required gates:

- `python3 scripts/validate_cashflow_invariants.py`
- `python3 scripts/validate_po_dashboard_invariants.py`
- Relevant focused pytest.
- `scripts/check_no_db_tracked.sh`

Stop if:

- Missing ads credentials are treated as zero spend.
- Returned/cancelled orders add active stock without QC.
- PO arrival and stock inbound events double-count.

### Phase 4: Daily Runner, Owner Reports, Release Gates

Owner: Agent 8.

Required outcomes:

- Strict daily truth runner exists or current runner is hardened so hard gates abort downstream publication.
- Run status records source manifests, row counts, hashes, validation results, and exception counts.
- Owner outputs contain a trust banner: green decision-grade or red blocked.
- If gates fail, owner receives exception report, not a green workbook.
- Daily automation can run without a human prompt.

Required tests first:

- Runner fail-closed fixture.
- Source freshness fixture.
- Report lineage fixture.
- Red owner brief fixture.
- Scheduler/interpreter determinism fixture.

Required gates:

- Focused runner/report tests.
- `python3 scripts/validate_params.py --strict`
- `python3 scripts/run_end_of_day.py --verbose` only if safe in the current repo state.
- `pytest -q` when practical for release candidate.
- `scripts/check_no_db_tracked.sh`

Stop if:

- Any required gate is skipped.
- The runner catches hard failures and continues to green publication.
- Outputs recompute business math outside canonical derived tables.

## Required Data Model Targets

These may be implemented as new tables or mapped to existing equivalent tables only if tests prove the contract:

- `source_manifest`
- `pipeline_run` or hardened `fact_runs`
- `validation_result`
- `exception_queue`
- `stock_anchor`
- `stock_adjustment_batch`
- `stock_ledger`
- `fact_inventory_snapshot_size`
- `offer_availability_snapshot`
- `order_status_event`
- `fact_orders_kaspi`
- `fact_order_entries_kaspi`
- `sales_fact_v2` or canonical successor
- `return_qc_event`
- `po_header`
- `po_part`
- `po_line`
- `fact_cashflow_events`
- `fact_cashflow_daily`
- `ads_source_refresh_runs`
- `ads_campaign_product_daily`
- `owner_report_snapshot`

## Universal Gates

Every implementation agent must follow:

- Tests before changes.
- Dry-run default for writes.
- Explicit apply gate for DB or external writes.
- DB backup before apply.
- Rollback story in closeout.
- No destructive edits to history.
- No stale v8/v2/v6/V15 formula authority for new behavior.
- No treating unknown/missing data as zero.
- No green owner output when hard gates fail.

## Completion Criteria

The rollout is complete only when:

- Authority/schema gates are green.
- The one-time 20% stock decrease is applied exactly once or explicitly remains owner-blocked.
- Current stock by SKU-size rebuilds from ledger with no negative balances and lineage.
- Orders/sales/returns/cancellations/inbound/ads/cashflow have explicit contracts and fail-closed gates.
- Daily runner can generate a decision-grade snapshot or a red blocked brief without manual recalculation.
- Required tests pass.
- Handoff folder contains closeouts for every executed agent.
- Rollback steps are written for every write-capable stage.
