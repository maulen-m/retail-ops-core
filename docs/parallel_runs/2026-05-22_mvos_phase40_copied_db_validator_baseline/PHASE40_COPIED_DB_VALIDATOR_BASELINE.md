# PHASE40_COPIED_DB_VALIDATOR_BASELINE

Status: `YELLOW_BASELINE_RETAINED_BLOCKERS_VISIBLE`
Created: `2026-05-22`
Evidence root: `exports/validation/mvos_phase40_copied_db_validator_baseline/20260522_061104`

This is a non-production copied-DB validator baseline. It copies the current production DB into the Phase40 evidence folder, runs selected validators against the copy and read-only source files, and records the exact current pass/fail shape before any CodeCaptain answer or optional owner-approved source acquisition. It does not authorize production DB writes, workbook writes, source-pointer writes, scheduler/LaunchAgent/cron changes, Web_automation writes, Kaspi/API/WebUI mutations, external writes, ad-platform writes, ad spend, stock changes, price changes, cash movement, PO commitment, owner publication, production preflight, or production apply.

## Copied DB Boundary

Copied DB:

`exports/validation/mvos_phase40_copied_db_validator_baseline/20260522_061104/app_phase40_copy.db`

SHA evidence:

`exports/validation/mvos_phase40_copied_db_validator_baseline/20260522_061104/db_copy_sha256.tsv`

The copied DB SHA equals current `db/app.db` SHA at copy time:

`726a6bc45a4811423390e28698a63e39f5d9400057fb2671ca68c255468371b5`

## Baseline Interpretation

Phase40 intentionally uses a plain DB copy. It does not reapply the Phase33/34/35 copied-temp materializations and does not apply any optional LINE-31-LS COGS, status-ledger, ads, or stock substitute contract. Therefore failures here are the current baseline blockers, not regressions from prior specialized copied-temp proofs.

The useful signal is:

- SQLite integrity passes.
- Cashflow invariants pass.
- Strict order-cashflow coverage passes with `cash_in_missing_count=0` and `still_blocked_source_missing_count=0`.
- Exception queue DB contract passes.
- C3 source freshness and publication gates fail on the plain copy.
- Order-entry freshness, workbook anchor, day-complete, stock drift, PO dashboard, COGS, single-truth, PO money, offer linkage, on-delivery freeze, and DIM_SKU alignment all fail on the plain copy.

## Validator Exit Matrix

| Command | Exit | Baseline signal |
| --- | ---: | --- |
| `01_sqlite_integrity` | `0` | DB copy integrity OK. |
| `02_validate_policy_source_freshness` | `1` | Missing current freshness result rows for required sources including operational truth, manual bank, external ads, inbound workbook, payment evidence, supplier routes, and Kaspi Marketing DirectAPI. |
| `03_validate_policy_gate_results` | `1` | Owner-publication policy gates blocked: ads, cashflow, exception queue, PO source, source freshness, stock source. |
| `04_validate_cashflow_invariants` | `0` | `PASS: 848 days validated`. |
| `05_validate_order_cashflow_coverage` | `0` | PASS, `cash_in_missing_count=0`, deterministic exceptions remain visible. |
| `06_validate_order_entries_freshness` | `1` | `IDENTITY_COVERAGE_FAIL` for `STOREB`, `ACMEWEAR`, and `UNIVERSAL`. |
| `07_validate_sales_vs_workbook_anchor` | `1` | Workbook content lag: workbook max date `2026-04-09`, as-of `2026-05-22`, lag `43` days. |
| `08_validate_day_complete_20260518` | `1` | Two violations remain in the plain copy: `844362551` and `861137901`. |
| `09_validate_inventory_cost_drift` | `1` | Stock snapshot `2026-05-04`, cost drift `16,835,338.88 KZT` vs allowed `803,909.74 KZT`. |
| `10_validate_po_dashboard_invariants` | `1` | Stock snapshot stale vs cutoff `2026-05-17`. |
| `11_validate_exception_queue_db` | `0` | Exception queue DB contract OK. |
| `12_validate_cogs_integrity` | `1` | One unresolved COGS row and SKU remain. |
| `13_validate_single_truth_system` | `1` | Historical DB part ids missing in workbook plus PO quantity/weight/payment mismatches in plain route. |
| `14_validate_single_truth_alignment` | `1` | Cashflow invariants pass inside the validator, but inventory cost drift and plan alignment fail. |
| `15_validate_po_money_gate` | `1` | Required failures: inbound sheet consistency, single-truth system, COGS integrity, single-truth alignment. |
| `16_validate_offer_linkage` | `1` | Mapper table missing: `fact_offer_stock_mapper_current`. |
| `17_validate_on_delivery_freeze` | `1` | Multiple shipped rows have missing `INVENTORY_ON_DELIVERY_COST` balance; retained row `929183530` remains present. |
| `18_validate_dim_sku_light_alignment` | `1` | `weight_mismatches=10`, `base_mismatches=11`. |

Machine-readable exit matrix:

`exports/validation/mvos_phase40_copied_db_validator_baseline/20260522_061104/VALIDATOR_EXIT_MATRIX.tsv`

## Retained Blocker Mapping

| Blocker group | Phase40 evidence |
| --- | --- |
| Ads/source truth | `validate_policy_source_freshness` and `validate_policy_gate_results` remain blocked; no accepted current packets were applied. |
| Cashflow truth | Cashflow invariants and strict order-cashflow coverage pass, but C3 cashflow/source gates still fail on the plain DB copy. |
| Order entry/sales/workbook | Order-entry freshness, workbook anchor, and day-complete fail on the plain copy; prior copied-temp closures remain review-only evidence. |
| Status/lifecycle | Day-complete still fails on the plain copy; same-window status-ledger continuity remains a separate retained blocker. |
| Physical stock/PO | Inventory cost drift and PO dashboard invariants fail from stale physical stock source. |
| PO money/single truth | Single-truth system/alignment and PO money gate fail on the plain copy; Phase39 route remains the correct contract path. |
| B012 daily autonomy | COGS, on-delivery freeze, and DIM_SKU alignment fail on the plain copy; LINE-31-LS COGS authority and default route remain unresolved. |
| Dirty repo | Not cleared; Phase37 grouping remains the current production stopline. |

## Next Route

1. Send or review the Phase38 CodeCaptain addendum pack with Phase39/40 as optional local addenda.
2. If CodeCaptain accepts specific contracts, run one copied-temp integrator on a fresh DB copy and re-run this validator matrix.
3. If the owner chooses to accelerate source acquisition, use the exact optional phrases from Phase38 and keep all fetches read-only/local-evidence-only.
4. Do not run production preflight from this state.

## Gate

`YELLOW_BASELINE_RETAINED_BLOCKERS_VISIBLE`

Reason: Phase40 produced useful copied-DB baseline evidence, but the current plain DB copy still fails multiple validator routes and retained source/authority blockers remain unresolved.
