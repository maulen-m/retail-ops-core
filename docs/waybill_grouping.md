# Waybill Grouping Logic (Kaspi Orders Bundler)

Source of truth: `~/Docs/kaspi_etl/docs/ops/kaspi/run_today_and_archive_input.command`
and `~/Docs/kaspi_etl/docs/ops/kaspi/build_kaspi_orders.py`.

This document captures the exact grouping rules and runtime behavior
so we can re-implement the same behavior inside this repo.

## Entry Point and Flow

Shell wrapper: `run_today_and_archive_input.command`

1) Bootstraps Python environment:
   - `python_env_bootstrap.zsh` selects a Python binary and ensures deps.
2) Runs the builder:
   - `build_kaspi_orders.py --input ... --outbase ... --date ... --zip-mode ...`
3) Archives input files after success:
   - moves `*.xlsx` and `*.zip` from input to `OUTBASE/Archive/input_<timestamp>/`

## Environment Variables

- `KASPI_INPUT_DIR` or `IN`:
  Input folder with Excel + waybill ZIPs.
  Default: `<ops>/Kaspi_orders/input`
- `KASPI_OUTBASE_DIR` or `OUTBASE`:
  Output base with `Today/` and `Archive/`.
  Default: `<ops>/Kaspi_orders`
- `KASPI_RUN_DATE` or `RUN_DATE`:
  Date to build (default "today").
- `KASPI_ZIP_MODE` or `ZIP_MODE`:
  `"one"` (single ZIP) or `"per-store"`.

## Input Requirements

Expected input:
1) Exactly one Excel `.xlsx` file (latest modified wins).
2) One or more ZIPs with PDF waybills. PDFs contain an OrderID in filename
   (regex finds any digits in filename).

Excel required columns (canonical):
- `Date`
- `STORE_NAME`
- `OrderID`
- `Quantity`
- `Kaspi_name_core`
- `MY_SIZE`

Aliases accepted:
- Date: `PLANNED_SHIPPING_DATE`, `Плановая дата передачи курьеру`, `Дата поступления заказа`
- OrderID: `№ заказа`
- Quantity: `Количество`
- Store: `STORE_NAME`, `Store_name`, `Store Name`

Notes:
- Date parsing uses day-first semantics for non-ISO strings.
- Quantity is coerced to int (default 1).

## Date Selection

`--date` accepts:
- `today`, `yesterday`, `tomorrow`
- ISO `YYYY-MM-DD`
- Any other string parsed with `dayfirst=True`

The script selects the first sheet that has required columns and includes
at least one row for the target date. If none match, it falls back to
the first sheet with required columns.

If no rows for the target date, it errors and prints available dates.

## Waybill Mapping

Waybill PDFs are pulled from ZIP files. For each PDF:
- Extract first digit sequence from filename as OrderID.
- Keep the first PDF found per OrderID (first ZIP wins).

## Grouping Rules (Actual Code Behavior)

The header comment in `build_kaspi_orders.py` says multi-qty groups are
cross-order by core. However, the code does **per-order** handling.
Below reflects the real behavior:

### 1) SPECIAL: Multi-Qty (Quantity > 1, not multi-line)

Definition:
- Orders with `Quantity > 1`
- Excludes multi-line orders (OrderID with multiple rows)

Grouping:
- One PDF per OrderID (no cross-order grouping).

Filename:
- `<core>___<size>-<qnt>.pdf`
- Prefixed with `Местовая-<n>_` if duplicate base name exists.

### 2) SPECIAL: Multi-Line (OrderID appears on multiple rows)

Definition:
- OrderID appears more than once in the day data.

Grouping:
- One PDF per OrderID.

Filename:
- A combined string of segments:
  `core1-size1-qnt1(1/N)___core2-size2-qnt2(2/N)....pdf`
- Prefixed with `Местовая-<n>_` if duplicate base name exists.

### 3) NORMAL: Singles

Definition:
- `Quantity == 1` and OrderID is not multi-line.

Grouping:
- Group by `(Kaspi_name_core, MY_SIZE)` across orders.
- Merge all PDFs for matching order IDs in that group.

Filename:
- `<core>___<size>-<count>.pdf` where count = number of orders in group.

## Output Structure

Outputs are created under:
```
<OUTBASE>/Today/<d.m.yy>_<STORE>_qnt<sum>/
  SPECIAL_multi_qty/
  SPECIAL_multi_line/
  NORMAL_singles/
  manifest_special_multi_qty.csv
  manifest_special_multi_line.csv
  manifest_normal_singles.csv
```

Root-level logs:
- `<OUTBASE>/Today/build_log.csv`
- `<OUTBASE>/Today/missing_orders.csv` (if missing PDFs)

ZIP output:
- If `--zip-mode one`: `Today/kaspi_orders_<d.m.yy>.zip`
- If `--zip-mode per-store`: one ZIP per store folder

Rotation:
- If `Today/` has content, it is moved to `Archive/<yesterday>`
  (with a `_N` suffix if that folder already exists).

## Matching and Errors

Match rate is computed as:
```
matched_order_ids / total_order_ids_for_day * 100
```

If `--fail-below-match` is provided and match rate is below threshold,
the script exits with an error.

Other failures:
- No .xlsx in input
- No .zip in input
- No matching sheet with required columns
- No rows for requested date
- No PDFs found inside ZIPs

## Implementation Notes for Porting

To reproduce logic in this repo:
- Match the alias handling and date parsing behavior.
- Replicate the exact grouping rules above (including the "multi-qty"
  per-OrderID behavior).
- Preserve filename sanitization and the "Местовая-<n>_" prefix behavior.
- Match the output folder structure and ZIP behavior.
