from __future__ import annotations

import json
import hashlib
import sqlite3
from pathlib import Path

import pytest

from scripts.materialize_header_only_real_entry_reclassification import (
    WRITE_ENV_GATE,
    HeaderOnlyRealEntryReclassificationError,
    materialize_header_only_real_entry_reclassification,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _make_db(path: Path, *, offer_code: str = "CL_NEW-CLO_MEN_RUSH_WHITE_XL_135396192") -> None:
    raw_json = json.dumps(
        {
            "attributes": {
                "offer": {
                    "code": offer_code,
                    "name": "Rush white XL",
                }
            }
        },
        ensure_ascii=False,
    )
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE fact_order_entry_header_only_source_gap_quarantine (
                store_code TEXT NOT NULL,
                order_id TEXT NOT NULL,
                sale_id INTEGER,
                order_date TEXT,
                reason_code TEXT NOT NULL,
                header_sku_key TEXT,
                header_sku_id TEXT,
                header_my_size TEXT,
                header_kaspi_offer_name TEXT,
                header_quantity REAL,
                header_source_file TEXT,
                source_hierarchy_checked_json TEXT,
                publication_exclusion_required INTEGER NOT NULL DEFAULT 1,
                product_stock_excluded INTEGER NOT NULL DEFAULT 1,
                product_cogs_excluded INTEGER NOT NULL DEFAULT 1,
                product_profit_excluded INTEGER NOT NULL DEFAULT 1,
                sku_publication_excluded INTEGER NOT NULL DEFAULT 1,
                publication_exclusion_proof_json TEXT,
                owner_or_codecaptain_review_status TEXT,
                active_flag INTEGER NOT NULL DEFAULT 1,
                created_by TEXT,
                created_at TEXT,
                PRIMARY KEY (store_code, order_id)
            );
            CREATE TABLE fact_order_entries_kaspi (
                entry_id TEXT PRIMARY KEY,
                order_id TEXT,
                store_code TEXT,
                product_id TEXT,
                offer_id TEXT,
                quantity REAL,
                unit_price_kzt REAL,
                total_price_kzt REAL,
                raw_json TEXT
            );
            CREATE TABLE fact_cashflow_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date TEXT,
                event_type TEXT,
                account TEXT,
                amount_kzt REAL,
                store_code TEXT,
                sku_key TEXT,
                sku_id TEXT,
                ref_type TEXT,
                ref_id TEXT,
                source TEXT,
                event_hash TEXT
            );
            CREATE TABLE stock_ledger (
                ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date TEXT,
                event_type TEXT,
                sku_key TEXT,
                sku_id TEXT,
                my_size TEXT,
                store_code TEXT,
                qty_change INTEGER,
                reference_id TEXT,
                reference_type TEXT,
                idempotency_key TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO fact_order_entry_header_only_source_gap_quarantine (
                store_code, order_id, sale_id, order_date, reason_code,
                header_sku_key, header_sku_id, header_my_size,
                header_kaspi_offer_name, header_quantity, header_source_file,
                source_hierarchy_checked_json, publication_exclusion_required,
                product_stock_excluded, product_cogs_excluded,
                product_profit_excluded, sku_publication_excluded,
                publication_exclusion_proof_json, owner_or_codecaptain_review_status,
                active_flag, created_by, created_at
            ) VALUES (
                'STOREB', '906730647', 430844, '2026-05-03',
                'HEADER_ONLY_NO_REAL_ITEM_ENTRY_EVIDENCE',
                'CL_NEW-CLO_MEN_RUSH_WHITE', 'CL_NEW-CLO_MEN_RUSH_WHITE_XL',
                'XL', 'Header fallback', 1, 'KASPI_API_HEADER_FALLBACK_REBUILD',
                '{"real_item_entry_evidence_exists": false}',
                1, 1, 1, 1, 1, '{"old": true}', 'REVIEW_REQUIRED',
                1, 'old_agent', '2026-05-09T18:23:56+05:00'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO fact_order_entries_kaspi (
                entry_id, order_id, store_code, product_id, offer_id, quantity,
                unit_price_kzt, total_price_kzt, raw_json
            ) VALUES (
                'entry-1', '906730647', 'STOREB', 'product-1', '', 1, 0, 3000, ?
            )
            """,
            (raw_json,),
        )
        conn.execute(
            """
            INSERT INTO fact_cashflow_events (
                event_date, event_type, account, amount_kzt, store_code, sku_key,
                sku_id, ref_type, ref_id, source, event_hash
            ) VALUES (
                '2026-05-16', 'INVENTORY_RETURN', 'INVENTORY_ON_HAND_COST',
                959.71, 'STOREB', 'CL_NEW-CLO_MEN_RUSH_WHITE',
                'CL_NEW-CLO_MEN_RUSH_WHITE_XL', 'ORDER', '906730647',
                'ORDER_MODELLED', 'return-906730647'
            )
            """
        )


def _run(
    db_path: Path,
    output_root: Path,
    *,
    backup_dir: Path | None = None,
    apply: bool = False,
    expected_pre_sha256: str | None = None,
) -> dict:
    return materialize_header_only_real_entry_reclassification(
        db_path=db_path,
        output_root=output_root,
        backup_dir=backup_dir,
        store_code="STOREB",
        order_id="906730647",
        expected_active_header_only_count=1,
        expected_api_entry_count=1,
        expected_product_cashflow_reference_count=1,
        expected_stock_ledger_reference_count=0,
        expected_pre_sha256=expected_pre_sha256,
        apply=apply,
    )


def test_reclassification_dry_run_does_not_mutate(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)

    summary = _run(db_path, tmp_path / "dry")

    assert summary["apply"]["applied"] is False
    assert summary["before"]["active_header_only_count"] == 1
    assert summary["after"]["active_header_only_count"] == 1
    assert summary["before"]["api_entries_with_offer_matching_header_sku_id"] == 1
    assert summary["before"]["product_cashflow_reference_count"] == 1
    assert Path(summary["summary_json"]).exists()


def test_reclassification_apply_requires_env_gate(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)

    with pytest.raises(HeaderOnlyRealEntryReclassificationError, match=WRITE_ENV_GATE):
        _run(db_path, tmp_path / "blocked", backup_dir=tmp_path / "backups", apply=True)

    with sqlite3.connect(db_path) as conn:
        active = conn.execute(
            "SELECT active_flag FROM fact_order_entry_header_only_source_gap_quarantine"
        ).fetchone()[0]
    assert active == 1
    assert not (tmp_path / "backups").exists()


def test_reclassification_apply_deactivates_header_only_row_without_deleting_product_truth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)

    monkeypatch.setenv(WRITE_ENV_GATE, "1")
    summary = _run(
        db_path,
        tmp_path / "apply",
        backup_dir=tmp_path / "backups",
        apply=True,
        expected_pre_sha256=_sha256(db_path),
    )

    assert summary["apply"]["applied"] is True
    assert summary["apply"]["updated_rows"] == 1
    assert summary["after"]["active_header_only_count"] == 0
    assert summary["after"]["api_entry_count"] == 1
    assert summary["after"]["product_cashflow_reference_count"] == 1
    assert summary["product_cashflow_deleted"] == 0
    assert summary["stock_ledger_deleted"] == 0
    assert Path(summary["backup_path"]).exists()
    assert "source.backup(target)" in summary["rollback"]["restore_command"]

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT active_flag, publication_exclusion_required,
                   product_stock_excluded, product_cogs_excluded,
                   product_profit_excluded, sku_publication_excluded,
                   owner_or_codecaptain_review_status,
                   publication_exclusion_proof_json
            FROM fact_order_entry_header_only_source_gap_quarantine
            WHERE order_id='906730647'
            """
        ).fetchone()
        product_cashflow = conn.execute(
            "SELECT COUNT(*) FROM fact_cashflow_events WHERE ref_id='906730647'"
        ).fetchone()[0]
        entries = conn.execute(
            "SELECT COUNT(*) FROM fact_order_entries_kaspi WHERE order_id='906730647'"
        ).fetchone()[0]

    assert row[:6] == (0, 0, 0, 0, 0, 0)
    assert row[6] == "SUPERSEDED_BY_REAL_API_ENTRY_EVIDENCE"
    assert json.loads(row[7])["header_only_quarantine_active_after_apply"] is False
    assert product_cashflow == 1
    assert entries == 1


def test_reclassification_mismatched_offer_code_fails(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path, offer_code="CL_OTHER_SKU_XL_123")

    with pytest.raises(
        HeaderOnlyRealEntryReclassificationError,
        match="api_entries_with_offer_matching_header_sku_id mismatch",
    ):
        _run(db_path, tmp_path / "mismatch")


def test_reclassification_apply_requires_expected_pre_sha(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)

    monkeypatch.setenv(WRITE_ENV_GATE, "1")
    with pytest.raises(HeaderOnlyRealEntryReclassificationError, match="expected-pre-sha256"):
        _run(db_path, tmp_path / "missing_sha", backup_dir=tmp_path / "backups", apply=True)

    with pytest.raises(HeaderOnlyRealEntryReclassificationError, match="pre-write SHA mismatch"):
        _run(
            db_path,
            tmp_path / "bad_sha",
            backup_dir=tmp_path / "backups",
            apply=True,
            expected_pre_sha256="0" * 64,
        )


def test_reclassification_apply_refuses_sqlite_sidecars(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    Path(f"{db_path}-wal").write_text("sidecar", encoding="utf-8")

    monkeypatch.setenv(WRITE_ENV_GATE, "1")
    with pytest.raises(HeaderOnlyRealEntryReclassificationError, match="SQLite sidecars"):
        _run(
            db_path,
            tmp_path / "sidecar",
            backup_dir=tmp_path / "backups",
            apply=True,
            expected_pre_sha256=_sha256(db_path),
        )
