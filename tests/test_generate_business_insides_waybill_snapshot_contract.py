from __future__ import annotations

import json
from datetime import date
import os
import sqlite3
from pathlib import Path

from scripts.generate_business_insides import (
    load_shipped_truth_snapshot,
    load_waybill_selection_snapshot,
)


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


def test_waybill_snapshot_prefers_archive_when_cache_underflow_detected(
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
                "target_date": as_of,
                "stores": {"UNIVERSAL": ["835000001"]},
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
    monkeypatch.setattr("scripts.generate_business_insides.PROJECT_ROOT", tmp_path)

    snapshot = load_waybill_selection_snapshot(
        db_path=db_path,
        as_of_date=date.fromisoformat(as_of),
        selection_cache_path=cache_path,
    )
    assert snapshot["status"] == "available_archive"
    assert snapshot["reason"] == "archive_fallback_cache_underflow"
    assert snapshot["totals"]["orders"] == 2


def test_load_shipped_truth_snapshot_reads_range_summary(tmp_path: Path) -> None:
    shipped_root = tmp_path / "shipped_truth"
    summary_path = shipped_root / "2026-02-01_to_2026-03-01" / "summary.json"
    summary_path.parent.mkdir(parents=True)
    summary_path.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "day": "2026-02-08",
                        "store": "Universal",
                        "api_primary": 10,
                        "provisional": False,
                    },
                    {
                        "day": "2026-02-08",
                        "store": "AcmeWear",
                        "api_primary": 3,
                        "provisional": False,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    snapshot = load_shipped_truth_snapshot(
        as_of_date=date.fromisoformat("2026-02-08"),
        shipped_truth_root=shipped_root,
    )

    assert snapshot is not None
    assert snapshot["status"] == "available_shipped_truth"
    assert snapshot["totals"]["orders"] == 13
    assert snapshot["stores"]["Universal"]["orders"] == 10
    assert snapshot["stores"]["AcmeWear"]["orders"] == 3


def test_load_shipped_truth_snapshot_returns_none_when_day_missing(tmp_path: Path) -> None:
    shipped_root = tmp_path / "shipped_truth"
    summary_path = shipped_root / "2026-02-01_to_2026-03-01" / "summary.json"
    summary_path.parent.mkdir(parents=True)
    summary_path.write_text(json.dumps({"rows": []}), encoding="utf-8")

    snapshot = load_shipped_truth_snapshot(
        as_of_date=date.fromisoformat("2026-02-10"),
        shipped_truth_root=shipped_root,
    )

    assert snapshot is None


def test_load_shipped_truth_snapshot_prefers_newest_summary(tmp_path: Path) -> None:
    shipped_root = tmp_path / "shipped_truth"
    older = shipped_root / "2026-02-17_to_2026-02-17" / "summary.json"
    newer = shipped_root / "2026-02-01_to_2026-03-01" / "summary.json"
    older.parent.mkdir(parents=True)
    newer.parent.mkdir(parents=True)
    older.write_text(
        json.dumps(
            {"rows": [{"day": "2026-02-17", "store": "Universal", "api_primary": 48, "provisional": False}]}
        ),
        encoding="utf-8",
    )
    newer.write_text(
        json.dumps(
            {"rows": [{"day": "2026-02-17", "store": "Universal", "api_primary": 50, "provisional": False}]}
        ),
        encoding="utf-8",
    )
    # Use distinct timestamps: fast filesystems can otherwise assign equal
    # mtimes and legitimately invoke the smaller-window tie-breaker.
    os.utime(older, ns=(1_000_000_000, 1_000_000_000))
    os.utime(newer, ns=(2_000_000_000, 2_000_000_000))

    snapshot = load_shipped_truth_snapshot(
        as_of_date=date.fromisoformat("2026-02-17"),
        shipped_truth_root=shipped_root,
    )

    assert snapshot is not None
    assert snapshot["totals"]["orders"] == 50
