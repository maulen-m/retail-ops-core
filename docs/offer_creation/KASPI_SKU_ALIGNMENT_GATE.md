# Kaspi SKU Alignment Gate

## Goal
Block offer uploads when XLSM identity fields are not aligned with internal SKU truth in:
`~/Docs/Autonomous_business/db/app.db`

CLI:
`python3 scripts/validate_kaspi_offer_template.py`

Default validation mode:
- `fast`

## Hard-Fail Inputs
- `--xlsm`: offer template file
- `--category`: `men-sport-suits`, `men-thermal-underwear`, `women-sport-suits`, or `women-thermal-underwear`
- `--store`: optional store scope (`ACMEWEAR`, etc.)
- `--expect-sku-key`: optional strict product lock
- `--expect-sku-prefix`: optional namespace lock

## Validation Layers
1. Workbook contract:
  - `attributes` and `values` sheets exist
  - required fields are present
  - list-bound values exist in `values` dictionary
2. Identity extraction:
  - `merchant_sku` (`Артикул`)
  - manufacturer code (`Артикул производителя`)
3. DB resolution:
  - token -> `sku_key` candidates from:
    - `dim_kaspi_article_map`
    - `fact_offer_stock_mapper_current`
  - `sku_key` existence in `dim_sku`
4. Consistency checks:
  - unresolved token => fail
  - ambiguous token => fail
  - merchant/manufacturer resolve to different `sku_key` => fail
  - model token mismatch (source token vs resolved `sku_key`) => fail
  - `--expect-sku-key` mismatch => fail
  - `--expect-sku-prefix` mismatch => fail

## Why This Exists
Historical mistakes included uploads where LINE51 rows were encoded with LINE61 identity tokens.
Kaspi accepted some files, but internal mapping drift required cleanup workarounds later.
This gate prevents that class of error before upload.

## Expected Operator Flow
1. Prefer a manifest-driven build:
   - `python3 scripts/build_kaspi_offer_from_manifest.py --manifest <FILE> --apply`
2. Prepare XLSM from latest template.
3. Run SKU gate command in the right mode:
   - repeat color / same proven category: `--mode fast`
   - new product in an already-proven category: `--mode balanced`
   - new category / first upload / returned row-level errors: `--mode strict`
4. Run package gate:
   - `python3 scripts/validate_kaspi_offer_package.py --package-dir <DIR> --zip <ZIP>`
5. If both gates pass, upload.
6. If gate fails, update mapping and/or XLSM/package structure, then rerun.

## Example Commands
LINE51 batch:
```bash
python3 scripts/validate_kaspi_offer_template.py \
  --xlsm docs/offer_creation/LINE51_WORKING_FILE.xlsm \
  --category men-sport-suits \
  --store ACMEWEAR \
  --mode fast \
  --expect-sku-key CL_OC_MEN_LINE51_WHITE \
  --report-json exports/offer_validation_line51.json
```

Thermal batch:
```bash
python3 scripts/validate_kaspi_offer_template.py \
  --xlsm docs/offer_creation/LINE51_THERMAL_WORKING_FILE.xlsm \
  --category men-thermal-underwear \
  --store ACMEWEAR \
  --mode strict \
  --expect-sku-key CL_OC_MEN_LINE51_WHITE
```

Women LINE31 sport batch:
```bash
python3 scripts/validate_kaspi_offer_template.py \
  --xlsm ~/Docs/Business2/Content/Content_db_1/Kaspi/Product_offers/LINE31/Starry_Black/women-sport-suits/<package>/Women-sport-suits-import-template_FIXED.xlsm \
  --category women-sport-suits \
  --store ACMEWEAR \
  --mode fast \
  --expect-sku-key CL_OF_ARC_WM_LINE31_C-023_STARRY-BLACK
```

## Exit Codes
- `0`: pass
- `2`: validation failures (hard gate stop)

## Mode Semantics
- `fast`
  - business-owned required-field checks
  - SKU alignment checks
  - skips values-sheet replay
- `balanced`
  - `fast` plus values-sheet checks only for list-bound columns that were actually filled in the current XLSM
- `strict`
  - `fast` plus full list-bound values replay for the template

## Test Coverage
Covered in:
- `tests/test_validate_kaspi_offer_template.py`

Scenarios:
- valid LINE51 pass
- LINE51 token mapped to LINE61 fail
- invalid dictionary value fail
- missing required field fail
- ambiguous mapping fail
