# Thermal Category (Men thermal underwear) — V1 Notes

Source template:
- `docs/offer_creation/templates/Men-thermal-underwear-import-template.xlsm`

Reference upload (filled with shared values from Line61):
- `docs/offer_creation/ACMEWEAR_LINE61_THERMAL_V1_REFERENCE.xlsm`

## Differences vs Men sport suits template
Thermal template uses different required fields (row 1 in `attributes`).
Required fields (thermal):
- `merchant_sku`
- `name`
- `brand`
- `Thermal underwear*...*model`
- `Thermal underwear*...*sport`
- `Thermal underwear*...*gender`
- `Thermal underwear*...*manufacturer size`
- `Thermal underwear*...*fabric`
- `Thermal underwear*...*notice1`
- `Clothes*General.clothes*size`

## V1 filled values
The V1 reference now fills required thermal-only fields:
- `model` = `комплект`
- `gender` = `мужской`
- `notice1` = value copied from `additional information`

## Next input needed
If Kaspi rejects, inspect cell comments in the result XLSM for exact errors.
