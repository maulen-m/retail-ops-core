from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

import pytest

from scripts.run_strict_daily_preflight import run_preflight


def _seed_sqlite_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS sanity_check (id INTEGER PRIMARY KEY)")
        conn.commit()
    finally:
        conn.close()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_preflight_proof_window_lock_blocks_before_db_or_workbook_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = tmp_path / "proof_window.lock"
    lock_path.write_text("release proof in progress\n", encoding="utf-8")
    db_path = tmp_path / "must_not_open.db"
    workbook_path = tmp_path / "must_not_stat.xlsx"

    def _forbidden_subprocess(*_args, **_kwargs):
        raise AssertionError("proof-window lock must block before validator subprocesses")

    def _forbidden_business_insides(*_args, **_kwargs):
        raise AssertionError("proof-window lock must block before business-insides generation")

    monkeypatch.setenv("AB_PROOF_WINDOW_LOCK_PATH", str(lock_path))
    monkeypatch.setattr("scripts.run_strict_daily_preflight.subprocess.run", _forbidden_subprocess)
    monkeypatch.setattr(
        "scripts.run_strict_daily_preflight._ensure_business_insides_snapshot",
        _forbidden_business_insides,
    )

    code, summary = run_preflight(
        db_path=db_path,
        workbook_path=workbook_path,
        emit_lineage=True,
        ensure_business_insides=True,
        emit_drift_pack=True,
    )

    assert code != 0
    assert "STRICT_DAILY_PREFLIGHT_BLOCKED_BY_PROOF_WINDOW_LOCK" in summary
    assert str(lock_path) in summary


def test_preflight_proof_window_lock_uses_repo_default_when_env_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path = tmp_path / "config" / "proof_window.lock"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text("release proof in progress\n", encoding="utf-8")

    def _forbidden_subprocess(*_args, **_kwargs):
        raise AssertionError("default proof-window lock must block validator subprocesses")

    monkeypatch.delenv("AB_PROOF_WINDOW_LOCK_PATH", raising=False)
    monkeypatch.setattr("scripts.run_strict_daily_preflight.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("scripts.run_strict_daily_preflight.subprocess.run", _forbidden_subprocess)

    code, summary = run_preflight(
        db_path=tmp_path / "db" / "app.db",
        workbook_path=None,
        emit_lineage=False,
        ensure_business_insides=False,
    )

    assert code != 0
    assert "STRICT_DAILY_PREFLIGHT_BLOCKED_BY_PROOF_WINDOW_LOCK" in summary
    assert str(lock_path) in summary


def test_preflight_fails_closed_when_workbook_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    _seed_sqlite_db(db_path)
    monkeypatch.delenv("AB_CRM_WORKBOOK_PATH", raising=False)

    code, summary = run_preflight(
        db_path=db_path,
        workbook_path=None,
        emit_lineage=False,
    )

    assert code != 0
    assert "AB_CRM_WORKBOOK_PATH" in summary


def test_preflight_uses_env_workbook_path_when_not_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    _seed_sqlite_db(db_path)
    missing_workbook = tmp_path / "missing.xlsx"
    monkeypatch.setenv("AB_CRM_WORKBOOK_PATH", str(missing_workbook))

    code, summary = run_preflight(
        db_path=db_path,
        workbook_path=None,
        emit_lineage=False,
    )

    assert code != 0
    assert str(missing_workbook) in summary


def test_preflight_propagates_strict_validation_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    workbook_path = tmp_path / "crm.xlsx"
    _seed_sqlite_db(db_path)
    workbook_path.write_text("fixture", encoding="utf-8")

    def _fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=["python3"], returncode=0)

    monkeypatch.setattr("scripts.run_strict_daily_preflight.subprocess.run", _fake_run)

    code, summary = run_preflight(
        db_path=db_path,
        workbook_path=workbook_path,
        emit_lineage=False,
        ensure_business_insides=False,
    )

    assert code == 0
    assert "PASS" in summary


def test_preflight_emits_lineage_when_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    workbook_path = tmp_path / "crm.xlsx"
    _seed_sqlite_db(db_path)
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
        ensure_business_insides=False,
    )

    assert code == 0
    assert lineage_path.exists()


def test_cli_emit_lineage_does_not_crash_from_script_entrypoint(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    workbook_path = tmp_path / "crm.xlsx"
    lineage_path = tmp_path / "lineage.json"
    _seed_sqlite_db(db_path)
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
            "--no-ensure-business-insides",
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
    _seed_sqlite_db(db_path)
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
    _seed_sqlite_db(db_path)
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
    _seed_sqlite_db(db_path)
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


def test_preflight_autogenerates_business_insides_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    workbook_path = tmp_path / "crm.xlsx"
    _seed_sqlite_db(db_path)
    workbook_path.write_text("fixture", encoding="utf-8")
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "business_insides" / "snapshots").mkdir(parents=True, exist_ok=True)

    calls: list[list[str]] = []

    def _fake_run(cmd, *args, **kwargs):
        calls.append([str(part) for part in cmd])
        cmd_str = " ".join(str(part) for part in cmd)
        if "generate_business_insides.py" in cmd_str:
            snapshot = (
                tmp_path
                / "config"
                / "business_insides"
                / "BUSINESS_INSIDES_2026-02-17.md"
            )
            snapshot.write_text("# ok\n", encoding="utf-8")
            return subprocess.CompletedProcess(args=cmd, returncode=0)
        if "validate_params.py" in cmd_str:
            return subprocess.CompletedProcess(args=cmd, returncode=0)
        raise AssertionError(f"Unexpected command: {cmd_str}")

    monkeypatch.setattr("scripts.run_strict_daily_preflight.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("scripts.run_strict_daily_preflight.subprocess.run", _fake_run)

    code, summary = run_preflight(
        db_path=db_path,
        workbook_path=workbook_path,
        emit_lineage=False,
        ensure_business_insides=True,
        business_insides_as_of="2026-02-17",
    )

    assert code == 0
    assert "PASS" in summary
    gen_calls = [cmd for cmd in calls if "generate_business_insides.py" in " ".join(cmd)]
    assert gen_calls, "expected generate_business_insides.py call"
    assert all("--strict-cogs" not in cmd for cmd in gen_calls)
    assert any("validate_params.py" in " ".join(cmd) for cmd in calls)


def test_preflight_fails_when_business_insides_generation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    workbook_path = tmp_path / "crm.xlsx"
    _seed_sqlite_db(db_path)
    workbook_path.write_text("fixture", encoding="utf-8")
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "business_insides" / "snapshots").mkdir(parents=True, exist_ok=True)

    def _fake_run(cmd, *args, **kwargs):
        cmd_str = " ".join(str(part) for part in cmd)
        if "generate_business_insides.py" in cmd_str:
            return subprocess.CompletedProcess(args=cmd, returncode=7)
        raise AssertionError("validate_params should not run when generation fails")

    monkeypatch.setattr("scripts.run_strict_daily_preflight.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("scripts.run_strict_daily_preflight.subprocess.run", _fake_run)

    code, summary = run_preflight(
        db_path=db_path,
        workbook_path=workbook_path,
        emit_lineage=False,
        ensure_business_insides=True,
        business_insides_as_of="2026-02-17",
    )

    assert code == 7
    assert "business-insides generation failed" in summary


def test_preflight_emits_drift_pack_after_strict_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    workbook_path = tmp_path / "crm.xlsx"
    _seed_sqlite_db(db_path)
    workbook_path.write_text("fixture", encoding="utf-8")
    calls: list[dict] = []

    def _fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=["python3"], returncode=0)

    def _fake_build(*, db_path: Path, as_of: str, workbook_path: Path, max_lag_days: int):
        calls.append(
            {
                "db_path": str(db_path),
                "as_of": as_of,
                "workbook_path": str(workbook_path),
                "max_lag_days": max_lag_days,
            }
        )
        out_dir = tmp_path / "exports" / "validation" / as_of
        out_dir.mkdir(parents=True, exist_ok=True)
        md = out_dir / "single_truth_drift_pack.md"
        js = out_dir / "single_truth_drift_pack.json"
        md.write_text("# ok\n", encoding="utf-8")
        js.write_text("{}", encoding="utf-8")
        return {"markdown_path": str(md), "json_path": str(js)}

    monkeypatch.setattr("scripts.run_strict_daily_preflight.subprocess.run", _fake_run)
    monkeypatch.setattr("scripts.run_strict_daily_preflight.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("scripts.run_strict_daily_preflight.build_single_truth_drift_pack", _fake_build, raising=False)

    code, summary = run_preflight(
        db_path=db_path,
        workbook_path=workbook_path,
        emit_lineage=False,
        ensure_business_insides=False,
        emit_drift_pack=True,
        business_insides_as_of="2026-02-17",
    )

    assert code == 0
    assert "PASS" in summary
    assert len(calls) == 1
    assert calls[0]["max_lag_days"] == 1


def test_preflight_passes_workbook_env_to_validate_params_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    workbook_path = tmp_path / "crm.xlsx"
    _seed_sqlite_db(db_path)
    workbook_path.write_text("fixture", encoding="utf-8")
    captured_env: dict[str, str] = {}
    captured_db_path: Path | None = None

    def _fake_run(cmd, *args, **kwargs):
        nonlocal captured_db_path
        cmd_str = " ".join(str(part) for part in cmd)
        if "validate_params.py" in cmd_str:
            captured_env.update(kwargs.get("env", {}))
            captured_db_path = Path(cmd[cmd.index("--db") + 1])
            return subprocess.CompletedProcess(args=cmd, returncode=0)
        raise AssertionError(f"Unexpected command: {cmd_str}")

    monkeypatch.setattr("scripts.run_strict_daily_preflight.subprocess.run", _fake_run)

    code, _summary = run_preflight(
        db_path=db_path,
        workbook_path=workbook_path,
        emit_lineage=False,
        ensure_business_insides=False,
    )

    assert code == 0
    assert captured_env.get("AB_CRM_WORKBOOK_PATH") == str(workbook_path)
    assert captured_db_path is not None
    assert captured_db_path != db_path


def test_preflight_keeps_source_db_stable_when_strict_validator_mutates_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    workbook_path = tmp_path / "crm.xlsx"
    _seed_sqlite_db(db_path)
    workbook_path.write_text("fixture", encoding="utf-8")
    before_hash = _sha256(db_path)
    captured_db_path: Path | None = None

    def _fake_run(cmd, *args, **kwargs):
        nonlocal captured_db_path
        cmd_str = " ".join(str(part) for part in cmd)
        if "validate_params.py" in cmd_str:
            captured_db_path = Path(cmd[cmd.index("--db") + 1])
            conn = sqlite3.connect(captured_db_path)
            try:
                conn.execute("CREATE VIEW validation_only_view AS SELECT 1 AS ok")
                conn.commit()
            finally:
                conn.close()
            return subprocess.CompletedProcess(args=cmd, returncode=0)
        raise AssertionError(f"Unexpected command: {cmd_str}")

    monkeypatch.setattr("scripts.run_strict_daily_preflight.subprocess.run", _fake_run)

    code, summary = run_preflight(
        db_path=db_path,
        workbook_path=workbook_path,
        emit_lineage=False,
        ensure_business_insides=False,
    )

    assert code == 0
    assert "PASS" in summary
    assert captured_db_path is not None
    assert captured_db_path != db_path
    assert _sha256(db_path) == before_hash


def test_preflight_fails_when_workbook_mtime_is_future_beyond_skew(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    workbook_path = tmp_path / "crm.xlsx"
    _seed_sqlite_db(db_path)
    workbook_path.write_text("fixture", encoding="utf-8")
    now = time.time()
    future_ts = now + 600
    os.utime(workbook_path, (future_ts, future_ts))

    def _fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=["python3"], returncode=0)

    monkeypatch.setattr("scripts.run_strict_daily_preflight.subprocess.run", _fake_run)

    code, summary = run_preflight(
        db_path=db_path,
        workbook_path=workbook_path,
        emit_lineage=False,
        ensure_business_insides=False,
    )

    assert code != 0
    assert "future workbook mtime" in summary


def test_preflight_allows_small_future_mtime_within_skew(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    workbook_path = tmp_path / "crm.xlsx"
    _seed_sqlite_db(db_path)
    workbook_path.write_text("fixture", encoding="utf-8")
    now = time.time()
    future_ts = now + 30
    os.utime(workbook_path, (future_ts, future_ts))

    def _fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=["python3"], returncode=0)

    monkeypatch.setattr("scripts.run_strict_daily_preflight.subprocess.run", _fake_run)

    code, summary = run_preflight(
        db_path=db_path,
        workbook_path=workbook_path,
        emit_lineage=False,
        ensure_business_insides=False,
    )

    assert code == 0
    assert "PASS" in summary


def test_preflight_uses_36h_default_age_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "app.db"
    workbook_path = tmp_path / "crm.xlsx"
    _seed_sqlite_db(db_path)
    workbook_path.write_text("fixture", encoding="utf-8")
    old_ts = time.time() - (40 * 3600)
    os.utime(workbook_path, (old_ts, old_ts))

    def _fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=["python3"], returncode=0)

    monkeypatch.setattr("scripts.run_strict_daily_preflight.subprocess.run", _fake_run)

    code, summary = run_preflight(
        db_path=db_path,
        workbook_path=workbook_path,
        emit_lineage=False,
        ensure_business_insides=False,
    )

    assert code != 0
    assert "stale workbook" in summary
