from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from scripts.materialize_merchant_cabinet_offer_availability import materialize

AGENT9141_STOCK_SOURCE = Path(
    "~/Docs/Autonomous_business_agent_handoffs/"
    "2026-05-19_mvos_agent914_readonly_source_acquisition_wave/"
    "agent9141_stock_live_readonly_source_acquisition_evidence/parsed/"
    "STOCK_SOURCE_NORMALIZED_ROWS.tsv"
)
AGENT9141_STOCK_SOURCE_SHA256 = (
    "283ee1c0b362509dd1c556a9c4671eb661672b29e895ca6bb574855fc7f579e2"
)


def _seed_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE offer_availability_snapshot (
            snapshot_id TEXT PRIMARY KEY,
            snapshot_date TEXT NOT NULL,
            store_code TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT NOT NULL,
            offer_available_qty INTEGER,
            physical_stock_qty INTEGER,
            status TEXT NOT NULL,
            source_manifest_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE fact_inventory_snapshot_size (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            my_size TEXT NOT NULL,
            current_stock INTEGER NOT NULL DEFAULT 0,
            inbound_stock INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE stock_ledger (
            ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_date TEXT NOT NULL,
            event_type TEXT NOT NULL,
            sku_key TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            my_size TEXT NOT NULL,
            qty_change INTEGER NOT NULL
        );
        CREATE TABLE exception_queue (
            exception_id TEXT PRIMARY KEY,
            run_id TEXT,
            domain TEXT,
            severity TEXT,
            status TEXT,
            reason TEXT
        );
        INSERT INTO fact_inventory_snapshot_size
            (snapshot_date, sku_id, sku_key, my_size, current_stock, inbound_stock)
            VALUES ('2026-05-04', 'CL_OC_MEN_LINE52_BLACK_L', 'CL_OC_MEN_LINE52_BLACK', 'L', 3, 0);
        INSERT INTO stock_ledger
            (event_date, event_type, sku_key, sku_id, my_size, qty_change)
            VALUES ('2026-05-04', 'COUNT', 'CL_OC_MEN_LINE52_BLACK', 'CL_OC_MEN_LINE52_BLACK_L', 'L', 3);
        INSERT INTO exception_queue
            (exception_id, domain, severity, status, reason)
            VALUES ('ex-1', 'STOCK', 'HIGH', 'OPEN', 'retained');
        """
    )
    conn.commit()
    conn.close()


def _write_source(path: Path) -> str:
    rows = [
        {
            "store_code": "STOREB",
            "sale_state": "ACTIVE",
            "source_file": "storeb_ACTIVE.xlsx",
            "source_file_sha256": "abc",
            "excel_row": "2",
            "sku": "CL_OC_MEN_LINE52_BLACK_L_116515378",
            "model": "Принт_5в1_черный_мужской_46-48_116515378_(Line52)_(L)",
            "brand": "pro-combat",
            "price": "9996",
            "pp1": "2",
            "pp2": "3",
            "pp3": "no",
            "pp4": "",
            "pp5": "0",
            "preorder": "99",
            "positive_on_hand_units_pp1_pp5": "5",
            "positive_preorder_units": "99",
        },
        {
            "store_code": "STOREB",
            "sale_state": "ARCHIVE",
            "source_file": "storeb_ARCHIVE.xlsx",
            "source_file_sha256": "def",
            "excel_row": "3",
            "sku": "CL_OC_MEN_LINE52_BLACK_XL_116515378",
            "model": "Принт_5в1_черный_мужской_50_116515378_(Line52)_(XL)",
            "brand": "pro-combat",
            "price": "9996",
            "pp1": "9",
            "pp2": "9",
            "pp3": "no",
            "pp4": "no",
            "pp5": "no",
            "preorder": "7",
            "positive_on_hand_units_pp1_pp5": "18",
            "positive_preorder_units": "7",
        },
        {
            "store_code": "ACMEWEAR",
            "sale_state": "ACTIVE",
            "source_file": "acmewear_ACTIVE.xlsx",
            "source_file_sha256": "jkl",
            "excel_row": "5",
            "sku": "SUIT-31-LS-ST-S-42",
            "model": "",
            "brand": "",
            "price": "9996",
            "pp1": "4",
            "pp2": "no",
            "pp3": "no",
            "pp4": "no",
            "pp5": "no",
            "preorder": "0",
            "positive_on_hand_units_pp1_pp5": "4",
            "positive_preorder_units": "0",
        },
        {
            "store_code": "ACMEWEAR",
            "sale_state": "ACTIVE",
            "source_file": "acmewear_ACTIVE.xlsx",
            "source_file_sha256": "mno",
            "excel_row": "6",
            "sku": "CL_OC_MEN_LINE51_WHITE_K-O_TRM_XL_1_159806992",
            "model": "Комплект_ACMEWEAR_LINE51_TRM_черный-белый",
            "brand": "",
            "price": "9996",
            "pp1": "4",
            "pp2": "no",
            "pp3": "no",
            "pp4": "no",
            "pp5": "no",
            "preorder": "0",
            "positive_on_hand_units_pp1_pp5": "4",
            "positive_preorder_units": "0",
        },
        {
            "store_code": "UNIVERSAL",
            "sale_state": "ARCHIVE",
            "source_file": "universal_ARCHIVE.xlsx",
            "source_file_sha256": "pqr",
            "excel_row": "7",
            "sku": "LOSINA BLACK XL 52",
            "model": "",
            "brand": "",
            "price": "9996",
            "pp1": "4",
            "pp2": "no",
            "pp3": "no",
            "pp4": "no",
            "pp5": "no",
            "preorder": "0",
            "positive_on_hand_units_pp1_pp5": "4",
            "positive_preorder_units": "0",
        },
        {
            "store_code": "ACMEWEAR",
            "sale_state": "ACTIVE",
            "source_file": "acmewear_ACTIVE.xlsx",
            "source_file_sha256": "ghi",
            "excel_row": "8",
            "sku": "UNPARSEABLE",
            "model": "unknown",
            "brand": "",
            "price": "",
            "pp1": "1",
            "pp2": "no",
            "pp3": "no",
            "pp4": "no",
            "pp5": "no",
            "preorder": "0",
            "positive_on_hand_units_pp1_pp5": "1",
            "positive_preorder_units": "0",
        },
    ]
    pd.DataFrame(rows).to_csv(path, sep="\t", index=False)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_dry_run_writes_manifest_without_db_mutation(tmp_path: Path) -> None:
    db = tmp_path / "agent9178_evidence" / "copied.db"
    source = tmp_path / "rows.tsv"
    _seed_db(db)
    source_sha = _write_source(source)

    manifest = materialize(
        db_path=db,
        source_normalized_rows=source,
        source_sha256=source_sha,
        snapshot_date="2026-05-19",
        source_manifest_id="test-manifest",
        output_dir=tmp_path / "out",
        apply=False,
    )

    conn = sqlite3.connect(str(db))
    try:
        assert conn.execute("SELECT COUNT(*) FROM offer_availability_snapshot").fetchone()[0] == 0
    finally:
        conn.close()
    assert manifest["parsed_identity_rows"] == 2
    assert manifest["unparsed_identity_rows"] == 4
    assert manifest["inserted_rows"] == 0


def test_apply_is_env_gated_and_writes_offer_availability_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "agent9178_evidence" / "copied.db"
    source = tmp_path / "rows.tsv"
    _seed_db(db)
    source_sha = _write_source(source)
    monkeypatch.setenv("ENABLE_MERCHANT_CABINET_OFFER_AVAILABILITY_WRITE", "1")

    manifest = materialize(
        db_path=db,
        source_normalized_rows=source,
        source_sha256=source_sha,
        snapshot_date="2026-05-19",
        source_manifest_id="test-manifest",
        output_dir=tmp_path / "out",
        apply=True,
    )

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM offer_availability_snapshot ORDER BY my_size").fetchall()
        assert len(rows) == 2
        assert {row["physical_stock_qty"] for row in rows} == {None}
        qty_by_size = {row["my_size"]: row["offer_available_qty"] for row in rows}
        assert qty_by_size["L"] == 5
        assert qty_by_size["XL"] == 0
        assert conn.execute("SELECT COUNT(*) FROM fact_inventory_snapshot_size").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM stock_ledger").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM exception_queue WHERE status='OPEN'").fetchone()[0] == 1
    finally:
        conn.close()

    assert manifest["inserted_rows"] == 2
    assert manifest["open_stock_high_exceptions_before"] == 1
    assert manifest["open_stock_high_exceptions_after"] == 1
    unparsed = pd.read_csv(
        tmp_path / "out" / "merchant_cabinet_offer_availability_unparsed_rows.tsv",
        sep="\t",
        dtype=str,
        keep_default_na=False,
    )
    reasons = set(unparsed["unparsed_reason"])
    assert "compact bundle alias requires separate owner/source contract" in reasons
    assert "size variant alias requires explicit identity mapping" in reasons
    assert "free-text losina alias requires separate owner/source contract" in reasons


def test_apply_refuses_without_env_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "agent9178_evidence" / "copied.db"
    source = tmp_path / "rows.tsv"
    _seed_db(db)
    source_sha = _write_source(source)
    monkeypatch.delenv("ENABLE_MERCHANT_CABINET_OFFER_AVAILABILITY_WRITE", raising=False)

    with pytest.raises(RuntimeError, match="ENABLE_MERCHANT_CABINET_OFFER_AVAILABILITY_WRITE=1"):
        materialize(
            db_path=db,
            source_normalized_rows=source,
            source_sha256=source_sha,
            snapshot_date="2026-05-19",
            source_manifest_id="test-manifest",
            output_dir=tmp_path / "out",
            apply=True,
        )


def test_current_agent9141_packet_counts_match_accepted_boundary(tmp_path: Path) -> None:
    if not AGENT9141_STOCK_SOURCE.exists():
        pytest.skip("Agent9141 stock source packet is not present in this environment")
    db = tmp_path / "agent9178_evidence" / "copied.db"
    _seed_db(db)

    manifest = materialize(
        db_path=db,
        source_normalized_rows=AGENT9141_STOCK_SOURCE,
        source_sha256=AGENT9141_STOCK_SOURCE_SHA256,
        snapshot_date="2026-05-19",
        source_manifest_id="agent9141-current-packet",
        output_dir=tmp_path / "out",
        apply=False,
    )

    assert manifest["source_rows"] == 1277
    assert manifest["parsed_identity_rows"] == 892
    assert manifest["unparsed_identity_rows"] == 385
    assert manifest["inserted_rows"] == 0
