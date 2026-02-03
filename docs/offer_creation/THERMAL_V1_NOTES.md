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
- `model` = `комплект`
- `gender` = `мужской`
- `clasp` = `спереди`
- `notice1` values moved into `additional information` (notice1 cleared)

## Risk
`notice1` is required by the template; it is currently empty after relocation.
If Kaspi enforces required fields, this will fail unless we re‑fill notice1.

## Next input needed
If Kaspi rejects, inspect cell comments in the result XLSM for exact errors.
