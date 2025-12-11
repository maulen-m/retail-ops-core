# Phase 11: Daily Kaspi Order Workflow (Excel-Integrated)

## Objective
Recreate legacy kaspi_etl daily workflow in `~/Docs/Autonomous_business/`:
1. Import new orders from ActiveOrders.xlsx → SALES_KSP_CRM_V3.xlsx
2. Group waybill PDFs by store/type after sizes are manually set

## File Locations

```
~/Docs/Autonomous_business/
├── excel_ui/
│   ├── SALES_KSP_CRM_V3.xlsx          # Master CRM file
│   ├── ActiveOrders/                   # Input folder
│   │   ├── ActiveOrders_*.xlsx         # Kaspi exports (input)
│   │   └── waybill*.zip                # Waybill ZIPs (input)
│   └── Kaspi_orders/                   # Output folder
│       └── Today/
│           ├── build_log.csv           # Master log (ALL stores)
│           ├── missing_orders.csv      # ALL missing items
│           ├── package_summary.csv     # Package counts
│           └── {DD.MM.YY}_{STORE}_qnt{total}/
│               ├── NORMAL_singles/
│               ├── SPECIAL_multi_line/
│               ├── SPECIAL_multi_qty/
│               ├── manifest_normal_singles.csv
│               ├── manifest_special_multi_line.csv
│               └── manifest_special_multi_qty.csv
├── scripts/
│   ├── import_orders_to_crm.py         # NEW: Order import CLI
│   └── build_daily_waybills.py         # NEW: Waybill grouper CLI
└── config/
    └── kaspi_stores.yaml               # Store mapping config
```

## Store Code Mapping

```python
STORE_MAP = {
    '30137883_PP1': 'AcmeWear',
    '30000001_PP1': 'Universal',
    '30290083_PP1': '11KZ',
    '30000002_PP1': 'STORE-B',
    # Add new stores here as needed
}
```

---

## Script 1: `scripts/import_orders_to_crm.py`

### Purpose
Read ActiveOrders*.xlsx files, filter for "Ожидает передачи курьеру", append new rows to SALES_KSP_CRM_V3.xlsx

### Input: ActiveOrders.xlsx (28 columns)

| Col | Russian Header | Description |
|-----|----------------|-------------|
| 0 | № заказа | Order ID |
| 1 | Дата поступления заказа | Order receipt date |
| 2 | Название товара в Kaspi Магазине | Kaspi offer name |
| 3 | Название в системе продавца | Seller product name |
| 4 | Артикул | SKU/Article |
| 5 | Сумма | Price (KZT) |
| 6 | Категория | Category |
| 7 | Адрес самовывоза/доставки | Delivery address |
| 8 | Дата изменения статуса | Status change date |
| 9 | Статус | Status (FILTER: "Ожидает передачи курьеру") |
| 10 | Причина отмены | Cancel reason |
| 11 | Способ оплаты | Payment method |
| 12 | Способ доставки | Delivery method |
| 13 | Курьерская служба | Courier service |
| 14 | Принял | Accepted by |
| 15 | Выдал | Issued by |
| 16 | Отменил | Cancelled by |
| 17 | Оценка покупателя | Customer rating |
| 18 | Отзыв покупателя | Customer review |
| 19 | Дата публикации отзыва | Review date |
| 20 | Оформил | Ordered by |
| 21 | Количество | Quantity |
| 22 | Стоимость доставки для покупателя | Delivery fee (customer) |
| 23 | Стоимость доставки для продавца | Delivery fee (seller) |
| 24 | Компенсация за доставку | Delivery compensation |
| 25 | Требуется подписание | Signature required (FILTER: "Не требуется") |
| 26 | Плановая дата передачи курьеру | Planned shipping date |
| 27 | Склад передачи КД | Store/Warehouse code |

### Output: SALES_KSP_CRM_1 Sheet (52 columns)

| Col | Header | Source | Notes |
|-----|--------|--------|-------|
| A | Return | blank | Manual entry |
| B | Date | `Плановая дата передачи курьеру` | Parse DD.MM.YYYY |
| C | STORE_NAME | `Склад передачи КД` → STORE_MAP | Lookup |
| D | HEIGHT | blank | Manual entry |
| E | WEIGHT | blank | Manual entry |
| F | Quantity | `Количество` | |
| G | Kaspi_name_core | Extract from `Название товара в Kaspi Магазине` | See extraction logic |
| H | OrderID | `№ заказа` | str() |
| I | Phone | `customer.cellPhone` from API | Populated automatically (Phase 12) |
| J | MY_SIZE | blank | **USER FILLS THIS** |
| K | PROBABLE_SIZE | blank | Optional auto-fill |
| L | KASPI_OFFER_NAME | `Название товара в Kaspi Магазине` | |
| M | SKU_key | Extract from `Артикул` | Parse before `_` |
| N | SKU_ID | blank → derive from SKU_key + MY_SIZE AFTER user fills MY_SIZE | |
| O | Sell_price_kzt | `Сумма` | |
| P | Total_price | `Сумма` × `Количество` | |
| Q | Total_net_rev | blank | Formula |
| R | MODEL | Extract from SKU_key | |
| S | PLANNED_SHIPPING_DATE | `Плановая дата передачи курьеру` | |
| T | Product_Type | Extract from SKU_key prefix | CL/ELS/FUR/KIDS |
| U | Delivery_fee_kzt | `Стоимость доставки для продавца` | |
| V | Total_weight | blank | Lookup from dim_sku |
| W | SKU_ID_KSP | `Артикул` | |
| X | Kaspi_name_source | `Название в системе продавца` | |
| Y-AZ | Raw Kaspi columns | Direct copy from ActiveOrders | All 28 columns |

### Filtering Logic

```python
def filter_orders(df: pd.DataFrame, target_date: date = None) -> pd.DataFrame:
    """
    Filter ActiveOrders for import.
    
    Criteria:
    1. Статус == "Ожидает передачи курьеру"
    2. Требуется подписание == "Не требуется" (if column exists)
    3. Плановая дата передачи курьеру <= target_date (optional)
    """
    mask = df['Статус'] == 'Ожидает передачи курьеру'
    
    if 'Требуется подписание' in df.columns:
        mask &= df['Требуется подписание'] == 'Не требуется'
    
    if target_date:
        df['_plan_date'] = pd.to_datetime(
            df['Плановая дата передачи курьеру'], 
            dayfirst=True, 
            errors='coerce'
        )
        mask &= df['_plan_date'].dt.date <= target_date
        df.drop('_plan_date', axis=1, inplace=True)
    
    return df[mask].copy()
```

### Deduplication Logic

```python
def deduplicate_orders(new_df: pd.DataFrame, existing_df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove orders that already exist in CRM.
    
    Dedup key: OrderID (№ заказа)
    """
    existing_ids = set(existing_df['OrderID'].astype(str).unique())
    new_df['_order_id_str'] = new_df['№ заказа'].astype(str)
    new_orders = new_df[~new_df['_order_id_str'].isin(existing_ids)].copy()
    new_orders.drop('_order_id_str', axis=1, inplace=True)
    return new_orders
```

### Kaspi_name_core Extraction

```python
def extract_kaspi_name_core(offer_name: str) -> str:
    """
    Extract core product name from Kaspi offer name.
    
    Examples:
    - "Спортивный костюм AcmeWear 05 черный, белый 3XL" → "Line51" (via SKU lookup)
    - "Тайтсы черные мужской L 48-50 123591314 (XL)" → "Тайтсы_черные"
    
    If no match, return sanitized version of first 2-3 words.
    """
    # Remove size indicators and numbers at end
    import re
    clean = re.sub(r'\s+\d+[-/]\d+.*$', '', offer_name)
    clean = re.sub(r'\s+[SMLX]{1,3}L?\s*$', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'\s+\d+\s*$', '', clean)
    
    # Sanitize for filename
    clean = re.sub(r'[^\w\s-]', '', clean)
    clean = '_'.join(clean.split()[:3])
    
    return clean or 'UNKNOWN'
```

### CLI Interface

```bash
# Scan folder, import new orders
python scripts/import_orders_to_crm.py \
    --orders-dir excel_ui/ActiveOrders/ \
    --crm-file excel_ui/SALES_KSP_CRM_V3.xlsx \
    --date 2025-12-10

# Dry run (preview only)
python scripts/import_orders_to_crm.py --dry-run

# Verbose output
python scripts/import_orders_to_crm.py --verbose
```

### Implementation Notes

1. **Use xlwings for CRM writes** (openpyxl corrupts external links/formulas)
2. **Use openpyxl for reading only** (inspection, header detection)
3. **Preserve formulas** in columns Q+ (don't overwrite)
4. **Append to end** of SALES_KSP_CRM_1 sheet
5. **Date parsing**: Handle DD.MM.YYYY, YYYY-MM-DD, Excel serial numbers
6. **Idempotent**: Re-running won't duplicate orders
7. **Phone column (I)**: Populated from Kaspi API `customer.cellPhone` (Phase 12)

---

## Script 2: `scripts/build_daily_waybills.py`

### Purpose
Read CRM with assigned sizes, extract waybills from ZIP, group PDFs by store and type

### Input Requirements

1. **CRM file** with:
   - `Date` == target_date
   - `MY_SIZE` is NOT blank (sizes assigned)
   - `Статус` == "Ожидает передачи курьеру" (not yet shipped)

2. **Waybill ZIP** containing:
   - Files named `KASPI_SHOP-{OrderID}.pdf`

### Grouping Logic

```
┌─────────────────────────────────────────────────────────────┐
│                    ORDER CLASSIFICATION                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Is Quantity > 1?                                           │
│       │                                                     │
│       ├── YES ──► SPECIAL_multi_qty                         │
│       │           Group by KASPI_OFFER_NAME                 │
│       │           Filename: Местовая-N_{core}_{size}-{qty}  │
│       │                                                     │
│       └── NO ──► Does OrderID appear on multiple lines?     │
│                       │                                     │
│                       ├── YES ──► SPECIAL_multi_line        │
│                       │           Merge all SKUs for order  │
│                       │           Filename: Местовая-N_     │
│                       │             {core1}-{sz1}-{q1}(1-N) │
│                       │             _{core2}-{sz2}-{q2}(2-N)│
│                       │                                     │
│                       └── NO ──► NORMAL_singles             │
│                                   Single PDF per item       │
│                                   Filename: {core}_{size}-  │
│                                             {qty}.pdf       │
└─────────────────────────────────────────────────────────────┘
```

### Output Structure

**Folder pattern:** `excel_ui/Kaspi_orders/Today/{DD.MM.YY}_{STORE}_qnt{total}/`

```
excel_ui/Kaspi_orders/Today/
├── build_log.csv                      # Master log (ALL stores, ALL orders)
├── missing_orders.csv                 # ALL missing items across stores
├── package_summary.csv                # Package counts table
├── 10.12.25_Universal_qnt61/
│   ├── NORMAL_singles/
│   │   ├── Футболка_белая_M-1.pdf
│   │   └── Тайтсы_черные_XL-1.pdf
│   ├── SPECIAL_multi_line/
│   │   └── Местовая-1_Длинный_рашгард_Белый-L-1(1-2)_Трусы_белые-L-1(2-2).pdf
│   ├── SPECIAL_multi_qty/
│   │   └── Местовая-1_Принт_5в1_черный_XL-2.pdf
│   ├── manifest_normal_singles.csv    # This store only
│   ├── manifest_special_multi_line.csv
│   └── manifest_special_multi_qty.csv
├── 10.12.25_AcmeWear_qnt23/
│   └── ...
└── 10.12.25_11KZ_qnt0/
    └── ...
```

### File Naming Conventions

**NORMAL_singles:**
```
{kaspi_name_core}_{MY_SIZE}-{QTY}.pdf
```
Example: `Футболка_белая_M-1.pdf`

**SPECIAL_multi_qty:** (same product, qty > 1)
```
Местовая-{N}_{kaspi_name_core}_{MY_SIZE}-{QTY}.pdf
```
Example: `Местовая-1_Принт_5в1_черный_XL-2.pdf`

**SPECIAL_multi_line:** (same OrderID, multiple SKUs)
```
Местовая-{N}_{core1}-{size1}-{qty1}(1-{total})_{core2}-{size2}-{qty2}(2-{total})_...pdf
```
Example: `Местовая-1_Длинный_рашгард_Белый-L-1(1-2)_Трусы_белые-L-1(2-2).pdf`

Where:
- `Местовая-{N}` = package number (sequential within type)
- `(1-2)` = item 1 of 2 items in this multi-line order
- `(2-2)` = item 2 of 2 items in this multi-line order

### Manifest CSV Files

All manifest CSVs share these **required columns** (must be present):
- `kaspi_name_core` — Product core name
- `size` — MY_SIZE value
- `sku_key` — SKU key
- `sku_id` — Full SKU ID (derived from sku_key + size)

**Sorting order for ALL manifests:**
1. `kaspi_name_core` (alphabetical)
2. `size` (Kids: 22→34, Men: S→4XL)
3. `sku_key` (alphabetical)
4. `sku_id` (alphabetical)

---

**manifest_normal_singles.csv:**
```csv
type,store,order_id,kaspi_name_core,size,sku_key,sku_id,quantity,kaspi_offer_name,output
NORMAL,Universal,725777649,Футболка_белая,M,CL_NEW-CLO_MEN_TSHIRT_WHITE,CL_NEW-CLO_MEN_TSHIRT_WHITE_M,1,Футболка белая мужская M,NORMAL_singles/Футболка_белая_M-1.pdf
```

---

**manifest_special_multi_qty.csv:** (same product, qty > 1)
```csv
type,store,order_id,kaspi_name_core,size,sku_key,sku_id,quantity,kaspi_offer_name,output
MULTI_QTY,Universal,725777649,Принт_5в1_черный,XL,CL_OC_MEN_LINE52_BLACK,CL_OC_MEN_LINE52_BLACK_XL,2,Комплект Принт 5в1 черный XL,SPECIAL_multi_qty/Местовая-1_Принт_5в1_черный_XL-2.pdf
MULTI_QTY,Universal,725777650,Принт_5в1_черный,2XL,CL_OC_MEN_LINE52_BLACK,CL_OC_MEN_LINE52_BLACK_2XL,3,Комплект Принт 5в1 черный 2XL,SPECIAL_multi_qty/Местовая-2_Принт_5в1_черный_2XL-3.pdf
```

---

**manifest_special_multi_line.csv:** (same OrderID, multiple SKUs)
```csv
type,store,order_id,items_count,kaspi_name_core,size,sku_key,sku_id,quantity,items_detail,output
MULTI_LINE,Universal,725777650,2,Длинный_рашгард_Белый,L,CL_NEW-CLO_MEN_RASH_WHITE,CL_NEW-CLO_MEN_RASH_WHITE_L,1,"Длинный_рашгард_Белый-L-1;Трусы_белые-L-1",SPECIAL_multi_line/Местовая-1_Длинный_рашгард_Белый-L-1(1-2)_Трусы_белые-L-1(2-2).pdf
```
Note: For multi-line, list the FIRST item's kaspi_name_core/size/sku for sorting, with `items_detail` containing all items.

---

**missing_orders.csv:** (missing PDF for xlsx row, OR missing xlsx row for PDF)
```csv
store,order_id,kaspi_name_core,size,sku_key,sku_id,reason
Universal,725777651,Тайтсы_черные,XL,CL_NEW-CLO_MEN_TAICI_BLACK,CL_NEW-CLO_MEN_TAICI_BLACK_XL,PDF_NOT_FOUND
Universal,725777652,UNKNOWN,,,,XLSX_ROW_MISSING
```

Reasons:
- `PDF_NOT_FOUND` — xlsx row exists but no matching waybill PDF
- `XLSX_ROW_MISSING` — PDF exists but no matching xlsx row

---

**build_log.csv:** (master log — ALL stores, ALL orders in one file)

Location: `excel_ui/Kaspi_orders/Today/build_log.csv`

```csv
type,store,order_id,kaspi_name_core,size,sku_key,sku_id,quantity,kaspi_offer_name,output,status,processed_at
NORMAL,Universal,725777649,Футболка_белая,M,CL_NEW-CLO_MEN_TSHIRT_WHITE,CL_NEW-CLO_MEN_TSHIRT_WHITE_M,1,Футболка белая мужская M,10.12.25_Universal_qnt61/NORMAL_singles/Футболка_белая_M-1.pdf,OK,2025-12-10T14:30:00
MULTI_QTY,Universal,725777650,Принт_5в1_черный,XL,CL_OC_MEN_LINE52_BLACK,CL_OC_MEN_LINE52_BLACK_XL,2,Комплект Принт 5в1 черный XL,10.12.25_Universal_qnt61/SPECIAL_multi_qty/Местовая-1_Принт_5в1_черный_XL-2.pdf,OK,2025-12-10T14:30:01
NORMAL,AcmeWear,725777651,Тайтсы_черные,L,CL_NEW-CLO_MEN_TAICI_BLACK,CL_NEW-CLO_MEN_TAICI_BLACK_L,1,Тайтсы черные мужской L,10.12.25_AcmeWear_qnt23/NORMAL_singles/Тайтсы_черные_L-1.pdf,OK,2025-12-10T14:30:02
NORMAL,Universal,725777652,Тайтсы_черные,XL,CL_NEW-CLO_MEN_TAICI_BLACK,CL_NEW-CLO_MEN_TAICI_BLACK_XL,1,,MISSING,PDF_NOT_FOUND,2025-12-10T14:30:03
```

Columns:
- `type` — NORMAL / MULTI_QTY / MULTI_LINE
- `store` — Store name
- `order_id` — Kaspi order ID
- `kaspi_name_core` — Product core name
- `size` — MY_SIZE
- `sku_key` — SKU key
- `sku_id` — Full SKU ID
- `quantity` — Item quantity
- `kaspi_offer_name` — Full Kaspi offer name
- `output` — Relative path to output PDF
- `status` — OK / PDF_NOT_FOUND / XLSX_ROW_MISSING
- `processed_at` — ISO timestamp

**Sorting:** Same as other manifests (kaspi_name_core → size → sku_key → sku_id)

### Package Summary File

**package_summary.csv** — Count packages before shipping:

| Сегодня | 10.12.2025 | |
|:--------|:----------:|:----------:|
| **Магазин** | **Заказов** | **Мест** |
| **Итого** | **79** | **83** |
| Universal | 58 | 60 |
| AcmeWear | 21 | 23 |
| 11KZ | 0 | 0 |

Where:
- **Сегодня** = Today's date
- **Магазин** = Store
- **Заказов** = Unique orders count
- **Мест** = Total distinct packages
- **Итого** = Total

### Package Counting Rules

**Heavy items (ALWAYS separate package):**
Items with weight ≥0.5 kg/unit average, or these specific SKUs:
```python
HEAVY_ITEMS = {
    # By kaspi_name_core
    'Костюм_мужской_Хус',
    'Костюм_Ромбик_ДЕТСКИЙ',
    'Спортивный_3в1_десткий_черный',
    'Принт_5в1_черный',
    'Line51',
    'Костюм_мужской_Ромбик',
    # By sku_key
    'CL_NEW-CLO2_MEN_SUIT-61_BLACK',
    'CL_NEW-CLO2_MEN_SUIT-51_BLACK_GREY',
    'CL_NK_MEN_LINE51_WHITE',
}
```

**Package counting logic:**
```python
def count_packages(orders: list) -> int:
    """
    Count distinct packages for shipping.
    
    Rules:
    - NORMAL_singles: 1 package per item
    - MULTI_LINE: 
        - If total qty ≤3 AND no heavy items → 1 package
        - If total qty >3 OR has heavy items → each heavy item = separate package
    - MULTI_QTY:
        - If qty ≤3 AND not heavy item → 1 package
        - If qty >3 OR heavy item → 1 package per item
    """
    packages = 0
    for order in orders:
        if order.type == 'NORMAL':
            packages += 1
        elif order.type == 'MULTI_LINE':
            heavy_count = sum(1 for item in order.items if is_heavy(item))
            light_count = len(order.items) - heavy_count
            if order.total_qty <= 3 and heavy_count == 0:
                packages += 1
            else:
                packages += heavy_count + (1 if light_count > 0 else 0)
        elif order.type == 'MULTI_QTY':
            if order.qty <= 3 and not is_heavy(order):
                packages += 1
            else:
                packages += order.qty
    return packages
```

### CLI Interface

```bash
# Build waybills for today
python scripts/build_daily_waybills.py \
    --crm-file excel_ui/SALES_KSP_CRM_V3.xlsx \
    --zip "excel_ui/ActiveOrders/waybill*.zip" \
    --output-dir excel_ui/Kaspi_orders/Today/

# Specific date
python scripts/build_daily_waybills.py --date 2025-12-10

# Dry run
python scripts/build_daily_waybills.py --dry-run

# Update CRM status after building
python scripts/build_daily_waybills.py --mark-shipped
```

**Output folders created:**
- `excel_ui/Kaspi_orders/Today/10.12.25_Universal_qnt61/`
- `excel_ui/Kaspi_orders/Today/10.12.25_AcmeWear_qnt23/`
- etc.

### Post-Build: Update CRM Status

After successful waybill build, optionally mark orders as shipped in CRM.

---

## Script 3: Mac Double-Click Commands

### `excel_ui/run_import_orders.command`

```bash
#!/bin/bash
# Import new Kaspi orders into CRM
# Double-click to run

cd ~/Docs/Autonomous_business
source .venv/bin/activate

echo "========================================"
echo "  Kaspi Order Import"
echo "========================================"
echo ""

python scripts/import_orders_to_crm.py \
    --orders-dir excel_ui/ActiveOrders/ \
    --crm-file excel_ui/SALES_KSP_CRM_V3.xlsx \
    --verbose

echo ""
echo "========================================"
echo "  Done! Press Enter to close..."
echo "========================================"
read
```

### `excel_ui/run_build_waybills.command`

```bash
#!/bin/bash
# Build grouped waybill PDFs
# Double-click to run AFTER setting MY_SIZE in CRM

cd ~/Docs/Autonomous_business
source .venv/bin/activate

echo "========================================"
echo "  Kaspi Waybill Builder"
echo "========================================"
echo ""

python scripts/build_daily_waybills.py \
    --crm-file excel_ui/SALES_KSP_CRM_V3.xlsx \
    --zip "excel_ui/ActiveOrders/waybill*.zip" \
    --output-dir excel_ui/Kaspi_orders/Today/ \
    --verbose

echo ""
echo "========================================"
echo "  Done! Press Enter to close..."
echo "========================================"
read
```

**Make executable:**
```bash
chmod +x excel_ui/run_import_orders.command
chmod +x excel_ui/run_build_waybills.command
```

---

## Reference: Existing Code to Reuse

### From `core/parsers/kaspi_export_parser.py`
- `parse_active_orders()` — Column normalization
- `filter_for_shipment()` — Status filtering
- Russian column mapping

### From `core/waybill/pdf_grouper.py`
- `WaybillGroup` dataclass
- `extract_waybills_from_zip()` — ZIP handling
- `group_orders()` — NORMAL/MULTI_LINE/MULTI_QTY logic
- `merge_pdfs()` — PyPDF2 merging

### From `config/kaspi_column_map.yaml`
- Russian → English column mapping
- Status value mapping

---

## Tests Required

### `tests/test_import_orders_to_crm.py` (12+ tests)
- test_parse_activeorders_columns
- test_filter_status_awaiting_courier
- test_filter_signature_not_required
- test_filter_by_date
- test_store_code_mapping
- test_deduplicate_existing_orders
- test_extract_kaspi_name_core
- test_date_parsing_dd_mm_yyyy
- test_date_parsing_excel_serial
- test_append_to_crm_preserves_formulas
- test_idempotent_reimport
- test_dry_run_no_changes

### `tests/test_build_daily_waybills.py` (20+ tests)
- test_filter_orders_with_size
- test_extract_waybills_from_zip
- test_group_normal_single
- test_group_multi_line_same_order
- test_group_multi_qty_same_product
- test_filename_normal_format
- test_filename_multiline_format_with_sequence
- test_filename_multiqty_format
- test_per_store_folders_with_date_qty
- test_manifest_has_required_columns (kaspi_name_core, size, sku_key, sku_id)
- test_manifest_sorting_by_core_size_sku
- test_manifest_size_sort_kids_22_to_34
- test_manifest_size_sort_men_s_to_4xl
- test_missing_orders_csv_pdf_not_found
- test_missing_orders_csv_xlsx_row_missing
- test_build_log_csv_all_stores
- test_build_log_csv_status_column
- test_pdf_merge_multi_line
- test_collision_handling
- test_dry_run_no_files
- test_package_count_normal
- test_package_count_heavy_items_separate
- test_package_count_multiline_under_3
- test_package_count_multiline_over_3
- test_package_summary_csv_format

---

## Success Criteria

1. ✅ `run_import_orders.command` double-click → new orders appear in CRM
2. ✅ Orders filtered correctly (status + signature + date)
3. ✅ No duplicates on re-run
4. ✅ Store codes mapped to names
5. ✅ User fills `MY_SIZE` column manually in Excel
6. ✅ `run_build_waybills.command` double-click → grouped PDFs created
7. ✅ Per-store folders with format `{DD.MM.YY}_{STORE}_qnt{total}/`
8. ✅ File naming: `{core}_{size}-{qty}.pdf` for normal, `Местовая-N_...` for special
9. ✅ Multi-line files show `(1-N)_(2-N)` sequence notation
10. ✅ Separate manifest CSVs per store (normal, multi_line, multi_qty)
11. ✅ All manifests have required columns: kaspi_name_core, size, sku_key, sku_id
12. ✅ All manifests sorted by: kaspi_name_core → size → sku_key → sku_id
13. ✅ build_log.csv at Today level with ALL stores/orders
14. ✅ missing_orders.csv with PDF_NOT_FOUND and XLSX_ROW_MISSING reasons
15. ✅ Package summary table with correct package counting (heavy items separate)
16. ✅ 32+ tests passing

---

## Constraints

1. **Use xlwings for CRM writes** (openpyxl corrupts external links)
2. **Use openpyxl for reading only** (header inspection, dedup checks)
3. **Preserve CRM formulas** in columns Q+ (Total_net_rev, etc.)
4. **Date parsing**: Handle DD.MM.YYYY, YYYY-MM-DD, Excel serial numbers
5. **Idempotent**: Re-running same day won't duplicate orders
6. **DO NOT modify** `~/Docs/kaspi_etl/` — that's the fallback
7. **PyPDF2** for PDF merging (already installed)

---

## Execution Order

1. TASK-191: Create `scripts/import_orders_to_crm.py`
2. TASK-192: Create `scripts/build_daily_waybills.py` (with package counting)
3. TASK-193: Create `.command` files for Mac double-click
4. TASK-194: Create tests (27+)
5. TASK-195: Update DAILY_SOP.md with new workflow

Commit after each task: `Phase 11: TASK-XXX - description`

---

## Appendix: Size Sort Order

For manifest_special_multi_qty.csv sorting:

```python
SIZE_ORDER_KIDS = ['22', '24', '26', '28', '30', '32', '34']
SIZE_ORDER_MEN = ['S', 'M', 'L', 'XL', '2XL', '3XL', '4XL']

def size_sort_key(size: str) -> tuple:
    """Return sort key for size ordering."""
    if size in SIZE_ORDER_KIDS:
        return (0, SIZE_ORDER_KIDS.index(size))
    elif size in SIZE_ORDER_MEN:
        return (1, SIZE_ORDER_MEN.index(size))
    else:
        return (2, size)  # Unknown sizes at end
```
