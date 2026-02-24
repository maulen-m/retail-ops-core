from pathlib import Path
import plistlib


def _read_daily_ops_report_plist() -> dict:
    plist_path = Path("config/com.example.kaspi-daily-ops-report.plist")
    assert plist_path.exists(), "missing daily ops report launchd plist"
    return plistlib.loads(plist_path.read_bytes())


def test_daily_ops_report_plist_contract() -> None:
    plist = _read_daily_ops_report_plist()
    assert plist.get("Label") == "com.example.kaspi-daily-ops-report"

    interval = plist.get("StartCalendarInterval", {})
    assert int(interval.get("Hour", -1)) == 19
    assert int(interval.get("Minute", -1)) == 10

    args = plist.get("ProgramArguments", [])
    assert args[0] == "~/Docs/Autonomous_business/.venv/bin/python"
    assert args[1] == "~/Docs/Autonomous_business/scripts/run_kaspi_daily_ops_report_scheduler.py"
    assert "/usr/bin/env" not in args


def test_install_scheduler_mentions_daily_ops_report_job() -> None:
    script = Path("scripts/install_scheduler.sh").read_text(encoding="utf-8")
    assert "com.example.kaspi-daily-ops-report.plist" in script
    assert "com.example.kaspi-daily-ops-report" in script
    assert "19:10" in script
