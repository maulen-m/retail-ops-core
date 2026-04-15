from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
import time

import pytest
import yaml

from scripts.validate_opex_readiness import OpexReadinessError, validate_opex_readiness


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE fact_cashflow_commitments (
            commit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            commit_date TEXT NOT NULL,
            commit_type TEXT NOT NULL,
            amount_kzt REAL NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO fact_cashflow_commitments (commit_date, commit_type, amount_kzt) VALUES ('2026-05-01', 'OPEX', 10000)"
    )
    conn.commit()
    conn.close()


def test_validate_opex_readiness_pass(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)

    schedule_yaml = tmp_path / "opex_schedule.yaml"
    source_xlsx = tmp_path / "source.xlsx"
    source_xlsx.write_text("xlsx", encoding="utf-8")
    schedule_yaml.write_text(
        yaml.safe_dump({"source_xlsx": str(source_xlsx)}),
        encoding="utf-8",
    )
    recent = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp()
    import os

    os.utime(schedule_yaml, (recent, recent))

    report = validate_opex_readiness(
        db_path=db_path,
        as_of=date(2026, 3, 4),
        output_root=tmp_path / "out",
        schedule_yaml=schedule_yaml,
        max_schedule_age_days=30,
        min_horizon_days=30,
        reference_utc=datetime(2026, 3, 4, 18, 0, 0, tzinfo=timezone.utc),
        strict=True,
    )
    assert report["status"] == "PASS"
    assert report["ok"] is True
    assert report["max_commit_date"] == "2026-05-01"


def test_validate_opex_readiness_fails_stale_schedule(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)

    schedule_yaml = tmp_path / "opex_schedule.yaml"
    source_xlsx = tmp_path / "source.xlsx"
    source_xlsx.write_text("xlsx", encoding="utf-8")
    schedule_yaml.write_text(yaml.safe_dump({"source_xlsx": str(source_xlsx)}), encoding="utf-8")
    stale = time.time() - (40 * 86400)
    schedule_yaml.chmod(0o644)
    import os

    os.utime(schedule_yaml, (stale, stale))

    with pytest.raises(OpexReadinessError):
        validate_opex_readiness(
            db_path=db_path,
            as_of=date(2026, 3, 4),
            output_root=tmp_path / "out",
            schedule_yaml=schedule_yaml,
            max_schedule_age_days=30,
            min_horizon_days=30,
            reference_utc=datetime(2026, 3, 4, 18, 0, 0, tzinfo=timezone.utc),
            strict=True,
        )


def test_validate_opex_readiness_uses_as_of_window_for_historical_replay(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)

    schedule_yaml = tmp_path / "opex_schedule.yaml"
    source_xlsx = tmp_path / "source.xlsx"
    source_xlsx.write_text("xlsx", encoding="utf-8")
    schedule_yaml.write_text(yaml.safe_dump({"source_xlsx": str(source_xlsx)}), encoding="utf-8")

    historical_modified = datetime(2026, 3, 9, 9, 5, 45, tzinfo=timezone.utc).timestamp()
    import os

    os.utime(schedule_yaml, (historical_modified, historical_modified))

    report = validate_opex_readiness(
        db_path=db_path,
        as_of=date(2026, 3, 19),
        output_root=tmp_path / "out",
        schedule_yaml=schedule_yaml,
        max_schedule_age_days=30,
        min_horizon_days=30,
        strict=True,
        reference_utc=datetime(2026, 4, 14, 16, 41, 56, tzinfo=timezone.utc),
    )
    assert report["status"] == "PASS"
    assert report["schedule_age_days"] == 10
