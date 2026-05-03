# LINE51 Bundle DB Ingest Handoff

Date: `2026-04-23`
Owner lane: Autonomous_business internal agent
Source identity spec: [LINE51_BUNDLE_IDENTITY_SPEC_2026-04-23.md](~/Docs/Oracle/Content/content/kaspi_bundles/line51_orange/LINE51_BUNDLE_IDENTITY_SPEC_2026-04-23.md)
Shared family architecture: [PAIRED_BUNDLE_COLOR_VARIANT_ARCHITECTURE_2026-04-23.md](~/Docs/Oracle/Content/content/kaspi_bundles/PAIRED_BUNDLE_COLOR_VARIANT_ARCHITECTURE_2026-04-23.md)

## Purpose

Prepare Autonomous_business to ingest the new compact Line51 bundle identities safely.

This handoff covers:

- exact `sku_key` naming
- exact `sku_id_ksp` naming
- exact Kaspi row tokens for all Beli bundle offers
- normalized `sku_id` mapping
- DB tables that must be updated
- parser/gate implications before live upload

## Decision Summary

1. New bundle family keys are compact:
   - `LINE-21-LS`
   - `LINE-21-TS`
   - `LINE-31-LS`
   - `LINE-31-TS`
2. Kaspi-facing row identity is the exact full token:
   - `<bundle-family>-<category>-<size-label>-<size-rus>`
3. `Артикул` and `Артикул производителя` are the same exact token.
4. `SKU_ID_KSP (prepared)` must equal that same exact token.
5. Internal normalized `sku_key` is Beli-product-specific and bundle-family only.
6. Internal normalized `sku_id` stays on the existing size-bucket model:
   - `LINE-21-LS_S`
   - `LINE-21-LS_XL`
   - `LINE-31-TS_4XL`
7. `XL-48` and `XL-50` both map to normalized `my_size = XL`.
8. `4XL-56`, `4XL-58`, and `4XL-60` all map to normalized `my_size = 4XL`.
9. `family_id` is shared with the paired Line61 bundle for the same set composition and category.

## Why This Shape

This keeps three things true at the same time:

1. Kaspi and workbook rows stay human-readable and size-specific.
2. Order review still shows approximate Russian size directly in the article.
3. Internal inventory logic stays compatible with the current normalized size buckets and does not require a size-model expansion in the same rollout.

## Coverage Summary

- Bundle families: `4`
- Category variants: `8`
- Exact Kaspi-facing row tokens: `80`
- Normalized `dim_sku_size` rows: `28`
  - `7` normalized sizes per bundle family

## Canonical Field Rules

| Field | Exact value rule |
|---|---|
| `sku_key` | Beli bundle family token only |
| `family_id` | shared paired-family token, category-specific |
| `sku_id_ksp` | exact Kaspi row token |
| `Артикул` | exact Kaspi row token |
| `Артикул производителя` | same as `Артикул` |
| `Merchant SKU` in workbook blocks | exact Kaspi row token |
| `SKU_ID (normalized)` | `<sku_key>_<my_size>` |
| `Probable Size` | normalized size label only |
| `Size RUS` | numeric size from Kaspi row token |
| `Код изображений` | category-specific, size-free token |

## Canonical Size Mapping

| Exact size token | `my_size` | `Size RUS` | Normalized `sku_id` suffix |
|---|---|---:|---|
| `S-42` | `S` | `42` | `_S` |
| `M-44` | `M` | `44` | `_M` |
| `L-46` | `L` | `46` | `_L` |
| `XL-48` | `XL` | `48` | `_XL` |
| `XL-50` | `XL` | `50` | `_XL` |
| `2XL-52` | `2XL` | `52` | `_2XL` |
| `3XL-54` | `3XL` | `54` | `_3XL` |
| `4XL-56` | `4XL` | `56` | `_4XL` |
| `4XL-58` | `4XL` | `58` | `_4XL` |
| `4XL-60` | `4XL` | `60` | `_4XL` |

## Exact Bundle Matrix

### `LINE-21-LS`

- `sku_key`: `LINE-21-LS`
- Sport `family_id`: `PAIR-21-LS-ST`
- Thermal `family_id`: `PAIR-21-LS-TRM`
- Sport image/group token: `LINE-21-LS-ST`
- Thermal image/group token: `LINE-21-LS-TRM`

| Exact size token | `my_size` | `Size RUS` | Normalized `sku_id` | `sku_id_ksp` sport | `sku_id_ksp` thermal |
|---|---|---:|---|---|---|
| `S-42` | `S` | `42` | `LINE-21-LS_S` | `LINE-21-LS-ST-S-42` | `LINE-21-LS-TRM-S-42` |
| `M-44` | `M` | `44` | `LINE-21-LS_M` | `LINE-21-LS-ST-M-44` | `LINE-21-LS-TRM-M-44` |
| `L-46` | `L` | `46` | `LINE-21-LS_L` | `LINE-21-LS-ST-L-46` | `LINE-21-LS-TRM-L-46` |
| `XL-48` | `XL` | `48` | `LINE-21-LS_XL` | `LINE-21-LS-ST-XL-48` | `LINE-21-LS-TRM-XL-48` |
| `XL-50` | `XL` | `50` | `LINE-21-LS_XL` | `LINE-21-LS-ST-XL-50` | `LINE-21-LS-TRM-XL-50` |
| `2XL-52` | `2XL` | `52` | `LINE-21-LS_2XL` | `LINE-21-LS-ST-2XL-52` | `LINE-21-LS-TRM-2XL-52` |
| `3XL-54` | `3XL` | `54` | `LINE-21-LS_3XL` | `LINE-21-LS-ST-3XL-54` | `LINE-21-LS-TRM-3XL-54` |
| `4XL-56` | `4XL` | `56` | `LINE-21-LS_4XL` | `LINE-21-LS-ST-4XL-56` | `LINE-21-LS-TRM-4XL-56` |
| `4XL-58` | `4XL` | `58` | `LINE-21-LS_4XL` | `LINE-21-LS-ST-4XL-58` | `LINE-21-LS-TRM-4XL-58` |
| `4XL-60` | `4XL` | `60` | `LINE-21-LS_4XL` | `LINE-21-LS-ST-4XL-60` | `LINE-21-LS-TRM-4XL-60` |

### `LINE-21-TS`

- `sku_key`: `LINE-21-TS`
- Sport `family_id`: `PAIR-21-TS-ST`
- Thermal `family_id`: `PAIR-21-TS-TRM`
- Sport image/group token: `LINE-21-TS-ST`
- Thermal image/group token: `LINE-21-TS-TRM`

| Exact size token | `my_size` | `Size RUS` | Normalized `sku_id` | `sku_id_ksp` sport | `sku_id_ksp` thermal |
|---|---|---:|---|---|---|
| `S-42` | `S` | `42` | `LINE-21-TS_S` | `LINE-21-TS-ST-S-42` | `LINE-21-TS-TRM-S-42` |
| `M-44` | `M` | `44` | `LINE-21-TS_M` | `LINE-21-TS-ST-M-44` | `LINE-21-TS-TRM-M-44` |
| `L-46` | `L` | `46` | `LINE-21-TS_L` | `LINE-21-TS-ST-L-46` | `LINE-21-TS-TRM-L-46` |
| `XL-48` | `XL` | `48` | `LINE-21-TS_XL` | `LINE-21-TS-ST-XL-48` | `LINE-21-TS-TRM-XL-48` |
| `XL-50` | `XL` | `50` | `LINE-21-TS_XL` | `LINE-21-TS-ST-XL-50` | `LINE-21-TS-TRM-XL-50` |
| `2XL-52` | `2XL` | `52` | `LINE-21-TS_2XL` | `LINE-21-TS-ST-2XL-52` | `LINE-21-TS-TRM-2XL-52` |
| `3XL-54` | `3XL` | `54` | `LINE-21-TS_3XL` | `LINE-21-TS-ST-3XL-54` | `LINE-21-TS-TRM-3XL-54` |
| `4XL-56` | `4XL` | `56` | `LINE-21-TS_4XL` | `LINE-21-TS-ST-4XL-56` | `LINE-21-TS-TRM-4XL-56` |
| `4XL-58` | `4XL` | `58` | `LINE-21-TS_4XL` | `LINE-21-TS-ST-4XL-58` | `LINE-21-TS-TRM-4XL-58` |
| `4XL-60` | `4XL` | `60` | `LINE-21-TS_4XL` | `LINE-21-TS-ST-4XL-60` | `LINE-21-TS-TRM-4XL-60` |

### `LINE-31-LS`

- `sku_key`: `LINE-31-LS`
- Sport `family_id`: `PAIR-31-LS-ST`
- Thermal `family_id`: `PAIR-31-LS-TRM`
- Sport image/group token: `LINE-31-LS-ST`
- Thermal image/group token: `LINE-31-LS-TRM`

| Exact size token | `my_size` | `Size RUS` | Normalized `sku_id` | `sku_id_ksp` sport | `sku_id_ksp` thermal |
|---|---|---:|---|---|---|
| `S-42` | `S` | `42` | `LINE-31-LS_S` | `LINE-31-LS-ST-S-42` | `LINE-31-LS-TRM-S-42` |
| `M-44` | `M` | `44` | `LINE-31-LS_M` | `LINE-31-LS-ST-M-44` | `LINE-31-LS-TRM-M-44` |
| `L-46` | `L` | `46` | `LINE-31-LS_L` | `LINE-31-LS-ST-L-46` | `LINE-31-LS-TRM-L-46` |
| `XL-48` | `XL` | `48` | `LINE-31-LS_XL` | `LINE-31-LS-ST-XL-48` | `LINE-31-LS-TRM-XL-48` |
| `XL-50` | `XL` | `50` | `LINE-31-LS_XL` | `LINE-31-LS-ST-XL-50` | `LINE-31-LS-TRM-XL-50` |
| `2XL-52` | `2XL` | `52` | `LINE-31-LS_2XL` | `LINE-31-LS-ST-2XL-52` | `LINE-31-LS-TRM-2XL-52` |
| `3XL-54` | `3XL` | `54` | `LINE-31-LS_3XL` | `LINE-31-LS-ST-3XL-54` | `LINE-31-LS-TRM-3XL-54` |
| `4XL-56` | `4XL` | `56` | `LINE-31-LS_4XL` | `LINE-31-LS-ST-4XL-56` | `LINE-31-LS-TRM-4XL-56` |
| `4XL-58` | `4XL` | `58` | `LINE-31-LS_4XL` | `LINE-31-LS-ST-4XL-58` | `LINE-31-LS-TRM-4XL-58` |
| `4XL-60` | `4XL` | `60` | `LINE-31-LS_4XL` | `LINE-31-LS-ST-4XL-60` | `LINE-31-LS-TRM-4XL-60` |

### `LINE-31-TS`

- `sku_key`: `LINE-31-TS`
- Sport `family_id`: `PAIR-31-TS-ST`
- Thermal `family_id`: `PAIR-31-TS-TRM`
- Sport image/group token: `LINE-31-TS-ST`
- Thermal image/group token: `LINE-31-TS-TRM`

| Exact size token | `my_size` | `Size RUS` | Normalized `sku_id` | `sku_id_ksp` sport | `sku_id_ksp` thermal |
|---|---|---:|---|---|---|
| `S-42` | `S` | `42` | `LINE-31-TS_S` | `LINE-31-TS-ST-S-42` | `LINE-31-TS-TRM-S-42` |
| `M-44` | `M` | `44` | `LINE-31-TS_M` | `LINE-31-TS-ST-M-44` | `LINE-31-TS-TRM-M-44` |
| `L-46` | `L` | `46` | `LINE-31-TS_L` | `LINE-31-TS-ST-L-46` | `LINE-31-TS-TRM-L-46` |
| `XL-48` | `XL` | `48` | `LINE-31-TS_XL` | `LINE-31-TS-ST-XL-48` | `LINE-31-TS-TRM-XL-48` |
| `XL-50` | `XL` | `50` | `LINE-31-TS_XL` | `LINE-31-TS-ST-XL-50` | `LINE-31-TS-TRM-XL-50` |
| `2XL-52` | `2XL` | `52` | `LINE-31-TS_2XL` | `LINE-31-TS-ST-2XL-52` | `LINE-31-TS-TRM-2XL-52` |
| `3XL-54` | `3XL` | `54` | `LINE-31-TS_3XL` | `LINE-31-TS-ST-3XL-54` | `LINE-31-TS-TRM-3XL-54` |
| `4XL-56` | `4XL` | `56` | `LINE-31-TS_4XL` | `LINE-31-TS-ST-4XL-56` | `LINE-31-TS-TRM-4XL-56` |
| `4XL-58` | `4XL` | `58` | `LINE-31-TS_4XL` | `LINE-31-TS-ST-4XL-58` | `LINE-31-TS-TRM-4XL-58` |
| `4XL-60` | `4XL` | `60` | `LINE-31-TS_4XL` | `LINE-31-TS-ST-4XL-60` | `LINE-31-TS-TRM-4XL-60` |

## Required DB / Workbook Updates

### 1. `dim_sku`

Insert or upsert four new bundle family rows:

- `LINE-21-LS`
- `LINE-21-TS`
- `LINE-31-LS`
- `LINE-31-TS`

These become the canonical style-level keys for Beli bundle inventory/reporting.

### 2. `dim_sku_size`

Insert or upsert `7` normalized size rows per bundle family:

- `_S`
- `_M`
- `_L`
- `_XL`
- `_2XL`
- `_3XL`
- `_4XL`

Total new normalized size rows: `28`

### 3. `dim_kaspi_article_map`

Insert or upsert `80` exact Kaspi article rows:

- all sport `sku_id_ksp` tokens
- all thermal `sku_id_ksp` tokens
- `Артикул` and `Артикул производителя` both resolving to the same `sku_key`
- each exact token resolving to:
  - `sku_key`
  - normalized `sku_id`
  - normalized `my_size`
  - `Size RUS`

### 4. Workbook ingest surfaces

Update the LINE bundle workbook-preparation path so that:

- `SKU_ID_KSP (prepared)` = exact Kaspi row token
- `Merchant SKU` = exact Kaspi row token
- `SKU_key` = bundle family token
- `SKU_ID (normalized)` = normalized `sku_id`
- `Probable Size` = normalized `my_size`
- `Size RUS` = numeric size
- `family_id` = shared paired-family token for the matching category

## Parser / Gate Requirements

Current risk:

- `core/parsers/kaspi_parser.py`
- `core/parsers/kaspi_export_parser.py`

still primarily split Kaspi `Артикул` by underscore `_`.

The new Beli bundle tokens are hyphen-first, so the ingestion path must not rely on the old underscore heuristic for these offers.

### Safe resolution rule

For LINE bundle offers, resolve in this order:

1. `dim_kaspi_article_map`
2. explicit LINE bundle regex fallback
3. only then general legacy heuristics

### Recommended LINE regex fallback

Use a LINE bundle matcher equivalent to:

`^(LINE-\d{2}-(?:LS|TS))-(ST|TRM)-(S|M|L|XL|2XL|3XL|4XL)-(\d{2})$`

Resolution from regex:

- `sku_key` = group 1
- category token = group 2
- label token = group 3
- `Size RUS` = group 4
- `my_size` = normalized label token
- `sku_id` = `<sku_key>_<my_size>`
- `sku_id_ksp` = full exact token

### Important invariant

`LINE-21-LS-ST-XL-48` and `LINE-21-LS-ST-XL-50` must resolve to:

- same `sku_key`: `LINE-21-LS`
- same normalized `sku_id`: `LINE-21-LS_XL`
- different `sku_id_ksp`
- different `Size RUS`

That same rule applies to the three `4XL` Russian-size variants.

## Upload / Validation Contract

Before live upload enablement:

1. `Артикул` and `Артикул производителя` must both resolve to the same `sku_key`.
2. `family_id` must equal the shared paired-family token exactly.
3. `Код изображений` must equal the category token exactly:
   - `LINE-21-LS-ST`
   - `LINE-21-LS-TRM`
   - etc.
4. `Комплектация` must exclude `подарочная сумка`.
5. `dim_kaspi_article_map` coverage must be complete for all `80` exact tokens.

## Execution Checklist For Internal Agent

1. Back up `db/app.db`.
2. Add the 4 new bundle family rows to `dim_sku`.
3. Add the 28 normalized bundle size rows to `dim_sku_size`.
4. Add the 80 exact Kaspi token rows to `dim_kaspi_article_map`.
5. Update workbook mapping generation so `SKU_ID_KSP (prepared)` and `Merchant SKU` use the exact row token.
6. Update LINE identity resolution so it consults `dim_kaspi_article_map` before underscore heuristics.
7. Re-run offer validation gates against LINE bundle XLSMs.
8. Re-run ingest/path validation using one sport and one thermal LINE bundle sample.

## Success Criteria

The migration is correct when all of the following are true:

- every LINE bundle row resolves cleanly to one Beli-specific bundle-family `sku_key`
- no LINE bundle row falls through to legacy underscore parsing
- `XL-48` and `XL-50` remain distinguishable in `sku_id_ksp`
- internal `sku_id` still uses the existing normalized size buckets
- workbook / template validation passes without SKU alignment errors
- the LINE side can share one Kaspi card with the matching Line61 side through `family_id`

## Out Of Scope For This Pass

- changing the global size model beyond current normalized buckets
- splitting internal stock buckets by Russian numeric size
- changing legacy filesystem bundle ids in Business2
- live upload itself
