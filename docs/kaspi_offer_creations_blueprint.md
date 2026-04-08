# Kaspi Offer Creations Blueprint (ACMEWEAR Line61 – Men sport suits)

**Purpose:** capture the proven path that led to a successful Kaspi batch offer upload (V10) and the failure modes that must be avoided. This is the operational playbook for future Kaspi offer creation.

**Scope:** Kaspi batch XLSM uploads + images ZIP packaging. Templates vary by category; always respect the current template’s `attributes` + `values` sheets.

Primary contract docs:
- `docs/offer_creation/KASPI_TEMPLATE_FIELD_MAPPING_CONTRACT.md`
- `docs/offer_creation/KASPI_SKU_ALIGNMENT_GATE.md`
- `docs/offer_creation/OFFER_MANIFEST_SCHEMA.md`
- `docs/offer_creation/KASPI_MANIFEST_WORKFLOW.md`

---

## ✅ What worked (V10 success)

**Working reference file:** `docs/offer_creation/ACMEWEAR_LINE61_V10_REFERENCE.xlsm`

V10 succeeded after these changes:
1) **Clean ZIP structure**
   - XLSM at ZIP root.
   - `images/` (lowercase) folder at ZIP root.
   - Inside `images/`, create a folder named exactly as the shared image/article code:
     - `images/<image_code>/1.png`
     - `images/<image_code>/2.png`
   - No nested top-level folder, no `__MACOSX`, no `Images/` (capital).
2) **Unique `merchant_sku` after swap**
   - We swapped `Артикул` (merchant_sku) with `Артикул производителя`.
   - Duplicates were eliminated by suffixing sizes:
     - `OF_SUIT-61_BLK_XL_48`, `OF_SUIT-61_BLK_XL_50`
     - `OF_SUIT-61_BLK_4XL_56`, `_58`, `_60`
3) **Multi-value delimiter normalized**
   - Multi-value fields must use **comma + space** (`, `), not semicolons.
   - Example: `худи, футболка, майка, рашгард, шорты, леггинсы`
4) **Glue group remained intact**
   - `family_id = ACMEWEAR61` on all rows to force a single product card.

---

## ❌ What failed (and why)

### V4 failure
- ZIP contained a top-level folder, `__MACOSX` entries, and `Images/` (capital). Kaspi expects:
  - XLSM at root
  - `images/` lowercase

### V5 failure
- Errors were stored as **cell comments**, not in a separate error sheet.
- Errors indicated invalid dictionary values for:
  - `fabric` (Состав)
  - `components` (Комплектация)
- Semicolon-delimited lists were not accepted.

---

## Non‑negotiables

1) **ZIP layout must be clean**
   - Root: XLSM + `images/`
   - Image files must live inside `images/<image_code>/...`, not flat `images/1.png`
   - No extra folders, no macOS artifacts
2) **`merchant_sku` must be unique per row**
3) **Multi‑value fields must use `, ` (comma + space)**
4) **Respect `values` sheet**
   - All list-bound fields must use values from `values`.
5) **Do not rename or reorder columns/sheets**
6) **Use Excel-safe-ops rules**
   - Always back up XLSM before writing.

---

## How to debug Kaspi errors

Kaspi’s validation report often embeds **error messages as cell comments** inside the returned XLSM. Steps:

1) Open the returned XLSM.
2) Inspect cell comments in the `attributes` sheet.
3) Common error text:
   - `Поле должно содержать значение из справочника`

**Automation hint:** openpyxl can read comments and surface per‑row errors.

---

## Future workflow (repeatable)

1) **Start from the latest fresh merchant template**
   - Re-download the category template from Kaspi merchant UI from time to time.
   - Categories and template contracts can change; stale templates may be rejected.
   - For the LINE31 2026-03-19 failure, template age was not the suspected cause because the women templates were downloaded ~3 hours before upload.
2) **Prefer manifest-driven build**
   - Create/update `offer_manifest.yaml` inside the product/color root.
   - Use `python3 scripts/build_kaspi_offer_from_manifest.py --manifest <FILE> --apply`
3) **Fill product data** and validate against `values` sheet.
4) **Run hard gate (mandatory before ZIP):**
   - repeat color / same proven category:
     - `python3 scripts/validate_kaspi_offer_template.py --xlsm <FILE> --category <CATEGORY> --store <STORE> --mode fast`
   - new product / proven category:
     - `... --mode balanced`
   - new category / refreshed template / row-level rejection debugging:
     - `... --mode strict`
5) **Run technical package gate (mandatory before upload):**
   - `python3 scripts/validate_kaspi_offer_package.py --package-dir <DIR> --zip <ZIP>`
6) **Ensure `merchant_sku` uniqueness**.
7) **Normalize delimiters** for multi‑value fields.
8) **Package ZIP correctly**:
   - XLSM root
   - images in `images/<image_code>/1.png`
9) **Generate workbook ingest payload / append mappings if needed**
   - `python3 scripts/build_kaspi_offer_from_manifest.py --manifest <FILE> --apply --apply-workbook`
10) **Upload** and read error comments if rejected.

## Processing-error triage

If Kaspi upload history shows:
- `Ошибка при обработке`
- `0` parsed offers

Then debug in this order:
1. ZIP structure and nested image folders
2. Template preservation / workbook container drift
3. Only then row-level values and returned XLSM comments

---

## Known success reference

- `docs/offer_creation/ACMEWEAR_LINE61_V10_REFERENCE.xlsm` (V10)

Use this as a baseline for future offer creation.

---

## Thermal category (men thermal underwear)

Thermal templates have **different required fields** than men sport suits.
See:
- `docs/offer_creation/templates/Men-thermal-underwear-import-template.xlsm`
- `docs/offer_creation/THERMAL_V1_NOTES.md`

The V1 thermal reference is prefilled with shared values:
- `docs/offer_creation/ACMEWEAR_LINE61_THERMAL_V1_REFERENCE.xlsm`
