from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _status_path(tmp_path: Path) -> Path:
    dryrun = tmp_path / "dryrun"
    dryrun.mkdir(parents=True)
    closeout = dryrun / "closeout.md"
    log = dryrun / "wrangler_dryrun.log"
    bundle = dryrun / "bundle" / "index.js"
    bundle.parent.mkdir()
    closeout.write_text("Gate: GREEN_WRANGLER_DRY_RUN_READY_NO_DEPLOY\n", encoding="utf-8")
    log.write_text("--dry-run: exiting now.\n", encoding="utf-8")
    bundle.write_text("export default {};\n", encoding="utf-8")

    default_status = Path("docs/current/LINE31_LAUNCH_CURRENT_STATUS.json")
    status = json.loads(default_status.read_text(encoding="utf-8"))
    status["latest_web_wrangler_dryrun"] = {
        "exists": True,
        "dir": str(dryrun),
        "closeout": str(closeout),
        "gate": "GREEN_WRANGLER_DRY_RUN_READY_NO_DEPLOY",
        "log_path": str(log),
        "log_sha256": "log-sha",
        "bundle_index_path": str(bundle),
        "bundle_index_sha256": "bundle-sha",
    }
    path = tmp_path / "status.json"
    path.write_text(json.dumps(status), encoding="utf-8")
    return path


def _base_command(tmp_path: Path) -> list[str]:
    return [
        sys.executable,
        "scripts/run_line31_deploy_liveqa_readiness_sequence.py",
        "--status",
        str(_status_path(tmp_path)),
        "--output-root",
        str(tmp_path),
        "--run-id",
        "test_run",
        "--skip-live-route-probe",
        "--json",
    ]


def test_sequence_plan_mode_writes_no_external_actions(tmp_path: Path) -> None:
    completed = subprocess.run(
        _base_command(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["gate"] == "YELLOW_WAITING_FOR_EXACT_DEPLOY_LIVEQA_APPROVAL_NO_EXTERNAL_WRITE"
    assert payload["external_write_attempted"] is False
    assert payload["meta_write_attempted"] is False
    assert payload["deploy_approval_gate"]["approval_text_present"] is False
    assert payload["wrangler_dryrun"]["ready_for_deploy_package"] is True
    closeout = Path(payload["output_dir"]) / "closeout.md"
    assert closeout.exists()
    closeout_text = closeout.read_text(encoding="utf-8")
    assert "Gate: YELLOW_WAITING_FOR_EXACT_DEPLOY_LIVEQA_APPROVAL_NO_EXTERNAL_WRITE" in closeout_text
    assert "Wrangler dry-run ready: `True`" in closeout_text


def test_sequence_execute_rejects_wrong_approval_before_external_actions(tmp_path: Path) -> None:
    approval = tmp_path / "approval.txt"
    approval.write_text("not the exact phrase\n", encoding="utf-8")

    completed = subprocess.run(
        [
            *_base_command(tmp_path),
            "--execute-approved-deploy-liveqa",
            "--approval-text-file",
            str(approval),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "approval text does not exactly match" in completed.stderr
    assert not (tmp_path / "line31_deploy_liveqa_readiness_sequence_test_run").exists()
