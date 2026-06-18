from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

import scripts.validate_cogs_realism_vs_forensic as realism_mod
from scripts.validate_cogs_realism_vs_forensic import (
    CogsRealismError,
    validate_cogs_realism_vs_forensic,
)


def _seed_db(db_path: Path, *, cogs_kzt: float, sale_date: str = "2026-01-05") -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE view_sales_line_truth (
                sale_date TEXT,
                store_code TEXT,
                sku_key TEXT,
                units REAL,
                net_rev_kzt REAL,
                cogs_kzt REAL
            )
            """
        )
        conn.execute(
            "INSERT INTO view_sales_line_truth VALUES (?,'ACMEWEAR','SKU_A',1,1000,?)",
            (sale_date, cogs_kzt),
        )
        conn.commit()
    finally:
        conn.close()


def _write_forensic_csv(path: Path, *, cogs_kzt: float) -> None:
    _write_forensic_csv_with_date(path, cogs_kzt=cogs_kzt, sale_date="2026-01-05")


def _write_forensic_csv_with_date(path: Path, *, cogs_kzt: float, sale_date: str) -> None:
    df = pd.DataFrame(
        [
            {
                "transaction_date": sale_date,
                "status_internal": "DELIVERED",
                "is_delivered_truth_row": 1,
                "mapped_sku_key": "SKU_A",
                "net_rev_kzt": 1000.0,
                "final_cogs_kzt": cogs_kzt,
            }
        ]
    )
    df.to_csv(path, index=False)


def _write_supersession_manifest(
    path: Path,
    *,
    truth_source: str = "webui_archive",
    parity_status: str = "PASS",
    audit_status: str = "PASS",
    relative_paths: bool = False,
    applies_when: dict[str, object] | None = None,
) -> None:
    parity_path = path.parent / "parity_summary.json"
    audit_path = path.parent / "audit_report.json"
    payload = {
        "version": 1,
        "truth_sources": {
            truth_source: {
                "decision": "SUPERSEDED",
                "reason": "legacy_forensic_stale",
                "required_reports": {
                    "monthly_economics_parity": {
                        "path": parity_path.name if relative_paths else str(parity_path),
                        "status": "PASS",
                    },
                    "audit_cogs_realism": {
                        "path": audit_path.name if relative_paths else str(audit_path),
                        "status": "PASS",
                    },
                },
            }
        },
    }
    if applies_when:
        payload["truth_sources"][truth_source]["applies_when"] = applies_when
    parity_path.write_text(
        json.dumps({"status": parity_status}, ensure_ascii=False),
        encoding="utf-8",
    )
    audit_path.write_text(
        json.dumps({"status": audit_status}, ensure_ascii=False),
        encoding="utf-8",
    )
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_validate_cogs_realism_vs_forensic_pass(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    forensic = tmp_path / "forensic.csv"
    _seed_db(db, cogs_kzt=500.0)
    _write_forensic_csv(forensic, cogs_kzt=500.0)
    payload = validate_cogs_realism_vs_forensic(
        start="2026-01-01",
        end="2026-01-31",
        strict=True,
        db_path=db,
        forensic_file=forensic,
        max_month_gap_pct=0.05,
        output_dir=tmp_path / "out",
    )
    assert payload["status"] == "PASS"


def test_validate_cogs_realism_vs_forensic_strict_fail(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    forensic = tmp_path / "forensic.csv"
    _seed_db(db, cogs_kzt=500.0)
    _write_forensic_csv(forensic, cogs_kzt=1000.0)
    with pytest.raises(CogsRealismError):
        validate_cogs_realism_vs_forensic(
            start="2026-01-01",
            end="2026-01-31",
            strict=True,
            db_path=db,
            forensic_file=forensic,
            max_month_gap_pct=0.05,
            output_dir=tmp_path / "out",
        )


def test_validate_cogs_realism_webui_honors_effective_db_quarantine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "app.db"
    forensic = tmp_path / "forensic.csv"
    ledger = tmp_path / "ledger"
    out_dir = tmp_path / "out"
    ledger.mkdir()
    out_dir.mkdir()
    _write_forensic_csv(forensic, cogs_kzt=500.0)

    monkeypatch.setattr(
        realism_mod,
        "build_webui_truth_projection",
        lambda **_kwargs: (
            pd.DataFrame(
                [
                    {
                        "order_id": "1",
                        "sale_date": "2026-01-05",
                        "store_code": "ACMEWEAR",
                        "sku_key": "SKU_A",
                        "units": 1.0,
                        "net_rev_kzt": 1000.0,
                        "cogs_kzt": 500.0,
                        "db_match_status": "MATCHED",
                    }
                ]
            ),
            {"projected_rows": 1, "missing_in_db_orders": 1},
        ),
    )

    (out_dir / "webui_vs_db_report.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "ledger_root": str(ledger.resolve()),
                "period": {"start": "2026-01-01", "end": "2026-01-31"},
                "missing_in_db_orders": 0,
                "original_missing_in_db_orders": 1,
            }
        ),
        encoding="utf-8",
    )

    payload = validate_cogs_realism_vs_forensic(
        start="2026-01-01",
        end="2026-01-31",
        strict=True,
        db_path=db,
        truth_source="webui_archive",
        ledger_root=ledger,
        as_of="2026-03-07",
        forensic_file=forensic,
        max_month_gap_pct=0.05,
        output_dir=out_dir,
    )
    assert payload["status"] == "PASS"
    assert payload["truth_errors"] == []


def test_validate_cogs_realism_vs_forensic_allows_explicit_webui_supersession(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "app.db"
    forensic = tmp_path / "forensic.csv"
    manifest = tmp_path / "cogs_forensic_reference.json"
    _seed_db(db, cogs_kzt=700.0)
    _write_forensic_csv(forensic, cogs_kzt=500.0)
    _write_supersession_manifest(manifest, parity_status="PASS", audit_status="PASS")
    monkeypatch.setattr(
        realism_mod,
        "build_webui_truth_projection",
        lambda **_kwargs: (
            pd.DataFrame(
                [
                    {
                        "order_id": "1",
                        "sale_date": "2026-01-05",
                        "store_code": "ACMEWEAR",
                        "sku_key": "SKU_A",
                        "units": 1.0,
                        "net_rev_kzt": 1000.0,
                        "cogs_kzt": 700.0,
                        "db_match_status": "MATCHED",
                    }
                ]
            ),
            {"projected_rows": 1, "missing_in_db_orders": 0},
        ),
    )

    payload = validate_cogs_realism_vs_forensic(
        start="2026-01-01",
        end="2026-01-31",
        strict=True,
        db_path=db,
        truth_source="webui_archive",
        forensic_file=forensic,
        forensic_reference_manifest=manifest,
        max_month_gap_pct=0.05,
        output_dir=tmp_path / "out",
    )
    assert payload["status"] == "PASS"
    assert payload["forensic_comparison_status"] == "SUPERSEDED"


def test_validate_cogs_realism_vs_forensic_supersession_requires_green_reports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "app.db"
    forensic = tmp_path / "forensic.csv"
    manifest = tmp_path / "cogs_forensic_reference.json"
    _seed_db(db, cogs_kzt=700.0)
    _write_forensic_csv(forensic, cogs_kzt=500.0)
    _write_supersession_manifest(manifest, parity_status="FAIL", audit_status="PASS")
    monkeypatch.setattr(
        realism_mod,
        "build_webui_truth_projection",
        lambda **_kwargs: (
            pd.DataFrame(
                [
                    {
                        "order_id": "1",
                        "sale_date": "2026-01-05",
                        "store_code": "ACMEWEAR",
                        "sku_key": "SKU_A",
                        "units": 1.0,
                        "net_rev_kzt": 1000.0,
                        "cogs_kzt": 700.0,
                        "db_match_status": "MATCHED",
                    }
                ]
            ),
            {"projected_rows": 1, "missing_in_db_orders": 0},
        ),
    )

    with pytest.raises(CogsRealismError):
        validate_cogs_realism_vs_forensic(
            start="2026-01-01",
            end="2026-01-31",
            strict=True,
            db_path=db,
            truth_source="webui_archive",
            forensic_file=forensic,
            forensic_reference_manifest=manifest,
            max_month_gap_pct=0.05,
            output_dir=tmp_path / "out",
        )


def test_validate_cogs_realism_vs_forensic_supersession_resolves_relative_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "app.db"
    forensic = tmp_path / "forensic.csv"
    manifest = tmp_path / "cogs_forensic_reference.json"
    _seed_db(db, cogs_kzt=700.0)
    _write_forensic_csv(forensic, cogs_kzt=500.0)
    _write_supersession_manifest(
        manifest,
        parity_status="PASS",
        audit_status="PASS",
        relative_paths=True,
    )
    monkeypatch.setattr(
        realism_mod,
        "build_webui_truth_projection",
        lambda **_kwargs: (
            pd.DataFrame(
                [
                    {
                        "order_id": "1",
                        "sale_date": "2026-01-05",
                        "store_code": "ACMEWEAR",
                        "sku_key": "SKU_A",
                        "units": 1.0,
                        "net_rev_kzt": 1000.0,
                        "cogs_kzt": 700.0,
                        "db_match_status": "MATCHED",
                    }
                ]
            ),
            {"projected_rows": 1, "missing_in_db_orders": 0},
        ),
    )

    payload = validate_cogs_realism_vs_forensic(
        start="2026-01-01",
        end="2026-01-31",
        strict=True,
        db_path=db,
        truth_source="webui_archive",
        forensic_file=forensic,
        forensic_reference_manifest=manifest,
        max_month_gap_pct=0.05,
        output_dir=tmp_path / "out",
    )
    assert payload["status"] == "PASS"


def test_validate_cogs_realism_vs_forensic_allows_bounded_db_post_forensic_supersession(
    tmp_path: Path,
) -> None:
    db = tmp_path / "app.db"
    forensic = tmp_path / "forensic.csv"
    manifest = tmp_path / "cogs_forensic_reference.json"
    _seed_db(db, cogs_kzt=700.0, sale_date="2026-03-05")
    _write_forensic_csv_with_date(forensic, cogs_kzt=500.0, sale_date="2026-02-24")
    _write_supersession_manifest(
        manifest,
        truth_source="db",
        parity_status="PASS",
        audit_status="PASS",
        applies_when={
            "requires_no_forensic_rows_in_window": True,
            "window_start_after_forensic_max_sale_date": True,
        },
    )

    payload = validate_cogs_realism_vs_forensic(
        start="2026-03-01",
        end="2026-03-31",
        strict=True,
        db_path=db,
        truth_source="db",
        forensic_file=forensic,
        forensic_reference_manifest=manifest,
        max_month_gap_pct=0.05,
        output_dir=tmp_path / "out",
    )

    assert payload["status"] == "PASS"
    assert payload["forensic_comparison_status"] == "SUPERSEDED"
    assert payload["forensic_rows_in_window"] == 0
    assert payload["forensic_max_sale_date"] == "2026-02-24"


def test_validate_cogs_realism_vs_forensic_db_supersession_does_not_mask_in_window_mismatch(
    tmp_path: Path,
) -> None:
    db = tmp_path / "app.db"
    forensic = tmp_path / "forensic.csv"
    manifest = tmp_path / "cogs_forensic_reference.json"
    _seed_db(db, cogs_kzt=700.0, sale_date="2026-02-24")
    _write_forensic_csv_with_date(forensic, cogs_kzt=500.0, sale_date="2026-02-24")
    _write_supersession_manifest(
        manifest,
        truth_source="db",
        parity_status="PASS",
        audit_status="PASS",
        applies_when={
            "requires_no_forensic_rows_in_window": True,
            "window_start_after_forensic_max_sale_date": True,
        },
    )

    with pytest.raises(CogsRealismError):
        validate_cogs_realism_vs_forensic(
            start="2026-02-01",
            end="2026-02-28",
            strict=True,
            db_path=db,
            truth_source="db",
            forensic_file=forensic,
            forensic_reference_manifest=manifest,
            max_month_gap_pct=0.05,
            output_dir=tmp_path / "out",
        )


def test_validate_cogs_realism_vs_forensic_db_supersession_requires_window_after_coverage(
    tmp_path: Path,
) -> None:
    db = tmp_path / "app.db"
    forensic = tmp_path / "forensic.csv"
    manifest = tmp_path / "cogs_forensic_reference.json"
    _seed_db(db, cogs_kzt=700.0, sale_date="2025-05-05")
    _write_forensic_csv_with_date(forensic, cogs_kzt=500.0, sale_date="2026-02-24")
    _write_supersession_manifest(
        manifest,
        truth_source="db",
        parity_status="PASS",
        audit_status="PASS",
        applies_when={
            "requires_no_forensic_rows_in_window": True,
            "window_start_after_forensic_max_sale_date": True,
        },
    )

    with pytest.raises(CogsRealismError):
        validate_cogs_realism_vs_forensic(
            start="2025-05-01",
            end="2025-05-31",
            strict=True,
            db_path=db,
            truth_source="db",
            forensic_file=forensic,
            forensic_reference_manifest=manifest,
            max_month_gap_pct=0.05,
            output_dir=tmp_path / "out",
        )
