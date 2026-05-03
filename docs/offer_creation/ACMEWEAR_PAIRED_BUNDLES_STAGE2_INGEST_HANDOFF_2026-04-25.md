# ACMEWEAR Paired Bundles Stage-2 Ingest Handoff

Date: `2026-04-25`
Owner lane: Autonomous_business internal ingestion agent

Primary source docs:
- [LINE61_BUNDLE_IDENTITY_SPEC_2026-04-25.md](~/Docs/Oracle/Content/content/kaspi_bundles/line61_orange/LINE61_BUNDLE_IDENTITY_SPEC_2026-04-25.md)
- [LINE51_BUNDLE_IDENTITY_SPEC_2026-04-23.md](~/Docs/Oracle/Content/content/kaspi_bundles/line51_orange/LINE51_BUNDLE_IDENTITY_SPEC_2026-04-23.md)
- [PAIRED_BUNDLE_COLOR_VARIANT_ARCHITECTURE_2026-04-23.md](~/Docs/Oracle/Content/content/kaspi_bundles/PAIRED_BUNDLE_COLOR_VARIANT_ARCHITECTURE_2026-04-23.md)
- [LINE61_BUNDLE_DB_INGEST_HANDOFF_2026-04-25.md](~/Docs/Autonomous_business/docs/offer_creation/LINE61_BUNDLE_DB_INGEST_HANDOFF_2026-04-25.md)
- [LINE51_BUNDLE_DB_INGEST_HANDOFF_2026-04-23.md](~/Docs/Autonomous_business/docs/offer_creation/LINE51_BUNDLE_DB_INGEST_HANDOFF_2026-04-23.md)

Package roots to validate after DB ingest:
- `~/Docs/Business2/Content/Content_db_1/Kaspi/Product_offers/Line61/Orange/bundles`
- `~/Docs/Business2/Content/Content_db_1/Kaspi/Product_offers/Line51/Orange/bundles`

## Purpose

Clear `stage2_product_truth_pending` for the current ACMEWEAR bundle rollout by ingesting the new compact Line61 + Line51 bundle identities into Autonomous_business truth.

This handoff is the stage between:

1. package preparation being complete
2. live ACMEWEAR Kaspi master upload beginning

This agent does **not** upload to Kaspi.
This agent owns only:

- DB truth
- parser / mapping truth
- validation reruns
- evidence that the SKU-alignment gate is green

## Current Situation

Package generation is already green:

- Line61 package layouts: `12/12` valid
- Line51 package layouts: `8/8` valid

The remaining red gate is identity truth:

- every rebuilt XLSM currently fails with `unresolved SKU mapping`
- example token:
  - `SUIT-21-TS-ST-S-42`
  - `LINE-21-LS-TRM-S-42`

That failure means:

- the XLSM rows are already using the new compact tokens correctly
- but those tokens do not yet exist in Autonomous_business truth tables

So this is a DB-ingest / parser-alignment task, not a Content/package task.

## Locked Scope

### Product families in scope

Suit:

- `SUIT-21-LS`
- `SUIT-21-TS`
- `SUIT-31-LS`
- `SUIT-31-TS`
- `SUIT-21-TK`
- `SUIT-31-TK`

Beli:

- `LINE-21-LS`
- `LINE-21-TS`
- `LINE-31-LS`
- `LINE-31-TS`

### Category variants in scope

- sport: `ST`
- thermal: `TRM`

### Exact rollout coverage

- bundle families: `10`
- category variants: `20`
- exact Kaspi article tokens to cover: `200`
- normalized `dim_sku_size` rows to cover: `70`

## Locked Identity Truth

### Shared paired `family_id` values

These are shared between matching Suit and Beli LS/TS bundles:

- `PAIR-21-LS-ST`
- `PAIR-21-LS-TRM`
- `PAIR-21-TS-ST`
- `PAIR-21-TS-TRM`
- `PAIR-31-LS-ST`
- `PAIR-31-LS-TRM`
- `PAIR-31-TS-ST`
- `PAIR-31-TS-TRM`

### Standalone Suit TK `family_id` values

- `SUIT-21-TK-ST`
- `SUIT-21-TK-TRM`
- `SUIT-31-TK-ST`
- `SUIT-31-TK-TRM`

### Exact row-token pattern

For every bundle row:

`<sku_key>-<category-token>-<size-label>-<size-rus>`

Examples:

- `SUIT-21-LS-ST-S-42`
- `SUIT-31-TK-TRM-4XL-60`
- `LINE-21-LS-ST-XL-48`
- `LINE-31-TS-TRM-2XL-52`

### Exact size token set

- `S-42`
- `M-44`
- `L-46`
- `XL-48`
- `XL-50`
- `2XL-52`
- `3XL-54`
- `4XL-56`
- `4XL-58`
- `4XL-60`

### Normalized size rule

Exact Kaspi row token stays full-resolution, but normalized internal `sku_id` stays bucketed:

- `XL-48` and `XL-50` -> normalized `_XL`
- `4XL-56`, `4XL-58`, `4XL-60` -> normalized `_4XL`

Examples:

- `SUIT-21-LS-ST-XL-48` -> `SUIT-21-LS_XL`
- `SUIT-21-LS-ST-XL-50` -> `SUIT-21-LS_XL`
- `LINE-31-TS-TRM-4XL-56` -> `LINE-31-TS_4XL`
- `LINE-31-TS-TRM-4XL-60` -> `LINE-31-TS_4XL`

## Required Write Targets

### 1. `dim_sku`

Upsert all `10` compact bundle-family `sku_key` rows.

### 2. `dim_sku_size`

Upsert normalized size rows for every in-scope family:

- `_S`
- `_M`
- `_L`
- `_XL`
- `_2XL`
- `_3XL`
- `_4XL`

Total target rows: `70`

### 3. `dim_kaspi_article_map`

Upsert all `200` exact Kaspi-facing row tokens.

Each token must resolve to:

- `sku_key`
- normalized `sku_id`
- normalized `my_size`
- exact `Size RUS`
- `store_code = ACMEWEAR` where store-scoped mapping is used

### 4. Parser / resolution truth

The ingest path must not rely on legacy underscore-only heuristics for these bundles.

Safe resolution order:

1. `dim_kaspi_article_map`
2. explicit bundle regex fallback
3. only then legacy heuristics

Recommended explicit regex fallbacks:

Suit:

`^(SUIT-\d{2}-(?:LS|TS|TK))-(ST|TRM)-(S|M|L|XL|2XL|3XL|4XL)-(\d{2})$`

Beli:

`^(LINE-\d{2}-(?:LS|TS))-(ST|TRM)-(S|M|L|XL|2XL|3XL|4XL)-(\d{2})$`

Resolution from regex:

- `sku_key` = group 1
- category token = group 2
- size label = group 3
- `Size RUS` = group 4
- normalized `my_size` = group 3
- normalized `sku_id` = `<sku_key>_<my_size>`
- `sku_id_ksp` = full exact token

## Required Invariants

1. `Артикул` and `Артикул производителя` must resolve to the same exact `sku_key`.
2. No compact bundle token may fall through to old underscore parsing first.
3. Shared `family_id` must be category-specific and exact.
4. `Код изображений` must be category-specific and size-free:
   - `SUIT-21-LS-ST`
   - `SUIT-21-LS-TRM`
   - `LINE-31-TS-ST`
   - etc.
5. `Комплектация` is already correct in the XLSMs and must remain garments-only.

## Execution Checklist

1. Back up `db/app.db` before any write.
2. Record the backup path in the run evidence.
3. Upsert `dim_sku` for all 10 compact bundle families.
4. Upsert `dim_sku_size` for all normalized family-size combinations.
5. Upsert `dim_kaspi_article_map` for all 200 exact row tokens.
6. Update bundle token resolution so map lookup happens before legacy heuristics.
7. Re-run the SKU alignment validator against all current bundle XLSMs under the two Business2 package roots.
8. Confirm the previous `unresolved SKU mapping` errors are gone.
9. Re-run any downstream truth replay needed so the stopline can move from `stage2_product_truth_pending` to upload-ready.

## Minimum Validation Required

Repo gates:

- `scripts/lint_docs.sh`

Identity / offer gates:

- `python3 scripts/validate_kaspi_offer_template.py ...` for all in-scope package XLSMs

Recommended result expectation:

- zero `unresolved SKU mapping` errors
- zero ambiguous mappings
- zero merchant/manufacturer mismatches

## Success Criteria

This handoff is complete only when all of the following are true:

1. Every current Line61 and Line51 bundle XLSM resolves cleanly through DB truth.
2. `dim_sku` contains all compact bundle families.
3. `dim_kaspi_article_map` contains all exact compact Kaspi row tokens.
4. No validator report contains `unresolved SKU mapping`.
5. The rollout can truthfully remove `stage2_product_truth_pending` as the remaining blocker.

## Still Out Of Scope After This Agent

These are **not** owned by this ingestion handoff:

- live ACMEWEAR master upload to Kaspi
- collecting the new public Kaspi card URLs
- secondary-store UI onboarding
- replacing or reordering any images

Those happen only after this DB truth lane is green.

## Suggested Deliverables Back

Return one compact evidence note containing:

- DB backup path
- exact tables updated
- counts inserted / upserted
- validator commands run
- validator summary before vs after
- any residual blockers, if something still fails
