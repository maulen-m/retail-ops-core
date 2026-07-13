from __future__ import annotations

from pathlib import Path

from scripts.preflight_shipment import run_preflight_shipment


def test_preflight_blocks_on_failed_gate(tmp_path: Path) -> None:
    def fake_runner(cmd: str) -> tuple[int, str]:
        if "check_local_app_db.py" in cmd:
            return 1, "db preflight failed"
        return 0, "ok"

    report = run_preflight_shipment(project_root=tmp_path, runner=fake_runner)
    assert report["ok"] is False
    assert report["exit_code"] == 1
    assert any(item["step"] == "local_db_preflight" and item["rc"] == 1 for item in report["checks"])


def test_preflight_passes_when_all_gates_green(tmp_path: Path) -> None:
    report = run_preflight_shipment(project_root=tmp_path, runner=lambda cmd: (0, "ok"))
    assert report["ok"] is True
    assert report["exit_code"] == 0
    assert len(report["checks"]) >= 3
