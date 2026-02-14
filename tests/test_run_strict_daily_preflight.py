from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from scripts.run_strict_daily_preflight import run_preflight


def test_preflight_fails_closed_when_workbook_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    db_path.write_text("", encoding="utf-8")

    code, summary = run_preflight(
        db_path=db_path,
        workbook_path=None,
        emit_lineage=False,
    )

    assert code != 0
    assert "AB_CRM_WORKBOOK_PATH" in summary


def test_preflight_propagates_strict_validation_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    workbook_path = tmp_path / "crm.xlsx"
    db_path.write_text("", encoding="utf-8")
    workbook_path.write_text("fixture", encoding="utf-8")

    def _fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=["python3"], returncode=0)

    monkeypatch.setattr("scripts.run_strict_daily_preflight.subprocess.run", _fake_run)

    code, summary = run_preflight(
        db_path=db_path,
        workbook_path=workbook_path,
        emit_lineage=False,
    )

    assert code == 0
    assert "PASS" in summary


def test_preflight_emits_lineage_when_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    workbook_path = tmp_path / "crm.xlsx"
    db_path.write_text("", encoding="utf-8")
    workbook_path.write_text("fixture", encoding="utf-8")
    lineage_path = tmp_path / "lineage.json"

    def _fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=["python3"], returncode=0)

    def _fake_emit(*, db_path: Path, workbook_path: Path, output_path: Path, strict_exit_code: int):
        output_path.write_text('{"ok": true}', encoding="utf-8")
        assert db_path.exists()
        assert workbook_path.exists()
        assert strict_exit_code == 0

    monkeypatch.setattr("scripts.run_strict_daily_preflight.subprocess.run", _fake_run)
    monkeypatch.setattr("scripts.run_strict_daily_preflight.emit_lineage_report", _fake_emit)

    code, _summary = run_preflight(
        db_path=db_path,
        workbook_path=workbook_path,
        emit_lineage=True,
        lineage_output=lineage_path,
    )

    assert code == 0
    assert lineage_path.exists()


def test_cli_emit_lineage_does_not_crash_from_script_entrypoint(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    workbook_path = tmp_path / "crm.xlsx"
    lineage_path = tmp_path / "lineage.json"
    db_path.write_text("", encoding="utf-8")
    workbook_path.write_text("fixture", encoding="utf-8")

    repo_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_strict_daily_preflight.py",
            "--db",
            str(db_path),
            "--workbook",
            str(workbook_path),
            "--emit-lineage",
            "--lineage-output",
            str(lineage_path),
        ],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )

    assert "ModuleNotFoundError" not in (completed.stderr or "")
    assert "STRICT_DAILY_PREFLIGHT" in (completed.stdout or "")
    assert lineage_path.exists()


def test_preflight_fails_when_workbook_is_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    workbook_path = tmp_path / "crm.xlsx"
    db_path.write_text("", encoding="utf-8")
    workbook_path.write_text("fixture", encoding="utf-8")
    stale_seconds = 72 * 3600
    old_ts = time.time() - stale_seconds
    workbook_path.touch()
    os.utime(workbook_path, (old_ts, old_ts))

    def _fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=["python3"], returncode=0)

    monkeypatch.setattr("scripts.run_strict_daily_preflight.subprocess.run", _fake_run)

    code, summary = run_preflight(
        db_path=db_path,
        workbook_path=workbook_path,
        emit_lineage=False,
        max_workbook_age_hours=24.0,
    )

    assert code != 0
    assert "stale workbook" in summary


def test_preflight_sends_failure_alert_on_strict_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    workbook_path = tmp_path / "crm.xlsx"
    db_path.write_text("", encoding="utf-8")
    workbook_path.write_text("fixture", encoding="utf-8")
    calls: list[tuple[str, str, str]] = []

    def _fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=["python3"], returncode=5)

    def _fake_alert(*, error_message: str, script_name: str, context: str):
        calls.append((error_message, script_name, context))
        return True

    monkeypatch.setattr("scripts.run_strict_daily_preflight.subprocess.run", _fake_run)
    monkeypatch.setattr("scripts.run_strict_daily_preflight.send_run_failure_alert", _fake_alert)

    code, summary = run_preflight(
        db_path=db_path,
        workbook_path=workbook_path,
        emit_lineage=False,
        send_alert_on_fail=True,
    )

    assert code == 5
    assert "FAIL" in summary
    assert len(calls) == 1
    assert calls[0][1] == "run_strict_daily_preflight"


def test_preflight_alert_failures_are_best_effort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    workbook_path = tmp_path / "crm.xlsx"
    db_path.write_text("", encoding="utf-8")
    workbook_path.write_text("fixture", encoding="utf-8")

    def _fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=["python3"], returncode=4)

    def _fake_alert(**_kwargs):
        raise RuntimeError("telegram down")

    monkeypatch.setattr("scripts.run_strict_daily_preflight.subprocess.run", _fake_run)
    monkeypatch.setattr("scripts.run_strict_daily_preflight.send_run_failure_alert", _fake_alert)

    code, summary = run_preflight(
        db_path=db_path,
        workbook_path=workbook_path,
        emit_lineage=False,
        send_alert_on_fail=True,
    )

    assert code == 4
    assert "FAIL" in summary
