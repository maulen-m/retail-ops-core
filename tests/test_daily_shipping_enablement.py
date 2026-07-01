from __future__ import annotations

import json
import subprocess
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts import run_daily_shipping_enablement as enablement


ALMATY_TZ = ZoneInfo("Asia/Almaty")


def _completed(command: list[str], returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, returncode, stdout="ok\n", stderr="")


def test_enable_commands_split_resume_from_post_cutoff_validation(tmp_path: Path) -> None:
    commands = enablement.enable_commands(tmp_path, apply=True)
    labels = [label for label, _command in commands]

    assert labels == [
        "status_daily_ops",
        "resume_daily_ops_dry_run",
        "resume_daily_ops_apply",
        "verify_daily_ops_running",
    ]
    assert commands[0][1][1].endswith("scripts/manage_business_automation.py")
    assert commands[2][1][2:6] == ["resume", "--scope", "daily-ops", "--apply"]
    assert "sync_google_ops_board.py" not in " ".join(" ".join(command) for _label, command in commands)
    assert "run_kaspi_import_scheduler.py" not in " ".join(" ".join(command) for _label, command in commands)


def test_enable_dry_run_does_not_include_apply_or_verify(tmp_path: Path) -> None:
    commands = enablement.enable_commands(tmp_path, apply=False)
    labels = [label for label, _command in commands]

    assert labels == ["status_daily_ops", "resume_daily_ops_dry_run"]
    assert all("--apply" not in command for _label, command in commands)


def test_seconds_until_cutoff_includes_settle_window() -> None:
    current = datetime(2026, 6, 20, 16, 59, 0, tzinfo=ALMATY_TZ)

    wait = enablement.seconds_until_cutoff(
        current=current,
        target_date=date(2026, 6, 20),
        hour=17,
        minute=0,
        settle_seconds=180,
    )

    assert wait == 240


def test_validate_defers_before_cutoff_without_running_commands(tmp_path: Path, monkeypatch) -> None:
    args = enablement.build_parser().parse_args(
        [
            "--output-root",
            str(tmp_path),
            "--target-date",
            "2026-06-20",
            "--settle-seconds",
            "180",
            "--output-json",
            str(tmp_path / "validate.json"),
            "validate",
        ]
    )
    monkeypatch.setattr(
        enablement,
        "now_almaty",
        lambda: datetime(2026, 6, 20, 16, 59, 0, tzinfo=ALMATY_TZ),
    )

    def fail_runner(command, env=None):
        raise AssertionError(f"runner should not be called before cutoff: {command}")

    assert enablement.run_validate(args, runner=fail_runner) == 0

    payload = json.loads((tmp_path / "validate.json").read_text(encoding="utf-8"))
    assert payload["status"] == "DEFER_UNTIL_POST_CUTOFF"
    assert payload["seconds_until_post_cutoff"] == 240


def test_run_enable_records_fast_resume_evidence(tmp_path: Path, monkeypatch) -> None:
    args = enablement.build_parser().parse_args(
        [
            "--output-root",
            str(tmp_path),
            "--target-date",
            "2026-06-20",
            "--output-json",
            str(tmp_path / "enable.json"),
            "enable",
            "--apply",
        ]
    )
    calls: list[list[str]] = []
    monkeypatch.setattr(
        enablement,
        "now_almaty",
        lambda: datetime(2026, 6, 20, 15, 0, 0, tzinfo=ALMATY_TZ),
    )

    def runner(command, env=None):
        calls.append(list(command))
        return _completed(command)

    assert enablement.run_enable(args, runner=runner) == 0

    payload = json.loads((tmp_path / "enable.json").read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["action"] == "enable"
    assert payload["post_cutoff_validation_not_before"] == "2026-06-20T17:03:00+05:00"
    assert len(payload["commands"]) == 4
    assert any("--apply" in command for command in calls)


def test_validation_commands_are_read_only_post_cutoff_checks(tmp_path: Path) -> None:
    commands = enablement.validation_commands(tmp_path, target_date=date(2026, 6, 20), lookback_days=5)
    joined = "\n".join(" ".join(command) for _label, command in commands)

    assert "run_google_ops_board_prewindow_health.py" in joined
    assert "--profile closeout" in joined
    assert "sync_google_ops_board.py" in joined
    assert "--validate-only" in joined
    assert "report_import_status.py" not in joined
    assert "evaluate_import_run_result.py" not in joined
    assert "SALES_KSP_CRM_V3.xlsx" not in joined
    assert "--apply" not in joined


def test_validation_commands_pass_service_account_when_provided(tmp_path: Path) -> None:
    service_account = tmp_path / "service-account.json"
    commands = enablement.validation_commands(
        tmp_path,
        target_date=date(2026, 6, 20),
        lookback_days=5,
        service_account_json=service_account,
    )
    joined = "\n".join(" ".join(command) for _label, command in commands)

    assert joined.count("--service-account-json") == 2
    assert str(service_account) in joined


def test_postcutoff_no_send_report_allows_confirmed_telegram_delivery(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(enablement, "PROJECT_ROOT", tmp_path)
    send_dir = (
        tmp_path
        / "excel_ui"
        / "Kaspi_orders"
        / "Today"
        / "MERGED"
        / "SEND"
        / "20.06.26_MERGED_qnt5"
    )
    send_dir.mkdir(parents=True)
    seen: dict[str, object] = {}

    def fake_delivery_completion_state(**kwargs):
        seen.update(kwargs)
        return {
            "completed": True,
            "status": "TELEGRAM_CONFIRMED",
            "channel": "telegram",
            "manifest_count": 3,
            "confirmed_count": 3,
            "pending_count": 0,
        }

    monkeypatch.setattr(enablement, "delivery_completion_state", fake_delivery_completion_state)

    report = enablement.build_no_send_no_autofill_report(
        target_date=date(2026, 6, 20),
        run_dir=tmp_path / "run",
    )

    assert report["today_send_batch_dir_count"] == 1
    assert report["premature_telegram_send_detected"] is False
    assert report["telegram_delivery_completion"]["status"] == "TELEGRAM_CONFIRMED"
    assert seen["target_date"] == date(2026, 6, 20)


def test_postcutoff_no_send_report_blocks_unconfirmed_send_batch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(enablement, "PROJECT_ROOT", tmp_path)
    send_dir = (
        tmp_path
        / "excel_ui"
        / "Kaspi_orders"
        / "Today"
        / "MERGED"
        / "SEND"
        / "20.06.26_MERGED_qnt5"
    )
    send_dir.mkdir(parents=True)

    monkeypatch.setattr(
        enablement,
        "delivery_completion_state",
        lambda **_kwargs: {
            "completed": False,
            "status": "TELEGRAM_LEDGER_INCOMPLETE",
            "channel": "telegram",
            "manifest_count": 3,
            "confirmed_count": 2,
            "pending_count": 1,
        },
    )

    report = enablement.build_no_send_no_autofill_report(
        target_date=date(2026, 6, 20),
        run_dir=tmp_path / "run",
    )

    assert report["today_send_batch_dir_count"] == 1
    assert report["premature_telegram_send_detected"] is True
    assert report["telegram_delivery_completion"]["pending_count"] == 1
