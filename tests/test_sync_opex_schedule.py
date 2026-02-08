import os
import sqlite3
from pathlib import Path

import pandas as pd
import yaml

from scripts.sync_opex_schedule import sync_opex_schedule


def _init_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE fact_cashflow_commitments (
            commit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            commit_date TEXT NOT NULL,
            commit_type TEXT NOT NULL,
            amount_kzt REAL NOT NULL,
            probability REAL,
            scenario_tag TEXT,
            ref_id TEXT,
            notes TEXT
        );
        """
    )
    conn.commit()
    conn.close()


def _write_opex_xlsx(path: Path) -> None:
    rows = [
        {
            "Day_of_the_mnth": 5,
            "payment_schedule": "monthly",
            "Expense_type": "ops",
            "Expense_name": "Rent",
            "amount_daily_kzt": None,
            "amount_monthly_kzt": 150000,
            "today_date": "2026-02-08",
            "Months_of_payments_left_estimate": "const",
            "Current_principal_left": None,
        },
        {
            "Day_of_the_mnth": None,
            "payment_schedule": "daily",
            "Expense_type": "ops",
            "Expense_name": "Packing",
            "amount_daily_kzt": 2500,
            "amount_monthly_kzt": None,
            "today_date": "2026-02-08",
            "Months_of_payments_left_estimate": 1,
            "Current_principal_left": None,
        },
    ]
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name="Sheet1", index=False)


def test_sync_opex_dry_run_no_db_write(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    xlsx_path = tmp_path / "opex.xlsx"
    out_dir = tmp_path / "config_opex"
    _init_db(db_path)
    _write_opex_xlsx(xlsx_path)

    result = sync_opex_schedule(
        xlsx_path=xlsx_path,
        db_path=db_path,
        output_dir=out_dir,
        apply=False,
        replace_existing=False,
        horizon_days=30,
    )

    conn = sqlite3.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM fact_cashflow_commitments").fetchone()[0]
    conn.close()

    assert count == 0
    assert result["db_rows_inserted"] == 0
    assert (out_dir / "opex_schedule.yaml").exists()
    assert (out_dir / "opex_commitments.csv").exists()


def test_sync_opex_apply_requires_enable_cashflow_write_and_apply_flag(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    xlsx_path = tmp_path / "opex.xlsx"
    _init_db(db_path)
    _write_opex_xlsx(xlsx_path)

    if "ENABLE_CASHFLOW_WRITE" in os.environ:
        del os.environ["ENABLE_CASHFLOW_WRITE"]

    try:
        sync_opex_schedule(
            xlsx_path=xlsx_path,
            db_path=db_path,
            output_dir=tmp_path / "config_opex",
            apply=True,
            replace_existing=False,
            horizon_days=30,
        )
    except RuntimeError as exc:
        assert "ENABLE_CASHFLOW_WRITE=1" in str(exc)
    else:
        raise AssertionError("expected RuntimeError when apply=True without env gate")


def test_sync_opex_writes_repo_yaml_and_commitments_csv(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.db"
    xlsx_path = tmp_path / "opex.xlsx"
    out_dir = tmp_path / "config_opex"
    _init_db(db_path)
    _write_opex_xlsx(xlsx_path)
    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")

    sync_opex_schedule(
        xlsx_path=xlsx_path,
        db_path=db_path,
        output_dir=out_dir,
        apply=True,
        replace_existing=True,
        horizon_days=30,
    )

    schedule_path = out_dir / "opex_schedule.yaml"
    csv_path = out_dir / "opex_commitments.csv"
    assert schedule_path.exists()
    assert csv_path.exists()

    payload = yaml.safe_load(schedule_path.read_text(encoding="utf-8"))
    assert payload["source_xlsx"] == str(xlsx_path)
    assert payload["rows_generated"] > 0

    conn = sqlite3.connect(str(db_path))
    inserted = conn.execute("SELECT COUNT(*) FROM fact_cashflow_commitments").fetchone()[0]
    conn.close()
    assert inserted > 0


def test_sync_opex_replace_existing_keeps_idempotent_commitment_set(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.db"
    xlsx_path = tmp_path / "opex.xlsx"
    out_dir = tmp_path / "config_opex"
    _init_db(db_path)
    _write_opex_xlsx(xlsx_path)
    monkeypatch.setenv("ENABLE_CASHFLOW_WRITE", "1")

    sync_opex_schedule(
        xlsx_path=xlsx_path,
        db_path=db_path,
        output_dir=out_dir,
        apply=True,
        replace_existing=True,
        horizon_days=30,
    )
    conn = sqlite3.connect(str(db_path))
    first_count = conn.execute("SELECT COUNT(*) FROM fact_cashflow_commitments").fetchone()[0]
    conn.close()

    sync_opex_schedule(
        xlsx_path=xlsx_path,
        db_path=db_path,
        output_dir=out_dir,
        apply=True,
        replace_existing=True,
        horizon_days=30,
    )
    conn = sqlite3.connect(str(db_path))
    second_count = conn.execute("SELECT COUNT(*) FROM fact_cashflow_commitments").fetchone()[0]
    conn.close()

    assert first_count == second_count
