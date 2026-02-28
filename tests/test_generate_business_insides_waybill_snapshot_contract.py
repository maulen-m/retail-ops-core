from __future__ import annotations

import json
from datetime import date
import sqlite3
from pathlib import Path

from scripts.generate_business_insides import load_waybill_selection_snapshot


def _seed_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE fact_orders_kaspi (
                order_id TEXT,
                store_code TEXT,
                quantity REAL
            )
            """
        )
        conn.executemany(
            "INSERT INTO fact_orders_kaspi(order_id, store_code, quantity) VALUES (?, ?, ?)",
            [
                ("835000001", "UNIVERSAL", 1),
                ("835000002", "ACMEWEAR", 2),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def test_waybill_snapshot_uses_archive_fallback_on_cache_target_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    as_of = "2026-02-26"
    db_path = tmp_path / "app.db"
    _seed_db(db_path)

    cache_path = tmp_path / "_waybill_selection_orders.json"
    cache_path.write_text(
        json.dumps(
            {
                "target_date": "2026-02-28",
                "stores": {"UNIVERSAL": ["999999999"]},
            }
        ),
        encoding="utf-8",
    )

    archive_root = tmp_path / "archive"
    archive_dir = archive_root / f"input_{as_of}_183543"
    waybill_dir = archive_dir / "waybills"
    waybill_dir.mkdir(parents=True)
    (archive_dir / "archive_manifest.json").write_text(
        json.dumps(
            {
                "selected_count": 2,
                "copied_waybills": 2,
                "missing_waybills": 0,
            }
        ),
        encoding="utf-8",
    )
    (waybill_dir / "835000001.pdf").write_bytes(b"%PDF")
    (waybill_dir / "835000002.pdf").write_bytes(b"%PDF")
    monkeypatch.setenv("AB_WAYBILL_ARCHIVE_ROOT", str(archive_root))

    snapshot = load_waybill_selection_snapshot(
        db_path=db_path,
        as_of_date=date.fromisoformat(as_of),
        selection_cache_path=cache_path,
    )
    assert snapshot["status"] == "available_archive"
    assert snapshot["totals"]["orders"] == 2
    assert snapshot["stores"]["UNIVERSAL"]["orders"] == 1
    assert snapshot["stores"]["ACMEWEAR"]["orders"] == 1


def test_waybill_snapshot_mismatch_without_archive_is_fail_closed(tmp_path: Path, monkeypatch) -> None:
    as_of = "2026-02-26"
    db_path = tmp_path / "app.db"
    _seed_db(db_path)
    cache_path = tmp_path / "_waybill_selection_orders.json"
    cache_path.write_text(
        json.dumps(
            {
                "target_date": "2026-02-28",
                "stores": {"UNIVERSAL": ["835000001"]},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AB_WAYBILL_ARCHIVE_ROOT", str(tmp_path / "missing_archive_root"))

    snapshot = load_waybill_selection_snapshot(
        db_path=db_path,
        as_of_date=date.fromisoformat(as_of),
        selection_cache_path=cache_path,
    )
    assert snapshot["status"] == "as_of_mismatch"
    assert snapshot["totals"]["orders"] == 0
    assert snapshot["stores"] == {}
