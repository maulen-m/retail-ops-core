from __future__ import annotations

from pathlib import Path

from scripts import run_daily_autopilot as autopilot


def test_daily_autopilot_writes_exception_artifacts_on_success(tmp_path: Path, monkeypatch) -> None:
    as_of = "2026-02-26"
    summary_json = tmp_path / "exports" / "validation" / "board_v10_runtime" / as_of / "daily_ops_summary.json"
    summary_json.parent.mkdir(parents=True, exist_ok=True)
    summary_json.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        autopilot,
        "run_kaspi_daily_ops",
        lambda **_kwargs: {"ok": True, "exit_code": 0, "summary_json": str(summary_json)},
    )
    monkeypatch.setattr(
        autopilot,
        "generate_daily_ops_report",
        lambda **_kwargs: {"json_path": str(tmp_path / "exports" / "daily" / as_of / "daily_ops_report.json")},
    )
    monkeypatch.setattr(autopilot, "validate_daily_ops_report", lambda *_args, **_kwargs: {"ok": True, "errors": []})
    monkeypatch.setattr(autopilot, "build_domain_scorecards", lambda **_kwargs: {"ok": True, "exit_code": 0})
    monkeypatch.setattr(autopilot, "validate_cashfloor", lambda **_kwargs: {"ok": True, "exit_code": 0})
    monkeypatch.setattr(autopilot, "translate_transfer_ledger_to_cashflow", lambda **_kwargs: {"ok": True, "exit_code": 0})
    monkeypatch.setattr(autopilot, "build_daily_ops_timings", lambda **_kwargs: {"ok": True, "exit_code": 0})
    monkeypatch.setattr(autopilot, "build_weekly_health_scorecard", lambda **_kwargs: {"ok": True, "exit_code": 0})
    monkeypatch.setattr(autopilot, "build_green_streak_tracker", lambda **_kwargs: {"ok": True, "exit_code": 0})
    monkeypatch.setattr(autopilot, "run_system_doctor", lambda **_kwargs: {"ok": True, "exit_code": 0})

    report = autopilot.run_daily_autopilot(
        project_root=tmp_path,
        as_of=as_of,
        strict=True,
    )
    assert report["ok"] is True
    assert report["exit_code"] == 0
    assert Path(report["exceptions_json"]).exists()
    assert Path(report["exceptions_md"]).exists()


def test_daily_autopilot_fails_closed_and_records_exception(tmp_path: Path, monkeypatch) -> None:
    as_of = "2026-02-26"
    summary_json = tmp_path / "exports" / "validation" / "board_v10_runtime" / as_of / "daily_ops_summary.json"
    summary_json.parent.mkdir(parents=True, exist_ok=True)
    summary_json.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        autopilot,
        "run_kaspi_daily_ops",
        lambda **_kwargs: {"ok": True, "exit_code": 0, "summary_json": str(summary_json)},
    )
    monkeypatch.setattr(
        autopilot,
        "generate_daily_ops_report",
        lambda **_kwargs: {"json_path": str(tmp_path / "exports" / "daily" / as_of / "daily_ops_report.json")},
    )
    monkeypatch.setattr(autopilot, "validate_daily_ops_report", lambda *_args, **_kwargs: {"ok": True, "errors": []})
    monkeypatch.setattr(autopilot, "build_domain_scorecards", lambda **_kwargs: {"ok": False, "exit_code": 1})
    monkeypatch.setattr(autopilot, "validate_cashfloor", lambda **_kwargs: {"ok": True, "exit_code": 0})
    monkeypatch.setattr(autopilot, "translate_transfer_ledger_to_cashflow", lambda **_kwargs: {"ok": True, "exit_code": 0})
    monkeypatch.setattr(autopilot, "build_daily_ops_timings", lambda **_kwargs: {"ok": True, "exit_code": 0})
    monkeypatch.setattr(autopilot, "build_weekly_health_scorecard", lambda **_kwargs: {"ok": True, "exit_code": 0})
    monkeypatch.setattr(autopilot, "build_green_streak_tracker", lambda **_kwargs: {"ok": True, "exit_code": 0})
    monkeypatch.setattr(autopilot, "run_system_doctor", lambda **_kwargs: {"ok": True, "exit_code": 0})

    report = autopilot.run_daily_autopilot(
        project_root=tmp_path,
        as_of=as_of,
        strict=True,
    )
    assert report["ok"] is False
    assert report["exit_code"] == 1
    exceptions = report["payload"]["exceptions"]
    assert any(row["step"] == "build_domain_scorecards" for row in exceptions)
