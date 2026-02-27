from __future__ import annotations

import csv
from pathlib import Path
import sqlite3

import pytest

from scripts.validate_sales_truth_external_reference import (
    validate_sales_truth_external_reference,
)


def _init_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE sales_fact_v2 (
            order_id TEXT,
            order_date TEXT,
            store_code TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            quantity REAL,
            net_rev REAL,
            cogs REAL,
            profit REAL,
            status TEXT,
            return_flag INTEGER
        );
        """
    )
    conn.executemany(
        """
        INSERT INTO sales_fact_v2 (
            order_id, order_date, store_code, sku_key, sku_id, my_size,
            quantity, net_rev, cogs, profit, status, return_flag
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("ORD-1", "2026-02-25", "ACMEWEAR", "SKU_A", "SKU_A", "L", 1, 1000, 0, 0, "DELIVERED", 0),
            ("ORD-2", "2026-02-25", "ACMEWEAR", "SKU_B", "SKU_B", "XL", 2, 4000, 0, 0, "DELIVERED", 0),
            ("ORD-3", "2026-02-25", "UNIVERSAL", "SKU_C", "SKU_C", "M", 1, 2000, 0, 0, "DELIVERED", 0),
        ],
    )
    conn.commit()
    conn.close()


def _write_reference_dir(reference_dir: Path, *, acmewear_units: float = 3.0, acmewear_rev: float = 5000.0, acmewear_orders: int = 2, acmewear_order_ids: list[str] | None = None) -> None:
    reference_dir.mkdir(parents=True, exist_ok=True)
    lines_path = reference_dir / "kaspi_etl_reference_delivered_lines_2026-01-01_to_2026-02-27.csv"
    by_store_path = reference_dir / "kaspi_etl_reference_delivered_daily_by_store_2026-01-01_to_2026-02-27.csv"
    total_path = reference_dir / "kaspi_etl_reference_delivered_daily_total_2026-01-01_to_2026-02-27.csv"
    order_ids = acmewear_order_ids or ["ORD-1", "ORD-2"]
    with lines_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "sale_date",
                "store_code",
                "order_id",
                "quantity",
                "gross_rev_kzt",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "sale_date": "2026-02-25",
                "store_code": "ACMEWEAR",
                "order_id": order_ids[0],
                "quantity": "1",
                "gross_rev_kzt": "1000",
            }
        )
        writer.writerow(
            {
                "sale_date": "2026-02-25",
                "store_code": "ACMEWEAR",
                "order_id": order_ids[1] if len(order_ids) > 1 else order_ids[0],
                "quantity": "2",
                "gross_rev_kzt": "4000",
            }
        )
        writer.writerow(
            {
                "sale_date": "2026-02-25",
                "store_code": "UNIVERSAL",
                "order_id": "ORD-3",
                "quantity": "1",
                "gross_rev_kzt": "2000",
            }
        )
    with by_store_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "sale_date",
                "store_code",
                "units_delivered",
                "gross_rev_kzt",
                "orders_delivered",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "sale_date": "2026-02-25",
                "store_code": "ACMEWEAR",
                "units_delivered": str(acmewear_units),
                "gross_rev_kzt": str(acmewear_rev),
                "orders_delivered": str(acmewear_orders),
            }
        )
        writer.writerow(
            {
                "sale_date": "2026-02-25",
                "store_code": "UNIVERSAL",
                "units_delivered": "1",
                "gross_rev_kzt": "2000",
                "orders_delivered": "1",
            }
        )
    with total_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "sale_date",
                "units_delivered",
                "gross_rev_kzt",
                "orders_delivered",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "sale_date": "2026-02-25",
                "units_delivered": str(float(acmewear_units) + 1.0),
                "gross_rev_kzt": str(float(acmewear_rev) + 2000.0),
                "orders_delivered": str(int(acmewear_orders) + 1),
            }
        )


def test_validate_sales_truth_external_reference_passes(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    ref_dir = tmp_path / "ref"
    _write_reference_dir(ref_dir)

    report = validate_sales_truth_external_reference(
        project_root=tmp_path,
        db_path=db_path,
        as_of="2026-02-26",
        output_root=tmp_path / "exports" / "daily",
        archive_dir=None,
        reference_dir=ref_dir,
        include_as_of_day=False,
        strict=True,
        strict_if_configured=False,
    )
    assert report["status"] == "PASS"
    assert report["ok"] is True


def test_validate_sales_truth_external_reference_fails_on_aggregate_mismatch(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    ref_dir = tmp_path / "ref"
    _write_reference_dir(ref_dir, acmewear_units=4.0, acmewear_rev=5000.0, acmewear_orders=2)

    with pytest.raises(RuntimeError, match="external reference parity failed"):
        validate_sales_truth_external_reference(
            project_root=tmp_path,
            db_path=db_path,
            as_of="2026-02-26",
            output_root=tmp_path / "exports" / "daily",
            archive_dir=None,
            reference_dir=ref_dir,
            include_as_of_day=False,
            strict=True,
            strict_if_configured=False,
        )


def test_validate_sales_truth_external_reference_fails_on_order_set_mismatch(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    ref_dir = tmp_path / "ref"
    _write_reference_dir(ref_dir, acmewear_order_ids=["ORD-1", "ORD-X"])

    with pytest.raises(RuntimeError, match="external reference parity failed"):
        validate_sales_truth_external_reference(
            project_root=tmp_path,
            db_path=db_path,
            as_of="2026-02-26",
            output_root=tmp_path / "exports" / "daily",
            archive_dir=None,
            reference_dir=ref_dir,
            include_as_of_day=False,
            strict=True,
            strict_if_configured=False,
        )


def test_validate_sales_truth_external_reference_skips_when_not_configured(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    report = validate_sales_truth_external_reference(
        project_root=tmp_path,
        db_path=db_path,
        as_of="2026-02-26",
        output_root=tmp_path / "exports" / "daily",
        archive_dir=None,
        reference_dir=None,
        include_as_of_day=False,
        strict=False,
        strict_if_configured=True,
    )
    assert report["status"] == "SKIP"
    assert report["ok"] is True

