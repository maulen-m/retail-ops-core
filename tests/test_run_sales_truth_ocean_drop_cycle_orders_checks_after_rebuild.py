from __future__ import annotations

from pathlib import Path

from scripts.run_sales_truth_ocean_drop_cycle import run_sales_truth_ocean_drop_cycle


def test_cycle_runs_post_rebuild_parity_check_and_records_step(tmp_path: Path) -> None:
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

    steps = [row["step"] for row in report["steps"]]
    rebuild_idx = steps.index("rebuild_sales_fact_v2_from_kaspi_entries")
    parity_idx = steps.index("validate_sales_truth_ocean_drop_parity_post_rebuild")

    assert report["ok"] is True
    assert parity_idx > rebuild_idx
    assert any("validate_sales_truth_ocean_drop_parity.py" in cmd and "--window-days 14" in cmd for cmd in calls)
