from __future__ import annotations

import csv
from datetime import date
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from core.calc.economics import calc_net_rev
from scripts.build_terminal_date_source_formula_manifest import (
    CANONICAL_HASH_VERSION,
    ManifestError,
    _canonical_sha,
    build_manifest,
)
from scripts.build_publication_anchor_reconciliation_packet import (
    _load_lifecycle_evidence,
    _terminal_resolution,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed(tmp_path: Path) -> tuple[Path, Path]:
    db = tmp_path / "app.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE sales_fact_v2 (
            sale_id INTEGER PRIMARY KEY,
            order_id TEXT NOT NULL,
            order_date DATE NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT NOT NULL,
            kaspi_offer_name TEXT NOT NULL,
            store_code TEXT,
            quantity INTEGER NOT NULL,
            sell_price_kzt REAL,
            delivery_fee REAL,
            cogs REAL,
            net_rev REAL,
            profit REAL,
            status TEXT,
            return_flag INTEGER,
            return_date DATE,
            ingested_at DATETIME,
            source_file TEXT,
            api_updated_at DATETIME,
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
        CREATE TABLE fact_order_status_observations (
            id INTEGER PRIMARY KEY,
            order_id TEXT NOT NULL,
            store_code TEXT NOT NULL,
            status_internal TEXT NOT NULL,
            source TEXT NOT NULL,
            observed_at TEXT NOT NULL
        );
        """
    )
    net_rev = round(
        calc_net_rev(9000.0, delivery_fee=500.0, as_of_date=date(2026, 3, 1)), 2
    )
    conn.execute(
        """
        INSERT INTO sales_fact_v2 VALUES (
            1, 'ORDER-1', '2026-03-01', 'SKU_A', 'SKU_A_M', 'M', 'Offer A',
            'ACMEWEAR', 1, 9000, 500, NULL, ?, NULL, 'DELIVERED', 0, NULL,
            '2026-03-01T00:00:00Z', 'source.csv', '2026-03-01T00:00:00Z',
            'ENTRY-1', 'ARTICLE-1', 'LINE-1'
        )
        """,
        (net_rev,),
    )
    conn.execute(
        """
        INSERT INTO fact_sales_workbook_anchor VALUES (
            'ORDER-1', 'ACMEWEAR', '2026-03-01', 1, ?, 9000,
            'workbook.xlsx', '2026-03-02T00:00:00Z'
        )
        """,
        (net_rev + 10,),
    )
    conn.execute(
        """
        INSERT INTO fact_order_status_observations VALUES (
            1, 'ORDER-1', 'ACMEWEAR', 'COMPLETED', 'API',
            '2026-03-03T12:00:00Z'
        )
        """
    )
    conn.execute(
        """
        CREATE VIEW view_sales_line_truth AS
        SELECT
            s.order_id,
            a.sale_date,
            s.store_code,
            s.sku_key,
            s.sku_id,
            s.my_size,
            a.quantity AS units,
            a.net_rev_kzt,
            'sales_fact_v2' AS source_table,
            s.sku_key AS source_sku_key,
            s.sku_id AS source_sku_id,
            s.quantity AS source_units,
            s.net_rev AS source_net_rev_kzt
        FROM sales_fact_v2 s
        JOIN fact_sales_workbook_anchor a
          ON a.order_id=s.order_id AND a.store_code=s.store_code
        """
    )
    conn.commit()
    anchor = dict(conn.execute("SELECT * FROM fact_sales_workbook_anchor").fetchone())
    terminal = _terminal_resolution(
        _load_lifecycle_evidence(conn, {("ORDER-1", "ACMEWEAR")})[
            ("ORDER-1", "ACMEWEAR")
        ]
    )
    conn.close()

    packet = tmp_path / "packet.csv"
    fields = [
        "order_id",
        "store_code",
        "source_formula_proven",
        "selected_sale_dates",
        "source_dates",
        "anchor_present",
        "anchor_row_sha256",
        "terminal_date_status",
        "terminal_date",
        "terminal_rank",
        "terminal_direct",
        "terminal_date_semantics",
        "terminal_activation_eligible",
        "terminal_evidence_count",
        "terminal_evidence_sha256",
        "terminal_all_positive_evidence_count",
        "terminal_all_positive_evidence_sha256",
        "terminal_later_positive_evidence_count",
        "terminal_later_positive_evidence_sha256",
        "terminal_negative_evidence_count",
        "terminal_negative_evidence_sha256",
        "canonical_hash_version",
        "negative_after_or_on_terminal",
        "next_action",
    ]
    with packet.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "order_id": "ORDER-1",
                "store_code": "ACMEWEAR",
                "source_formula_proven": True,
                "selected_sale_dates": "2026-03-01",
                "source_dates": "2026-03-01",
                "anchor_present": True,
                "anchor_row_sha256": _canonical_sha(anchor),
                "terminal_date_status": terminal["status"],
                "terminal_date": terminal["canonical_date"],
                "terminal_rank": terminal["rank"],
                "terminal_direct": True,
                "terminal_date_semantics": terminal["date_semantics"],
                "terminal_activation_eligible": terminal[
                    "activation_eligible"
                ],
                "terminal_evidence_count": len(terminal["evidence"]),
                "terminal_evidence_sha256": _canonical_sha(terminal["evidence"]),
                "terminal_all_positive_evidence_count": len(
                    terminal["all_positive_evidence"]
                ),
                "terminal_all_positive_evidence_sha256": _canonical_sha(
                    terminal["all_positive_evidence"]
                ),
                "terminal_later_positive_evidence_count": len(
                    terminal["later_positive_evidence"]
                ),
                "terminal_later_positive_evidence_sha256": _canonical_sha(
                    terminal["later_positive_evidence"]
                ),
                "terminal_negative_evidence_count": len(
                    terminal["negative_evidence"]
                ),
                "terminal_negative_evidence_sha256": _canonical_sha(
                    terminal["negative_evidence"]
                ),
                "canonical_hash_version": CANONICAL_HASH_VERSION,
                "negative_after_or_on_terminal": False,
                "next_action": (
                    "RECOMPUTE_SOURCE_FORMULA_AT_"
                    "TERMINAL_OBSERVATION_CANDIDATE_DATE"
                ),
            }
        )
    return db, packet


def _write_crm_provenance_fixture(
    tmp_path: Path, db: Path
) -> tuple[Path, Path, Path]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    source = dict(conn.execute("SELECT * FROM sales_fact_v2").fetchone())
    conn.close()
    workbook = tmp_path / "source.xlsx"
    workbook.write_bytes(b"pinned CRM fixture")
    proof = {
        "proof_key": "1" * 64,
        "source_kind": "CRM_XLSX_PHYSICAL_ROW",
        "source_workbook_path": str(workbook.resolve()),
        "source_workbook_sha256": _sha256(workbook),
        "source_sheet": "SALES_KSP_CRM_1",
        "source_physical_row": 42,
        "source_formula_row_sha256": "2" * 64,
        "source_allowlisted_row_sha256": "3" * 64,
        "source_allowlisted_fields": {},
        "order_id": source["order_id"],
        "store_code": source["store_code"],
        "sale_id": source["sale_id"],
        "order_date": source["order_date"],
        "sku_key": source["sku_key"],
        "sku_id": source["sku_id"],
        "size": source["my_size"],
        "quantity": str(source["quantity"]),
        "unit_sell_price_kzt": str(source["sell_price_kzt"]),
        "seller_delivery_fee_total_kzt": str(source["delivery_fee"]),
        "canonical_line_net_rev_kzt": str(source["net_rev"]),
        "repair_required": True,
        "evidence_status": "SOURCE_PROVEN_REPAIR_CANDIDATE",
        "db_row": source,
        "db_row_sha256": _canonical_sha(source),
    }
    proof_path = tmp_path / "proof.jsonl"
    proof_path.write_text(json.dumps(proof, sort_keys=True) + "\n", encoding="utf-8")
    pre_sha = "4" * 64
    manifest = {
        "schema": "sales_formula_provenance_crm_v4",
        "db_sha256": pre_sha,
        "proof_path": str(proof_path.resolve()),
        "proof_sha256": _sha256(proof_path),
        "proof_count": 1,
        "workbook_path": str(workbook.resolve()),
        "workbook_sha256": _sha256(workbook),
        "workbook_sheet": "SALES_KSP_CRM_1",
    }
    manifest["manifest_sha256"] = _canonical_sha(manifest)
    manifest_path = tmp_path / "provenance_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    db_sha = _sha256(db)
    apply_report = {
        "status": "PASS",
        "mode": "APPLY",
        "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": manifest["manifest_sha256"],
        "db_pre_sha256": pre_sha,
        "db_post_sha256": db_sha,
        "table_counts_unchanged": True,
        "target_readback_mismatch_count": 0,
        "non_target_sales_fact_v2_sha256_before": "5" * 64,
        "non_target_sales_fact_v2_sha256_after": "5" * 64,
        "target_count": 1,
    }
    apply_path = tmp_path / "apply_report.json"
    apply_path.write_text(json.dumps(apply_report), encoding="utf-8")
    return proof_path, manifest_path, apply_path


def test_builds_read_only_terminal_observation_candidate_manifest(
    tmp_path: Path,
) -> None:
    db, packet = _seed(tmp_path)
    before = _sha256(db)
    output = tmp_path / "manifest.json"
    result = build_manifest(
        db_path=db,
        packet_csv=packet,
        output_path=output,
        expected_db_sha256=before,
        expected_packet_sha256=_sha256(packet),
        expected_target_count=1,
        expected_eligible_count=1,
        expected_cross_month_transition_count=0,
    )

    assert _sha256(db) == before
    assert result["db_sha256_before"] == result["db_sha256_after"] == before
    assert result["target_count"] == result["eligible_count"] == 1
    assert result["exclusion_count"] == 0
    assert result["schema"] == (
        "terminal_observation_publication_candidate_manifest_v2"
    )
    assert result["operation"] == (
        "CANDIDATE_ONLY_INSERT_PUBLICATION_BINDING_HEADER_AND_LINES"
    )
    assert result["source_rows_immutable"] is True
    target = result["targets"][0]
    assert "old_row" not in target
    assert "new_row" not in target
    line = target["binding_line_candidates"][0]
    assert line["source_row_preimage"]["order_date"] == "2026-03-01"
    assert line["source_original_date"] == "2026-03-01"
    assert line["candidate_publication_date"] == "2026-03-03"
    assert line["candidate_units"] == "1"
    assert line["source_entry_id"] == "ENTRY-1"
    assert line["line_identity_key"] == "LINE-1"
    header = target["binding_header_candidate"]
    assert header["candidate_publication_date"] == "2026-03-03"
    assert header["provisional_flag"] is True
    assert header["activation_eligible"] is False
    assert header["activation_blocker"] == (
        "TERMINAL_EFFECTIVE_DATE_POLICY_UNRESOLVED"
    )
    assert header["originating_manifest_payload_sha256"] == result[
        "binding_payload_sha256"
    ]
    assert target["formula"]["candidate_minus_source_net_rev_kzt"] == "0.0"
    assert target["terminal_evidence"]["activation_eligible"] is False
    assert result["cross_month_transition_count"] == 0
    assert result["candidate_transition_only"] is True
    assert result["activation_eligible_count"] == 0
    assert result["activation_blocked_count"] == 1
    assert json.loads(output.read_text())["manifest_sha256"] == result["manifest_sha256"]


def test_rejects_anchor_preimage_drift(tmp_path: Path) -> None:
    db, packet = _seed(tmp_path)
    rows = list(csv.DictReader(packet.open(encoding="utf-8")))
    rows[0]["anchor_row_sha256"] = "b" * 64
    with packet.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ManifestError, match="eligible count changed"):
        build_manifest(
            db_path=db,
            packet_csv=packet,
            output_path=tmp_path / "manifest.json",
            expected_target_count=1,
            expected_eligible_count=1,
        )


def test_rejects_multiple_selected_source_lines(tmp_path: Path) -> None:
    db, packet = _seed(tmp_path)
    conn = sqlite3.connect(db)
    conn.execute("DROP VIEW view_sales_line_truth")
    conn.execute(
        """
        INSERT INTO sales_fact_v2
        SELECT 2, order_id, order_date, 'SKU_B', 'SKU_B_L', 'L', kaspi_offer_name,
               store_code, quantity, sell_price_kzt, delivery_fee, cogs, net_rev,
               profit, status, return_flag, return_date, ingested_at, source_file,
               api_updated_at, 'ENTRY-2', 'ARTICLE-2', 'LINE-2'
        FROM sales_fact_v2 WHERE sale_id=1
        """
    )
    conn.execute(
        """
        CREATE VIEW view_sales_line_truth AS
        SELECT s.order_id, a.sale_date, s.store_code, s.sku_key, s.sku_id,
               s.my_size, s.quantity AS units, s.net_rev AS net_rev_kzt,
               'sales_fact_v2' AS source_table, s.sku_key AS source_sku_key,
               s.sku_id AS source_sku_id, s.quantity AS source_units,
               s.net_rev AS source_net_rev_kzt
        FROM sales_fact_v2 s
        JOIN fact_sales_workbook_anchor a
          ON a.order_id=s.order_id AND a.store_code=s.store_code
        """
    )
    conn.commit()
    conn.close()

    with pytest.raises(ManifestError, match="eligible count changed"):
        build_manifest(
            db_path=db,
            packet_csv=packet,
            output_path=tmp_path / "manifest.json",
            expected_target_count=1,
            expected_eligible_count=1,
        )


def test_accepts_pinned_crm_physical_row_when_api_line_ids_are_absent(
    tmp_path: Path,
) -> None:
    db, packet = _seed(tmp_path)
    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE sales_fact_v2 SET source_entry_id=NULL, line_identity_key=NULL"
    )
    conn.commit()
    conn.close()
    proof, manifest, apply_report = _write_crm_provenance_fixture(tmp_path, db)

    result = build_manifest(
        db_path=db,
        packet_csv=packet,
        output_path=tmp_path / "binding_manifest.json",
        source_provenance_jsonl=proof,
        source_provenance_manifest=manifest,
        source_provenance_apply_report=apply_report,
        expected_db_sha256=_sha256(db),
        expected_target_count=1,
        expected_eligible_count=1,
    )

    identity = result["targets"][0]["binding_line_candidates"][0][
        "immutable_source_identity"
    ]
    assert identity["kind"] == "CRM_XLSX_PHYSICAL_ROW"
    assert identity["source_physical_row"] == 42
    assert result["source_rows_immutable"] is True


def test_manifest_is_deterministic_except_generated_at(tmp_path: Path) -> None:
    db, packet = _seed(tmp_path)
    first = build_manifest(
        db_path=db,
        packet_csv=packet,
        output_path=tmp_path / "first.json",
        expected_target_count=1,
        expected_eligible_count=1,
    )
    second = build_manifest(
        db_path=db,
        packet_csv=packet,
        output_path=tmp_path / "second.json",
        expected_target_count=1,
        expected_eligible_count=1,
    )
    assert first["manifest_sha256"] == second["manifest_sha256"]
    assert first["binding_payload_sha256"] == second["binding_payload_sha256"]
    assert first["target_key_sha256"] == second["target_key_sha256"]
    assert first["targets"] == second["targets"]


def test_manifest_quarantines_later_negative_lifecycle_evidence(
    tmp_path: Path,
) -> None:
    db, packet = _seed(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            "INSERT INTO fact_order_status_observations VALUES "
            "(2, 'ORDER-1', 'ACMEWEAR', 'CANCELLED', 'API', "
            "'2026-03-04T12:00:00Z')"
        )
        terminal = _terminal_resolution(
            _load_lifecycle_evidence(conn, {("ORDER-1", "ACMEWEAR")})[
                ("ORDER-1", "ACMEWEAR")
            ]
        )
    rows = list(csv.DictReader(packet.open(encoding="utf-8")))
    row = rows[0]
    row.update(
        {
            "terminal_date_status": terminal["status"],
            "terminal_date": terminal["canonical_date"],
            "terminal_rank": terminal["rank"],
            "terminal_direct": terminal["direct"],
            "terminal_date_semantics": terminal["date_semantics"],
            "terminal_activation_eligible": terminal["activation_eligible"],
            "terminal_evidence_count": len(terminal["evidence"]),
            "terminal_evidence_sha256": _canonical_sha(terminal["evidence"]),
            "terminal_all_positive_evidence_count": len(
                terminal["all_positive_evidence"]
            ),
            "terminal_all_positive_evidence_sha256": _canonical_sha(
                terminal["all_positive_evidence"]
            ),
            "terminal_later_positive_evidence_count": len(
                terminal["later_positive_evidence"]
            ),
            "terminal_later_positive_evidence_sha256": _canonical_sha(
                terminal["later_positive_evidence"]
            ),
            "terminal_negative_evidence_count": len(
                terminal["negative_evidence"]
            ),
            "terminal_negative_evidence_sha256": _canonical_sha(
                terminal["negative_evidence"]
            ),
            "negative_after_or_on_terminal": terminal[
                "negative_after_or_on_terminal"
            ],
        }
    )
    with packet.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)

    result = build_manifest(
        db_path=db,
        packet_csv=packet,
        output_path=tmp_path / "negative.json",
        expected_target_count=1,
        expected_eligible_count=0,
    )
    assert result["eligible_count"] == 0
    assert result["exclusion_count"] == 1
    assert "not a direct observation-date candidate" in result["exclusions"][0][
        "reason"
    ]
