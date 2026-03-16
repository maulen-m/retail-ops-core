from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts.generate_business_insides import (
    _run_ocean_drop_alignment_check,
    generate_business_insides,
)


def test_strict_business_insides_rejects_skipped_alignment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "scripts.generate_business_insides.compute_paid_capital_truth",
        lambda **_: {"cash_actual_kzt": 0.0},
    )
    monkeypatch.setattr(
        "scripts.generate_business_insides.compute_sales_metrics",
        lambda **_: {"unresolved_rows": 0},
    )
    monkeypatch.setattr(
        "scripts.generate_business_insides._load_anchor_metadata",
        lambda _registry: {
            "configured": True,
            "registry_path": "dummy",
            "ocean_drop_path_resolved": "dummy",
            "sha256": "dummy",
            "sha256_computed": "dummy",
            "as_of_end": "2026-02-26",
            "source": "test",
            "transaction_date_mode": "status_change_date",
        },
    )
    monkeypatch.setattr(
        "scripts.generate_business_insides._run_ocean_drop_alignment_check",
        lambda **_: {"status": "skipped", "ok": False, "reason": "no_anchor"},
    )

    with pytest.raises(RuntimeError, match="Strict BUSINESS_INSIDES alignment failed"):
        generate_business_insides(
            db_path=tmp_path / "app.db",
            bank_accounts_path=tmp_path / "bank.yml",
            as_of="2026-02-26",
            output_dir=tmp_path / "out",
            strict=True,
        )


def test_run_ocean_drop_alignment_check_returns_pass_no_overlap(monkeypatch, tmp_path: Path) -> None:
    anchor_csv = tmp_path / "anchor.csv"
    anchor_csv.write_text("x", encoding="utf-8")

    monkeypatch.setattr(
        "scripts.generate_business_insides._load_anchor_metadata",
        lambda _registry: {
            "configured": True,
            "registry_path": str(tmp_path / "anchor_registry.json"),
            "ocean_drop_path_resolved": str(anchor_csv),
            "sha256": "dummy",
            "sha256_computed": "dummy",
            "as_of_end": "2026-03-03",
            "source": "test",
            "transaction_date_mode": "delivered_status_date",
        },
    )

    def _raise_no_overlap(**_: object) -> dict[str, object]:
        raise RuntimeError("no reference rows in requested window_days=7")

    monkeypatch.setattr(
        "scripts.validate_sales_truth_ocean_drop_parity.validate_sales_truth_ocean_drop_parity",
        _raise_no_overlap,
    )
    monkeypatch.setattr(
        "scripts.generate_business_insides.build_ocean_drop_snapshot_dataframe",
        lambda **_: (
            pd.DataFrame(
                [
                    {
                        "status_internal": "DELIVERED",
                        "return_flag": 0,
                        "sale_date": "2026-02-26",
                        "quantity": 1.0,
                        "net_rev_kzt": 1000.0,
                    }
                ]
            ),
            {},
        ),
    )

    report = _run_ocean_drop_alignment_check(
        db_path=tmp_path / "app.db",
        as_of_date=date(2026, 3, 7),
        anchor_registry_path=tmp_path / "anchor_registry.json",
        output_root=tmp_path / "out",
        strict=True,
        window_days=7,
    )

    assert report["status"] == "PASS_NO_OVERLAP"
    assert report["ok"] is True
    assert report["reason"] == "no_reference_rows_in_requested_window"
    assert report["reference_window_overlap"] is False
    assert report["reference_max_sale_date"] == "2026-02-26"
