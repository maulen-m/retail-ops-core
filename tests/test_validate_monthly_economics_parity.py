from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3

import pandas as pd
import pytest

from scripts.validate_monthly_economics_parity import _build_parser, validate_monthly_economics_parity


def _seed_db(path: Path, *, jan_net_rev: float = 12000.0, jan_order_date: str = "2026-01-11") -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE sales_fact_v2 (
            order_id TEXT,
            order_date TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            kaspi_offer_name TEXT,
            store_code TEXT,
            quantity REAL,
            sell_price_kzt REAL,
            delivery_fee REAL,
            cogs REAL,
            net_rev REAL,
            profit REAL,
            status TEXT,
            return_flag INTEGER,
            return_date TEXT,
            source_file TEXT,
            api_updated_at TEXT
        );
        """
    )
    conn.executemany(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name, store_code, quantity,
         sell_price_kzt, delivery_fee, cogs, net_rev, profit, status, return_flag, return_date, source_file, api_updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "O-PROV",
                "2025-07-20",
                "SKU_A",
                "SKU_A_M",
                "M",
                "Offer A",
                "ACMEWEAR",
                2,
                0,
                0,
                500,
                1000,
                500,
                "DELIVERED",
                0,
                None,
                "seed",
                None,
            ),
            (
                "O-DEC",
                jan_order_date,
                "SKU_B",
                "SKU_B_L",
                "L",
                "Offer B",
                "UNIVERSAL",
                1,
                0,
                0,
                3000,
                jan_net_rev,
                jan_net_rev - 3000,
                "DELIVERED",
                0,
                None,
                "seed",
                None,
            ),
        ],
    )
    conn.commit()
    conn.close()


def _write_mapped(
    path: Path,
    *,
    dec_transaction_date: str = "2026-01-11",
    dec_mapped_sku_key: str = "SKU_B",
    dec_mapped_sku_id: str = "SKU_B_L",
    dec_mapped_size: str = "L",
) -> None:
    dec_month = dec_transaction_date[:7]
    pd.DataFrame(
        [
            {
                "line_id": "l1",
                "order_id": "O-PROV",
                "transaction_date": "2025-07-20",
                "transaction_month": "2025-07",
                "transaction_date_source": "creation_date_fallback",
                "store_code": "ACMEWEAR",
                "status_internal": "DELIVERED",
                "return_flag": "0",
                "quantity": "2",
                "gross_rev_kzt": "1000",
                "net_rev_kzt": "1000",
                "mapped_sku_key": "SKU_A",
                "mapped_sku_id": "SKU_A_M",
                "mapped_size": "M",
            },
            {
                "line_id": "l2",
                "order_id": "O-DEC",
                "transaction_date": dec_transaction_date,
                "transaction_month": dec_month,
                "transaction_date_source": "status_change_date",
                "store_code": "UNIVERSAL",
                "status_internal": "DELIVERED",
                "return_flag": "0",
                "quantity": "1",
                "gross_rev_kzt": "12000",
                "net_rev_kzt": "12000",
                "mapped_sku_key": dec_mapped_sku_key,
                "mapped_sku_id": dec_mapped_sku_id,
                "mapped_size": dec_mapped_size,
            },
        ]
    ).to_csv(path, index=False, encoding="utf-8")


def test_validate_monthly_economics_parity_passes_with_provisional_months(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    mapped = tmp_path / "mapped.csv"
    _seed_db(db, jan_net_rev=12000.0)
    _write_mapped(mapped)

    report = validate_monthly_economics_parity(
        since=date(2025, 6, 6),
        until=date(2026, 3, 2),
        db_path=db,
        mapped_csv=mapped,
        output_root=tmp_path / "out",
        strict=True,
        tolerance_pct=0.0,
        statusdate_cutover=date(2026, 1, 1),
    )

    assert report["status"] == "PASS"
    assert report["decision_grade_mismatch_count"] == 0
    assert report["provisional_pair_count"] >= 1
    assert Path(report["summary_json"]).exists()
    assert Path(report["report_md"]).exists()


def test_validate_monthly_economics_parity_fails_when_decision_grade_exceeds_archive(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    mapped = tmp_path / "mapped.csv"
    _seed_db(db, jan_net_rev=13000.0)
    _write_mapped(mapped)

    with pytest.raises(RuntimeError, match="decision-grade"):
        validate_monthly_economics_parity(
            since=date(2025, 6, 6),
            until=date(2026, 3, 2),
            db_path=db,
            mapped_csv=mapped,
            output_root=tmp_path / "out",
            strict=True,
            tolerance_pct=0.0,
            statusdate_cutover=date(2026, 1, 1),
        )


def test_validate_monthly_economics_parity_uses_status_month_projection(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    mapped = tmp_path / "mapped.csv"
    _seed_db(db, jan_net_rev=12000.0, jan_order_date="2026-03-31")
    _write_mapped(mapped, dec_transaction_date="2026-04-01")

    report = validate_monthly_economics_parity(
        since=date(2025, 6, 6),
        until=date(2026, 5, 2),
        db_path=db,
        mapped_csv=mapped,
        output_root=tmp_path / "out",
        strict=True,
        tolerance_pct=0.0,
        statusdate_cutover=date(2026, 1, 1),
    )

    assert report["status"] == "PASS"
    assert report["db_projection_surface"] == "monthly_sales_economics_statusdate_projection"

    monthly_db = pd.read_csv(report["monthly_db_csv"])
    shifted = monthly_db[
        (monthly_db["sale_month"] == "2026-04") & (monthly_db["store_code"] == "UNIVERSAL")
    ].iloc[0]
    assert shifted["db_units"] == 1
    assert not (
        (monthly_db["sale_month"] == "2026-03") & (monthly_db["store_code"] == "UNIVERSAL")
    ).any()

    projection = pd.read_csv(report["db_projection_csv"])
    row = projection[projection["order_id"] == "O-DEC"].iloc[0]
    assert row["sale_date"] == "2026-04-01"
    assert row["db_source_sale_dates"] == "2026-03-31"
    assert row["db_match_status"] == "MATCHED"


def test_validate_monthly_economics_parity_order_fallback_for_blank_archive_identity(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    mapped = tmp_path / "mapped.csv"
    _seed_db(db, jan_net_rev=12000.0, jan_order_date="2026-03-31")
    _write_mapped(
        mapped,
        dec_transaction_date="2026-04-01",
        dec_mapped_sku_key="NAN",
        dec_mapped_sku_id="NAN_NAN",
        dec_mapped_size="NAN",
    )

    report = validate_monthly_economics_parity(
        since=date(2025, 6, 6),
        until=date(2026, 5, 2),
        db_path=db,
        mapped_csv=mapped,
        output_root=tmp_path / "out",
        strict=True,
        tolerance_pct=0.0,
        statusdate_cutover=date(2026, 1, 1),
    )

    assert report["status"] == "PASS"
    assert report["db_projection_meta"]["order_store_identity_fallback_rows"] == 1

    projection = pd.read_csv(report["db_projection_csv"])
    row = projection[projection["order_id"] == "O-DEC"].iloc[0]
    assert row["match_key_kind"] == "order_store_missing_archive_identity"
    assert row["sale_date"] == "2026-04-01"
    assert row["db_source_sale_dates"] == "2026-03-31"


def test_validate_monthly_economics_parity_parser_default_cutover() -> None:
    parser = _build_parser()
    args = parser.parse_args(["--since", "2025-06-06", "--until", "2026-03-04"])
    assert args.statusdate_cutover == "2026-02-27"
