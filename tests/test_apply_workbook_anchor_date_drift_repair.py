from __future__ import annotations

import sqlite3
from pathlib import Path

import openpyxl
import pytest

from scripts.apply_workbook_anchor_date_drift_repair import (
    ENV_GATE,
    DateDriftRepairError,
    _sha256_file,
    run_repair,
)


def _write_workbook(path: Path, rows: list[tuple[str, str, float, float, str]]) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    ws.append(
        [
            "OrderID",
            "Date",
            "KASPI_OFFER_NAME",
            "Quantity",
            "Total_price",
            "Total_net_rev",
            "STORE_NAME",
        ]
    )
    for order_id, day, qty, net_rev, store in rows:
        ws.append([order_id, day, f"OFFER-{order_id}", qty, net_rev, net_rev, store])
    wb.save(path)


def _seed_sales_fact_v2(
    db_path: Path,
    rows: list[tuple[str, str, str, float, float]],
) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE sales_fact_v2 (
            sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            order_date TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT,
            kaspi_offer_name TEXT NOT NULL,
            store_code TEXT,
            quantity REAL NOT NULL,
            sell_price_kzt REAL,
            delivery_fee REAL,
            cogs REAL,
            net_rev REAL,
            profit REAL,
            status TEXT,
            return_flag INTEGER,
            return_date TEXT,
            ingested_at TEXT DEFAULT CURRENT_TIMESTAMP,
            source_file TEXT,
            api_updated_at TEXT,
            UNIQUE(order_id, sku_id, store_code, kaspi_offer_name)
        );
        """
    )
    for idx, (order_id, day, source_file, qty, net_rev) in enumerate(rows, start=1):
        conn.execute(
            """
            INSERT INTO sales_fact_v2 (
                order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
                store_code, quantity, sell_price_kzt, delivery_fee, cogs, net_rev,
                profit, status, return_flag, return_date, source_file, api_updated_at
            ) VALUES (
                ?, ?, 'SKU', ?, 'L', ?, 'ACMEWEAR', ?, ?, 0, 0, ?, 0,
                'DELIVERED', 0, NULL, ?, NULL
            )
            """,
            (order_id, day, f"SKU_{idx}", f"OFFER-{order_id}", qty, net_rev, net_rev, source_file),
        )
    conn.commit()
    conn.close()


def _date_drift_fixture(tmp_path: Path) -> tuple[Path, Path]:
    db = tmp_path / "app.db"
    workbook = tmp_path / "crm.xlsx"
    _seed_sales_fact_v2(
        db,
        [
            ("ORD-DRIFT", "2026-02-05", "KASPI_API_ENTRIES_REBUILD", 1.0, 100.0),
        ],
    )
    _write_workbook(
        workbook,
        [
            ("ORD-DRIFT", "2026-02-04", 1.0, 100.0, "ACMEWEAR"),
            ("ORD-ANCHOR", "2026-02-05", 1.0, 50.0, "ACMEWEAR"),
        ],
    )
    return db, workbook


def _repair_kwargs(db: Path, workbook: Path, output_dir: Path) -> dict[str, object]:
    return {
        "db_path": db,
        "workbook_path": workbook,
        "start": "2026-02-04",
        "end": "2026-02-05",
        "as_of": "2026-02-05",
        "expected_error_references": 1,
        "expected_failing_dates": 1,
        "expected_unresolved_error_references": 0,
        "expected_units_overage": 0.0,
        "expected_net_overage_kzt": 50.0,
        "output_dir": output_dir,
    }


def _sales_rows(db_path: Path) -> list[dict[str, object]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = [dict(row) for row in conn.execute("SELECT * FROM sales_fact_v2 ORDER BY sale_id")]
    conn.close()
    return rows


def test_dry_run_does_not_mutate_sales_fact_v2(tmp_path: Path) -> None:
    db, workbook = _date_drift_fixture(tmp_path)

    before = _sales_rows(db)
    report = run_repair(**_repair_kwargs(db, workbook, tmp_path / "dry_run"))
    after = _sales_rows(db)

    assert report["status"] == "DRY_RUN"
    assert report["selected_move_count"] == 1
    assert report["selected_sale_row_count"] == 1
    assert report["rows_updated"] == 0
    assert report["simulation_post"]["validator_report"]["ok"] is True
    assert report["simulation_post"]["classifier_report"]["error_references_total"] == 0
    assert before == after


def test_apply_requires_env_gate_and_backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db, workbook = _date_drift_fixture(tmp_path)

    with pytest.raises(DateDriftRepairError, match=ENV_GATE):
        run_repair(
            **_repair_kwargs(db, workbook, tmp_path / "apply_without_gate"),
            apply=True,
            backup_dir=tmp_path / "backups",
        )

    monkeypatch.setenv(ENV_GATE, "1")
    with pytest.raises(DateDriftRepairError, match="--backup-dir"):
        run_repair(**_repair_kwargs(db, workbook, tmp_path / "apply_without_backup"), apply=True)


def test_apply_enforces_pre_sha_and_updates_only_order_date(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, workbook = _date_drift_fixture(tmp_path)
    monkeypatch.setenv(ENV_GATE, "1")

    with pytest.raises(DateDriftRepairError, match="pre-SHA mismatch"):
        run_repair(
            **_repair_kwargs(db, workbook, tmp_path / "wrong_sha"),
            apply=True,
            backup_dir=tmp_path / "backups_wrong",
            expected_pre_sha256="0" * 64,
        )

    before = _sales_rows(db)[0]
    report = run_repair(
        **_repair_kwargs(db, workbook, tmp_path / "apply"),
        apply=True,
        backup_dir=tmp_path / "backups",
        expected_pre_sha256=_sha256_file(db),
    )
    after = _sales_rows(db)[0]

    assert report["status"] == "APPLIED"
    assert report["rows_updated"] == 1
    assert Path(report["gate"]["backup_path"]).exists()
    assert report["gate"]["backup_sha256"]
    assert report["post_apply"]["validator_report"]["ok"] is True
    assert report["post_apply"]["classifier_report"]["error_references_total"] == 0
    assert before["order_date"] == "2026-02-05"
    assert after["order_date"] == "2026-02-04"
    for key, value in before.items():
        if key == "order_date":
            continue
        assert after[key] == value


def test_unexpected_same_day_bucket_is_refused(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    workbook = tmp_path / "crm.xlsx"
    _seed_sales_fact_v2(
        db,
        [
            ("ORD-SAME", "2026-02-05", "KASPI_API_ENTRIES_REBUILD", 1.0, 100.0),
        ],
    )
    _write_workbook(
        workbook,
        [
            ("ORD-SAME", "2026-02-05", 1.0, 50.0, "ACMEWEAR"),
        ],
    )

    with pytest.raises(DateDriftRepairError, match="unexpected classifier buckets"):
        run_repair(**_repair_kwargs(db, workbook, tmp_path / "same_day_value_overage"))
