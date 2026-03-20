# Kaspi SKU Alignment Gate

## Goal
Block offer uploads when XLSM identity fields are not aligned with internal SKU truth in:
`~/Docs/Autonomous_business/db/app.db`

CLI:
`python3 scripts/validate_kaspi_offer_template.py`

## Hard-Fail Inputs
- `--xlsm`: offer template file
- `--category`: `men-sport-suits` or `men-thermal-underwear`
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
1. Prepare XLSM from latest template.
2. Run gate command.
3. If gate passes, create ZIP and upload.
4. If gate fails, update mapping and/or XLSM values, then rerun.

## Example Commands
LINE51 batch:
```bash
python3 scripts/validate_kaspi_offer_template.py \
  --xlsm docs/offer_creation/LINE51_WORKING_FILE.xlsm \
  --category men-sport-suits \
  --store ACMEWEAR \
  --expect-sku-key CL_OC_MEN_LINE51_WHITE \
  --report-json exports/offer_validation_line51.json
```

Thermal batch:
```bash
python3 scripts/validate_kaspi_offer_template.py \
  --xlsm docs/offer_creation/LINE51_THERMAL_WORKING_FILE.xlsm \
  --category men-thermal-underwear \
  --store ACMEWEAR \
  --expect-sku-key CL_OC_MEN_LINE51_WHITE
```

## Exit Codes
- `0`: pass
- `2`: validation failures (hard gate stop)

## Test Coverage
Covered in:
- `tests/test_validate_kaspi_offer_template.py`

Scenarios:
- valid LINE51 pass
- LINE51 token mapped to LINE61 fail
- invalid dictionary value fail
- missing required field fail
- ambiguous mapping fail
