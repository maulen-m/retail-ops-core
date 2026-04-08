# Kaspi Offer Template Field Mapping Contract

## Purpose
This document is the source-of-truth contract for creating Kaspi batch offer uploads from scratch.
It covers:
- XLSM template filling rules
- variable/term mapping
- image and ZIP packaging rules
- backup and storage conventions
- mandatory SKU alignment checks against `~/Docs/Autonomous_business` DB

This contract is category-aware and uses LINE51 as the worked example.

## Required Workflow
1. Start from the current Kaspi category template (`intro`, `attributes`, `values` sheets).
   - Re-download templates from merchant UI periodically; stale templates can be rejected after category changes.
2. Back up the template before any edits.
3. Fill only data rows in `attributes` (rows 4+), never rename/reorder sheets or columns.
4. Validate list-bound values against `values` sheet.
5. Run hard gate:
`python3 scripts/validate_kaspi_offer_template.py --xlsm <FILE> --category <CATEGORY> --store ACMEWEAR --mode <fast|balanced|strict> --expect-sku-key <SKU_KEY>`
6. Run technical package gate:
`python3 scripts/validate_kaspi_offer_package.py --package-dir <DIR> --zip <ZIP>`
7. Package ZIP with exact structure:
  - XLSM at ZIP root
  - `images/` lowercase at ZIP root
  - `images/<image_code>/1.png ... 5.png`
  - no `__MACOSX`, no nested parent directory
8. Store live workflow files under:
`~/Docs/Business2/Content/Content_db_1/Kaspi/Product_offers/<PRODUCT>/<COLOR>/`
9. Prefer manifest-driven build:
`python3 scripts/build_kaspi_offer_from_manifest.py --manifest <FILE> --apply`

## Template Semantics
In `attributes` sheet:
- row 1 = type/required metadata
- row 2 = machine key (automation key)
- row 3 = display name (operator name)
- row 4+ = product offer rows

Rule:
- `обязательное поле` means non-empty value is required in each active row.
- `из списка` means value must exist in `values` sheet dictionary.
- `множество значений` means use comma-separated tokens with delimiter `, `.

## Core Identity Fields
- `merchant_sku` (`Артикул`)
- `...manufacturer code` (`Артикул производителя`)
- `family_id` (`Объединить в одну карточку`)

Identity contract:
1. `merchant_sku` and `Артикул производителя` are business-identity tokens; both must align with internal `sku_key`.
2. They must resolve to the same single `sku_key` through DB mapping.
3. If unresolved/ambiguous/mismatched, upload is blocked.
4. `family_id` glues size rows into one product card and must be identical across the same product batch.

## LINE51 Example (Men sport suits)
Internal product:
- `sku_key = CL_OC_MEN_LINE51_WHITE`

Example identity rows:
- `OF_LINE51_K-O_S`
- `OF_LINE51_K-O_M`
- `OF_LINE51_K-O_L`
- `OF_LINE51_K-O_XL_48`
- `OF_LINE51_K-O_XL_50`
- `OF_LINE51_K-O_2XL`
- `OF_LINE51_K-O_3XL`
- `OF_LINE51_K-O_4XL_56`
- `OF_LINE51_K-O_4XL_58`
- `OF_LINE51_K-O_4XL_60`

For each row:
- `Артикул` = value above
- `Артикул производителя` = same value (recommended safe mode)
- `Объединить в одну карточку` = single family value

## Value Mapping Rules
1. Every list-bound column must use values from `values` sheet exactly (case-sensitive for upload safety).
2. Multi-value fields use `, ` (comma + space), never semicolon.
3. Color values must come from template dictionary (for LINE51 batch: `черный, белый` when dictionary allows both).

## Validation Mode Policy
- `fast`:
  - default for repeat color variants in the same already-proven category
  - checks business-owned required fields + SKU alignment only
- `balanced`:
  - use for a new product in a category we already proved before
  - checks business-owned required fields + SKU alignment + only the list-bound columns we actually filled
- `strict`:
  - use for the first upload in a new category, first batch from a refreshed template, or when Kaspi returns row-level validation comments
  - replays the full list-bound template dictionary on top of the business-owned required-field gate

## Category Notes
### Men sport suits
- Uses `Women sport suits*...` machine keys in current template; this is normal template naming.
- Required/optional flags must be read from row 1 of the actual template version.

### Men thermal underwear
- Required fields differ from sport suits.
- Re-check required/list-bound columns from thermal template before every batch.

## Images and ZIP
1. Kaspi image limit for this workflow: max 5 images in upload ZIP per offer package.
2. Folder format:
`images/<image_code>/1.png`
3. Keep extra image sets outside upload ZIP (separate operator archive).
4. The `<image_code>` folder name must match the value written in `Код изображений`.

## Backups and Audit
1. Keep timestamped XLSM backup before edits.
2. Keep upload logs with timestamp + result.
3. Preserve returned Kaspi result XLSM for error-comment audit.

## Non-Negotiables
1. No upload if hard gate fails.
2. No manual overrides bypassing DB SKU alignment.
3. No template structural edits (sheet/column reorder/rename).
4. No ZIPs in repo; external storage only for heavy files.

## Live Manifest Reference
- `~/Docs/Business2/Content/Content_db_1/Kaspi/Product_offers/LINE31/Starry_Black/offer_manifest.yaml`
