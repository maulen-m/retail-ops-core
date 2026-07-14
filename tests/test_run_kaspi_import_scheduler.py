from pathlib import Path

from scripts import run_kaspi_import_scheduler as scheduler


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_runner_invokes_direct_source_refresh_without_crm() -> None:
    script = Path("scripts/run_kaspi_import_scheduler.py").read_text(encoding="utf-8")
    assert scheduler.PROJECT_ROOT == PROJECT_ROOT
    assert scheduler.SOURCE_REFRESH_PATH == (
        PROJECT_ROOT / "scripts" / "run_google_ops_board_publish_scheduler.py"
    )
    assert "run_full_import.command" not in script
    assert '"--force-source-refresh"' in script
