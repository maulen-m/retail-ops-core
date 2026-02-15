from pathlib import Path


def test_runner_invokes_run_full_import_command_with_project_root() -> None:
    script = Path("scripts/run_kaspi_import_scheduler.py").read_text(encoding="utf-8")
    assert 'Path("~/Docs/Autonomous_business")' in script
    assert 'Path("~/Docs/Autonomous_business/excel_ui/run_full_import.command")' in script
    assert 'subprocess.run(["/bin/bash", str(command_path)]' in script
