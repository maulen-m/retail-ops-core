from __future__ import annotations

import json
from pathlib import Path

from scripts.build_domain_scorecards import build_domain_scorecards


def test_cashflow_scorecard_fail_closed_in_strict_mode(tmp_path: Path) -> None:
    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        if "validate_po_money_gate.py" in cmd:
            return 0, json.dumps({"ok": True, "checks": []})
        if "validate_inventory_cost_drift.py" in cmd:
            return 0, "PASS: inventory cost drift within tolerance"
        if "validate_cashflow_invariants.py" in cmd:
            return 1, "FAIL: invariant breach"
        if "build_ops_drift_pack.py" in cmd:
            return 0, "json_path=exports/validation/2026-02-25/single_truth_drift_pack.json"
        if "validate_drift_pack_slo.py" in cmd:
            return 0, "DRIFT_PACK_SLO PASS"
        raise AssertionError(f"unexpected command: {cmd}")

    report = build_domain_scorecards(
        project_root=Path(".").resolve(),
        as_of="2026-02-25",
        output_root=tmp_path,
        strict=True,
        runner=fake_runner,
    )
    assert report["ok"] is False
    assert report["exit_code"] == 1

    cash_json = tmp_path / "2026-02-25" / "cashflow_scorecard.json"
    payload = json.loads(cash_json.read_text(encoding="utf-8"))
    assert payload["domain"] == "cashflow"
    assert payload["status"] == "RED"

