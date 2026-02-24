from __future__ import annotations

from pathlib import Path

from scripts.run_kaspi_daily_ops import run_kaspi_daily_ops


def test_orchestrator_resume_skips_successful_steps_from_checkpoint(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        calls.append(cmd)
        return 0, f"ok::{cmd}"

    checkpoint = tmp_path / "checkpoint.json"
    first = run_kaspi_daily_ops(
        project_root=Path(".").resolve(),
        as_of="2026-02-25",
        output_root=tmp_path / "runs",
        allow_store_failures=set(),
        runner=fake_runner,
        checkpoint_path=checkpoint,
        resume=False,
    )
    assert first["ok"] is True
    first_call_count = len(calls)

    calls.clear()
    second = run_kaspi_daily_ops(
        project_root=Path(".").resolve(),
        as_of="2026-02-25",
        output_root=tmp_path / "runs",
        allow_store_failures=set(),
        runner=fake_runner,
        checkpoint_path=checkpoint,
        resume=True,
    )
    assert second["ok"] is True
    assert any(step.get("from_checkpoint") for step in second["steps"])
    assert len(calls) < first_call_count


def test_orchestrator_waybill_cache_is_opt_in_and_reused(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        calls.append(cmd)
        return 0, f"ok::{cmd}"

    cache_dir = tmp_path / "cache"
    first = run_kaspi_daily_ops(
        project_root=Path(".").resolve(),
        as_of="2026-02-25",
        output_root=tmp_path / "runs",
        allow_store_failures=set(),
        runner=fake_runner,
        enable_cache=True,
        cache_dir=cache_dir,
    )
    assert first["ok"] is True
    waybill_calls_first = sum("report_waybill_status.py" in cmd for cmd in calls)
    assert waybill_calls_first > 0

    calls.clear()
    second = run_kaspi_daily_ops(
        project_root=Path(".").resolve(),
        as_of="2026-02-25",
        output_root=tmp_path / "runs",
        allow_store_failures=set(),
        runner=fake_runner,
        enable_cache=True,
        cache_dir=cache_dir,
    )
    assert second["ok"] is True
    waybill_calls_second = sum("report_waybill_status.py" in cmd for cmd in calls)
    assert waybill_calls_second == 0
    assert any(step.get("from_cache") for step in second["steps"] if step["step"].startswith("waybill_status_"))


def test_orchestrator_cache_preserves_waybill_step_parity(tmp_path: Path) -> None:
    calls: list[str] = []
    seq = {"n": 0}

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        calls.append(cmd)
        seq["n"] += 1
        return 0, f"seq={seq['n']}::{cmd}"

    cache_dir = tmp_path / "cache"
    first = run_kaspi_daily_ops(
        project_root=Path(".").resolve(),
        as_of="2026-02-25",
        output_root=tmp_path / "runs",
        allow_store_failures=set(),
        runner=fake_runner,
        enable_cache=True,
        cache_dir=cache_dir,
    )
    first_waybill = {
        step["step"]: step["summary"]
        for step in first["steps"]
        if step["step"].startswith("waybill_status_")
    }

    calls.clear()
    second = run_kaspi_daily_ops(
        project_root=Path(".").resolve(),
        as_of="2026-02-25",
        output_root=tmp_path / "runs",
        allow_store_failures=set(),
        runner=fake_runner,
        enable_cache=True,
        cache_dir=cache_dir,
    )
    second_waybill = {
        step["step"]: step["summary"]
        for step in second["steps"]
        if step["step"].startswith("waybill_status_")
    }

    assert first_waybill == second_waybill
    assert sum("report_waybill_status.py" in cmd for cmd in calls) == 0
