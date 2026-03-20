from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.resolve_owner_truth_runtime_mode import RuntimeModeError, resolve_owner_truth_runtime_mode


def test_replay_mode_requires_existing_daily_ops_summary(tmp_path: Path) -> None:
    with pytest.raises(RuntimeModeError, match="REPLAY_DAILY_OPS_SUMMARY_MISSING"):
        resolve_owner_truth_runtime_mode(
            project_root=tmp_path,
            as_of="2026-03-08",
            mode="replay",
            strict=True,
        )


def test_replay_mode_consumes_existing_seed_when_present(tmp_path: Path) -> None:
    runtime_root = tmp_path / "exports" / "validation" / "board_v8_runtime" / "2026-03-08"
    runtime_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / "daily_ops_summary.json").write_text(
        json.dumps({"as_of": "2026-03-08", "ok": True, "status": "PASS"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (runtime_root / "ops_selection_seed.json").write_text(
        json.dumps({"as_of": "2026-03-08", "stores": {"ACMEWEAR": ["1"]}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report = resolve_owner_truth_runtime_mode(
        project_root=tmp_path,
        as_of="2026-03-08",
        mode="replay",
        strict=True,
    )

    assert report["ok"] is True
    assert report["mode"] == "replay"
    assert report["run_kaspi_daily_ops"] is False
    assert report["reuse_existing_daily_ops_summary"] is True
    assert report["use_ops_selection_seed"] is True
    assert report["blocked_inputs"] == []


def test_live_mode_forces_fresh_daily_ops_and_rejects_seed_consumption(tmp_path: Path) -> None:
    runtime_root = tmp_path / "exports" / "validation" / "board_v8_runtime" / "2026-03-09"
    runtime_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / "daily_ops_summary.json").write_text(
        json.dumps({"as_of": "2026-03-09", "ok": True, "status": "PASS"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (runtime_root / "ops_selection_seed.json").write_text(
        json.dumps({"as_of": "2026-03-09", "stores": {"ACMEWEAR": ["1"]}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report = resolve_owner_truth_runtime_mode(
        project_root=tmp_path,
        as_of="2026-03-09",
        mode="live",
        strict=True,
    )

    assert report["ok"] is True
    assert report["mode"] == "live"
    assert report["run_kaspi_daily_ops"] is True
    assert report["reuse_existing_daily_ops_summary"] is False
    assert report["use_ops_selection_seed"] is False
    assert report["blocked_inputs"] == [
        {
            "kind": "replay_only_seed",
            "path": str(runtime_root / "ops_selection_seed.json"),
            "action": "ignored_in_live_mode",
        }
    ]
