import plistlib
from pathlib import Path

from scripts.render_launchd_plists import render_launchd_plists


def _read_waybill_deadline_plist(tmp_path: Path) -> tuple[dict, Path]:
    project_root = Path(__file__).resolve().parents[1]
    report = render_launchd_plists(project_root=project_root, output_dir=tmp_path)
    plist_path = Path(report["rendered_files"]["com.example.kaspi-waybill-deadline.plist"])
    return plistlib.loads(plist_path.read_bytes()), project_root


def test_waybill_deadline_plist_schedule_is_expected(tmp_path: Path) -> None:
    plist, _project_root = _read_waybill_deadline_plist(tmp_path)
    interval = plist.get("StartCalendarInterval", {})
    assert int(interval.get("Hour", -1)) == 18
    assert int(interval.get("Minute", -1)) == 30


def test_waybill_deadline_plist_runs_merged_build_waybills_command(tmp_path: Path) -> None:
    plist, project_root = _read_waybill_deadline_plist(tmp_path)
    args = plist.get("ProgramArguments", [])
    assert args[:2] == ["/bin/bash", str(project_root / "excel_ui" / "run_merged_build_waybills.command")]
    assert plist.get("Label") == "com.example.kaspi-waybill-deadline"
    assert plist.get("WorkingDirectory") == str(project_root)


def test_install_scheduler_mentions_waybill_deadline_job() -> None:
    script = Path("scripts/install_scheduler.sh").read_text(encoding="utf-8")
    assert "render_launchd_plists.py" in script
    assert "com.example.kaspi-waybill-deadline" in script
    assert "18:30" in script
