import sqlite3
from pathlib import Path

from scripts.validate_single_truth_alignment import validate_alignment_payload


def _seed_po_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE po_line (
            po_id TEXT,
            po_part_id TEXT,
            sku_key TEXT,
            my_size TEXT,
            order_qty INTEGER
        );
        """
    )
    conn.executemany(
        "INSERT INTO po_line (po_id, sku_key, my_size, order_qty) VALUES (?, ?, ?, ?)",
        [
            ("PO-5", "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "M", 110),
            ("PO-5", "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "L", 240),
        ],
    )
    conn.commit()
    conn.close()


def test_validate_alignment_flags_real_archive_qty_mismatch(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_po_db(db_path)
    payload = {
        "pos": {
            "PO-5": {
                "po_name": "PO-5",
                "po_kind": "REAL_ARCHIVE",
                "po_message_date": "2026-01-21",
                "sku_level": [
                    {
                        "sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                        "po_qty_total": 999,
                        "baseline_snapshot_date": "2026-01-21",
                    }
                ],
                "size_level": [
                    {"sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "size": "M", "order_qty": 110},
                    {"sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "size": "L", "order_qty": 240},
                ],
            }
        }
    }

    errors = validate_alignment_payload(
        payload, db_path=db_path, run_cashflow=False, run_drift=False
    )
    assert any("po_line" in err and "PO-5" in err for err in errors)


def test_validate_alignment_flags_snapshot_after_message_date(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_po_db(db_path)
    payload = {
        "pos": {
            "PLAN-0": {
                "po_name": "PLAN-0",
                "po_kind": "PLAN",
                "po_message_date": "2026-03-01",
                "sku_level": [
                    {
                        "sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                        "po_qty_total": 350,
                        "baseline_snapshot_date": "2026-03-02",
                    }
                ],
                "size_level": [],
            }
        }
    }

    errors = validate_alignment_payload(
        payload, db_path=db_path, run_cashflow=False, run_drift=False
    )
    assert any("baseline_snapshot_date" in err for err in errors)


def test_validate_alignment_allows_real_archive_baseline_after_message_date(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_po_db(db_path)
    payload = {
        "pos": {
            "PO-5": {
                "po_name": "PO-5",
                "po_kind": "REAL_ARCHIVE",
                "po_message_date": "2026-01-21",
                "sku_level": [
                    {
                        "sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                        "po_qty_total": 350,
                        "baseline_snapshot_date": "2026-02-07",
                    }
                ],
                "size_level": [
                    {"sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "size": "M", "order_qty": 110},
                    {"sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "size": "L", "order_qty": 240},
                ],
            }
        }
    }

    errors = validate_alignment_payload(
        payload, db_path=db_path, run_cashflow=False, run_drift=False
    )
    assert not any("baseline_snapshot_date" in err for err in errors)


def test_validate_alignment_ignores_active_bag_skus_for_coverage(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE po_line (
            po_id TEXT,
            sku_key TEXT,
            my_size TEXT,
            order_qty INTEGER
        );
        CREATE TABLE dim_sku (
            sku_key TEXT,
            active_flag INTEGER,
            product_type TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO po_line (po_id, sku_key, my_size, order_qty) VALUES ('PO-4.1', 'Bag_gift', 'STD', 10)"
    )
    conn.execute(
        "INSERT INTO dim_sku (sku_key, active_flag, product_type) VALUES ('Bag_gift', 1, 'Bag')"
    )
    conn.commit()
    conn.close()

    payload = {
        "pos": {
            "PO-4.1": {
                "po_name": "PO-4.1",
                "po_kind": "REAL_ARCHIVE",
                "po_message_date": "2026-01-14",
                "sku_level": [],
                "size_level": [],
            }
        }
    }
    errors = validate_alignment_payload(
        payload, db_path=db_path, run_cashflow=False, run_drift=False
    )
    assert not any("Bag_gift" in err for err in errors)


def test_validate_alignment_reports_drift_failure(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.db"
    _seed_po_db(db_path)
    payload = {
        "pos": {
            "PO-5": {
                "po_name": "PO-5",
                "po_kind": "REAL_ARCHIVE",
                "po_message_date": "2026-01-21",
                "sku_level": [
                    {
                        "sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                        "po_qty_total": 350,
                        "baseline_snapshot_date": "2026-01-21",
                    }
                ],
                "size_level": [
                    {"sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "size": "M", "order_qty": 110},
                    {"sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "size": "L", "order_qty": 240},
                ],
            }
        }
    }
    monkeypatch.setattr(
        "scripts.validate_single_truth_alignment.validate_cashflow_invariants.validate",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(
        "scripts.validate_single_truth_alignment.validate_inventory_cost_drift.validate_drift",
        lambda *_args, **_kwargs: 1,
    )

    errors = validate_alignment_payload(
        payload, db_path=db_path, run_cashflow=True, run_drift=True
    )
    assert any("inventory cost drift validation failed" in err for err in errors)


def test_validate_alignment_passes_when_drift_and_cashflow_pass(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "app.db"
    _seed_po_db(db_path)
    payload = {
        "pos": {
            "PO-5": {
                "po_name": "PO-5",
                "po_kind": "REAL_ARCHIVE",
                "po_message_date": "2026-01-21",
                "sku_level": [
                    {
                        "sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                        "po_qty_total": 350,
                        "baseline_snapshot_date": "2026-01-21",
                    }
                ],
                "size_level": [
                    {"sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "size": "M", "order_qty": 110},
                    {"sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "size": "L", "order_qty": 240},
                ],
            }
        }
    }
    monkeypatch.setattr(
        "scripts.validate_single_truth_alignment.validate_cashflow_invariants.validate",
        lambda *_args, **_kwargs: 0,
    )
    monkeypatch.setattr(
        "scripts.validate_single_truth_alignment.validate_inventory_cost_drift.validate_drift",
        lambda *_args, **_kwargs: 0,
    )

    errors = validate_alignment_payload(
        payload, db_path=db_path, run_cashflow=True, run_drift=True
    )
    assert errors == []


def test_validate_alignment_prefers_part_rows_over_legacy_null_part(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE po_line (
            po_id TEXT,
            po_part_id TEXT,
            sku_key TEXT,
            my_size TEXT,
            order_qty INTEGER
        );
        """
    )
    conn.executemany(
        """
        INSERT INTO po_line (po_id, po_part_id, sku_key, my_size, order_qty)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("PO-5", None, "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "M", 110),
            ("PO-5", None, "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "L", 240),
            ("PO-5", "PO-5.2", "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "M", 110),
            ("PO-5", "PO-5.2", "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "L", 240),
        ],
    )
    conn.commit()
    conn.close()

    payload = {
        "pos": {
            "PO-5": {
                "po_name": "PO-5",
                "po_kind": "REAL_ARCHIVE",
                "po_message_date": "2026-01-21",
                "sku_level": [
                    {
                        "sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                        "po_qty_total": 350,
                        "baseline_snapshot_date": "2026-01-21",
                    }
                ],
                "size_level": [
                    {"sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "size": "M", "order_qty": 110},
                    {"sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "size": "L", "order_qty": 240},
                ],
            }
        }
    }
    errors = validate_alignment_payload(
        payload, db_path=db_path, run_cashflow=False, run_drift=False
    )
    assert errors == []
