#!/usr/bin/env python3
"""
Migration 013: Stock Ledger & PO Tracking System (Phase 10).

Creates:
- stock_ledger: Event-sourced stock tracking (INITIAL/SALE/INBOUND/ADJUSTMENT/RETURN/WRITE_OFF)
- po_header: Purchase order lifecycle with dates, costs, FX rates
- po_line: Size-level PO items with costs
- sales_fact_v2: Enhanced sales with return tracking
- fact_input_audit: Comprehensive audit logging for all human inputs

TASK-172: Create schema migration for stock ledger tables

Critical Constraints:
- Sales dedup key: (order_id, sku_id, store_code, kaspi_offer_name)
- Archive fields (archive_alm_arrival, archive_ast_arrival) are IMMUTABLE once set
- Lead time L=21 days (ship_date_cargo → ast_arrival_date)
- FX rates entered manually: CNY/KZT after supplier payment, USD/KZT at cargo arrival
- Cargo rate = 2.66 USD/kg for clothes
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "db" / "app.db"


def migrate():
    """Run migration 013."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=" * 70)
    print("Migration 013: Stock Ledger & PO Tracking System (Phase 10)")
    print("=" * 70)

    # =========================================================================
    # 1. STOCK LEDGER (Event-Sourced Stock Tracking)
    # =========================================================================
    print("\n[1/5] Creating stock_ledger table...")

    cursor.execute("""
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
        )
    """)
    print("  - stock_ledger table created")

    # Stock ledger indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ledger_sku ON stock_ledger(sku_id, event_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ledger_sku_key ON stock_ledger(sku_key, event_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ledger_date ON stock_ledger(event_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ledger_type ON stock_ledger(event_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ledger_ref ON stock_ledger(reference_id, reference_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ledger_store ON stock_ledger(store_code)")
    print("  - Indexes created: sku, sku_key, date, type, ref, store")

    # =========================================================================
    # 2. PO HEADER (Purchase Order Lifecycle)
    # =========================================================================
    print("\n[2/5] Creating po_header table...")

    cursor.execute("""
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
            archive_alm_arrival DATE,                    -- Auto-lock: first real ALM arrival (IMMUTABLE)
            archive_ast_arrival DATE,                    -- Auto-lock: first real AST arrival (IMMUTABLE)
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
        )
    """)
    print("  - po_header table created")

    # PO header indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_po_header_status ON po_header(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_po_header_supplier ON po_header(supplier_code)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_po_header_ast_nom ON po_header(ast_arrival_nom)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_po_header_created ON po_header(created_at)")
    print("  - Indexes created: status, supplier, ast_arrival_nom, created_at")

    # PO header update trigger
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_po_header_updated
        AFTER UPDATE ON po_header
        FOR EACH ROW
        BEGIN
            UPDATE po_header
            SET updated_at = CURRENT_TIMESTAMP
            WHERE po_id = NEW.po_id;
        END
    """)
    print("  - Update trigger created")

    # =========================================================================
    # 3. PO LINE (Size-Level PO Items)
    # =========================================================================
    print("\n[3/5] Creating po_line table...")

    cursor.execute("""
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
            unit_weight_kg REAL,                         -- Weight per unit
            freight_share_kzt REAL,                      -- Auto: proportional cargo cost
            landed_cost_unit_kzt REAL,                   -- Auto: unit_cost_kzt + freight_share per unit

            -- Status
            status TEXT DEFAULT 'PENDING',               -- PENDING/PARTIAL/RECEIVED
            receive_date DATE,                           -- When fully received

            -- Audit
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (po_id) REFERENCES po_header(po_id)
        )
    """)
    print("  - po_line table created")

    # PO line indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_po_line_po ON po_line(po_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_po_line_sku ON po_line(sku_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_po_line_sku_key ON po_line(sku_key)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_po_line_status ON po_line(status)")
    print("  - Indexes created: po_id, sku_id, sku_key, status")

    # PO line update trigger
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_po_line_updated
        AFTER UPDATE ON po_line
        FOR EACH ROW
        BEGIN
            UPDATE po_line
            SET updated_at = CURRENT_TIMESTAMP
            WHERE po_line_id = NEW.po_line_id;
        END
    """)
    print("  - Update trigger created")

    # =========================================================================
    # 4. SALES FACT V2 (Enhanced with return tracking)
    # =========================================================================
    print("\n[4/5] Creating sales_fact_v2 table...")

    cursor.execute("""
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
        )
    """)
    print("  - sales_fact_v2 table created")

    # Sales fact v2 indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_v2_order ON sales_fact_v2(order_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_v2_date ON sales_fact_v2(order_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_v2_sku ON sales_fact_v2(sku_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_v2_sku_key ON sales_fact_v2(sku_key)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_v2_store ON sales_fact_v2(store_code)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_v2_status ON sales_fact_v2(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sales_v2_return ON sales_fact_v2(return_flag)")
    print("  - Indexes created: order, date, sku, sku_key, store, status, return_flag")

    # =========================================================================
    # 5. FACT INPUT AUDIT (All human inputs tracked)
    # =========================================================================
    print("\n[5/5] Creating fact_input_audit table...")

    cursor.execute("""
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
        )
    """)
    print("  - fact_input_audit table created")

    # Audit indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_table ON fact_input_audit(table_name, record_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_time ON fact_input_audit(changed_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_type ON fact_input_audit(change_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_source ON fact_input_audit(source)")
    print("  - Indexes created: table+record, time, type, source")

    # =========================================================================
    # Commit and verify
    # =========================================================================
    conn.commit()

    print("\n" + "=" * 70)
    print("VERIFICATION")
    print("=" * 70)

    # Verify all tables
    tables_created = [
        "stock_ledger",
        "po_header",
        "po_line",
        "sales_fact_v2",
        "fact_input_audit",
    ]

    for table_name in tables_created:
        cursor.execute(f"""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name = ?
        """, (table_name,))
        result = cursor.fetchone()
        if result:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = len(cursor.fetchall())
            print(f"  {table_name}: {columns} columns, {count} rows")
        else:
            print(f"  ERROR: {table_name} not created!")

    # Show stock_ledger event types info
    print("\n" + "=" * 70)
    print("STOCK LEDGER EVENT TYPES")
    print("=" * 70)
    print("  INITIAL    - Bootstrap/opening balance")
    print("  SALE       - Stock decrease from customer order (qty_change < 0)")
    print("  INBOUND    - Stock increase from PO arrival (qty_change > 0)")
    print("  RETURN     - Stock increase from customer return (qty_change > 0)")
    print("  ADJUSTMENT - Manual stock correction (+/-)")
    print("  WRITE_OFF  - Stock decrease from damage/loss (qty_change < 0)")

    # Show PO status flow
    print("\n" + "=" * 70)
    print("PO STATUS FLOW")
    print("=" * 70)
    print("  DRAFT → SENT → PREPARING → SHIPPED_SELLER → SHIPPED_CARGO")
    print("  → IN_TRANSIT → ARRIVED_ALM → ARRIVED_AST → RECEIVED → CLOSED")

    conn.close()

    print("\n" + "=" * 70)
    print("Migration 013 complete!")
    print("=" * 70)


if __name__ == "__main__":
    migrate()
