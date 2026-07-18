"""Governed line-level publication bindings for canonical sales truth.

The tables installed here are additive.  They preserve the immutable source
sales rows and workbook anchor while allowing a separately validated binding
to publish an exact terminal date and exact line economics.
"""

from __future__ import annotations

import sqlite3


HEADER_TABLE = "fact_sales_publication_binding_header"
LINE_TABLE = "fact_sales_publication_binding_line"


HEADER_REQUIRED_COLUMNS = {
    "binding_id",
    "order_id",
    "store_code",
    "binding_status",
    "active_flag",
    "provisional_flag",
    "publication_effective_date",
    "terminal_date_semantics",
    "expected_line_count",
    "external_evidence_validated",
    "anchor_sale_date",
    "anchor_quantity",
    "anchor_net_rev_kzt",
    "anchor_total_price_kzt",
    "anchor_source_file",
    "anchor_updated_at",
}

LINE_REQUIRED_COLUMNS = {
    "binding_id",
    "line_ordinal",
    "source_table",
    "source_sale_id",
    "source_entry_id",
    "line_identity_key",
    "source_order_id",
    "source_store_code",
    "source_order_date",
    "source_sku_key",
    "source_sku_id",
    "source_my_size",
    "source_quantity",
    "source_sell_price_kzt",
    "source_delivery_fee",
    "source_cogs_kzt",
    "source_net_rev_kzt",
    "source_profit_kzt",
    "source_status",
    "source_return_flag",
    "source_file",
    "source_kaspi_article",
    "unbound_sale_date",
    "unbound_units",
    "unbound_net_rev_kzt",
    "publication_sale_date",
    "publication_units",
    "publication_net_rev_kzt",
}


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def publication_binding_schema_ready(conn: sqlite3.Connection) -> bool:
    header = table_columns(conn, HEADER_TABLE)
    lines = table_columns(conn, LINE_TABLE)
    return HEADER_REQUIRED_COLUMNS.issubset(header) and LINE_REQUIRED_COLUMNS.issubset(lines)


def install_publication_binding_schema(conn: sqlite3.Connection) -> None:
    """Install the additive v1 binding schema without modifying sales data."""

    statements = [
        f"""
        CREATE TABLE IF NOT EXISTS {HEADER_TABLE} (
            binding_id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            store_code TEXT NOT NULL,
            binding_status TEXT NOT NULL CHECK (binding_status IN ('VALID', 'REVOKED')),
            active_flag INTEGER NOT NULL DEFAULT 0 CHECK (active_flag IN (0, 1)),
            provisional_flag INTEGER NOT NULL DEFAULT 0 CHECK (provisional_flag IN (0, 1)),
            publication_effective_date TEXT NOT NULL,
            terminal_date_semantics TEXT NOT NULL,
            expected_line_count INTEGER NOT NULL CHECK (expected_line_count > 0),
            external_evidence_validated INTEGER NOT NULL DEFAULT 0
                CHECK (external_evidence_validated IN (0, 1)),
            copied_db_pre_sha256 TEXT NOT NULL,
            canonical_hash_version TEXT NOT NULL,
            economics_policy_sha256 TEXT NOT NULL,
            originating_manifest_path TEXT NOT NULL,
            originating_manifest_file_sha256 TEXT NOT NULL,
            originating_manifest_internal_sha256 TEXT NOT NULL,
            source_proof_file_path TEXT NOT NULL,
            source_proof_file_sha256 TEXT NOT NULL,
            source_proof_key TEXT NOT NULL,
            source_sidecar_manifest_path TEXT NOT NULL,
            source_sidecar_manifest_file_sha256 TEXT NOT NULL,
            source_sidecar_manifest_internal_sha256 TEXT NOT NULL,
            promotion_manifest_path TEXT NOT NULL,
            promotion_manifest_file_sha256 TEXT NOT NULL,
            promotion_manifest_internal_sha256 TEXT NOT NULL,
            promotion_apply_report_path TEXT NOT NULL,
            promotion_apply_report_sha256 TEXT NOT NULL,
            api_header_path TEXT NOT NULL,
            api_header_sha256 TEXT NOT NULL,
            terminal_evidence_sha256 TEXT NOT NULL,
            workbook_anchor_preimage_sha256 TEXT NOT NULL,
            unbound_selected_multiset_sha256 TEXT NOT NULL,
            source_line_multiset_sha256 TEXT NOT NULL,
            anchor_sale_date TEXT NOT NULL,
            anchor_quantity REAL NOT NULL,
            anchor_net_rev_kzt REAL NOT NULL,
            anchor_total_price_kzt REAL NOT NULL,
            anchor_source_file TEXT,
            anchor_updated_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """,
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_sales_publication_binding_active
        ON {HEADER_TABLE}(order_id, UPPER(TRIM(store_code)))
        WHERE active_flag = 1
        """,
        f"""
        CREATE TABLE IF NOT EXISTS {LINE_TABLE} (
            binding_id TEXT NOT NULL,
            line_ordinal INTEGER NOT NULL CHECK (line_ordinal > 0),
            source_table TEXT NOT NULL CHECK (source_table = 'sales_fact_v2'),
            source_sale_id INTEGER NOT NULL,
            source_entry_id TEXT NOT NULL,
            line_identity_key TEXT NOT NULL,
            source_order_id TEXT NOT NULL,
            source_store_code TEXT NOT NULL,
            source_order_date TEXT NOT NULL,
            source_sku_key TEXT NOT NULL,
            source_sku_id TEXT NOT NULL,
            source_my_size TEXT NOT NULL,
            source_quantity REAL NOT NULL,
            source_sell_price_kzt REAL NOT NULL,
            source_delivery_fee REAL NOT NULL,
            source_cogs_kzt REAL,
            source_net_rev_kzt REAL NOT NULL,
            source_profit_kzt REAL,
            source_status TEXT NOT NULL,
            source_return_flag INTEGER NOT NULL,
            source_file TEXT,
            source_kaspi_article TEXT,
            source_row_preimage_sha256 TEXT NOT NULL,
            entry_evidence_sha256 TEXT NOT NULL,
            source_line_proof_sha256 TEXT NOT NULL,
            promotion_target_sha256 TEXT NOT NULL,
            unbound_sale_date TEXT NOT NULL,
            unbound_units REAL NOT NULL,
            unbound_net_rev_kzt REAL NOT NULL,
            publication_sale_date TEXT NOT NULL,
            publication_units REAL NOT NULL,
            publication_net_rev_kzt REAL NOT NULL,
            PRIMARY KEY (binding_id, line_ordinal),
            UNIQUE (binding_id, source_sale_id),
            FOREIGN KEY (binding_id) REFERENCES {HEADER_TABLE}(binding_id) ON DELETE RESTRICT
        )
        """,
    ]
    for statement in statements:
        conn.execute(statement)
