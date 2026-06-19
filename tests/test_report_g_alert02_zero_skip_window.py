from __future__ import annotations

import json
from pathlib import Path

from scripts.report_g_alert02_zero_skip_window import build_zero_skip_window_report


def _write_config(tmp_path: Path, single_log: Path, residual_log: Path) -> Path:
    config = {
        "contract_id": "ALERT_ZERO_SKIP_WINDOW_V1",
        "gate_id": "G-ALERT-02",
        "repair_start_date": "2026-06-13",
        "required_days": 7,
        "post_eod_cutoff_local_time": "21:10",
        "skipped_alert_patterns": ["Telegram alert skipped"],
        "jobs": [
            {
                "job_id": "single_truth_preflight",
                "log_path": str(single_log),
                "date_patterns": [
                    "lineage_(?P<date>\\d{8})_(?P<time>\\d{6})\\.json",
                    "as_of=(?P<date>\\d{4}-\\d{2}-\\d{2})",
                ],
            },
            {
                "job_id": "on_delivery_residuals",
                "log_path": str(residual_log),
                "date_patterns": [
                    "on_delivery_residuals_(?P<date>\\d{4}-\\d{2}-\\d{2})_(?P<time>\\d{8}_\\d{6})\\.md"
                ],
            },
        ],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def _write_window_logs(single_log: Path, residual_log: Path, *, through_day: int = 19, skip_day: int | None = None) -> None:
    single_lines: list[str] = []
    residual_lines: list[str] = []
    for day in range(13, through_day + 1):
        if skip_day == day:
            single_lines.append("Telegram alert skipped: Telegram env missing")
        single_lines.append(
            f"STRICT_DAILY_PREFLIGHT FAIL: validate_params --strict rc=1 lineage=/tmp/lineage_202606{day:02d}_210020.json"
        )
        if skip_day == day:
            residual_lines.append("Telegram alert skipped: Telegram env missing")
        residual_lines.append(
            f"report=/tmp/on_delivery_residuals_2026-06-{day:02d}_202606{day:02d}_210500.md"
        )
    single_log.write_text("\n".join(single_lines) + "\n", encoding="utf-8")
    residual_log.write_text("\n".join(residual_lines) + "\n", encoding="utf-8")


def test_zero_skip_window_green_when_complete_after_cutoff(tmp_path: Path) -> None:
    single_log = tmp_path / "single.log"
    residual_log = tmp_path / "residual.log"
    _write_window_logs(single_log, residual_log)
    config = _write_config(tmp_path, single_log, residual_log)

    report = build_zero_skip_window_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-19T21:12:00+05:00",
    )

    assert report["gate"] == "GREEN"
    assert report["skipped_alert_total"] == 0
    assert report["missing_evidence_count"] == 0
    assert report["telegram_send_performed"] is False
    assert Path(report["json_path"]).exists()


def test_zero_skip_window_armed_before_cutoff_and_missing_today(tmp_path: Path) -> None:
    single_log = tmp_path / "single.log"
    residual_log = tmp_path / "residual.log"
    _write_window_logs(single_log, residual_log, through_day=18)
    config = _write_config(tmp_path, single_log, residual_log)

    report = build_zero_skip_window_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-19T20:24:00+05:00",
    )

    assert report["gate"] == "ARMED"
    assert "scheduled_evidence_missing:single_truth_preflight:2026-06-19" in report["blockers"]
    assert "scheduled_evidence_missing:on_delivery_residuals:2026-06-19" in report["blockers"]
    assert any(item.startswith("post_eod_cutoff_not_met:") for item in report["blockers"])


def test_zero_skip_window_red_on_skip_regression(tmp_path: Path) -> None:
    single_log = tmp_path / "single.log"
    residual_log = tmp_path / "residual.log"
    _write_window_logs(single_log, residual_log, skip_day=15)
    config = _write_config(tmp_path, single_log, residual_log)

    report = build_zero_skip_window_report(
        config_path=config,
        output_root=tmp_path / "out",
        as_of="2026-06-19T21:12:00+05:00",
    )

    assert report["gate"] == "RED"
    assert "skipped_alert_regression:single_truth_preflight:1" in report["blockers"]
    assert "skipped_alert_regression:on_delivery_residuals:1" in report["blockers"]
