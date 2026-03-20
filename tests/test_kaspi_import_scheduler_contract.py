import plistlib
from pathlib import Path

from scripts.render_launchd_plists import render_launchd_plists


def _read_kaspi_import_plist(tmp_path: Path) -> tuple[dict, Path]:
    project_root = Path(__file__).resolve().parents[1]
    report = render_launchd_plists(project_root=project_root, output_dir=tmp_path)
    plist_path = Path(report["rendered_files"]["com.example.kaspi-import.plist"])
    return plistlib.loads(plist_path.read_bytes()), project_root


def test_kaspi_import_plist_schedule_is_expected(tmp_path: Path) -> None:
    plist, _project_root = _read_kaspi_import_plist(tmp_path)
    intervals = plist.get("StartCalendarInterval", [])
    pairs = sorted((int(item["Hour"]), int(item["Minute"])) for item in intervals)
    assert pairs == [(11, 0), (16, 3)]


def test_kaspi_import_plist_uses_v2_label(tmp_path: Path) -> None:
    plist, _project_root = _read_kaspi_import_plist(tmp_path)
    assert plist.get("Label") == "com.example.kaspi-import-v2"


def test_kaspi_import_plist_uses_rendered_project_root_command_path(tmp_path: Path) -> None:
    plist, project_root = _read_kaspi_import_plist(tmp_path)
    args = plist.get("ProgramArguments", [])
    assert args[:3] == [
        "/usr/bin/env",
        "python3",
        str(project_root / "scripts" / "run_kaspi_import_scheduler.py"),
    ]


def test_kaspi_import_plist_uses_runtime_log_paths(tmp_path: Path) -> None:
    plist, project_root = _read_kaspi_import_plist(tmp_path)
    assert plist.get("StandardOutPath") == (
        str(project_root / "runtime_logs" / "kaspi_import_stdout.log")
    )
    assert plist.get("StandardErrorPath") == (
        str(project_root / "runtime_logs" / "kaspi_import_stderr.log")
    )


def test_install_scheduler_script_uses_bootstrap_and_enable() -> None:
    script = Path("scripts/install_scheduler.sh").read_text(encoding="utf-8")
    assert "render_launchd_plists.py" in script
    assert "launchctl bootout" in script
    assert "launchctl bootstrap" in script
    assert "launchctl enable" in script
    assert "com.example.kaspi-import-v2" in script
    assert "runtime_logs" in script
    assert "11:00" in script
    assert "16:03" in script
