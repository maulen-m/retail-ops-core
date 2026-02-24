from __future__ import annotations

from pathlib import Path

from scripts.run_kaspi_daily_ops import run_kaspi_daily_ops


def _capture(profile: str, tmp_path: Path, stores_config: Path | None = None) -> list[str]:
    commands: list[str] = []

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        commands.append(cmd)
        return 0, "ok"

    kwargs = {}
    if stores_config is not None:
        kwargs["stores_config"] = stores_config

    run_kaspi_daily_ops(
        project_root=Path(".").resolve(),
        as_of="2026-02-23",
        output_root=tmp_path,
        allow_store_failures=set(),
        runner=fake_runner,
        profile=profile,
        **kwargs,
    )
    return commands


def test_today_fast_profile_uses_exact_day_waybill_status_window(tmp_path: Path) -> None:
    commands = _capture("today-fast", tmp_path)
    waybill_cmds = [cmd for cmd in commands if "report_waybill_status.py" in cmd]
    assert waybill_cmds
    assert all("--since-days 1" in cmd for cmd in waybill_cmds)
    assert all("--include-overdue" not in cmd for cmd in waybill_cmds)


def test_catch_up_profile_includes_overdue_waybill_window(tmp_path: Path) -> None:
    commands = _capture("catch-up", tmp_path)
    waybill_cmds = [cmd for cmd in commands if "report_waybill_status.py" in cmd]
    assert waybill_cmds
    assert all("--since-days 3" in cmd for cmd in waybill_cmds)
    assert all("--include-overdue" in cmd for cmd in waybill_cmds)


def test_orchestrator_uses_explicit_stores_config_when_provided(tmp_path: Path) -> None:
    stores_config = tmp_path / "stores.yaml"
    stores_config.write_text(
        "stores:\n"
        "  UNIVERSAL:\n"
        "    active: false\n"
        "  STOREB:\n"
        "    active: true\n",
        encoding="utf-8",
    )
    commands = _capture("today-fast", tmp_path, stores_config=stores_config)
    waybill_cmds = [cmd for cmd in commands if "report_waybill_status.py" in cmd]
    assert waybill_cmds
    assert all("--store STOREB" in cmd for cmd in waybill_cmds)
