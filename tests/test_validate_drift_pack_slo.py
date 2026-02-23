from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.validate_drift_pack_slo import validate_drift_pack_slo


def _write_pack(root: Path, as_of: str, *, status: str = "PASS") -> Path:
    day_dir = root / as_of
    day_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "as_of": as_of,
        "generated_at": as_of,
        "status": status,
        "status_reasons": ["ok"],
        "workbook_overage": {"status": "ok"},
        "cogs_integrity": {"unresolved_rows": 0},
        "on_delivery_residuals": {"residual_count": 0},
        "dim_sku_alignment": {"status": "ok"},
        "paid_capital_snapshot": {"cash_actual_kzt": 1},
    }
    json_path = day_dir / "single_truth_drift_pack.json"
    md_path = day_dir / "single_truth_drift_pack.md"
    json_path.write_text(json.dumps(payload), encoding="utf-8")
    md_path.write_text("# drift pack\n", encoding="utf-8")
    return json_path


def test_validate_drift_pack_slo_fails_when_pack_missing(tmp_path: Path) -> None:
    report = validate_drift_pack_slo(output_root=tmp_path, as_of="2026-02-23", max_age_hours=36.0)
    assert report["ok"] is False
    assert any("missing drift pack json" in err for err in report["errors"])


def test_validate_drift_pack_slo_fails_for_critical_status(tmp_path: Path) -> None:
    _write_pack(tmp_path, "2026-02-23", status="CRITICAL")
    report = validate_drift_pack_slo(output_root=tmp_path, as_of="2026-02-23", max_age_hours=36.0)
    assert report["ok"] is False
    assert any("status=CRITICAL" in err for err in report["errors"])


def test_validate_drift_pack_slo_fails_for_stale_file(tmp_path: Path) -> None:
    json_path = _write_pack(tmp_path, "2026-02-23", status="PASS")
    stale = datetime.now(timezone.utc) - timedelta(hours=50)
    ts = stale.timestamp()
    json_path.touch()
    (json_path.parent / "single_truth_drift_pack.md").touch()
    Path(json_path).stat()
    import os

    os.utime(json_path, (ts, ts))
    os.utime(json_path.parent / "single_truth_drift_pack.md", (ts, ts))

    report = validate_drift_pack_slo(output_root=tmp_path, as_of="2026-02-23", max_age_hours=36.0)
    assert report["ok"] is False
    assert any("older than max_age_hours" in err for err in report["errors"])


def test_validate_drift_pack_slo_passes_for_fresh_warn_status(tmp_path: Path) -> None:
    _write_pack(tmp_path, "2026-02-23", status="WARN")
    report = validate_drift_pack_slo(output_root=tmp_path, as_of="2026-02-23", max_age_hours=36.0)
    assert report["ok"] is True
