"""
Bootstrap database with initial dimension data.
Seeds: dim_store, dim_params, dim_sku (from Excel or hardcoded).
Idempotent: safe to re-run.
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db import get_db, init_db  # noqa: E402


# ===========================
# SEED DATA
# ===========================

STORES = [
    ("UNIVERSAL", "kaspi", "KZ", 1),
    ("ACMEWEAR", "kaspi", "KZ", 1),
    ("11KZ", "kaspi", "KZ", 1),
    ("MELVIS", "kaspi", "KZ", 1),
    ("STOREB", "kaspi", "KZ", 1),
]

# Global params + Product_Type overrides
PARAMS = [
    # Global defaults
    ("R_days", None, 10, "Review period (days)"),
    ("L_days", None, 21, "Lead time (days) - global default"),
    ("B_days", None, 14, "Safety floor buffer (days)"),
    ("z_factor", None, 1.65, "Service level factor (~95%)"),
    ("TV_mix_floor", None, 0.23, "Size-mix volatility floor"),
    ("VAT_rate", None, 0.03, "VAT rate (3%)"),
    ("commission", None, 0.125, "Platform commission (Kaspi)"),
    ("CNY_KZT", None, 75, "CNY to KZT exchange rate"),
    ("USD_KZT", None, 520, "USD to KZT exchange rate"),
    ("cargo_rate_cl", None, 2.66, "Cargo rate USD/kg for CL"),

    # Product_Type overrides
    ("L_days_CL", "CL", 21, "Lead time for Clothing"),
    ("L_days_ELS", "ELS", 20, "Lead time for ELS"),
    ("L_days_WB", "WB", 32, "Lead time for Wildberries"),
    ("B_days_ELS", "ELS", 21, "Buffer for ELS"),
    ("commission_WB", "WB", 0.245, "WB commission"),
]

# Example SKUs (LINE52, LINE51)
SKUS = [
    ("CL_OC_MEN_LINE52_BLACK", "LINE52", "BLACK",
     "CL", 47, 0.95, "HOODIE", "MEN"),
    ("CL_OC_MEN_LINE51_WHITE", "LINE51", "WHITE",
     "CL", 60, 0.95, "HOODIE", "MEN"),
]

# Example sizes for LINE52
SIZES_LINE52 = ["S", "M", "L", "XL", "2XL", "3XL", "4XL"]


def seed_stores(conn):
    """Insert stores (idempotent)."""
    for store_code, channel, region, active in STORES:
        conn.execute("""
            INSERT OR IGNORE INTO dim_store
            (store_code, channel, region, active_flag)
            VALUES (?, ?, ?, ?)
        """, (store_code, channel, region, active))
    print(f"  ✓ Seeded {len(STORES)} stores")


def seed_params(conn):
    """Insert parameters (idempotent)."""
    for param_key, product_type, value, desc in PARAMS:
        conn.execute("""
            INSERT OR REPLACE INTO dim_params
            (param_key, product_type, param_value, description)
            VALUES (?, ?, ?, ?)
        """, (param_key, product_type, value, desc))
    print(f"  ✓ Seeded {len(PARAMS)} params")


def seed_skus(conn):
    """Insert SKUs (idempotent)."""
    for sku_key, model, color, ptype, cost, weight, cat, gender in SKUS:
        conn.execute("""
            INSERT OR IGNORE INTO dim_sku
            (sku_key, model, color, product_type, base_cost_cny,
             weight_kg, category, gender)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (sku_key, model, color, ptype, cost, weight, cat, gender))

    # Seed sizes for LINE52
    for i, size in enumerate(SIZES_LINE52, 1):
        sku_id = f"CL_OC_MEN_LINE52_BLACK_{size}"
        conn.execute("""
            INSERT OR IGNORE INTO dim_sku_size
            (sku_id, sku_key, my_size, size_order)
            VALUES (?, ?, ?, ?)
        """, (sku_id, "CL_OC_MEN_LINE52_BLACK", size, i))

    print(f"  ✓ Seeded {len(SKUS)} SKUs, {len(SIZES_LINE52)} sizes")


def main():
    """Bootstrap the database."""
    print("=== Bootstrap Database ===")

    # Initialize schema
    print("1. Initializing schema...")
    init_db()
    print("  ✓ Schema created")

    # Seed data
    print("2. Seeding dimensions...")
    with get_db() as conn:
        seed_stores(conn)
        seed_params(conn)
        seed_skus(conn)

    print("\n✅ Bootstrap complete!")
    print(f"   Database: {Path(__file__).parent.parent / 'db' / 'app.db'}")


if __name__ == "__main__":
    main()
