from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.report_g_price05_fresh_backlog import build_report


def _write_run(
    run_dir: Path,
    *,
    rows: list[dict[str, object]],
    errors: int = 0,
    dry_run: bool = True,
    verify: bool = True,
    vintage_logged_rows: int | None = None,
) -> None:
    run_dir.mkdir(parents=True)
    summary = {
        "run_id": "test-run",
        "dry_run": dry_run,
        "verify": verify,
        "errors": errors,
        "api_requests": 2,
        "stores": {
            "30000001": {
                "api_sets_attempted": 0,
                "api_sets_succeeded": 0,
            }
        },
        "price_write_vintage_version": "PRICE_WRITE_VINTAGE_V1",
        "price_write_vintage_source_basis": "floor_csv:test",
        "price_write_vintage_logged_rows": len(rows) if vintage_logged_rows is None else vintage_logged_rows,
        "planned_actions_csv": str(run_dir / "planned_actions.csv"),
        "remaining_live_price_mismatches": 0,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    columns = [
        "store_name",
        "operation",
        "target_field",
        "target_value",
        "current_price",
        "live_price_target",
        "need_min",
        "need_max",
        "need_live_price",
        "source_rule",
        "stale_anchor_guard_applied",
        "live_reset_down",
        "min_reset_down",
        "vintage_ok",
        "vintage_fail_reason",
    ]
    for name in ("planned_actions.csv", "price_write_vintage_log.csv"):
        with (run_dir / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)


def _row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "store_name": "UNIVERSAL",
        "operation": "set_new_price",
        "target_field": "current_price",
        "target_value": "14990",
        "current_price": "9990",
        "live_price_target": "14990",
        "need_min": "false",
        "need_max": "false",
        "need_live_price": "true",
        "source_rule": "floor35_exact",
        "stale_anchor_guard_applied": "",
        "live_reset_down": "",
        "min_reset_down": "",
        "vintage_ok": "true",
        "vintage_fail_reason": "",
    }
    base.update(overrides)
    return base


def test_zero_backlog_fresh_scan_is_green(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_run(run_dir, rows=[])

    report = build_report(run_dir, disposition="open_backlog", output_dir=tmp_path / "out")

    assert report["gate"] == "GREEN"
    assert report["action_summary"]["planned_action_rows"] == 0
    assert report["blockers"] == []
    assert (tmp_path / "out" / "g_price05_fresh_backlog_report.json").exists()


def test_open_planned_actions_are_red_until_dispositioned(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_run(
        run_dir,
        rows=[
            _row(),
            _row(
                store_name="STORE-B",
                operation="set_min_price",
                target_field="min_price",
                need_live_price="false",
                need_min="true",
                live_price_target="",
            ),
        ],
    )

    report = build_report(run_dir, disposition="open_backlog", output_dir=tmp_path / "out")

    assert report["gate"] == "RED"
    assert report["action_summary"]["planned_action_rows"] == 2
    assert report["action_summary"]["live_price_raise_rows"] == 1
    assert report["action_summary"]["live_price_update_rows"] == 1
    assert report["action_summary"]["min_update_rows"] == 1
    assert any("fresh backlog remains open with 2 planned actions" in item for item in report["blockers"])


def test_vintage_mismatch_is_red_even_with_drop_disposition(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    _write_run(run_dir, rows=[_row(vintage_ok="false", vintage_fail_reason="stale_floor")], vintage_logged_rows=0)

    report = build_report(
        run_dir,
        disposition="formal_drop_approved",
        applied_evidence="owner decision test",
        output_dir=tmp_path / "out",
    )

    assert report["gate"] == "RED"
    assert any("vintage logged row count 0" in item for item in report["blockers"])
    assert report["action_summary"]["vintage_fail_reasons"] == {"stale_floor": 1}
