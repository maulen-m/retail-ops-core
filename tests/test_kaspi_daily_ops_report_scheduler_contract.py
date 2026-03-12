import plistlib
from pathlib import Path

from scripts.render_launchd_plists import render_launchd_plists


def _read_daily_ops_report_plist(tmp_path: Path) -> tuple[dict, Path]:
    project_root = Path(__file__).resolve().parents[1]
    report = render_launchd_plists(project_root=project_root, output_dir=tmp_path)
    plist_path = Path(report["rendered_files"]["com.example.kaspi-daily-ops-report.plist"])
    return plistlib.loads(plist_path.read_bytes()), project_root


def test_daily_ops_report_plist_contract(tmp_path: Path) -> None:
    plist, project_root = _read_daily_ops_report_plist(tmp_path)
    assert plist.get("Label") == "com.example.kaspi-daily-ops-report"

    interval = plist.get("StartCalendarInterval", {})
    assert int(interval.get("Hour", -1)) == 19
    assert int(interval.get("Minute", -1)) == 10

    args = plist.get("ProgramArguments", [])
    assert args[0] == str(project_root / ".venv" / "bin" / "python")
    assert args[1] == str(project_root / "scripts" / "run_kaspi_daily_ops_report_scheduler.py")
    assert "/usr/bin/env" not in args


def test_install_scheduler_mentions_daily_ops_report_job() -> None:
    script = Path("scripts/install_scheduler.sh").read_text(encoding="utf-8")
    assert "render_launchd_plists.py" in script
    assert "com.example.kaspi-daily-ops-report" in script
    assert "19:10" in script
