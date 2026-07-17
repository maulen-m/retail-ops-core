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


def test_forced_refresh_retries_temporary_lock_contention(monkeypatch) -> None:
    returncodes = [scheduler.LOCK_CONTENTION_EXIT_CODE, scheduler.LOCK_CONTENTION_EXIT_CODE, 0]
    calls: list[list[str]] = []
    sleeps: list[int] = []

    class Result:
        def __init__(self, returncode: int) -> None:
            self.returncode = returncode

    monkeypatch.setattr(
        scheduler.subprocess,
        "run",
        lambda command, **_kwargs: calls.append(list(command)) or Result(returncodes.pop(0)),
    )
    monkeypatch.setattr(scheduler.time, "sleep", lambda seconds: sleeps.append(seconds))

    assert scheduler.run_forced_source_refresh(project_root=PROJECT_ROOT, env={}) == 0
    assert len(calls) == 3
    assert sleeps == [scheduler.LOCK_RETRY_INTERVAL_SECONDS] * 2


def test_forced_refresh_fails_after_bounded_lock_retries(monkeypatch) -> None:
    calls: list[list[str]] = []

    class Result:
        returncode = scheduler.LOCK_CONTENTION_EXIT_CODE

    monkeypatch.setattr(scheduler, "LOCK_RETRY_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(
        scheduler.subprocess,
        "run",
        lambda command, **_kwargs: calls.append(list(command)) or Result(),
    )
    monkeypatch.setattr(scheduler.time, "sleep", lambda _seconds: None)

    assert scheduler.run_forced_source_refresh(project_root=PROJECT_ROOT, env={}) == 75
    assert len(calls) == 3
