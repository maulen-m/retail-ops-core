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
    project_root = tmp_path / "project"
    (project_root / "config").mkdir(parents=True)
    (project_root / "config" / "stores.yaml").write_text(
        "stores:\n  UNIVERSAL:\n    active: true\n",
        encoding="utf-8",
    )

    report = run_kaspi_daily_ops(
        project_root=project_root,
        as_of="2026-02-23",
        output_root=tmp_path,
        allow_store_failures=set(),
        runner=lambda _cmd, _cwd: (0, "ok"),
        stores_config=project_root / "config" / "stores.yaml",
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
    assert any(step["step"] == "validate_schema" for step in payload["steps"])


def test_orchestrator_surfaces_latest_shipping_backlog_report(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    (project_root / "config").mkdir(parents=True)
    (project_root / "config" / "stores.yaml").write_text(
        "stores:\n  UNIVERSAL:\n    active: true\n",
        encoding="utf-8",
    )
    backlog_dir = project_root / "reports" / "kaspi_pending_backlog" / "2026-02-23"
    backlog_dir.mkdir(parents=True)
    backlog_json = backlog_dir / "ship_orders_backlog_ALL_STORES_latest.json"
    backlog_md = backlog_dir / "ship_orders_backlog_ALL_STORES_latest.md"
    backlog_json.write_text(
        json.dumps(
            {
                "target_date": "2026-02-23",
                "store_scope": "ALL_STORES",
                "initial": {"summary": {"overdue_pending": 4, "stale_pending": 2}},
                "remaining": {"summary": {"overdue_pending": 1, "stale_pending": 1}},
            }
        ),
        encoding="utf-8",
    )
    backlog_md.write_text("# backlog\n", encoding="utf-8")

    report = run_kaspi_daily_ops(
        project_root=project_root,
        as_of="2026-02-23",
        output_root=tmp_path,
        allow_store_failures=set(),
        runner=lambda _cmd, _cwd: (0, "ok"),
        stores_config=project_root / "config" / "stores.yaml",
    )

    payload = json.loads(Path(report["summary_json"]).read_text(encoding="utf-8"))
    assert payload["shipping_backlog_latest"]["present"] is True
    assert payload["shipping_backlog_latest"]["json_path"].endswith("ship_orders_backlog_ALL_STORES_latest.json")
    assert payload["shipping_backlog_latest"]["remaining_overdue_pending"] == 1
