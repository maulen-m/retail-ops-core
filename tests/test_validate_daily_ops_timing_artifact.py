from __future__ import annotations

import json
from pathlib import Path

from scripts import validate_daily_ops_timing_artifact as mod


def test_validate_daily_ops_timing_artifact_passes_required_shape(tmp_path: Path) -> None:
    payload = {
        "as_of": "2026-02-23",
        "profile": "today-fast",
        "runs": [
            {
                "run_id": 1,
                "total_duration_sec": 1.2,
                "steps": [
                    {"step": "anchor_health", "duration_sec": 0.1},
                    {"step": "ops_status", "duration_sec": 0.1},
                ],
            }
        ],
        "step_stats": {"anchor_health": {"avg_duration_sec": 0.1, "runs": 1}},
    }
    path = tmp_path / "benchmark_timings.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    report = mod.validate_timing_artifact(path, strict=True)

    assert report["ok"] is True
    assert report["errors"] == []


def test_validate_daily_ops_timing_artifact_flags_missing_runs(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text(json.dumps({"as_of": "2026-02-23", "profile": "today-fast"}), encoding="utf-8")

    report = mod.validate_timing_artifact(path, strict=False)

    assert report["ok"] is False
    assert any("runs" in err for err in report["errors"])
