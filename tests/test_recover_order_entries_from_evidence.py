import json
import hashlib
import sqlite3
from pathlib import Path

import pytest

import scripts.recover_order_entries_from_evidence as recovery
from scripts.recover_order_entries_from_evidence import (
    EvidenceRow,
    SourceBundle,
    TargetRow,
    build_missing_fact_order_targets,
    assign_evidence_to_targets,
    build_missing_targets,
    dedupe_evidence_rows,
    evidence_to_entry,
    make_non_api_entry_id,
    recover_order_entries,
    redacted_workbook_raw_json,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _make_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE sales_fact_v2 (
                sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                order_date TEXT NOT NULL,
                sku_key TEXT NOT NULL DEFAULT '',
                sku_id TEXT NOT NULL DEFAULT '',
                my_size TEXT NOT NULL DEFAULT '',
                kaspi_offer_name TEXT NOT NULL DEFAULT '',
                store_code TEXT DEFAULT 'UNIVERSAL',
                quantity INTEGER NOT NULL DEFAULT 1,
                sell_price_kzt REAL,
                status TEXT DEFAULT 'DELIVERED',
                return_flag INTEGER DEFAULT 0
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
                raw_json TEXT,
                updated_at TEXT DEFAULT (datetime('now')),
                delivery_cost_kzt REAL,
                base_price_kzt REAL,
                entry_number INTEGER,
                category_code TEXT,
                category_title TEXT
            );
            CREATE TABLE fact_orders_kaspi (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                store_code TEXT NOT NULL,
                kaspi_offer_name TEXT,
                sku_key TEXT,
                sku_id TEXT,
                my_size TEXT,
                quantity INTEGER DEFAULT 1,
                unit_price_kzt REAL,
                created_at TEXT,
                kaspi_status TEXT,
                internal_status TEXT DEFAULT 'NEW',
                kaspi_status_detail TEXT
            );
            CREATE TABLE dim_kaspi_article_map (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_code TEXT NOT NULL,
                kaspi_article TEXT NOT NULL,
                sku_key TEXT,
                sku_id TEXT,
                active_flag INTEGER DEFAULT 1
            );
            """
        )


def _target(order_id: str = "O-1", store_code: str = "ACMEWEAR") -> TargetRow:
    return TargetRow(
        sale_id=1,
        order_id=order_id,
        store_code=store_code,
        order_date="2026-01-02",
        sku_key="SKU",
        sku_id="SKU_L",
        my_size="L",
        kaspi_offer_name="Offer",
        quantity=1,
        sell_price_kzt=1000.0,
    )


def _evidence(
    source_name: str,
    *,
    order_id: str = "O-1",
    store_code: str = "ACMEWEAR",
    source_kind: str = "workbook_row",
    entry_id: str = "",
    offer_id: str = "ARTICLE-1",
    sku_id: str | None = None,
    source_row_number: int = 2,
    business_date: str = "2026-01-02",
) -> EvidenceRow:
    return EvidenceRow(
        source_name=source_name,
        source_kind=source_kind,
        source_path=Path(f"/tmp/{source_name}.xlsx"),
        order_id=order_id,
        store_code=store_code,
        quantity=1.0,
        business_date=business_date,
        offer_id=offer_id,
        unit_price_kzt=1000.0,
        total_price_kzt=1000.0,
        entry_id=entry_id,
        sku_id=sku_id if sku_id is not None else ("SKU_L" if source_name == "CURRENT_CRM" else ""),
        sku_key="SKU" if (sku_id is None and source_name == "CURRENT_CRM") or sku_id else "",
        my_size="L" if (sku_id is None and source_name == "CURRENT_CRM") or sku_id else "",
        source_sheet="Sheet1",
        source_row_number=source_row_number,
        offer_name="Offer",
    )


def test_source_hierarchy_priority_prefers_current_crm() -> None:
    target = _target()
    assignments = assign_evidence_to_targets(
        [target],
        [
            SourceBundle("CURRENT_CRM", "HIGH", {target.pair: [_evidence("CURRENT_CRM")]}),
            SourceBundle(
                "API_RAW_ORDER_ENTRIES",
                "VERY_HIGH",
                {target.pair: [_evidence("API_RAW_ORDER_ENTRIES", source_kind="api_raw_order_entry", entry_id="api-1")]},
            ),
            SourceBundle("WEBUI_ARCHIVE_SOURCE_BACKUP", "HIGH", {target.pair: [_evidence("WEBUI_ARCHIVE_SOURCE_BACKUP")]}),
            SourceBundle("RESERVE_ARCHIVE_WORKBOOK", "MEDIUM", {target.pair: [_evidence("RESERVE_ARCHIVE_WORKBOOK")]}),
        ],
        article_map={},
    )

    assert assignments[target.pair].source_name == "CURRENT_CRM"
    assert assignments[target.pair].target_row_count == 1


def test_no_synthetic_entries_when_evidence_missing() -> None:
    target = _target()
    assignments = assign_evidence_to_targets(
        [target],
        [SourceBundle("CURRENT_CRM", "HIGH", {})],
        article_map={},
    )

    assert assignments[target.pair].source_name == "UNRECOVERED_QUARANTINE"
    assert assignments[target.pair].evidence_rows == []


def test_non_api_provenance_key_is_deterministic() -> None:
    row = _evidence("CURRENT_CRM")
    same = _evidence("CURRENT_CRM")
    changed = _evidence("CURRENT_CRM", source_row_number=3)

    assert make_non_api_entry_id(row) == make_non_api_entry_id(same)
    assert make_non_api_entry_id(row) == make_non_api_entry_id(changed)
    assert make_non_api_entry_id(row).startswith("RECOV-WORKBOOK-")


def test_workbook_lifecycle_snapshots_supersede_by_public_offer_grain() -> None:
    earlier = _evidence(
        "CURRENT_CRM", source_row_number=20, business_date="2026-01-02"
    )
    later = _evidence(
        "CURRENT_CRM", source_row_number=9, business_date="2026-01-03"
    )
    later = EvidenceRow(
        **{
            **later.__dict__,
            "sku_id": "SKU_XL",
            "my_size": "XL",
            "total_price_kzt": 1200.0,
        }
    )

    deduped = dedupe_evidence_rows([later, earlier])

    assert len(deduped) == 1
    assert deduped[0].source_row_number == 9
    assert deduped[0].sku_id == "SKU_XL"
    assert make_non_api_entry_id(earlier) == make_non_api_entry_id(later)


def test_workbook_entry_id_is_stable_across_source_names_and_paths() -> None:
    current = _evidence("CURRENT_CRM")
    reserve = _evidence("RESERVE_ARCHIVE_WORKBOOK")

    assert make_non_api_entry_id(current) == make_non_api_entry_id(reserve)


def test_workbook_same_rank_conflict_fails_closed() -> None:
    first = _evidence("CURRENT_CRM", source_row_number=5)
    conflict = EvidenceRow(
        **{
            **first.__dict__,
            "quantity": 2.0,
            "total_price_kzt": 2000.0,
        }
    )

    with pytest.raises(recovery.RecoveryError, match="irreconcilable workbook snapshots"):
        dedupe_evidence_rows([first, conflict])


def test_workbook_distinct_public_offers_remain_distinct_lines() -> None:
    first = _evidence("CURRENT_CRM", offer_id="ARTICLE-1")
    second = _evidence("CURRENT_CRM", offer_id="ARTICLE-2", source_row_number=3)

    deduped = dedupe_evidence_rows([first, second])

    assert [row.offer_id for row in deduped] == ["ARTICLE-1", "ARTICLE-2"]


def test_api_dedupe_uses_stable_entry_source_key() -> None:
    row = _evidence("API_RAW_ORDER_ENTRIES", source_kind="api_raw_order_entry", entry_id="entry-1")
    duplicate = _evidence("API_RAW_ORDER_ENTRIES", source_kind="api_raw_order_entry", entry_id="entry-1")
    other = _evidence(
        "API_RAW_ORDER_ENTRIES",
        source_kind="api_raw_order_entry",
        entry_id="entry-2",
        offer_id="ARTICLE-2",
    )

    deduped = dedupe_evidence_rows([row, duplicate, other])

    assert [item.entry_id for item in deduped] == ["entry-1", "entry-2"]


def test_api_distinct_entry_ids_preserve_same_offer_multiline_order() -> None:
    first = _evidence(
        "API_RAW_ORDER_ENTRIES",
        source_kind="api_raw_order_entry",
        entry_id="entry-1",
    )
    second = _evidence(
        "API_RAW_ORDER_ENTRIES",
        source_kind="api_raw_order_entry",
        entry_id="entry-2",
    )

    deduped = dedupe_evidence_rows([first, second])

    assert [item.entry_id for item in deduped] == ["entry-1", "entry-2"]


def test_api_same_entry_id_conflicting_payload_fails_closed() -> None:
    first = _evidence(
        "API_RAW_ORDER_ENTRIES",
        source_kind="api_raw_order_entry",
        entry_id="entry-1",
    )
    conflict = EvidenceRow(**{**first.__dict__, "quantity": 2.0})

    with pytest.raises(recovery.RecoveryError, match="immutable API entry_id"):
        dedupe_evidence_rows([first, conflict])


def test_workbook_raw_json_redacts_pii_fields() -> None:
    raw = redacted_workbook_raw_json(
        _evidence("CURRENT_CRM"),
        item_payload={
            "OrderID": "O-1",
            "Phone": "+77770000000",
            "Адрес самовывоза/доставки": "private address",
            "customer_phone": "should-not-survive",
            "SKU_ID": "SKU_L",
            "Артикул": "ARTICLE-1",
            "Quantity": 1,
        },
    )
    payload = json.loads(raw)
    text = json.dumps(payload, ensure_ascii=False).lower()

    assert "phone" not in text
    assert "address" not in text
    assert "адрес" not in text
    assert "+77770000000" not in text
    assert payload["item"]["SKU_ID"] == "SKU_L"


def test_temp_db_apply_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.sqlite"
    _make_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sales_fact_v2(order_id, order_date, store_code, sku_key, sku_id, my_size, quantity, status)
            VALUES ('O-1', '2026-01-02', 'ACMEWEAR', 'SKU', 'SKU_L', 'L', 1, 'DELIVERED')
            """
        )
    source = SourceBundle("CURRENT_CRM", "HIGH", {("O-1", "ACMEWEAR"): [_evidence("CURRENT_CRM")]})

    monkeypatch.setenv("ENABLE_ORDER_ENTRY_RECOVERY_WRITE", "1")
    applied = recover_order_entries(
        db_path=db_path,
        as_of="2026-01-03",
        output_root=tmp_path / "apply",
        source_bundles=[source],
        apply=True,
        strict=True,
    )
    post_apply = recover_order_entries(
        db_path=db_path,
        as_of="2026-01-03",
        output_root=tmp_path / "post_apply",
        source_bundles=[source],
        apply=False,
        strict=True,
    )

    assert applied["apply"]["inserted_entry_rows"] == 1
    assert post_apply["target"]["validator_rows"] == 0
    assert post_apply["apply"]["would_insert_entry_rows"] == 0


def test_recovery_ts_pins_inserted_entry_updated_at(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.sqlite"
    _make_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sales_fact_v2(order_id, order_date, store_code, sku_key, sku_id, my_size, quantity, status)
            VALUES ('O-1', '2026-01-02', 'ACMEWEAR', 'SKU', 'SKU_L', 'L', 1, 'DELIVERED')
            """
        )
    source = SourceBundle("CURRENT_CRM", "HIGH", {("O-1", "ACMEWEAR"): [_evidence("CURRENT_CRM")]})
    pinned_ts = "2026-05-04T23:59:59+05:00"

    monkeypatch.setenv("ENABLE_ORDER_ENTRY_RECOVERY_WRITE", "1")
    summary = recover_order_entries(
        db_path=db_path,
        as_of="2026-05-04",
        output_root=tmp_path / "apply",
        source_bundles=[source],
        recovery_ts=pinned_ts,
        apply=True,
        strict=True,
    )

    with sqlite3.connect(db_path) as conn:
        updated_at = conn.execute(
            "SELECT updated_at FROM fact_order_entries_kaspi WHERE order_id='O-1'"
        ).fetchone()[0]

    assert summary["recovery_ts"] == pinned_ts
    assert updated_at == pinned_ts


def test_explicit_recovery_ts_after_as_of_fails_closed(tmp_path: Path) -> None:
    db_path = tmp_path / "app.sqlite"
    _make_db(db_path)

    try:
        recover_order_entries(
            db_path=db_path,
            as_of="2026-05-04",
            output_root=tmp_path / "dry_run",
            source_bundles=[],
            recovery_ts="2026-05-05T00:00:00+05:00",
        )
    except recovery.RecoveryError as exc:
        assert "after as_of" in str(exc)
    else:
        raise AssertionError("post-as-of recovery_ts should fail closed")


def test_production_apply_summary_marks_production_modified(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sales_fact_v2(order_id, order_date, store_code, sku_key, sku_id, my_size, quantity, status)
            VALUES ('O-1', '2026-01-02', 'ACMEWEAR', 'SKU', 'SKU_L', 'L', 1, 'DELIVERED')
            """
        )
    source = SourceBundle("CURRENT_CRM", "HIGH", {("O-1", "ACMEWEAR"): [_evidence("CURRENT_CRM")]})

    monkeypatch.setattr(recovery, "DEFAULT_DB", db_path)
    monkeypatch.setenv("ENABLE_ORDER_ENTRY_RECOVERY_WRITE", "1")
    monkeypatch.setenv("ENABLE_ORDER_ENTRY_RECOVERY_PROD_WRITE", "1")

    applied = recover_order_entries(
        db_path=db_path,
        as_of="2026-01-03",
        output_root=tmp_path / "apply",
        source_bundles=[source],
        expected_pre_sha256=_sha256(db_path),
        backup_dir=tmp_path / "backups",
        apply=True,
        strict=True,
    )

    assert applied["apply"]["inserted_entry_rows"] == 1
    assert applied["apply"]["production_apply"] is True
    assert applied["production_db_modified"] is True
    assert Path(applied["backup_path"]).exists()
    assert applied["integrity_check"]["backup"] == "ok"
    assert len(applied["backup_sha256"]) == 64


def test_production_apply_requires_expected_sha_and_backup_dir(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sales_fact_v2(order_id, order_date, store_code, sku_key, sku_id, my_size, quantity, status)
            VALUES ('O-1', '2026-01-02', 'ACMEWEAR', 'SKU', 'SKU_L', 'L', 1, 'DELIVERED')
            """
        )
    source = SourceBundle("CURRENT_CRM", "HIGH", {("O-1", "ACMEWEAR"): [_evidence("CURRENT_CRM")]})

    monkeypatch.setattr(recovery, "DEFAULT_DB", db_path)
    monkeypatch.setenv("ENABLE_ORDER_ENTRY_RECOVERY_WRITE", "1")
    monkeypatch.setenv("ENABLE_ORDER_ENTRY_RECOVERY_PROD_WRITE", "1")

    try:
        recover_order_entries(
            db_path=db_path,
            as_of="2026-01-03",
            output_root=tmp_path / "missing_sha",
            source_bundles=[source],
            backup_dir=tmp_path / "backups",
            apply=True,
        )
    except recovery.RecoveryError as exc:
        assert "expected-pre-sha256" in str(exc)
    else:
        raise AssertionError("production apply should require expected SHA")

    try:
        recover_order_entries(
            db_path=db_path,
            as_of="2026-01-03",
            output_root=tmp_path / "missing_backup",
            source_bundles=[source],
            expected_pre_sha256=_sha256(db_path),
            apply=True,
        )
    except recovery.RecoveryError as exc:
        assert "backup-dir" in str(exc)
    else:
        raise AssertionError("production apply should require backup dir")


def test_validator_facing_dry_run_counts(tmp_path: Path) -> None:
    db_path = tmp_path / "app.sqlite"
    _make_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sales_fact_v2(order_id, order_date, store_code, sku_key, sku_id, my_size, quantity, status)
            VALUES ('O-1', '2026-01-02', 'ACMEWEAR', 'SKU', 'SKU_L', 'L', 1, 'DELIVERED')
            """
        )
        conn.execute(
            """
            INSERT INTO sales_fact_v2(order_id, order_date, store_code, sku_key, sku_id, my_size, quantity, status)
            VALUES ('O-2', '2026-01-02', 'ACMEWEAR', 'SKU', 'SKU_L', 'L', 1, 'OPEN')
            """
        )
        conn.execute(
            """
            INSERT INTO fact_order_entries_kaspi(entry_id, order_id, store_code, offer_id, quantity)
            VALUES ('existing', 'O-3', 'ACMEWEAR', 'ARTICLE-3', 1)
            """
        )
    targets = build_missing_targets(db_path, as_of="2026-01-03")
    source = SourceBundle("CURRENT_CRM", "HIGH", {("O-1", "ACMEWEAR"): [_evidence("CURRENT_CRM")]})

    summary = recover_order_entries(
        db_path=db_path,
        as_of="2026-01-03",
        output_root=tmp_path / "dry_run",
        source_bundles=[source],
        apply=False,
        strict=True,
    )

    assert [target.order_id for target in targets] == ["O-1"]
    assert summary["target"]["validator_rows"] == 1
    assert summary["target"]["order_store_pairs"] == 1
    assert summary["recovery_by_source"]["CURRENT_CRM"]["target_rows"] == 1
    assert summary["apply"]["would_insert_entry_rows"] == 1
    assert summary["apply"]["applied"] is False


def test_target_order_csv_filter_narrows_missing_scope(tmp_path: Path) -> None:
    db_path = tmp_path / "app.sqlite"
    target_csv = tmp_path / "target_orders.csv"
    _make_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO sales_fact_v2(order_id, order_date, store_code, sku_key, sku_id, my_size, quantity, status)
            VALUES (?, '2026-01-02', 'ACMEWEAR', 'SKU', 'SKU_L', 'L', 1, 'DELIVERED')
            """,
            [("O-1",), ("O-2",)],
        )
    target_csv.write_text(
        "order_id,store_code,order_date\nO-2,ACMEWEAR,2026-01-02\n",
        encoding="utf-8",
    )
    source = SourceBundle(
        "CURRENT_CRM",
        "HIGH",
        {("O-2", "ACMEWEAR"): [_evidence("CURRENT_CRM", order_id="O-2")]},
    )

    summary = recover_order_entries(
        db_path=db_path,
        as_of="2026-01-03",
        output_root=tmp_path / "dry_run",
        source_bundles=[source],
        target_order_csv=target_csv,
        apply=False,
        strict=True,
    )

    assert summary["target_filter"]["applied"] is True
    assert summary["target_filter"]["requested_order_store_pairs"] == 1
    assert summary["target"]["validator_rows"] == 1
    assert summary["recovery_by_source"]["CURRENT_CRM"]["target_rows"] == 1
    assert summary["quarantine"]["target_rows"] == 0


def test_target_order_csv_filter_rejects_unmatched_pairs(tmp_path: Path) -> None:
    db_path = tmp_path / "app.sqlite"
    target_csv = tmp_path / "target_orders.csv"
    _make_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sales_fact_v2(order_id, order_date, store_code, sku_key, sku_id, my_size, quantity, status)
            VALUES ('O-1', '2026-01-02', 'ACMEWEAR', 'SKU', 'SKU_L', 'L', 1, 'DELIVERED')
            """
        )
    target_csv.write_text(
        "order_id,store_code\nO-2,ACMEWEAR\n",
        encoding="utf-8",
    )

    try:
        recover_order_entries(
            db_path=db_path,
            as_of="2026-01-03",
            output_root=tmp_path / "dry_run",
            source_bundles=[],
            target_order_csv=target_csv,
        )
    except recovery.RecoveryError as exc:
        assert "not in the current missing target set" in str(exc)
    else:
        raise AssertionError("stale target-order CSV should fail closed")


def test_evidence_to_entry_keeps_recovered_entry_separate_from_sku_mapping() -> None:
    entry = evidence_to_entry(
        _evidence("API_RAW_ORDER_ENTRIES", source_kind="api_raw_order_entry", entry_id="api-entry", sku_id=""),
        recovery_ts="2026-05-04T10:00:00+05:00",
        article_mapped=False,
    )

    assert entry["entry_id"] == "api-entry"
    assert entry["offer_id"] == "ARTICLE-1"
    assert entry["sku_rebuild_mappable"] is False


def test_fact_orders_target_mode_uses_headers_not_sales_fact(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.sqlite"
    _make_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi(
                order_id, created_at, store_code, sku_key, sku_id, my_size, quantity,
                kaspi_status, internal_status, kaspi_status_detail
            )
            VALUES ('O-HEADER', '2026-05-05T10:00:00+05:00', 'ACMEWEAR', '', '', '', 1,
                    'ARCHIVE', 'COMPLETED', 'COMPLETED')
            """
        )

    source = SourceBundle(
        "API_RAW_ORDER_ENTRIES",
        "VERY_HIGH",
        {
            ("O-HEADER", "ACMEWEAR"): [
                _evidence(
                    "API_RAW_ORDER_ENTRIES",
                    order_id="O-HEADER",
                    source_kind="api_raw_order_entry",
                    entry_id="api-header-entry",
                    sku_id="",
                )
            ]
        },
    )

    monkeypatch.setenv("ENABLE_ORDER_ENTRY_RECOVERY_WRITE", "1")
    applied = recover_order_entries(
        db_path=db_path,
        as_of="2026-05-13",
        start_date="2026-05-05",
        target_source="fact_orders_kaspi",
        output_root=tmp_path / "apply",
        source_bundles=[source],
        recovery_ts="2026-05-13T23:59:59+05:00",
        apply=True,
        strict=True,
    )

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT entry_id, order_id, store_code FROM fact_order_entries_kaspi").fetchall()

    assert applied["target_source"] == "fact_orders_kaspi"
    assert applied["target"]["order_store_pairs"] == 1
    assert applied["apply"]["inserted_entry_rows"] == 1
    assert rows == [("api-header-entry", "O-HEADER", "ACMEWEAR")]


def test_fact_orders_entry_required_only_matches_freshness_skip_rules(tmp_path: Path) -> None:
    db_path = tmp_path / "app.sqlite"
    _make_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO fact_orders_kaspi(
                order_id, created_at, store_code, quantity, kaspi_status, internal_status, kaspi_status_detail
            )
            VALUES (?, ?, 'ACMEWEAR', 1, ?, ?, ?)
            """,
            [
                ("O-COMPLETE", "2026-05-05T10:00:00+05:00", "ARCHIVE", "COMPLETED", "COMPLETED"),
                ("O-CANCELLED", "2026-05-05T10:00:00+05:00", "ARCHIVE", "CANCELLED", "CANCELLED"),
                ("O-PENDING", "2026-05-05T10:00:00+05:00", "NEW", "NEW", "ACCEPTED_BY_MERCHANT"),
            ],
        )

    targets = build_missing_fact_order_targets(
        db_path,
        start_date="2026-05-05",
        as_of="2026-05-13",
        stores=("ACMEWEAR",),
        entry_required_only=True,
    )

    assert [target.order_id for target in targets] == ["O-COMPLETE"]


def test_strict_fact_orders_missing_evidence_still_fails_without_accepted_quarantine(tmp_path: Path) -> None:
    db_path = tmp_path / "app.sqlite"
    _make_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi(
                order_id, created_at, store_code, quantity, kaspi_status, internal_status, kaspi_status_detail
            )
            VALUES ('O-MISSING', '2026-05-15T10:00:00+05:00', 'UNIVERSAL', 1,
                    'ARCHIVE', 'COMPLETED', 'COMPLETED')
            """
        )

    try:
        recover_order_entries(
            db_path=db_path,
            as_of="2026-05-18",
            start_date="2026-05-05",
            target_source="fact_orders_kaspi",
            stores=("UNIVERSAL",),
            entry_required_only=True,
            output_root=tmp_path / "dry_run",
            source_bundles=[],
            recovery_ts="2026-05-18T23:59:59+05:00",
            strict=True,
        )
    except recovery.RecoveryError as exc:
        assert "unrecovered target rows=1" in str(exc)
    else:
        raise AssertionError("strict missing evidence should fail without accepted quarantine")


def test_strict_fact_orders_can_accept_copied_temp_no_entry_quarantine(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "app.sqlite"
    contract_path = tmp_path / "accepted_no_entry_quarantine.csv"
    _make_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi(
                order_id, created_at, store_code, sku_key, sku_id, my_size, quantity,
                kaspi_status, internal_status, kaspi_status_detail
            )
            VALUES ('O-MISSING', '2026-05-15T10:00:00+05:00', 'UNIVERSAL',
                    'SKU', 'SKU_XL', 'XL', 1, 'ARCHIVE', 'COMPLETED', 'COMPLETED')
            """
        )
    contract_path.write_text(
        "\n".join(
            [
                "order_id,store_code,classification,copied_temp_only,production_write_authorized,source_authority,notes",
                "O-MISSING,UNIVERSAL,RETAINED_ORDER_ENTRY_QUARANTINE,true,false,owner_confirmed,no real item-entry evidence",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("ENABLE_ORDER_ENTRY_RECOVERY_WRITE", "1")
    summary = recover_order_entries(
        db_path=db_path,
        as_of="2026-05-18",
        start_date="2026-05-05",
        target_source="fact_orders_kaspi",
        stores=("UNIVERSAL",),
        entry_required_only=True,
        output_root=tmp_path / "apply",
        source_bundles=[],
        recovery_ts="2026-05-18T23:59:59+05:00",
        accepted_no_entry_quarantine_csv=contract_path,
        apply=True,
        strict=True,
    )

    with sqlite3.connect(db_path) as conn:
        entry_count = conn.execute("SELECT COUNT(*) FROM fact_order_entries_kaspi").fetchone()[0]

    assert summary["quarantine"]["target_rows"] == 1
    assert summary["accepted_no_entry_quarantine"]["accepted_target_rows"] == 1
    assert summary["strict"]["passed"] is True
    assert summary["strict"]["passed_by_accepted_no_entry_quarantine"] is True
    assert summary["apply"]["inserted_entry_rows"] == 0
    assert entry_count == 0


def test_accepted_no_entry_quarantine_rejects_production_write_authority(tmp_path: Path) -> None:
    contract_path = tmp_path / "accepted_no_entry_quarantine.csv"
    contract_path.write_text(
        "\n".join(
            [
                "order_id,store_code,classification,copied_temp_only,production_write_authorized",
                "O-MISSING,UNIVERSAL,RETAINED_ORDER_ENTRY_QUARANTINE,true,true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        recovery.load_accepted_no_entry_quarantine(contract_path)
    except recovery.RecoveryError as exc:
        assert "must not authorize production writes" in str(exc)
    else:
        raise AssertionError("no-entry quarantine contract must deny production write authority")


def test_fact_orders_target_mode_defaults_to_api_only_sources(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "app.sqlite"
    api_root = tmp_path / "api_packet"
    store_root = api_root / "store_ACMEWEAR"
    store_root.mkdir(parents=True)
    _make_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi(order_id, created_at, store_code, quantity, kaspi_status, internal_status, kaspi_status_detail)
            VALUES ('O-API', '2026-05-05T10:00:00+05:00', 'ACMEWEAR', 1, 'ARCHIVE', 'COMPLETED', 'COMPLETED')
            """
        )
    (store_root / "archive_order_entries_raw.jsonl").write_text(
        json.dumps(
            {
                "order_code": "O-API",
                "store_code": "ACMEWEAR",
                "entries": [
                    {
                        "id": "api-only-entry",
                        "attributes": {
                            "offer": {"code": "ARTICLE-1", "name": "Offer"},
                            "quantity": 1,
                            "basePrice": 1000,
                            "totalPrice": 1000,
                        },
                        "relationships": {"product": {"data": {"id": "P-1"}}},
                    }
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("ENABLE_ORDER_ENTRY_RECOVERY_WRITE", "1")
    summary = recover_order_entries(
        db_path=db_path,
        as_of="2026-05-13",
        start_date="2026-05-05",
        target_source="fact_orders_kaspi",
        output_root=tmp_path / "apply",
        api_entry_roots=[api_root],
        recovery_ts="2026-05-13T23:59:59+05:00",
        apply=True,
        strict=True,
    )

    assert summary["sources"]["workbook_sources_used"] is False
    assert summary["sources"]["source_mode"] == "api_raw_order_entries_only"
    assert summary["apply"]["inserted_entry_rows"] == 1
