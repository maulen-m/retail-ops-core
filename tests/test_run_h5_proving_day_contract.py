from __future__ import annotations

from pathlib import Path

from scripts.run_h5_proving_day import run_h5_proving_day


def test_run_h5_proving_day_includes_ads_and_owner_pnl_steps(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        calls.append(cmd)
        return 0, "ok"

    report = run_h5_proving_day(
        project_root=Path(".").resolve(),
        as_of="2026-03-04",
        output_root=tmp_path,
        strict=True,
        runner=fake_runner,
    )
    assert report["ok"] is True
    joined = "\n".join(calls)
    assert "validate_ads_sidecar_readiness.py" in joined
    assert "build_owner_pnl_report.py" in joined


def test_run_h5_proving_day_stops_after_first_failure(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        calls.append(cmd)
        if "validate_ads_sidecar_readiness.py" in cmd:
            return 1, "status=FAIL\nerror_code=ADS_SOURCE_STALE"
        return 0, "ok"

    report = run_h5_proving_day(
        project_root=Path(".").resolve(),
        as_of="2026-03-04",
        output_root=tmp_path,
        strict=True,
        runner=fake_runner,
    )
    assert report["ok"] is False
    assert any("validate_ads_sidecar_readiness.py" in c for c in calls)
    assert all("build_owner_pnl_report.py" not in c for c in calls)
