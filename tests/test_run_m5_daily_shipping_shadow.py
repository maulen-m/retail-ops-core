from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from scripts.run_m5_daily_shipping_shadow import (
    DEFAULT_RELEASE_TAG,
    ShadowGateError,
    build_shadow_commands,
    run_shadow,
    sanitize_shadow_environment,
    verify_snapshot_transfer,
)


EXPECTED_COMMIT = "a" * 40
TAG_COMMIT = "b" * 40


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    project = tmp_path / "receiver" / "Autonomous_business"
    (project / "config").mkdir(parents=True)
    (project / "db").mkdir()
    with sqlite3.connect(project / "db" / "app.db") as connection:
        connection.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, state TEXT)")
        connection.execute("INSERT INTO orders(state) VALUES ('SHIPPED')")

    workbook = project / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
    workbook.parent.mkdir()
    with ZipFile(workbook, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")

    runtime_state = project / "runtime" / "state"
    runtime_state.mkdir(parents=True)
    (runtime_state / "waybill_shipping_obligations.json").write_text(
        '{"orders": []}\n', encoding="utf-8"
    )

    business_date = "2026-07-13"
    checkpoint = (
        project
        / "exports"
        / "google_ops_board"
        / "workflow_runs"
        / business_date
        / "closeout_checkpoint.json"
    )
    _write_json(checkpoint, {"stages": {}})

    home = tmp_path / "home"
    dotenv = project / ".env"
    dotenv.write_text("PLACEHOLDER=1\n", encoding="utf-8")
    dotenv.chmod(0o600)
    service_account = home / "Docs" / "Business" / "S" / "board.json"
    _write_json(service_account, {"placeholder": True})
    service_account.chmod(0o600)

    manifest = {
        "schema_version": 1,
        "project_root": str(project),
        "runtime_home": str(home),
        "credential_files": [
            {"path": "${PROJECT_ROOT}/.env", "required": True, "max_mode": "0600"},
            {"path": "${HOME}/Docs/Business/S/board.json", "required": True, "max_mode": "0600"},
        ],
        "schedulers": [
            {
                "label": "com.example.google-ops-board-closeout-watch",
                "environment_variables": {
                    "AB_GOOGLE_OPS_BOARD_SPREADSHEET_ID": "sheet-test-id"
                },
            },
            {"label": "com.example.waybill-telegram-control"},
        ],
    }
    manifest_path = project / "config" / "daily_shipping_runtime.json"
    _write_json(manifest_path, manifest)
    python_bin = project / ".venv" / "bin" / "python"
    python_bin.parent.mkdir(parents=True)
    python_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    python_bin.chmod(0o700)

    snapshot = tmp_path / "snapshot"
    source_db = snapshot / "data" / "app.db.sqlite"
    source_db.parent.mkdir(parents=True)
    source_db.write_bytes((project / "db" / "app.db").read_bytes())
    source_workbook = snapshot / "excel_ui" / workbook.name
    source_workbook.parent.mkdir()
    source_workbook.write_bytes(workbook.read_bytes())
    source_state = snapshot / "runtime" / "state" / "waybill_shipping_obligations.json"
    source_state.parent.mkdir(parents=True)
    source_state.write_bytes(
        (runtime_state / "waybill_shipping_obligations.json").read_bytes()
    )
    source_checkpoint = snapshot / "workflow" / "closeout_checkpoint.json"
    source_checkpoint.parent.mkdir()
    source_checkpoint.write_bytes(checkpoint.read_bytes())
    replay_dir = snapshot / "workflow" / "replay"
    _write_json(
        replay_dir / "closeout_report.json",
        {
            "ok": True,
            "mode": "apply",
            "target_date": business_date,
            "run_id": "preserved-apply-run",
        },
    )
    _write_json(
        replay_dir / "run_control_snapshot.json",
        {"target_date": business_date, "matrix": [["target_date"], [business_date]]},
    )
    _write_json(
        replay_dir / "salesraw_snapshot.json",
        {"target_date": business_date, "matrix": [["Date"], [business_date]]},
    )
    _write_json(
        replay_dir / "closeout_evidence.json",
        {
            "schema_version": 1,
            "ok": True,
            "gate": "GREEN",
            "target_date": business_date,
            "run_id": "preserved-apply-run",
            "completion_kind": "zero_order_noop",
            "expected_order_count": 0,
            "manifest_count": 0,
            "confirmed_count": 0,
            "pending_count": 0,
            "required_stage_count": 0,
            "closeout_report_sha256": _sha256(
                replay_dir / "closeout_report.json"
            ),
            "terminal_artifact_sha256": {
                "expected_orders": "1" * 64,
                "zero_order_marker": "2" * 64,
            },
            "credential_values_exposed": False,
            "customer_data_exposed": False,
            "external_writes_performed": 0,
        },
    )
    artifacts = {}
    for path in (
        source_db,
        source_workbook,
        source_state,
        source_checkpoint,
        replay_dir / "closeout_report.json",
        replay_dir / "closeout_evidence.json",
        replay_dir / "run_control_snapshot.json",
        replay_dir / "salesraw_snapshot.json",
    ):
        relative = path.relative_to(snapshot).as_posix()
        artifacts[relative] = {"sha256": _sha256(path), "size_bytes": path.stat().st_size}
    snapshot_manifest = snapshot / "snapshot_manifest.json"
    _write_json(
        snapshot_manifest,
        {
            "schema_version": 1,
            "hostname": "M1-source",
            "business_date": business_date,
            "database_quick_check": "ok",
            "artifacts": artifacts,
        },
    )
    return project, manifest_path, snapshot_manifest, home


def _runner(output_root: Path, *, dirty: bool = False, head: str = EXPECTED_COMMIT,
            tag_ancestor: bool = True, fail_stage: str = ""):
    def fake(command: list[str], **kwargs):
        joined = " ".join(command)
        if command[:3] == ["git", "status", "--porcelain"]:
            return SimpleNamespace(returncode=0, stdout=" M tracked.py\n" if dirty else "", stderr="")
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout=head + "\n", stderr="")
        if command[:2] == ["git", "rev-parse"]:
            return SimpleNamespace(returncode=0, stdout=TAG_COMMIT + "\n", stderr="")
        if command[:3] == ["git", "merge-base", "--is-ancestor"]:
            return SimpleNamespace(returncode=0 if tag_ancestor else 1, stdout="", stderr="")
        if command[:2] == ["launchctl", "list"]:
            return SimpleNamespace(returncode=0, stdout="PID\tStatus\tLabel\n", stderr="")
        stage = ""
        if "run_daily_shipping_release_gate.sh" in joined:
            stage = "release_gate"
        elif "validate_daily_shipping_runtime.py" in joined:
            stage = "runtime_credentials"
        elif "preflight_shipment.py" in joined:
            stage = "shipment_preflight"
        elif "run_google_ops_board_closeout.py" in joined:
            stage = "preserved_day_replay"
        if stage == fail_stage:
            return SimpleNamespace(
                returncode=7,
                stdout="SECRET_OUTPUT_SHOULD_NOT_LEAK",
                stderr="TOKEN_SHOULD_NOT_LEAK",
            )
        if stage == "runtime_credentials":
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({"ok": True, "credential_values_read": False}),
                stderr="",
            )
        if stage == "shipment_preflight":
            target = Path(command[command.index("--output") + 1])
            _write_json(target, {"ok": True, "exit_code": 0})
        if stage == "preserved_day_replay":
            target = Path(command[command.index("--json-out") + 1])
            _write_json(
                target,
                {
                    "ok": True,
                    "mode": "dry_run",
                    "board_source_mode": "preserved_snapshot",
                },
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    return fake


def test_snapshot_transfer_verifies_hashes_sqlite_and_workbook(tmp_path: Path) -> None:
    project, _manifest, snapshot_manifest, _home = _fixture(tmp_path)

    report = verify_snapshot_transfer(snapshot_manifest, project_root=project)

    assert report["artifact_count"] == 8
    assert report["database_quick_check"] == "ok"
    assert report["workbook_zip_ok"] is True
    assert report["closeout_evidence_gate"] == "GREEN"
    assert report["closeout_completion_kind"] == "zero_order_noop"


def test_snapshot_transfer_rejects_tampered_receiver_copy(tmp_path: Path) -> None:
    project, _manifest, snapshot_manifest, _home = _fixture(tmp_path)
    state = project / "runtime" / "state" / "waybill_shipping_obligations.json"
    tampered = bytearray(state.read_bytes())
    tampered[0] = ord("[")
    state.write_bytes(tampered)

    with pytest.raises(ShadowGateError, match="receiver SHA-256 mismatch"):
        verify_snapshot_transfer(snapshot_manifest, project_root=project)


def test_snapshot_transfer_rejects_unsafe_artifact_path(tmp_path: Path) -> None:
    project, _manifest, snapshot_manifest, _home = _fixture(tmp_path)
    payload = json.loads(snapshot_manifest.read_text(encoding="utf-8"))
    payload["artifacts"]["../escape"] = {"sha256": "0" * 64, "size_bytes": 1}
    _write_json(snapshot_manifest, payload)

    with pytest.raises(ShadowGateError, match="unsafe snapshot artifact path"):
        verify_snapshot_transfer(snapshot_manifest, project_root=project)


def test_snapshot_transfer_requires_database_and_workbook(tmp_path: Path) -> None:
    project, _manifest, snapshot_manifest, _home = _fixture(tmp_path)
    payload = json.loads(snapshot_manifest.read_text(encoding="utf-8"))
    payload["artifacts"].pop("excel_ui/SALES_KSP_CRM_V3.xlsx")
    _write_json(snapshot_manifest, payload)

    with pytest.raises(ShadowGateError, match="required snapshot artifact missing"):
        verify_snapshot_transfer(snapshot_manifest, project_root=project)


def test_snapshot_transfer_requires_preserved_board_replay(tmp_path: Path) -> None:
    project, _manifest, snapshot_manifest, _home = _fixture(tmp_path)
    payload = json.loads(snapshot_manifest.read_text(encoding="utf-8"))
    payload["artifacts"].pop("workflow/replay/closeout_evidence.json")
    _write_json(snapshot_manifest, payload)

    with pytest.raises(ShadowGateError, match="required snapshot artifact missing"):
        verify_snapshot_transfer(snapshot_manifest, project_root=project)


def test_snapshot_transfer_rejects_closeout_evidence_drift(tmp_path: Path) -> None:
    project, _manifest, snapshot_manifest, _home = _fixture(tmp_path)
    evidence_path = snapshot_manifest.parent / "workflow" / "replay" / "closeout_evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["closeout_report_sha256"] = "0" * 64
    _write_json(evidence_path, evidence)
    payload = json.loads(snapshot_manifest.read_text(encoding="utf-8"))
    payload["artifacts"]["workflow/replay/closeout_evidence.json"] = {
        "sha256": _sha256(evidence_path),
        "size_bytes": evidence_path.stat().st_size,
    }
    _write_json(snapshot_manifest, payload)

    with pytest.raises(ShadowGateError, match="closeout evidence hash"):
        verify_snapshot_transfer(snapshot_manifest, project_root=project)


def test_shadow_environment_strips_write_gates_and_secret_values() -> None:
    environment = sanitize_shadow_environment(
        {
            "HOME": "~",
            "PATH": "/usr/bin:/bin",
            "ENABLE_GOOGLE_OPS_BOARD_WRITE": "1",
            "TELEGRAM_BOT_TOKEN": "must-not-survive",
            "API_SECRET": "must-not-survive",
            "LANG": "en_US.UTF-8",
        },
        python_bin="/repo/.venv/bin/python",
    )

    assert environment["HOME"] == "~"
    assert environment["PYTHON_BIN"] == "/repo/.venv/bin/python"
    assert "ENABLE_GOOGLE_OPS_BOARD_WRITE" not in environment
    assert "TELEGRAM_BOT_TOKEN" not in environment
    assert "API_SECRET" not in environment


def test_shadow_commands_never_contain_apply_send_or_launchctl(tmp_path: Path) -> None:
    project, manifest_path, snapshot_manifest, _home = _fixture(tmp_path)
    commands = build_shadow_commands(
        project_root=project,
        manifest_path=manifest_path,
        snapshot_manifest_path=snapshot_manifest,
        output_root=tmp_path / "output",
        python_bin=project / ".venv" / "bin" / "python",
    )
    flattened = " ".join(value for stage in commands for value in stage["argv"])

    assert "--apply" not in flattened
    assert "--send" not in flattened
    assert "launchctl" not in flattened
    assert any(stage["name"] == "preserved_day_replay" for stage in commands)
    replay = next(stage for stage in commands if stage["name"] == "preserved_day_replay")
    assert "--shadow-board-run-dir" in replay["argv"]
    assert replay["argv"][replay["argv"].index("--shadow-board-run-dir") + 1] == str(
        snapshot_manifest.parent / "workflow" / "replay"
    )


def test_shadow_refuses_same_source_and_receiver_host(tmp_path: Path) -> None:
    project, manifest_path, snapshot_manifest, _home = _fixture(tmp_path)

    with pytest.raises(ShadowGateError, match="source host"):
        run_shadow(
            project_root=project,
            manifest_path=manifest_path,
            snapshot_manifest_path=snapshot_manifest,
            output_root=tmp_path / "output",
            expected_commit=EXPECTED_COMMIT,
            receiver_hostname="M1-source",
            required_runtime_root=project,
            runner=_runner(tmp_path / "output"),
        )


def test_shadow_refuses_noncanonical_runtime_path(tmp_path: Path) -> None:
    project, manifest_path, snapshot_manifest, _home = _fixture(tmp_path)

    with pytest.raises(ShadowGateError, match="runtime path mismatch"):
        run_shadow(
            project_root=project,
            manifest_path=manifest_path,
            snapshot_manifest_path=snapshot_manifest,
            output_root=tmp_path / "output",
            expected_commit=EXPECTED_COMMIT,
            receiver_hostname="M5-target",
            required_runtime_root=tmp_path / "different-root",
            runner=_runner(tmp_path / "output"),
        )


def test_shadow_refuses_dirty_checkout(tmp_path: Path) -> None:
    project, manifest_path, snapshot_manifest, _home = _fixture(tmp_path)

    with pytest.raises(ShadowGateError, match="checkout is dirty"):
        run_shadow(
            project_root=project,
            manifest_path=manifest_path,
            snapshot_manifest_path=snapshot_manifest,
            output_root=tmp_path / "output",
            expected_commit=EXPECTED_COMMIT,
            receiver_hostname="M5-target",
            required_runtime_root=project,
            runner=_runner(tmp_path / "output", dirty=True),
        )


def test_shadow_refuses_wrong_checkout_commit(tmp_path: Path) -> None:
    project, manifest_path, snapshot_manifest, _home = _fixture(tmp_path)

    with pytest.raises(ShadowGateError, match="checkout commit mismatch"):
        run_shadow(
            project_root=project,
            manifest_path=manifest_path,
            snapshot_manifest_path=snapshot_manifest,
            output_root=tmp_path / "output",
            expected_commit=EXPECTED_COMMIT,
            receiver_hostname="M5-target",
            required_runtime_root=project,
            runner=_runner(tmp_path / "output", head="c" * 40),
        )


def test_shadow_requires_release_tag_to_be_ancestor(tmp_path: Path) -> None:
    project, manifest_path, snapshot_manifest, _home = _fixture(tmp_path)

    with pytest.raises(ShadowGateError, match="release tag is not an ancestor"):
        run_shadow(
            project_root=project,
            manifest_path=manifest_path,
            snapshot_manifest_path=snapshot_manifest,
            output_root=tmp_path / "output",
            expected_commit=EXPECTED_COMMIT,
            receiver_hostname="M5-target",
            required_runtime_root=project,
            runner=_runner(tmp_path / "output", tag_ancestor=False),
        )


def test_shadow_refuses_any_loaded_shipping_label(tmp_path: Path) -> None:
    project, manifest_path, snapshot_manifest, _home = _fixture(tmp_path)

    with pytest.raises(ShadowGateError, match="shipping labels already loaded"):
        run_shadow(
            project_root=project,
            manifest_path=manifest_path,
            snapshot_manifest_path=snapshot_manifest,
            output_root=tmp_path / "output",
            expected_commit=EXPECTED_COMMIT,
            receiver_hostname="M5-target",
            required_runtime_root=project,
            launchctl_output="-\t0\tcom.example.waybill-telegram-control\n",
            runner=_runner(tmp_path / "output"),
        )


def test_shadow_rejects_loose_credential_permissions(tmp_path: Path) -> None:
    project, manifest_path, snapshot_manifest, _home = _fixture(tmp_path)
    (project / ".env").chmod(0o644)

    with pytest.raises(ShadowGateError, match="credential mode exceeds"):
        run_shadow(
            project_root=project,
            manifest_path=manifest_path,
            snapshot_manifest_path=snapshot_manifest,
            output_root=tmp_path / "output",
            expected_commit=EXPECTED_COMMIT,
            receiver_hostname="M5-target",
            required_runtime_root=project,
            runner=_runner(tmp_path / "output"),
        )


def test_shadow_refuses_output_inside_repo(tmp_path: Path) -> None:
    project, manifest_path, snapshot_manifest, _home = _fixture(tmp_path)

    with pytest.raises(ShadowGateError, match="output root must be outside"):
        run_shadow(
            project_root=project,
            manifest_path=manifest_path,
            snapshot_manifest_path=snapshot_manifest,
            output_root=project / "shadow-output",
            expected_commit=EXPECTED_COMMIT,
            receiver_hostname="M5-target",
            required_runtime_root=project,
            runner=_runner(project / "shadow-output"),
        )


def test_full_shadow_run_writes_owner_only_green_report(tmp_path: Path) -> None:
    project, manifest_path, snapshot_manifest, _home = _fixture(tmp_path)
    output_root = tmp_path / "output"

    report = run_shadow(
        project_root=project,
        manifest_path=manifest_path,
        snapshot_manifest_path=snapshot_manifest,
        output_root=output_root,
        expected_commit=EXPECTED_COMMIT,
        receiver_hostname="M5-target",
        required_runtime_root=project,
        runner=_runner(output_root),
    )

    persisted = json.loads((output_root / "shadow_report.json").read_text(encoding="utf-8"))
    assert report["gate"] == "GREEN"
    assert report["external_writes_performed"] == 0
    assert report["credential_values_read"] is True
    assert report["credential_values_read_by_wrapper"] is False
    assert report["credential_values_exposed"] is False
    assert report["cutover_authorized"] is False
    assert persisted == report
    assert output_root.stat().st_mode & 0o777 == 0o700
    assert (output_root / "shadow_report.json").stat().st_mode & 0o777 == 0o600
    assert [stage["name"] for stage in report["stages"]] == [
        "release_gate",
        "runtime_credentials",
        "shipment_preflight",
        "preserved_day_replay",
    ]


def test_failed_subprocess_is_redacted_and_reported_red(tmp_path: Path) -> None:
    project, manifest_path, snapshot_manifest, _home = _fixture(tmp_path)
    output_root = tmp_path / "output"

    report = run_shadow(
        project_root=project,
        manifest_path=manifest_path,
        snapshot_manifest_path=snapshot_manifest,
        output_root=output_root,
        expected_commit=EXPECTED_COMMIT,
        receiver_hostname="M5-target",
        required_runtime_root=project,
        runner=_runner(output_root, fail_stage="shipment_preflight"),
    )
    serialized = json.dumps(report)

    assert report["gate"] == "RED"
    assert report["stages"][-1]["returncode"] == 7
    assert "SECRET_OUTPUT_SHOULD_NOT_LEAK" not in serialized
    assert "TOKEN_SHOULD_NOT_LEAK" not in serialized
    assert report["external_writes_performed"] == 0


def test_default_release_anchor_is_v22() -> None:
    assert DEFAULT_RELEASE_TAG == "release/daily-shipping-20260713-v2.2"
