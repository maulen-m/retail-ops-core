from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import sqlite3

from scripts.build_publication_anchor_reconciliation_packet import (
    _canonical_sha,
    _load_lifecycle_evidence,
    _terminal_resolution,
    build_packet,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_packet_separates_formula_publication_and_terminal_date(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE fact_sales_workbook_anchor (
                order_id TEXT, store_code TEXT, sale_date TEXT, quantity REAL,
                net_rev_kzt REAL, total_price_kzt REAL, source_file TEXT
            );
            CREATE TABLE fact_order_status_observations (
                id INTEGER PRIMARY KEY, order_id TEXT, store_code TEXT,
                status_internal TEXT, observed_at TEXT, source TEXT
            );
            INSERT INTO fact_sales_workbook_anchor VALUES
                ('O1', 'UNIVERSAL', '2026-03-01', 1, 990, 1000, 'source.xlsx'),
                ('O2', 'ACMEWEAR', '2026-01-01', 1, 900, 1000, 'source.xlsx');
            INSERT INTO fact_order_status_observations VALUES
                (1, 'O1', 'UNIVERSAL', 'DELIVERED', '2026-03-03', 'WEBUI'),
                (2, 'O2', 'ACMEWEAR', 'DELIVERED', '2026-01-05', 'WEBUI'),
                (3, 'O1', 'UNIVERSAL', 'COMPLETED', '2026-03-05', 'API');
            """
        )

    classification = tmp_path / "classification.csv"
    _write_csv(
        classification,
        [
            {
                "order_id": "O1",
                "store_code": "UNIVERSAL",
                "classification": "WORKBOOK_ANCHOR_AMOUNT_OVERRIDE_ONLY",
                "selected_sale_dates": "2026-03-01",
                "source_dates": "2026-03-01",
            },
            {
                "order_id": "O2",
                "store_code": "ACMEWEAR",
                "classification": "WORKBOOK_ANCHOR_DATE_OVERRIDE_ONLY",
                "selected_sale_dates": "2026-01-01",
                "source_dates": "2025-12-31",
            },
        ],
    )
    order_rows = tmp_path / "order_rows.csv"
    _write_csv(
        order_rows,
        [
            {
                "order_id": "O1",
                "store_code": "UNIVERSAL",
                "sales_amount_source_formula_proven": "True",
                "sales_amount_source_formula_unproven_line_count": "0",
                "sales_amount_publication_binding_proven": "False",
            },
            {
                "order_id": "O2",
                "store_code": "ACMEWEAR",
                "sales_amount_source_formula_proven": "True",
                "sales_amount_source_formula_unproven_line_count": "0",
                "sales_amount_publication_binding_proven": "False",
            },
        ],
    )
    cash_report = tmp_path / "cash.json"
    cash_report.write_text(
        json.dumps(
            {
                "status": "FAIL",
                "covered_pairs": 0,
                "order_rows_csv": str(order_rows),
            }
        ),
        encoding="utf-8",
    )
    before = db.read_bytes()
    packet = build_packet(
        db_path=db,
        classification_csv=classification,
        cash_report_path=cash_report,
        output_dir=tmp_path / "out",
        statusdate_cutover=__import__("datetime").date(2026, 2, 27),
        expected_mismatch_rows=2,
        expected_source_formula_proven=2,
    )
    assert db.read_bytes() == before
    assert packet["source_formula_proven_count"] == 2
    assert packet["next_action_counts"] == {
        "PRE_CUTOVER_PROVISIONAL_SOURCE_VALUES_AVAILABLE": 1,
        "RECOMPUTE_SOURCE_FORMULA_AT_TERMINAL_OBSERVATION_CANDIDATE_DATE": 1,
    }
    assert packet["db_sha256_before"] == packet["db_sha256_after"]
    assert packet["schema"] == "publication_anchor_reconciliation_v5"
    assert packet["canonical_hash_version"] == (
        "canonical-json-v1-sort-keys-utf8-no-whitespace"
    )
    assert Path(packet["manifest_path"]).is_file()
    assert Path(packet["closeout_path"]).is_file()
    rows = list(csv.DictReader(Path(packet["rows_csv"]["path"]).open()))
    o1 = next(row for row in rows if row["order_id"] == "O1")
    assert o1["terminal_date_status"] == (
        "DIRECT_TERMINAL_OBSERVATION_DATE_CANDIDATE"
    )
    assert o1["terminal_date_semantics"] == (
        "TERMINAL_OBSERVATION_DATE_CANDIDATE"
    )
    assert o1["terminal_activation_eligible"] == "False"
    assert o1["terminal_all_positive_evidence_count"] == "2"
    assert o1["terminal_later_positive_evidence_count"] == "1"


def test_unexplained_multiline_with_exact_api_entries_is_economics_not_identity_gap(
    tmp_path: Path,
) -> None:
    db = tmp_path / "app.db"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE fact_sales_workbook_anchor (
                order_id TEXT, store_code TEXT, sale_date TEXT, quantity REAL,
                net_rev_kzt REAL, total_price_kzt REAL, source_file TEXT
            );
            CREATE TABLE fact_order_status_observations (
                id INTEGER PRIMARY KEY, order_id TEXT, store_code TEXT,
                status_internal TEXT, observed_at TEXT, source TEXT
            );
            CREATE TABLE sales_fact_v2 (
                sale_id INTEGER PRIMARY KEY, order_id TEXT, store_code TEXT,
                sku_key TEXT, sku_id TEXT, my_size TEXT, quantity REAL,
                sell_price_kzt REAL, kaspi_article TEXT, source_entry_id TEXT,
                line_identity_key TEXT
            );
            CREATE TABLE fact_orders_kaspi (
                id INTEGER PRIMARY KEY, order_id TEXT, store_code TEXT,
                sku_key TEXT, sku_id TEXT, my_size TEXT, quantity REAL,
                unit_price_kzt REAL, kaspi_article TEXT, source_entry_id TEXT,
                source TEXT
            );
            INSERT INTO fact_order_status_observations VALUES
                (1, 'O3', 'UNIVERSAL', 'COMPLETED', '2026-03-03', 'API');
            INSERT INTO sales_fact_v2 VALUES
                (10, 'O3', 'UNIVERSAL', 'SKU_A', 'SKU_A_S', 'S', 1,
                 1000, 'ART_A', 'ENTRY-A', 'ENTRY:ENTRY-A'),
                (11, 'O3', 'UNIVERSAL', 'SKU_B', 'SKU_B_M', 'M', 2,
                 2000, 'ART_B', 'ENTRY-B', 'ENTRY:ENTRY-B');
            INSERT INTO fact_orders_kaspi VALUES
                (20, 'O3', 'UNIVERSAL', 'SKU_A', 'SKU_A_S', 'S', 1,
                 1000, 'ART_A', 'ENTRY-A', 'API'),
                (21, 'O3', 'UNIVERSAL', 'SKU_B', 'SKU_B_M', 'M', 2,
                 2000, 'ART_B', 'ENTRY-B', 'API');
            """
        )
    classification = tmp_path / "classification.csv"
    _write_csv(
        classification,
        [
            {
                "order_id": "O3",
                "store_code": "UNIVERSAL",
                "classification": "UNEXPLAINED_SOURCE_LINE_MISMATCH",
                "source_line_count": "2",
                "selected_sale_dates": "2026-03-01",
                "source_dates": "2026-03-01",
            }
        ],
    )
    order_rows = tmp_path / "order_rows.csv"
    _write_csv(
        order_rows,
        [
            {
                "order_id": "O3",
                "store_code": "UNIVERSAL",
                "sales_amount_source_formula_proven": "False",
                "sales_amount_source_formula_unproven_line_count": "1",
                "sales_amount_publication_binding_proven": "False",
            }
        ],
    )
    cash_report = tmp_path / "cash.json"
    cash_report.write_text(
        json.dumps(
            {"status": "FAIL", "covered_pairs": 0, "order_rows_csv": str(order_rows)}
        ),
        encoding="utf-8",
    )
    packet = build_packet(
        db_path=db,
        classification_csv=classification,
        cash_report_path=cash_report,
        output_dir=tmp_path / "out",
        statusdate_cutover=__import__("datetime").date(2026, 2, 27),
        expected_mismatch_rows=1,
        expected_source_formula_proven=0,
    )
    assert packet["source_line_identity_proven_count"] == 1
    assert packet["next_action_counts"] == {
        "SOURCE_LINE_ECONOMICS_PROOF_REQUIRED": 1
    }
    row = next(csv.DictReader(Path(packet["rows_csv"]["path"]).open()))
    assert row["source_line_identity_proven"] == "True"
    assert row["source_line_identity_count"] == "2"
    assert len(row["source_line_identity_evidence_sha256"]) == 64
    assert row["effective_classification"] == (
        "SOURCE_LINE_IDENTITY_PROVEN_ECONOMICS_UNRESOLVED"
    )


def test_pinned_derived_order_conflict_overrides_terminal_proof_request(
    tmp_path: Path,
) -> None:
    db = tmp_path / "app.db"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE fact_sales_workbook_anchor (
                order_id TEXT, store_code TEXT, sale_date TEXT, quantity REAL,
                net_rev_kzt REAL, total_price_kzt REAL, source_file TEXT
            );
            CREATE TABLE fact_order_status_observations (
                id INTEGER PRIMARY KEY, order_id TEXT, store_code TEXT,
                status_internal TEXT, observed_at TEXT, source TEXT
            );
            INSERT INTO fact_sales_workbook_anchor VALUES
                ('610999345', 'ACMEWEAR', '2025-08-12', 1, 1186.55, 1398,
                 'source.xlsx');
            """
        )
    classification = tmp_path / "classification.csv"
    _write_csv(
        classification,
        [
            {
                "order_id": "610999345",
                "store_code": "ACMEWEAR",
                "classification": "WORKBOOK_ANCHOR_AMOUNT_OVERRIDE_ONLY",
                "selected_sale_dates": "2025-08-12",
                "source_dates": "2025-08-12",
            }
        ],
    )
    order_rows = tmp_path / "order_rows.csv"
    _write_csv(
        order_rows,
        [
            {
                "order_id": "610999345",
                "store_code": "ACMEWEAR",
                "sales_amount_source_formula_proven": "True",
                "sales_amount_source_formula_unproven_line_count": "0",
                "sales_amount_publication_binding_proven": "False",
            }
        ],
    )
    cash_report = tmp_path / "cash.json"
    cash_report.write_text(
        json.dumps(
            {"status": "FAIL", "covered_pairs": 0, "order_rows_csv": str(order_rows)}
        ),
        encoding="utf-8",
    )
    conflict_payload = {
        "schema": "derived_order_id_conflict_packet_v2",
        "verdict": "DERIVED_ORDER_ID_CONFLICT_QUARANTINE",
        "derived_order_id": "610999345",
        "raw_order_id": "610619543",
        "expected_store": "ACMEWEAR",
        "workbook_safe_row_sha256": "a" * 64,
        "proofs": {
            "derived_and_raw_ids_differ": True,
            "all_pinned_workbooks_match_one_safe_row": True,
            "derived_anchor_exists": True,
            "raw_anchor_absent": True,
            "derived_terminal_evidence_absent": True,
            "raw_terminal_evidence_present": True,
            "raw_product_identity_matches_workbook": True,
            "production_write_authorized": False,
        },
    }
    conflict_payload["evidence_sha256"] = _canonical_sha(conflict_payload)
    conflict_path = tmp_path / "conflict.json"
    conflict_path.write_text(json.dumps(conflict_payload), encoding="utf-8")
    conflict_file_sha = hashlib.sha256(conflict_path.read_bytes()).hexdigest()
    packet = build_packet(
        db_path=db,
        classification_csv=classification,
        cash_report_path=cash_report,
        output_dir=tmp_path / "out",
        statusdate_cutover=__import__("datetime").date(2026, 2, 27),
        expected_mismatch_rows=1,
        expected_source_formula_proven=1,
        derived_order_conflict_evidence_path=conflict_path,
        expected_derived_order_conflict_evidence_sha256=conflict_file_sha,
    )
    assert packet["derived_order_id_conflict_quarantine_count"] == 1
    assert packet["next_action_counts"] == {
        "QUARANTINE_DERIVED_ORDER_ID_CONFLICT": 1
    }
    row = next(csv.DictReader(Path(packet["rows_csv"]["path"]).open()))
    assert row["effective_classification"] == (
        "DERIVED_ORDER_ID_CONFLICT_QUARANTINE"
    )
    assert row["derived_order_id_conflict_raw_order_id"] == "610619543"


def test_complete_api_order_rank_four_requires_every_row_and_one_date(
    tmp_path: Path,
) -> None:
    db = tmp_path / "rank4.db"
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE fact_orders_kaspi (
                id INTEGER PRIMARY KEY, order_id TEXT, store_code TEXT,
                internal_status TEXT, kaspi_status TEXT, source TEXT,
                status_updated_at TEXT
            );
            INSERT INTO fact_orders_kaspi VALUES
                (1, 'O1', 'ACMEWEAR', 'COMPLETED', 'ARCHIVE', 'API',
                 '2026-03-03T10:00:00Z'),
                (2, 'O1', 'ACMEWEAR', 'ACTIVE', 'NEW', 'API',
                 '2026-03-03T10:00:00Z');
            """
        )
        key = ("O1", "ACMEWEAR")
        assert _load_lifecycle_evidence(conn, {key}).get(key, []) == []

        conn.execute(
            "UPDATE fact_orders_kaspi SET internal_status='COMPLETED', "
            "kaspi_status='ARCHIVE' WHERE id=2"
        )
        complete = _load_lifecycle_evidence(conn, {key})[key]
        assert len(complete) == 1
        assert complete[0]["rank"] == 4
        assert complete[0]["evidence_kind"] == (
            "COMPLETE_API_ORDER_STATUS_UPDATED_AT"
        )
        resolved = _terminal_resolution(complete)
        assert resolved["status"] == (
            "DIRECT_TERMINAL_OBSERVATION_DATE_CANDIDATE"
        )
        assert resolved["activation_eligible"] is False

        conn.execute(
            "UPDATE fact_orders_kaspi SET status_updated_at="
            "'2026-03-04T10:00:00Z' WHERE id=2"
        )
        ambiguous = _terminal_resolution(_load_lifecycle_evidence(conn, {key})[key])
        assert ambiguous["status"] == "AMBIGUOUS_TOP_RANK_TERMINAL_DATE"
        assert ambiguous["activation_eligible"] is False


def test_source_status_change_timestamp_is_distinct_from_observation() -> None:
    exact = {
        "rank": 2,
        "status": "COMPLETED",
        "event_date": "2026-03-03",
        "source": "WEBUI_STATUS_LEDGER_SCOPED",
        "source_table": "order_status_event",
        "evidence_kind": "SOURCE_STATUS_CHANGE_TIMESTAMP",
        "row_id": "1",
        "row_preimage": {},
        "row_sha256": "a" * 64,
    }
    later_observation = {
        **exact,
        "rank": 3,
        "event_date": "2026-03-05",
        "source": "API",
        "source_table": "fact_order_status_observations",
        "evidence_kind": "TERMINAL_STATUS_OBSERVATION",
        "row_id": "2",
        "row_sha256": "b" * 64,
    }
    resolved = _terminal_resolution([later_observation, exact])
    assert resolved["status"] == "DIRECT_TERMINAL_STATUS_CHANGE_DATE"
    assert resolved["date_semantics"] == "STATUS_CHANGE_TIMESTAMP_PROVEN"
    assert resolved["activation_eligible"] is True
    assert resolved["later_positive_evidence"] == [later_observation]
