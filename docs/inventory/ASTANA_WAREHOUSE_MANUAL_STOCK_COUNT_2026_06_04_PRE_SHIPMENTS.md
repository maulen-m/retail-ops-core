# Astana Warehouse Manual Stock Count - 2026-06-04 Pre-Shipments

Status: owner-approved local physical stock count for mapped rows; DB apply not included.

Canonical machine-readable source:

- `config/anchors/manual_stock_counts/astana_warehouse_manual_stock_count_2026_06_04_pre_shipments.approved.json`
- `config/anchors/manual_stock_counts/astana_warehouse_manual_stock_count_2026_06_04_pre_shipments.approved_aggregate.csv`

Timing:

- Effective anchor timestamp: `2026-06-04T14:00:23+05:00`.
- Counted before the 04.06.2026 daily Kaspi shipments.
- Replay must subtract trusted 04.06 daily shipments and later shipped/order movements after the anchor.

Scope notes:

- `3_in_1_men_sets` is quarantined because canonical SKU/card mapping is pending.
- `CL_OC_MEN_LINE51_WHITE_S` is not materialized, overwritten, zeroed, or unknown-filled.
- Rombik `S` remains one shared men/kids stock pool.

Totals:

- Materialized rows: `66`.
- Materialized units: `3989`.
- Quarantined mapping-pending units: `273`.
- OCR roll-up reference total excluding LINE51 S: `5786`.

Dry-run replay:

- Evidence folder: `~/Docs/Autonomous_business/exports/validation/manual_stock_20260604_pre_shipments_dryrun_20260611`.
- Trusted post-anchor shipped quantity on materialized rows: `119`.
- Latest DB snapshot compared as before-state: `2026-05-31`.
- No DB write was performed.

Validation:

Use:

```bash
python3 -m core.ops.manual_stock_count_manifest --manifest ~/Docs/Autonomous_business/config/anchors/manual_stock_counts/astana_warehouse_manual_stock_count_2026_06_04_pre_shipments.approved.json
```
