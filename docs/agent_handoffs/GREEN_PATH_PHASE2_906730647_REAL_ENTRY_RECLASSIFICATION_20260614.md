# Green Path Phase 2 906730647 Real-Entry Reclassification

Gate: GREEN

Date: 2026-06-14

## Scope

This lane resolved the remaining STOREB header-only source-gap leak for order `906730647`.

The stale header-only quarantine row claimed there was no real item-entry evidence. Current DB truth now has a real Kaspi API entry for the same order:

```text
entry_id=OTA2NzMwNjQ3IyMw
product_id=MTM1Mzk2MTky
offer_code=CL_NEW-CLO_MEN_RUSH_WHITE_XL_135396192
header_sku_id=CL_NEW-CLO_MEN_RUSH_WHITE_XL
```

The repair deactivated the stale header-only quarantine row. It did not delete product cashflow, did not delete or insert order-entry rows, and did not use header fields as canonical item-entry truth.

Overall Phase 2 remains blocked by separate order-entry, lifecycle, and owner-approval stock issues.

## Implementation

Added:

- `scripts/materialize_header_only_real_entry_reclassification.py`
- `tests/test_header_only_real_entry_reclassification.py`

The materializer is fail-closed:

- requires `ENABLE_HEADER_ONLY_REAL_ENTRY_RECLASSIFICATION_APPLY=1` for apply,
- requires `--expected-pre-sha256` for apply,
- refuses SQLite sidecars,
- requires exactly one active header-only row,
- requires exactly one real API entry,
- requires the API offer code to match the header SKU/size prefix,
- requires the expected product-cashflow and stock-reference counts,
- creates a SQLite backup before mutation.

## Evidence

Evidence root:

- `exports/validation/orchestrator_906730647_real_entry_reclassification_20260614/`

Copied DB proof v2:

- summary: `exports/validation/orchestrator_906730647_real_entry_reclassification_20260614/copied_db_apply_v2/summary.json`
- result: `updated_rows=1`, `active_header_only_after=0`
- operational validator after copied apply: `finding_count=494`

Production apply:

- summary: `exports/validation/orchestrator_906730647_real_entry_reclassification_20260614/prod_apply/summary.json`
- pre-SHA: `04a1e8a1ffbd0530ca6a435050f9d71a670d6f3e5eef4ffa4b350d5a6e347116`
- post-SHA: `16f80740ef01928dd94f2180f4ace1116e37e80f751d54022278bca0e767840b`
- backup: `exports/validation/orchestrator_906730647_real_entry_reclassification_20260614/backups/app_2026-06-14_011044.db`
- backup SHA: `fccf18601a22cef9b8ba8446115cf9d060072aed3c7ce70526dc916029eed40c`

Production before:

```text
active_header_only_count=1
api_entry_count=1
api_entries_with_offer_matching_header_sku_id=1
product_cashflow_reference_count=1
stock_ledger_reference_count=0
```

Production after:

```text
active_header_only_count=0
api_entry_count=1
product_cashflow_reference_count=1
stock_ledger_reference_count=0
```

DB row state after apply:

```text
active_flag=0
publication_exclusion_required=0
product_stock_excluded=0
product_cogs_excluded=0
product_profit_excluded=0
sku_publication_excluded=0
owner_or_codecaptain_review_status=SUPERSEDED_BY_REAL_API_ENTRY_EVIDENCE
```

Daily-ops safety:

- before apply v2: `exports/validation/orchestrator_906730647_real_entry_reclassification_20260614/daily_ops_paused_before_prod_apply_v2.json`
- after apply: `exports/validation/orchestrator_906730647_real_entry_reclassification_20260614/daily_ops_paused_after_prod_apply.json`
- result: `0/10` loaded, protected surfaces quiet, cron quiet.

## Validation

Focused tests:

```bash
pytest -q tests/test_header_only_real_entry_reclassification.py tests/test_header_only_source_gap_quarantine.py tests/test_header_only_source_gap_quarantine_prod_wrapper.py
python3 -m py_compile scripts/materialize_header_only_real_entry_reclassification.py
```

Result:

```text
14 passed
py_compile passed
```

Operational stock integration after production apply:

- file: `exports/validation/orchestrator_906730647_real_entry_reclassification_20260614/operational_stock_after_prod_apply.json`
- status: `RED`
- finding_count: `494`

Post-apply finding census:

```text
ERROR ORDER_ENTRY_MISSING                                   219
ERROR ORDER_LIFECYCLE_MISSING_COMPLETED                       8
WARN  ORDER_ENTRY_HEADER_ONLY_SOURCE_GAP_QUARANTINED         244
WARN  ORDER_ENTRY_PRODUCT_IDENTITY_QUARANTINED                23
```

C3 strict validators after production apply:

```text
Required source src_ab_db_stock_truth freshness for requested as-of 2026-06-13 is STALE and blocks publication (blocks_publication=1)
Required C3 gate source_freshness is BLOCKED and blocks owner publication
Required C3 gate stock_source_truth is BLOCKED and blocks owner publication
```

Remaining negative stock rows:

- `exports/validation/orchestrator_906730647_real_entry_reclassification_20260614/negative_stock_rows_20260613.txt`

## Rollback

Rollback DB backup:

```text
~/Docs/Autonomous_business/exports/validation/orchestrator_906730647_real_entry_reclassification_20260614/backups/app_2026-06-14_011044.db
```

Rollback command is recorded in the production summary. Then verify:

```bash
sqlite3 -readonly db/app.db 'PRAGMA integrity_check;'
```

## Remaining Work

Next repair queue:

1. Repair or strictly quarantine the 219 `ORDER_ENTRY_MISSING` rows.
2. Repair the 8 `ORDER_LIFECYCLE_MISSING_COMPLETED` rows.
3. Apply the 9 owner-approval stock rows only after exact approval evidence exists.
4. Rebuild the 2026-06-13 stock snapshot and replay C3.

