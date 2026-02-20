#!/usr/bin/env python3
"""
Apply manual size-share overrides to dim_anchor (DB source of truth).

Run:
    python3 scripts/migrate_014_anchor_overrides.py
"""

from datetime import datetime
from pathlib import Path
import sys
import sqlite3

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "db" / "app.db"

SKU_KEYS = [
    "CL_NEW-CLO_MEN_NIKE-SHIRT_BLACK",
    "CL_NEW-CLO_MEN_NIKE-SHIRT_GREY",
    "CL_NEW-CLO_MEN_NIKE-SHIRT_WHITE",
]

SHARES = {
    "S_share": 0.0417,
    "M_share": 0.2058,
    "L_share": 0.3173,
    "XL_share": 0.2501,
    "2XL_share": 0.1235,
    "3XL_share": 0.0617,
    "4XL_share": 0.0,
    "22_share": 0.0,
    "24_share": 0.0,
    "26_share": 0.0,
    "28_share": 0.0,
    "30_share": 0.0,
}


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"DB not found: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='dim_anchor'")
    if not cur.fetchone():
        raise SystemExit("dim_anchor table not found")

    cols = [row["name"] for row in cur.execute("PRAGMA table_info(dim_anchor)")]
    missing_cols = [c for c in SHARES if c not in cols]
    if missing_cols:
        raise SystemExit(f"Missing columns in dim_anchor: {missing_cols}")

    now = datetime.now().isoformat(timespec="seconds")

    for sku_key in SKU_KEYS:
        row = cur.execute("SELECT sku_key FROM dim_anchor WHERE sku_key = ?", (sku_key,)).fetchone()
        if row:
            sets = ", ".join(f"\"{k}\" = ?" for k in SHARES)
            params = list(SHARES.values()) + [now, sku_key]
            cur.execute(f"UPDATE dim_anchor SET {sets}, updated_at = ? WHERE sku_key = ?", params)
        else:
            values = {c: None for c in cols}
            values["sku_key"] = sku_key
            values["d_active"] = 0.0
            values["sigma"] = 0.0
            values["updated_at"] = now
            for k, v in SHARES.items():
                values[k] = v
            col_list = ", ".join(f"\"{c}\"" for c in cols)
            placeholders = ", ".join("?" for _ in cols)
            cur.execute(
                f"INSERT INTO dim_anchor ({col_list}) VALUES ({placeholders})",
                [values[c] for c in cols],
            )

    conn.commit()

    for sku_key in SKU_KEYS:
        row = cur.execute(
            "SELECT sku_key, S_share, M_share, L_share, XL_share, \"2XL_share\", \"3XL_share\" "
            "FROM dim_anchor WHERE sku_key = ?",
            (sku_key,),
        ).fetchone()
        print(dict(row))

    conn.close()


if __name__ == "__main__":
    main()
