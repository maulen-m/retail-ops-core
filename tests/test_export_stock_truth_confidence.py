from __future__ import annotations

import hashlib
import sqlite3
from datetime import date
from pathlib import Path

from scripts.export_stock_truth_confidence import export_stock_truth_confidence


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _create_schema(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE dim_sku (
                sku_key TEXT PRIMARY KEY,
                model TEXT NOT NULL,
                color TEXT,
                product_type TEXT NOT NULL,
                base_cost_cny REAL NOT NULL,
                weight_kg REAL NOT NULL,
                category TEXT,
                gender TEXT,
                active_flag INTEGER DEFAULT 1
            );
            CREATE TABLE dim_sku_size (
                sku_id TEXT PRIMARY KEY,
                sku_key TEXT NOT NULL,
                my_size TEXT NOT NULL,
                barcode TEXT,
                size_order INTEGER,
                active_flag INTEGER DEFAULT 1
            );
            CREATE TABLE fact_inventory_snapshot_size (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_date TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                sku_key TEXT NOT NULL,
                my_size TEXT NOT NULL,
                current_stock INTEGER NOT NULL DEFAULT 0,
                inbound_stock INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(snapshot_date, sku_id)
            );
            CREATE TABLE stock_ledger (
                ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date TEXT NOT NULL,
                event_type TEXT NOT NULL,
                sku_key TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                my_size TEXT NOT NULL,
                store_code TEXT DEFAULT 'UNIVERSAL',
                qty_change INTEGER NOT NULL,
                reference_id TEXT,
                reference_type TEXT,
                notes TEXT,
                input_source TEXT DEFAULT 'SYSTEM',
                created_by TEXT DEFAULT 'system',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                idempotency_key TEXT
            );
            CREATE TABLE exception_queue (
                exception_id TEXT PRIMARY KEY,
                domain TEXT NOT NULL,
                severity TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'OPEN',
                reason TEXT NOT NULL,
                evidence_json TEXT NOT NULL DEFAULT '{}'
            );
            """
        )


def _seed(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO dim_sku (
                sku_key, model, color, product_type, base_cost_cny,
                weight_kg, category, gender, active_flag
            )
            VALUES (?, ?, ?, 'CL', 1, 1, 'TEST', 'MEN', ?)
            """,
            [
                ("SKU_A", "A", "BLACK", 1),
                ("SKU_B", "B", "WHITE", 1),
                ("SKU_C", "C", "RED", 1),
                ("SKU_INACTIVE", "X", "GRAY", 0),
            ],
        )
        conn.executemany(
            """
            INSERT INTO dim_sku_size (sku_id, sku_key, my_size, barcode, size_order, active_flag)
            VALUES (?, ?, ?, '', ?, ?)
            """,
            [
                ("SKU_A_M", "SKU_A", "M", 1, 1),
                ("SKU_B_L", "SKU_B", "L", 2, 1),
                ("SKU_C_S", "SKU_C", "S", 3, 1),
                ("SKU_INACTIVE_M", "SKU_INACTIVE", "M", 4, 1),
            ],
        )
        conn.executemany(
            """
            INSERT INTO fact_inventory_snapshot_size (
                snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock
            )
            VALUES ('2026-06-16', ?, ?, ?, ?, 0)
            """,
            [
                ("SKU_A_M", "SKU_A", "M", 5),
                ("SKU_B_L", "SKU_B", "L", 7),
            ],
        )
        conn.executemany(
            """
            INSERT INTO stock_ledger (
                event_date, event_type, sku_key, sku_id, my_size, qty_change,
                reference_id, reference_type, notes, input_source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("2026-06-16", "INITIAL", "SKU_A", "SKU_A_M", "M", 5, "init", "TEST", "", "SYSTEM"),
                (
                    "2026-06-16",
                    "ADJUSTMENT",
                    "SKU_A",
                    "SKU_A_M",
                    "M",
                    0,
                    "owner_count",
                    "TEST",
                    "",
                    "OWNER_APPROVED_TEMP_OCR_OVERRIDE",
                ),
                ("2026-06-16", "INITIAL", "SKU_B", "SKU_B_L", "L", 7, "init", "TEST", "", "SYSTEM"),
                (
                    "2026-06-16",
                    "ADJUSTMENT",
                    "SKU_B",
                    "SKU_B_L",
                    "L",
                    -2,
                    "NEGATIVE_CLAMP_TEST",
                    "ADJUSTMENT",
                    "NEGATIVE_CLAMP_TEST",
                    "SYSTEM",
                ),
            ],
        )
        conn.execute(
            """
            INSERT INTO exception_queue (
                exception_id, domain, severity, status, reason, evidence_json
            )
            VALUES ('EX-1', 'stock', 'HIGH', 'OPEN', 'SKU_B_L stock quarantine', '{"sku_id":"SKU_B_L"}')
            """
        )


def test_export_scores_all_active_rows_and_writes_latest_files(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _create_schema(db_path)
    _seed(db_path)

    before = _sha256(db_path)
    summary = export_stock_truth_confidence(
        db_path=db_path,
        as_of=date(2026, 6, 17),
        output_root=tmp_path / "out",
        current_root=tmp_path / "current",
        include_default_manifests=False,
    )
    after = _sha256(db_path)

    assert before == after
    assert summary["active_sku_size_rows"] == 3
    assert summary["score_rows"] == 3
    assert summary["missing_score_rows"] == 0
    assert summary["snapshot_missing_rows"] == 1
    assert Path(summary["output_files"]["score_csv"]).exists()
    assert Path(summary["output_files"]["spot_check_csv"]).exists()
    assert (tmp_path / "current" / "stock_truth_confidence_latest.csv").exists()
    assert (tmp_path / "current" / "summary_latest.json").exists()


def test_risky_rows_are_scored_and_gated_hold(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _create_schema(db_path)
    _seed(db_path)

    summary = export_stock_truth_confidence(
        db_path=db_path,
        as_of=date(2026, 6, 17),
        output_root=tmp_path / "out",
        current_root=None,
        include_default_manifests=False,
    )

    rows = {
        row["sku_id"]: row
        for row in __import__("json").loads(Path(summary["output_files"]["score_json"]).read_text(encoding="utf-8"))[
            "rows"
        ]
    }

    assert rows["SKU_A_M"]["confidence_band"] == "GREEN"
    assert rows["SKU_A_M"]["price_upload_gate"] == "ALLOW"
    assert rows["SKU_B_L"]["confidence_band"] == "RED"
    assert rows["SKU_B_L"]["price_upload_gate"] == "HOLD"
    assert "open_exception" in rows["SKU_B_L"]["notes"]
    assert "negative_clamp_history" in rows["SKU_B_L"]["notes"]
    assert rows["SKU_C_S"]["snapshot_present"] == "false"
    assert rows["SKU_C_S"]["ads_gate"] == "HOLD"
