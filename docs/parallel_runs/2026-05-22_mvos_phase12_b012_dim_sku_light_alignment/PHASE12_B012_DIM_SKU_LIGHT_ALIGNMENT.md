# Phase 12 B012 DIM_SKU_light Alignment Repair

Status: `B012_DIM_SKU_ALIGNMENT_COPIED_TEMP_CLOSED_SOURCE_AUTHORITY_REVIEW_RETAINED`
Created: `2026-05-22`

This is a non-production blocker-closure lane. It does not authorize production DB writes, workbook writes, source-pointer writes, scheduler/LaunchAgent/cron changes, Web_automation writes, Kaspi/API/WebUI writes, external writes, ad-platform writes, cash movement, PO commitment, stock changes, price changes, owner publication, production preflight, or production apply.

## Purpose

Phase 11 reduced `B012_may21_drift_pack_critical` from COGS `CRITICAL` to drift-pack `WARN`, but the pack still contained this warning:

```text
dim_sku_alignment status=error
Failed to locate DIM_SKU_light header row
```

The Phase 12 goal was to determine whether that warning was a true missing-source blocker or a parser/schema blocker caused by the current `DIM_SKU_light_v7` workbook shape.

## Evidence Boundary

Evidence root:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase12_b012_dim_sku_light_alignment/agent21_dim_sku_light_evidence`

Copied DB:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-22_mvos_phase12_b012_dim_sku_light_alignment/agent21_dim_sku_light_evidence/copied_db/agent21_b012_dim_sku_light_copied_temp.db`

Workbook read-only source:

`~/Documents/useful tables/Main crm spreadsheets/main tables/Purchase_orders/vibe_code_PO/Inbound_calendar_V10.002.xlsx`

Sheet:

`DIM_SKU_light_v7`

## Repair

The canonical parser `core.excel.dim_sku_light_parser.parse_dim_sku_light` now supports the current one-column markdown pipe-table workbook shape while preserving the existing tabular Excel path.

Focused proof:

```text
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_dim_sku_light_parser.py tests/test_validate_dim_sku_light_alignment.py
7 passed in 0.47s
```

Parser diagnostics on the live workbook:

```json
{
  "header_row_index": 97,
  "rows_scanned": 47,
  "rows_valid": 47,
  "filtered_helper_rows": 0,
  "filtered_invalid_sku_rows": 0,
  "duplicate_sku_keys": 0,
  "selected_rows": 47,
  "source_format": "markdown_pipe_table"
}
```

## Result Before Copied-Temp Sync

`validate_dim_sku_light_alignment.py` no longer fails with `Failed to locate DIM_SKU_light header row`.

It now reaches the real alignment gate:

```text
dim_sku_light_alignment: compared=34 weight_mismatches=10 base_mismatches=11
WARN: base-cost reference drift against dim_sku_light workbook: 11
ERROR: weight mismatches against dim_sku_light workbook: 10
```

The existing dry-run/apply-gated sync path confirmed the exact copied-temp repair shape:

```text
dim_sku light sync DRY-RUN: parsed=47 compared=34 missing_in_db=3 would_update=10
updates: weight=10 base=0 applied=0 large_weight_shift=0
parser: header_row=97 valid=47 helper_filtered=0 invalid_sku_filtered=0 duplicates=0
```

## Copied-Temp Sync Proof

The existing guarded writer was then applied to the copied DB only:

```text
ENABLE_DIM_SKU_SYNC_WRITE=1 python3 scripts/sync_dim_sku_from_dim_sku_light.py --db <copied_db> --apply
dim_sku light sync APPLY: parsed=47 compared=34 missing_in_db=3 would_update=10
updates: weight=10 base=0 applied=10 large_weight_shift=0
parser: header_row=97 valid=47 helper_filtered=0 invalid_sku_filtered=0 duplicates=0
```

After that copied-temp-only sync, the alignment validator passed:

```text
dim_sku_light_alignment: compared=34 weight_mismatches=0 base_mismatches=11
WARN: base-cost reference drift against dim_sku_light workbook: 11
OK: dim_sku light alignment passed
```

Detailed evidence:

- `reports/dim_sku_light_alignment_summary.json`
- `reports/dim_sku_light_alignment_full_report.json`
- `reports/dim_sku_light_alignment_after_copied_db_sync_summary.json`
- `reports/dim_sku_light_alignment_after_copied_db_sync_full_report.json`
- `reports/dim_sku_light_parser_diagnostics.json`
- `reports/dim_sku_light_v7_top_rows_source_authority.json`
- `reports/weight_mismatches.csv`
- `reports/base_mismatches.csv`
- `reports/dim_sku_light_selected_rows.csv`
- `reports/copied_db_dim_sku_weights_after_sync.csv`

## Retained Yellow

This lane is `YELLOW`, not `GREEN`.

The closed portion is narrow:

- closed: parser/schema compatibility for markdown-style `DIM_SKU_light_v7`;
- closed in copied-temp only: `10` weight mismatches can be repaired by the existing guarded sync path on a copied DB;
- retained for production/final authority: `DIM_SKU_light_v7` row 5 describes itself as `Status: fallback planning anchor, not operational truth`, and older repo decisions identify weight restore as an explicit controlled path, so CodeCaptain/owner review is still needed before any production route;
- retained: `11` base-cost reference drifts, currently warning-only because base-cost enforcement remains disabled in this validator;
- retained: `B012` daily autonomy, because Phase 11 also retained `133` on-delivery residuals and default/repeated-run drift-pack autonomy is not green.

## Next Best Route

The next safe `B012` moves are:

- separately classify the `133` on-delivery residuals instead of hiding them under the DIM_SKU repair;
- ask CodeCaptain whether the copied-temp `DIM_SKU_light_v7` sync proof is acceptable as the DIM_SKU subgate closure despite the fallback-anchor/source-authority nuance;
- if accepted, wire the same parser path into the default drift-pack route and rerun the full copied-temp daily-autonomy matrix before any production-preflight conversation.
