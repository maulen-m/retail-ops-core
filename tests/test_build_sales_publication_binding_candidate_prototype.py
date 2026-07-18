from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

import scripts.build_sales_publication_binding_candidate_prototype as prototype_module
from scripts.build_sales_publication_binding_candidate_prototype import (
    ENV_GATE,
    PrototypeError,
    _canonical_sha,
    build_prototype,
)
from scripts.build_publication_anchor_reconciliation_packet import (
    _load_lifecycle_evidence,
    _terminal_resolution,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed(tmp_path: Path) -> tuple[Path, Path]:
    db = tmp_path / "source.db"
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        conn.executescript(
            """
            CREATE TABLE sales_fact_v2 (
                sale_id INTEGER PRIMARY KEY, order_id TEXT NOT NULL,
                order_date DATE NOT NULL, sku_key TEXT NOT NULL,
                sku_id TEXT NOT NULL, my_size TEXT NOT NULL,
                kaspi_offer_name TEXT NOT NULL, store_code TEXT,
                quantity INTEGER NOT NULL, sell_price_kzt REAL,
                delivery_fee REAL, cogs REAL, net_rev REAL, profit REAL,
                status TEXT, return_flag INTEGER, return_date DATE,
                ingested_at DATETIME, source_file TEXT,
                api_updated_at DATETIME, source_entry_id TEXT,
                kaspi_article TEXT, line_identity_key TEXT
            );
            CREATE TABLE fact_sales_workbook_anchor (
                order_id TEXT NOT NULL, store_code TEXT NOT NULL,
                sale_date TEXT NOT NULL, quantity REAL NOT NULL,
                net_rev_kzt REAL NOT NULL, total_price_kzt REAL NOT NULL,
                source_file TEXT, updated_at TEXT,
                PRIMARY KEY(order_id, store_code)
            );
            CREATE TABLE fact_order_status_observations (
                id INTEGER PRIMARY KEY, order_id TEXT NOT NULL,
                store_code TEXT NOT NULL, status_internal TEXT NOT NULL,
                source TEXT NOT NULL, observed_at TEXT NOT NULL
            );
            """
        )
        # SQLite renders this value as ``2828.88`` when cast to text. Keeping
        # the longer JSON representation closes the real formatting-drift
        # regression encountered by order 839916277.
        net_rev = 2828.8799999999997
        conn.execute(
            """
            INSERT INTO sales_fact_v2 VALUES (
                1, 'ORDER-1', '2026-03-01', 'SKU_A', 'SKU_A_M', 'M',
                'Offer A', 'ACMEWEAR', 1, 9000, 500, NULL, ?, NULL,
                'DELIVERED', 0, NULL, '2026-03-01T00:00:00Z',
                'source.csv', '2026-03-01T00:00:00Z', 'ENTRY-1',
                'ARTICLE-1', 'LINE-1'
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
            SELECT s.order_id, a.sale_date, s.store_code, s.sku_key,
                   s.sku_id, s.my_size, a.quantity AS units,
                   a.net_rev_kzt, NULL AS cogs_kzt, NULL AS profit_kzt,
                   'NONE' AS cogs_source, 'sales_fact_v2' AS source_table,
                   s.sku_key AS source_sku_key,
                   s.sku_id AS source_sku_id,
                   s.quantity AS source_units,
                   s.net_rev AS source_net_rev_kzt,
                   s.cogs AS source_cogs_kzt,
                   s.profit AS source_profit_kzt
            FROM sales_fact_v2 s
            JOIN fact_sales_workbook_anchor a
              ON a.order_id=s.order_id AND a.store_code=s.store_code
            """
        )
        anchor = dict(
            conn.execute("SELECT * FROM fact_sales_workbook_anchor").fetchone()
        )
        source = dict(conn.execute("SELECT * FROM sales_fact_v2").fetchone())
        selected = dict(conn.execute("SELECT * FROM view_sales_line_truth").fetchone())
        terminal = _terminal_resolution(
            _load_lifecycle_evidence(conn, {("ORDER-1", "ACMEWEAR")})[
                ("ORDER-1", "ACMEWEAR")
            ]
        )
    source_row = {key: source[key] for key in source}
    selected_row = {
        key: selected[key]
        for key in (
            "source_table",
            "source_sku_key",
            "source_sku_id",
            "my_size",
            "source_units",
            "source_net_rev_kzt",
            "sale_date",
            "units",
            "net_rev_kzt",
        )
    }
    identity = {
        "kind": "API_ENTRY_AND_LINE_IDENTITY",
        "source_entry_id": "ENTRY-1",
        "line_identity_key": "LINE-1",
    }
    line = {
        "line_ordinal": 1,
        "source_table": "sales_fact_v2",
        "source_physical_row_id": {"column": "sale_id", "value": 1},
        "source_entry_id": "ENTRY-1",
        "line_identity_key": "LINE-1",
        "immutable_source_identity": identity,
        "immutable_source_identity_sha256": _canonical_sha(identity),
        "source_row_preimage": source_row,
        "source_row_sha256": _canonical_sha(source_row),
        "source_original_date": "2026-03-01",
        "candidate_publication_date": "2026-03-03",
        "candidate_units": "1",
        "candidate_net_rev_kzt": str(source["net_rev"]),
        "stored_source_net_rev_kzt": str(source["net_rev"]),
        "canonical_source_date_net_rev_kzt": str(source["net_rev"]),
    }
    header = {
        "activation_blocker": "TERMINAL_EFFECTIVE_DATE_POLICY_UNRESOLVED",
        "activation_eligible": False,
        "binding_status": "CANDIDATE_VALIDATED_UNAPPLIED",
        "binding_version": "publication-binding-candidate-v2",
        "candidate_publication_date": "2026-03-03",
        "canonical_hash_version": "canonical-json-v1-sort-keys-utf8-no-whitespace",
        "copied_db_sha256": _sha256(db),
        "order_id": "ORDER-1",
        "originating_manifest_payload_sha256": "a" * 64,
        "policy_sha256": "b" * 64,
        "provisional_flag": True,
        "reason": "RECOMPUTE_SOURCE_FORMULA_AT_TERMINAL_OBSERVATION_CANDIDATE_DATE",
        "selected_source_line_multiset_sha256": _canonical_sha([selected_row]),
        "source_line_multiset_sha256": "c" * 64,
        "store_code": "ACMEWEAR",
        "terminal_all_positive_evidence_sha256": _canonical_sha(
            terminal["all_positive_evidence"]
        ),
        "terminal_date_semantics": "TERMINAL_OBSERVATION_DATE_CANDIDATE",
        "terminal_evidence_sha256": _canonical_sha(terminal["evidence"]),
        "terminal_later_positive_evidence_sha256": _canonical_sha(
            terminal["later_positive_evidence"]
        ),
        "terminal_negative_evidence_sha256": _canonical_sha(
            terminal["negative_evidence"]
        ),
        "terminal_rank": terminal["rank"],
        "workbook_anchor_sha256": _canonical_sha(anchor),
    }
    target = {
        "target_key": {"order_id": "ORDER-1", "store_code": "ACMEWEAR"},
        "operation": "CANDIDATE_ONLY_INSERT_PUBLICATION_BINDING_HEADER_AND_LINES",
        "source_rows_immutable": True,
        "workbook_anchor_preimage": anchor,
        "workbook_anchor_sha256": _canonical_sha(anchor),
        "selected_source_line_preimages": [selected_row],
        "selected_source_line_multiset_sha256": _canonical_sha([selected_row]),
        "terminal_evidence": {
            "activation_blocker": "TERMINAL_EFFECTIVE_DATE_POLICY_UNRESOLVED",
            "activation_eligible": False,
            "candidate_date": "2026-03-03",
            "date_semantics": "TERMINAL_OBSERVATION_DATE_CANDIDATE",
        },
        "binding_header_candidate": header,
        "binding_line_candidates": [line],
    }
    manifest = {
        "schema": "terminal_observation_publication_candidate_manifest_v2",
        "generated_at": "2026-07-16T00:00:00Z",
        "production_write_authorized": False,
        "writer_or_apply_path_exists": False,
        "db_sha256_before": _sha256(db),
        "binding_payload_sha256": "a" * 64,
        "policy_sha256": "b" * 64,
        "target_key_sha256": _canonical_sha([["ORDER-1", "ACMEWEAR"]]),
        "activation_eligible_count": 0,
        "activation_blocked_count": 1,
        "targets": [target],
    }
    manifest["manifest_sha256"] = _canonical_sha(
        {key: value for key, value in manifest.items() if key != "generated_at"}
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return db, manifest_path


def test_dry_run_creates_no_output(tmp_path: Path) -> None:
    source, manifest = _seed(tmp_path)
    output = tmp_path / "prototype.db"
    report = build_prototype(
        source_db=source,
        manifest_path=manifest,
        output_db=output,
        report_path=None,
        apply=False,
        expected_target_count=1,
    )
    assert report["mode"] == "DRY_RUN"
    assert report["write_applied"] is False
    assert not output.exists()


def test_apply_requires_explicit_local_copy_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, manifest = _seed(tmp_path)
    monkeypatch.delenv(ENV_GATE, raising=False)
    with pytest.raises(PrototypeError, match=ENV_GATE):
        build_prototype(
            source_db=source,
            manifest_path=manifest,
            output_db=tmp_path / "prototype.db",
            report_path=None,
            apply=True,
            expected_target_count=1,
        )


def test_apply_loads_only_inactive_candidates_and_preserves_truth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, manifest = _seed(tmp_path)
    before = _sha256(source)
    output = tmp_path / "prototype.db"
    report_path = tmp_path / "report.json"
    monkeypatch.setenv(ENV_GATE, "1")
    report = build_prototype(
        source_db=source,
        manifest_path=manifest,
        output_db=output,
        report_path=report_path,
        apply=True,
        expected_target_count=1,
    )
    assert _sha256(source) == before
    assert report["write_applied"] is True
    assert report["source_truth_hashes_before"] == report["source_truth_hashes_after"]
    assert report["readback"]["effective_status_counts"] == {"CANDIDATE": 1}
    assert report["readback"]["publication_binding_usable_count"] == 0
    assert report["readback"]["active_count"] == 0
    assert report_path.is_file()
    with sqlite3.connect(output) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE fact_sales_publication_binding_candidate_header "
                "SET active_flag=1"
            )


def test_source_or_anchor_drift_becomes_invalid_without_row_disappearance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, manifest = _seed(tmp_path)
    output = tmp_path / "prototype.db"
    monkeypatch.setenv(ENV_GATE, "1")
    build_prototype(
        source_db=source,
        manifest_path=manifest,
        output_db=output,
        report_path=None,
        apply=True,
        expected_target_count=1,
    )
    with sqlite3.connect(output) as conn:
        before = conn.execute("SELECT COUNT(*) FROM view_sales_line_truth").fetchone()[0]
        conn.execute("UPDATE sales_fact_v2 SET my_size='L' WHERE sale_id=1")
        conn.commit()
        row = conn.execute(
            "SELECT effective_status, publication_binding_usable FROM "
            "view_sales_publication_binding_candidate_validation"
        ).fetchone()
        after = conn.execute("SELECT COUNT(*) FROM view_sales_line_truth").fetchone()[0]
        assert row == ("INVALID", 0)
        assert before == after == 1

        conn.execute("UPDATE sales_fact_v2 SET my_size='M' WHERE sale_id=1")
        conn.execute(
            "UPDATE fact_sales_workbook_anchor SET quantity=2 "
            "WHERE order_id='ORDER-1' AND store_code='ACMEWEAR'"
        )
        conn.commit()
        row = conn.execute(
            "SELECT effective_status, publication_binding_usable FROM "
            "view_sales_publication_binding_candidate_validation"
        ).fetchone()
        after = conn.execute("SELECT COUNT(*) FROM view_sales_line_truth").fetchone()[0]
        assert row == ("INVALID", 0)
        assert before == after == 1


def test_refuses_existing_output_and_canonical_source_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, manifest = _seed(tmp_path)
    output = tmp_path / "prototype.db"
    output.write_bytes(b"must not be replaced")
    with pytest.raises(PrototypeError, match="already exists"):
        build_prototype(
            source_db=source,
            manifest_path=manifest,
            output_db=output,
            report_path=None,
            apply=False,
            expected_target_count=1,
        )
    assert output.read_bytes() == b"must not be replaced"

    monkeypatch.setattr(prototype_module, "CANONICAL_DB_PATH", source.resolve())
    with pytest.raises(PrototypeError, match="canonical production"):
        build_prototype(
            source_db=source,
            manifest_path=manifest,
            output_db=tmp_path / "other.db",
            report_path=None,
            apply=False,
            expected_target_count=1,
        )


def test_rejects_activation_eligible_manifest(tmp_path: Path) -> None:
    source, manifest_path = _seed(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    manifest["activation_eligible_count"] = 1
    manifest["manifest_sha256"] = _canonical_sha(
        {
            key: value
            for key, value in manifest.items()
            if key not in {"generated_at", "manifest_sha256"}
        }
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(PrototypeError, match="activation-eligible"):
        build_prototype(
            source_db=source,
            manifest_path=manifest_path,
            output_db=tmp_path / "prototype.db",
            report_path=None,
            apply=False,
            expected_target_count=1,
        )


@pytest.mark.parametrize("collision", ["source", "manifest", "output", "canonical"])
def test_refuses_report_path_collision_with_protected_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    collision: str,
) -> None:
    source, manifest = _seed(tmp_path)
    output = tmp_path / "prototype.db"
    canonical = tmp_path / "canonical.db"
    canonical.write_bytes(b"canonical sentinel")
    monkeypatch.setattr(prototype_module, "CANONICAL_DB_PATH", canonical.resolve())
    paths = {
        "source": source,
        "manifest": manifest,
        "output": output,
        "canonical": canonical,
    }
    before = {
        path: path.read_bytes() for path in paths.values() if path.exists()
    }

    with pytest.raises(PrototypeError, match="report path collides"):
        build_prototype(
            source_db=source,
            manifest_path=manifest,
            output_db=output,
            report_path=paths[collision],
            apply=False,
            expected_target_count=1,
        )

    assert not output.exists()
    for path, content in before.items():
        assert path.read_bytes() == content


def test_refuses_existing_report_hardlink_to_source(tmp_path: Path) -> None:
    source, manifest = _seed(tmp_path)
    report = tmp_path / "source-report-hardlink"
    report.hardlink_to(source)

    with pytest.raises(PrototypeError, match="report path aliases"):
        build_prototype(
            source_db=source,
            manifest_path=manifest,
            output_db=tmp_path / "prototype.db",
            report_path=report,
            apply=False,
            expected_target_count=1,
        )
