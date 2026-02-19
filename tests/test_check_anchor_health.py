from __future__ import annotations

from datetime import date, timedelta
import os
from pathlib import Path
import subprocess
import sys

from openpyxl import Workbook

from scripts.check_anchor_health import check_anchor_health


def _write_sales_workbook(path: Path, day: date) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "SALES_KSP_CRM_1"
    ws.append(["Date", "Quantity", "Total_net_rev"])
    ws.append([day.isoformat(), 1, 1000.0])
    wb.save(path)


def _prepare_repo(tmp_path: Path, *, venv_script: str) -> tuple[Path, Path, Path]:
    project = tmp_path / "repo"
    crm_workbook = project / "excel_ui" / "SALES_KSP_CRM_V3.xlsx"
    inbound_workbook = project / "inbound" / "Inbound_calendar_V10.002.xlsx"
    inbound_workbook.parent.mkdir(parents=True, exist_ok=True)
    inbound_workbook.write_bytes(b"inbound-fixture")

    anchors = project / "config" / "anchors"
    anchors.mkdir(parents=True, exist_ok=True)
    os.symlink(crm_workbook, anchors / "SALES_KSP_CRM_LATEST.xlsx")
    os.symlink(inbound_workbook, anchors / "INBOUND_CALENDAR_LATEST.xlsx")

    venv_python = project / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True, exist_ok=True)
    venv_python.write_text(venv_script, encoding="utf-8")
    venv_python.chmod(0o755)
    return project, crm_workbook, venv_python


def test_anchor_health_fails_when_anchor_symlink_missing(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    venv_python = project / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True, exist_ok=True)
    venv_python.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    venv_python.chmod(0o755)

    rc, lines = check_anchor_health(project_root=project)
    assert rc != 0
    assert any("missing anchor symlink" in line for line in lines)


def test_anchor_health_fails_when_crm_workbook_is_stale(tmp_path: Path) -> None:
    project, crm_workbook, _venv = _prepare_repo(
        tmp_path, venv_script="#!/bin/bash\nif [ \"$1\" = \"-c\" ]; then exit 0; fi\nexit 0\n"
    )
    now = 1_760_000_000.0
    _write_sales_workbook(crm_workbook, date(2026, 2, 19))
    stale_ts = now - (48 * 3600)
    os.utime(crm_workbook, (stale_ts, stale_ts))

    rc, lines = check_anchor_health(
        project_root=project,
        now_ts=now,
        max_age_hours=24,
        max_future_skew_seconds=120,
        max_lag_days=10,
    )
    assert rc != 0
    assert any("stale workbook mtime" in line for line in lines)


def test_anchor_health_fails_when_workbook_content_lag_exceeds(tmp_path: Path) -> None:
    project, crm_workbook, _venv = _prepare_repo(
        tmp_path, venv_script="#!/bin/bash\nif [ \"$1\" = \"-c\" ]; then exit 0; fi\nexit 0\n"
    )
    anchor_day = date(2026, 2, 10)
    _write_sales_workbook(crm_workbook, anchor_day)
    now = 1_760_000_000.0
    os.utime(crm_workbook, (now, now))

    rc, lines = check_anchor_health(
        project_root=project,
        now_ts=now,
        max_age_hours=72,
        max_future_skew_seconds=120,
        max_lag_days=1,
        as_of=date(2026, 2, 19),
    )
    assert rc != 0
    assert any("workbook content lag exceeds threshold" in line for line in lines)


def test_anchor_health_fails_when_venv_import_contract_breaks(tmp_path: Path) -> None:
    project, crm_workbook, _venv = _prepare_repo(
        tmp_path,
        venv_script=(
            "#!/bin/bash\n"
            "if [ \"$1\" = \"-c\" ]; then\n"
            "  exit 1\n"
            "fi\n"
            "exit 0\n"
        ),
    )
    _write_sales_workbook(crm_workbook, date.today())
    now = 1_760_000_000.0
    os.utime(crm_workbook, (now, now))

    rc, lines = check_anchor_health(
        project_root=project,
        now_ts=now,
        max_age_hours=72,
        max_future_skew_seconds=120,
        max_lag_days=10,
        as_of=date.today(),
    )
    assert rc != 0
    assert any("cannot import pandas/requests/openpyxl" in line for line in lines)


def test_anchor_health_passes_when_symlinks_and_runtime_are_healthy(tmp_path: Path) -> None:
    project, crm_workbook, _venv = _prepare_repo(
        tmp_path, venv_script="#!/bin/bash\nif [ \"$1\" = \"-c\" ]; then exit 0; fi\nexit 0\n"
    )
    as_of = date(2026, 2, 19)
    _write_sales_workbook(crm_workbook, as_of - timedelta(days=1))
    now = 1_760_000_000.0
    os.utime(crm_workbook, (now, now))

    rc, lines = check_anchor_health(
        project_root=project,
        now_ts=now,
        max_age_hours=72,
        max_future_skew_seconds=120,
        max_lag_days=1,
        as_of=as_of,
    )
    assert rc == 0
    assert any("anchor health PASS" in line for line in lines)


def test_anchor_health_cli_runs_from_external_cwd_without_module_error(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir(parents=True, exist_ok=True)
    script = Path(__file__).resolve().parents[1] / "scripts" / "check_anchor_health.py"
    outside_cwd = tmp_path / "outside"
    outside_cwd.mkdir(parents=True, exist_ok=True)

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--project-root",
            str(project),
        ],
        cwd=str(outside_cwd),
        text=True,
        capture_output=True,
        check=False,
    )

    output = (completed.stdout or "") + (completed.stderr or "")
    assert completed.returncode != 0
    assert "ModuleNotFoundError" not in output
    assert "missing anchor symlink" in output
