from pathlib import Path
import plistlib


def _read_kaspi_import_plist() -> dict:
    plist_path = Path("config/com.example.kaspi-import.plist")
    assert plist_path.exists(), "missing Kaspi import launchd plist"
    return plistlib.loads(plist_path.read_bytes())


def test_kaspi_import_plist_schedule_is_expected() -> None:
    plist = _read_kaspi_import_plist()
    intervals = plist.get("StartCalendarInterval", [])
    pairs = sorted((int(item["Hour"]), int(item["Minute"])) for item in intervals)
    assert pairs == [(16, 5)]


def test_kaspi_import_plist_uses_v2_label() -> None:
    plist = _read_kaspi_import_plist()
    assert plist.get("Label") == "com.example.kaspi-import-v2"


def test_kaspi_import_plist_uses_absolute_command_path() -> None:
    plist = _read_kaspi_import_plist()
    args = plist.get("ProgramArguments", [])
    assert args[:3] == [
        "/usr/bin/env",
        "python3",
        "~/Docs/Autonomous_business/scripts/run_kaspi_import_scheduler.py",
    ]


def test_kaspi_import_plist_uses_runtime_log_paths() -> None:
    plist = _read_kaspi_import_plist()
    assert plist.get("StandardOutPath") == (
        "~/Docs/Autonomous_business/runtime_logs/kaspi_import_stdout.log"
    )
    assert plist.get("StandardErrorPath") == (
        "~/Docs/Autonomous_business/runtime_logs/kaspi_import_stderr.log"
    )


def test_install_scheduler_script_uses_bootstrap_and_enable() -> None:
    script = Path("scripts/install_scheduler.sh").read_text(encoding="utf-8")
    assert "launchctl bootout" in script
    assert "launchctl bootstrap" in script
    assert "launchctl enable" in script
    assert "com.example.kaspi-import-v2" in script
    assert "runtime_logs" in script
    assert "16:05" in script
