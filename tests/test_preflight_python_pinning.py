from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest

from scripts.run_strict_daily_preflight import bootstrap_repo_venv_python, _resolve_reexec_target


def test_bootstrap_reexecs_into_repo_venv_python_when_available(tmp_path: Path) -> None:
    venv_python = tmp_path / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True, exist_ok=True)
    venv_python.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    current_python = tmp_path / "python-system"
    current_python.write_text("", encoding="utf-8")
    called: list[tuple[str, list[str]]] = []

    def _fake_execv(executable: str, argv: list[str]) -> None:
        called.append((executable, argv))

    changed = bootstrap_repo_venv_python(
        project_root=tmp_path,
        current_executable=current_python,
        argv=["scripts/run_strict_daily_preflight.py", "--db", "db/app.db"],
        execv_fn=_fake_execv,
    )

    assert changed is True
    assert called
    assert called[0][0] == str(venv_python.resolve())
    assert called[0][1][0] == str(venv_python.resolve())


def test_bootstrap_skips_reexec_when_already_in_venv(tmp_path: Path) -> None:
    venv_python = tmp_path / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True, exist_ok=True)
    venv_python.write_text("#!/usr/bin/env python3\n", encoding="utf-8")

    changed = bootstrap_repo_venv_python(
        project_root=tmp_path,
        current_executable=venv_python,
        execv_fn=lambda *_args: None,
    )

    assert changed is False


def test_bootstrap_skips_reexec_when_venv_missing(tmp_path: Path) -> None:
    changed = bootstrap_repo_venv_python(
        project_root=tmp_path,
        current_executable=tmp_path / "python-system",
        execv_fn=lambda *_args: None,
    )

    assert changed is False


def test_resolve_reexec_target_returns_none_when_venv_missing(tmp_path: Path) -> None:
    target = _resolve_reexec_target(
        project_root=tmp_path,
        current_executable=tmp_path / "python-system",
    )
    assert target is None


def test_preflight_help_runs_under_system_python_when_venv_exists() -> None:
    system_python = Path("/usr/bin/python3")
    if not system_python.exists():
        pytest.skip("/usr/bin/python3 not available")
    repo_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [str(system_python), "scripts/run_strict_daily_preflight.py", "--help"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "run strict daily preflight" in (completed.stdout or "").lower()
