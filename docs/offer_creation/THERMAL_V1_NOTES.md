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

Line61 reference covers only overlapping fields. The following **required** fields are still empty in V1 and must be provided:
- `Thermal underwear*...*model`
- `Thermal underwear*...*gender`
- `Thermal underwear*...*notice1`

## Next input needed
Please provide values for those three fields; after that, V1 can be made upload‑ready.
