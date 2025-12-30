# Phase 11-12 Progress Report

## Overview

Phases 11 and 12 implement the automated daily Kaspi order workflow:
- **Phase 11**: Excel-based import and waybill building
- **Phase 12**: API-based shipping and waybill download

---

## Phase 11: Daily Kaspi Order Workflow (COMPLETED)

### Status: COMPLETE (5 tasks, 41 tests passing)

### Tasks Completed

| Task | Script | Description | Status |
|------|--------|-------------|--------|
| TASK-191 | `scripts/import_orders_to_crm.py` | Import orders from ActiveOrders.xlsx to CRM | DONE |
| TASK-192 | `scripts/build_daily_waybills.py` | Build waybill bundles by store/type | DONE |
| TASK-193 | `.command` files | macOS double-click launchers | DONE |
| TASK-194 | Tests | 41 tests for import and builder | DONE |
| TASK-195 | `docs/DAILY_SOP.md` | Operations documentation | DONE |

### Key Features

1. **Import Script** (`scripts/import_orders_to_crm.py`)
   - Parses `ActiveOrders*.xlsx` from Kaspi seller dashboard
   - Filters by status: "Ожидает передачи курьеру"
   - Filters by signature: "Не требуется"
   - Deduplicates against existing orders in CRM
   - Preserves Excel formulas (columns A-X)
   - Writes raw Kaspi data to columns Y-AZ

2. **Waybill Builder** (`scripts/build_daily_waybills.py`)
   - Reads CRM orders with MY_SIZE filled
   - Groups orders: NORMAL, MULTI_QTY, MULTI_LINE
   - Applies heavy item packaging logic
   - Generates organized output folders with manifests

3. **Package Counting Logic**
   ```
   NORMAL (qty=1):           1 package
   MULTI_QTY, qty<=3, light: 1 package
   MULTI_QTY, qty>3 or heavy: qty packages
   MULTI_LINE with heavy:    heavy_count + (1 if light items)
   ```

4. **Heavy Items** (always separate packages)
   - Костюм_мужской_Хус
   - Line51
   - Принт_5в1_черный
   - Костюм_Ромбик_ДЕТСКИЙ
   - Спортивный_3в1_детский_черный
   - CL_NEW-CLO2_MEN_SUIT-61_BLACK
   - CL_NEW-CLO2_MEN_SUIT-51_BLACK_GREY
   - CL_NK_MEN_LINE51_WHITE
   - CL_OC_MEN_LINE52_BLACK

---

## Phase 12: Automated API Shipping Workflow (COMPLETED)

### Status: COMPLETE (4 tasks)

### Tasks Completed

| Task | Script | Description | Status |
|------|--------|-------------|--------|
| Task 1 | `scripts/ship_orders_api.py` | Set package count, move to "Передача" | DONE |
| Task 2 | `scripts/download_waybills_api.py` | Download waybills via API | DONE |
| Task 3 | `build_daily_waybills.py` modification | Load from waybills folder | DONE |
| Task 4 | `run_build_waybills.command` update | 3-step workflow | DONE |

### Key Implementation Details

#### 1. Ship Orders API (`scripts/ship_orders_api.py`)

**Purpose**: Set "Количество мест" (package count) and move orders from "Упаковка" to "Передача"

**Workflow**:
1. Query API for orders in "Упаковка" stage (`get_pending_assembly_orders()`)
2. Match with CRM orders (MY_SIZE filled, planned_date <= today)
3. Calculate package count using heavy item logic
4. Call `assemble_order(order_code, parcel_count)`

**API Details**:
```python
# KaspiAPIClient.assemble_order()
data = {
    "data": {
        "type": "orders",
        "id": base64_order_id,
        "attributes": {
            "status": "ASSEMBLE",
            "numberOfSpace": str(parcel_count)  # Package count as STRING
        }
    }
}
```

**Test Results**:
```
UNIVERSAL: 28 orders pending assembly
ACMEWEAR: 27 orders pending assembly
Total: 55 orders ready to ship
```

#### 2. Download Waybills API (`scripts/download_waybills_api.py`)

**Purpose**: Download waybill PDFs for today's shipped orders only

**Critical Fix**: The original implementation downloaded ALL orders in KASPI_DELIVERY state (207+). The fix filters to only orders with `planned_date == target_date` (exact match).

**Filtering Logic**:
```python
# Default: exact_date=True - only today's batch
# --all-dates flag: include all historical orders
target_orders = get_target_order_ids_from_crm(
    crm_path, sheet_name, target_date,
    exact_date=not all_dates
)
```

**Test Results**:
```
Before fix: 207 waybills (all historical)
After fix:   78 waybills (Dec 10 batch only)
```

**Output Location**: `excel_ui/ActiveOrders/waybills/{order_code}.pdf`

#### 3. Build Daily Waybills Modification

**Change**: Added `load_all_waybills()` function to load from both:
1. ZIP files (legacy): `waybill*.zip`
2. API downloads (new): `waybills/{order_code}.pdf`

**Priority**: API downloads override ZIP extractions

#### 4. Updated Workflow (`run_build_waybills.command`)

```bash
#!/bin/bash
# 3-step automated workflow

# Step 1: Ship orders (set package count via API)
python scripts/ship_orders_api.py --verbose

# Step 2: Download waybills (via API)
python scripts/download_waybills_api.py --verbose

# Step 3: Build waybill bundles
python scripts/build_daily_waybills.py --verbose
```

---

## Environment Requirements

```bash
# Required in .env for API write operations
ENABLE_KASPI_WRITE=1
```

---

## Script Reference

| Script | Purpose | CLI Options |
|--------|---------|-------------|
| `import_orders_to_crm.py` | Import ActiveOrders to CRM | `--dry-run`, `--verbose`, `--date-end` |
| `build_daily_waybills.py` | Build waybill bundles | `--dry-run`, `--verbose`, `--date` |
| `ship_orders_api.py` | Ship orders via API | `--dry-run`, `--verbose`, `--store` |
| `download_waybills_api.py` | Download waybills | `--dry-run`, `--verbose`, `--all-dates` |
| `export_api_orders.py` | Export API orders to Excel | `--dry-run`, `--verbose`, `--all-stores` |

---

## Launcher Files

| File | Purpose |
|------|---------|
| `run_import_orders.command` | Import new orders (manual ActiveOrders download) |
| `run_import_orders_all_dates.command` | Import all orders (no date filter) |
| `run_full_import.command` | API export + CRM import |
| `run_build_waybills.command` | Full 3-step workflow (ship + download + build) |

---

## Store Mapping

| Kaspi Warehouse Code | Display Name | API Code |
|---------------------|--------------|----------|
| 30137883_PP1 | AcmeWear | ACMEWEAR |
| 30000001_PP1 | Universal | UNIVERSAL |
| 30290083_PP1 | 11KZ | 11KZ |
| 30000002_PP1 | STORE-B | STOREB |

---

## Known Issues and Fixes

### Issue 1: 265 → 0 Import Filter Bug (FIXED)

**Root Cause**: Filter required `d is not None and d <= end_date`
**Fix**: Changed to `d is None or d <= end_date`
**Location**: `scripts/import_orders_to_crm.py`, line 166

### Issue 2: Waybill Over-Download (FIXED)

**Root Cause**: Downloaded all 207 KASPI_DELIVERY orders instead of today's batch
**Fix**: Added `exact_date` filter to match only `planned_date == target_date`
**Location**: `scripts/download_waybills_api.py`, `get_target_order_ids_from_crm()`

---

## Success Criteria

- [x] Import orders deduplicates correctly
- [x] CRM formulas preserved after import
- [x] Package count calculated correctly (heavy items separate)
- [x] Orders move from "Упаковка" to "Передача" via API
- [x] Waybills download for today's batch only (not historical)
- [x] Waybill bundles created with correct grouping
- [x] Dry-run mode works for all scripts
- [x] 41 tests passing

---

*Document version: 1.0*
*Last updated: 2025-12-11*
