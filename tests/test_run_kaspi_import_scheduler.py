from pathlib import Path

from scripts import run_kaspi_import_scheduler as scheduler


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_runner_invokes_run_full_import_command_with_project_root() -> None:
    script = Path("scripts/run_kaspi_import_scheduler.py").read_text(encoding="utf-8")
    assert scheduler.PROJECT_ROOT == PROJECT_ROOT
    assert scheduler.COMMAND_PATH == PROJECT_ROOT / "excel_ui" / "run_full_import.command"
    assert scheduler.DB_CHECK_PATH == PROJECT_ROOT / "scripts" / "check_local_app_db.py"
    assert '--db-path' in script
    assert 'ERROR: local DB preflight failed; skipping scheduled import.' in script
    assert 'subprocess.run(["/bin/bash", str(command_path)]' in script
