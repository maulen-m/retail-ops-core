from __future__ import annotations

import os
import sqlite3
import time
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts.build_owner_pnl_report import _build_parser, OwnerPnlError, build_owner_pnl_report


def _init_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE sales_fact_v2 (
            order_id TEXT,
            order_date DATE,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            store_code TEXT,
            quantity INTEGER,
            cogs REAL,
            net_rev REAL,
            profit REAL,
            status TEXT,
            return_flag INTEGER
        );
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            cogs_kzt REAL,
            base_cost_cny REAL,
            weight_kg REAL
        );
        CREATE TABLE dim_sku_size (
            sku_id TEXT PRIMARY KEY,
            sku_key TEXT,
            my_size TEXT
        );
        CREATE TABLE ads_spend_sidecar_daily (
            date TEXT,
            store_code TEXT,
            mapped_cost_kzt REAL,
            unmapped_cost_kzt REAL,
            total_cost_kzt REAL,
            mapped_rows INTEGER,
            unmapped_rows INTEGER,
            mapping_coverage_pct REAL
        );
        CREATE TABLE fact_cashflow_commitments (
            commit_date TEXT,
            commit_type TEXT,
            amount_kzt REAL
        );
        """
    )
    conn.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, cogs, net_rev, profit, status, return_flag)
        VALUES ('O1', '2026-01-15', 'SKU_A', 'SKU_A_M', 'M', 'UNIVERSAL', 2, 4000, 10000, 6000, 'DELIVERED', 0)
        """
    )
    conn.execute(
        "INSERT INTO dim_sku (sku_key, cogs_kzt, base_cost_cny, weight_kg) VALUES ('SKU_A', 2000, 20, 0.8)"
    )
    conn.execute(
        "INSERT INTO dim_sku_size (sku_id, sku_key, my_size) VALUES ('SKU_A_M', 'SKU_A', 'M')"
    )
    conn.execute(
        """
        INSERT INTO ads_spend_sidecar_daily
        (date, store_code, mapped_cost_kzt, unmapped_cost_kzt, total_cost_kzt, mapped_rows, unmapped_rows, mapping_coverage_pct)
        VALUES ('2026-01-15', 'UNIVERSAL', 900, 100, 1000, 9, 1, 90.0)
        """
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_commitments
        (commit_date, commit_type, amount_kzt)
        VALUES ('2026-01-20', 'OPEX', 500)
        """
    )
    conn.commit()
    conn.close()


def _write_mapped_csv(path: Path, *, tx_date: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "transaction_date": tx_date,
                "store_code": "UNIVERSAL",
                "order_id": "O1",
                "quantity": "2",
                "net_rev_kzt": "10000",
                "status_internal": "DELIVERED",
                "return_flag": "0",
                "transaction_date_source": "status_change_date",
            }
        ]
    ).to_csv(path, index=False, encoding="utf-8")


def _write_opex_schedule(path: Path) -> None:
    source = path.parent / "source.xlsx"
    source.write_text("xlsx", encoding="utf-8")
    path.write_text(f"source_xlsx: {source}\n", encoding="utf-8")


def _write_webui_validation(
    validation_dir: Path,
    *,
    decision: str = "CRM_REMAINS_CHRONOLOGY_AUTHORITY",
    workbook_status: str = "PASS",
    db_status: str = "PASS",
) -> None:
    validation_dir.mkdir(parents=True, exist_ok=True)
    (validation_dir / "shipped_day_authority_decision.json").write_text(
        '{"status":"PASS","ok":true,"decision":"%s"}\n' % decision,
        encoding="utf-8",
    )
    (validation_dir / "sales_against_workbook_report.json").write_text(
        '{"status":"%s","ok":%s}\n' % (workbook_status, "true" if workbook_status == "PASS" else "false"),
        encoding="utf-8",
    )
    for name, status in {
        "webui_vs_db_report.json": db_status,
        "ads_offer_universe_report.json": "PASS",
        "ads_spend_reality_report.json": "PASS",
        "cogs_completeness_report.json": "PASS",
        "cogs_realism_report.json": "PASS",
        "order_status_audit_report.json": "PASS",
    }.items():
        (validation_dir / name).write_text(
            '{"status":"%s","ok":%s}\n' % (status, "true" if status == "PASS" else "false"),
            encoding="utf-8",
        )


def test_build_owner_pnl_report_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    mapped_csv = tmp_path / "mapped" / "2026-01-01_to_2026-03-02" / "ArchiveSales_ALL_STORES_statusdate_mapped.csv"
    _write_mapped_csv(mapped_csv, tx_date="2026-01-15")
    opex_schedule = tmp_path / "opex_schedule.yaml"
    _write_opex_schedule(opex_schedule)

    ads_source = tmp_path / "ads.db"
    ads_source.write_text("ok", encoding="utf-8")
    monkeypatch.setenv("AB_ADS_DB_PATH", str(ads_source))

    report = build_owner_pnl_report(
        db_path=db_path,
        as_of=date(2026, 3, 2),
        since=date(2026, 1, 1),
        mapped_root=tmp_path / "mapped",
        mapped_csv=mapped_csv,
        output_root=tmp_path / "owner",
        parity_output_root=tmp_path / "parity",
        include_store_breakdown=True,
        strict=True,
        statusdate_cutover=date(2026, 1, 1),
        opex_schedule_yaml=opex_schedule,
    )
    assert report["status"] == "PASS"
    jan = next(r for r in report["monthly_totals"] if r["sale_month"] == "2026-01")
    assert jan["decision_grade"] is True
    assert jan["net_rev_kzt"] == 10000.0
    assert jan["profit_after_ads_kzt"] == pytest.approx(
        (jan["net_rev_kzt"] or 0.0) - (jan["cogs_kzt"] or 0.0) - (jan["ads_kzt"] or 0.0),
        abs=0.01,
    )
    assert Path(report["ascii_path"]).exists()


def test_build_owner_pnl_caps_statusdate_coverage_at_100(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    mapped_csv = tmp_path / "mapped" / "2026-01-01_to_2026-03-02" / "ArchiveSales_ALL_STORES_statusdate_mapped.csv"
    _write_mapped_csv(mapped_csv, tx_date="2026-01-15")
    opex_schedule = tmp_path / "opex_schedule.yaml"
    _write_opex_schedule(opex_schedule)

    ads_source = tmp_path / "ads.db"
    ads_source.write_text("ok", encoding="utf-8")
    monkeypatch.setenv("AB_ADS_DB_PATH", str(ads_source))

    monkeypatch.setattr(
        "scripts.build_owner_pnl_report.build_webui_truth_projection",
        lambda **_kwargs: (
            pd.DataFrame(
                [
                    {
                        "order_id": "O1",
                        "sale_date": "2026-01-15",
                        "store_code": "UNIVERSAL",
                        "sku_key": "SKU_A",
                        "units": 2.0,
                        "net_rev_kzt": 10000.0,
                        "cogs_kzt": 4000.0,
                        "db_match_status": "MATCHED",
                    },
                    {
                        "order_id": "O2",
                        "sale_date": "2026-01-16",
                        "store_code": "UNIVERSAL",
                        "sku_key": "SKU_A",
                        "units": 1.0,
                        "net_rev_kzt": 5000.0,
                        "cogs_kzt": 2000.0,
                        "db_match_status": "MATCHED",
                    },
                ]
            ),
            {"projected_rows": 2, "missing_in_db_orders": 0},
        ),
    )

    validation = tmp_path / "validation"
    _write_webui_validation(validation)
    ledger = tmp_path / "ledger"
    ledger.mkdir()

    report = build_owner_pnl_report(
        db_path=db_path,
        as_of=date(2026, 3, 2),
        since=date(2026, 1, 1),
        mapped_root=tmp_path / "mapped",
        mapped_csv=mapped_csv,
        output_root=tmp_path / "owner",
        parity_output_root=tmp_path / "parity",
        include_store_breakdown=True,
        strict=False,
        truth_source="webui_archive",
        validation_dir=validation,
        ledger_root=ledger,
        statusdate_cutover=date(2026, 1, 1),
        opex_schedule_yaml=opex_schedule,
    )

    monthly = next(row for row in report["monthly_totals"] if row["sale_month"] == "2026-01")
    store_row = next(row for row in report["monthly_by_store"] if row["store_code"] == "UNIVERSAL")
    assert monthly["statusdate_coverage_pct"] == pytest.approx(100.0)
    assert store_row["statusdate_coverage_pct"] == pytest.approx(100.0)


def test_build_owner_pnl_report_strict_uses_live_sidecar_when_ads_source_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    mapped_csv = tmp_path / "mapped" / "2026-01-01_to_2026-03-02" / "ArchiveSales_ALL_STORES_statusdate_mapped.csv"
    _write_mapped_csv(mapped_csv, tx_date="2026-01-15")
    opex_schedule = tmp_path / "opex_schedule.yaml"
    _write_opex_schedule(opex_schedule)

    ads_source = tmp_path / "ads.db"
    ads_source.write_text("stale", encoding="utf-8")
    stale_epoch = time.time() - (80 * 3600)
    os.utime(ads_source, (stale_epoch, stale_epoch))
    monkeypatch.setenv("AB_ADS_DB_PATH", str(ads_source))

    report = build_owner_pnl_report(
        db_path=db_path,
        as_of=date(2026, 3, 2),
        since=date(2026, 1, 1),
        mapped_root=tmp_path / "mapped",
        mapped_csv=mapped_csv,
        output_root=tmp_path / "owner",
        parity_output_root=tmp_path / "parity",
        include_store_breakdown=False,
        strict=True,
        opex_schedule_yaml=opex_schedule,
    )

    assert report["status"] == "PASS"
    assert report["ads_readiness"]["ok"] is True


def test_build_owner_pnl_locks_pre_cutover_month(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    mapped_csv = tmp_path / "mapped" / "2025-12-01_to_2026-03-02" / "ArchiveSales_ALL_STORES_statusdate_mapped.csv"
    _write_mapped_csv(mapped_csv, tx_date="2025-12-15")
    opex_schedule = tmp_path / "opex_schedule.yaml"
    _write_opex_schedule(opex_schedule)

    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM sales_fact_v2")
    conn.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, cogs, net_rev, profit, status, return_flag)
        VALUES ('O2', '2025-12-15', 'SKU_A', 'SKU_A_M', 'M', 'UNIVERSAL', 1, 2000, 6000, 4000, 'DELIVERED', 0)
        """
    )
    conn.commit()
    conn.close()

    ads_source = tmp_path / "ads.db"
    ads_source.write_text("ok", encoding="utf-8")
    monkeypatch.setenv("AB_ADS_DB_PATH", str(ads_source))

    report = build_owner_pnl_report(
        db_path=db_path,
        as_of=date(2026, 3, 2),
        since=date(2025, 12, 1),
        mapped_root=tmp_path / "mapped",
        mapped_csv=mapped_csv,
        output_root=tmp_path / "owner",
        parity_output_root=tmp_path / "parity",
        include_store_breakdown=False,
        strict=False,
        opex_schedule_yaml=opex_schedule,
    )
    dec = next(r for r in report["monthly_totals"] if r["sale_month"] == "2025-12")
    assert dec["decision_grade"] is False
    assert dec["net_rev_kzt"] is None
    assert dec["profit_after_ads_kzt"] is None


def test_build_owner_pnl_parser_default_cutover() -> None:
    parser = _build_parser()
    args = parser.parse_args(["--as-of", "2026-03-04"])
    assert args.statusdate_cutover == "2026-02-27"


def test_build_owner_pnl_strict_fails_when_opex_required_and_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM fact_cashflow_commitments")
    conn.commit()
    conn.close()

    mapped_csv = tmp_path / "mapped" / "2026-01-01_to_2026-03-02" / "ArchiveSales_ALL_STORES_statusdate_mapped.csv"
    _write_mapped_csv(mapped_csv, tx_date="2026-01-15")
    opex_schedule = tmp_path / "missing_schedule.yaml"

    ads_source = tmp_path / "ads.db"
    ads_source.write_text("ok", encoding="utf-8")
    monkeypatch.setenv("AB_ADS_DB_PATH", str(ads_source))

    with pytest.raises(OwnerPnlError):
        build_owner_pnl_report(
            db_path=db_path,
            as_of=date(2026, 3, 2),
            since=date(2026, 1, 1),
            mapped_root=tmp_path / "mapped",
            mapped_csv=mapped_csv,
            output_root=tmp_path / "owner",
            parity_output_root=tmp_path / "parity",
            include_store_breakdown=False,
            strict=True,
            require_opex_for_net_publication=True,
            opex_schedule_yaml=opex_schedule,
        )


def test_build_owner_pnl_webui_fallback_passes_with_workbook_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    mapped_csv = tmp_path / "mapped" / "2026-01-01_to_2026-03-02" / "ArchiveSales_ALL_STORES_statusdate_mapped.csv"
    _write_mapped_csv(mapped_csv, tx_date="2026-01-15")
    opex_schedule = tmp_path / "opex_schedule.yaml"
    _write_opex_schedule(opex_schedule)
    ads_source = tmp_path / "ads.db"
    ads_source.write_text("ok", encoding="utf-8")
    monkeypatch.setenv("AB_ADS_DB_PATH", str(ads_source))

    validation = tmp_path / "validation"
    _write_webui_validation(validation)
    ledger = tmp_path / "ledger"
    ledger.mkdir()

    monkeypatch.setattr(
        "scripts.build_owner_pnl_report.build_webui_truth_projection",
        lambda **_kwargs: (
            pd.DataFrame(
                [
                    {
                        "order_id": "O1",
                        "sale_date": "2026-01-15",
                        "store_code": "UNIVERSAL",
                        "sku_key": "SKU_A",
                        "units": 2.0,
                        "net_rev_kzt": 10000.0,
                        "cogs_kzt": 4000.0,
                        "db_match_status": "MATCHED",
                    }
                ]
            ),
            {"projected_rows": 1, "missing_in_db_orders": 0},
        ),
    )

    report = build_owner_pnl_report(
        db_path=db_path,
        as_of=date(2026, 3, 2),
        since=date(2026, 1, 1),
        mapped_root=tmp_path / "mapped",
        mapped_csv=mapped_csv,
        output_root=tmp_path / "owner",
        parity_output_root=tmp_path / "parity",
        include_store_breakdown=True,
        strict=True,
        truth_source="webui_archive",
        validation_dir=validation,
        ledger_root=ledger,
        statusdate_cutover=date(2026, 1, 1),
        opex_schedule_yaml=opex_schedule,
    )

    assert report["status"] == "PASS"


def test_build_owner_pnl_webui_fallback_fails_when_workbook_gate_red(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    mapped_csv = tmp_path / "mapped" / "2026-01-01_to_2026-03-02" / "ArchiveSales_ALL_STORES_statusdate_mapped.csv"
    _write_mapped_csv(mapped_csv, tx_date="2026-01-15")
    opex_schedule = tmp_path / "opex_schedule.yaml"
    _write_opex_schedule(opex_schedule)
    ads_source = tmp_path / "ads.db"
    ads_source.write_text("ok", encoding="utf-8")
    monkeypatch.setenv("AB_ADS_DB_PATH", str(ads_source))

    validation = tmp_path / "validation"
    _write_webui_validation(validation, workbook_status="FAIL")
    ledger = tmp_path / "ledger"
    ledger.mkdir()

    monkeypatch.setattr(
        "scripts.build_owner_pnl_report.build_webui_truth_projection",
        lambda **_kwargs: (
            pd.DataFrame(
                [
                    {
                        "order_id": "O1",
                        "sale_date": "2026-01-15",
                        "store_code": "UNIVERSAL",
                        "sku_key": "SKU_A",
                        "units": 2.0,
                        "net_rev_kzt": 10000.0,
                        "cogs_kzt": 4000.0,
                        "db_match_status": "MATCHED",
                    }
                ]
            ),
            {"projected_rows": 1, "missing_in_db_orders": 0},
        ),
    )

    with pytest.raises(OwnerPnlError):
        build_owner_pnl_report(
            db_path=db_path,
            as_of=date(2026, 3, 2),
            since=date(2026, 1, 1),
            mapped_root=tmp_path / "mapped",
            mapped_csv=mapped_csv,
            output_root=tmp_path / "owner",
            parity_output_root=tmp_path / "parity",
            include_store_breakdown=True,
            strict=True,
            truth_source="webui_archive",
            validation_dir=validation,
            ledger_root=ledger,
            statusdate_cutover=date(2026, 1, 1),
            opex_schedule_yaml=opex_schedule,
        )


def test_build_owner_pnl_webui_uses_effective_missing_in_db_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    mapped_csv = tmp_path / "mapped" / "2026-01-01_to_2026-03-02" / "ArchiveSales_ALL_STORES_statusdate_mapped.csv"
    _write_mapped_csv(mapped_csv, tx_date="2026-01-15")
    opex_schedule = tmp_path / "opex_schedule.yaml"
    _write_opex_schedule(opex_schedule)
    ads_source = tmp_path / "ads.db"
    ads_source.write_text("ok", encoding="utf-8")
    monkeypatch.setenv("AB_ADS_DB_PATH", str(ads_source))

    validation = tmp_path / "validation"
    _write_webui_validation(validation)
    (validation / "webui_vs_db_report.json").write_text(
        (
            "{"
            "\"status\":\"PASS\","
            "\"ok\":true,"
            "\"missing_in_db_orders\":0,"
            "\"period\":{\"start\":\"2026-01-01\",\"end\":\"2026-03-02\"},"
            "\"ledger_root\":\"%s\""
            "}\n"
        )
        % str((tmp_path / "ledger").resolve()),
        encoding="utf-8",
    )
    ledger = tmp_path / "ledger"
    ledger.mkdir(exist_ok=True)

    monkeypatch.setattr(
        "scripts.build_owner_pnl_report.build_webui_truth_projection",
        lambda **_kwargs: (
            pd.DataFrame(
                [
                    {
                        "order_id": "O1",
                        "sale_date": "2026-01-15",
                        "store_code": "UNIVERSAL",
                        "sku_key": "SKU_A",
                        "units": 2.0,
                        "net_rev_kzt": 10000.0,
                        "cogs_kzt": 4000.0,
                        "db_match_status": "MATCHED",
                    }
                ]
            ),
            {"projected_rows": 1, "missing_in_db_orders": 5},
        ),
    )

    report = build_owner_pnl_report(
        db_path=db_path,
        as_of=date(2026, 3, 2),
        since=date(2026, 1, 1),
        mapped_root=tmp_path / "mapped",
        mapped_csv=mapped_csv,
        output_root=tmp_path / "owner",
        parity_output_root=tmp_path / "parity",
        include_store_breakdown=False,
        strict=True,
        truth_source="webui_archive",
        validation_dir=validation,
        ledger_root=ledger,
        statusdate_cutover=date(2026, 1, 1),
        opex_schedule_yaml=opex_schedule,
    )

    assert report["status"] == "PASS"
    assert report["webui_truth_projection"]["missing_in_db_orders"] == 0
