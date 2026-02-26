from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validate_as_of_consistency import validate_as_of_consistency
from scripts.system_doctor import run_system_doctor


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _seed_required_artifacts(root: Path, as_of: str) -> None:
    _write_json(root / "exports" / "daily" / as_of / "daily_ops_report.json", {"as_of": as_of, "ok": True, "status": "GREEN"})
    _write_json(root / "exports" / "daily" / as_of / "po_scorecard.json", {"as_of": as_of})
    _write_json(root / "exports" / "daily" / as_of / "inventory_scorecard.json", {"as_of": as_of})
    _write_json(root / "exports" / "daily" / as_of / "cashflow_scorecard.json", {"as_of": as_of})
    _write_json(root / "exports" / "daily" / as_of / "truth_drift_report.json", {"as_of": as_of})
    _write_json(root / "exports" / "perf" / as_of / "daily_ops_timings.json", {"as_of": as_of})
    _write_json(root / "exports" / "diagnostics" / as_of / "system_health.json", {"as_of": as_of, "ok": True, "status": "GREEN"})
    _write_json(root / "exports" / "exceptions" / as_of / "exceptions.json", {"as_of": as_of, "exceptions": [], "ok": True, "status": "GREEN"})
    _write_json(
        root / "config" / "business_insides" / f"BUSINESS_INSIDES_{as_of}.json",
        {"as_of": as_of, "waybill_snapshot": {"status": "available", "target_date": as_of, "stores": {}}},
    )


def test_as_of_consistency_passes_when_all_required_artifacts_match(tmp_path: Path) -> None:
    as_of = "2026-02-26"
    _seed_required_artifacts(tmp_path, as_of)
    report = validate_as_of_consistency(
        project_root=tmp_path,
        as_of=as_of,
        as_of_source="explicit",
        output_root=tmp_path / "exports" / "diagnostics",
        strict=True,
    )
    assert report["ok"] is True
    assert report["status"] == "PASS"


def test_as_of_consistency_fails_closed_on_mismatch(tmp_path: Path) -> None:
    as_of = "2026-02-26"
    _seed_required_artifacts(tmp_path, as_of)
    _write_json(tmp_path / "exports" / "daily" / as_of / "po_scorecard.json", {"as_of": "2026-02-25"})
    with pytest.raises(RuntimeError, match="as-of consistency validation failed"):
        validate_as_of_consistency(
            project_root=tmp_path,
            as_of=as_of,
            as_of_source="explicit",
            output_root=tmp_path / "exports" / "diagnostics",
            strict=True,
        )


def test_system_doctor_includes_as_of_consistency_check() -> None:
    calls: list[str] = []

    def fake_runner(cmd: str, _cwd: Path) -> tuple[int, str]:
        calls.append(cmd)
        return 0, "ok"

    report = run_system_doctor(
        project_root=Path(".").resolve(),
        as_of="2026-02-26",
        output_dir=Path("exports/diagnostics/2026-02-26"),
        strict=True,
        runner=fake_runner,
    )
    assert report["ok"] is True
    assert any("validate_as_of_consistency.py" in cmd for cmd in calls)


def test_as_of_consistency_fails_on_waybill_selection_date_mismatch(tmp_path: Path) -> None:
    as_of = "2026-02-26"
    _seed_required_artifacts(tmp_path, as_of)
    _write_json(
        tmp_path / "excel_ui" / "ActiveOrders" / "waybills" / "_waybill_selection_orders.json",
        {"target_date": "2026-02-25", "stores": {"ACMEWEAR": ["1"]}},
    )
    with pytest.raises(RuntimeError, match="as-of consistency validation failed"):
        validate_as_of_consistency(
            project_root=tmp_path,
            as_of=as_of,
            as_of_source="explicit",
            output_root=tmp_path / "exports" / "diagnostics",
            strict=True,
        )
