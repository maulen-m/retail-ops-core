import sqlite3
import sys
import hashlib
from datetime import date
from pathlib import Path

import scripts.cashflow_preflight_po as preflight


def _file_state(path: Path) -> tuple[bool, str | None, int | None, int | None]:
    if not path.exists():
        return False, None, None, None
    stat = path.stat()
    return True, hashlib.sha256(path.read_bytes()).hexdigest(), stat.st_mtime_ns, stat.st_size


def _init_preflight_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(
            """
            CREATE TABLE fact_cashflow_daily (
                date TEXT PRIMARY KEY,
                cash_close REAL,
                receivables_close REAL,
                inventory_cost_close REAL,
                sales_accrued_kzt REAL,
                cogs_kzt REAL
            );
            CREATE TABLE fact_cashflow_commitments (
                commit_date TEXT,
                commit_type TEXT,
                amount_kzt REAL,
                scenario_tag TEXT,
                ref_id TEXT,
                notes TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO fact_cashflow_daily (
                date, cash_close, receivables_close, inventory_cost_close, sales_accrued_kzt, cogs_kzt
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("2026-01-10", 10000.0, 0.0, 0.0, 0.0, 0.0),
        )
        conn.execute(
            """
            INSERT INTO fact_cashflow_commitments (
                commit_date, commit_type, amount_kzt, scenario_tag, ref_id, notes
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("2026-01-10", "OPEX", 1000.0, "base", "OPEX-TEST", None),
        )
        conn.commit()
    finally:
        conn.close()


def test_preflight_floor_is_configurable(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "cashflow.db"
    _init_preflight_db(db_path)

    config_path = tmp_path / "cashflow_scenarios.yaml"
    config_path.write_text(
        "\n".join(
            [
                "cash_floor_abs_kzt: 123",
                "cash_floor_base_mult: 2.0",
                "cash_floor_cons_mult: 3.0",
                "payout_lag_days_override: 0",
                "cash_in_mode: delivered",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(preflight, "SCENARIOS_CONFIG", config_path)
    monkeypatch.setattr(preflight, "get_cutoff_date_almaty", lambda: date(2026, 1, 10))

    class DummyPayout:
        base_lag_days = 0
        conservative_lag_days = 0

    monkeypatch.setattr(preflight, "load_payout_model", lambda: DummyPayout())
    output_path = tmp_path / "cashflow_preflight_report.txt"
    canonical_state_before = _file_state(preflight.EXPORT_PATH)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cashflow_preflight_po.py",
            "--db",
            str(db_path),
            "--days",
            "3",
            "--output",
            str(output_path),
        ],
    )

    assert preflight.main() == 0
    output = capsys.readouterr().out
    assert "base_floor_kzt: 2000.00" in output
    assert "conservative_floor_kzt: 3123.00" in output
    assert output_path.exists()
    assert _file_state(preflight.EXPORT_PATH) == canonical_state_before


def test_nonproduction_db_requires_explicit_noncanonical_output(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "cashflow.db"
    _init_preflight_db(db_path)

    config_path = tmp_path / "cashflow_scenarios.yaml"
    config_path.write_text(
        "\n".join(
            [
                "cash_floor_abs_kzt: 123",
                "cash_floor_base_mult: 2.0",
                "cash_floor_cons_mult: 3.0",
                "payout_lag_days_override: 0",
                "cash_in_mode: delivered",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(preflight, "SCENARIOS_CONFIG", config_path)
    monkeypatch.setattr(preflight, "get_cutoff_date_almaty", lambda: date(2026, 1, 10))

    class DummyPayout:
        base_lag_days = 0
        conservative_lag_days = 0

    monkeypatch.setattr(preflight, "load_payout_model", lambda: DummyPayout())
    canonical_path = tmp_path / "canonical_cashflow_preflight_report.txt"
    canonical_path.write_text("trusted\n", encoding="utf-8")
    monkeypatch.setattr(preflight, "EXPORT_PATH", canonical_path)
    canonical_state_before = _file_state(canonical_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["cashflow_preflight_po.py", "--db", str(db_path), "--days", "3"],
    )

    assert preflight.main() == 2
    output = capsys.readouterr().out
    assert "--output is required" in output
    assert _file_state(canonical_path) == canonical_state_before


def test_preflight_rejects_output_path_that_collides_with_db(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "cashflow.db"
    _init_preflight_db(db_path)
    db_state_before = _file_state(db_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cashflow_preflight_po.py",
            "--db",
            str(db_path),
            "--output",
            str(db_path),
        ],
    )

    assert preflight.main() == 2
    output = capsys.readouterr().out
    assert "must not resolve to the DB path" in output
    assert _file_state(db_path) == db_state_before
