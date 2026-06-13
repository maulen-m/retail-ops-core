# Green Path Phase 2 Current Gate Audit And Header-Only Proof

Gate: YELLOW

Date: 2026-06-14

## Scope

This audit re-baselined the current post-apply state after the committed cashflow, ads, Meta spend, and source-backed stock repairs. It originally did not perform production DB writes.

Update: the 251-row header-only cleanup was subsequently applied safely in production after the wrapper was hardened. See `docs/agent_handoffs/GREEN_PATH_PHASE2_HEADER_ONLY_PROD_APPLY_20260614.md`.

Update 2: the remaining `906730647` header-only leak was subsequently reclassified from stale header-only quarantine to real API entry evidence. See `docs/agent_handoffs/GREEN_PATH_PHASE2_906730647_REAL_ENTRY_RECLASSIFICATION_20260614.md`.

The result corrects an overly narrow reading of the previous closeout: the compact C3 publication blockers are stock-related, but the deeper operational stock integration validator still reports order-entry and lifecycle blockers that must be repaired before Phase 2 can honestly close.

## Read-Only Gate Evidence

Evidence root:

- `exports/validation/orchestrator_current_gate_audit_20260614/`

Commands:

```bash
.venv/bin/python scripts/validate_policy_source_freshness.py --db db/app.db --as-of 2026-06-13 --strict --json
.venv/bin/python scripts/validate_policy_gate_results.py --db db/app.db --strict --json
.venv/bin/python scripts/validate_operational_stock_integration_gates.py --db db/app.db --as-of 2026-06-13 --json --max-findings 80
```

C3 source freshness:

- `ok=false`
- blocker: `src_ab_db_stock_truth` is `STALE` for requested as-of `2026-06-13`

C3 gate results:

- `source_freshness`: `BLOCKED`
- `stock_source_truth`: `BLOCKED`

Production negative stock rows remain exactly:

```text
SUIT-31-LS_3XL|UNIVERSAL|-3
LINE-31-TS_3XL|UNIVERSAL|-2
SUIT-31-LS_XL|UNIVERSAL|-2
LINE-31-LS_XL|UNIVERSAL|-1
LINE-31-TS_XL|UNIVERSAL|-1
CL_NEW-CLO_KIDS_KID-31_BLACK_L|UNIVERSAL|-1
CL_NEW-CLO_KIDS_KID-31_BLACK_M|UNIVERSAL|-1
CL_NEW-CLO_KIDS_KID-31_BLACK_S|UNIVERSAL|-1
SUIT-31-TS_XL|UNIVERSAL|-1
```

Operational stock integration validator:

- status: `RED`
- finding_count: `503`

Current finding census:

```text
ERROR ORDER_ENTRY_MISSING                                   219
ERROR ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_PRODUCT_COGS_LEAK    8
ERROR ORDER_LIFECYCLE_MISSING_COMPLETED                       8
ERROR ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_ENTRY_LEAK            1
WARN  ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_QUARANTINED         244
WARN  ORDER_ENTRY_PRODUCT_IDENTITY_QUARANTINED                23
```

## Header-Only Copied DB Proof

The current DB contains 252 STOREB header-only quarantine rows. One order, `906730647`, now has a real `fact_order_entries_kaspi` API entry and must not be replayed as header-only evidence. Therefore the current proof generated a 251-row classification from the existing quarantine table, excluding only `906730647`.

Evidence root:

- `exports/validation/orchestrator_header_only_quarantine_current_proof_20260614/`

Generated classification:

- `exports/validation/orchestrator_header_only_quarantine_current_proof_20260614/source/current_header_only_251_classification.tsv`
- SHA-256: `7beab3053a31a5a232e031e12d546ba52ca3543625ddec4fd33be5fad04cca6e`

Production dry-run:

- `candidate_rows`: `251`
- `leakage_before.product_cashflow_reference_count`: `7`
- `fact_order_entries_inserted`: `0`
- `header_fields_used_as_canonical_item_entry_truth`: `false`
- production DB modified: `false`

Copied DB proof:

- copied DB: `exports/validation/orchestrator_header_only_quarantine_current_proof_20260614/copied_db/header_only_quarantine_probe.db`
- copied DB SHA-256 after apply: `09aab26b1f33e17e97e7b4df9bf83ba8445227091df73ed158468cd20bc3341e`
- integrity: `ok`
- applied on copied DB only with `ENABLE_HEADER_ONLY_SOURCE_GAP_QUARANTINE_TEMP_APPLY=1`

Copied DB apply result:

```text
candidate_rows=251
applied=True
deleted_stock_ledger_rows=0
deleted_product_cashflow_rows=7
nulled_sales_fact_product_profit_rows=0
fact_order_entries_inserted=0
```

Copied DB operational validator after apply:

```text
status RED
finding_count 496
ERROR ORDER_ENTRY_MISSING                                   219
ERROR ORDER_LIFECYCLE_MISSING_COMPLETED                       8
ERROR ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_ENTRY_LEAK            1
ERROR ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_PRODUCT_COGS_LEAK    1
WARN  ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_QUARANTINED         244
WARN  ORDER_ENTRY_PRODUCT_IDENTITY_QUARANTINED                23
```

The remaining header-only source-gap product/entry leak is `906730647`; it now has real API item-entry evidence and needs a separate de-quarantine or reclassification repair, not a header-only replay.

## Current Next-Best Repair Order

1. Repair the 219 `ORDER_ENTRY_MISSING` rows from real source evidence or strict quarantine.
2. Repair the 8 `ORDER_LIFECYCLE_MISSING_COMPLETED` rows.
3. Apply the 9 remaining owner-approval stock repairs only after exact owner evidence exists.
4. Rebuild the `2026-06-13` stock snapshot and replay C3.

## Production Apply Addendum

The production-safe wrapper was hardened and applied after this audit:

- closeout: `docs/agent_handoffs/GREEN_PATH_PHASE2_HEADER_ONLY_PROD_APPLY_20260614.md`
- evidence: `exports/validation/orchestrator_header_only_prod_apply_20260614/`
- result: `candidate_rows=251`, `deleted_product_cashflow_rows=7`, `deleted_stock_ledger_rows=0`, `cash_in_preserved=True`
- wrapper mode: `sqlite_in_place`, `target_replaced=False`
- operational stock finding count after apply: `496`

The `906730647` real-entry reclassification was then applied:

- closeout: `docs/agent_handoffs/GREEN_PATH_PHASE2_906730647_REAL_ENTRY_RECLASSIFICATION_20260614.md`
- evidence: `exports/validation/orchestrator_906730647_real_entry_reclassification_20260614/`
- result: `updated_rows=1`, `active_header_only_after=0`
- operational stock finding count after apply: `494`

## Safety Notes

- Production DB write occurred only in the later addendum lane, with backup and rollback evidence in `exports/validation/orchestrator_header_only_prod_apply_20260614/`.
- The `906730647` production DB write occurred only in its later addendum lane, with backup and rollback evidence in `exports/validation/orchestrator_906730647_real_entry_reclassification_20260614/`.
- No customer, Telegram, LaunchAgent, Kaspi merchant, pricing, workbook, or external-system write occurred.
- The earlier wrapper file-replacement stopline is closed by `GREEN_PATH_PHASE2_HEADER_ONLY_PROD_APPLY_20260614.md`; the wrapper now uses SQLite backup, staging proof, and in-place target apply.
