from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import scripts.run_end_of_day as eod
from scripts.run_end_of_day import DryRunTracker, build_run_tracker


def test_dry_run_tracker_is_memory_only(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    monkeypatch.setattr("scripts.run_end_of_day.DB_PATH", db_path)

    tracker = build_run_tracker(SimpleNamespace(dry_run=True))
    tracker.start()
    tracker.start_step("validate_params")
    tracker.complete_step()
    tracker.add_output_file("exports/example.json")
    tracker.fail_step("retained blocker")
    tracker.fail("dry-run failed")

    assert isinstance(tracker, DryRunTracker)
    assert tracker.run_id == "dry-run"
    assert tracker.to_summary()["steps_completed"] == 1
    assert not db_path.exists()


def test_pipeline_passes_current_validation_as_of_and_api_dry_run(monkeypatch):
    captured = []

    def fake_run_step(step, dry_run=False, verbose=False):
        captured.append(
            {
                "script": step.script,
                "args": list(step.args),
                "dry_run_args": list(step.dry_run_args or []),
                "dry_run": dry_run,
            }
        )
        step.success = True
        step.duration_s = 0.0
        return True

    monkeypatch.setattr(eod, "run_step", fake_run_step)
    monkeypatch.setattr(eod, "get_cutoff_date_almaty", lambda: date(2026, 6, 13))
    monkeypatch.setattr(eod, "get_validation_date_almaty", lambda: date(2026, 6, 14))

    args = SimpleNamespace(
        dry_run=True,
        skip_sync=True,
        skip_api_sync=False,
        skip_day_complete=True,
        skip_workbook_sync=True,
        workbook=Path("unused.xlsx"),
        auto_assign_sizes=False,
        size_store=None,
        api_lookback_days=13,
        po4_inbound=None,
        sync_opex=False,
        opex_xlsx=None,
        verbose=False,
        continue_on_error=False,
    )

    assert eod._run_pipeline(args, datetime(2026, 6, 14, 14, 0, 0)) == 0

    validate_step = next(row for row in captured if row["script"] == "validate_params.py")
    assert validate_step["args"] == ["--strict", "--as-of", "2026-06-14"]

    sync_step = next(row for row in captured if row["script"] == "sync_kaspi_orders.py")
    assert sync_step["dry_run"] is True
    assert sync_step["dry_run_args"] == ["--dry-run"]
