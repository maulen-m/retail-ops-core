from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts.verify_daily_shipping_closeout import (
    CloseoutEvidenceError,
    STAGE_ORDER,
    _resolve_delivery_pin,
    _resolve_stage_evidence,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _resumed_fixture(tmp_path: Path) -> tuple[dict, Path, Path, str]:
    target = "2026-07-15"
    workflow_root = tmp_path / "workflow_runs"
    prior_run_id = "20260715_192512_2026-07-15_closeout"
    current_run_id = "20260715_192722_2026-07-15_closeout"
    prior_run = workflow_root / target / prior_run_id
    current_run = workflow_root / target / current_run_id
    resumed = STAGE_ORDER[:4]
    checkpoint_stages: dict[str, dict] = {}
    steps: list[dict] = []
    for stage in STAGE_ORDER:
        source_run = prior_run if stage in resumed else current_run
        step_path = source_run / f"step_{stage}.json"
        _write_json(
            step_path,
            {"name": stage, "ok": True, "returncode": 0},
        )
        step = {"name": stage, "ok": True, "returncode": 0}
        if stage in resumed:
            step["from_checkpoint"] = True
            checkpoint_stages[stage] = {
                "status": "ok",
                "execution_mode": "apply",
                "run_id": prior_run_id,
                "run_dir": str(prior_run),
                "step_report_path": str(step_path),
            }
        steps.append(step)
    checkpoint_path = workflow_root / target / "closeout_checkpoint.json"
    _write_json(
        checkpoint_path,
        {
            "target_date": target,
            "execution_mode": "apply",
            "stages": checkpoint_stages,
        },
    )
    closeout = {
        "checkpoint_path": str(checkpoint_path),
        "resumed_from_checkpoint": True,
        "resumed_stages": list(resumed),
        "steps": steps,
    }
    return closeout, current_run, workflow_root, target


def test_resumed_stage_evidence_resolves_exact_checkpoint_sources(tmp_path: Path) -> None:
    closeout, current_run, workflow_root, target = _resumed_fixture(tmp_path)

    checkpoint, stage_dirs, step_hashes = _resolve_stage_evidence(
        closeout=closeout,
        run_dir=current_run,
        workflow_root=workflow_root,
        target=target,
    )

    assert checkpoint is not None
    assert stage_dirs["size_writeback"].name == "20260715_192512_2026-07-15_closeout"
    assert stage_dirs["delivery_send"] == current_run.resolve()
    assert set(step_hashes) == set(STAGE_ORDER)


@pytest.mark.parametrize(
    ("mutator", "error"),
    [
        (
            lambda payload, _current, _workflow: payload.__setitem__(
                "resumed_stages", ["size_writeback", "download_waybills"]
            ),
            "contiguous stage prefix",
        ),
        (
            lambda payload, _current, _workflow: payload["steps"][0].pop(
                "from_checkpoint"
            ),
            "provenance disagrees",
        ),
        (
            lambda payload, _current, workflow: payload.__setitem__(
                "checkpoint_path", str(workflow / "other_checkpoint.json")
            ),
            "canonical closeout checkpoint",
        ),
    ],
)
def test_resumed_stage_evidence_fails_closed_on_provenance_drift(
    tmp_path: Path,
    mutator,
    error: str,
) -> None:
    closeout, current_run, workflow_root, target = _resumed_fixture(tmp_path)
    closeout = copy.deepcopy(closeout)
    mutator(closeout, current_run, workflow_root)

    with pytest.raises(CloseoutEvidenceError, match=error):
        _resolve_stage_evidence(
            closeout=closeout,
            run_dir=current_run,
            workflow_root=workflow_root,
            target=target,
        )


def test_resumed_stage_evidence_rejects_checkpoint_source_run_path_drift(
    tmp_path: Path,
) -> None:
    closeout, current_run, workflow_root, target = _resumed_fixture(tmp_path)
    checkpoint_path = Path(closeout["checkpoint_path"])
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint["stages"]["shipping"]["run_dir"] = str(
        workflow_root / target / "different_run"
    )
    _write_json(checkpoint_path, checkpoint)

    with pytest.raises(CloseoutEvidenceError, match="shipping source run directory"):
        _resolve_stage_evidence(
            closeout=closeout,
            run_dir=current_run,
            workflow_root=workflow_root,
            target=target,
        )


def _attach_future_resumed_evidence(closeout: dict, current_run: Path) -> Path:
    checkpoint_path = Path(closeout["checkpoint_path"])
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    for step in closeout["steps"]:
        if step.get("from_checkpoint"):
            step["checkpoint_source"] = {
                "run_id": checkpoint["stages"][step["name"]]["run_id"]
            }
    evidence_path = current_run / "resumed_checkpoint_evidence.json"
    _write_json(
        evidence_path,
        {
            "schema_version": 1,
            "target_date": checkpoint["target_date"],
            "execution_mode": "apply",
            "checkpoint_path": str(checkpoint_path.resolve()),
            "checkpoint_sha256": hashlib.sha256(checkpoint_path.read_bytes()).hexdigest(),
            "resumed_stages": closeout["resumed_stages"],
            "stage_sources": {
                stage: checkpoint["stages"][stage]
                for stage in closeout["resumed_stages"]
            },
            "required_orders": checkpoint.get("required_orders") or {},
            "delivery_artifacts": checkpoint.get("delivery_artifacts") or {},
            "run_control_resume_fingerprint": checkpoint.get(
                "run_control_resume_fingerprint"
            )
            or "",
        },
    )
    closeout["resumed_checkpoint_evidence_path"] = str(evidence_path)
    closeout["resumed_checkpoint_evidence_sha256"] = hashlib.sha256(
        evidence_path.read_bytes()
    ).hexdigest()
    return evidence_path


def test_future_resumed_evidence_is_hash_and_checkpoint_bound(tmp_path: Path) -> None:
    closeout, current_run, workflow_root, target = _resumed_fixture(tmp_path)
    evidence_path = _attach_future_resumed_evidence(closeout, current_run)

    _resolve_stage_evidence(
        closeout=closeout,
        run_dir=current_run,
        workflow_root=workflow_root,
        target=target,
    )

    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence["delivery_artifacts"] = {"manifest_sha256": "different"}
    _write_json(evidence_path, evidence)
    closeout["resumed_checkpoint_evidence_sha256"] = hashlib.sha256(
        evidence_path.read_bytes()
    ).hexdigest()
    with pytest.raises(CloseoutEvidenceError, match="resumed evidence delivery pin"):
        _resolve_stage_evidence(
            closeout=closeout,
            run_dir=current_run,
            workflow_root=workflow_root,
            target=target,
        )


def test_future_resumed_evidence_rejects_file_hash_drift(tmp_path: Path) -> None:
    closeout, current_run, workflow_root, target = _resumed_fixture(tmp_path)
    evidence_path = _attach_future_resumed_evidence(closeout, current_run)
    evidence_path.write_text(evidence_path.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(CloseoutEvidenceError, match="evidence SHA-256 mismatch"):
        _resolve_stage_evidence(
            closeout=closeout,
            run_dir=current_run,
            workflow_root=workflow_root,
            target=target,
        )


def test_report_delivery_pin_must_equal_checkpoint_pin() -> None:
    with pytest.raises(CloseoutEvidenceError, match="report/checkpoint"):
        _resolve_delivery_pin(
            closeout={"pinned_delivery_artifacts": {"manifest_sha256": "report"}},
            checkpoint={"delivery_artifacts": {"manifest_sha256": "checkpoint"}},
        )
