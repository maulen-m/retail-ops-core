from pathlib import Path


def test_runner_invokes_run_full_import_command_with_project_root() -> None:
    script = Path("scripts/run_kaspi_import_scheduler.py").read_text(encoding="utf-8")
    assert "PROJECT_ROOT = Path(__file__).resolve().parents[1]" in script
    assert 'COMMAND_PATH = PROJECT_ROOT / "excel_ui" / "run_full_import.command"' in script
    assert 'DB_CHECK_PATH = PROJECT_ROOT / "scripts" / "check_local_app_db.py"' in script
    assert '--db-path' in script
    assert 'ERROR: local DB preflight failed; skipping scheduled import.' in script
    assert 'subprocess.run(["/bin/bash", str(command_path)]' in script
