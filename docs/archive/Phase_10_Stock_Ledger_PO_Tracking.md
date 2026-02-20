# Phase 10: Stock Ledger & PO Tracking System
## Implementation Plan for Opus Agent

**Date:** 2025-12-10  
**Estimated Effort:** 1 hour  
**Priority:** HIGH (foundation for autonomous operations)  
**Prerequisites:** Phase 9.6 complete (86 tests passing)

---

## Overview

Build an event-sourced stock tracking system with proper PO lifecycle management. This replaces the current `fact_inventory_snapshot_size` approach with a full ledger that tracks every stock change.

### Key Constraints (from Adil)

1. **Sales File Path:** `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`
2. **Sales Dedup Key:** `(order_id, sku_id, store_code, kaspi_offer_name)` — NOT simpler keys, because:
   - Same order can have same kaspi_offer_name with qty=2 but customer needs 2 different sizes (split into 2 rows)
   - Same order can have 2 different kaspi_offer_name with same or different sku_id
3. **Payment Timing:**
   - CNY to supplier: After `ship_date_seller` (when supplier sends to China warehouse), takes up to 10 days
   - FX rate (CNY/KZT) is known when paying
   - Cargo payment: USD at Astana arrival, rate 2.66$/kg for clothes, paid by that day's USD/KZT rate
4. **Lead Time:** L=21 days is `ship_date_cargo` → `ast_arrival_date` (Almaty-Astana is ~3 days of that)
5. **Supplier Prep:** After `message_date`, supplier prepares PO (up to 20 days, ~70kg/day speed), then sends to China warehouse (1-2 days), then cargo ships
6. **Returns:** Not tracked manually in Excel. System reads "Return" column from SALES_KSP_CRM_V3.xlsx and updates from API. Track in DB with write logs.
7. **Legacy Protection:** Do NOT modify files in `~/Docs/kaspi_etl/` — that's fallback if new system fails

---

## File Structure

```
~/Docs/Autonomous_business/
├── core/
│   ├── db/
│   │   ├── __init__.py (existing)
│   │   ├── queries.py (existing)
│   │   ├── schema_v2.sql (NEW - ledger tables)
│   │   └── ledger.py (NEW - ledger operations)
│   ├── calc/
│   │   ├── size_allocation.py (existing)
│   │   └── landed_cost.py (NEW - cost calculations)
│   ├── ingest/
│   │   ├── __init__.py (NEW)
│   │   ├── sales_ingest.py (NEW - sales file ingestion)
│   │   └── po_ingest.py (NEW - PO operations)
│   └── po/
│       ├── __init__.py (NEW)
│       ├── lifecycle.py (NEW - PO state machine)
│       └── eta.py (NEW - ETA calculations)
├── scripts/
│   ├── migrate_010_ledger.py (NEW - schema migration)
│   ├── bootstrap_ledger.py (NEW - initial stock load)
│   ├── ingest_sales_v2.py (NEW - sales ingestion CLI)
│   ├── po_cli.py (NEW - PO management CLI)
│   ├── rebuild_snapshot.py (NEW - ledger → snapshot)
│   └── daily_pipeline_v2.py (NEW - updated pipeline)
├── tests/
│   ├── test_stock_ledger.py (NEW)
│   ├── test_po_lifecycle.py (NEW)
│   ├── test_sales_ingest.py (NEW)
│   ├── test_landed_cost.py (NEW)
│   └── test_eta_calc.py (NEW)
├── excel_ui/
│   └── SALES_KSP_CRM_V3.xlsx (existing - sales source)
├── excel/
│   ├── Current_stock_2025-12-09.xlsx (existing - bootstrap source)
│   └── Inbound_template_09.12.2025.xlsx (existing - PO template reference)
└── db/
    └── app.db (existing - will be migrated)
```

---

## Database Schema Additions

### New Tables

```sql
-- ============================================================================
-- STOCK LEDGER (Event-Sourced Stock Tracking)
-- ============================================================================

CREATE TABLE IF NOT EXISTS stock_ledger (
    ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_date DATE NOT NULL,                    -- Date of stock change
    event_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    event_type TEXT NOT NULL,                    -- INITIAL/SALE/INBOUND/ADJUSTMENT/RETURN/WRITE_OFF
    sku_key TEXT NOT NULL,                       -- Style-level (FK to dim_sku)
    sku_id TEXT NOT NULL,                        -- Size-level (FK to dim_sku_size)
    my_size TEXT NOT NULL,
    store_code TEXT DEFAULT 'UNIVERSAL',
    qty_change INTEGER NOT NULL,                 -- +inbound, -sale
    running_balance INTEGER,                     -- Optional: running total after this event
    reference_id TEXT,                           -- order_id, po_id, adjustment_id
    reference_type TEXT,                         -- SALE/PO/ADJUSTMENT
    kaspi_offer_name TEXT,                       -- For sales events
    notes TEXT,
    input_source TEXT DEFAULT 'SYSTEM',          -- SYSTEM/MANUAL/IMPORT/API
    created_by TEXT DEFAULT 'system',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ledger_sku ON stock_ledger(sku_id, event_date);
CREATE INDEX idx_ledger_date ON stock_ledger(event_date);
CREATE INDEX idx_ledger_ref ON stock_ledger(reference_id, reference_type);

-- ============================================================================
-- PO HEADER (Purchase Order Lifecycle)
-- ============================================================================

CREATE TABLE IF NOT EXISTS po_header (
    po_id TEXT PRIMARY KEY,                      -- e.g., PO-2025-047
    supplier_code TEXT DEFAULT 'SUPP_A',
    
    -- Dates (Manual inputs marked with *)
    message_date DATE,                           -- * When PO message sent to supplier
    est_prep_days INTEGER,                       -- Auto: estimated prep days based on weight
    ship_date_seller DATE,                       -- * When supplier sent to China warehouse
    ship_date_cargo DATE,                        -- * When cargo shipped from China
    alm_arrival_nom DATE,                        -- Auto: nominal ETA to Almaty
    ast_arrival_nom DATE,                        -- Auto: nominal ETA to Astana
    alm_arrival_real DATE,                       -- * Actual arrival in Almaty
    ast_arrival_real DATE,                       -- * Actual arrival in Astana
    archive_alm_arrival DATE,                    -- Auto-lock: first real ALM arrival (immutable)
    archive_ast_arrival DATE,                    -- Auto-lock: first real AST arrival (immutable)
    estimate_delay_days INTEGER DEFAULT 0,       -- * Manual delay buffer
    
    -- Status
    status TEXT DEFAULT 'DRAFT',                 -- DRAFT/SENT/PREPARING/SHIPPED_SELLER/SHIPPED_CARGO/IN_TRANSIT/ARRIVED_ALM/ARRIVED_AST/RECEIVED/CLOSED
    
    -- Units
    units_total INTEGER DEFAULT 0,               -- Auto: sum of po_line.order_qty
    units_received INTEGER DEFAULT 0,            -- Auto: sum of po_line.received_qty
    weight_nom_kg REAL DEFAULT 0,                -- Auto: sum of (order_qty × unit_weight)
    weight_real_kg REAL,                         -- * Actual weight from cargo invoice
    
    -- Cargo tracking
    cargo_freight_id TEXT,                       -- * Cargo provider tracking ID
    total_places INTEGER,                        -- * Number of bags/boxes
    
    -- Costs - CNY (supplier payment)
    fx_rate_cny_plan REAL DEFAULT 78.0,          -- Planned CNY/KZT rate
    fx_rate_cny_actual REAL,                     -- * Actual CNY/KZT at payment
    payment_date_cny DATE,                       -- * When CNY payment completed
    total_cost_cny REAL DEFAULT 0,               -- Auto: sum of po_line costs
    total_cost_kzt_supplier REAL,                -- Auto: total_cost_cny × fx_rate_cny_actual
    
    -- Costs - USD (cargo payment)
    cargo_rate_usd_kg REAL DEFAULT 2.66,         -- USD per kg for clothes
    fx_rate_usd_kzt REAL,                        -- * USD/KZT rate at cargo payment
    payment_date_cargo DATE,                     -- * When cargo payment completed
    cargo_cost_usd REAL,                         -- Auto: weight_real_kg × cargo_rate_usd_kg
    cargo_cost_kzt REAL,                         -- Auto: cargo_cost_usd × fx_rate_usd_kzt
    
    -- Totals
    total_landed_cost_kzt REAL,                  -- Auto: supplier + cargo costs
    
    -- Audit
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- PO LINE (Size-Level PO Items)
-- ============================================================================

CREATE TABLE IF NOT EXISTS po_line (
    po_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
    po_id TEXT NOT NULL,                         -- FK to po_header
    sku_key TEXT NOT NULL,                       -- Style-level SKU
    sku_id TEXT NOT NULL,                        -- Size-level SKU
    my_size TEXT NOT NULL,
    
    -- Quantities
    order_qty INTEGER NOT NULL,                  -- Units ordered
    received_qty INTEGER DEFAULT 0,              -- Units received so far
    
    -- Costs
    unit_cost_cny REAL NOT NULL,                 -- Unit cost in CNY
    unit_cost_kzt REAL,                          -- Auto: unit_cost_cny × fx_rate_cny_actual
    freight_share_kzt REAL,                      -- Auto: proportional cargo cost
    landed_cost_unit_kzt REAL,                   -- Auto: unit_cost_kzt + freight_share per unit
    
    -- Status
    status TEXT DEFAULT 'PENDING',               -- PENDING/PARTIAL/RECEIVED
    receive_date DATE,                           -- When fully received
    
    -- Audit
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (po_id) REFERENCES po_header(po_id)
);

CREATE INDEX idx_po_line_po ON po_line(po_id);
CREATE INDEX idx_po_line_sku ON po_line(sku_id);

-- ============================================================================
-- SALES FACT V2 (Enhanced with return tracking)
-- ============================================================================

CREATE TABLE IF NOT EXISTS sales_fact_v2 (
    sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL,
    order_date DATE NOT NULL,
    sku_key TEXT NOT NULL,
    sku_id TEXT NOT NULL,
    my_size TEXT NOT NULL,
    kaspi_offer_name TEXT NOT NULL,              -- Part of unique key
    store_code TEXT DEFAULT 'UNIVERSAL',
    
    -- Quantities
    quantity INTEGER NOT NULL,
    
    -- Prices
    sell_price_kzt REAL,
    delivery_fee REAL,
    cogs REAL,
    net_rev REAL,
    profit REAL,
    
    -- Status
    status TEXT DEFAULT 'DELIVERED',             -- DELIVERED/CANCELLED/RETURNED
    return_flag INTEGER DEFAULT 0,               -- From Excel "Return" column
    return_date DATE,                            -- When return was processed
    
    -- Source tracking
    ingested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    source_file TEXT,
    api_updated_at DATETIME,                     -- Last API status update
    
    -- Unique constraint for dedup
    UNIQUE(order_id, sku_id, store_code, kaspi_offer_name)
);

CREATE INDEX idx_sales_v2_order ON sales_fact_v2(order_id);
CREATE INDEX idx_sales_v2_date ON sales_fact_v2(order_date);
CREATE INDEX idx_sales_v2_sku ON sales_fact_v2(sku_id);

-- ============================================================================
-- INPUT AUDIT LOG (All human inputs tracked)
-- ============================================================================

CREATE TABLE IF NOT EXISTS fact_input_audit (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    record_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    change_type TEXT NOT NULL,                   -- INSERT/UPDATE/DELETE
    changed_by TEXT DEFAULT 'adil',
    changed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    reason TEXT,
    source TEXT DEFAULT 'MANUAL'                 -- MANUAL/API/SYSTEM
);

CREATE INDEX idx_audit_table ON fact_input_audit(table_name, record_id);
CREATE INDEX idx_audit_time ON fact_input_audit(changed_at);
```

---

## Milestone 1: Stock Ledger Foundation

### TASK-172: Create schema migration script
**File:** `scripts/migrate_010_ledger.py`

**What to build:**
- Read existing schema
- Create new tables: `stock_ledger`, `po_header`, `po_line`, `sales_fact_v2`, `fact_input_audit`
- Add indexes
- Verify migration success

**Test:** Run migration, verify all tables exist with correct columns

---

### TASK-173: Create ledger.py module
**File:** `core/db/ledger.py`

**Functions:**

```python
def add_ledger_event(
    event_type: str,           # INITIAL/SALE/INBOUND/ADJUSTMENT/RETURN/WRITE_OFF
    sku_id: str,
    qty_change: int,           # + or -
    event_date: date,
    reference_id: str = None,
    reference_type: str = None,
    kaspi_offer_name: str = None,
    notes: str = None,
    input_source: str = 'SYSTEM'
) -> int:
    """Insert event into stock_ledger, return ledger_id."""

def get_stock_balance(sku_id: str, as_of_date: date = None) -> int:
    """Calculate stock balance from ledger events."""

def get_stock_balances_all(as_of_date: date = None) -> dict[str, int]:
    """Get all SKU balances: {sku_id: balance}."""

def rebuild_snapshot_from_ledger(snapshot_date: date = None) -> int:
    """
    Rebuild fact_inventory_snapshot_size from stock_ledger.
    Also calculate inbound_stock from pending po_line.
    Returns number of snapshot rows created.
    """
```

**Tests:** 10 tests
- test_add_event_sale
- test_add_event_inbound
- test_add_event_adjustment
- test_get_balance_empty
- test_get_balance_after_events
- test_balance_multiple_events
- test_rebuild_snapshot_matches_ledger
- test_rebuild_includes_inbound
- test_negative_balance_allowed (edge case)
- test_event_date_vs_created_at

---

### TASK-174: Bootstrap ledger from current stock
**File:** `scripts/bootstrap_ledger.py`

**What to build:**
- Read `~/Docs/Autonomous_business/excel/Current_stock_2025-12-09.xlsx`
- For each row: create INITIAL event in stock_ledger
- Verify: sum of INITIAL events = sum of Excel rows

**Columns expected in Excel:**
- `sku_id` or `SKU_ID`
- `sku_key` or `SKU_key`
- `my_size` or `MY_SIZE`
- `current_stock` or `Current_stock`

**CLI:**
```bash
python scripts/bootstrap_ledger.py excel/Current_stock_2025-12-09.xlsx --date 2025-12-09
```

**Tests:** 4 tests
- test_bootstrap_creates_initial_events
- test_bootstrap_idempotent (re-run doesn't duplicate)
- test_bootstrap_matches_excel_totals
- test_bootstrap_handles_missing_columns

---

### TASK-175: Create rebuild_snapshot.py script
**File:** `scripts/rebuild_snapshot.py`

**What to build:**
- Call `rebuild_snapshot_from_ledger()`
- Calculate `inbound_stock` from `po_line WHERE status IN ('PENDING', 'PARTIAL')`
- Update `fact_inventory_snapshot_size` with new data
- Print summary

**CLI:**
```bash
python scripts/rebuild_snapshot.py              # Rebuild for today
python scripts/rebuild_snapshot.py --date 2025-12-09
python scripts/rebuild_snapshot.py --verbose
```

**Tests:** 3 tests
- test_rebuild_creates_snapshot
- test_rebuild_includes_pending_po_inbound
- test_rebuild_cli_runs

---

## Milestone 2: Sales Integration

### TASK-176: Create sales_ingest.py module
**File:** `core/ingest/sales_ingest.py`

**Key constraint:** Unique key is `(order_id, sku_id, store_code, kaspi_offer_name)`

**Functions:**

```python
def parse_sales_excel(
    xlsx_path: str,
    sheet_name: str = 'SALES_KSP_CRM_1'
) -> list[dict]:
    """
    Parse sales Excel file.
    
    Expected columns:
    - order_id / № заказа
    - order_date / Дата заказа
    - kaspi_offer_name / Название товара
    - sku_id (derived from kaspi_offer_name via Sku_Map)
    - quantity / Количество
    - sell_price / Сумма
    - Return (0/1 flag)
    - status
    
    Returns list of sale dicts.
    """

def ingest_sales(
    xlsx_path: str,
    apply_to_ledger: bool = True
) -> dict:
    """
    Ingest sales from Excel to sales_fact_v2 and stock_ledger.
    
    Steps:
    1. Parse Excel
    2. Map kaspi_offer_name → sku_id via dim_sku_size
    3. Deduplicate on (order_id, sku_id, store_code, kaspi_offer_name)
    4. Insert new records to sales_fact_v2
    5. For each new sale: add SALE event to stock_ledger (qty_change = -quantity)
    6. For returns (return_flag=1): add RETURN event (qty_change = +quantity)
    
    Returns: {'inserted': N, 'skipped': N, 'returns': N, 'unmapped': [...]}
    """

def get_unmapped_offers(xlsx_path: str) -> list[str]:
    """Return list of kaspi_offer_name not found in dim_sku_size."""
```

**Tests:** 12 tests
- test_parse_sales_excel
- test_parse_handles_russian_columns
- test_ingest_new_sales
- test_ingest_dedup_exact_key
- test_ingest_same_order_different_offers (should NOT dedup)
- test_ingest_same_order_same_offer_different_size (should NOT dedup - different sku_id)
- test_ingest_creates_sale_events
- test_ingest_return_flag_creates_return_event
- test_ingest_unmapped_logged
- test_ingest_idempotent
- test_ingest_updates_existing_status
- test_stock_decreases_after_sale

---

### TASK-177: Create ingest_sales_v2.py CLI
**File:** `scripts/ingest_sales_v2.py`

**CLI:**
```bash
# Ingest from default path
python scripts/ingest_sales_v2.py

# Ingest from specific file
python scripts/ingest_sales_v2.py --file excel_ui/SALES_KSP_CRM_V3.xlsx

# Dry run (no writes)
python scripts/ingest_sales_v2.py --dry-run

# Show unmapped offers
python scripts/ingest_sales_v2.py --show-unmapped

# Don't apply to ledger (just sales_fact_v2)
python scripts/ingest_sales_v2.py --no-ledger
```

**Output:**
```
Sales Ingestion Report (2025-12-10)
=====================================
Source: excel_ui/SALES_KSP_CRM_V3.xlsx
Sheet: SALES_KSP_CRM_1

New sales inserted:     47
Duplicates skipped:    128
Returns processed:       3
Unmapped offers:         2
  - "Куртка демисезонная NEW MODEL" (5 orders)
  - "Тестовый товар" (1 order)

Stock ledger events:    50 (47 SALE + 3 RETURN)
=====================================
```

**Tests:** 2 tests
- test_cli_dry_run
- test_cli_default_path

---

### TASK-178: Handle return updates from API
**File:** `core/ingest/sales_ingest.py` (extend)

**Function:**

```python
def update_returns_from_api(api_returns: list[dict]) -> int:
    """
    Update sales_fact_v2 with return status from API.
    
    For each return:
    1. Find matching sale in sales_fact_v2
    2. Update status = 'RETURNED', return_flag = 1, return_date = today
    3. Add RETURN event to stock_ledger if not already exists
    4. Log to fact_input_audit
    
    Returns: number of returns processed
    """
```

**Note:** API integration will come from Kaspi API module (existing). This function handles the DB updates once API data is retrieved.

**Tests:** 4 tests
- test_update_return_status
- test_return_adds_stock_back
- test_return_logged_to_audit
- test_duplicate_return_ignored

---

## Milestone 3: PO Tracking

### TASK-179: Create PO lifecycle module
**File:** `core/po/lifecycle.py`

**Status Machine:**
```
DRAFT → SENT → PREPARING → SHIPPED_SELLER → SHIPPED_CARGO → IN_TRANSIT → ARRIVED_ALM → ARRIVED_AST → RECEIVED → CLOSED
```

**Functions:**

```python
def create_po(supplier_code: str = 'SUPP_A') -> str:
    """
    Create new PO with auto-generated ID.
    Returns po_id (e.g., 'PO-2025-048').
    """

def add_po_line(
    po_id: str,
    sku_key: str,
    my_size: str,
    order_qty: int,
    unit_cost_cny: float
) -> int:
    """Add line to PO, update po_header totals. Returns po_line_id."""

def update_po_field(
    po_id: str,
    field_name: str,
    new_value: any,
    reason: str = None
) -> None:
    """
    Update PO field with audit logging.
    Auto-recalculates derived fields (ETAs, costs) as needed.
    Protects archive_* fields from modification.
    """

def get_po_status(po_id: str) -> dict:
    """Get full PO status including all lines and calculated fields."""

def confirm_po_arrival(
    po_id: str,
    arrival_type: str,  # 'ALM' or 'AST'
    arrival_date: date,
    received_quantities: dict[str, int] = None  # {sku_id: qty} for partial
) -> dict:
    """
    Confirm PO arrival.
    
    If arrival_type == 'AST' and received_quantities provided:
    1. Update po_line.received_qty
    2. Create INBOUND events in stock_ledger
    3. Update po_header.units_received
    4. Set status to RECEIVED or PARTIAL
    5. Lock archive_ast_arrival (immutable after first set)
    
    Returns: {'units_received': N, 'status': 'RECEIVED'/'PARTIAL'}
    """

def close_po(po_id: str) -> None:
    """Close PO after all units received and costs finalized."""
```

**Tests:** 14 tests
- test_create_po_generates_id
- test_add_po_line_updates_totals
- test_update_field_logs_audit
- test_update_archive_field_blocked
- test_status_transitions
- test_confirm_arrival_alm
- test_confirm_arrival_ast_creates_inbound_events
- test_confirm_partial_arrival
- test_units_received_calculated
- test_close_po_requires_all_received
- test_weight_nom_calculated
- test_prep_days_estimated
- test_po_line_status_updates
- test_get_po_status_complete

---

### TASK-180: Create ETA calculation module
**File:** `core/po/eta.py`

**Lead Time Rules:**
- Supplier prep: estimate based on weight_nom_kg / 70 kg per day, max 20 days
- Supplier → China warehouse: 1-2 days
- Cargo ship → Astana: L = 21 days
- Almaty → Astana: ~3 days (part of L=21)

**Functions:**

```python
def estimate_prep_days(weight_kg: float, max_days: int = 20) -> int:
    """
    Estimate supplier prep days based on weight.
    Formula: ceil(weight_kg / 70), capped at max_days.
    """

def calc_eta(
    message_date: date = None,
    ship_date_seller: date = None,
    ship_date_cargo: date = None,
    estimate_delay_days: int = 0
) -> tuple[date, date]:
    """
    Calculate nominal ETAs.
    
    Logic:
    1. If ship_date_cargo set:
       alm_arrival_nom = ship_date_cargo + 18 days
       ast_arrival_nom = ship_date_cargo + 21 days + delay
    2. Elif ship_date_seller set:
       alm_arrival_nom = ship_date_seller + 20 days  (1-2 days to cargo + 18)
       ast_arrival_nom = ship_date_seller + 23 days + delay
    3. Else (only message_date):
       # Estimate: prep + ship + transit
       alm_arrival_nom = message_date + est_prep_days + 20 days
       ast_arrival_nom = message_date + est_prep_days + 23 days + delay
    
    Returns (alm_arrival_nom, ast_arrival_nom)
    """

def recalc_all_etas() -> int:
    """Recalculate ETAs for all non-closed POs. Returns count updated."""
```

**Tests:** 8 tests
- test_estimate_prep_days
- test_estimate_prep_capped
- test_eta_from_message_date
- test_eta_from_ship_seller
- test_eta_from_ship_cargo
- test_eta_with_delay
- test_eta_updates_po_header
- test_recalc_all_etas

---

### TASK-181: Create landed cost module
**File:** `core/calc/landed_cost.py`

**Cost Structure:**
- Supplier cost: `unit_cost_cny × fx_rate_cny_actual` (after payment)
- Cargo cost: `weight_real_kg × 2.66 × fx_rate_usd_kzt` (after AST arrival)
- Landed cost per unit: `unit_cost_kzt + (freight_share / order_qty)`

**Functions:**

```python
def calc_supplier_costs(po_id: str) -> None:
    """
    Calculate supplier costs after fx_rate_cny_actual is set.
    Updates po_line.unit_cost_kzt and po_header.total_cost_kzt_supplier.
    """

def calc_cargo_costs(po_id: str) -> None:
    """
    Calculate cargo costs after weight_real_kg and fx_rate_usd_kzt are set.
    Updates po_header.cargo_cost_usd, cargo_cost_kzt.
    """

def calc_landed_costs(po_id: str) -> None:
    """
    Calculate full landed costs per line.
    
    For each po_line:
    1. Get weight share: (order_qty × unit_weight) / weight_real_kg
    2. freight_share_kzt = cargo_cost_kzt × weight_share
    3. landed_cost_unit_kzt = unit_cost_kzt + (freight_share_kzt / order_qty)
    
    Also updates po_header.total_landed_cost_kzt.
    """

def get_sku_landed_cost(po_id: str, sku_id: str) -> float:
    """Get landed cost for specific SKU/size from a PO."""
```

**Tests:** 8 tests
- test_calc_supplier_costs
- test_calc_cargo_costs
- test_calc_landed_costs
- test_freight_share_proportional_to_weight
- test_landed_cost_per_unit
- test_requires_fx_rates
- test_requires_real_weight
- test_total_landed_matches_sum

---

### TASK-182: Create PO CLI
**File:** `scripts/po_cli.py`

**Commands:**

```bash
# Create new PO
python scripts/po_cli.py create --supplier SUPP_A

# Add lines to PO
python scripts/po_cli.py add-line PO-2025-048 --sku LINE52_BLACK --size XL --qty 50 --cost 47

# Update PO field
python scripts/po_cli.py update PO-2025-048 --message-date 2025-12-10
python scripts/po_cli.py update PO-2025-048 --ship-seller 2025-12-15
python scripts/po_cli.py update PO-2025-048 --ship-cargo 2025-12-17
python scripts/po_cli.py update PO-2025-048 --fx-cny 78.5
python scripts/po_cli.py update PO-2025-048 --delay-days 3

# Confirm arrival
python scripts/po_cli.py arrive PO-2025-048 --type ALM --date 2025-12-30
python scripts/po_cli.py arrive PO-2025-048 --type AST --date 2026-01-02

# Receive inventory (confirms AST arrival + adds to stock)
python scripts/po_cli.py receive PO-2025-048 --date 2026-01-02
python scripts/po_cli.py receive PO-2025-048 --partial --sku LINE52_BLACK_XL:45,LINE52_BLACK_L:30

# Enter cargo costs
python scripts/po_cli.py cargo PO-2025-048 --weight 72.5 --usd-rate 525

# View PO status
python scripts/po_cli.py show PO-2025-048

# List all POs
python scripts/po_cli.py list
python scripts/po_cli.py list --status IN_TRANSIT
```

**Tests:** 5 tests (CLI integration)
- test_create_po_cli
- test_update_po_cli
- test_arrive_po_cli
- test_receive_creates_inbound_events
- test_show_po_cli

---

## Milestone 4: Audit Trail

### TASK-183: Create audit logging decorator
**File:** `core/db/ledger.py` (extend)

**Functions:**

```python
def log_audit(
    table_name: str,
    record_id: str,
    field_name: str,
    old_value: any,
    new_value: any,
    change_type: str,  # INSERT/UPDATE/DELETE
    reason: str = None,
    source: str = 'MANUAL'
) -> int:
    """Log change to fact_input_audit. Returns audit_id."""

def get_audit_history(
    table_name: str = None,
    record_id: str = None,
    since: datetime = None
) -> list[dict]:
    """Get audit history with optional filters."""

def audit_logged(func):
    """Decorator to auto-log function calls that modify data."""
```

**Tests:** 6 tests
- test_log_audit_insert
- test_log_audit_update
- test_log_audit_delete
- test_get_audit_history_filtered
- test_audit_decorator
- test_audit_preserves_old_value

---

### TASK-184: Integrate audit logging into PO and sales modules
**File:** Multiple files (updates)

**What to update:**
- `core/po/lifecycle.py`: Wrap `update_po_field()`, `confirm_po_arrival()` with audit logging
- `core/ingest/sales_ingest.py`: Log return updates
- `core/db/ledger.py`: Log manual adjustments

**Tests:** 4 tests
- test_po_update_logged
- test_arrival_logged
- test_return_update_logged
- test_adjustment_logged

---

## Milestone 5: Integration & CLI

### TASK-185: Create stock adjustment CLI
**File:** `scripts/po_cli.py` (extend)

**Commands:**

```bash
# Manual stock adjustment
python scripts/po_cli.py adjust LINE52_BLACK_XL --qty -5 --reason "Physical count discrepancy"
python scripts/po_cli.py adjust LINE52_BLACK_L --qty +10 --reason "Found in warehouse"

# View stock for SKU
python scripts/po_cli.py stock LINE52_BLACK
python scripts/po_cli.py stock --all --reorder-only
```

**Tests:** 3 tests
- test_adjust_positive
- test_adjust_negative
- test_adjust_requires_reason

---

### TASK-186: Create daily_pipeline_v2.py
**File:** `scripts/daily_pipeline_v2.py`

**Pipeline Steps:**

```python
def run_daily_pipeline(
    dry_run: bool = False,
    skip_sales: bool = False,
    skip_po_check: bool = False,
    no_alerts: bool = False
) -> dict:
    """
    Full daily pipeline:
    
    1. Ingest new sales from SALES_KSP_CRM_V3.xlsx
       → sales_fact_v2 + stock_ledger SALE events
    
    2. Check for PO arrivals (based on ast_arrival_nom = today)
       → Prompt for confirmation if any expected
    
    3. Rebuild stock_snapshot from ledger
       → fact_inventory_snapshot_size updated
    
    4. Recalculate PO ETAs
       → po_header.alm_arrival_nom, ast_arrival_nom updated
    
    5. Run SKU metrics calculation
       → fact_sku_metrics updated
    
    6. Generate PO suggestions (Phase 9.6)
       → exports/YYYY-MM-DD/po_suggestions.csv
    
    7. Send Telegram alerts for REORDER status
    
    Returns: summary dict
    """
```

**CLI:**
```bash
python scripts/daily_pipeline_v2.py
python scripts/daily_pipeline_v2.py --dry-run
python scripts/daily_pipeline_v2.py --skip-sales --skip-po-check
python scripts/daily_pipeline_v2.py --no-alerts
```

**Tests:** 4 tests
- test_pipeline_full_run
- test_pipeline_dry_run
- test_pipeline_sales_creates_ledger_events
- test_pipeline_updates_snapshot

---

## Milestone 6: Migration & Validation

### TASK-187: Create validation script
**File:** `scripts/validate_ledger.py`

**Checks:**
1. Sum of INITIAL events = bootstrap Excel totals
2. Stock snapshot balance = sum of ledger events
3. All po_line have valid sku_id in dim_sku_size
4. All sales_fact_v2 have valid sku_id
5. No orphaned po_line (po_id exists in po_header)
6. Audit log has entries for all PO updates
7. Inbound in snapshot matches pending po_line totals

**CLI:**
```bash
python scripts/validate_ledger.py --verbose
python scripts/validate_ledger.py --check balance
python scripts/validate_ledger.py --check po
```

**Tests:** 7 validation checks (not unit tests)

---

### TASK-188: Import existing PO data
**File:** `scripts/import_po_from_excel.py`

**What to build:**
- Read PO data from `~/Docs/Autonomous_business/excel/Inbound_template_09.12.2025.xlsx`
- Parse PO_headers sheet → po_header table
- Parse PO_book sheet → po_line table
- Parse Inventory_move sheet (since 2025-11-08) → stock_ledger INBOUND events
- Handle already-received POs correctly

**CLI:**
```bash
python scripts/import_po_from_excel.py excel/Inbound_template_09.12.2025.xlsx --dry-run
python scripts/import_po_from_excel.py excel/Inbound_template_09.12.2025.xlsx
```

**Tests:** 4 tests
- test_import_po_headers
- test_import_po_lines
- test_import_inventory_moves
- test_import_idempotent

---

### TASK-189: Integration with Phase 9.6
**File:** `core/db/queries.py` (update)

**What to update:**
- `get_size_current_stock()`: Read from rebuilt snapshot (ledger-based)
- `get_size_inbound()`: Read from po_line WHERE status IN ('PENDING', 'PARTIAL')
- Ensure Phase 9.6 PO generator uses new data sources

**Tests:** 3 tests
- test_current_stock_from_ledger
- test_inbound_from_po_line
- test_phase96_uses_new_sources

---

### TASK-190: Update ARCHITECTURE.md
**File:** `docs/ARCHITECTURE.md`

**What to add:**
- Stock Ledger section
- PO Lifecycle section
- Event types explanation
- Data flow diagram

---

## Test Summary

| Milestone | Tasks | Tests |
|-----------|-------|-------|
| 1: Stock Ledger | 4 | 17 |
| 2: Sales Integration | 3 | 18 |
| 3: PO Tracking | 4 | 35 |
| 4: Audit Trail | 2 | 10 |
| 5: Integration | 2 | 7 |
| 6: Migration | 4 | 14 |
| **TOTAL** | **19** | **101** |

---

## Execution Order

Execute tasks in order: TASK-172 through TASK-190.

**Critical Path:**
1. TASK-172 (schema) — must be first
2. TASK-173 (ledger module) — foundation
3. TASK-174 (bootstrap) — initial data
4. TASK-176-177 (sales) — daily operations
5. TASK-179-182 (PO) — can parallel with sales after ledger done
6. TASK-186 (pipeline) — integration
7. TASK-187-189 (validation) — final checks

---

## Success Criteria

Phase 10 is complete when:

1. ✅ All 101 tests passing
2. ✅ Bootstrap creates INITIAL events matching Excel
3. ✅ Sales ingestion creates SALE events and decrements stock
4. ✅ PO arrival creates INBOUND events and increments stock
5. ✅ Snapshot rebuilt from ledger matches expected balances
6. ✅ All human inputs logged to fact_input_audit
7. ✅ Phase 9.6 PO generator works with new data sources
8. ✅ Daily pipeline v2 runs end-to-end

---

## Notes for Opus

1. **DO NOT modify** files in `~/Docs/kaspi_etl/` — that's the fallback system
2. **Sales dedup key** is `(order_id, sku_id, store_code, kaspi_offer_name)` — this is critical
3. **Archive fields** (`archive_alm_arrival`, `archive_ast_arrival`) are immutable once set
4. **Lead time L=21** is from `ship_date_cargo` to `ast_arrival_date`
5. **FX rates** are entered manually: CNY/KZT after supplier payment, USD/KZT at cargo arrival
6. **Cargo rate** is 2.66 USD/kg for clothes
7. Commit after each task with message: `Phase 10: TASK-XXX - description`
