from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3

import pytest

from scripts import validate_params as vp


def _touch_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.close()


def test_validate_params_passes_as_of_to_on_delivery_freeze(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _touch_db(db_path)
    workbook = tmp_path / "INBOUND_CALENDAR_LATEST.xlsx"
    workbook.write_bytes(b"placeholder")

    freeze_call: dict[str, object] = {}

    monkeypatch.setattr(vp, "validate_schema", lambda _db: [])
    monkeypatch.setattr(vp, "validate_fx_rates", lambda *_a, **_k: None)
    monkeypatch.setattr(vp, "validate_params", lambda *_a, **_k: None)
    monkeypatch.setattr(vp, "validate_budget_caps", lambda *_a, **_k: None)
    monkeypatch.setattr(vp, "validate_demand_overrides", lambda *_a, **_k: None)
    monkeypatch.setattr(vp, "validate_runs_table", lambda *_a, **_k: None)
    monkeypatch.setattr(vp, "resolve_single_truth_workbook_path", lambda **_k: workbook)
    monkeypatch.setattr(vp, "validate_inbound_sheet_consistency", lambda **_k: {"ok": True, "mismatches": []})
    monkeypatch.setattr(vp, "validate_astana_totals_alignment", lambda **_k: {"ok": True, "errors": [], "warnings": []})
    monkeypatch.setattr(vp, "validate_single_truth_system", lambda **_k: [])

    def _freeze_probe(**kwargs):
        freeze_call.update(kwargs)
        return []

    monkeypatch.setattr(vp, "validate_on_delivery_freeze", _freeze_probe)
    monkeypatch.setattr(vp, "validate_business_insides", lambda **_k: [])
    monkeypatch.setattr(
        vp,
        "reconcile_sales_truth",
        lambda **_k: {
            "daily_mismatch_count": 0,
            "sales_fact_v2": {"cogs_coverage_pct": 100.0},
            "fact_sales": {"cogs_coverage_pct": 100.0},
        },
    )
    monkeypatch.setattr(vp, "validate_sales_truth_consumers", lambda **_k: {"ok": True, "errors": [], "checked_scripts": []})
    monkeypatch.setattr(vp, "validate_offer_linkage", lambda **_k: {"ok": True, "metrics": {"resolved_rows": 0, "unresolved_rows": 0, "ambiguous_rows": 0}})
    monkeypatch.setattr(vp, "validate_cogs_integrity", lambda **_k: {"ok": True, "errors": [], "window_start": "2026-03-01", "window_end": "2026-03-04", "total_rows": 0})
    monkeypatch.setattr(vp, "validate_profit_publication_integrity", lambda **_k: {"ok": True, "errors": [], "window_start": "2026-03-01", "window_end": "2026-03-04"})
    monkeypatch.setattr(vp, "validate_dim_sku_light_alignment", lambda **_k: {"ok": True, "errors": [], "warnings": [], "compared_count": 0, "base_mismatch_count": 0})
    monkeypatch.setattr(vp, "validate_dim_sku_weight_guard_schema", lambda *_a, **_k: [])
    monkeypatch.setattr(vp, "validate_write_side_manifest", lambda **_k: {"ok": True, "errors": [], "checked_count": 0})

    monkeypatch.setattr(
        "sys.argv",
        [
            "validate_params.py",
            "--strict",
            "--db",
            str(db_path),
            "--as-of",
            "2026-03-04",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        vp.main()

    assert exc.value.code == 0
    assert freeze_call.get("until") == date(2026, 3, 4)
