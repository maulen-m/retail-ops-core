from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validate_h5_artifact_set import validate_h5_artifact_set


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _seed_daily_artifacts(root: Path, as_of: str) -> None:
    _write_json(root / "exports" / "daily" / as_of / "daily_ops_report.json", {"as_of": as_of})
    _write_json(root / "exports" / "daily" / as_of / "sales_vs_waybill_parity.json", {"as_of": as_of})
    _write_json(root / "exports" / "exceptions" / as_of / "exceptions.json", {"as_of": as_of})
    _write_json(root / "exports" / "diagnostics" / as_of / "system_health.json", {"as_of": as_of})
    _write_json(root / "exports" / "perf" / as_of / "daily_ops_timings.json", {"as_of": as_of})
    _write_json(root / "exports" / "daily" / as_of / "truth_drift_report.json", {"as_of": as_of})


def test_h5_artifact_set_passes_without_weekly_requirement(tmp_path: Path) -> None:
    as_of = "2026-02-26"
    _seed_daily_artifacts(tmp_path, as_of)

    report = validate_h5_artifact_set(
        project_root=tmp_path,
        as_of=as_of,
        output_root=tmp_path / "exports" / "validation" / "h5",
        require_weekly=False,
        strict=True,
    )
    assert report["ok"] is True
    assert report["status"] == "PASS"


def test_h5_artifact_set_fails_closed_on_missing_required_artifact(tmp_path: Path) -> None:
    as_of = "2026-02-26"
    _seed_daily_artifacts(tmp_path, as_of)
    (tmp_path / "exports" / "perf" / as_of / "daily_ops_timings.json").unlink()

    with pytest.raises(RuntimeError, match="h5 artifact-set validation failed"):
        validate_h5_artifact_set(
            project_root=tmp_path,
            as_of=as_of,
            output_root=tmp_path / "exports" / "validation" / "h5",
            require_weekly=False,
            strict=True,
        )


def test_h5_artifact_set_fails_on_asof_mismatch(tmp_path: Path) -> None:
    as_of = "2026-02-26"
    _seed_daily_artifacts(tmp_path, as_of)
    _write_json(
        tmp_path / "exports" / "exceptions" / as_of / "exceptions.json",
        {"as_of": "2026-02-25"},
    )

    with pytest.raises(RuntimeError, match="h5 artifact-set validation failed"):
        validate_h5_artifact_set(
            project_root=tmp_path,
            as_of=as_of,
            output_root=tmp_path / "exports" / "validation" / "h5",
            require_weekly=False,
            strict=True,
        )


def test_h5_artifact_set_weekly_requirement_enforced(tmp_path: Path) -> None:
    as_of = "2026-02-26"
    _seed_daily_artifacts(tmp_path, as_of)
    week_key = "2026-W09"
    _write_json(
        tmp_path / "exports" / "health" / "weekly" / week_key / "weekly_health_scorecard.json",
        {"as_of": as_of},
    )

    report = validate_h5_artifact_set(
        project_root=tmp_path,
        as_of=as_of,
        output_root=tmp_path / "exports" / "validation" / "h5",
        require_weekly=True,
        strict=True,
    )
    assert report["ok"] is True
    assert report["status"] == "PASS"
