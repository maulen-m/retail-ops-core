from __future__ import annotations

import fcntl
import hashlib
import json
import plistlib
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from scripts.manage_daily_shipping_recovery import (
    BACKUP_APPLY_ENV,
    RETENTION_APPLY_ENV,
    RESTORE_APPLY_ENV,
    RecoveryLock,
    create_snapshot,
    recovery_status,
    restore_drill,
    run_backup,
    run_retention,
)


UTC = timezone.utc
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_closeout_run(
    project: Path,
    *,
    run_name: str,
    target_date: str = "2026-07-13",
    ok: bool = True,
    mode: str = "apply",
) -> Path:
    run_dir = (
        project
        / "exports"
        / "google_ops_board"
        / "workflow_runs"
        / target_date
        / run_name
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    closeout = {
        "ok": ok,
        "mode": mode,
        "target_date": target_date,
        "run_id": run_name,
    }
    if ok and mode == "apply":
        expected_path = run_dir / "expected_closeout_orders.json"
        expected_path.write_text(
            json.dumps(
                {
                    "schema_version": 3,
                    "target_date": target_date,
                    "request_identity": {
                        "target_date": target_date,
                        "ready_set_at": f"{target_date}T17:00:00+05:00",
                    },
                    "expected_order_ids": [],
                    "orders": [],
                    "counts": {"orders": 0, "order_lines": 0, "overdue_orders": 0},
                }
            ),
            encoding="utf-8",
        )
        expected_sha = _sha256(expected_path)
        marker_path = run_dir / "zero_order_completion.json"
        marker_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "completed": True,
                    "mode": "apply",
                    "run_id": run_name,
                    "target_date": target_date,
                    "request_identity": {
                        "target_date": target_date,
                        "ready_set_at": f"{target_date}T17:00:00+05:00",
                    },
                    "required_order_count": 0,
                    "required_orders_path": str(expected_path.resolve()),
                    "required_orders_sha256": expected_sha,
                }
            ),
            encoding="utf-8",
        )
        closeout.update(
            {
                "zero_order_noop": True,
                "expected_closeout_order_count": 0,
                "expected_closeout_orders_path": str(expected_path.resolve()),
                "zero_order_completion_path": str(marker_path.resolve()),
            }
        )
    (run_dir / "closeout_report.json").write_text(
        json.dumps(closeout), encoding="utf-8"
    )
    (run_dir / "run_control_snapshot.json").write_text(
        json.dumps({"target_date": target_date, "matrix": [["target_date"], [target_date]]}),
        encoding="utf-8",
    )
    (run_dir / "salesraw_snapshot.json").write_text(
        json.dumps({"target_date": target_date, "matrix": [["Date"], [target_date]]}),
        encoding="utf-8",
    )
    return run_dir


def _project_fixture(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / "db").mkdir(parents=True)
    with sqlite3.connect(project / "db" / "app.db") as conn:
        conn.execute(
            "CREATE TABLE orders (id INTEGER PRIMARY KEY, state TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO orders(state) VALUES ('READY')")
    workbook = project / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
    workbook.parent.mkdir(parents=True)
    with ZipFile(workbook, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
    state = project / "runtime" / "state"
    state.mkdir(parents=True)
    (state / "waybill_shipping_obligations.json").write_text(
        json.dumps({"orders": ["order-1"]}), encoding="utf-8"
    )
    checkpoint = (
        project
        / "exports"
        / "google_ops_board"
        / "workflow_runs"
        / "2026-07-13"
        / "closeout_checkpoint.json"
    )
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text(json.dumps({"stages": {}}), encoding="utf-8")
    _write_closeout_run(
        project,
        run_name="20260713_191124_2026-07-13_closeout",
    )
    return project


def _write_extended_optional_shipping_state(project: Path) -> dict[str, bytes]:
    state = project / "runtime" / "state"
    payloads = {
        "waybill_prepacked_exclusion.json": b'{"excluded_order_ids":["order-1"]}\n',
        "google_ops_board_closeout_halt_barrier.json": b'{"halted":true}\n',
    }
    for filename, content in payloads.items():
        (state / filename).write_bytes(content)
    return payloads


def test_create_snapshot_is_sqlite_consistent_and_manifest_verified(
    tmp_path: Path,
) -> None:
    project = _project_fixture(tmp_path)
    _write_extended_optional_shipping_state(project)
    state_root = tmp_path / "state"

    report = create_snapshot(
        project_root=project,
        state_root=state_root,
        now=datetime(2026, 7, 13, 17, 0, tzinfo=UTC),
        hostname="M1-test",
    )

    snapshot = Path(report["snapshot_dir"])
    copied_db = snapshot / "data" / "app.db.sqlite"
    manifest_path = snapshot / "snapshot_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    with sqlite3.connect(f"file:{copied_db}?mode=ro", uri=True) as conn:
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT state FROM orders").fetchone()[0] == "READY"

    assert stat_mode(snapshot) == 0o700
    assert manifest["hostname"] == "M1-test"
    assert manifest["database_quick_check"] == "ok"
    assert manifest["artifacts"]["data/app.db.sqlite"]["sha256"] == _sha256(copied_db)
    assert "excel_ui/SALES_KSP_CRM_V3.xlsx" in manifest["artifacts"]
    assert "runtime/state/waybill_shipping_obligations.json" in manifest["artifacts"]
    assert "runtime/state/waybill_prepacked_exclusion.json" in manifest["artifacts"]
    assert (
        "runtime/state/google_ops_board_closeout_halt_barrier.json"
        in manifest["artifacts"]
    )
    assert "workflow/closeout_checkpoint.json" in manifest["artifacts"]
    assert "workflow/replay/closeout_report.json" in manifest["artifacts"]
    assert "workflow/replay/closeout_evidence.json" in manifest["artifacts"]
    assert "workflow/replay/run_control_snapshot.json" in manifest["artifacts"]
    assert "workflow/replay/salesraw_snapshot.json" in manifest["artifacts"]
    replay_report = json.loads(
        (snapshot / "workflow" / "replay" / "closeout_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert replay_report["run_id"] == "20260713_191124_2026-07-13_closeout"
    closeout_evidence = json.loads(
        (snapshot / "workflow" / "replay" / "closeout_evidence.json").read_text(
            encoding="utf-8"
        )
    )
    serialized_evidence = json.dumps(closeout_evidence)
    assert closeout_evidence["gate"] == "GREEN"
    assert closeout_evidence["completion_kind"] == "zero_order_noop"
    assert closeout_evidence["closeout_report_sha256"] == _sha256(
        snapshot / "workflow" / "replay" / "closeout_report.json"
    )
    assert closeout_evidence["pending_count"] == 0
    assert closeout_evidence["customer_data_exposed"] is False
    assert str(project) not in serialized_evidence


def test_snapshot_succeeds_when_extended_optional_state_files_are_absent(
    tmp_path: Path,
) -> None:
    project = _project_fixture(tmp_path)

    report = create_snapshot(
        project_root=project,
        state_root=tmp_path / "state",
        now=datetime(2026, 7, 13, 17, 0, tzinfo=UTC),
        hostname="M1-test",
    )

    manifest = json.loads(Path(report["manifest_path"]).read_text(encoding="utf-8"))
    assert report["gate"] == "GREEN"
    assert "runtime/state/waybill_prepacked_exclusion.json" not in manifest["artifacts"]
    assert (
        "runtime/state/google_ops_board_closeout_halt_barrier.json"
        not in manifest["artifacts"]
    )


def test_snapshot_ignores_newer_failed_closeout_for_replay(tmp_path: Path) -> None:
    project = _project_fixture(tmp_path)
    _write_closeout_run(
        project,
        run_name="20260713_201500_2026-07-13_closeout",
        ok=False,
    )

    report = create_snapshot(
        project_root=project,
        state_root=tmp_path / "state",
        now=datetime(2026, 7, 13, 17, 0, tzinfo=UTC),
        hostname="M1-test",
    )

    replay_report = json.loads(
        (
            Path(report["snapshot_dir"])
            / "workflow"
            / "replay"
            / "closeout_report.json"
        ).read_text(encoding="utf-8")
    )
    assert replay_report["run_id"] == "20260713_191124_2026-07-13_closeout"


def test_snapshot_ignores_newer_superficial_ok_closeout_without_terminal_evidence(
    tmp_path: Path,
) -> None:
    project = _project_fixture(tmp_path)
    superficial = _write_closeout_run(
        project,
        run_name="20260713_202000_2026-07-13-closeout",
    )
    closeout_path = superficial / "closeout_report.json"
    payload = json.loads(closeout_path.read_text(encoding="utf-8"))
    payload["zero_order_noop"] = False
    payload.pop("zero_order_completion_path")
    closeout_path.write_text(json.dumps(payload), encoding="utf-8")

    report = create_snapshot(
        project_root=project,
        state_root=tmp_path / "state",
        now=datetime(2026, 7, 13, 17, 0, tzinfo=UTC),
        hostname="M1-test",
    )

    replay_report = json.loads(
        (
            Path(report["snapshot_dir"])
            / "workflow"
            / "replay"
            / "closeout_report.json"
        ).read_text(encoding="utf-8")
    )
    assert replay_report["run_id"] == "20260713_191124_2026-07-13_closeout"


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


def test_snapshot_root_inside_repo_is_refused(tmp_path: Path) -> None:
    project = _project_fixture(tmp_path)

    with pytest.raises(ValueError, match="outside the repo"):
        create_snapshot(
            project_root=project, state_root=project / "runtime" / "recovery"
        )


def test_remote_backup_requires_explicit_apply_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project_fixture(tmp_path)
    monkeypatch.delenv(BACKUP_APPLY_ENV, raising=False)

    with pytest.raises(PermissionError, match=BACKUP_APPLY_ENV):
        run_backup(project_root=project, state_root=tmp_path / "state", apply=True)


def test_remote_backup_uses_password_command_without_exposing_a_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project_fixture(tmp_path)
    state_root = tmp_path / "state"
    monkeypatch.setenv(BACKUP_APPLY_ENV, "1")
    commands: list[list[str]] = []

    def fake_runner(command: list[str], **kwargs):
        commands.append(command)
        assert kwargs["env"]["RESTIC_PASSWORD_COMMAND"].startswith("/usr/bin/security ")
        snapshot_dir = Path(command[-1])
        assert (snapshot_dir / "snapshot_manifest.json").exists()
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {"message_type": "summary", "snapshot_id": "snapshot-123"}
            )
            + "\n",
            stderr="",
        )

    report = run_backup(
        project_root=project,
        state_root=state_root,
        apply=True,
        runner=fake_runner,
        now=datetime(2026, 7, 13, 17, 15, tzinfo=UTC),
        hostname="M1-test",
    )
    serialized = json.dumps(report)

    assert report["gate"] == "GREEN"
    assert report["snapshot_id"] == "snapshot-123"
    assert commands[0][0].endswith("restic")
    assert "backup" in commands[0]
    assert "password" not in serialized.lower()
    assert not any((state_root / "staging").iterdir())
    assert (state_root / "latest_success.json").exists()


def test_failed_remote_backup_cleans_staging_and_does_not_advance_latest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project_fixture(tmp_path)
    state_root = tmp_path / "state"
    state_root.mkdir()
    latest = state_root / "latest_success.json"
    latest.write_text(json.dumps({"snapshot_id": "prior"}), encoding="utf-8")
    monkeypatch.setenv(BACKUP_APPLY_ENV, "1")

    def fake_runner(command: list[str], **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="remote unavailable")

    report = run_backup(
        project_root=project,
        state_root=state_root,
        apply=True,
        runner=fake_runner,
    )

    assert report["gate"] == "RED"
    assert json.loads(latest.read_text(encoding="utf-8"))["snapshot_id"] == "prior"
    assert not any((state_root / "staging").iterdir())
    assert "remote unavailable" not in json.dumps(report)


def test_recovery_lock_refuses_concurrent_backup(tmp_path: Path) -> None:
    lock = tmp_path / ".backup.lock"
    with lock.open("a+") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match="already running"):
            with RecoveryLock(lock):
                pass


def test_status_enforces_freshness_and_never_needs_credentials(tmp_path: Path) -> None:
    state_root = tmp_path / "state"
    state_root.mkdir()
    recorded = datetime(2026, 7, 13, 17, 0, tzinfo=UTC)
    (state_root / "latest_success.json").write_text(
        json.dumps({"completed_at_utc": recorded.isoformat(), "snapshot_id": "abc"}),
        encoding="utf-8",
    )

    fresh = recovery_status(
        state_root=state_root,
        now=recorded + timedelta(minutes=14, seconds=59),
        max_age_minutes=15,
    )
    stale = recovery_status(
        state_root=state_root,
        now=recorded + timedelta(minutes=15, seconds=1),
        max_age_minutes=15,
    )

    assert fresh["gate"] == "GREEN"
    assert stale["gate"] == "RED"
    assert fresh["credential_values_read"] is False


def test_restore_drill_verifies_manifest_hashes_sqlite_and_rto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project_fixture(tmp_path)
    optional_state_payloads = _write_extended_optional_shipping_state(project)
    source_state = tmp_path / "source-state"
    snapshot_report = create_snapshot(project_root=project, state_root=source_state)
    source_snapshot = Path(snapshot_report["snapshot_dir"])
    manifest_sha = _sha256(source_snapshot / "snapshot_manifest.json")
    state_root = tmp_path / "state"
    state_root.mkdir()
    (state_root / "latest_success.json").write_text(
        json.dumps(
            {
                "snapshot_id": "snapshot-123",
                "manifest_sha256": manifest_sha,
                "completed_at_utc": datetime.now(UTC).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    target = tmp_path / "restore-target"
    monkeypatch.setenv(RESTORE_APPLY_ENV, "1")

    def fake_runner(command: list[str], **kwargs):
        restored = (
            Path(command[command.index("--target") + 1])
            / "restored"
            / source_snapshot.name
        )
        shutil.copytree(source_snapshot, restored)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    report = restore_drill(
        state_root=state_root,
        target=target,
        apply=True,
        runner=fake_runner,
        elapsed_seconds=lambda: 12.5,
    )

    assert report["gate"] == "GREEN"
    assert report["database_quick_check"] == "ok"
    assert report["manifest_sha256"] == manifest_sha
    assert report["elapsed_seconds"] == 12.5
    assert report["rto_met"] is True
    restored_state = (
        target / "restored" / source_snapshot.name / "runtime" / "state"
    )
    for filename, expected_bytes in optional_state_payloads.items():
        assert (restored_state / filename).read_bytes() == expected_bytes


def test_retention_requires_explicit_apply_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(RETENTION_APPLY_ENV, raising=False)

    with pytest.raises(PermissionError, match=RETENTION_APPLY_ENV):
        run_retention(state_root=tmp_path / "state", apply=True)


def test_retention_is_tag_scoped_and_records_only_a_redacted_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = tmp_path / "state"
    monkeypatch.setenv(RETENTION_APPLY_ENV, "1")
    commands: list[list[str]] = []

    def fake_runner(command: list[str], **kwargs):
        commands.append(command)
        assert kwargs["env"]["RESTIC_PASSWORD_COMMAND"].startswith("/usr/bin/security ")
        return SimpleNamespace(returncode=0, stdout='[{"keep": true}]', stderr="")

    report = run_retention(
        state_root=state_root,
        apply=True,
        runner=fake_runner,
        now=datetime(2026, 7, 13, 18, 0, tzinfo=UTC),
    )

    assert report["gate"] == "GREEN"
    assert report["policy"] == {
        "keep_within": "24h",
        "keep_daily": 14,
        "keep_weekly": 8,
        "keep_monthly": 12,
    }
    assert commands == [
        [
            commands[0][0],
            "forget",
            "--json",
            "--tag",
            "daily-shipping-critical",
            "--keep-within",
            "24h",
            "--keep-daily",
            "14",
            "--keep-weekly",
            "8",
            "--keep-monthly",
            "12",
            "--prune",
        ]
    ]
    assert "password" not in json.dumps(report).lower()
    assert (state_root / "latest_retention.json").exists()


def test_failed_retention_does_not_expose_provider_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = tmp_path / "state"
    monkeypatch.setenv(RETENTION_APPLY_ENV, "1")

    def fake_runner(command: list[str], **kwargs):
        return SimpleNamespace(
            returncode=1, stdout="", stderr="sensitive provider detail"
        )

    report = run_retention(state_root=state_root, apply=True, runner=fake_runner)

    assert report["gate"] == "RED"
    assert report["error"] == "encrypted_retention_failed"
    assert "sensitive provider detail" not in json.dumps(report)
    assert not (state_root / "latest_retention.json").exists()


@pytest.mark.parametrize(
    "plist_name,label",
    [
        ("com.example.daily-shipping-recovery.plist", "com.example.daily-shipping-recovery"),
        (
            "com.example.daily-shipping-recovery-retention.plist",
            "com.example.daily-shipping-recovery-retention",
        ),
    ],
)
def test_candidate_launchagents_are_inert_until_explicit_install(
    plist_name: str, label: str
) -> None:
    plist_path = PROJECT_ROOT / "config" / plist_name
    payload = plistlib.loads(plist_path.read_bytes())

    assert payload["Label"] == label
    assert payload["RunAtLoad"] is False
    assert payload["KeepAlive"] is False
    assert any(value == "1" for value in payload["EnvironmentVariables"].values())
    assert not (Path.home() / "Library" / "LaunchAgents" / plist_path.name).exists()
