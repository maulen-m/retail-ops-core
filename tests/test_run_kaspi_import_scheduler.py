from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.run_kaspi_import_scheduler as sched


def _make_cmd(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)


def _patch_runtime_paths(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setattr(sched, "PROJECT_ROOT", root)
    monkeypatch.setattr(sched, "DOTENV_PATH", root / ".env")
    monkeypatch.setattr(sched, "RUNTIME_LOG_DIR", root / "runtime_logs")
    monkeypatch.setattr(sched, "STDOUT_LOG_PATH", root / "runtime_logs" / "kaspi_import_stdout.log")
    monkeypatch.setattr(sched, "STDERR_LOG_PATH", root / "runtime_logs" / "kaspi_import_stderr.log")
    monkeypatch.setattr(sched, "REPORT_DIR", root / "runtime_logs" / "import_reports")


def test_parse_dotenv_strips_quotes(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "# comment",
                "KASPI_IMPORT_POPUP_TERMINAL='1'",
                'X="abc"',
                "Y=noquote",
                "",
            ]
        ),
        encoding="utf-8",
    )
    parsed = sched._parse_dotenv(env_path)
    assert parsed["KASPI_IMPORT_POPUP_TERMINAL"] == "1"
    assert parsed["X"] == "abc"
    assert parsed["Y"] == "noquote"


def test_write_run_report_includes_tails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runtime_paths(monkeypatch, tmp_path)
    sched.STDOUT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    sched.STDOUT_LOG_PATH.write_text("line1\nline2\n", encoding="utf-8")
    sched.STDERR_LOG_PATH.write_text("err1\nerr2\n", encoding="utf-8")

    started = datetime(2026, 2, 24, 16, 3, 0)
    finished = started + timedelta(minutes=4, seconds=30)
    report = sched._write_run_report(
        started_at=started,
        finished_at=finished,
        return_code=0,
        command_path=tmp_path / "excel_ui" / "run_full_import.command",
    )

    text = report.read_text(encoding="utf-8")
    assert "Outcome: SUCCESS" in text
    assert "Duration: 270s" in text
    assert "line2" in text
    assert "err2" in text


def test_main_popup_enabled_via_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runtime_paths(monkeypatch, tmp_path)
    cmd = tmp_path / "excel_ui" / "run_full_import.command"
    _make_cmd(cmd)
    monkeypatch.setattr(sched, "COMMAND_PATH", cmd)
    sched.STDOUT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    sched.STDOUT_LOG_PATH.write_text("ok\n", encoding="utf-8")
    sched.STDERR_LOG_PATH.write_text("", encoding="utf-8")
    sched.DOTENV_PATH.write_text("KASPI_IMPORT_POPUP_TERMINAL=1\n", encoding="utf-8")

    calls: list[list[str]] = []

    def fake_run(args, cwd=None, env=None, check=False):  # type: ignore[no-untyped-def]
        calls.append(args)
        return SimpleNamespace(returncode=0)

    popup_calls: list[Path] = []
    monkeypatch.setattr(sched.subprocess, "run", fake_run)
    monkeypatch.setattr(sched, "_show_terminal_popup", lambda path: popup_calls.append(path))
    monkeypatch.delenv("KASPI_IMPORT_POPUP_TERMINAL", raising=False)

    rc = sched.main()
    assert rc == 0
    assert calls and calls[0][0] == "/bin/bash"
    assert popup_calls and popup_calls[0].exists()


def test_main_popup_disabled_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_runtime_paths(monkeypatch, tmp_path)
    cmd = tmp_path / "excel_ui" / "run_full_import.command"
    _make_cmd(cmd)
    monkeypatch.setattr(sched, "COMMAND_PATH", cmd)
    sched.STDOUT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    sched.STDOUT_LOG_PATH.write_text("ok\n", encoding="utf-8")
    sched.STDERR_LOG_PATH.write_text("", encoding="utf-8")
    sched.DOTENV_PATH.write_text("", encoding="utf-8")

    def fake_run(args, cwd=None, env=None, check=False):  # type: ignore[no-untyped-def]
        return SimpleNamespace(returncode=0)

    popup_calls: list[Path] = []
    monkeypatch.setattr(sched.subprocess, "run", fake_run)
    monkeypatch.setattr(sched, "_show_terminal_popup", lambda path: popup_calls.append(path))
    monkeypatch.delenv("KASPI_IMPORT_POPUP_TERMINAL", raising=False)

    rc = sched.main()
    assert rc == 0
    assert popup_calls == []

