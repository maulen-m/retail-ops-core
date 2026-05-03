# LINE61 Bundle DB Ingest Handoff

Date: `2026-04-25`
Owner lane: Autonomous_business internal agent
Source identity spec: [LINE61_BUNDLE_IDENTITY_SPEC_2026-04-25.md](~/Docs/Oracle/Content/content/kaspi_bundles/line61_orange/LINE61_BUNDLE_IDENTITY_SPEC_2026-04-25.md)
Shared family architecture: [PAIRED_BUNDLE_COLOR_VARIANT_ARCHITECTURE_2026-04-23.md](~/Docs/Oracle/Content/content/kaspi_bundles/PAIRED_BUNDLE_COLOR_VARIANT_ARCHITECTURE_2026-04-23.md)

## Purpose

Prepare Autonomous_business to ingest the new compact Line61 bundle identities safely across the paired LS/TS lane and the standalone TK lane.

## Decision Summary

1. New Suit bundle family keys are compact:
   - `SUIT-21-LS`
   - `SUIT-21-TS`
   - `SUIT-31-LS`
   - `SUIT-31-TS`
   - `SUIT-21-TK`
   - `SUIT-31-TK`
2. Kaspi-facing row identity is:
   - `<sku_key>-<category>-<size-label>-<size-rus>`
3. `Артикул` and `Артикул производителя` are the same exact token.
4. `sku_id_ksp` matches that same exact token.
5. Normalized internal `sku_id` stays bucketed by `my_size`.
6. Paired LS/TS bundles use shared family ids with LINE.
7. Standalone TK bundles use Suit-only category-specific family ids.

## Canonical Field Rules

| Field | Exact value rule |
|---|---|
| `sku_key` | Suit bundle family token only |
| `family_id` | paired shared-family token for LS/TS, Suit-only token for TK |
| `sku_id_ksp` | exact Kaspi row token |
| `Артикул` | exact Kaspi row token |
| `Артикул производителя` | same as `Артикул` |
| `SKU_ID (normalized)` | `<sku_key>_<my_size>` |
| `Код изображений` | category-specific, size-free token |
| `Комплектация` | garments only, no gift bag |

## Exact Bundle Matrix

| Filesystem bundle id | `sku_key` | Sport `family_id` | Thermal `family_id` |
|---|---|---|---|
| `blk-21_ls` | `SUIT-21-LS` | `PAIR-21-LS-ST` | `PAIR-21-LS-TRM` |
| `blk-21_ts` | `SUIT-21-TS` | `PAIR-21-TS-ST` | `PAIR-21-TS-TRM` |
| `blk-31_ls` | `SUIT-31-LS` | `PAIR-31-LS-ST` | `PAIR-31-LS-TRM` |
| `blk-31_ts` | `SUIT-31-TS` | `PAIR-31-TS-ST` | `PAIR-31-TS-TRM` |
| `blk-21_tk` | `SUIT-21-TK` | `SUIT-21-TK-ST` | `SUIT-21-TK-TRM` |
| `blk-31_tk` | `SUIT-31-TK` | `SUIT-31-TK-ST` | `SUIT-31-TK-TRM` |

## Exact Token Examples

| `sku_key` | Sport row example | Thermal row example | Normalized `sku_id` example |
|---|---|---|---|
| `SUIT-21-LS` | `SUIT-21-LS-ST-XL-48` | `SUIT-21-LS-TRM-XL-50` | `SUIT-21-LS_XL` |
| `SUIT-21-TS` | `SUIT-21-TS-ST-S-42` | `SUIT-21-TS-TRM-3XL-54` | `SUIT-21-TS_S` |
| `SUIT-31-LS` | `SUIT-31-LS-ST-2XL-52` | `SUIT-31-LS-TRM-4XL-60` | `SUIT-31-LS_2XL` / `SUIT-31-LS_4XL` |
| `SUIT-31-TS` | `SUIT-31-TS-ST-L-46` | `SUIT-31-TS-TRM-XL-48` | `SUIT-31-TS_L` |
| `SUIT-21-TK` | `SUIT-21-TK-ST-M-44` | `SUIT-21-TK-TRM-4XL-58` | `SUIT-21-TK_M` / `SUIT-21-TK_4XL` |
| `SUIT-31-TK` | `SUIT-31-TK-ST-3XL-54` | `SUIT-31-TK-TRM-4XL-56` | `SUIT-31-TK_3XL` / `SUIT-31-TK_4XL` |

## Required DB / Workbook Updates

1. Upsert six new `dim_sku` rows using the compact `SUIT-..` bundle families.
2. Upsert normalized `dim_sku_size` rows for every bucketed size per Suit bundle family.
3. Upsert exact Kaspi article mappings in `dim_kaspi_article_map` for both `ST` and `TRM`.
4. Ensure workbook ingest uses:
   - `SKU_ID_KSP (prepared)` = exact Kaspi row token
   - `Merchant SKU` = exact Kaspi row token
   - `SKU_key` = compact bundle family token
   - `SKU_ID (normalized)` = compact bundle family + normalized size

## Guardrails

1. `XL-48` and `XL-50` remain distinct in `sku_id_ksp`, but both map to normalized `sku_id = ..._XL`.
2. `4XL-56`, `4XL-58`, and `4XL-60` remain distinct in `sku_id_ksp`, but all map to normalized `sku_id = ..._4XL`.
3. Paired LS/TS rows must not collapse Suit and LINE into one `sku_key`; only `family_id` is shared.
