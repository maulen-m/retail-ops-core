from __future__ import annotations

import json
from pathlib import Path

from scripts.run_kaspi_daily_ops import run_kaspi_daily_ops


def test_orchestrator_fails_closed_when_required_step_fails(tmp_path: Path) -> None:
    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        if "check_anchor_health.py" in cmd:
            return 1, "anchor health FAIL"
        return 0, "ok"

    report = run_kaspi_daily_ops(
        project_root=Path(".").resolve(),
        as_of="2026-02-23",
        output_root=tmp_path,
        allow_store_failures=set(),
        runner=fake_runner,
    )
    assert report["ok"] is False
    assert report["exit_code"] == 1
    assert any(step["step"] == "anchor_health" and not step["ok"] for step in report["steps"])


def test_orchestrator_requires_explicit_override_for_store_failures(tmp_path: Path) -> None:
    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        if "--store STOREB" in cmd:
            return 1, "store fail"
        return 0, "ok"

    blocked = run_kaspi_daily_ops(
        project_root=Path(".").resolve(),
        as_of="2026-02-23",
        output_root=tmp_path,
        allow_store_failures=set(),
        runner=fake_runner,
    )
    assert blocked["ok"] is False

    allowed = run_kaspi_daily_ops(
        project_root=Path(".").resolve(),
        as_of="2026-02-23",
        output_root=tmp_path,
        allow_store_failures={"STOREB"},
        runner=fake_runner,
    )
    assert allowed["ok"] is True


def test_orchestrator_writes_deterministic_summary_artifacts(tmp_path: Path) -> None:
    report = run_kaspi_daily_ops(
        project_root=Path(".").resolve(),
        as_of="2026-02-23",
        output_root=tmp_path,
        allow_store_failures=set(),
        runner=lambda _cmd, _cwd: (0, "ok"),
    )
    assert report["ok"] is True

    run_dir = tmp_path / "2026-02-23"
    summary_json = run_dir / "daily_ops_summary.json"
    summary_md = run_dir / "daily_ops_summary.md"
    assert summary_json.exists()
    assert summary_md.exists()

    payload = json.loads(summary_json.read_text(encoding="utf-8"))
    assert payload["as_of"] == "2026-02-23"
    assert payload["ok"] is True
