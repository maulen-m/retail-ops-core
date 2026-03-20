from __future__ import annotations

from pathlib import Path
import plistlib

from scripts.render_launchd_plists import render_launchd_plists


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_plist(path: Path) -> dict:
    return plistlib.loads(path.read_bytes())


def test_render_launchd_plists_preserves_contract_schedules(tmp_path: Path) -> None:
    report = render_launchd_plists(project_root=_repo_root(), output_dir=tmp_path)

    import_plist = _load_plist(Path(report["rendered_files"]["com.example.kaspi-import.plist"]))
    waybill_plist = _load_plist(Path(report["rendered_files"]["com.example.kaspi-waybill-deadline.plist"]))
    daily_ops_plist = _load_plist(Path(report["rendered_files"]["com.example.kaspi-daily-ops-report.plist"]))

    import_intervals = sorted(
        (int(item["Hour"]), int(item["Minute"])) for item in import_plist.get("StartCalendarInterval", [])
    )
    assert import_intervals == [(11, 0), (16, 3)]

    assert (
        int(waybill_plist["StartCalendarInterval"]["Hour"]),
        int(waybill_plist["StartCalendarInterval"]["Minute"]),
    ) == (18, 30)
    assert (
        int(daily_ops_plist["StartCalendarInterval"]["Hour"]),
        int(daily_ops_plist["StartCalendarInterval"]["Minute"]),
    ) == (19, 10)


def test_render_launchd_plists_resolves_project_root_paths(tmp_path: Path) -> None:
    project_root = _repo_root()
    report = render_launchd_plists(project_root=project_root, output_dir=tmp_path)

    import_plist = _load_plist(Path(report["rendered_files"]["com.example.kaspi-import.plist"]))
    waybill_plist = _load_plist(Path(report["rendered_files"]["com.example.kaspi-waybill-deadline.plist"]))
    daily_ops_plist = _load_plist(Path(report["rendered_files"]["com.example.kaspi-daily-ops-report.plist"]))

    assert import_plist["WorkingDirectory"] == str(project_root)
    assert import_plist["ProgramArguments"][:3] == [
        "/usr/bin/env",
        "python3",
        str(project_root / "scripts" / "run_kaspi_import_scheduler.py"),
    ]
    assert waybill_plist["ProgramArguments"][:2] == [
        "/bin/bash",
        str(project_root / "excel_ui" / "run_merged_build_waybills.command"),
    ]
    assert daily_ops_plist["ProgramArguments"][:2] == [
        str(project_root / ".venv" / "bin" / "python"),
        str(project_root / "scripts" / "run_kaspi_daily_ops_report_scheduler.py"),
    ]
    assert str(project_root / "runtime_logs" / "kaspi_import_stdout.log") == import_plist["StandardOutPath"]

