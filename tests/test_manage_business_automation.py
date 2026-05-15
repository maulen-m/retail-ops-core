from __future__ import annotations

import json
from pathlib import Path

from scripts import manage_business_automation as mba


def _manifest(tmp_path: Path) -> dict:
    return {
        "scopes": {
            "daily-ops": {
                "labels": [
                    "com.example.kaspi-import-v2",
                    "com.example.google-ops-board-closeout-watch",
                ]
            }
        },
        "labels": [
            {
                "label": "com.example.kaspi-import-v2",
                "plist": str(tmp_path / "com.example.kaspi-import-v2.plist"),
                "group": "3_db_import_and_crm_after_no_active_proof_window",
                "purpose": "Kaspi import v2",
                "risk": [],
            },
            {
                "label": "com.example.google-ops-board-closeout-watch",
                "plist": str(tmp_path / "com.example.google-ops-board-closeout-watch.plist"),
                "group": "5_employee_writeback_and_closeout",
                "purpose": "Google Ops Board READY closeout watcher",
                "risk": [],
            },
        ],
        "protected_surfaces": [
            {
                "name": "production_db",
                "path": str(tmp_path / "app.db"),
                "sidecars": [str(tmp_path / "app.db-wal")],
            }
        ],
    }


def _runner_factory(loaded: set[str], calls: list[list[str]]):
    def runner(args: list[str]) -> dict:
        calls.append(args)
        if args[:2] == ["launchctl", "print"]:
            label = args[2].rsplit("/", 1)[1]
            if label in loaded:
                return {
                    "args": args,
                    "returncode": 0,
                    "stdout": "state = not running\nruns = 4\nlast exit code = 0\n",
                    "stderr": "",
                }
            return {"args": args, "returncode": 113, "stdout": "", "stderr": "not found"}
        if args[:2] == ["launchctl", "bootout"]:
            loaded.discard(args[2].rsplit("/", 1)[1])
            return {"args": args, "returncode": 0, "stdout": "", "stderr": ""}
        if args[:2] == ["launchctl", "bootstrap"]:
            loaded.add(args[3].split("/")[-1].removesuffix(".plist"))
            return {"args": args, "returncode": 0, "stdout": "", "stderr": ""}
        if args[:2] == ["launchctl", "enable"]:
            return {"args": args, "returncode": 0, "stdout": "", "stderr": ""}
        if args and args[0] == "lsof":
            return {"args": args, "returncode": 1, "stdout": "", "stderr": ""}
        if args == ["crontab", "-l"]:
            return {"args": args, "returncode": 1, "stdout": "", "stderr": "no crontab for user"}
        raise AssertionError(f"unexpected command: {args}")

    return runner


def test_manifest_contains_daily_ops_and_all_business_scopes() -> None:
    manifest = mba.load_manifest()

    daily = {entry.label for entry in mba.labels_for_scope(manifest, "daily-ops")}
    all_business = {entry.label for entry in mba.labels_for_scope(manifest, "all-business")}

    assert "com.example.kaspi-import-v2" in daily
    assert "com.example.google-ops-board-closeout-watch" in daily
    assert "com.example.waybill-telegram-control" in daily
    assert "com.webautomation.line61_line51_checkpoints" in all_business


def test_pause_dry_run_does_not_bootout_loaded_labels(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    calls: list[list[str]] = []
    loaded = {"com.example.kaspi-import-v2", "com.example.google-ops-board-closeout-watch"}

    code, report = mba.pause_or_resume(
        action="pause",
        manifest=manifest,
        scope="daily-ops",
        only_group=None,
        domain="gui/501",
        apply=False,
        evidence_root=tmp_path / "evidence",
        runner=_runner_factory(loaded, calls),
        environ={},
    )

    assert code == 0
    assert report["ok"] is True
    assert all(op["status"] == "dry_run_would_execute" for op in report["operations"])
    assert not any(call[:2] == ["launchctl", "bootout"] for call in calls)
    assert loaded == {"com.example.kaspi-import-v2", "com.example.google-ops-board-closeout-watch"}


def test_apply_requires_explicit_env_gate(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    calls: list[list[str]] = []
    loaded = {"com.example.kaspi-import-v2"}

    code, report = mba.pause_or_resume(
        action="pause",
        manifest=manifest,
        scope="daily-ops",
        only_group=None,
        domain="gui/501",
        apply=True,
        evidence_root=tmp_path / "evidence",
        runner=_runner_factory(loaded, calls),
        environ={},
    )

    assert code == 2
    assert report["ok"] is False
    assert report["gate"]["env_gate_set"] is False
    assert not any(call[:2] == ["launchctl", "bootout"] for call in calls)


def test_pause_apply_boots_out_loaded_labels_with_gate(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    calls: list[list[str]] = []
    loaded = {"com.example.kaspi-import-v2"}

    code, report = mba.pause_or_resume(
        action="pause",
        manifest=manifest,
        scope="daily-ops",
        only_group=None,
        domain="gui/501",
        apply=True,
        evidence_root=tmp_path / "evidence",
        runner=_runner_factory(loaded, calls),
        environ={mba.CONTROL_ENV_GATE: "1"},
    )

    assert code == 0
    assert report["ok"] is True
    assert ["launchctl", "bootout", "gui/501/com.example.kaspi-import-v2"] in calls
    assert "com.example.kaspi-import-v2" not in loaded


def test_verify_paused_requires_no_loaded_labels_no_holders_no_cron(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    calls: list[list[str]] = []

    code, report = mba.verify_state(
        manifest=manifest,
        scope="daily-ops",
        only_group=None,
        domain="gui/501",
        expect="paused",
        evidence_root=tmp_path / "evidence",
        runner=_runner_factory(set(), calls),
    )

    assert code == 0
    assert report["ok"] is True
    assert report["loaded_count"] == 0
    assert report["quiet_cron"] is True
    assert report["quiet_protected_surfaces"] is True


def test_cli_status_json_writes_output_file(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest(tmp_path)), encoding="utf-8")
    output_path = tmp_path / "status.json"
    calls: list[list[str]] = []

    code = mba.main(
        [
            "--manifest",
            str(manifest_path),
            "--scope",
            "daily-ops",
            "--output-json",
            str(output_path),
            "status",
        ],
        runner=_runner_factory({"com.example.kaspi-import-v2"}, calls),
        environ={},
    )

    assert code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["loaded_count"] == 1
    assert payload["label_count"] == 2


def test_pause_resume_runbook_and_goal_docs_are_linked() -> None:
    runbook = Path("docs/ops/BUSINESS_AUTOMATION_CONTROL_RUNBOOK.md")
    daily_sop = Path("docs/DAILY_SOP.md").read_text(encoding="utf-8")
    workflow_contract = Path("docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md").read_text(encoding="utf-8")
    strategic_goal = Path(
        "docs/parallel_runs/2026-05-04_owner_decisions_source_refresh_followup/"
        "STRATEGIC_GOAL_OPTION_B_THEN_C_20260504.md"
    ).read_text(encoding="utf-8")

    assert runbook.exists()
    runbook_text = runbook.read_text(encoding="utf-8")
    assert "scripts/manage_business_automation.py" in runbook_text
    assert "config/business_automation_manifest.json" in runbook_text
    assert "ENABLE_BUSINESS_AUTOMATION_CONTROL=1" in runbook_text
    assert "BUSINESS_AUTOMATION_CONTROL_RUNBOOK.md" in daily_sop
    assert "scripts/manage_business_automation.py" in workflow_contract
    assert "scripts/manage_business_automation.py" in strategic_goal
