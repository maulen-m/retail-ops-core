from __future__ import annotations

import csv
import hashlib
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from core.sales import ensure_sales_truth_views
import scripts.validate_monthly_cash_reconciliation as reconciliation
from scripts.validate_monthly_cash_reconciliation import (
    CashReconciliationError,
    DEFAULT_TOLERANCE_FRACTION,
    validate_monthly_cash_reconciliation,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _init_db(
    path: Path,
    *,
    sale_amount: float = 1000.0,
    cash_amount: float = 1000.0,
    prepare_views: bool = True,
) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE sales_fact_v2 (
            order_id TEXT,
            order_date TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            store_code TEXT,
            quantity INTEGER,
            sell_price_kzt REAL,
            delivery_fee REAL,
            cogs REAL,
            net_rev REAL,
            profit REAL,
            status TEXT,
            return_flag INTEGER
        );
        CREATE TABLE fact_cashflow_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_date TEXT,
            event_type TEXT,
            amount_kzt REAL,
            store_code TEXT,
            sku_key TEXT,
            sku_id TEXT,
            ref_type TEXT,
            ref_id TEXT,
            source TEXT,
            notes TEXT,
            run_id TEXT,
            event_hash TEXT
        );
        CREATE TABLE fact_order_entries_kaspi (
            entry_id TEXT PRIMARY KEY,
            order_id TEXT,
            store_code TEXT,
            quantity REAL,
            offer_id TEXT
        );
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            base_cost_cny REAL,
            weight_kg REAL
        );
        """
    )
    conn.execute("INSERT INTO dim_sku (sku_key, base_cost_cny, weight_kg) VALUES ('SKU_A', 10, 0.5)")
    conn.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity,
         sell_price_kzt, delivery_fee, cogs, net_rev, profit, status, return_flag)
        VALUES ('O1', '2026-02-15', 'SKU_A', 'SKU_A_M', 'M', 'UNIVERSAL', 1,
                ?, 0, 400, ?, 600, 'DELIVERED', 0)
        """,
        (sale_amount / 0.84, sale_amount),
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events
        (event_date, event_type, amount_kzt, store_code, ref_type, ref_id, source)
        VALUES ('2026-03-01', 'CASH_IN', ?, 'UNIVERSAL', 'ORDER', 'O1', 'ORDER_MODELLED')
        """,
        (cash_amount,),
    )
    if prepare_views:
        ensure_sales_truth_views(conn)
    conn.commit()
    conn.close()


def test_validate_monthly_cash_reconciliation_pass(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path, sale_amount=1000.0, cash_amount=980.0)
    db_sha_before = _sha256(db_path)

    report = validate_monthly_cash_reconciliation(
        db_path=db_path,
        since=date(2026, 2, 1),
        until=date(2026, 3, 20),
        output_root=tmp_path / "out",
        tolerance_pct=0.05,
        statusdate_cutover=date(2026, 1, 1),
        require_covered_pairs=True,
        strict=True,
    )
    assert report["status"] == "PASS"
    assert report["covered_pairs"] >= 1
    assert report["rows"][0]["sale_month"] == "2026-02"
    assert report["rows"][0]["cash_net_rev_kzt"] == 980.0
    assert report["order_fallback_resolution_count"] == 1
    assert _sha256(db_path) == db_sha_before


def test_cli_default_tolerance_is_one_percent() -> None:
    args = reconciliation._build_parser().parse_args(["--as-of", "2026-03-20"])
    assert args.tolerance_pct == DEFAULT_TOLERANCE_FRACTION == 0.01


def test_validate_monthly_cash_reconciliation_fails_on_large_diff(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path, sale_amount=1000.0, cash_amount=200.0)
    db_sha_before = _sha256(db_path)

    with pytest.raises(CashReconciliationError):
        validate_monthly_cash_reconciliation(
            db_path=db_path,
            since=date(2026, 2, 1),
            until=date(2026, 3, 20),
            output_root=tmp_path / "out",
            tolerance_pct=0.05,
            statusdate_cutover=date(2026, 1, 1),
            require_covered_pairs=True,
            strict=True,
        )
    assert _sha256(db_path) == db_sha_before


def test_validate_monthly_cash_reconciliation_requires_prepared_view_without_mutation(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path, prepare_views=False)
    db_sha_before = _sha256(db_path)

    with pytest.raises(CashReconciliationError, match="required view missing"):
        validate_monthly_cash_reconciliation(
            db_path=db_path,
            since=date(2026, 2, 1),
            until=date(2026, 3, 20),
            output_root=tmp_path / "out",
            tolerance_pct=0.05,
            statusdate_cutover=date(2026, 1, 1),
            require_covered_pairs=True,
            strict=True,
        )
    assert _sha256(db_path) == db_sha_before


def test_nonproduction_db_cannot_use_canonical_output_root(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    db_sha_before = _sha256(db_path)
    canonical_output_root = tmp_path / "canonical_cash_reconciliation"
    monkeypatch.setattr(reconciliation, "DEFAULT_OUTPUT_ROOT", canonical_output_root)

    with pytest.raises(CashReconciliationError, match="explicit noncanonical output_root"):
        validate_monthly_cash_reconciliation(
            db_path=db_path,
            since=date(2026, 2, 1),
            until=date(2026, 3, 20),
            output_root=canonical_output_root,
            tolerance_pct=0.05,
            statusdate_cutover=date(2026, 1, 1),
            require_covered_pairs=True,
            strict=True,
        )
    assert not canonical_output_root.exists()
    assert _sha256(db_path) == db_sha_before


def test_order_entry_cash_precedes_order_cash_without_double_counting(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path, sale_amount=1000.0, cash_amount=1000.0)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO fact_order_entries_kaspi (entry_id, order_id, store_code, quantity, offer_id)
        VALUES ('E1', 'O1', 'UNIVERSAL', 1, 'SKU_A_M')
        """
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events
        (event_date, event_type, amount_kzt, store_code, ref_type, ref_id, source)
        VALUES ('2026-03-02', 'CASH_IN', 1000, 'UNIVERSAL', 'ORDER_ENTRY', 'E1', 'ORDER_MODELLED')
        """
    )
    conn.commit()
    conn.close()

    report = validate_monthly_cash_reconciliation(
        db_path=db_path,
        since=date(2026, 2, 1),
        until=date(2026, 3, 20),
        output_root=tmp_path / "out",
        tolerance_pct=0.01,
        statusdate_cutover=date(2026, 1, 1),
        require_covered_pairs=True,
        strict=True,
    )

    assert report["status"] == "PASS"
    assert report["rows"][0]["cash_net_rev_kzt"] == 1000.0
    assert report["order_entry_resolution_count"] == 1
    assert report["order_fallback_resolution_count"] == 0
    assert report["dual_ref_type_order_count"] == 1


def test_negative_cash_in_reversal_is_summed_in_order_cohort(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path, sale_amount=800.0, cash_amount=1000.0)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO fact_cashflow_events
        (event_date, event_type, amount_kzt, store_code, ref_type, ref_id, source)
        VALUES ('2026-04-01', 'CASH_IN', -200, 'UNIVERSAL', 'ORDER', 'O1', 'ORDER_MODELLED')
        """
    )
    conn.commit()
    conn.close()

    report = validate_monthly_cash_reconciliation(
        db_path=db_path,
        since=date(2026, 2, 1),
        until=date(2026, 4, 20),
        output_root=tmp_path / "out",
        tolerance_pct=0.01,
        statusdate_cutover=date(2026, 1, 1),
        require_covered_pairs=True,
        strict=True,
    )

    assert report["rows"][0]["cash_net_rev_kzt"] == 800.0
    assert report["rows"][0]["event_days"] == 2


def test_duplicate_chosen_cash_evidence_fails_closed(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path, sale_amount=1000.0, cash_amount=1000.0)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO fact_cashflow_events
            (event_date, event_type, amount_kzt, store_code, ref_type, ref_id, source)
            VALUES ('2026-03-01', 'CASH_IN', 1000, 'UNIVERSAL', 'ORDER', 'O1', 'SECOND_RUN')
            """
        )
        conn.commit()

    report = validate_monthly_cash_reconciliation(
        db_path=db_path,
        since=date(2026, 2, 1),
        until=date(2026, 3, 20),
        output_root=tmp_path / "out",
        tolerance_pct=0.01,
        statusdate_cutover=date(2026, 1, 1),
        require_covered_pairs=True,
        strict=False,
    )

    assert report["status"] == "FAIL"
    assert report["duplicate_chosen_cash_order_count"] == 1
    assert "CASH_RECON_DUPLICATE_CHOSEN_CASH" in report["error_codes"]
    assert report["rows"][0]["scope_complete"] is False
    with Path(report["order_rows_csv"]).open(encoding="utf-8", newline="") as handle:
        order_row = next(csv.DictReader(handle))
    assert order_row["cash_resolution"] == "AMBIGUOUS_DUPLICATE_CASH"


def test_sales_amount_formula_must_reproduce_effective_dated_canonical_formula(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path, sale_amount=1000.0, cash_amount=1000.0)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE sales_fact_v2 SET sell_price_kzt=1000, delivery_fee=0, net_rev=1000"
        )
        conn.commit()

    report = validate_monthly_cash_reconciliation(
        db_path=db_path,
        since=date(2026, 2, 1),
        until=date(2026, 3, 20),
        output_root=tmp_path / "out",
        tolerance_pct=0.01,
        statusdate_cutover=date(2026, 1, 1),
        require_covered_pairs=True,
        strict=False,
    )

    assert report["status"] == "FAIL"
    assert report["sales_amount_formula_proof_available"] is True
    assert report["sales_amount_formula_unproven_order_count"] == 1
    assert "CASH_RECON_SALES_AMOUNT_UNPROVEN" in report["error_codes"]
    assert report["rows"][0]["scope_complete"] is False


def test_anchor_published_amount_must_match_formula_proven_source_line(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path, sale_amount=1000.0, cash_amount=995.0)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE fact_sales_workbook_anchor (
                order_id TEXT,
                store_code TEXT,
                sale_date TEXT,
                quantity REAL,
                net_rev_kzt REAL,
                total_price_kzt REAL,
                source_file TEXT
            );
            INSERT INTO fact_sales_workbook_anchor (
                order_id, store_code, sale_date, quantity, net_rev_kzt,
                total_price_kzt, source_file
            ) VALUES (
                'O1', 'UNIVERSAL', '2026-02-15', 1, 995, 1000,
                'SALES_KSP_CRM_V3.xlsx'
            );
            """
        )
        ensure_sales_truth_views(conn)
        conn.commit()

    report = validate_monthly_cash_reconciliation(
        db_path=db_path,
        since=date(2026, 2, 1),
        until=date(2026, 3, 20),
        output_root=tmp_path / "out",
        tolerance_pct=0.01,
        statusdate_cutover=date(2026, 1, 1),
        require_covered_pairs=False,
        strict=False,
    )

    assert report["rows"][0]["db_net_rev_kzt"] == 995.0
    assert report["sales_amount_formula_unproven_order_count"] == 1
    assert report["sales_amount_source_formula_proven_order_count"] == 1
    assert report["sales_amount_publication_binding_unproven_order_count"] == 1
    assert report["sales_amount_published_source_mismatch_order_count"] == 1
    assert "CASH_RECON_SELECTED_AMOUNT_SOURCE_MISMATCH" in report["error_codes"]
    assert report["rows"][0]["scope_complete"] is False


@pytest.mark.parametrize(
    ("stored_delta", "expected_proven"),
    [
        (0.01, True),
        (0.014, False),
        (0.015, False),
    ],
)
def test_formula_source_amount_uses_unrounded_one_cent_boundary(
    tmp_path: Path,
    stored_delta: float,
    expected_proven: bool,
) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path, sale_amount=1000.0, cash_amount=1000.0)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE sales_fact_v2 SET net_rev = ?, profit = ? WHERE order_id = 'O1'",
            (1000.0 + stored_delta, 600.0 + stored_delta),
        )
        conn.commit()

    report = validate_monthly_cash_reconciliation(
        db_path=db_path,
        since=date(2026, 2, 1),
        until=date(2026, 3, 20),
        output_root=tmp_path / "out",
        tolerance_pct=0.01,
        statusdate_cutover=date(2026, 1, 1),
        require_covered_pairs=False,
        strict=False,
    )

    assert report["sales_amount_formula_unproven_order_count"] == (
        0 if expected_proven else 1
    )
    assert report["sales_amount_source_formula_proven_order_count"] == (
        1 if expected_proven else 0
    )
    assert report["sales_amount_publication_binding_proven_order_count"] == 1


@pytest.mark.parametrize(
    ("published_delta", "expected_proven"),
    [
        (0.01, True),
        (0.014, False),
        (0.015, False),
    ],
)
def test_published_source_amount_uses_unrounded_one_cent_boundary(
    tmp_path: Path,
    published_delta: float,
    expected_proven: bool,
) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path, sale_amount=1000.0, cash_amount=1000.0)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE fact_sales_workbook_anchor (
                order_id TEXT,
                store_code TEXT,
                sale_date TEXT,
                quantity REAL,
                net_rev_kzt REAL,
                total_price_kzt REAL,
                source_file TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO fact_sales_workbook_anchor (
                order_id, store_code, sale_date, quantity, net_rev_kzt,
                total_price_kzt, source_file
            ) VALUES ('O1', 'UNIVERSAL', '2026-02-15', 1, ?, 1000,
                      'SALES_KSP_CRM_V3.xlsx')
            """,
            (1000.0 + published_delta,),
        )
        ensure_sales_truth_views(conn)
        conn.commit()

    report = validate_monthly_cash_reconciliation(
        db_path=db_path,
        since=date(2026, 2, 1),
        until=date(2026, 3, 20),
        output_root=tmp_path / "out",
        tolerance_pct=0.01,
        statusdate_cutover=date(2026, 1, 1),
        require_covered_pairs=False,
        strict=False,
    )

    assert report["sales_amount_formula_unproven_order_count"] == (
        0 if expected_proven else 1
    )
    assert report["sales_amount_published_source_mismatch_order_count"] == (
        0 if expected_proven else 1
    )


def test_selected_source_line_multiset_must_match_exact_raw_identity(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path, sale_amount=1000.0, cash_amount=1000.0)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            DROP VIEW view_sales_daily_truth;
            DROP VIEW view_sales_line_truth;
            CREATE VIEW view_sales_line_truth AS
            SELECT
                order_id,
                date(order_date) AS sale_date,
                store_code,
                sku_key,
                sku_id,
                my_size,
                CAST(quantity AS REAL) AS units,
                CAST(net_rev AS REAL) AS net_rev_kzt,
                CAST(cogs AS REAL) AS cogs_kzt,
                CAST(profit AS REAL) AS profit_kzt,
                'formula_full' AS cogs_source,
                'sales_fact_v2' AS source_table,
                'DIFFERENT_RAW_SKU' AS source_sku_key,
                sku_id AS source_sku_id,
                CAST(quantity AS REAL) AS source_units,
                CAST(net_rev AS REAL) AS source_net_rev_kzt,
                CAST(cogs AS REAL) AS source_cogs_kzt,
                CAST(profit AS REAL) AS source_profit_kzt
            FROM sales_fact_v2
            WHERE UPPER(COALESCE(status, 'DELIVERED')) = 'DELIVERED'
              AND COALESCE(return_flag, 0) = 0;
            """
        )
        conn.commit()

    report = validate_monthly_cash_reconciliation(
        db_path=db_path,
        since=date(2026, 2, 1),
        until=date(2026, 3, 20),
        output_root=tmp_path / "out",
        tolerance_pct=0.01,
        statusdate_cutover=date(2026, 1, 1),
        require_covered_pairs=False,
        strict=False,
    )

    assert report["sales_amount_formula_unproven_order_count"] == 1
    assert report["sales_amount_source_formula_proven_order_count"] == 1
    assert report["sales_amount_publication_binding_unproven_order_count"] == 1
    assert report["sales_amount_source_multiset_mismatch_order_count"] == 1
    assert "CASH_RECON_SELECTED_SOURCE_MULTISET_MISMATCH" in report["error_codes"]
    assert report["rows"][0]["scope_complete"] is False


def test_selected_sale_date_must_match_effective_source_date(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path, sale_amount=1000.0, cash_amount=1000.0)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            DROP VIEW view_sales_daily_truth;
            DROP VIEW view_sales_line_truth;
            CREATE VIEW view_sales_line_truth AS
            SELECT
                order_id,
                date(order_date, '+1 day') AS sale_date,
                store_code,
                sku_key,
                sku_id,
                my_size,
                CAST(quantity AS REAL) AS units,
                CAST(net_rev AS REAL) AS net_rev_kzt,
                CAST(cogs AS REAL) AS cogs_kzt,
                CAST(profit AS REAL) AS profit_kzt,
                'formula_full' AS cogs_source,
                'sales_fact_v2' AS source_table,
                sku_key AS source_sku_key,
                sku_id AS source_sku_id,
                CAST(quantity AS REAL) AS source_units,
                CAST(net_rev AS REAL) AS source_net_rev_kzt,
                CAST(cogs AS REAL) AS source_cogs_kzt,
                CAST(profit AS REAL) AS source_profit_kzt
            FROM sales_fact_v2
            WHERE UPPER(COALESCE(status, 'DELIVERED')) = 'DELIVERED'
              AND COALESCE(return_flag, 0) = 0;
            """
        )
        conn.commit()

    report = validate_monthly_cash_reconciliation(
        db_path=db_path,
        since=date(2026, 2, 1),
        until=date(2026, 3, 20),
        output_root=tmp_path / "out",
        tolerance_pct=0.01,
        statusdate_cutover=date(2026, 1, 1),
        require_covered_pairs=False,
        strict=False,
    )

    assert report["sales_amount_formula_unproven_order_count"] == 1
    assert report["sales_amount_source_formula_proven_order_count"] == 1
    assert report["sales_amount_publication_binding_unproven_order_count"] == 1
    assert report["sales_amount_source_multiset_mismatch_order_count"] == 1
    assert "CASH_RECON_SELECTED_SOURCE_MULTISET_MISMATCH" in report["error_codes"]
    assert report["rows"][0]["scope_complete"] is False


def test_invalid_raw_source_line_cannot_disappear_from_formula_evidence(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path, sale_amount=1000.0, cash_amount=1000.0)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sales_fact_v2 (
                order_id, order_date, sku_key, sku_id, my_size, store_code,
                quantity, sell_price_kzt, delivery_fee, net_rev, cogs, profit,
                status, return_flag
            ) VALUES (
                'O1', '2026-02-15', 'SKU_BAD', 'SKU_BAD_L', 'L',
                'UNIVERSAL', 1, 1000, 0, NULL, 400, NULL, 'DELIVERED', 0
            )
            """
        )
        conn.executescript(
            """
            DROP VIEW view_sales_daily_truth;
            DROP VIEW view_sales_line_truth;
            CREATE VIEW view_sales_line_truth AS
            SELECT
                order_id, date(order_date) AS sale_date, store_code,
                sku_key, sku_id, my_size, CAST(quantity AS REAL) AS units,
                CAST(net_rev AS REAL) AS net_rev_kzt,
                CAST(cogs AS REAL) AS cogs_kzt,
                CAST(profit AS REAL) AS profit_kzt,
                'formula_full' AS cogs_source,
                'sales_fact_v2' AS source_table,
                sku_key AS source_sku_key,
                sku_id AS source_sku_id,
                CAST(quantity AS REAL) AS source_units,
                CAST(net_rev AS REAL) AS source_net_rev_kzt,
                CAST(cogs AS REAL) AS source_cogs_kzt,
                CAST(profit AS REAL) AS source_profit_kzt
            FROM sales_fact_v2
            WHERE net_rev IS NOT NULL
              AND UPPER(COALESCE(status, 'DELIVERED')) = 'DELIVERED'
              AND COALESCE(return_flag, 0) = 0;
            """
        )
        conn.commit()

    report = validate_monthly_cash_reconciliation(
        db_path=db_path,
        since=date(2026, 2, 1),
        until=date(2026, 3, 20),
        output_root=tmp_path / "out",
        tolerance_pct=0.01,
        statusdate_cutover=date(2026, 1, 1),
        require_covered_pairs=False,
        strict=False,
    )

    assert report["sales_amount_source_formula_proven_order_count"] == 0
    assert report["sales_amount_source_formula_unproven_order_count"] == 1
    with Path(report["order_rows_csv"]).open(
        encoding="utf-8", newline=""
    ) as handle:
        row = next(csv.DictReader(handle))
    assert row["sales_amount_source_formula_invalid_line_count"] == "1"
    assert int(row["sales_amount_source_multiset_mismatch_line_count"]) >= 1
    assert row["sales_amount_formula_proven"] == "False"


def test_sales_amount_formula_basis_unavailable_fails_closed(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path, sale_amount=1000.0, cash_amount=1000.0)
    with sqlite3.connect(db_path) as conn:
        conn.execute("ALTER TABLE sales_fact_v2 RENAME TO old_sales_fact_v2")
        conn.execute(
            """
            CREATE TABLE sales_fact_v2 (
                order_id TEXT,
                order_date TEXT,
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
            )
            """
        )
        conn.execute(
            """
            INSERT INTO sales_fact_v2
            SELECT order_id, order_date, sku_key, sku_id, my_size, store_code,
                   quantity, cogs, net_rev, profit, status, return_flag
            FROM old_sales_fact_v2
            """
        )
        conn.execute("DROP TABLE old_sales_fact_v2")
        ensure_sales_truth_views(conn)
        conn.commit()

    report = validate_monthly_cash_reconciliation(
        db_path=db_path,
        since=date(2026, 2, 1),
        until=date(2026, 3, 20),
        output_root=tmp_path / "out",
        tolerance_pct=0.01,
        statusdate_cutover=date(2026, 1, 1),
        require_covered_pairs=True,
        strict=False,
    )

    assert report["status"] == "FAIL"
    assert report["sales_amount_formula_proof_available"] is False
    assert report["sales_amount_formula_unproven_order_count"] == 1
    assert "CASH_RECON_SALES_AMOUNT_UNPROVEN" in report["error_codes"]
    assert report["rows"][0]["scope_complete"] is False


def test_sales_amount_formula_proof_follows_fact_sales_source(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path, sale_amount=1000.0, cash_amount=1000.0)
    canonical_net = reconciliation.calc_net_rev(
        1000.0,
        delivery_fee=0.0,
        as_of_date=date(2026, 1, 15),
    )
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE fact_sales (
                id INTEGER PRIMARY KEY,
                order_id TEXT NOT NULL,
                order_date TEXT NOT NULL,
                store_code TEXT NOT NULL,
                sku_key TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                my_size TEXT,
                quantity INTEGER NOT NULL,
                sell_price_kzt REAL NOT NULL,
                delivery_fee REAL NOT NULL,
                line_net_rev REAL NOT NULL,
                cogs_line REAL NOT NULL,
                profit_line REAL NOT NULL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO fact_sales (
                order_id, order_date, store_code, sku_key, sku_id, my_size,
                quantity, sell_price_kzt, delivery_fee, line_net_rev,
                cogs_line, profit_line
            ) VALUES ('F1', '2026-01-15', 'UNIVERSAL', 'SKU_A', 'SKU_A_M', 'M',
                      2, 1000, 0, ?, 800, ?)
            """,
            (canonical_net * 2, (canonical_net * 2) - 800),
        )
        ensure_sales_truth_views(conn)
        conn.commit()

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        source = conn.execute(
            "SELECT source_table FROM view_sales_line_truth WHERE order_id='F1'"
        ).fetchone()
        assert source["source_table"] == "fact_sales"
        available, proof = reconciliation._sales_amount_formula_proof(
            conn,
            since=date(2026, 1, 1),
            until=date(2026, 3, 20),
        )

    assert available is True
    assert proof[("F1", "UNIVERSAL")]["line_count"] == 1
    assert proof[("F1", "UNIVERSAL")]["unproven_line_count"] == 0
    assert proof[("F1", "UNIVERSAL")]["proven"] is True


def test_decision_grade_pair_fails_closed_on_missing_cash(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM fact_cashflow_events")
    conn.commit()
    conn.close()

    with pytest.raises(CashReconciliationError, match="cash reconciliation failed"):
        validate_monthly_cash_reconciliation(
            db_path=db_path,
            since=date(2026, 2, 1),
            until=date(2026, 3, 20),
            output_root=tmp_path / "out",
            tolerance_pct=0.05,
            statusdate_cutover=date(2026, 1, 1),
            require_covered_pairs=True,
            strict=True,
        )

    report = validate_monthly_cash_reconciliation(
        db_path=db_path,
        since=date(2026, 2, 1),
        until=date(2026, 3, 20),
        output_root=tmp_path / "out2",
        tolerance_pct=0.05,
        statusdate_cutover=date(2026, 1, 1),
        require_covered_pairs=True,
        strict=False,
    )
    assert "CASH_RECON_INCOMPLETE_COVERAGE" in report["error_codes"]
    assert report["missing_cash_order_count"] == 1
    assert report["decision_grade_missing_cash_order_count"] == 1
    assert report["provisional_missing_cash_order_count"] == 0
    assert report["uncovered_decision_grade_pairs"] == 1


def test_decision_grade_pair_fails_closed_on_event_store_mismatch(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE fact_cashflow_events SET store_code='STOREB'")
    conn.commit()
    conn.close()

    report = validate_monthly_cash_reconciliation(
        db_path=db_path,
        since=date(2026, 2, 1),
        until=date(2026, 3, 20),
        output_root=tmp_path / "out",
        tolerance_pct=0.05,
        statusdate_cutover=date(2026, 1, 1),
        require_covered_pairs=True,
        strict=False,
    )
    assert report["status"] == "FAIL"
    assert report["event_store_mismatch_order_count"] == 1
    assert report["rows"][0]["scope_complete"] is False


def test_decision_grade_pair_fails_closed_on_cross_store_sales_identity(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO sales_fact_v2
        (order_id, order_date, sku_key, sku_id, my_size, store_code, quantity, cogs, net_rev, profit, status, return_flag)
        VALUES ('O1', '2026-02-15', 'SKU_A', 'SKU_A_M', 'M', 'STOREB', 1, 400, 1000, 600, 'DELIVERED', 0)
        """
    )
    conn.commit()
    conn.close()

    report = validate_monthly_cash_reconciliation(
        db_path=db_path,
        since=date(2026, 2, 1),
        until=date(2026, 3, 20),
        output_root=tmp_path / "out",
        tolerance_pct=0.05,
        statusdate_cutover=date(2026, 1, 1),
        require_covered_pairs=True,
        strict=False,
    )
    assert report["status"] == "FAIL"
    assert report["identity_ambiguous_order_count"] == 1


def test_unmapped_order_entry_cash_fails_closed(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO fact_cashflow_events
        (event_date, event_type, amount_kzt, store_code, ref_type, ref_id, source)
        VALUES ('2026-03-02', 'CASH_IN', 1000, 'UNIVERSAL', 'ORDER_ENTRY', 'MISSING_ENTRY', 'ORDER_MODELLED')
        """
    )
    conn.commit()
    conn.close()

    report = validate_monthly_cash_reconciliation(
        db_path=db_path,
        since=date(2026, 2, 1),
        until=date(2026, 3, 20),
        output_root=tmp_path / "out",
        tolerance_pct=0.05,
        statusdate_cutover=date(2026, 1, 1),
        require_covered_pairs=True,
        strict=False,
    )
    assert "CASH_RECON_UNMAPPED_ORDER_ENTRY" in report["error_codes"]
    assert report["unmapped_order_entry_cash_event_count"] == 1


def test_exact_unmapped_recovered_entry_reversal_pair_is_neutralized(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.execute(
        """
        INSERT INTO fact_cashflow_events
        (event_date, event_type, amount_kzt, store_code, sku_key, sku_id,
         ref_type, ref_id, source, notes, run_id, event_hash)
        VALUES ('2026-03-02', 'CASH_IN', 1000, 'ACMEWEAR', 'SKU_A', 'SKU_A_M',
                'ORDER_ENTRY', 'RECOV-CURRENT_CRM-exact', 'ORDER_MODELLED',
                'D1 cash-in from StageCode; order_id=123456789', 'legacy-run', ?)
        """,
        ("a" * 64,),
    )
    positive_id = int(cursor.lastrowid)
    conn.execute(
        """
        INSERT INTO fact_cashflow_events
        (event_date, event_type, amount_kzt, store_code, sku_key, sku_id,
         ref_type, ref_id, source, notes, run_id, event_hash)
        VALUES ('2026-03-02', 'CASH_IN', -1000, 'ACMEWEAR', 'SKU_A', 'SKU_A_M',
                'ORDER_ENTRY', 'RECOV-CURRENT_CRM-exact', 'ORDER_IDENTITY_REPAIR',
                ?, 'exact-repair-run', ?)
        """,
        (
            f"exact recovered-entry reversal; order_id=123456789; supersedes_cash_id={positive_id}",
            "b" * 64,
        ),
    )
    conn.commit()
    conn.close()

    report = validate_monthly_cash_reconciliation(
        db_path=db_path,
        since=date(2026, 2, 1),
        until=date(2026, 3, 20),
        output_root=tmp_path / "out",
        tolerance_pct=0.05,
        statusdate_cutover=date(2026, 1, 1),
        require_covered_pairs=False,
        strict=False,
    )

    assert "CASH_RECON_UNMAPPED_ORDER_ENTRY" not in report["error_codes"]
    assert report["unmapped_order_entry_cash_event_count"] == 0
    assert report["neutralized_unmapped_order_entry_cash_event_count"] == 2
    assert report["neutralized_unmapped_order_entry_group_count"] == 1
    assert report["neutralized_unmapped_order_entry_net_amount_kzt"] == 0


@pytest.mark.parametrize(
    ("reversal_amount", "reversal_notes", "reversal_hash"),
    [
        (-999, "exact recovered-entry reversal; order_id=123456789; supersedes_cash_id=2", "b" * 64),
        (-1000, "exact recovered-entry reversal; order_id=999999999; supersedes_cash_id=2", "b" * 64),
        (-1000, "exact recovered-entry reversal; order_id=123456789; supersedes_cash_id=2", ""),
    ],
)
def test_inexact_unmapped_recovered_entry_pair_still_fails_closed(
    tmp_path: Path,
    reversal_amount: float,
    reversal_notes: str,
    reversal_hash: str,
) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    positive = conn.execute(
        """
        INSERT INTO fact_cashflow_events
        (event_date, event_type, amount_kzt, store_code, sku_key, sku_id,
         ref_type, ref_id, source, notes, run_id, event_hash)
        VALUES ('2026-03-02', 'CASH_IN', 1000, 'ACMEWEAR', 'SKU_A', 'SKU_A_M',
                'ORDER_ENTRY', 'RECOV-CURRENT_CRM-inexact', 'ORDER_MODELLED',
                'D1 cash-in from StageCode; order_id=123456789', 'legacy-run', ?)
        """,
        ("a" * 64,),
    )
    notes = reversal_notes.replace("supersedes_cash_id=2", f"supersedes_cash_id={positive.lastrowid}")
    conn.execute(
        """
        INSERT INTO fact_cashflow_events
        (event_date, event_type, amount_kzt, store_code, sku_key, sku_id,
         ref_type, ref_id, source, notes, run_id, event_hash)
        VALUES ('2026-03-02', 'CASH_IN', ?, 'ACMEWEAR', 'SKU_A', 'SKU_A_M',
                'ORDER_ENTRY', 'RECOV-CURRENT_CRM-inexact', 'ORDER_IDENTITY_REPAIR',
                ?, 'exact-repair-run', ?)
        """,
        (reversal_amount, notes, reversal_hash),
    )
    conn.commit()
    conn.close()

    report = validate_monthly_cash_reconciliation(
        db_path=db_path,
        since=date(2026, 2, 1),
        until=date(2026, 3, 20),
        output_root=tmp_path / "out",
        tolerance_pct=0.05,
        statusdate_cutover=date(2026, 1, 1),
        require_covered_pairs=False,
        strict=False,
    )

    assert "CASH_RECON_UNMAPPED_ORDER_ENTRY" in report["error_codes"]
    assert report["unmapped_order_entry_cash_event_count"] == 2
    assert report["neutralized_unmapped_order_entry_cash_event_count"] == 0


def test_strict_empty_scope_cannot_pass_by_omission(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)

    with pytest.raises(CashReconciliationError, match="cash reconciliation failed"):
        validate_monthly_cash_reconciliation(
            db_path=db_path,
            since=date(2026, 4, 1),
            until=date(2026, 4, 30),
            output_root=tmp_path / "out",
            tolerance_pct=0.05,
            statusdate_cutover=date(2026, 1, 1),
            require_covered_pairs=False,
            strict=True,
        )


def test_duplicate_recovered_entries_fail_quantity_parity(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.executemany(
        """
        INSERT INTO fact_order_entries_kaspi (entry_id, order_id, store_code, quantity, offer_id)
        VALUES (?, 'O1', 'UNIVERSAL', 1, 'SKU_A_M')
        """,
        [("RECOV-1",), ("RECOV-2",)],
    )
    conn.executemany(
        """
        INSERT INTO fact_cashflow_events
        (event_date, event_type, amount_kzt, store_code, ref_type, ref_id, source)
        VALUES ('2026-03-02', 'CASH_IN', 1000, 'UNIVERSAL', 'ORDER_ENTRY', ?, 'ORDER_MODELLED')
        """,
        [("RECOV-1",), ("RECOV-2",)],
    )
    conn.commit()
    conn.close()

    report = validate_monthly_cash_reconciliation(
        db_path=db_path,
        since=date(2026, 2, 1),
        until=date(2026, 3, 20),
        output_root=tmp_path / "out",
        tolerance_pct=0.05,
        statusdate_cutover=date(2026, 1, 1),
        require_covered_pairs=True,
        strict=False,
    )
    assert report["status"] == "FAIL"
    assert report["ambiguous_entry_resolution_count"] == 1
    assert report["entry_quantity_mismatch_order_count"] == 1
    assert report["entry_reference_incomplete_order_count"] == 0
    assert report["decision_grade_ambiguous_entry_order_count"] == 1
    assert report["rows"][0]["entry_identity_ambiguous_order_count"] == 1


def test_partial_entry_cash_does_not_fall_back_or_mix_order_cash(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.executemany(
        """
        INSERT INTO fact_order_entries_kaspi (entry_id, order_id, store_code, quantity, offer_id)
        VALUES (?, 'O1', 'UNIVERSAL', 0.5, ?)
        """,
        [("E1", "SKU_A_M_1"), ("E2", "SKU_A_M_2")],
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_events
        (event_date, event_type, amount_kzt, store_code, ref_type, ref_id, source)
        VALUES ('2026-03-02', 'CASH_IN', 500, 'UNIVERSAL', 'ORDER_ENTRY', 'E1', 'ORDER_MODELLED')
        """
    )
    conn.commit()
    conn.close()

    report = validate_monthly_cash_reconciliation(
        db_path=db_path,
        since=date(2026, 2, 1),
        until=date(2026, 3, 20),
        output_root=tmp_path / "out",
        tolerance_pct=0.05,
        statusdate_cutover=date(2026, 1, 1),
        require_covered_pairs=True,
        strict=False,
    )
    with Path(report["order_rows_csv"]).open(encoding="utf-8", newline="") as handle:
        order_row = next(csv.DictReader(handle))
    assert report["ambiguous_entry_resolution_count"] == 1
    assert report["entry_reference_incomplete_order_count"] == 1
    assert report["entry_quantity_mismatch_order_count"] == 0
    assert report["order_fallback_resolution_count"] == 0
    assert report["dual_ref_type_order_count"] == 1
    assert order_row["cash_resolution"] == "AMBIGUOUS_ENTRY"
    assert order_row["entry_reference_complete"] == "False"


def test_future_cash_reversal_does_not_leak_into_as_of_report(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path, sale_amount=1000.0, cash_amount=1000.0)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO fact_cashflow_events
        (event_date, event_type, amount_kzt, store_code, ref_type, ref_id, source)
        VALUES ('2026-04-01', 'CASH_IN', -1000, 'UNIVERSAL', 'ORDER', 'O1', 'ORDER_MODELLED')
        """
    )
    conn.commit()
    conn.close()

    report = validate_monthly_cash_reconciliation(
        db_path=db_path,
        since=date(2026, 2, 1),
        until=date(2026, 3, 20),
        output_root=tmp_path / "out",
        tolerance_pct=0.01,
        statusdate_cutover=date(2026, 1, 1),
        require_covered_pairs=True,
        strict=True,
    )
    assert report["status"] == "PASS"
    assert report["rows"][0]["cash_net_rev_kzt"] == 1000.0


def test_unrelated_historical_unsupported_cash_does_not_fail_selected_cohort(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path, sale_amount=1000.0, cash_amount=1000.0)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO fact_cashflow_events
        (event_date, event_type, amount_kzt, store_code, ref_type, ref_id, source)
        VALUES ('2020-01-01', 'CASH_IN', 1, 'UNKNOWN', 'LEGACY_UNKNOWN', 'OLD', 'LEGACY')
        """
    )
    conn.commit()
    conn.close()

    report = validate_monthly_cash_reconciliation(
        db_path=db_path,
        since=date(2026, 2, 1),
        until=date(2026, 3, 20),
        output_root=tmp_path / "out",
        tolerance_pct=0.01,
        statusdate_cutover=date(2026, 1, 1),
        require_covered_pairs=True,
        strict=True,
    )
    assert report["status"] == "PASS"
    assert report["unsupported_cash_event_count"] == 0
    assert report["unsupported_cash_event_count_asof_all"] == 1


def test_unsupported_cash_inside_reporting_window_fails_closed(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_db(db_path, sale_amount=1000.0, cash_amount=1000.0)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO fact_cashflow_events
        (event_date, event_type, amount_kzt, store_code, ref_type, ref_id, source)
        VALUES ('2026-03-02', 'CASH_IN', 1, 'UNKNOWN', 'UNKNOWN_REF', 'X', 'SYSTEM')
        """
    )
    conn.commit()
    conn.close()

    report = validate_monthly_cash_reconciliation(
        db_path=db_path,
        since=date(2026, 2, 1),
        until=date(2026, 3, 20),
        output_root=tmp_path / "out",
        tolerance_pct=0.01,
        statusdate_cutover=date(2026, 1, 1),
        require_covered_pairs=True,
        strict=False,
    )
    assert report["status"] == "FAIL"
    assert "CASH_RECON_UNSUPPORTED_REF_TYPE" in report["error_codes"]
    assert report["unsupported_cash_event_count"] == 1
