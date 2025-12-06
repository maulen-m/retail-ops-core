# Legacy Kaspi Scripts Audit

**TASK-110 Output**  
**Date:** 2025-12-06  
**Audited By:** Claude (Code Captain)  
**Source:** `pdf_sales_scripts_wrokflow_V3.md`

---

## Executive Summary

Two legacy scripts handle Kaspi order processing:

| Script | Purpose | LOC | Dependencies |
|--------|---------|-----|--------------|
| `import_active_orders.py` | ActiveOrders Excel → CRM append | ~150 | xlwings, pandas, psutil |
| `build_kaspi_orders.py` | Waybill ZIP → Grouped PDFs | ~350 | PyPDF2, pandas, shutil |

**Critical Finding:** Both scripts are tightly coupled to:
1. **xlwings** — requires Excel app running (macOS specific quirks)
2. **Hardcoded paths** — `~/Docs/kaspi_etl/docs/ops/kaspi/`
3. **Russian column names** — must match exactly or script fails silently

---

## Script 1: `import_active_orders.py`

### 1.1 Purpose
Appends new orders from Kaspi "ActiveOrders" Excel export to master CRM database (`SALES_KSP_CRM_V3.xlsx`).

### 1.2 File Locations

| Item | Path |
|------|------|
| Script | `docs/ops/kaspi/import_active_orders.py` |
| Master CRM | `docs/ops/kaspi/SALES_KSP_CRM_V3.xlsx` |
| Input Source | `~/Downloads/ActiveOrders*.xlsx` |
| Target Sheet | `SALES_KSP_CRM_1` |
| Target Table | Excel ListObject named `CRM` |

### 1.3 Input Schema (Kaspi ActiveOrders Export)

| Russian Column | English Equivalent | Data Type | Required |
|----------------|-------------------|-----------|----------|
| `№ заказа` | order_id | String | ✓ |
| `Статус` | status | String | ✓ |
| `Дата создания` | created_date | DateTime | |
| `Плановая дата передачи курьеру` | planned_date | DateTime | ✓ |
| `Название товара` | product_name | String | ✓ |
| `Артикул` | article/sku | String | ✓ |
| `Цена` | price | Number | ✓ |
| `Склад` | store/warehouse | String | ✓ |
| `Требуется подписание` | signature_required | String | |

### 1.4 Filter Logic

```python
# Status filter (EXACT MATCH required)
mask_status = df['Статус'] == 'Ожидает передачи курьеру'

# Signature filter (optional column)
mask_sign = df.get('Требуется подписание', 'Не требуется') == 'Не требуется'

# Date filter (planned date <= today)
df['PlanDate'] = pd.to_datetime(df['Плановая дата передачи курьеру'], dayfirst=True)
mask_date = df['PlanDate'] <= datetime.now()

# Combined
df_filtered = df[mask_status & mask_sign & mask_date]
```

**Edge Cases:**
- If `Требуется подписание` column missing → defaults to pass
- Date format assumed `DD.MM.YYYY` → `dayfirst=True` critical
- Empty result → script exits gracefully with message

### 1.5 Deduplication Logic

```python
# Read existing OrderIDs from CRM table
existing_data = tbl.range.options(pd.DataFrame, index=False, expand='table').value
existing_ids = set(existing_data['OrderID'].astype(str))

# Skip if already exists
for _, row in df_filtered.iterrows():
    oid = str(row['№ заказа'])
    if oid in existing_ids:
        continue  # Skip duplicate
```

**Note:** Dedup is by `OrderID` only, not `(OrderID, SKU)`. Multi-line orders (same OrderID, different SKUs) may have issues.

### 1.6 Output Schema (CRM Table)

| Column Index | Header | Source Column |
|--------------|--------|---------------|
| A | Date | `PlanDate.date()` |
| B | OrderID | `№ заказа` |
| C | SKU | `Артикул` |
| D | Name | `Название товара` |
| E | Price | `Цена` |
| F | Store | `Склад` |

### 1.7 xlwings Specifics

```python
app = xw.App(visible=False)  # Hidden Excel
wb = app.books.open(CRM_PATH)
sheet = wb.sheets['SALES_KSP_CRM_1']
tbl = sheet.tables['CRM']  # ListObject must exist

# Write after last row
start_row = tbl.range.last_cell.row + 1
sheet.range(f"A{start_row}").value = rows_to_add
wb.save()
```

**Risks:**
- Excel must not be open elsewhere (file lock)
- Formulas in CRM table may break if rows inserted incorrectly
- macOS requires Automation permissions for xlwings

### 1.8 Migration Requirements

| Requirement | Project 3 Solution |
|-------------|-------------------|
| xlwings dependency | Replace with openpyxl or pure DB |
| Hardcoded CRM path | Config-driven path |
| Russian columns | Column map YAML |
| Dedup by OrderID only | Dedup by (order_id, sku_id, store_code) |
| Excel ListObject write | Direct to SQLite fact_orders_kaspi |

---

## Script 2: `build_kaspi_orders.py`

### 2.1 Purpose
Groups waybill PDFs by product/size/quantity for efficient shipment preparation.

### 2.2 File Locations

| Item | Path |
|------|------|
| Script | `docs/ops/kaspi/build_kaspi_orders.py` |
| Input Excel | Any `.xlsx` with required columns |
| Input Waybills | ZIP files containing `KASPI_SHOP-<OrderID>.pdf` |
| Output | `_output_<date>/` directory |

### 2.3 Input Schema (Orders Excel)

| Column | Data Type | Required | Notes |
|--------|-----------|----------|-------|
| `Date` | Date | ✓ | Filter for target send date |
| `STORE_NAME` | String | ✓ | Used in output filename |
| `OrderID` | String | ✓ | Links to waybill PDF |
| `Quantity` | Integer | ✓ | Determines grouping type |
| `Kaspi_name_core` | String | ✓ | Product identifier |
| `MY_SIZE` | String | ✓ | Size code |

### 2.4 Grouping Logic

```
┌─────────────────────────────────────────────────────────────┐
│                    ORDER CLASSIFICATION                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Is Quantity > 1?                                           │
│       │                                                     │
│       ├── YES ──► SPECIAL_multi_qty                         │
│       │           Group by Kaspi_name_core across orders    │
│       │           Filename: <core>___qnt<sum>.pdf           │
│       │                                                     │
│       └── NO ──► Does OrderID appear on multiple lines?     │
│                       │                                     │
│                       ├── YES ──► SPECIAL_multi_line        │
│                       │           Merge all SKUs for order  │
│                       │           Filename: <store>___      │
│                       │             ORDER<id>_<n>items.pdf  │
│                       │                                     │
│                       └── NO ──► NORMAL_singles             │
│                                   Single PDF per item       │
│                                   Filename: <store>___      │
│                                     <size>___<item>.pdf     │
└─────────────────────────────────────────────────────────────┘
```

### 2.5 Detailed Grouping Rules

#### MULTI_QTY (Quantity > 1)
```python
# Group ACROSS orders by Kaspi_name_core
# If order has Quantity=3, find 3 waybills with same product
# Merge into single PDF

groups = df[df['Quantity'] > 1].groupby('Kaspi_name_core')
for core, group_df in groups:
    total_qty = group_df['Quantity'].sum()
    order_ids = group_df['OrderID'].tolist()
    # Find matching waybills and merge
    fname = f"{core}___qnt{total_qty}.pdf"
```

#### MULTI_LINE (Multiple SKUs per Order)
```python
# Same OrderID appears on multiple rows (different items)
order_counts = df['OrderID'].value_counts()
multi_line_orders = order_counts[order_counts > 1].index

for oid in multi_line_orders:
    items = df[df['OrderID'] == oid]
    n_items = len(items)
    store = items.iloc[0]['STORE_NAME']
    fname = f"{store}___ORDER{oid}_{n_items}items.pdf"
```

#### NORMAL (Single Item, Quantity=1)
```python
# Standard case: one item, one waybill
fname = f"{store}___{size}___{item_name}.pdf"

# Collision handling: if file exists, append order_id
if os.path.exists(dest):
    fname = f"{store}___{size}___{item_name}_{oid}.pdf"
```

### 2.6 Waybill PDF Extraction

```python
# ZIP contains files like: KASPI_SHOP-123456789.pdf
# Pattern: KASPI_SHOP-<OrderID>.pdf

def extract_order_id(filename):
    # KASPI_SHOP-123456789.pdf → 123456789
    match = re.search(r'KASPI_SHOP-(\d+)\.pdf', filename)
    return match.group(1) if match else None

# Build map: order_id → pdf_path
waybill_map = {}
for pdf_file in temp_dir.glob('*.pdf'):
    oid = extract_order_id(pdf_file.name)
    if oid:
        waybill_map[oid] = pdf_file
```

### 2.7 Output Structure

```
_output_2025-12-06/
├── NORMAL_singles/
│   ├── PP1___L___LINE52_BLACK.pdf
│   ├── PP1___M___LINE52_BLACK.pdf
│   └── PP2___XL___LINE51_WHITE.pdf
├── SPECIAL_multi_line/
│   ├── PP1___ORDER123456_2items.pdf
│   └── PP2___ORDER789012_3items.pdf
├── SPECIAL_multi_qty/
│   ├── LINE52_BLACK___qnt5.pdf
│   └── LINE51_WHITE___qnt3.pdf
├── manifest.csv          # All processed orders
├── missing_orders.csv    # Orders without waybills
└── build_log.csv         # Processing log
```

### 2.8 Filename Sanitization

```python
def sanitize_filename(name):
    """Remove/replace characters that break file systems."""
    # Replace: / \ : * ? " < > |
    invalid_chars = r'[/\\:*?"<>|]'
    return re.sub(invalid_chars, '_', name)
```

**Edge Cases:**
- Store names with `/` (e.g., "Store 1/2") → replaced with `_`
- Product names with quotes → replaced with `_`
- Very long names → may need truncation (not currently handled)

### 2.9 Migration Requirements

| Requirement | Project 3 Solution |
|-------------|-------------------|
| Standalone script | Integrate into daily pipeline |
| Hardcoded output dir | Config-driven output path |
| Manual date selection | Auto-detect from planned_date |
| Missing `MY_SIZE` handling | Pull from fact_orders_kaspi |
| PyPDF2 for merge | Keep PyPDF2 (stable, maintained) |

---

## Data Flow: Current vs Target

### Current Flow (Manual)
```
┌──────────────┐    Manual     ┌──────────────┐    Manual     ┌──────────────┐
│ Kaspi Web UI │ ──────────► │ ActiveOrders │ ──────────► │   CRM.xlsx   │
│  (5 stores)  │   Download   │    .xlsx     │   xlwings    │              │
└──────────────┘              └──────────────┘              └──────────────┘
        │                            │
        │ Manual                     │ Manual
        ▼ Download                   ▼
┌──────────────┐              ┌──────────────┐              ┌──────────────┐
│ Waybills.zip │ ──────────► │  Grouped     │ ──────────► │  Shipment    │
│              │   Script    │   PDFs       │   Manual    │  to Courier  │
└──────────────┘              └──────────────┘              └──────────────┘
```

### Target Flow (Phase 9.5)
```
┌──────────────┐    API Poll   ┌──────────────┐    Auto      ┌──────────────┐
│  Kaspi API   │ ──────────► │ fact_orders  │ ──────────► │  Alerts &    │
│  (5 stores)  │   5 min     │   _kaspi     │             │  Dashboard   │
└──────────────┘              └──────────────┘              └──────────────┘
        │                            │
        │ API                        │ Auto
        ▼ waybill URL               ▼
┌──────────────┐              ┌──────────────┐              ┌──────────────┐
│ Download     │ ──────────► │  Grouped     │ ──────────► │  Shipment    │
│ Parallel     │   Auto      │   PDFs       │   Ready     │  Ready Alert │
└──────────────┘              └──────────────┘              └──────────────┘
```

---

## Column Mapping Summary

### ActiveOrders → fact_orders_kaspi

| Kaspi Column (Russian) | fact_orders_kaspi Column | Transform |
|------------------------|-------------------------|-----------|
| `№ заказа` | `order_id` | str() |
| `Статус` | `kaspi_status` | direct |
| `Дата создания` | `created_at` | pd.to_datetime(dayfirst=True) |
| `Плановая дата передачи курьеру` | `planned_shipment_date` | pd.to_datetime(dayfirst=True) |
| `Название товара` | `kaspi_offer_name` | direct |
| `Артикул` | (parse) | extract sku_key, sku_id, my_size |
| `Цена` | `unit_price_kzt` | float |
| `Склад` | `store_code` | normalize to PP1/PP2/etc |
| `Требуется подписание` | (filter only) | not stored |
| (derived) | `internal_status` | NEW/READY/SHIPPED |

### Status Mapping

| Kaspi Status (Russian) | Internal Status | Action |
|------------------------|-----------------|--------|
| `Ожидает передачи курьеру` | READY | Include in shipment |
| `Принят` | NEW | Not ready yet |
| `Передан курьеру` | SHIPPED | Already shipped |
| `Завершен` | COMPLETED | Done |
| `Отменен` | CANCELLED | Exclude |

---

## Edge Cases to Handle

### 1. Multi-Line Orders
- Same OrderID with multiple SKUs
- Current: Groups into SPECIAL_multi_line
- Risk: Dedup by OrderID alone may skip valid lines

### 2. Quantity Mismatch
- Excel shows Quantity=3 but only 2 waybills in ZIP
- Current: Logs to missing_orders.csv
- Target: Alert and flag for manual review

### 3. Size Extraction Failures
- Kaspi `Артикул` doesn't always contain size
- Current: Falls back to empty or "UNKNOWN"
- Target: Lookup from dim_sku_size by kaspi_offer_name

### 4. Store Name Variations
- Kaspi may use different names: "PP1", "ПП1", "AcmeWear PP1"
- Current: Uses as-is
- Target: Normalize via store_code map

### 5. Date Format Variations
- Most: `DD.MM.YYYY`
- Some: `YYYY-MM-DD`
- Some: Excel serial numbers
- Target: Robust date parser with multiple format attempts

---

## Recommended Migration Order

1. **TASK-111:** Create column map YAML (1 hr)
2. **TASK-112:** Build parser with robust date handling (3 hrs)
3. **TASK-114:** Create fact_orders_kaspi table (1 hr)
4. **TASK-113:** Build ingestion CLI (3 hrs)
5. **TASK-115:** Rebuild PDF grouper (4 hrs)
6. **TASK-116:** Build waybill CLI (3 hrs)
7. **TASK-117-118:** Tests (4 hrs)
8. **Validation:** Side-by-side test vs legacy output

---

## Appendix: Full Column List from Kaspi Export

Based on documented exports, full column set:

```
№ заказа
Статус
Дата создания
Плановая дата передачи курьеру
Требуется подписание
Название товара
Артикул
Цена
Количество
Склад
Способ доставки
Адрес доставки
ФИО получателя
Телефон получателя
Комментарий
```

**Note:** Not all columns present in all exports. Parser must handle missing columns gracefully.

---

*Audit complete. Proceed to TASK-111 for column mapping.*
