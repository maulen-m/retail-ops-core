from pathlib import Path
import plistlib


def _read_waybill_deadline_plist() -> dict:
    plist_path = Path("config/com.example.kaspi-waybill-deadline.plist")
    assert plist_path.exists(), "missing waybill deadline launchd plist"
    return plistlib.loads(plist_path.read_bytes())


def test_waybill_deadline_plist_schedule_is_expected() -> None:
    plist = _read_waybill_deadline_plist()
    interval = plist.get("StartCalendarInterval", {})
    assert int(interval.get("Hour", -1)) == 18
    assert int(interval.get("Minute", -1)) == 30


def test_waybill_deadline_plist_runs_closeout_scheduler() -> None:
    plist = _read_waybill_deadline_plist()
    args = plist.get("ProgramArguments", [])
    assert args[:2] == [
        "~/Docs/Autonomous_business/.venv/bin/python",
        "~/Docs/Autonomous_business/scripts/run_google_ops_board_closeout_scheduler.py",
    ]
    assert plist.get("Label") == "com.example.kaspi-waybill-deadline"
    assert plist.get("WorkingDirectory") == "~/Docs/Autonomous_business"


def test_install_scheduler_mentions_waybill_deadline_job() -> None:
    script = Path("scripts/install_scheduler.sh").read_text(encoding="utf-8")
    assert "com.example.kaspi-waybill-deadline" in script
    assert "18:30" in script
