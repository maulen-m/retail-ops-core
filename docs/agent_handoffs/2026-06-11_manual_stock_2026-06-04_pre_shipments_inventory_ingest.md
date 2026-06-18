# Inventory Agent Handoff - 2026-06-04 Manual Stock Pre-Shipment Ingest

## Objective

Ingest the new warehouse OCR/manual stock records from the 2026-06-04 counting folder into Autonomous_business inventory truth, preserving traceability and correct event timing.

This handoff is **not live-write approval by itself**. Do read-only/dry-run first. Before any `db/app.db` mutation, back up the DB, use the repo write-enable gate, and stop on any route/mapping/stock mismatch.

## Repo

Work in:

```bash
cd ~/Docs/Autonomous_business
```

Read first:

- `~/Docs/Autonomous_business/AGENTS.md`
- `docs/00_START_HERE.md`
- `.claude/OPERATING.md`
- `docs/inventory/Master_Inventory_Rules_v9.md`
- `core/ops/manual_stock_count_manifest.py`
- `docs/inventory/ASTANA_WAREHOUSE_MANUAL_STOCK_COUNT_2026_05_30_2026_06_02.md`

## Source Evidence

Primary OCR report:

- `~/Downloads/Stock_ingestion_from_warehouse_counting/warehouse_stock_count_manual_results/images/04.06.2026_14_00_23/stock_count_04.06.2026_14_00.md`

Merged TOTAL append:

- `~/Downloads/Stock_ingestion_from_warehouse_counting/warehouse_stock_count_manual_results/TOTAL_stock_count_all.md`

Source images:

- `~/Downloads/Stock_ingestion_from_warehouse_counting/warehouse_stock_count_manual_results/images/04.06.2026_14_00_23`

Existing AB manual manifest to preserve as prior authority:

- `config/anchors/manual_stock_counts/astana_warehouse_manual_stock_count_2026_05_30_2026_06_02.approved.json`
- `config/anchors/manual_stock_counts/astana_warehouse_manual_stock_count_2026_05_30_2026_06_02.approved_aggregate.csv`

## Critical Timing Rule

The 2026-06-04 folder was counted **before the 04.06.2026 daily Kaspi order shipments**, not today and not after that day's shipments.

Use effective anchor timestamp:

```text
2026-06-04T14:00:23+05:00
```

Inventory replay rule:

- Anchor the provided SKU-size rows at the pre-shipment count.
- Then subtract trusted 2026-06-04 daily Kaspi shipments and all later shipped/order movements.
- If order timestamps are not granular enough to determine before/after count, owner instruction is to treat the 04.06 daily shipment batch as **after** this count and subtract it.
- Do not subtract any movement twice if a downstream current-stock rebuild already replayed it from this same anchor.

## Merge Semantics

Apply the red-label/source semantics exactly:

- Normal product label or `update`: latest replacement for the provided product/color/size rows only.
- `addition`: add the listed quantities on top of the latest already-ingested count for that exact product/color/size, then materialize the effective quantity as of `2026-06-04T14:00:23+05:00`.
- Missing size policy: absent sizes are **not zero** and are **not overwritten**.
- LINE51 `S` is not re-provided in the image. Do not overwrite, zero, or create an unknown replacement for `CL_OC_MEN_LINE51_WHITE_S`. Preserve the latest separately approved LINE51 `S` source if one exists; otherwise leave it absent.
- Shared pools must not be double-counted. Rombik `S` remains one shared men/kids pool.

## 2026-06-04 Effective Rows To Materialize

Use these as the effective pre-shipment quantities after applying replacement/addition semantics to prior OCR truth:

| Scope | SKU key / note | Effective pre-shipment quantities |
|---|---|---|
| Line52 black | `CL_OC_MEN_LINE52_BLACK` | M 42, L 129, 2XL 4, 3XL 83, 4XL 32 |
| Rombik men black, non-shared | `CL_NEW-CLO_MEN_ROMBIK_BLACK` | M 21, L 45, XL 5, 2XL 29, 3XL 21, 4XL 17 |
| Rombik shared S pool | `CL_NEW-CLO_MEN_ROMBIK_BLACK_S` / kid alias | S 75, shared men/kids pool, do not double-count |
| Line61 black | `CL_NEW-CLO2_MEN_SUIT-61_BLACK` | S 43, M 96, L 143, XL 93, 2XL 69, 3XL 24, 4XL 9 |
| Leggings white | `CL_NEW-CLO_MEN_LEG_WHITE` | S 19, M 34, L 97, XL 118, 2XL 79, 3XL 86 |
| Leggings black | `CL_NEW-CLO_MEN_LEG_BLACK` | S 16, M 17, L 56, XL 57, 2XL 52, 3XL 36 |
| kids31 black | `CL_NEW-CLO_KIDS_KID-31_BLACK` | 110/22 12, 120/24 9, 130/26 54, 140/28 33, 150/30 29 |
| Nike shirt white | `CL_NEW-CLO_MEN_NIKE-SHIRT_WHITE` | S 33, M 78, L 101, XL 51, 2XL 50, 3XL 22 |
| Nike shirt black | `CL_NEW-CLO_MEN_NIKE-SHIRT_BLACK` | S 46, M 21, L 153, XL 17, 2XL 47, 3XL 91 |
| Nike shirt grey | `CL_NEW-CLO_MEN_NIKE-SHIRT_GREY` | S 23, M 67, L 105, XL 80, 2XL 40, 3XL 22 |
| Shorts black | `CL_NC_MEN_SHORTS_BLACK` | S 20, M 40, L 79, XL 111, 2XL 80, 3XL 58, 4XL 20 |
| LINE51 black/white set | `CL_OC_MEN_LINE51_WHITE` family | M 105, L 190, XL 216, 2XL 145, 3XL 94; S no override |
| 3_in_1_men_sets | mapping pending | S 58, M 30, L 45, XL 65, 2XL 47, 3XL 28; quarantine until canonical SKU/card mapping is proven |

Known total represented by the current OCR roll-up is `5786` units excluding LINE51 `S` not re-provided. Do not use that total as a DB invariant if prior LINE51 `S` is preserved from another approved source.

## Implementation Guidance

Preferred safe path:

1. Create a new timestamped manual-stock anchor artifact, for example:
   - `config/anchors/manual_stock_counts/astana_warehouse_manual_stock_count_2026_06_04_pre_shipments.approved.json`
   - `config/anchors/manual_stock_counts/astana_warehouse_manual_stock_count_2026_06_04_pre_shipments.approved_aggregate.csv`
2. Do not silently rewrite the old 2026-05-30-to-2026-06-02 manifest. If you need multi-manifest consumption, update the loader to select latest covered SKU-size/shared-pool rows by `count_timestamp_at_almaty`.
3. If the current v1 manifest schema cannot represent addition provenance cleanly, materialize final effective quantities in the new manifest and preserve `source_event_type`, `source_delta`, and `prior_source` in row metadata or a sidecar.
4. Verify every SKU id/size mapping against canonical `dim_sku` / `dim_sku_size` before apply. Stop on any missing SKU, especially `3_in_1_men_sets`.
5. Build a dry-run current-stock replay from the 2026-06-04 pre-shipment anchor through today using trusted Kaspi shipped/order movements.
6. Compare before/after current stock by SKU-size, and produce an evidence CSV and Markdown summary.

## Required Stoplines

Stop and report if:

- `3_in_1_men_sets` cannot be mapped exactly to a canonical SKU/product offer route.
- Any LINE51 `S` path would be overwritten, zeroed, or set to unknown by this batch.
- 04.06 shipment replay cannot be proven or would be double-subtracted.
- Shared Rombik `S` pool appears twice in totals.
- Any canonical SKU-size mapping conflicts with Kaspi offer/card naming.
- Any validation gate fails.

## Suggested Validation

At minimum:

```bash
python3 -m core.ops.manual_stock_count_manifest
pytest -q tests/test_manual_stock_count_manifest.py
python3 scripts/validate_product_truth_canonicalization.py
```

Before DB apply, also follow repo write safety:

```bash
python3 scripts/validate_params.py --strict
python3 scripts/run_end_of_day.py --verbose
pytest -q
scripts/check_no_db_tracked.sh
```

If applying to `db/app.db`, create and record a DB backup path first. Use explicit write-enable env gates and `--apply`; otherwise remain dry-run/read-only.

## Closeout Required

Write a closeout with:

- New manifest/CSV paths.
- Whether `3_in_1_men_sets` was ingested or quarantined.
- LINE51 `S` handling proof.
- 04.06 shipment replay proof and source query/window.
- Before/after stock diff by SKU-size.
- Commands run and pass/fail results.
- DB backup path and rollback instructions if any DB write occurred.
