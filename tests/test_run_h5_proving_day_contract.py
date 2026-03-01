from __future__ import annotations

import json
from pathlib import Path

from scripts.run_h5_proving_day import run_h5_proving_day


def test_run_h5_proving_day_runs_required_chain(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        calls.append(cmd)
        return 0, "ok"

    report = run_h5_proving_day(
        project_root=tmp_path,
        as_of="2026-02-26",
        output_root=tmp_path / "exports" / "validation" / "h5",
        strict=True,
        runner=fake_runner,
    )
    assert report["ok"] is True
    assert report["status"] == "PASS"
    joined = "\n".join(calls)
    assert "system_doctor.py" in joined
    assert "validate_as_of_consistency.py" in joined
    assert "validate_business_insides_economics_ready.py" in joined
    assert "validate_ops_selection_parity.py" in joined
    assert "validate_scheduler_heartbeat.py" in joined
    assert "validate_kaspi_archive_pack_integrity.py --source ui" in joined
    assert "run_sales_truth_ocean_drop_cycle.py" in joined
    assert "triage_exceptions.py" in joined
    assert "validate_h5_artifact_set.py" in joined

    summary_json = tmp_path / "exports" / "validation" / "h5" / "2026-02-26" / "h5_proving_day_summary.json"
    assert summary_json.exists()
    payload = json.loads(summary_json.read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"


def test_run_h5_proving_day_fails_closed_on_first_error(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        calls.append(cmd)
        if "validate_as_of_consistency.py" in cmd:
            return 1, "mismatch"
        return 0, "ok"

    report = run_h5_proving_day(
        project_root=tmp_path,
        as_of="2026-02-26",
        output_root=tmp_path / "exports" / "validation" / "h5",
        strict=True,
        runner=fake_runner,
    )
    assert report["ok"] is False
    assert report["status"] == "FAIL"
    assert report["exit_code"] == 1
    assert any("validate_as_of_consistency.py" in cmd for cmd in calls)
    assert all("triage_exceptions.py" not in cmd for cmd in calls), "chain must stop on first failure"
