# Kaspi Offer Creations Blueprint (ACMEWEAR Line61 – Men sport suits)

**Purpose:** capture the proven path that led to a successful Kaspi batch offer upload (V10) and the failure modes that must be avoided. This is the operational playbook for future Kaspi offer creation.

**Scope:** Kaspi batch XLSM uploads + images ZIP packaging. Templates vary by category; always respect the current template’s `attributes` + `values` sheets.

---

## ✅ What worked (V10 success)

**Working reference file:** `docs/offer_creation/ACMEWEAR_LINE61_V10_REFERENCE.xlsm`

V10 succeeded after these changes:
1) **Clean ZIP structure**
   - XLSM at ZIP root.
   - `images/` (lowercase) folder at ZIP root.
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

1) **Start from the latest accepted template** (not old cached files).
2) **Fill product data** and validate against `values` sheet.
3) **Ensure `merchant_sku` uniqueness**.
4) **Normalize delimiters** for multi‑value fields.
5) **Package ZIP correctly**:
   - XLSM root
   - images in `images/<merchant_sku>/1.png`
6) **Upload** and read error comments if rejected.

---

## Known success reference

- `docs/offer_creation/ACMEWEAR_LINE61_V10_REFERENCE.xlsm` (V10)

Use this as a baseline for future offer creation.
