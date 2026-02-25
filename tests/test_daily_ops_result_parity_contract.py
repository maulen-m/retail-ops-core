from __future__ import annotations

from pathlib import Path

from scripts.build_daily_ops_timings import build_daily_ops_timings


def test_daily_ops_result_parity_contract(tmp_path: Path) -> None:
    seq = {"n": 0}

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        seq["n"] += 1
        # deterministic output by command text, not call order
        return 0, f"ok::{cmd}"

    report = build_daily_ops_timings(
        project_root=Path(".").resolve(),
        as_of="2026-02-25",
        output_root=tmp_path,
        profile="today-fast",
        repeats=2,
        strict=True,
        runner=fake_runner,
    )
    assert report["ok"] is True
    runs = report["payload"]["runs"]
    assert len(runs) == 2

    first_steps = {row["step"]: row["summary"] for row in runs[0]["steps"]}
    second_steps = {row["step"]: row["summary"] for row in runs[1]["steps"]}
    assert first_steps == second_steps

