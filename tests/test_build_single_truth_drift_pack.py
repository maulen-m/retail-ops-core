from __future__ import annotations

import json
from pathlib import Path

from scripts.build_single_truth_drift_pack import (
    build_single_truth_drift_pack,
    classify_pack_status,
)


def test_drift_pack_generates_required_sections_and_deterministic_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "app.db"
    db_path.write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr(
        "scripts.build_single_truth_drift_pack.collect_workbook_overage",
        lambda **_kwargs: {"status": "ok", "overage_days": 0},
    )
    monkeypatch.setattr(
        "scripts.build_single_truth_drift_pack.collect_cogs_summary",
        lambda **_kwargs: {"unresolved_rows": 0, "unresolved_skus": []},
    )
    monkeypatch.setattr(
        "scripts.build_single_truth_drift_pack.collect_on_delivery_residuals",
        lambda **_kwargs: {"residual_count": 0, "sample": []},
    )
    monkeypatch.setattr(
        "scripts.build_single_truth_drift_pack.collect_dim_sku_alignment",
        lambda **_kwargs: {"status": "ok", "weight_mismatch_count": 0},
    )
    monkeypatch.setattr(
        "scripts.build_single_truth_drift_pack.collect_paid_capital_snapshot",
        lambda **_kwargs: {"cash_actual_kzt": 1_000_000, "total_capital_paid_kzt": 2_000_000},
    )

    report = build_single_truth_drift_pack(
        db_path=db_path,
        as_of="2026-02-17",
        output_root=tmp_path / "exports" / "validation",
    )

    assert report["json_path"].endswith("/2026-02-17/single_truth_drift_pack.json")
    assert report["markdown_path"].endswith("/2026-02-17/single_truth_drift_pack.md")

    md = Path(report["markdown_path"]).read_text(encoding="utf-8")
    assert "## Workbook Overage" in md
    assert "## COGS Integrity" in md
    assert "## On-Delivery Residuals" in md
    assert "## Dim SKU Alignment" in md
    assert "## Paid Capital Snapshot" in md

    payload = json.loads(Path(report["json_path"]).read_text(encoding="utf-8"))
    assert payload["as_of"] == "2026-02-17"


def test_drift_pack_is_read_only_for_db_file(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.db"
    db_path.write_text("placeholder", encoding="utf-8")
    before_mtime = db_path.stat().st_mtime

    monkeypatch.setattr(
        "scripts.build_single_truth_drift_pack.collect_workbook_overage",
        lambda **_kwargs: {"status": "skipped"},
    )
    monkeypatch.setattr(
        "scripts.build_single_truth_drift_pack.collect_cogs_summary",
        lambda **_kwargs: {"unresolved_rows": 0, "unresolved_skus": []},
    )
    monkeypatch.setattr(
        "scripts.build_single_truth_drift_pack.collect_on_delivery_residuals",
        lambda **_kwargs: {"residual_count": 0, "sample": []},
    )
    monkeypatch.setattr(
        "scripts.build_single_truth_drift_pack.collect_dim_sku_alignment",
        lambda **_kwargs: {"status": "ok", "weight_mismatch_count": 0},
    )
    monkeypatch.setattr(
        "scripts.build_single_truth_drift_pack.collect_paid_capital_snapshot",
        lambda **_kwargs: {"cash_actual_kzt": 1, "total_capital_paid_kzt": 1},
    )

    build_single_truth_drift_pack(
        db_path=db_path,
        as_of="2026-02-17",
        output_root=tmp_path / "exports" / "validation",
    )

    after_mtime = db_path.stat().st_mtime
    assert before_mtime == after_mtime


def test_drift_pack_includes_status_classification(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    db_path.write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr(
        "scripts.build_single_truth_drift_pack.collect_workbook_overage",
        lambda **_kwargs: {"status": "ok", "ok": True, "overage_count": 0, "errors": []},
    )
    monkeypatch.setattr(
        "scripts.build_single_truth_drift_pack.collect_cogs_summary",
        lambda **_kwargs: {"unresolved_rows": 0, "unresolved_skus": 0},
    )
    monkeypatch.setattr(
        "scripts.build_single_truth_drift_pack.collect_on_delivery_residuals",
        lambda **_kwargs: {"residual_count": 0, "sample": []},
    )
    monkeypatch.setattr(
        "scripts.build_single_truth_drift_pack.collect_dim_sku_alignment",
        lambda **_kwargs: {"status": "ok", "weight_mismatch_count": 0, "errors": []},
    )
    monkeypatch.setattr(
        "scripts.build_single_truth_drift_pack.collect_paid_capital_snapshot",
        lambda **_kwargs: {"cash_actual_kzt": 1, "total_capital_paid_kzt": 1},
    )

    report = build_single_truth_drift_pack(
        db_path=db_path,
        as_of="2026-02-20",
        output_root=tmp_path / "exports" / "validation",
    )
    payload = json.loads(Path(report["json_path"]).read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"


def test_classify_pack_status_prioritizes_stop_line_then_critical() -> None:
    status, reasons = classify_pack_status(
        {
            "workbook_overage": {"status": "fail", "errors": ["anchor mismatch"]},
            "cogs_integrity": {"unresolved_rows": 0},
            "on_delivery_residuals": {"residual_count": 0},
            "dim_sku_alignment": {"status": "ok"},
        }
    )
    assert status == "STOP_LINE"
    assert any("workbook_overage" in reason for reason in reasons)
