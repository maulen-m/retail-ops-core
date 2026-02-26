from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import build_daily_ops_timings
from scripts import build_domain_scorecards
from scripts import build_green_streak_tracker
from scripts import run_daily_autopilot
from scripts import system_doctor
from scripts.resolve_as_of_date import resolve_as_of_date


def _write_daily_report(root: Path, day_iso: str, *, ok: bool = True, status: str = "GREEN") -> None:
    day_dir = root / "exports" / "daily" / day_iso
    day_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "as_of": day_iso,
        "status": status,
        "ok": ok,
        "hard_failures": [],
        "steps": [],
        "store_reports": [],
    }
    (day_dir / "daily_ops_report.json").write_text(json.dumps(payload), encoding="utf-8")


def test_resolve_as_of_date_prefers_latest_complete_day(tmp_path: Path) -> None:
    _write_daily_report(tmp_path, "2026-02-24")
    _write_daily_report(tmp_path, "2026-02-25")
    result = resolve_as_of_date(project_root=tmp_path, explicit_as_of=None, strict=True)
    assert result.as_of == "2026-02-25"
    assert result.source == "latest_complete_day"


def test_resolve_as_of_date_strict_fails_without_complete_day(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="no complete as-of date"):
        resolve_as_of_date(project_root=tmp_path, explicit_as_of=None, strict=True)


def test_resolve_as_of_date_non_strict_falls_back_to_today(tmp_path: Path) -> None:
    result = resolve_as_of_date(project_root=tmp_path, explicit_as_of=None, strict=False)
    assert result.source == "today_fallback"
    assert len(result.as_of) == 10


def test_strict_scripts_converge_on_same_resolved_as_of(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_daily_report(tmp_path, "2026-02-25")
    expected_as_of = "2026-02-25"

    seen: dict[str, str] = {}

    def fake_build_domain_scorecards(**kwargs):
        seen["build_domain_scorecards"] = kwargs["as_of"]
        return {
            "output_dir": str(tmp_path / "exports" / "daily" / expected_as_of),
            "ok": True,
            "exit_code": 0,
            "scorecards": {
                "po": {"status": "GREEN"},
                "inventory": {"status": "GREEN"},
                "cashflow": {"status": "GREEN"},
                "portfolio": {"status": "GREEN"},
                "truth_drift": {"status": "GREEN"},
            },
        }

    def fake_build_daily_ops_timings(**kwargs):
        seen["build_daily_ops_timings"] = kwargs["as_of"]
        return {
            "ok": True,
            "exit_code": 0,
            "json_path": str(tmp_path / "exports" / "perf" / expected_as_of / "daily_ops_timings.json"),
            "md_path": str(tmp_path / "exports" / "perf" / expected_as_of / "daily_ops_timings.md"),
        }

    def fake_build_green_streak_tracker(**kwargs):
        seen["build_green_streak_tracker"] = kwargs["as_of"]
        return {
            "ok": True,
            "exit_code": 0,
            "json_path": str(tmp_path / "exports" / "health" / "streak" / expected_as_of / "green_streak.json"),
            "md_path": str(tmp_path / "exports" / "health" / "streak" / expected_as_of / "green_streak.md"),
        }

    def fake_run_system_doctor(**kwargs):
        seen["system_doctor"] = kwargs["as_of"]
        return {
            "ok": True,
            "exit_code": 0,
            "json_path": str(tmp_path / "exports" / "diagnostics" / expected_as_of / "system_health.json"),
            "md_path": str(tmp_path / "exports" / "diagnostics" / expected_as_of / "system_health.md"),
            "checks_path": str(tmp_path / "exports" / "diagnostics" / expected_as_of / "system_health_checks.json"),
            "status": "GREEN",
            "blocked_layer": None,
        }

    def fake_run_daily_autopilot(**kwargs):
        seen["run_daily_autopilot"] = kwargs["as_of"]
        return {
            "ok": True,
            "exit_code": 0,
            "exceptions_json": str(tmp_path / "exports" / "exceptions" / expected_as_of / "exceptions.json"),
            "exceptions_md": str(tmp_path / "exports" / "exceptions" / expected_as_of / "exceptions.md"),
        }

    monkeypatch.setattr(build_domain_scorecards, "build_domain_scorecards", fake_build_domain_scorecards)
    monkeypatch.setattr(build_daily_ops_timings, "build_daily_ops_timings", fake_build_daily_ops_timings)
    monkeypatch.setattr(build_green_streak_tracker, "build_green_streak_tracker", fake_build_green_streak_tracker)
    monkeypatch.setattr(system_doctor, "run_system_doctor", fake_run_system_doctor)
    monkeypatch.setattr(run_daily_autopilot, "run_daily_autopilot", fake_run_daily_autopilot)

    # build_domain_scorecards main
    monkeypatch.setattr(
        "sys.argv",
        ["build_domain_scorecards.py", "--project-root", str(tmp_path), "--strict"],
    )
    assert build_domain_scorecards.main() == 0

    # build_daily_ops_timings main
    monkeypatch.setattr(
        "sys.argv",
        ["build_daily_ops_timings.py", "--project-root", str(tmp_path), "--strict"],
    )
    assert build_daily_ops_timings.main() == 0

    # build_green_streak_tracker main
    monkeypatch.setattr(
        "sys.argv",
        ["build_green_streak_tracker.py", "--daily-root", str(tmp_path / "exports" / "daily"), "--validation-root", str(tmp_path / "exports" / "validation"), "--output-root", str(tmp_path / "exports" / "health" / "streak"), "--strict"],
    )
    assert build_green_streak_tracker.main() == 0

    # system_doctor main
    monkeypatch.setattr(
        "sys.argv",
        ["system_doctor.py", "--project-root", str(tmp_path), "--strict"],
    )
    assert system_doctor.main() == 0

    # run_daily_autopilot main
    monkeypatch.setattr(
        "sys.argv",
        ["run_daily_autopilot.py", "--project-root", str(tmp_path), "--strict"],
    )
    assert run_daily_autopilot.main() == 0

    assert set(seen.values()) == {expected_as_of}
