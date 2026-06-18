from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from scripts.report_exception_exposure_metric import build_exception_exposure_metric


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE exception_queue (
                exception_id TEXT PRIMARY KEY,
                run_id TEXT,
                domain TEXT NOT NULL,
                severity TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'OPEN',
                reason TEXT NOT NULL,
                evidence_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT,
                resolved_at TEXT,
                owner TEXT NOT NULL DEFAULT '',
                recommended_action TEXT NOT NULL DEFAULT '',
                evidence_paths_json TEXT NOT NULL DEFAULT '[]',
                due_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE dim_sku (
                sku_key TEXT PRIMARY KEY,
                cogs_kzt REAL
            );
            CREATE TABLE dim_sku_size (
                sku_id TEXT PRIMARY KEY,
                sku_key TEXT NOT NULL,
                my_size TEXT
            );
            """
        )
        conn.execute("INSERT INTO dim_sku VALUES ('SKU_A', 1000.0)")
        conn.execute("INSERT INTO dim_sku VALUES ('SKU_B', 250.0)")
        conn.execute("INSERT INTO dim_sku_size VALUES ('SKU_B_M', 'SKU_B', 'M')")
        rows = [
            (
                "E1",
                "STOCK",
                "HIGH",
                "OPEN",
                "OWNER_OOS_ACTIVE_ZERO: active zero",
                json.dumps({"sku_key": "SKU_A", "physical_anchor_qty": 3}),
                "2026-06-10 12:00:00",
                "business_owner",
            ),
            (
                "E2",
                "CASH",
                "MEDIUM",
                "PENDING",
                "DIRECT_LOSS: direct",
                json.dumps({"exposure_kzt": 5000, "quantity": 2}),
                "2026-06-12",
                "ops",
            ),
            (
                "E3",
                "STOCK",
                "HIGH",
                "OPEN",
                "SIZELESS: missing qty",
                json.dumps({"sku_key": "SKU_A"}),
                "2026-06-14",
                "business_owner",
            ),
            (
                "E4",
                "STOCK",
                "LOW",
                "CLOSED",
                "CLOSED: ignore",
                json.dumps({"sku_key": "SKU_A", "physical_anchor_qty": 99}),
                "2026-06-01",
                "ops",
            ),
            (
                "E5",
                "STOCK",
                "LOW",
                "BLOCKED",
                "SIZE_MAP: sku-id",
                json.dumps({"sku_id": "SKU_B_M", "raw_current_stock": -4}),
                "2026-06-13",
                "ops",
            ),
        ]
        conn.executemany(
            """
            INSERT INTO exception_queue (
                exception_id, domain, severity, status, reason, evidence_json,
                created_at, owner
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def test_exception_exposure_metric_values_quantities_and_direct_kzt(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)

    result = build_exception_exposure_metric(
        db_path=db_path,
        as_of=__import__("datetime").date(2026, 6, 17),
        output_dir=tmp_path / "out",
    )

    payload = result["payload"]
    assert payload["status"] == "GREEN"
    assert payload["open_exception_count"] == 4
    assert payload["valued_exception_count"] == 3
    assert payload["unvalued_exception_count"] == 1
    assert payload["total_exposure_kzt"] == 9000.0
    assert payload["total_exposure_age_kzt_days"] == 50000.0
    assert payload["total_quantity_at_risk"] == 9.0
    assert payload["total_quantity_age_days"] == 47.0

    rows = {row["exception_id"]: row for row in payload["exceptions"]}
    assert rows["E1"]["exposure_kzt"] == 3000.0
    assert rows["E1"]["valuation_status"] == "VALUED_BY_COGS"
    assert rows["E2"]["exposure_kzt"] == 5000.0
    assert rows["E2"]["valuation_status"] == "VALUED_DIRECT"
    assert rows["E3"]["valuation_status"] == "UNVALUED_MISSING_QUANTITY"
    assert rows["E5"]["exposure_kzt"] == 1000.0
    assert rows["E5"]["quantity_at_risk"] == 4.0

    json_path = Path(result["json_path"])
    md_path = Path(result["md_path"])
    assert json_path.exists()
    assert md_path.exists()
    assert "exception_exposure: open=4" in md_path.read_text(encoding="utf-8")


def test_exception_exposure_metric_fails_when_exception_queue_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    sqlite3.connect(db_path).close()

    try:
        build_exception_exposure_metric(
            db_path=db_path,
            as_of=__import__("datetime").date(2026, 6, 17),
            output_dir=tmp_path / "out",
        )
    except RuntimeError as exc:
        assert "missing required table: exception_queue" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
