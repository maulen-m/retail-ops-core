import sqlite3
from datetime import date
from pathlib import Path

import pytest

from core.sales.publication_binding import install_publication_binding_schema
from core.sales.truth_views import ensure_sales_truth_views
from scripts.validate_monthly_cash_reconciliation import _sales_amount_formula_proof


def _seed_binding_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE sales_fact_v2 (
            sale_id INTEGER PRIMARY KEY,
            order_id TEXT NOT NULL,
            order_date TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT NOT NULL,
            kaspi_offer_name TEXT NOT NULL DEFAULT '',
            store_code TEXT,
            quantity REAL NOT NULL,
            sell_price_kzt REAL,
            delivery_fee REAL,
            cogs REAL,
            net_rev REAL,
            profit REAL,
            status TEXT,
            return_flag INTEGER,
            source_file TEXT,
            source_entry_id TEXT,
            kaspi_article TEXT,
            line_identity_key TEXT
        );
        CREATE TABLE fact_sales_workbook_anchor (
            order_id TEXT NOT NULL,
            store_code TEXT NOT NULL,
            sale_date TEXT NOT NULL,
            quantity REAL NOT NULL,
            net_rev_kzt REAL NOT NULL,
            total_price_kzt REAL NOT NULL,
            source_file TEXT,
            updated_at TEXT,
            PRIMARY KEY(order_id, store_code)
        );
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            base_cost_cny REAL,
            weight_kg REAL,
            cogs_kzt REAL
        );
        """
    )
    conn.execute(
        "INSERT INTO dim_sku VALUES ('SKU', NULL, NULL, 1000)"
    )
    conn.executemany(
        """
        INSERT INTO sales_fact_v2(
            sale_id, order_id, order_date, sku_key, sku_id, my_size,
            store_code, quantity, sell_price_kzt, delivery_fee, cogs, net_rev,
            profit, status, return_flag, source_file, source_entry_id,
            kaspi_article, line_identity_key
        ) VALUES (?, 'O1', '2026-01-12', 'SKU', ?, ?, 'ACMEWEAR', 1, 8982,
                  637.5, NULL, 6932.88, NULL, 'DELIVERED', 0, 'source.xlsx',
                  ?, ?, ?)
        """,
        [
            (1, "SKU_2XL", "2XL", "E0", "ARTICLE0", "ENTRY:E0"),
            (2, "SKU_3XL", "3XL", "E1", "ARTICLE1", "ENTRY:E1"),
        ],
    )
    conn.execute(
        """
        INSERT INTO fact_sales_workbook_anchor
        VALUES ('O1', 'ACMEWEAR', '2026-01-12', 2, 13727.92, 17964,
                'anchor.xlsx', '2026-03-07 20:42:46')
        """
    )
    install_publication_binding_schema(conn)
    ensure_sales_truth_views(conn)
    _insert_binding(conn)
    conn.commit()
    ensure_sales_truth_views(conn)
    return conn


def _insert_binding(conn: sqlite3.Connection, *, binding_id: str = "B1") -> None:
    conn.execute(
        """
        INSERT INTO fact_sales_publication_binding_header(
            binding_id, order_id, store_code, binding_status, active_flag,
            provisional_flag, publication_effective_date,
            terminal_date_semantics, expected_line_count,
            external_evidence_validated, copied_db_pre_sha256,
            canonical_hash_version, economics_policy_sha256,
            originating_manifest_path, originating_manifest_file_sha256,
            originating_manifest_internal_sha256, source_proof_file_path,
            source_proof_file_sha256, source_proof_key,
            source_sidecar_manifest_path, source_sidecar_manifest_file_sha256,
            source_sidecar_manifest_internal_sha256, promotion_manifest_path,
            promotion_manifest_file_sha256, promotion_manifest_internal_sha256,
            promotion_apply_report_path, promotion_apply_report_sha256,
            api_header_path, api_header_sha256, terminal_evidence_sha256,
            workbook_anchor_preimage_sha256, unbound_selected_multiset_sha256,
            source_line_multiset_sha256, anchor_sale_date, anchor_quantity,
            anchor_net_rev_kzt, anchor_total_price_kzt, anchor_source_file,
            anchor_updated_at
        ) VALUES (
            ?, 'O1', 'ACMEWEAR', 'VALID', 1, 0, '2026-01-13',
            'STATUS_CHANGE_TIMESTAMP_PROVEN', 2, 1,
            'a', 'canonical-json-v1-sort-keys-utf8-no-whitespace', 'b',
            '/manifest', 'c', 'd', '/proof', 'e', 'f', '/sidecar', 'g', 'h',
            '/promotion', 'i', 'j', '/apply', 'k', '/header', 'l', 'm',
            'n', 'o', 'p', '2026-01-12', 2, 13727.92, 17964,
            'anchor.xlsx', '2026-03-07 20:42:46'
        )
        """,
        (binding_id,),
    )
    for ordinal, sale_id, size, entry_id, article in (
        (1, 1, "2XL", "E0", "ARTICLE0"),
        (2, 2, "3XL", "E1", "ARTICLE1"),
    ):
        conn.execute(
            """
            INSERT INTO fact_sales_publication_binding_line(
                binding_id, line_ordinal, source_table, source_sale_id,
                source_entry_id, line_identity_key, source_order_id,
                source_store_code, source_order_date, source_sku_key,
                source_sku_id, source_my_size, source_quantity,
                source_sell_price_kzt, source_delivery_fee, source_cogs_kzt,
                source_net_rev_kzt, source_profit_kzt, source_status,
                source_return_flag, source_file, source_kaspi_article,
                source_row_preimage_sha256, entry_evidence_sha256,
                source_line_proof_sha256, promotion_target_sha256,
                unbound_sale_date, unbound_units, unbound_net_rev_kzt,
                publication_sale_date, publication_units,
                publication_net_rev_kzt
            ) VALUES (
                ?, ?, 'sales_fact_v2', ?, ?, ?, 'O1', 'ACMEWEAR',
                '2026-01-12', 'SKU', ?, ?, 1, 8982, 637.5, NULL, 6932.88,
                NULL, 'DELIVERED', 0, 'source.xlsx', ?, 'r', 's', 't', 'u',
                '2026-01-12', 1, 6863.96, '2026-01-13', 1, 6932.88
            )
            """,
            (
                binding_id,
                ordinal,
                sale_id,
                entry_id,
                f"ENTRY:{entry_id}",
                f"SKU_{size}",
                size,
                article,
            ),
        )


def test_two_line_binding_is_all_or_nothing_and_exact(tmp_path: Path) -> None:
    conn = _seed_binding_db(tmp_path / "app.db")
    rows = conn.execute(
        """
        SELECT source_row_id, sale_date, units, net_rev_kzt,
               publication_binding_status, publication_provisional_flag
        FROM view_sales_line_truth ORDER BY CAST(source_row_id AS INTEGER)
        """
    ).fetchall()
    unbound = conn.execute(
        "SELECT sale_date, net_rev_kzt FROM view_sales_line_truth_unbound ORDER BY source_row_id"
    ).fetchall()
    validation = conn.execute(
        "SELECT validation_status, publication_binding_usable FROM view_sales_publication_binding_validation"
    ).fetchone()
    conn.close()

    assert rows == [
        ("1", "2026-01-13", 1.0, 6932.88, "VALID_ACTIVE", 0),
        ("2", "2026-01-13", 1.0, 6932.88, "VALID_ACTIVE", 0),
    ]
    assert unbound == [("2026-01-12", 6863.96), ("2026-01-12", 6863.96)]
    assert validation == ("VALID_ACTIVE", 1)


def test_anchor_drift_keeps_membership_and_surfaces_invalid_binding(tmp_path: Path) -> None:
    conn = _seed_binding_db(tmp_path / "app.db")
    before = conn.execute("SELECT COUNT(*) FROM view_sales_line_truth").fetchone()[0]
    conn.execute(
        "UPDATE fact_sales_workbook_anchor SET net_rev_kzt=12000 WHERE order_id='O1'"
    )
    ensure_sales_truth_views(conn)
    rows = conn.execute(
        "SELECT sale_date, net_rev_kzt, publication_binding_status FROM view_sales_line_truth ORDER BY source_row_id"
    ).fetchall()
    after = conn.execute("SELECT COUNT(*) FROM view_sales_line_truth").fetchone()[0]
    conn.close()

    assert before == after == 2
    assert rows == [
        ("2026-01-12", 6000.0, "INVALID_ACTIVE:ANCHOR_PREIMAGE_MISMATCH"),
        ("2026-01-12", 6000.0, "INVALID_ACTIVE:ANCHOR_PREIMAGE_MISMATCH"),
    ]


def test_partial_binding_line_loss_invalidates_both_lines(tmp_path: Path) -> None:
    conn = _seed_binding_db(tmp_path / "app.db")
    conn.execute(
        "DELETE FROM fact_sales_publication_binding_line WHERE binding_id='B1' AND line_ordinal=2"
    )
    ensure_sales_truth_views(conn)
    rows = conn.execute(
        "SELECT net_rev_kzt, publication_binding_status FROM view_sales_line_truth ORDER BY source_row_id"
    ).fetchall()
    conn.close()

    assert rows == [
        (6863.96, "INVALID_ACTIVE:BINDING_LINE_COUNT_MISMATCH"),
        (6863.96, "INVALID_ACTIVE:BINDING_LINE_COUNT_MISMATCH"),
    ]


def test_active_binding_unique_per_order_store(tmp_path: Path) -> None:
    conn = _seed_binding_db(tmp_path / "app.db")
    with pytest.raises(sqlite3.IntegrityError):
        _insert_binding(conn, binding_id="B2")
    conn.close()


def test_monthly_formula_proof_accepts_valid_terminal_binding_only(tmp_path: Path) -> None:
    conn = _seed_binding_db(tmp_path / "app.db")
    conn.row_factory = sqlite3.Row
    available, proof = _sales_amount_formula_proof(
        conn,
        since=date(2026, 1, 1),
        until=date(2026, 1, 31),
    )
    state = proof[("O1", "ACMEWEAR")]
    assert available is True
    assert state["source_formula_proven"] is True
    assert state["publication_binding_proven"] is True
    assert state["source_multiset_mismatch_line_count"] == 0
    assert state["proven"] is True

    conn.execute("UPDATE sales_fact_v2 SET net_rev=6900 WHERE sale_id=2")
    ensure_sales_truth_views(conn)
    _, drifted_proof = _sales_amount_formula_proof(
        conn,
        since=date(2026, 1, 1),
        until=date(2026, 1, 31),
    )
    drifted = drifted_proof[("O1", "ACMEWEAR")]
    conn.close()
    assert drifted["publication_binding_proven"] is False
    assert drifted["proven"] is False
