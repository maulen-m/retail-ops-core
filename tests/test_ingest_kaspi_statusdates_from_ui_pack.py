from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from scripts.ingest_kaspi_statusdates_from_ui_pack import ingest_kaspi_statusdates_from_ui_pack


def _seed_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE fact_orders_kaspi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            store_code TEXT,
            status_updated_at TEXT
        );
        INSERT INTO fact_orders_kaspi (order_id, store_code, status_updated_at)
        VALUES ('1001', 'UNIVERSAL', ''),
               ('1002', 'UNIVERSAL', '2026-02-20');
        """
    )
    conn.commit()
    conn.close()


def _seed_ui_pack(root: Path) -> Path:
    pack = root / "ui_pack"
    store = pack / "store_UNIVERSAL"
    store.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "№ заказа": "1001",
                "Дата изменения статуса": "26.02.2026",
                "Склад передачи КД": "30000001_PP1",
            }
        ]
    ).to_csv(store / "ArchiveOrders_UNIVERSAL.csv", index=False, encoding="utf-8")
    return pack


def _fetch_status(path: Path, order_id: str) -> str:
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute(
            "SELECT COALESCE(status_updated_at, '') FROM fact_orders_kaspi WHERE order_id = ?",
            (order_id,),
        ).fetchone()
        return str(row[0] or "")
    finally:
        conn.close()


def test_dry_run_plans_updates_without_writing(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _seed_db(db)
    pack = _seed_ui_pack(tmp_path)

    report = ingest_kaspi_statusdates_from_ui_pack(
        db_path=db,
        ui_pack_root=pack,
        apply=False,
        strict=True,
        backup_root=tmp_path / "backups",
        apply_manifest_root=tmp_path / "manifests",
    )
    assert report["updates_planned"] == 1
    assert _fetch_status(db, "1001") == ""


def test_apply_requires_env_gate(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _seed_db(db)
    pack = _seed_ui_pack(tmp_path)

    with pytest.raises(RuntimeError, match="ENABLE_STATUSDATE_INGEST_APPLY=1"):
        ingest_kaspi_statusdates_from_ui_pack(
            db_path=db,
            ui_pack_root=pack,
            apply=True,
            strict=True,
            backup_root=tmp_path / "backups",
            apply_manifest_root=tmp_path / "manifests",
        )


def test_apply_updates_and_creates_backup(monkeypatch, tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _seed_db(db)
    pack = _seed_ui_pack(tmp_path)
    monkeypatch.setenv("ENABLE_STATUSDATE_INGEST_APPLY", "1")

    report = ingest_kaspi_statusdates_from_ui_pack(
        db_path=db,
        ui_pack_root=pack,
        apply=True,
        strict=True,
        backup_root=tmp_path / "backups",
        apply_manifest_root=tmp_path / "manifests",
    )
    assert report["updates_planned"] == 1
    assert report["backup_path"]
    assert Path(report["backup_path"]).exists()
    assert _fetch_status(db, "1001").startswith("2026-02-26")
