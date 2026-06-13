from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts.upsert_fx_rates import main


def _fx_args(db_path: Path) -> list[str]:
    return [
        "--db",
        str(db_path),
        "--effective-date",
        "2026-06-13",
        "--usdt-kzt",
        "485",
        "--usdt-cny",
        "6.7361111111",
        "--usd-kzt",
        "485",
        "--dlv-rate-usd-kg",
        "2.66",
        "--provider",
        "OWNER_ACTUAL",
        "--source",
        "PYTEST",
    ]


def _table_exists(db_path: Path, table_name: str) -> bool:
    with sqlite3.connect(str(db_path)) as conn:
        return (
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            ).fetchone()
            is not None
        )


def _create_fx_table(db_path: Path) -> None:
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE dim_fx_rates (
                effective_date TEXT PRIMARY KEY,
                usdt_kzt REAL NOT NULL,
                usdt_cny REAL NOT NULL,
                cny_kzt REAL NOT NULL,
                usd_kzt REAL NOT NULL,
                dlv_rate_usd_kg REAL NOT NULL,
                provider TEXT NOT NULL DEFAULT 'MANUAL',
                source TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            INSERT INTO dim_fx_rates (
                effective_date, usdt_kzt, usdt_cny, cny_kzt,
                usd_kzt, dlv_rate_usd_kg, provider, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-02-06",
                502.008032128514,
                6.91870584621685,
                72.5580828679126,
                514.0,
                2.66,
                "AUTO",
                "pytest",
            ),
        )


def test_default_invocation_does_not_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "app.db"
    db_path.touch()
    monkeypatch.delenv("ENABLE_FX_RATES_WRITE", raising=False)

    rc = main(_fx_args(db_path))

    assert rc == 0
    assert not _table_exists(db_path, "dim_fx_rates")


def test_apply_without_env_gate_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "app.db"
    db_path.touch()
    backup_dir = tmp_path / "backups"
    monkeypatch.delenv("ENABLE_FX_RATES_WRITE", raising=False)

    rc = main([*_fx_args(db_path), "--apply", "--backup-dir", str(backup_dir)])

    assert rc == 1
    assert not backup_dir.exists()
    assert not _table_exists(db_path, "dim_fx_rates")


def test_apply_with_env_gate_writes_exactly_one_expected_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    db_path.touch()
    backup_dir = tmp_path / "backups"
    monkeypatch.setenv("ENABLE_FX_RATES_WRITE", "1")

    rc = main([*_fx_args(db_path), "--apply", "--backup-dir", str(backup_dir)])

    assert rc == 0
    backups = list(backup_dir.glob("app_*.db"))
    assert len(backups) == 1
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            """
            SELECT effective_date, usdt_kzt, usdt_cny, cny_kzt,
                   usd_kzt, dlv_rate_usd_kg, provider, source
            FROM dim_fx_rates
            """
        ).fetchall()
    assert rows == [
        (
            "2026-06-13",
            485.0,
            6.7361111111,
            pytest.approx(485.0 / 6.7361111111),
            485.0,
            2.66,
            "OWNER_ACTUAL",
            "PYTEST",
        )
    ]


def test_dry_run_does_not_create_schema_on_empty_db(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    db_path.touch()

    rc = main([*_fx_args(db_path), "--dry-run", "--verbose"])

    assert rc == 0
    assert not _table_exists(db_path, "dim_fx_rates")


def test_show_latest_remains_read_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = tmp_path / "app.db"
    _create_fx_table(db_path)

    rc = main(["--db", str(db_path), "--show-latest"])

    assert rc == 0
    assert "2026-02-06" in capsys.readouterr().out
    with sqlite3.connect(str(db_path)) as conn:
        count = conn.execute("SELECT COUNT(*) FROM dim_fx_rates").fetchone()[0]
        source = conn.execute("SELECT source FROM dim_fx_rates").fetchone()[0]
    assert count == 1
    assert source == "pytest"
