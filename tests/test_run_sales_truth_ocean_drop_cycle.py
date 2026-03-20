from __future__ import annotations

from pathlib import Path

from scripts.run_sales_truth_ocean_drop_cycle import run_sales_truth_ocean_drop_cycle


def test_cycle_runs_all_steps_when_green(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        calls.append(cmd)
        return 0, "ok"

    report = run_sales_truth_ocean_drop_cycle(
        project_root=Path(".").resolve(),
        as_of="2026-02-26",
        output_root=tmp_path,
        strict=True,
        ocean_drop=None,
        crm_archive_lookup=None,
        window_days=14,
        runner=fake_runner,
    )

    assert report["ok"] is True
    assert len(calls) == 7
    assert "rebuild_sales_fact_v2_from_kaspi_entries.py" in calls[3]
    assert "validate_sales_truth_ocean_drop_parity.py" in calls[4]
    assert "--window-days 14" in calls[4]
    assert Path(report["json_path"]).exists()
    assert Path(report["md_path"]).exists()


def test_cycle_fails_closed_on_first_error(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        calls.append(cmd)
        if "validate_sales_truth_ocean_drop_parity.py" in cmd:
            return 1, "parity fail"
        return 0, "ok"

    report = run_sales_truth_ocean_drop_cycle(
        project_root=Path(".").resolve(),
        as_of="2026-02-26",
        output_root=tmp_path,
        strict=True,
        ocean_drop=None,
        crm_archive_lookup=None,
        window_days=14,
        runner=fake_runner,
    )

    assert report["ok"] is False
    assert report["status"] == "FAIL"
    assert report["steps"][4]["ok"] is False
    assert len(report["steps"]) == 5
