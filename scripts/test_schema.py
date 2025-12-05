"""
Verify schema was created correctly.
Lists all tables and row counts.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db import get_db  # noqa: E402


def main():
    print("=== Schema Verification ===\n")

    with get_db() as conn:
        # List tables
        cursor = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)
        tables = [row['name'] for row in cursor]

        print(f"Tables found: {len(tables)}")
        print("-" * 40)

        for table in tables:
            query = f"SELECT COUNT(*) as cnt FROM {table}"
            count = conn.execute(query).fetchone()['cnt']
            print(f"  {table:30} {count:>5} rows")

        print("\n=== Sample Data ===\n")

        # Show stores
        print("dim_store:")
        for row in conn.execute("SELECT * FROM dim_store"):
            print(f"  {dict(row)}")

        # Show params (first 5)
        print("\ndim_params (first 5):")
        for row in conn.execute("SELECT * FROM dim_params LIMIT 5"):
            print(f"  {dict(row)}")

    print("\n✅ Verification complete")


if __name__ == "__main__":
    main()
