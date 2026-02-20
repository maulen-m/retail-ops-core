import json
import sqlite3
from pathlib import Path

import pandas as pd

from scripts.validate_single_truth_system import validate_system


def _seed_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE po_part (
            po_part_id TEXT PRIMARY KEY,
            po_id TEXT,
            status TEXT,
            est_weight_kg REAL,
            total_bags INTEGER,
            is_paid_base INTEGER,
            is_paid_dlv INTEGER,
            to_pay_base_kzt REAL,
            to_pay_dlv_kzt REAL,
            total_units INTEGER
        );
        """
    )
    conn.executemany(
        """
        INSERT INTO po_part (
            po_part_id, po_id, status, est_weight_kg, total_bags,
            is_paid_base, is_paid_dlv, to_pay_base_kzt, to_pay_dlv_kzt, total_units
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("PO-4.1", "PO-4.1", "RECEIVED", 475.8, 13, 1, 1, 0, 0, 1430),
            ("PO-5.2", "PO-5", "IN_TRANSIT", 2188.5, 53, 0, 0, 9305790, 3085347.3, 3980),
        ],
    )
    conn.commit()
    conn.close()


def _write_workbook(path: Path, paid_dlv_po41: str = "YES") -> None:
    totals = pd.DataFrame(
        [
            {
                "PO_part_id": "PO-4.1",
                "PO_id": "PO-4.1",
                "is_paid_BASE": "YES",
                "is_paid_DLV": paid_dlv_po41,
                "To_pay_BASE_KZT": 0,
                "To_pay_DLV_KZT": 0,
                "Est. Weight (kg)": 475.8,
                "Total Bags": 13,
                "Total Units": 1430,
            },
            {
                "PO_part_id": "PO-5.2",
                "PO_id": "PO-5",
                "is_paid_BASE": "NO",
                "is_paid_DLV": "NO",
                "To_pay_BASE_KZT": 9305790,
                "To_pay_DLV_KZT": 3085347.3,
                "Est. Weight (kg)": 2188.5,
                "Total Bags": 53,
                "Total Units": 3980,
            },
        ]
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        totals.to_excel(writer, sheet_name="PO_part_id_Totals", index=False)


def _write_payload(path: Path) -> None:
    payload = {
        "archived_pos": ["PO-4.1", "PO-5.2"],
        "pos": {
            "PO-4.1": {"po_kind": "REAL_ARCHIVE"},
            "PO-5.2": {"po_kind": "REAL_ARCHIVE"},
        },
        "real_pos": [
            {"po_id": "PO-4.1", "weight_nom_kg": 475.8, "total_places": 13},
            {"po_id": "PO-5.2", "weight_nom_kg": 2188.5, "total_places": 53},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_validate_system_passes_when_db_workbook_dashboard_are_aligned(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    xlsx = tmp_path / "inbound.xlsx"
    dashboard = tmp_path / "dashboard.json"
    _seed_db(db_path)
    _write_workbook(xlsx)
    _write_payload(dashboard)

    errors = validate_system(db_path=db_path, workbook_path=xlsx, dashboard_path=dashboard)
    assert errors == []


def test_validate_system_fails_on_paid_flag_mismatch(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    xlsx = tmp_path / "inbound.xlsx"
    dashboard = tmp_path / "dashboard.json"
    _seed_db(db_path)
    _write_workbook(xlsx, paid_dlv_po41="NO")
    _write_payload(dashboard)

    errors = validate_system(db_path=db_path, workbook_path=xlsx, dashboard_path=dashboard)
    assert any("PO-4.1" in err and "is_paid_DLV" in err for err in errors)
