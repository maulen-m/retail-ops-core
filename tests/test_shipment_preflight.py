from __future__ import annotations

from pathlib import Path

from scripts.preflight_shipment import run_preflight_shipment


def test_preflight_blocks_on_failed_gate(tmp_path: Path) -> None:
    def fake_runner(cmd: str) -> tuple[int, str]:
        if "validate_params.py --strict" in cmd:
            return 1, "strict failed"
        return 0, "ok"

    report = run_preflight_shipment(project_root=tmp_path, as_of="2026-03-09", runner=fake_runner)
    assert report["ok"] is False
    assert report["exit_code"] == 1
    assert any(item["step"] == "validate_params_strict" and item["rc"] == 1 for item in report["checks"])


def test_preflight_passes_when_all_gates_green(tmp_path: Path) -> None:
    report = run_preflight_shipment(project_root=tmp_path, as_of="2026-03-09", runner=lambda cmd: (0, "ok"))
    assert report["ok"] is True
    assert report["exit_code"] == 0
    assert len(report["checks"]) >= 3
