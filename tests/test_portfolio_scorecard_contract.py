from __future__ import annotations

import json
from pathlib import Path

from scripts.build_domain_scorecards import build_domain_scorecards


def test_portfolio_scorecard_contract(tmp_path: Path) -> None:
    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        if "validate_po_money_gate.py" in cmd:
            return 0, json.dumps({"ok": True, "checks": []})
        if "validate_inventory_cost_drift.py" in cmd:
            return 0, "PASS"
        if "validate_cashflow_invariants.py" in cmd:
            return 0, "PASS"
        if "build_portfolio_completeness_report.py" in cmd:
            return 0, "status=PASS"
        if "build_ops_drift_pack.py" in cmd:
            return 0, "json_path=x"
        if "validate_drift_pack_slo.py" in cmd:
            return 0, "DRIFT_PACK_SLO PASS"
        raise AssertionError(f"unexpected command: {cmd}")

    report = build_domain_scorecards(
        project_root=Path(".").resolve(),
        as_of="2026-02-26",
        output_root=tmp_path,
        strict=True,
        runner=fake_runner,
    )
    assert report["ok"] is True
    payload = json.loads((tmp_path / "2026-02-26" / "portfolio_scorecard.json").read_text(encoding="utf-8"))
    assert payload["domain"] == "portfolio"
    assert payload["status"] == "GREEN"
