from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from scripts.validate_no_missing_identity_in_delivered_window import (
    IdentityCoverageError,
    validate_no_missing_identity_in_delivered_window,
)


def _seed_sales(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE sales_fact_v2 (
            order_id TEXT,
            order_date TEXT,
            store_code TEXT,
            sku_key TEXT,
            my_size TEXT,
            status TEXT,
            return_flag INTEGER
        );
        """
    )
    conn.commit()
    conn.close()


def test_identity_validator_passes_when_no_missing(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _seed_sales(db)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO sales_fact_v2 VALUES ('ORD-1', '2026-02-26', 'ACMEWEAR', 'SKU_A', 'L', 'DELIVERED', 0)"
    )
    conn.commit()
    conn.close()

    report = validate_no_missing_identity_in_delivered_window(
        db_path=db,
        as_of="2026-02-26",
        lookback_days=7,
        output_root=tmp_path / "out",
        strict=True,
    )
    assert report["status"] == "PASS"


def test_identity_validator_fails_closed_on_missing_size(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _seed_sales(db)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO sales_fact_v2 VALUES ('ORD-2', '2026-02-26', 'ACMEWEAR', 'SKU_A', '', 'DELIVERED', 0)"
    )
    conn.commit()
    conn.close()

    with pytest.raises(IdentityCoverageError, match="regression"):
        validate_no_missing_identity_in_delivered_window(
            db_path=db,
            as_of="2026-02-26",
            lookback_days=7,
            output_root=tmp_path / "out",
            strict=True,
        )
