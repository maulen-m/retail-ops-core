from __future__ import annotations

from pathlib import Path

import pytest

from scripts.generate_business_insides import generate_business_insides


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
