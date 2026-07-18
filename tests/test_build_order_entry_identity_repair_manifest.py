from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from scripts.build_order_entry_identity_repair_manifest import (
    OrderEntryIdentityManifestError,
    build_order_entry_identity_repair_manifest,
    write_manifest,
)
from scripts.apply_order_entry_identity_repair_manifest import (
    COPIED_APPLY_ENV_GATE,
    OrderEntryIdentityApplyError,
    apply_manifest_to_copied_db,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _b64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def _raw(offer_id: str, pos_id: str, *, quantity: int = 1, total: float = 8982.0) -> str:
    return json.dumps(
        {
            "attributes": {
                "offer": {"code": offer_id},
                "quantity": quantity,
                "totalPrice": total,
            },
            "relationships": {
                "deliveryPointOfService": {"data": {"id": pos_id}}
            },
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def _seed(path: Path, *, duplicate_second_mapping: bool = False) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
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
        CREATE TABLE dim_kaspi_article_map (
            id INTEGER PRIMARY KEY,
            store_code TEXT,
            merchant_id TEXT,
            kaspi_article TEXT,
            sku_key TEXT,
            sku_id TEXT,
            active_flag INTEGER DEFAULT 1
        );
        CREATE TABLE dim_sku_size (
            sku_id TEXT PRIMARY KEY,
            sku_key TEXT,
            my_size TEXT,
            active_flag INTEGER DEFAULT 1
        );
        CREATE TABLE fact_sales (
            id INTEGER PRIMARY KEY,
            order_id TEXT,
            store_code TEXT,
            kaspi_offer_name TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            quantity INTEGER,
            sell_price_kzt REAL
        );
        CREATE TABLE sales_fact_v2 (
            sale_id INTEGER PRIMARY KEY,
            order_id TEXT,
            store_code TEXT,
            kaspi_offer_name TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            quantity INTEGER,
            sell_price_kzt REAL,
            status TEXT,
            return_flag INTEGER
        );
        CREATE TABLE fact_orders_kaspi (
            id INTEGER PRIMARY KEY,
            order_id TEXT,
            store_code TEXT,
            kaspi_offer_name TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            assigned_size TEXT,
            quantity INTEGER,
            unit_price_kzt REAL,
            kaspi_status TEXT,
            internal_status TEXT,
            source TEXT
        );
        CREATE TABLE fact_cashflow_events (
            id INTEGER PRIMARY KEY,
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
            run_id TEXT,
            event_hash TEXT
        );
        """
    )

    order_id = "784153715"
    store = "ACMEWEAR"
    merchant = "30137883"
    sku_key = "CL_OC_MEN_LINE52_BLACK"
    offer_2xl = f"{sku_key}_103217238_50/2XL_(2XL)"
    offer_3xl = f"{sku_key}_103217238_52-54/52-54_(3XL)"
    pos = _b64("30137883_PP1")
    conn.executemany(
        """
        INSERT INTO fact_order_entries_kaspi (
            entry_id, order_id, store_code, product_id, offer_id, quantity,
            unit_price_kzt, total_price_kzt, raw_json
        ) VALUES (?, ?, ?, ?, ?, 1, 0, 8982, ?)
        """,
        [
            ("entry-0", order_id, store, "product-0", offer_2xl, _raw(offer_2xl, pos)),
            ("entry-1", order_id, store, "product-1", offer_3xl, _raw(offer_3xl, pos)),
        ],
    )
    conn.executemany(
        "INSERT INTO dim_sku_size (sku_id, sku_key, my_size) VALUES (?, ?, ?)",
        [(f"{sku_key}_2XL", sku_key, "2XL"), (f"{sku_key}_3XL", sku_key, "3XL")],
    )
    conn.executemany(
        """
        INSERT INTO dim_kaspi_article_map (
            id, store_code, merchant_id, kaspi_article, sku_key, sku_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (849, store, merchant, offer_2xl, sku_key, f"{sku_key}_2XL"),
            (651, store, merchant, offer_3xl, sku_key, f"{sku_key}_3XL"),
        ],
    )
    if duplicate_second_mapping:
        conn.execute(
            """
            INSERT INTO dim_kaspi_article_map (
                id, store_code, merchant_id, kaspi_article, sku_key, sku_id
            ) VALUES (999, ?, ?, ?, ?, ?)
            """,
            (store, merchant, offer_3xl, sku_key, f"{sku_key}_XL"),
        )

    fact_rows = [
        (10, "Print black 2XL", f"{sku_key}_2XL", "2XL"),
        (11, "Print black 52-54", f"{sku_key}_XL", "XL"),
    ]
    conn.executemany(
        """
        INSERT INTO fact_sales (
            id, order_id, store_code, kaspi_offer_name, sku_key, sku_id,
            my_size, quantity, sell_price_kzt
        ) VALUES (?, ?, 'ACMEWEAR', ?, ?, ?, ?, 1, 8982)
        """,
        [(row_id, order_id, name, sku_key, sku_id, size) for row_id, name, sku_id, size in fact_rows],
    )
    conn.executemany(
        """
        INSERT INTO sales_fact_v2 (
            sale_id, order_id, store_code, kaspi_offer_name, sku_key, sku_id,
            my_size, quantity, sell_price_kzt, status, return_flag
        ) VALUES (?, ?, 'ACMEWEAR', ?, ?, ?, ?, 1, 8982, 'DELIVERED', 0)
        """,
        [(row_id + 10, order_id, name, sku_key, sku_id, size) for row_id, name, sku_id, size in fact_rows],
    )
    conn.executemany(
        """
        INSERT INTO fact_orders_kaspi (
            id, order_id, store_code, kaspi_offer_name, sku_key, sku_id,
            my_size, assigned_size, quantity, unit_price_kzt, kaspi_status,
            internal_status, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, '', 1, ?, ?, ?, ?)
        """,
        [
            (1, order_id, store, "Print black 2XL", sku_key, f"{sku_key}_2XL", "2XL", 8982, "DELIVERED", "NEW", "kaspi_archive"),
            (2, order_id, store, "Print black 52-54", sku_key, f"{sku_key}_XL", "XL", 17964, "ARCHIVE", "NEW", "kaspi_archive"),
            (3, order_id, "UNKNOWN", "Print black 2XL", sku_key, f"{sku_key}_2XL", "2XL", 8982, "COMPLETED", "COMPLETED", "EXCEL_EXPORT"),
            (4, order_id, "UNKNOWN", "Print black 52-54", "", "", "3XL", 8982, "COMPLETED", "COMPLETED", "EXCEL_EXPORT"),
        ],
    )
    conn.executemany(
        """
        INSERT INTO fact_cashflow_events (
            id, event_date, event_type, account, amount_kzt, store_code,
            sku_key, sku_id, ref_type, ref_id, source, run_id, event_hash
        ) VALUES (?, '2026-01-26', 'CASH_IN', ?, ?, ?, ?, ?, 'ORDER', ?,
                  'ORDER_MODELLED', 'legacy', ?)
        """,
        [
            (100, "KASPI_PAY_ACMEWEAR", 6873.71, store, sku_key, f"{sku_key}_2XL", order_id, "h100"),
            (101, "KASPI_PAY_ACMEWEAR", 14034.59, store, sku_key, f"{sku_key}_XL", order_id, "h101"),
            (102, "KASPI_PAY_UNKNOWN", 6873.71, "UNKNOWN", "", "", order_id, "h102"),
        ],
    )
    conn.commit()
    conn.close()


def test_builds_exact_non_applying_manifest_and_preserves_source(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _seed(db)
    before = _sha256(db)

    manifest = build_order_entry_identity_repair_manifest(
        db_path=db,
        order_id="784153715",
        store_code="ACMEWEAR",
        merchant_id="30137883",
        expected_entry_count=2,
        expected_db_sha256=before,
    )

    assert _sha256(db) == before
    assert manifest["production_apply_authorized"] is False
    assert manifest["copied_apply_ready"] is False
    assert manifest["identity_patch_candidate_count"] == 6
    assert manifest["fact_orders_quarantine_candidate_count"] == 2
    assert manifest["cash_in_residual_count"] == 3
    assert manifest["requires_migration_031"] is True
    assert [row["mapping_row_id"] for row in manifest["entries"]] == [849, 651]
    assert [row["canonical_size"] for row in manifest["entries"]] == ["2XL", "3XL"]
    assert [row["row_id"] for row in manifest["projection_patches"]["fact_orders_kaspi"]] == [1, 4]
    assert manifest["projection_patches"]["fact_sales"][1]["after"]["my_size"] == "3XL"
    assert manifest["projection_patches"]["sales_fact_v2"][1]["after"]["sku_id"].endswith("_3XL")
    assert manifest["fact_orders_quarantine_candidates"][0]["action"] == "NO_WRITE_QUARANTINE_REQUIRED"
    assert manifest["cash_in_residuals"][2]["classification"] == "WRONG_STORE_DUPLICATE_CANDIDATE"
    assert len(manifest["manifest_sha256"]) == 64

    out = tmp_path / "manifest.json"
    file_sha = write_manifest(out, manifest)
    assert file_sha == _sha256(out)
    assert json.loads(out.read_text(encoding="utf-8"))["manifest_sha256"] == manifest["manifest_sha256"]


def test_manifest_is_deterministic_for_same_source(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _seed(db)
    kwargs = {
        "db_path": db,
        "order_id": "784153715",
        "store_code": "ACMEWEAR",
        "merchant_id": "30137883",
        "expected_entry_count": 2,
    }
    first = build_order_entry_identity_repair_manifest(**kwargs)
    second = build_order_entry_identity_repair_manifest(**kwargs)
    assert first == second


def test_fails_closed_on_conflicting_exact_mapping(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _seed(db, duplicate_second_mapping=True)
    with pytest.raises(OrderEntryIdentityManifestError, match="exact active mapping count"):
        build_order_entry_identity_repair_manifest(
            db_path=db,
            order_id="784153715",
            store_code="ACMEWEAR",
            merchant_id="30137883",
            expected_entry_count=2,
        )


def test_fails_closed_on_pre_hash_or_entry_count_mismatch(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _seed(db)
    with pytest.raises(OrderEntryIdentityManifestError, match="source DB SHA"):
        build_order_entry_identity_repair_manifest(
            db_path=db,
            order_id="784153715",
            store_code="ACMEWEAR",
            merchant_id="30137883",
            expected_entry_count=2,
            expected_db_sha256="0" * 64,
        )
    with pytest.raises(OrderEntryIdentityManifestError, match="entry count"):
        build_order_entry_identity_repair_manifest(
            db_path=db,
            order_id="784153715",
            store_code="ACMEWEAR",
            merchant_id="30137883",
            expected_entry_count=3,
        )


def _add_migration_031_projection_columns(path: Path) -> None:
    conn = sqlite3.connect(path)
    for table in ("fact_sales", "sales_fact_v2", "fact_orders_kaspi"):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN source_entry_id TEXT")
        conn.execute(f"ALTER TABLE {table} ADD COLUMN kaspi_article TEXT")
        conn.execute(f"ALTER TABLE {table} ADD COLUMN line_identity_key TEXT")
    conn.commit()
    conn.close()


def test_copied_apply_is_backup_first_exact_and_idempotent_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "app.identity_candidate.db"
    _seed(db)
    manifest = build_order_entry_identity_repair_manifest(
        db_path=db,
        order_id="784153715",
        store_code="ACMEWEAR",
        merchant_id="30137883",
        expected_entry_count=2,
    )
    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest_path, manifest)
    _add_migration_031_projection_columns(db)
    pre_sha = _sha256(db)

    monkeypatch.setenv(COPIED_APPLY_ENV_GATE, "1")
    report = apply_manifest_to_copied_db(
        copied_db_path=db,
        manifest_path=manifest_path,
        expected_manifest_sha256=manifest["manifest_sha256"],
        expected_copied_pre_sha256=pre_sha,
        backup_dir=tmp_path / "backups",
        report_path=tmp_path / "apply_report.json",
        apply=True,
    )

    assert report["status"] == "APPLIED_TO_COPIED_DB_ONLY"
    assert report["rows_updated"] == 6
    assert report["source_manifest_production_apply_authorized"] is False
    assert report["non_target_projection_hashes_unchanged"] is True
    assert report["cashflow_table_hash_unchanged"] is True
    assert Path(report["backup_path"]).is_file()
    assert _sha256(Path(report["backup_path"])) == pre_sha
    assert report["backup_sha256"] == pre_sha
    rollback = json.loads(Path(report["rollback_path"]).read_text(encoding="utf-8"))
    assert rollback["status"] == "READY"
    assert report["integrity_check"] == "ok"

    conn = sqlite3.connect(db)
    assert conn.execute(
        "SELECT store_code, sku_id, my_size, source_entry_id FROM fact_orders_kaspi WHERE id=4"
    ).fetchone() == (
        "ACMEWEAR",
        "CL_OC_MEN_LINE52_BLACK_3XL",
        "3XL",
        "entry-1",
    )
    assert conn.execute(
        "SELECT sku_id, my_size, source_entry_id FROM fact_sales WHERE id=11"
    ).fetchone() == ("CL_OC_MEN_LINE52_BLACK_3XL", "3XL", "entry-1")
    assert conn.execute(
        "SELECT sku_id, my_size, source_entry_id FROM sales_fact_v2 WHERE sale_id=21"
    ).fetchone() == ("CL_OC_MEN_LINE52_BLACK_3XL", "3XL", "entry-1")
    assert conn.execute("SELECT COUNT(*) FROM fact_cashflow_events").fetchone()[0] == 3
    conn.close()

    with pytest.raises(OrderEntryIdentityApplyError, match="before-row hash mismatch"):
        apply_manifest_to_copied_db(
            copied_db_path=db,
            manifest_path=manifest_path,
            expected_manifest_sha256=manifest["manifest_sha256"],
            expected_copied_pre_sha256=_sha256(db),
            backup_dir=tmp_path / "second_backups",
            report_path=tmp_path / "second_report.json",
            apply=True,
        )


def test_post_commit_failure_restores_exact_copied_preimage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = tmp_path / "app.identity_restore.db"
    _seed(db)
    manifest = build_order_entry_identity_repair_manifest(
        db_path=db,
        order_id="784153715",
        store_code="ACMEWEAR",
        merchant_id="30137883",
        expected_entry_count=2,
    )
    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest_path, manifest)
    _add_migration_031_projection_columns(db)
    pre_sha = _sha256(db)
    backup_dir = tmp_path / "backups"
    report_path = tmp_path / "report.json"
    monkeypatch.setenv(COPIED_APPLY_ENV_GATE, "1")

    def fail_post_commit(_path: Path) -> None:
        raise OrderEntryIdentityApplyError("injected post-commit failure")

    monkeypatch.setattr(
        "scripts.apply_order_entry_identity_repair_manifest._post_commit_barrier",
        fail_post_commit,
    )

    with pytest.raises(OrderEntryIdentityApplyError, match="restored"):
        apply_manifest_to_copied_db(
            copied_db_path=db,
            manifest_path=manifest_path,
            expected_manifest_sha256=manifest["manifest_sha256"],
            expected_copied_pre_sha256=pre_sha,
            backup_dir=backup_dir,
            report_path=report_path,
            apply=True,
        )

    assert _sha256(db) == pre_sha
    assert not report_path.exists()
    rollback_paths = list(backup_dir.glob("ROLLBACK_ORDER_ENTRY_IDENTITY_*.json"))
    assert len(rollback_paths) == 1
    rollback = json.loads(rollback_paths[0].read_text(encoding="utf-8"))
    assert rollback["status"] == "RESTORED_AFTER_POST_COMMIT_FAILURE"
    assert rollback["restore_verified"] is True
    assert rollback["restored_sha256"] == pre_sha


def test_copied_apply_requires_gate_and_exact_pre_hash(tmp_path: Path) -> None:
    db = tmp_path / "app.identity_candidate.db"
    _seed(db)
    manifest = build_order_entry_identity_repair_manifest(
        db_path=db,
        order_id="784153715",
        store_code="ACMEWEAR",
        merchant_id="30137883",
        expected_entry_count=2,
    )
    manifest_path = tmp_path / "manifest.json"
    write_manifest(manifest_path, manifest)
    _add_migration_031_projection_columns(db)

    with pytest.raises(OrderEntryIdentityApplyError, match=COPIED_APPLY_ENV_GATE):
        apply_manifest_to_copied_db(
            copied_db_path=db,
            manifest_path=manifest_path,
            expected_manifest_sha256=manifest["manifest_sha256"],
            expected_copied_pre_sha256=_sha256(db),
            backup_dir=tmp_path / "backups",
            report_path=tmp_path / "report.json",
            apply=True,
        )

    with pytest.MonkeyPatch.context() as patch:
        patch.setenv(COPIED_APPLY_ENV_GATE, "1")
        occupied_report = tmp_path / "occupied_report.json"
        occupied_report.write_text("occupied\n", encoding="utf-8")
        pre_collision_sha = _sha256(db)
        with pytest.raises(OrderEntryIdentityApplyError, match="report path already exists"):
            apply_manifest_to_copied_db(
                copied_db_path=db,
                manifest_path=manifest_path,
                expected_manifest_sha256=manifest["manifest_sha256"],
                expected_copied_pre_sha256=pre_collision_sha,
                backup_dir=tmp_path / "collision_backups",
                report_path=occupied_report,
                apply=True,
            )
        assert _sha256(db) == pre_collision_sha
        with pytest.raises(OrderEntryIdentityApplyError, match="copied DB pre-SHA mismatch"):
            apply_manifest_to_copied_db(
                copied_db_path=db,
                manifest_path=manifest_path,
                expected_manifest_sha256=manifest["manifest_sha256"],
                expected_copied_pre_sha256="0" * 64,
                backup_dir=tmp_path / "backups2",
                report_path=tmp_path / "report2.json",
                apply=True,
            )
