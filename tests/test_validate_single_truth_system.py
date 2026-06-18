import json
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from scripts.validate_single_truth_system import validate_system


def _seed_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE po_part (
            po_part_id TEXT PRIMARY KEY,
            po_id TEXT,
            status TEXT,
            cargo_freight_id TEXT,
            actual_dlv_pay_date TEXT,
            est_weight_kg REAL,
            actual_weight_kg REAL,
            total_bags INTEGER,
            paid_dlv_usd REAL,
            paid_dlv_kzt REAL,
            final_usd_per_kg REAL,
            usd_kzt_rate REAL,
            actual_dlv_days INTEGER,
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
            po_part_id, po_id, status, cargo_freight_id, actual_dlv_pay_date,
            est_weight_kg, actual_weight_kg, total_bags,
            paid_dlv_usd, paid_dlv_kzt, final_usd_per_kg, usd_kzt_rate, actual_dlv_days,
            is_paid_base, is_paid_dlv, to_pay_base_kzt, to_pay_dlv_kzt, total_units
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "PO-4.1",
                "PO-4.1",
                "RECEIVED",
                "WB-PO41",
                "2026-02-05",
                475.8,
                475.8,
                13,
                1290.0,
                670800.0,
                2.71,
                520.0,
                15,
                1,
                1,
                0,
                0,
                1430,
            ),
            (
                "PO-5.2",
                "PO-5",
                "IN_TRANSIT",
                "WB-PO52",
                "",
                2188.5,
                0.0,
                53,
                0.0,
                0.0,
                0.0,
                0.0,
                0,
                0,
                0,
                9305790,
                3085347.3,
                3980,
            ),
        ],
    )
    conn.commit()
    conn.close()


def _write_workbook(
    path: Path,
    paid_dlv_po41: str = "YES",
    po52_actual_dlv_days: object = 0,
    live_money_headers: bool = False,
    reference_base_header: bool = False,
) -> None:
    totals = pd.DataFrame(
        [
            {
                "PO_part_id": "PO-4.1",
                "PO_id": "PO-4.1",
                "Status": "Arrived",
                "Cargo_freight_id": "WB-PO41",
                "Actual_DLV_PAY_date": "2026-02-05",
                "is_paid_BASE": "YES",
                "is_paid_DLV": paid_dlv_po41,
                "To_pay_BASE_KZT": 0,
                "To_pay_DLV_KZT": 0,
                "Est. Weight (kg)": 475.8,
                "Total Bags": 13,
                "Total Units": 1430,
                "Actual_Weight_kg": 475.8,
                "Paid_DLV_USD": 1290.0,
                "Paid_DLV_KZT": 670800.0,
                "Final_USD_per_kg": 2.71,
                "USD_KZT_rate": 520.0,
                "Actual_DLV_days": 15,
            },
            {
                "PO_part_id": "PO-5.2",
                "PO_id": "PO-5",
                "Status": "Transit",
                "Cargo_freight_id": "WB-PO52",
                "Actual_DLV_PAY_date": "",
                "is_paid_BASE": "NO",
                "is_paid_DLV": "NO",
                "To_pay_BASE_KZT": 9305790,
                "To_pay_DLV_KZT": 3085347.3,
                "Est. Weight (kg)": 2188.5,
                "Total Bags": 53,
                "Total Units": 3980,
                "Actual_Weight_kg": 0.0,
                "Paid_DLV_USD": 0.0,
                "Paid_DLV_KZT": 0.0,
                "Final_USD_per_kg": 0.0,
                "USD_KZT_rate": 0.0,
                "Actual_DLV_days": po52_actual_dlv_days,
            },
        ]
    )
    if live_money_headers:
        totals = totals.rename(
            columns={
                "To_pay_BASE_KZT": "To_pay_BASE_KZT (live)",
                "To_pay_DLV_KZT": "To_pay_DLV_KZT (live)",
            }
        )
    if reference_base_header:
        totals = totals.rename(columns={"To_pay_BASE_KZT": "To_pay_BASE_KZT_reference"})
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


def test_validate_system_handles_nan_actual_dlv_days(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    xlsx = tmp_path / "inbound.xlsx"
    dashboard = tmp_path / "dashboard.json"
    _seed_db(db_path)
    _write_workbook(xlsx, po52_actual_dlv_days=float("nan"))
    _write_payload(dashboard)

    errors = validate_system(db_path=db_path, workbook_path=xlsx, dashboard_path=dashboard)
    assert errors == []


def test_validate_system_parses_excel_serial_actual_dlv_pay_date(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    xlsx = tmp_path / "inbound.xlsx"
    dashboard = tmp_path / "dashboard.json"
    _seed_db(db_path)
    _write_payload(dashboard)
    _write_workbook(xlsx)

    # Replace workbook pay date with Excel serial for 2026-02-05.
    df = pd.read_excel(xlsx, sheet_name="PO_part_id_Totals", dtype=object)
    df.loc[df["PO_part_id"] == "PO-4.1", "Actual_DLV_PAY_date"] = 46058
    with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="PO_part_id_Totals", index=False)

    errors = validate_system(db_path=db_path, workbook_path=xlsx, dashboard_path=dashboard)
    assert errors == []


def test_validate_system_accepts_live_to_pay_display_headers(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    xlsx = tmp_path / "inbound.xlsx"
    dashboard = tmp_path / "dashboard.json"
    _seed_db(db_path)
    _write_workbook(xlsx, live_money_headers=True)
    _write_payload(dashboard)

    errors = validate_system(db_path=db_path, workbook_path=xlsx, dashboard_path=dashboard)
    assert errors == []


def test_validate_system_accepts_explicit_historical_db_only_scope_contract(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    xlsx = tmp_path / "inbound.xlsx"
    dashboard = tmp_path / "dashboard.json"
    scope_contract = tmp_path / "po_part_current_scope_contract.tsv"
    _seed_db(db_path)
    _write_workbook(xlsx)
    _write_payload(dashboard)

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO po_part (
            po_part_id, po_id, status, cargo_freight_id, actual_dlv_pay_date,
            est_weight_kg, actual_weight_kg, total_bags,
            paid_dlv_usd, paid_dlv_kzt, final_usd_per_kg, usd_kzt_rate, actual_dlv_days,
            is_paid_base, is_paid_dlv, to_pay_base_kzt, to_pay_dlv_kzt, total_units
        ) VALUES (
            'Line52_PO-1', 'Line52_PO-1', 'RECEIVED', '', '',
            0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 260
        )
        """
    )
    conn.commit()
    conn.close()
    scope_contract.write_text(
        "\t".join(["po_part_id", "canonical_decision", "production_authority"]) + "\n"
        + "\t".join(
            [
                "Line52_PO-1",
                "HISTORICAL_DB_ONLY_OUT_OF_CURRENT_WORKBOOK_SCOPE",
                "false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    strict_errors = validate_system(db_path=db_path, workbook_path=xlsx, dashboard_path=dashboard)
    assert any("Line52_PO-1" in err for err in strict_errors)

    errors = validate_system(
        db_path=db_path,
        workbook_path=xlsx,
        dashboard_path=dashboard,
        po_part_scope_contract=scope_contract,
    )
    assert errors == []


def test_validate_system_fails_on_ambiguous_to_pay_display_headers(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    xlsx = tmp_path / "inbound.xlsx"
    dashboard = tmp_path / "dashboard.json"
    _seed_db(db_path)
    _write_workbook(xlsx)
    _write_payload(dashboard)

    df = pd.read_excel(xlsx, sheet_name="PO_part_id_Totals", dtype=object)
    df["To_pay_BASE_KZT (live)"] = df["To_pay_BASE_KZT"]
    with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="PO_part_id_Totals", index=False)

    with pytest.raises(RuntimeError, match="ambiguous columns.*To_pay_BASE_KZT"):
        validate_system(db_path=db_path, workbook_path=xlsx, dashboard_path=dashboard)


def test_validate_system_accepts_to_pay_base_kzt_reference_header(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    xlsx = tmp_path / "inbound.xlsx"
    dashboard = tmp_path / "dashboard.json"
    _seed_db(db_path)
    _write_workbook(xlsx, reference_base_header=True)
    _write_payload(dashboard)

    assert validate_system(db_path=db_path, workbook_path=xlsx, dashboard_path=dashboard) == []
