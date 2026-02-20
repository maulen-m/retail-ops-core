#!/usr/bin/env python3
"""
Migration 014: Extended Kaspi API order fields.

Adds missing columns to fact_orders_kaspi to store full API payload
attributes (status, delivery/payment details, planned/actual dates,
customer info, etc.).
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "db" / "app.db"


def migrate() -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=" * 60)
    print("Migration 014: Extended Kaspi API order fields")
    print("=" * 60)

    cursor.execute("PRAGMA table_info(fact_orders_kaspi)")
    existing = {row[1] for row in cursor.fetchall()}

    new_columns = [
        ("kaspi_status_detail", "TEXT"),
        ("planned_delivery_date", "TEXT"),
        ("courier_transmission_planning_date", "TEXT"),
        ("courier_transmission_date", "TEXT"),
        ("actual_shipment_date", "TEXT"),
        ("waybill_number", "TEXT"),
        ("delivery_mode", "TEXT"),
        ("payment_mode", "TEXT"),
        ("signature_required", "INTEGER"),
        ("credit_term", "INTEGER"),
        ("pre_order", "INTEGER"),
        ("approved_by_bank_date", "TEXT"),
        ("reservation_date", "TEXT"),
        ("delivery_cost", "REAL"),
        ("delivery_cost_for_seller", "REAL"),
        ("delivery_address", "TEXT"),
        ("is_imei_required", "INTEGER"),
        ("express", "INTEGER"),
        ("returned_to_warehouse", "INTEGER"),
        ("category", "TEXT"),
        ("customer_first_name", "TEXT"),
        ("customer_last_name", "TEXT"),
        ("customer_phone", "TEXT"),
    ]

    for col_name, col_type in new_columns:
        if col_name not in existing:
            cursor.execute(
                f"ALTER TABLE fact_orders_kaspi ADD COLUMN {col_name} {col_type}"
            )
            print(f"  - Added column: {col_name} ({col_type})")
        else:
            print(f"  - Column already exists: {col_name}")

    conn.commit()
    conn.close()

    print("\n" + "=" * 60)
    print("Migration 014 complete!")
    print("=" * 60)


if __name__ == "__main__":
    migrate()
