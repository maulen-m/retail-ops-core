from __future__ import annotations

import json
from pathlib import Path

from scripts.build_green_streak_tracker import build_green_streak_tracker


def _write_daily_report(root: Path, day_iso: str, ok: bool) -> None:
    day_dir = root / day_iso
    day_dir.mkdir(parents=True, exist_ok=True)
    payload = {"as_of": day_iso, "status": "GREEN" if ok else "RED", "ok": ok}
    (day_dir / "daily_ops_report.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_gate_transcript(root: Path, board_name: str, day_iso: str) -> None:
    path = root / f"{board_name}_{day_iso}" / "full_gates_green_final.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("PASS", encoding="utf-8")


def test_green_streak_tracker_counts_consecutive_green_days(tmp_path: Path) -> None:
    daily = tmp_path / "daily"
    validation = tmp_path / "validation"
    output = tmp_path / "streak"

    _write_daily_report(daily, "2026-02-24", True)
    _write_daily_report(daily, "2026-02-25", True)
    _write_daily_report(daily, "2026-02-26", True)
    _write_gate_transcript(validation, "board_v8", "2026-02-24")
    _write_gate_transcript(validation, "board_v9", "2026-02-25")
    _write_gate_transcript(validation, "board_v10", "2026-02-26")

    report = build_green_streak_tracker(
        as_of="2026-02-26",
        daily_root=daily,
        validation_root=validation,
        output_root=output,
        strict=True,
    )
    assert report["ok"] is True
    assert report["payload"]["streak_days"] == 3


def test_green_streak_tracker_fails_when_gate_transcript_missing(tmp_path: Path) -> None:
    daily = tmp_path / "daily"
    validation = tmp_path / "validation"
    output = tmp_path / "streak"
    _write_daily_report(daily, "2026-02-26", True)

    report = build_green_streak_tracker(
        as_of="2026-02-26",
        daily_root=daily,
        validation_root=validation,
        output_root=output,
        strict=True,
    )
    assert report["ok"] is False
    assert report["exit_code"] == 1
    assert "missing full_gates_green_final.md" in "\n".join(report["payload"]["errors"])
