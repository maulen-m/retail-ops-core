# CodeCaptain Review Prompt: Agent9125 YELLOW Retained-Blocker Board

Please review the current Autonomous_business MVOS copied-temp board after Agent912.

We need a decision-grade next-route recommendation, not a green pass unless the evidence supports it.

## Current Decision

Agent9125 closed:

- Gate: `YELLOW`
- Domain status: `YELLOW_RETAINED_BLOCKER_BOARD_PROOF`
- Required instruction: do not claim `COPIED_TEMP_GREEN_PROOF`.

The protected boundary stayed unchanged, and the copied DB proof board improved materially, but required validators still fail.

## What Improved

- C3 source contract is split into publication-relevant child source rows.
- `src_ab_db_operational_truth` is now informational/non-publication-blocking.
- Order-entry, cashflow, and order-status child sources are fresh on the copied-temp board.
- `DIM_SKU_light` workbook parser repair is confirmed by sync dry-run.
- Line61 shortage is classified as accepted real business truth: ordered/cargo `115`, actual received `92`, shortage `23`, XL `7`, 2XL `5`, 3XL `6`, 4XL `5`.
- Day-complete, order-entry freshness, COGS completeness with Agent873 unit evidence, exception queue, cashflow invariants, order-cashflow coverage, ads offer universe, and ads spend reality pass on the copied board.

## What Still Blocks Green

Required validators still fail:

- `validate_policy_source_freshness.py --as-of 2026-05-18 --strict --json`
- `validate_policy_gate_results.py --strict --json`
- `validate_po_dashboard_invariants.py`
- `validate_po_money_gate.py --as-of 2026-05-18 --json`
- `validate_single_truth_system.py`
- `validate_inbound_sheet_consistency.py --json` exits `1` by design while showing `unknown_mismatch_count=0` and `accepted_shortage_count=2`.

The retained blocker matrix identifies:

- `src_ab_db_stock_truth` stale: `fact_inventory_snapshot_size` and `stock_ledger` max observed `2026-05-04`.
- `src_ab_db_sales_truth` stale: `sales_fact_v2` max observed `2026-05-04`.
- `src_ab_db_ads_truth` stale for strict May 18 gate: ads source rows max observed `2026-05-17`.
- PO dashboard stale stock snapshot.
- PO money and single-truth remain blocked by retained DB/workbook part-history and payment mismatches.

## Questions For CodeCaptain

1. What accepted fresh stock source packet, if any, is sufficient to authorize copied-temp refresh of `fact_inventory_snapshot_size` and `stock_ledger` for as-of `2026-05-18`, with SKU-size identity, capture time, source hash, row count, and date at or beyond validator cutoff?
2. What accepted SKU-identity/mapping source, if any, is sufficient to authorize copied-temp rebuild of `sales_fact_v2` beyond `2026-05-04`, or should sales freshness remain blocked until a new source packet exists?
3. For ads, does the May 12-17 Agent9121 packet need a May 18-covering source packet, or should the contract allow date-only `2026-05-17` coverage for a May 18 as-of gate?
4. For PO money/single-truth, should production PO/inbound remain blocked until canonical workbook/DB refresh resolves retained part-history, PO-4.0 total/weight, and PO-5.2/PO-6 base-payment mismatches?
5. Is the next efficient phase source acquisition for stock/sales/ads plus separate PO/single-truth canonical refresh, or a narrower contract clarification before more implementation?

## Boundary

This packet is review-only. It does not authorize production DB writes, workbook writes, scheduler/LaunchAgent/cron changes, source-pointer writes, Web_automation writes, Kaspi/API/WebUI writes, external writes, ad-platform writes, cash movement, supplier payment, PO commitment, stock changes, price changes, owner publication, production preflight, production apply, or treating copied-temp evidence as production truth.
