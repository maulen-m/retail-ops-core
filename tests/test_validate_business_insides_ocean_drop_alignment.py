from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.validate_business_insides_ocean_drop_alignment import (
    validate_business_insides_ocean_drop_alignment,
)


def test_alignment_fails_when_external_check_not_pass(monkeypatch, tmp_path: Path) -> None:
    snapshot_json = tmp_path / "BUSINESS_INSIDES_2026-02-26.json"
    snapshot_md = tmp_path / "BUSINESS_INSIDES_2026-02-26.md"
    snapshot_json.write_text(
        json.dumps(
            {
                "external_check": {"status": "skipped"},
                "last_7_days": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    snapshot_md.write_text("x", encoding="utf-8")

    monkeypatch.setattr(
        "scripts.validate_business_insides_ocean_drop_alignment.load_ocean_drop_anchor",
        lambda _p: {"ocean_drop_path_resolved": str(tmp_path / "anchor.csv"), "sha256": "abc"},
    )
    monkeypatch.setattr(
        "scripts.validate_business_insides_ocean_drop_alignment.generate_business_insides",
        lambda **_: {"latest_json_path": str(snapshot_json), "latest_path": str(snapshot_md)},
    )

    with pytest.raises(RuntimeError, match="external check is not PASS"):
        validate_business_insides_ocean_drop_alignment(
            db_path=tmp_path / "app.db",
            as_of=pd.Timestamp("2026-02-26").date(),
            output_dir=tmp_path,
            anchor_registry=tmp_path / "anchor_registry.json",
            report_root=tmp_path / "out",
            strict=True,
            window_days=7,
            volatility_days=14,
        )


def test_alignment_passes_when_bi_matches_reference(monkeypatch, tmp_path: Path) -> None:
    snapshot_json = tmp_path / "BUSINESS_INSIDES_2026-02-26.json"
    snapshot_md = tmp_path / "BUSINESS_INSIDES_2026-02-26.md"
    snapshot_json.write_text(
        json.dumps(
            {
                "external_check": {"status": "PASS", "ok": True},
                "last_7_days": [
                    {"date": "2026-02-25", "units_delivered": 1, "net_rev_kzt": 1000},
                    {"date": "2026-02-26", "units_delivered": 2, "net_rev_kzt": 2200},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    snapshot_md.write_text("x", encoding="utf-8")
    (tmp_path / "anchor.csv").write_text("x", encoding="utf-8")

    monkeypatch.setattr(
        "scripts.validate_business_insides_ocean_drop_alignment.load_ocean_drop_anchor",
        lambda _p: {"ocean_drop_path_resolved": str(tmp_path / "anchor.csv"), "sha256": "abc"},
    )
    monkeypatch.setattr(
        "scripts.validate_business_insides_ocean_drop_alignment.generate_business_insides",
        lambda **_: {"latest_json_path": str(snapshot_json), "latest_path": str(snapshot_md)},
    )
    monkeypatch.setattr(
        "scripts.validate_business_insides_ocean_drop_alignment.validate_sales_truth_ocean_drop_parity",
        lambda **_: {"status": "PASS"},
    )
    monkeypatch.setattr(
        "scripts.validate_business_insides_ocean_drop_alignment.build_ocean_drop_snapshot_dataframe",
        lambda **_: (
            pd.DataFrame(
                [
                    {
                        "status_internal": "DELIVERED",
                        "return_flag": 0,
                        "sale_date": "2026-02-25",
                        "quantity": 1.0,
                        "net_rev_kzt": 1000.0,
                    },
                    {
                        "status_internal": "DELIVERED",
                        "return_flag": 0,
                        "sale_date": "2026-02-26",
                        "quantity": 2.0,
                        "net_rev_kzt": 2200.0,
                    },
                ]
            ),
            {},
        ),
    )

    report = validate_business_insides_ocean_drop_alignment(
        db_path=tmp_path / "app.db",
        as_of=pd.Timestamp("2026-02-26").date(),
        output_dir=tmp_path,
        anchor_registry=tmp_path / "anchor_registry.json",
        report_root=tmp_path / "out",
        strict=True,
        window_days=7,
        volatility_days=14,
    )
    assert report["status"] == "PASS"
    assert Path(report["report_json"]).exists()
