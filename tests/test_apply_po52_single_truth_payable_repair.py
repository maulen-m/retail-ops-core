from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from scripts.apply_po52_single_truth_payable_repair import (
    ENV_GATE,
    EXPECTED_DB_TO_PAY_BASE_KZT,
    PO52RepairError,
    PO_PART_ID,
    TARGET_TO_PAY_BASE_KZT,
    _sha256_file,
    run_repair,
)


def _seed_db(db_path: Path, *, to_pay_base_kzt: float = EXPECTED_DB_TO_PAY_BASE_KZT) -> None:
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
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
            total_units INTEGER,
            updated_at TEXT
        );
        """
    )
    conn.execute(
        """
        INSERT INTO po_part (
            po_part_id, po_id, status, cargo_freight_id, actual_dlv_pay_date,
            est_weight_kg, actual_weight_kg, total_bags,
            paid_dlv_usd, paid_dlv_kzt, final_usd_per_kg, usd_kzt_rate, actual_dlv_days,
            is_paid_base, is_paid_dlv, to_pay_base_kzt, to_pay_dlv_kzt, total_units, updated_at
        ) VALUES (
            'PO-5.2', 'PO-5', 'RECEIVED', 'nan', '2026-02-16',
            2188.5, 2161.336311383231, 47,
            5770.874005412271, 2845040.8846682496, 2.6700490687259015, 493.0, 16,
            0, 1, ?, 0.0, 3980, '2026-06-01 06:25:23'
        );
        """,
        (to_pay_base_kzt,),
    )
    conn.commit()
    conn.close()


def _write_workbook(path: Path, *, to_pay_base_kzt: float = TARGET_TO_PAY_BASE_KZT) -> None:
    totals = pd.DataFrame(
        [
            {
                "PO_part_id": "PO-5.2",
                "PO_id": "PO-5",
                "Status": "Arrived",
                "Cargo_freight_id": "nan",
                "Actual_DLV_PAY_date": "2026-02-16",
                "is_paid_BASE": "NO",
                "is_paid_DLV": "YES",
                "To_pay_BASE_KZT": to_pay_base_kzt,
                "To_pay_DLV_KZT": 0.0,
                "Est. Weight (kg)": 2188.5,
                "Total Bags": 47,
                "Total Units": 3980,
                "Actual_Weight_kg": 2161.336311383231,
                "Paid_DLV_USD": 5770.874005412271,
                "Paid_DLV_KZT": 2845040.8846682496,
                "Final_USD_per_kg": 2.6700490687259015,
                "USD_KZT_rate": 493.0,
                "Actual_DLV_days": 16,
            }
        ]
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        totals.to_excel(writer, sheet_name="PO_part_id_Totals", index=False)


def _write_dashboard(path: Path) -> None:
    path.write_text(
        """{
  "archived_pos": ["PO-5.2"],
  "pos": {"PO-5.2": {"po_kind": "REAL_ARCHIVE"}},
  "real_pos": [{"po_id": "PO-5.2", "weight_nom_kg": 2161.336311383231, "total_places": 47}]
}
""",
        encoding="utf-8",
    )


def _write_scope_contract(path: Path) -> None:
    path.write_text(
        "po_part_id\tcanonical_decision\tproduction_authority\n",
        encoding="utf-8",
    )


def _row(db_path: Path) -> dict[str, object]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = dict(conn.execute("SELECT * FROM po_part WHERE po_part_id = ?", (PO_PART_ID,)).fetchone())
    conn.close()
    return row


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    db = tmp_path / "app.db"
    workbook = tmp_path / "inbound.xlsx"
    dashboard = tmp_path / "dashboard.json"
    scope_contract = tmp_path / "po_part_current_scope_contract.tsv"
    _seed_db(db)
    _write_workbook(workbook)
    _write_dashboard(dashboard)
    _write_scope_contract(scope_contract)
    return db, workbook, dashboard, scope_contract


def test_dry_run_uses_simulation_db_and_does_not_mutate_source(tmp_path: Path) -> None:
    db, workbook, dashboard, scope_contract = _fixture(tmp_path)

    before = _row(db)
    report = run_repair(
        db_path=db,
        workbook_path=workbook,
        dashboard_path=dashboard,
        po_part_scope_contract=scope_contract,
        output_dir=tmp_path / "dry_run",
    )
    after = _row(db)

    assert report["status"] == "DRY_RUN"
    assert report["rows_updated"] == 1
    assert report["post"]["single_truth_errors"] == []
    assert report["db_sha256_changed"] is False
    assert before == after


def test_apply_requires_env_gate_and_backup_dir(tmp_path: Path) -> None:
    db, workbook, dashboard, scope_contract = _fixture(tmp_path)

    with pytest.raises(PO52RepairError, match=ENV_GATE):
        run_repair(
            db_path=db,
            workbook_path=workbook,
            dashboard_path=dashboard,
            po_part_scope_contract=scope_contract,
            output_dir=tmp_path / "missing_gate",
            backup_dir=tmp_path / "backups",
            apply=True,
        )

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv(ENV_GATE, "1")
        with pytest.raises(PO52RepairError, match="--backup-dir"):
            run_repair(
                db_path=db,
                workbook_path=workbook,
                dashboard_path=dashboard,
                po_part_scope_contract=scope_contract,
                output_dir=tmp_path / "missing_backup",
                apply=True,
            )


def test_apply_enforces_pre_sha_and_updates_only_target_column(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, workbook, dashboard, scope_contract = _fixture(tmp_path)
    monkeypatch.setenv(ENV_GATE, "1")

    with pytest.raises(PO52RepairError, match="pre-SHA mismatch"):
        run_repair(
            db_path=db,
            workbook_path=workbook,
            dashboard_path=dashboard,
            po_part_scope_contract=scope_contract,
            output_dir=tmp_path / "wrong_sha",
            backup_dir=tmp_path / "backups_wrong",
            expected_pre_sha256="0" * 64,
            apply=True,
        )

    before = _row(db)
    report = run_repair(
        db_path=db,
        workbook_path=workbook,
        dashboard_path=dashboard,
        po_part_scope_contract=scope_contract,
        output_dir=tmp_path / "apply",
        backup_dir=tmp_path / "backups",
        expected_pre_sha256=_sha256_file(db),
        apply=True,
    )
    after = _row(db)

    assert report["status"] == "APPLIED"
    assert Path(report["gate"]["backup_path"]).exists()
    assert report["post"]["single_truth_errors"] == []
    assert before["to_pay_base_kzt"] == EXPECTED_DB_TO_PAY_BASE_KZT
    assert after["to_pay_base_kzt"] == TARGET_TO_PAY_BASE_KZT
    for key, value in before.items():
        if key == "to_pay_base_kzt":
            continue
        assert after[key] == value


def test_refuses_if_workbook_target_value_drifts(tmp_path: Path) -> None:
    db, workbook, dashboard, scope_contract = _fixture(tmp_path)
    _write_workbook(workbook, to_pay_base_kzt=123.0)

    with pytest.raises(PO52RepairError, match="workbook PO-5.2"):
        run_repair(
            db_path=db,
            workbook_path=workbook,
            dashboard_path=dashboard,
            po_part_scope_contract=scope_contract,
            output_dir=tmp_path / "bad_workbook",
        )


def test_refuses_if_precondition_is_not_exact_known_mismatch(tmp_path: Path) -> None:
    db, workbook, dashboard, scope_contract = _fixture(tmp_path)
    _seed_db(db, to_pay_base_kzt=TARGET_TO_PAY_BASE_KZT)

    with pytest.raises(PO52RepairError, match="current To_pay_BASE_KZT"):
        run_repair(
            db_path=db,
            workbook_path=workbook,
            dashboard_path=dashboard,
            po_part_scope_contract=scope_contract,
            output_dir=tmp_path / "already_fixed",
        )
