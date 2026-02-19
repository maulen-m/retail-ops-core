from __future__ import annotations

from pathlib import Path
import subprocess


def _script_path() -> Path:
    return Path(__file__).resolve().parents[1] / "scripts" / "install_single_truth_ops_scheduler.sh"


def _run_validate_only(project_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(_script_path()), "--validate-only", "--project-dir", str(project_dir)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_validate_only_fails_when_repo_venv_missing(tmp_path: Path) -> None:
    project_dir = tmp_path / "repo"
    project_dir.mkdir(parents=True, exist_ok=True)

    completed = _run_validate_only(project_dir)

    assert completed.returncode != 0
    assert "missing .venv/bin/python" in (completed.stdout + completed.stderr)


def test_validate_only_fails_when_repo_venv_missing_required_imports(tmp_path: Path) -> None:
    project_dir = tmp_path / "repo"
    venv_python = project_dir / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True, exist_ok=True)
    venv_python.write_text(
        "#!/bin/bash\n"
        "if [ \"$1\" = \"-c\" ]; then\n"
        "  exit 1\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    venv_python.chmod(0o755)

    completed = _run_validate_only(project_dir)

    assert completed.returncode != 0
    assert "cannot import pandas/requests/openpyxl" in (completed.stdout + completed.stderr)


def test_validate_only_fails_when_anchor_health_check_fails(tmp_path: Path) -> None:
    project_dir = tmp_path / "repo"
    venv_python = project_dir / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True, exist_ok=True)
    venv_python.write_text(
        "#!/bin/bash\n"
        "if [ \"$1\" = \"-c\" ]; then\n"
        "  exit 0\n"
        "fi\n"
        "exit 9\n",
        encoding="utf-8",
    )
    venv_python.chmod(0o755)

    completed = _run_validate_only(project_dir)

    assert completed.returncode != 0
    assert "anchor health check failed" in (completed.stdout + completed.stderr)


def test_validate_only_passes_with_repo_venv_and_required_imports(tmp_path: Path) -> None:
    project_dir = tmp_path / "repo"
    venv_python = project_dir / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True, exist_ok=True)
    venv_python.write_text(
        "#!/bin/bash\n"
        "exit 0\n",
        encoding="utf-8",
    )
    venv_python.chmod(0o755)

    completed = _run_validate_only(project_dir)

    assert completed.returncode == 0
    assert "runtime checks passed" in (completed.stdout + completed.stderr)
