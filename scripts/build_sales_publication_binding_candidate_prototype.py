#!/usr/bin/env python3
"""Build an inactive publication-binding candidate prototype on a DB copy.

The source DB is always opened read-only and is never modified. Dry-run is the
default. Apply requires an explicit local-copy gate, refuses canonical
``db/app.db``, creates a new SQLite copy, installs candidate-only schema/views,
and loads only manifest rows that are explicitly provisional and activation
blocked. The existing sales truth view is not replaced or changed.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


ENV_GATE = "ENABLE_COPIED_PUBLICATION_BINDING_PROTOTYPE_WRITE"
MANIFEST_SCHEMA = "terminal_observation_publication_candidate_manifest_v2"
PROTOTYPE_SCHEMA = "sales_publication_binding_candidate_prototype_v1"
EXPECTED_BLOCKER = "TERMINAL_EFFECTIVE_DATE_POLICY_UNRESOLVED"
CANONICAL_DB_PATH = (PROJECT_ROOT / "db" / "app.db").resolve()


class PrototypeError(RuntimeError):
    """Raised when copied-prototype inputs or readback fail closed."""


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PrototypeError(f"invalid manifest JSON: {path}") from exc
    if not isinstance(value, dict):
        raise PrototypeError("manifest root is not an object")
    return value


def _connect_read_only(path: Path) -> sqlite3.Connection:
    resolved = path.expanduser().resolve()
    conn = sqlite3.connect(f"file:{resolved}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _normalize_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    return value


def _query_hash(conn: sqlite3.Connection, sql: str) -> dict[str, Any]:
    rows = [
        {key: _normalize_value(row[key]) for key in row.keys()}
        for row in conn.execute(sql)
    ]
    serialized = [
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        for row in rows
    ]
    serialized.sort()
    return {"row_count": len(rows), "sha256": _canonical_sha(serialized)}


def _truth_hashes(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    return {
        "sales_fact_v2": _query_hash(conn, "SELECT * FROM sales_fact_v2"),
        "fact_sales_workbook_anchor": _query_hash(
            conn, "SELECT * FROM fact_sales_workbook_anchor"
        ),
        "view_sales_line_truth": _query_hash(
            conn, "SELECT * FROM view_sales_line_truth"
        ),
    }


def _manifest_internal_sha(manifest: dict[str, Any]) -> str:
    return _canonical_sha(
        {
            key: value
            for key, value in manifest.items()
            if key not in {"generated_at", "manifest_sha256"}
        }
    )


def _validate_manifest(
    manifest: dict[str, Any],
    *,
    manifest_file_sha256: str,
    expected_manifest_file_sha256: str | None,
    expected_target_count: int | None,
) -> list[dict[str, Any]]:
    if _text(manifest.get("schema")) != MANIFEST_SCHEMA:
        raise PrototypeError("unsupported manifest schema")
    if expected_manifest_file_sha256 and (
        manifest_file_sha256 != expected_manifest_file_sha256
    ):
        raise PrototypeError("manifest file SHA-256 changed")
    internal = _manifest_internal_sha(manifest)
    if internal != _text(manifest.get("manifest_sha256")):
        raise PrototypeError("manifest internal SHA-256 mismatch")
    if bool(manifest.get("production_write_authorized")):
        raise PrototypeError("manifest unexpectedly authorizes production write")
    if bool(manifest.get("writer_or_apply_path_exists")):
        raise PrototypeError("manifest unexpectedly declares a writer/apply path")
    targets = manifest.get("targets")
    if not isinstance(targets, list) or not targets:
        raise PrototypeError("manifest targets are missing")
    if expected_target_count is not None and len(targets) != expected_target_count:
        raise PrototypeError(
            f"target count changed: {len(targets)}/{expected_target_count}"
        )
    if int(manifest.get("activation_eligible_count", -1)) != 0:
        raise PrototypeError("manifest contains activation-eligible rows")
    if int(manifest.get("activation_blocked_count", -1)) != len(targets):
        raise PrototypeError("manifest activation-blocked count changed")
    if "approved_publication_date" in json.dumps(manifest, ensure_ascii=False):
        raise PrototypeError("manifest contains approved-publication wording")

    keys: list[tuple[str, str]] = []
    for target in targets:
        if not isinstance(target, dict):
            raise PrototypeError("manifest target is not an object")
        key = target.get("target_key") or {}
        order_id = _text(key.get("order_id"))
        store_code = _text(key.get("store_code")).upper()
        if not order_id or not store_code:
            raise PrototypeError("blank target order/store identity")
        keys.append((order_id, store_code))
        header = target.get("binding_header_candidate") or {}
        lines = target.get("binding_line_candidates") or []
        terminal = target.get("terminal_evidence") or {}
        if len(lines) != 1:
            raise PrototypeError(f"target is not one-line: {order_id}/{store_code}")
        invariants = (
            _text(header.get("binding_status")) == "CANDIDATE_VALIDATED_UNAPPLIED",
            bool(header.get("provisional_flag")) is True,
            bool(header.get("activation_eligible")) is False,
            _text(header.get("activation_blocker")) == EXPECTED_BLOCKER,
            _text(header.get("terminal_date_semantics"))
            == "TERMINAL_OBSERVATION_DATE_CANDIDATE",
            bool(terminal.get("activation_eligible")) is False,
            _text(terminal.get("activation_blocker")) == EXPECTED_BLOCKER,
        )
        if not all(invariants):
            raise PrototypeError(
                f"target is not an inactive observation candidate: {order_id}/{store_code}"
            )
    if len(keys) != len(set(keys)):
        raise PrototypeError("duplicate manifest order/store target key")
    return targets


SCHEMA_SQL = r"""
CREATE TABLE sales_publication_binding_candidate_prototype_meta (
    prototype_id INTEGER PRIMARY KEY CHECK (prototype_id = 1),
    prototype_schema TEXT NOT NULL,
    manifest_schema TEXT NOT NULL,
    manifest_file_sha256 TEXT NOT NULL CHECK(length(manifest_file_sha256) = 64),
    manifest_internal_sha256 TEXT NOT NULL CHECK(length(manifest_internal_sha256) = 64),
    manifest_payload_sha256 TEXT NOT NULL CHECK(length(manifest_payload_sha256) = 64),
    policy_sha256 TEXT NOT NULL CHECK(length(policy_sha256) = 64),
    source_db_sha256 TEXT NOT NULL CHECK(length(source_db_sha256) = 64),
    target_key_sha256 TEXT NOT NULL CHECK(length(target_key_sha256) = 64),
    expected_target_count INTEGER NOT NULL CHECK(expected_target_count > 0),
    built_at TEXT NOT NULL,
    production_authority INTEGER NOT NULL DEFAULT 0 CHECK(production_authority = 0),
    published_view_changed INTEGER NOT NULL DEFAULT 0 CHECK(published_view_changed = 0)
);

CREATE TABLE fact_sales_publication_binding_candidate_header (
    candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL,
    store_code TEXT NOT NULL,
    candidate_status TEXT NOT NULL CHECK(candidate_status IN ('CANDIDATE','VALID','INVALID')),
    active_flag INTEGER NOT NULL DEFAULT 0 CHECK(active_flag = 0),
    activation_eligible INTEGER NOT NULL CHECK(activation_eligible IN (0,1)),
    provisional_flag INTEGER NOT NULL CHECK(provisional_flag IN (0,1)),
    activation_blocker TEXT NOT NULL,
    binding_version TEXT NOT NULL,
    reason TEXT NOT NULL,
    candidate_publication_date TEXT NOT NULL,
    terminal_date_semantics TEXT NOT NULL,
    terminal_rank INTEGER NOT NULL,
    canonical_hash_version TEXT NOT NULL,
    copied_db_sha256 TEXT NOT NULL,
    policy_sha256 TEXT NOT NULL,
    originating_manifest_payload_sha256 TEXT NOT NULL,
    workbook_anchor_sha256 TEXT NOT NULL,
    selected_source_line_multiset_sha256 TEXT NOT NULL,
    source_line_multiset_sha256 TEXT NOT NULL,
    terminal_evidence_sha256 TEXT NOT NULL,
    terminal_all_positive_evidence_sha256 TEXT NOT NULL,
    terminal_later_positive_evidence_sha256 TEXT NOT NULL,
    terminal_negative_evidence_sha256 TEXT NOT NULL,
    anchor_sale_date TEXT NOT NULL,
    anchor_quantity_text TEXT NOT NULL,
    anchor_net_rev_kzt_text TEXT NOT NULL,
    anchor_total_price_kzt_text TEXT NOT NULL,
    anchor_source_file TEXT,
    anchor_updated_at TEXT,
    UNIQUE(order_id, store_code, originating_manifest_payload_sha256),
    CHECK(
      candidate_status <> 'CANDIDATE' OR
      (active_flag=0 AND activation_eligible=0 AND provisional_flag=1 AND
       activation_blocker='TERMINAL_EFFECTIVE_DATE_POLICY_UNRESOLVED' AND
       terminal_date_semantics='TERMINAL_OBSERVATION_DATE_CANDIDATE')
    )
);

CREATE TABLE fact_sales_publication_binding_candidate_line (
    candidate_id INTEGER NOT NULL,
    line_ordinal INTEGER NOT NULL CHECK(line_ordinal > 0),
    source_table TEXT NOT NULL CHECK(source_table = 'sales_fact_v2'),
    source_physical_row_column TEXT NOT NULL CHECK(source_physical_row_column = 'sale_id'),
    source_physical_row_value INTEGER NOT NULL,
    source_entry_id TEXT,
    line_identity_key TEXT,
    immutable_identity_kind TEXT NOT NULL CHECK(immutable_identity_kind IN ('API_ENTRY_AND_LINE_IDENTITY','CRM_XLSX_PHYSICAL_ROW')),
    immutable_source_identity_sha256 TEXT NOT NULL,
    source_workbook_sha256 TEXT,
    source_sheet TEXT,
    source_workbook_physical_row INTEGER,
    source_formula_row_sha256 TEXT,
    source_allowlisted_row_sha256 TEXT,
    source_proof_key TEXT,
    source_proof_preimage_sha256 TEXT,
    source_proof_jsonl_sha256 TEXT,
    source_promotion_apply_report_sha256 TEXT,
    source_row_sha256 TEXT NOT NULL,
    source_sale_id INTEGER NOT NULL,
    source_order_id TEXT NOT NULL,
    source_order_date TEXT NOT NULL,
    source_sku_key TEXT NOT NULL,
    source_sku_id TEXT NOT NULL,
    source_my_size TEXT NOT NULL,
    source_kaspi_offer_name TEXT NOT NULL,
    source_store_code TEXT NOT NULL,
    source_quantity_text TEXT NOT NULL,
    source_sell_price_kzt_text TEXT,
    source_delivery_fee_text TEXT,
    source_cogs_text TEXT,
    source_net_rev_text TEXT,
    source_profit_text TEXT,
    source_status TEXT,
    source_return_flag_text TEXT,
    source_return_date TEXT,
    source_ingested_at TEXT,
    source_file TEXT,
    source_api_updated_at TEXT,
    source_kaspi_article TEXT,
    candidate_publication_date TEXT NOT NULL,
    candidate_units_text TEXT NOT NULL,
    candidate_net_rev_kzt_text TEXT NOT NULL,
    selected_source_table TEXT NOT NULL,
    selected_source_sku_key TEXT NOT NULL,
    selected_source_sku_id TEXT NOT NULL,
    selected_my_size TEXT NOT NULL,
    selected_source_units_text TEXT NOT NULL,
    selected_source_net_rev_kzt_text TEXT NOT NULL,
    selected_sale_date TEXT NOT NULL,
    selected_units_text TEXT NOT NULL,
    selected_net_rev_kzt_text TEXT NOT NULL,
    PRIMARY KEY(candidate_id, line_ordinal),
    FOREIGN KEY(candidate_id) REFERENCES fact_sales_publication_binding_candidate_header(candidate_id) ON DELETE RESTRICT,
    UNIQUE(source_table, source_physical_row_value),
    CHECK(
      (immutable_identity_kind='API_ENTRY_AND_LINE_IDENTITY' AND
       source_entry_id IS NOT NULL AND line_identity_key IS NOT NULL) OR
      (immutable_identity_kind='CRM_XLSX_PHYSICAL_ROW' AND
       source_workbook_sha256 IS NOT NULL AND source_sheet IS NOT NULL AND
       source_workbook_physical_row IS NOT NULL AND
       source_formula_row_sha256 IS NOT NULL AND
       source_allowlisted_row_sha256 IS NOT NULL)
    )
);

CREATE VIEW view_sales_publication_binding_candidate_checks AS
SELECT
  h.candidate_id,
  h.order_id,
  h.store_code,
  h.candidate_status,
  h.active_flag,
  h.activation_eligible,
  h.provisional_flag,
  h.activation_blocker,
  h.terminal_date_semantics,
  (SELECT COUNT(*) FROM fact_sales_publication_binding_candidate_line l0
    WHERE l0.candidate_id=h.candidate_id) AS candidate_line_count,
  (SELECT COUNT(*) FROM fact_sales_workbook_anchor a
    WHERE CAST(a.order_id AS TEXT)=h.order_id AND UPPER(TRIM(a.store_code))=h.store_code) AS anchor_row_count,
  (SELECT COUNT(*) FROM fact_sales_workbook_anchor a
    WHERE CAST(a.order_id AS TEXT)=h.order_id AND UPPER(TRIM(a.store_code))=h.store_code
      AND CAST(a.sale_date AS TEXT) IS h.anchor_sale_date
      AND CAST(a.quantity AS REAL) IS CAST(h.anchor_quantity_text AS REAL)
      AND CAST(a.net_rev_kzt AS REAL) IS CAST(h.anchor_net_rev_kzt_text AS REAL)
      AND CAST(a.total_price_kzt AS REAL) IS CAST(h.anchor_total_price_kzt_text AS REAL)
      AND CAST(a.source_file AS TEXT) IS h.anchor_source_file
      AND CAST(a.updated_at AS TEXT) IS h.anchor_updated_at) AS anchor_preimage_match_count,
  (SELECT COUNT(*) FROM sales_fact_v2 s
    JOIN fact_sales_publication_binding_candidate_line l ON l.candidate_id=h.candidate_id
    WHERE s.sale_id=l.source_sale_id
      AND CAST(s.order_id AS TEXT) IS l.source_order_id
      AND CAST(s.order_date AS TEXT) IS l.source_order_date
      AND CAST(s.sku_key AS TEXT) IS l.source_sku_key
      AND CAST(s.sku_id AS TEXT) IS l.source_sku_id
      AND CAST(s.my_size AS TEXT) IS l.source_my_size
      AND CAST(s.kaspi_offer_name AS TEXT) IS l.source_kaspi_offer_name
      AND UPPER(TRIM(CAST(s.store_code AS TEXT))) IS l.source_store_code
      AND CAST(s.quantity AS REAL) IS CAST(l.source_quantity_text AS REAL)
      AND CAST(s.sell_price_kzt AS REAL) IS CAST(l.source_sell_price_kzt_text AS REAL)
      AND CAST(s.delivery_fee AS REAL) IS CAST(l.source_delivery_fee_text AS REAL)
      AND CAST(s.cogs AS REAL) IS CAST(l.source_cogs_text AS REAL)
      AND CAST(s.net_rev AS REAL) IS CAST(l.source_net_rev_text AS REAL)
      AND CAST(s.profit AS REAL) IS CAST(l.source_profit_text AS REAL)
      AND CAST(s.status AS TEXT) IS l.source_status
      AND CAST(s.return_flag AS INTEGER) IS CAST(l.source_return_flag_text AS INTEGER)
      AND CAST(s.return_date AS TEXT) IS l.source_return_date
      AND CAST(s.ingested_at AS TEXT) IS l.source_ingested_at
      AND CAST(s.source_file AS TEXT) IS l.source_file
      AND CAST(s.api_updated_at AS TEXT) IS l.source_api_updated_at
      AND CAST(s.source_entry_id AS TEXT) IS l.source_entry_id
      AND CAST(s.kaspi_article AS TEXT) IS l.source_kaspi_article
      AND CAST(s.line_identity_key AS TEXT) IS l.line_identity_key) AS source_preimage_match_count,
  (SELECT COUNT(*) FROM view_sales_line_truth v
    WHERE CAST(v.order_id AS TEXT)=h.order_id AND UPPER(TRIM(v.store_code))=h.store_code) AS selected_row_count,
  (SELECT COUNT(*) FROM view_sales_line_truth v
    JOIN fact_sales_publication_binding_candidate_line l ON l.candidate_id=h.candidate_id
    WHERE CAST(v.order_id AS TEXT)=h.order_id AND UPPER(TRIM(v.store_code))=h.store_code
      AND CAST(v.source_table AS TEXT) IS l.selected_source_table
      AND CAST(v.source_sku_key AS TEXT) IS l.selected_source_sku_key
      AND CAST(v.source_sku_id AS TEXT) IS l.selected_source_sku_id
      AND CAST(v.my_size AS TEXT) IS l.selected_my_size
      AND CAST(v.source_units AS REAL) IS CAST(l.selected_source_units_text AS REAL)
      AND CAST(v.source_net_rev_kzt AS REAL) IS CAST(l.selected_source_net_rev_kzt_text AS REAL)
      AND CAST(v.sale_date AS TEXT) IS l.selected_sale_date
      AND CAST(v.units AS REAL) IS CAST(l.selected_units_text AS REAL)
      AND CAST(v.net_rev_kzt AS REAL) IS CAST(l.selected_net_rev_kzt_text AS REAL)) AS selected_preimage_match_count,
  (SELECT COUNT(*) FROM sales_publication_binding_candidate_prototype_meta m
    WHERE m.prototype_id=1 AND m.policy_sha256=h.policy_sha256
      AND m.manifest_payload_sha256=h.originating_manifest_payload_sha256) AS policy_manifest_match_count
FROM fact_sales_publication_binding_candidate_header h;

CREATE VIEW view_sales_publication_binding_candidate_validation AS
SELECT
  c.*,
  CASE
    WHEN c.candidate_line_count<>1 OR c.anchor_row_count<>1 OR
         c.anchor_preimage_match_count<>1 OR c.source_preimage_match_count<>1 OR
         c.selected_row_count<>1 OR c.selected_preimage_match_count<>1 OR
         c.policy_manifest_match_count<>1 OR c.active_flag<>0
      THEN 'INVALID'
    WHEN c.candidate_status='VALID' AND c.activation_eligible=1 AND
         c.provisional_flag=0 AND c.activation_blocker=''
      THEN 'VALID'
    ELSE 'CANDIDATE'
  END AS effective_status,
  0 AS publication_binding_usable
FROM view_sales_publication_binding_candidate_checks c;
"""


def _as_db_text(value: Any) -> str | None:
    return None if value is None else str(value)


def _as_nullable_db_text(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _insert_manifest(
    conn: sqlite3.Connection,
    *,
    manifest: dict[str, Any],
    manifest_file_sha256: str,
    source_db_sha256: str,
    targets: Iterable[dict[str, Any]],
) -> None:
    targets = list(targets)
    conn.execute(
        """
        INSERT INTO sales_publication_binding_candidate_prototype_meta VALUES
        (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
        """,
        (
            PROTOTYPE_SCHEMA,
            MANIFEST_SCHEMA,
            manifest_file_sha256,
            manifest["manifest_sha256"],
            manifest["binding_payload_sha256"],
            manifest["policy_sha256"],
            source_db_sha256,
            manifest["target_key_sha256"],
            len(targets),
            datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        ),
    )
    for target in targets:
        header = target["binding_header_candidate"]
        anchor = target["workbook_anchor_preimage"]
        cursor = conn.execute(
            """
            INSERT INTO fact_sales_publication_binding_candidate_header (
              order_id, store_code, candidate_status, active_flag,
              activation_eligible, provisional_flag, activation_blocker,
              binding_version, reason, candidate_publication_date,
              terminal_date_semantics, terminal_rank, canonical_hash_version,
              copied_db_sha256, policy_sha256,
              originating_manifest_payload_sha256, workbook_anchor_sha256,
              selected_source_line_multiset_sha256,
              source_line_multiset_sha256, terminal_evidence_sha256,
              terminal_all_positive_evidence_sha256,
              terminal_later_positive_evidence_sha256,
              terminal_negative_evidence_sha256, anchor_sale_date,
              anchor_quantity_text, anchor_net_rev_kzt_text,
              anchor_total_price_kzt_text, anchor_source_file, anchor_updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                header["order_id"],
                _text(header["store_code"]).upper(),
                "CANDIDATE",
                0,
                int(bool(header["activation_eligible"])),
                int(bool(header["provisional_flag"])),
                header["activation_blocker"],
                header["binding_version"],
                header["reason"],
                header["candidate_publication_date"],
                header["terminal_date_semantics"],
                int(header["terminal_rank"]),
                header["canonical_hash_version"],
                header["copied_db_sha256"],
                header["policy_sha256"],
                header["originating_manifest_payload_sha256"],
                header["workbook_anchor_sha256"],
                header["selected_source_line_multiset_sha256"],
                header["source_line_multiset_sha256"],
                header["terminal_evidence_sha256"],
                header["terminal_all_positive_evidence_sha256"],
                header["terminal_later_positive_evidence_sha256"],
                header["terminal_negative_evidence_sha256"],
                _as_db_text(anchor["sale_date"]),
                _as_db_text(anchor["quantity"]),
                _as_db_text(anchor["net_rev_kzt"]),
                _as_db_text(anchor["total_price_kzt"]),
                _as_db_text(anchor.get("source_file")),
                _as_db_text(anchor.get("updated_at")),
            ),
        )
        candidate_id = int(cursor.lastrowid)
        line = target["binding_line_candidates"][0]
        source = line["source_row_preimage"]
        selected = target["selected_source_line_preimages"][0]
        identity = line["immutable_source_identity"]
        conn.execute(
            """
            INSERT INTO fact_sales_publication_binding_candidate_line (
              candidate_id, line_ordinal, source_table,
              source_physical_row_column, source_physical_row_value,
              source_entry_id, line_identity_key, immutable_identity_kind,
              immutable_source_identity_sha256, source_workbook_sha256,
              source_sheet, source_workbook_physical_row,
              source_formula_row_sha256, source_allowlisted_row_sha256,
              source_proof_key, source_proof_preimage_sha256,
              source_proof_jsonl_sha256, source_promotion_apply_report_sha256,
              source_row_sha256, source_sale_id, source_order_id,
              source_order_date, source_sku_key, source_sku_id, source_my_size,
              source_kaspi_offer_name, source_store_code, source_quantity_text,
              source_sell_price_kzt_text, source_delivery_fee_text,
              source_cogs_text, source_net_rev_text, source_profit_text,
              source_status, source_return_flag_text, source_return_date,
              source_ingested_at, source_file, source_api_updated_at,
              source_kaspi_article, candidate_publication_date,
              candidate_units_text, candidate_net_rev_kzt_text,
              selected_source_table, selected_source_sku_key,
              selected_source_sku_id, selected_my_size,
              selected_source_units_text, selected_source_net_rev_kzt_text,
              selected_sale_date, selected_units_text,
              selected_net_rev_kzt_text
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                candidate_id,
                int(line["line_ordinal"]),
                line["source_table"],
                line["source_physical_row_id"]["column"],
                int(line["source_physical_row_id"]["value"]),
                _as_nullable_db_text(line.get("source_entry_id")),
                _as_nullable_db_text(line.get("line_identity_key")),
                identity["kind"],
                line["immutable_source_identity_sha256"],
                _as_db_text(identity.get("source_workbook_sha256")),
                _as_db_text(identity.get("source_sheet")),
                identity.get("source_physical_row"),
                _as_db_text(identity.get("source_formula_row_sha256")),
                _as_db_text(identity.get("source_allowlisted_row_sha256")),
                _as_db_text(identity.get("proof_key")),
                _as_db_text(identity.get("proof_preimage_sha256")),
                _as_db_text(identity.get("proof_jsonl_sha256")),
                _as_db_text(identity.get("promotion_apply_report_sha256")),
                line["source_row_sha256"],
                int(source["sale_id"]),
                _as_db_text(source["order_id"]),
                _as_db_text(source["order_date"]),
                _as_db_text(source["sku_key"]),
                _as_db_text(source["sku_id"]),
                _as_db_text(source["my_size"]),
                _as_db_text(source["kaspi_offer_name"]),
                _text(source["store_code"]).upper(),
                _as_db_text(source["quantity"]),
                _as_db_text(source.get("sell_price_kzt")),
                _as_db_text(source.get("delivery_fee")),
                _as_db_text(source.get("cogs")),
                _as_db_text(source.get("net_rev")),
                _as_db_text(source.get("profit")),
                _as_db_text(source.get("status")),
                _as_db_text(source.get("return_flag")),
                _as_db_text(source.get("return_date")),
                _as_db_text(source.get("ingested_at")),
                _as_db_text(source.get("source_file")),
                _as_db_text(source.get("api_updated_at")),
                _as_db_text(source.get("kaspi_article")),
                line["candidate_publication_date"],
                _as_db_text(line["candidate_units"]),
                _as_db_text(line["candidate_net_rev_kzt"]),
                _as_db_text(selected["source_table"]),
                _as_db_text(selected["source_sku_key"]),
                _as_db_text(selected["source_sku_id"]),
                _as_db_text(selected["my_size"]),
                _as_db_text(selected["source_units"]),
                _as_db_text(selected["source_net_rev_kzt"]),
                _as_db_text(selected["sale_date"]),
                _as_db_text(selected["units"]),
                _as_db_text(selected["net_rev_kzt"]),
            ),
        )


def _prototype_readback(
    conn: sqlite3.Connection,
    *,
    expected_target_count: int,
) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    integrity = _text(conn.execute("PRAGMA integrity_check").fetchone()[0])
    header_count = int(
        conn.execute(
            "SELECT COUNT(*) FROM fact_sales_publication_binding_candidate_header"
        ).fetchone()[0]
    )
    line_count = int(
        conn.execute(
            "SELECT COUNT(*) FROM fact_sales_publication_binding_candidate_line"
        ).fetchone()[0]
    )
    status_counts = {
        row[0]: int(row[1])
        for row in conn.execute(
            "SELECT effective_status, COUNT(*) FROM "
            "view_sales_publication_binding_candidate_validation "
            "GROUP BY effective_status ORDER BY effective_status"
        )
    }
    invalid_count = int(
        conn.execute(
            "SELECT COUNT(*) FROM view_sales_publication_binding_candidate_validation "
            "WHERE effective_status='INVALID'"
        ).fetchone()[0]
    )
    usable_count = int(
        conn.execute(
            "SELECT COUNT(*) FROM view_sales_publication_binding_candidate_validation "
            "WHERE publication_binding_usable<>0"
        ).fetchone()[0]
    )
    activation_eligible_count = int(
        conn.execute(
            "SELECT COALESCE(SUM(activation_eligible),0) FROM "
            "fact_sales_publication_binding_candidate_header"
        ).fetchone()[0]
    )
    active_count = int(
        conn.execute(
            "SELECT COALESCE(SUM(active_flag),0) FROM "
            "fact_sales_publication_binding_candidate_header"
        ).fetchone()[0]
    )
    target_keys = [
        [row[0], row[1]]
        for row in conn.execute(
            "SELECT order_id, store_code FROM "
            "fact_sales_publication_binding_candidate_header "
            "ORDER BY store_code, order_id"
        )
    ]
    check_pass_counts_row = conn.execute(
        """
        SELECT
          SUM(candidate_line_count=1),
          SUM(anchor_row_count=1),
          SUM(anchor_preimage_match_count=1),
          SUM(source_preimage_match_count=1),
          SUM(selected_row_count=1),
          SUM(selected_preimage_match_count=1),
          SUM(policy_manifest_match_count=1)
        FROM view_sales_publication_binding_candidate_checks
        """
    ).fetchone()
    check_names = (
        "candidate_line_count",
        "anchor_row_count",
        "anchor_preimage_match_count",
        "source_preimage_match_count",
        "selected_row_count",
        "selected_preimage_match_count",
        "policy_manifest_match_count",
    )
    check_pass_counts = {
        name: int(check_pass_counts_row[index] or 0)
        for index, name in enumerate(check_names)
    }
    invalid_targets = [
        {
            "order_id": row[0],
            "store_code": row[1],
            "candidate_line_count": int(row[2]),
            "anchor_row_count": int(row[3]),
            "anchor_preimage_match_count": int(row[4]),
            "source_preimage_match_count": int(row[5]),
            "selected_row_count": int(row[6]),
            "selected_preimage_match_count": int(row[7]),
            "policy_manifest_match_count": int(row[8]),
        }
        for row in conn.execute(
            """
            SELECT order_id, store_code, candidate_line_count, anchor_row_count,
                   anchor_preimage_match_count, source_preimage_match_count,
                   selected_row_count, selected_preimage_match_count,
                   policy_manifest_match_count
            FROM view_sales_publication_binding_candidate_checks
            WHERE candidate_line_count<>1 OR anchor_row_count<>1 OR
                  anchor_preimage_match_count<>1 OR
                  source_preimage_match_count<>1 OR selected_row_count<>1 OR
                  selected_preimage_match_count<>1 OR
                  policy_manifest_match_count<>1
            ORDER BY store_code, order_id
            LIMIT 20
            """
        )
    ]
    ok = (
        integrity == "ok"
        and header_count == line_count == expected_target_count
        and status_counts == {"CANDIDATE": expected_target_count}
        and invalid_count == usable_count == activation_eligible_count == active_count == 0
    )
    return {
        "ok": ok,
        "integrity": integrity,
        "header_count": header_count,
        "line_count": line_count,
        "effective_status_counts": status_counts,
        "invalid_count": invalid_count,
        "publication_binding_usable_count": usable_count,
        "activation_eligible_count": activation_eligible_count,
        "active_count": active_count,
        "target_key_sha256": _canonical_sha(target_keys),
        "check_pass_counts": check_pass_counts,
        "invalid_targets": invalid_targets,
    }


def build_prototype(
    *,
    source_db: Path,
    manifest_path: Path,
    output_db: Path,
    report_path: Path | None,
    apply: bool,
    expected_manifest_file_sha256: str | None = None,
    expected_target_count: int | None = None,
) -> dict[str, Any]:
    source_db = source_db.expanduser().resolve()
    manifest_path = manifest_path.expanduser().resolve()
    output_db = output_db.expanduser().resolve()
    report_path = report_path.expanduser().resolve() if report_path else None
    if not source_db.is_file() or not manifest_path.is_file():
        raise PrototypeError("source DB or manifest is missing")
    if source_db == CANONICAL_DB_PATH:
        raise PrototypeError("canonical production db/app.db is forbidden")
    if output_db in {source_db, CANONICAL_DB_PATH}:
        raise PrototypeError("output DB must be a new non-production copy")
    if output_db.exists():
        raise PrototypeError("output DB already exists")
    if report_path is not None:
        protected_paths = {
            source_db,
            manifest_path,
            output_db,
            CANONICAL_DB_PATH,
        }
        if report_path in protected_paths:
            raise PrototypeError("report path collides with a protected input or DB")
        if report_path.exists():
            if any(
                protected.exists() and os.path.samefile(report_path, protected)
                for protected in protected_paths
            ):
                raise PrototypeError(
                    "report path aliases a protected input or DB"
                )
            raise PrototypeError("report path already exists")

    manifest_file_sha = _file_sha256(manifest_path)
    manifest = _read_json(manifest_path)
    targets = _validate_manifest(
        manifest,
        manifest_file_sha256=manifest_file_sha,
        expected_manifest_file_sha256=expected_manifest_file_sha256,
        expected_target_count=expected_target_count,
    )
    source_sha_before = _file_sha256(source_db)
    if source_sha_before != _text(manifest.get("db_sha256_before")):
        raise PrototypeError("source DB SHA-256 does not match manifest")
    with _connect_read_only(source_db) as source_conn:
        integrity = _text(source_conn.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity != "ok":
            raise PrototypeError(f"source DB integrity failed: {integrity}")
        source_truth_hashes = _truth_hashes(source_conn)

    plan = {
        "schema": PROTOTYPE_SCHEMA,
        "mode": "APPLY" if apply else "DRY_RUN",
        "source_db": str(source_db),
        "source_db_sha256": source_sha_before,
        "source_db_integrity": integrity,
        "manifest_path": str(manifest_path),
        "manifest_file_sha256": manifest_file_sha,
        "manifest_internal_sha256": manifest["manifest_sha256"],
        "manifest_payload_sha256": manifest["binding_payload_sha256"],
        "target_count": len(targets),
        "activation_eligible_count": 0,
        "activation_blocked_count": len(targets),
        "output_db": str(output_db),
        "production_authority": False,
        "published_view_change_authorized": False,
        "source_truth_hashes_before": source_truth_hashes,
        "write_applied": False,
    }
    if not apply:
        return plan
    if os.environ.get(ENV_GATE) != "1":
        raise PrototypeError(f"apply requires {ENV_GATE}=1")

    output_db.parent.mkdir(parents=True, exist_ok=True)
    try:
        with _connect_read_only(source_db) as source_conn:
            with sqlite3.connect(output_db) as destination:
                source_conn.backup(destination)
        with sqlite3.connect(output_db) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript(SCHEMA_SQL)
            conn.execute("BEGIN IMMEDIATE")
            _insert_manifest(
                conn,
                manifest=manifest,
                manifest_file_sha256=manifest_file_sha,
                source_db_sha256=source_sha_before,
                targets=targets,
            )
            conn.commit()
            readback = _prototype_readback(
                conn, expected_target_count=len(targets)
            )
            output_truth_hashes = _truth_hashes(conn)
        if not readback["ok"]:
            raise PrototypeError(f"prototype readback failed: {readback}")
        if readback["target_key_sha256"] != _text(
            manifest.get("target_key_sha256")
        ):
            raise PrototypeError("prototype target-key SHA-256 changed")
        if output_truth_hashes != source_truth_hashes:
            raise PrototypeError("source or published-view logical hashes changed")
        source_sha_after = _file_sha256(source_db)
        if source_sha_after != source_sha_before:
            raise PrototypeError("source DB bytes changed")
        result = {
            **plan,
            "write_applied": True,
            "source_db_sha256_after": source_sha_after,
            "output_db_sha256": _file_sha256(output_db),
            "source_truth_hashes_after": output_truth_hashes,
            "readback": readback,
        }
        result["report_sha256"] = _canonical_sha(
            {key: value for key, value in result.items() if key != "report_sha256"}
        )
        if report_path:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            with report_path.open("x", encoding="utf-8") as report_file:
                report_file.write(
                    json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n"
                )
            if _file_sha256(source_db) != source_sha_before:
                raise PrototypeError("source DB bytes changed after report write")
            if _file_sha256(manifest_path) != manifest_file_sha:
                raise PrototypeError("manifest bytes changed after report write")
            if _file_sha256(output_db) != result["output_db_sha256"]:
                raise PrototypeError("output DB bytes changed after report write")
        return result
    except Exception:
        if output_db.exists():
            output_db.unlink()
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-db", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--expected-manifest-file-sha256")
    parser.add_argument("--expected-target-count", type=int)
    parser.add_argument("--apply", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    report = build_prototype(
        source_db=args.source_db,
        manifest_path=args.manifest,
        output_db=args.output_db,
        report_path=args.report,
        apply=args.apply,
        expected_manifest_file_sha256=args.expected_manifest_file_sha256,
        expected_target_count=args.expected_target_count,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
