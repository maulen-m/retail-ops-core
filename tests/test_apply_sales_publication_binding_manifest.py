import json
import sqlite3
from pathlib import Path

import pytest

import scripts.apply_sales_publication_binding_manifest as applier
from core.sales.publication_binding import (
    HEADER_TABLE,
    LINE_TABLE,
    install_publication_binding_schema,
)
from core.sales.truth_views import ensure_sales_truth_views
from core.sales.truth_view_contract import build_truth_view_contract
from core.sales.publication_prerequisites import (
    build_minimal_publication_schema_contract,
    install_minimal_publication_schema,
)
from scripts.build_sales_publication_binding_manifest import (
    OLD_PUBLIC_COLUMNS,
    SCHEMA_VERSION,
    _multiset_hash,
    canonical_sha256,
    sha256_file,
)


def _seed_db(path: Path, *, refreshed_binding_schema: bool) -> None:
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
        CREATE TABLE audit_marker (
            marker TEXT PRIMARY KEY
        );
        CREATE TABLE fact_orders_kaspi (
            id INTEGER PRIMARY KEY,
            order_id TEXT NOT NULL,
            store_code TEXT NOT NULL,
            kaspi_article TEXT,
            line_identity_key TEXT
        );
        CREATE TABLE fact_sales (
            id INTEGER PRIMARY KEY,
            order_id TEXT NOT NULL,
            order_date TEXT,
            store_code TEXT NOT NULL,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            quantity REAL,
            line_net_rev REAL,
            cogs_line REAL,
            profit_line REAL
        );
        """
    )
    conn.executemany(
        "INSERT INTO dim_sku VALUES (?, NULL, NULL, 1000)",
        [("SKU_O1",), ("SKU_O2",)],
    )
    rows = []
    for order_index, (order_id, order_date) in enumerate(
        (("O1", "2026-01-12"), ("O2", "2026-01-13"))
    ):
        for line_index, size in enumerate(("2XL", "3XL")):
            sale_id = order_index * 2 + line_index + 1
            entry_id = f"{order_id}_E{line_index}"
            rows.append(
                (
                    sale_id,
                    order_id,
                    order_date,
                    f"SKU_{order_id}",
                    f"SKU_{order_id}_{size}",
                    size,
                    "ACMEWEAR",
                    1,
                    8982,
                    637.5,
                    None,
                    6932.88,
                    None,
                    "DELIVERED",
                    0,
                    "source.xlsx",
                    entry_id,
                    f"ARTICLE_{order_id}_{line_index}",
                    f"ENTRY:{entry_id}",
                )
            )
    conn.executemany(
        """
        INSERT INTO sales_fact_v2(
            sale_id, order_id, order_date, sku_key, sku_id, my_size,
            store_code, quantity, sell_price_kzt, delivery_fee, cogs, net_rev,
            profit, status, return_flag, source_file, source_entry_id,
            kaspi_article, line_identity_key
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.executemany(
        """
        INSERT INTO fact_sales_workbook_anchor
        VALUES (?, 'ACMEWEAR', ?, 2, 13865.76, 17964,
                'anchor.xlsx', '2026-03-07 20:42:46')
        """,
        [("O1", "2026-01-12"), ("O2", "2026-01-13")],
    )
    install_minimal_publication_schema(conn)
    if refreshed_binding_schema:
        install_publication_binding_schema(conn)
    ensure_sales_truth_views(conn)
    conn.commit()
    conn.close()


def _make_manifest(
    db_path: Path,
    *,
    order_id: str = "O1",
    binding_id: str = "B_TARGET",
) -> dict[str, object]:
    copied_db_sha = sha256_file(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        minimal_contract = build_minimal_publication_schema_contract(conn)
        source_rows = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM sales_fact_v2 WHERE order_id=? ORDER BY sale_id",
                (order_id,),
            ).fetchall()
        ]
        anchor = dict(
            conn.execute(
                "SELECT * FROM fact_sales_workbook_anchor WHERE order_id=? AND store_code='ACMEWEAR'",
                (order_id,),
            ).fetchone()
        )
        unbound_rows = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM view_sales_line_truth_unbound "
                "WHERE order_id=? AND store_code='ACMEWEAR' "
                "ORDER BY CAST(source_row_id AS INTEGER)",
                (order_id,),
            ).fetchall()
        ]
        selected_all = [
            dict(row)
            for row in conn.execute(
                f"SELECT {','.join(OLD_PUBLIC_COLUMNS)} FROM view_sales_line_truth"
            ).fetchall()
        ]
    finally:
        conn.close()

    unbound_by_sale_id = {
        int(row["source_row_id"]): row
        for row in unbound_rows
    }
    targets = []
    expected_bound_rows = []
    target_keys = set()
    for ordinal, source in enumerate(source_rows, start=1):
        sale_id = int(source["sale_id"])
        unbound = unbound_by_sale_id[sale_id]
        publication = {
            "sale_date": source["order_date"],
            "units": source["quantity"],
            "net_rev_kzt": source["net_rev"],
        }
        target = {
            "line_ordinal": ordinal,
            "sale_id": sale_id,
            "source_row_preimage": source,
            "source_row_preimage_sha256": canonical_sha256(source),
            "entry_evidence_sha256": canonical_sha256(
                {"sale_id": sale_id, "source_entry_id": source["source_entry_id"]}
            ),
            "source_line_proof_sha256": canonical_sha256(
                {"sale_id": sale_id, "proof": "fixture"}
            ),
            "promotion_target_sha256": canonical_sha256(
                {"sale_id": sale_id, "promotion": "fixture"}
            ),
            "unbound_selected_preimage": unbound,
            "publication": publication,
        }
        targets.append(target)
        old_row = {column: unbound[column] for column in OLD_PUBLIC_COLUMNS}
        old_row["sale_date"] = publication["sale_date"]
        old_row["units"] = publication["units"]
        old_row["net_rev_kzt"] = publication["net_rev_kzt"]
        if old_row["cogs_kzt"] is not None:
            old_row["profit_kzt"] = round(
                float(publication["net_rev_kzt"]) - float(old_row["cogs_kzt"]),
                2,
            )
        expected_bound_rows.append(old_row)
        target_keys.add(
            (
                str(source["order_id"]),
                str(source["store_code"]).upper(),
                "sales_fact_v2",
                str(source["sku_id"]),
                str(source["my_size"]),
            )
        )

    non_target = [
        row
        for row in selected_all
        if (
            str(row["order_id"]),
            str(row["store_code"]).upper(),
            str(row["source_table"]),
            str(row["source_sku_id"]),
            str(row["my_size"]),
        )
        not in target_keys
    ]
    body: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "binding_id": binding_id,
        "order_id": order_id,
        "store_code": "ACMEWEAR",
        "provisional_flag": False,
        "publication_effective_date": source_rows[0]["order_date"],
        "terminal_date_semantics": "STATUS_CHANGE_TIMESTAMP_PROVEN",
        "expected_line_count": len(targets),
        "copied_db_sha256": copied_db_sha,
        "canonical_hash_version": "canonical-json-v1-sort-keys-utf8-no-whitespace",
        "economics_policy_sha256": canonical_sha256([]),
        "economics_policy_files": [],
        "source_proof_file_path": "/fixture/source-proof.jsonl",
        "source_proof_file_sha256": "source-proof-sha",
        "source_proof_key": f"{order_id}:ACMEWEAR",
        "source_sidecar_manifest_path": "/fixture/source-sidecar.json",
        "source_sidecar_manifest_file_sha256": "source-sidecar-file-sha",
        "source_sidecar_manifest_internal_sha256": "source-sidecar-internal-sha",
        "promotion_manifest_path": "/fixture/promotion.json",
        "promotion_manifest_file_sha256": "promotion-file-sha",
        "promotion_manifest_internal_sha256": "promotion-internal-sha",
        "promotion_apply_report_path": "/fixture/promotion-apply.json",
        "promotion_apply_report_sha256": "promotion-apply-sha",
        "api_header_path": "/fixture/api-header.json",
        "api_header_sha256": "api-header-sha",
        "terminal_evidence_sha256": "terminal-evidence-sha",
        "anchor_preimage": anchor,
        "anchor_preimage_sha256": canonical_sha256(anchor),
        "unbound_selected_multiset_sha256": _multiset_hash(
            [{column: row[column] for column in OLD_PUBLIC_COLUMNS} for row in unbound_rows],
            sort_fields=("order_id", "store_code", "source_sku_id", "my_size"),
        ),
        "source_rows_multiset_sha256": canonical_sha256(source_rows),
        "targets": targets,
        "expected_bound_old_columns_multiset_sha256": _multiset_hash(
            expected_bound_rows,
            sort_fields=("order_id", "store_code", "source_sku_id", "my_size"),
        ),
        "non_target_old_columns_count": len(non_target),
        "non_target_old_columns_multiset_sha256": _multiset_hash(
            non_target,
            sort_fields=(
                "order_id",
                "store_code",
                "source_table",
                "source_sku_key",
                "source_sku_id",
                "my_size",
                "sale_date",
            ),
        ),
        "truth_view_runtime_contract": build_truth_view_contract(db_path),
        "minimal_publication_schema_contract": minimal_contract,
    }
    body["manifest_sha256"] = canonical_sha256(body)
    return body


def _write_manifest(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _binding_counts(path: Path, *, binding_id: str | None = None) -> tuple[int, int]:
    conn = sqlite3.connect(path)
    try:
        where = " WHERE binding_id=?" if binding_id else ""
        params = (binding_id,) if binding_id else ()
        return (
            int(conn.execute(f"SELECT COUNT(*) FROM {HEADER_TABLE}{where}", params).fetchone()[0]),
            int(conn.execute(f"SELECT COUNT(*) FROM {LINE_TABLE}{where}", params).fetchone()[0]),
        )
    finally:
        conn.close()


def _patch_unit_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(applier, "_assert_copied_target", lambda _path: None)
    monkeypatch.setattr(applier, "_validate_external_evidence", lambda _manifest: None)
    monkeypatch.setattr(
        applier,
        "_rebuild_manifest",
        lambda manifest, _db_path: manifest,
    )
    monkeypatch.setenv(applier.WRITE_ENV_GATE, "1")


def _dry_and_apply(
    *,
    db_path: Path,
    manifest_path: Path,
    work_dir: Path,
) -> dict[str, object]:
    pre_sha = sha256_file(db_path)
    dry_report = applier.apply_manifest(
        db_path=db_path,
        manifest_path=manifest_path,
        output_path=work_dir / "dry-report.json",
        backup_dir=None,
        apply=False,
        expected_pre_sha256=pre_sha,
        expected_target_count=2,
    )
    assert dry_report["status"] == "PASS"
    assert dry_report["rows_inserted"] == 0
    return applier.apply_manifest(
        db_path=db_path,
        manifest_path=manifest_path,
        output_path=work_dir / "apply-report.json",
        backup_dir=work_dir / "backups",
        apply=True,
        expected_pre_sha256=pre_sha,
        expected_target_count=2,
    )


def test_first_apply_rejects_legacy_view_before_backup_or_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_unit_dependencies(monkeypatch)
    db_path = tmp_path / "legacy.db"
    _seed_db(db_path, refreshed_binding_schema=False)
    reviewed_db = tmp_path / "reviewed-refreshed.db"
    _seed_db(reviewed_db, refreshed_binding_schema=True)
    conn = sqlite3.connect(db_path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert HEADER_TABLE not in tables
    assert LINE_TABLE not in tables

    manifest_path = tmp_path / "manifest.json"
    manifest = _make_manifest(reviewed_db)
    _write_manifest(manifest_path, manifest)
    pre_sha = sha256_file(db_path)
    output_path = tmp_path / "legacy-report.json"
    backup_dir = tmp_path / "legacy-backups"
    with pytest.raises(
        applier.PublicationBindingApplyError,
        match="refresh copied baseline",
    ):
        applier.apply_manifest(
            db_path=db_path,
            manifest_path=manifest_path,
            output_path=output_path,
            backup_dir=backup_dir,
            apply=True,
            expected_pre_sha256=pre_sha,
            expected_target_count=2,
        )

    assert sha256_file(db_path) == pre_sha
    assert not output_path.exists()
    assert not backup_dir.exists()
    conn = sqlite3.connect(db_path)
    try:
        tables = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        conn.close()
    assert HEADER_TABLE not in tables
    assert LINE_TABLE not in tables


@pytest.mark.parametrize(
    "mutation",
    ["schema_v1", "missing_contract", "missing_minimal_contract"],
)
def test_manifest_without_v2_truth_view_contract_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    _patch_unit_dependencies(monkeypatch)
    db_path = tmp_path / f"{mutation}.db"
    _seed_db(db_path, refreshed_binding_schema=True)
    manifest = _make_manifest(db_path)
    if mutation == "schema_v1":
        manifest["schema_version"] = "sales_publication_binding_manifest_v1"
    elif mutation == "missing_contract":
        manifest.pop("truth_view_runtime_contract")
    else:
        manifest.pop("minimal_publication_schema_contract")
    manifest.pop("manifest_sha256")
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    manifest_path = tmp_path / f"{mutation}.json"
    _write_manifest(manifest_path, manifest)
    pre_sha = sha256_file(db_path)

    with pytest.raises(applier.PublicationBindingApplyError):
        applier.apply_manifest(
            db_path=db_path,
            manifest_path=manifest_path,
            output_path=tmp_path / f"{mutation}-report.json",
            backup_dir=tmp_path / f"{mutation}-backups",
            apply=True,
            expected_pre_sha256=pre_sha,
            expected_target_count=2,
        )

    assert sha256_file(db_path) == pre_sha
    assert not (tmp_path / f"{mutation}-report.json").exists()
    assert not (tmp_path / f"{mutation}-backups").exists()


def test_first_apply_accepts_refreshed_baseline_with_empty_binding_tables(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_unit_dependencies(monkeypatch)
    db_path = tmp_path / "refreshed.db"
    _seed_db(db_path, refreshed_binding_schema=True)
    assert _binding_counts(db_path) == (0, 0)
    manifest_path = tmp_path / "manifest.json"
    manifest = _make_manifest(db_path)
    _write_manifest(manifest_path, manifest)

    report = _dry_and_apply(db_path=db_path, manifest_path=manifest_path, work_dir=tmp_path)

    assert report["binding_table_counts_before"] == {HEADER_TABLE: 0, LINE_TABLE: 0}
    assert report["binding_table_counts_after"] == {HEADER_TABLE: 1, LINE_TABLE: 2}
    assert report["binding_non_target_hashes_before"] == report["binding_non_target_hashes_after"]
    assert report["target_old_columns_multiset_sha256"] == manifest["expected_bound_old_columns_multiset_sha256"]
    assert report["non_target_old_columns_multiset_sha256"] == manifest["non_target_old_columns_multiset_sha256"]


def test_existing_other_binding_is_preserved_by_new_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_unit_dependencies(monkeypatch)
    db_path = tmp_path / "existing.db"
    _seed_db(db_path, refreshed_binding_schema=True)
    other_manifest = _make_manifest(db_path, order_id="O2", binding_id="B_OTHER")
    conn = sqlite3.connect(db_path)
    applier._insert_binding(
        conn,
        manifest=other_manifest,
        manifest_path=tmp_path / "other-manifest.json",
        manifest_file_sha256="other-manifest-file-sha",
    )
    ensure_sales_truth_views(conn)
    conn.commit()
    existing_hashes = {
        table: applier._logical_hash(conn, table)
        for table in applier.BINDING_MUTATION_TABLES
    }
    conn.close()
    assert _binding_counts(db_path, binding_id="B_OTHER") == (1, 2)

    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, _make_manifest(db_path))
    report = _dry_and_apply(db_path=db_path, manifest_path=manifest_path, work_dir=tmp_path)

    assert report["binding_table_counts_before"] == {HEADER_TABLE: 1, LINE_TABLE: 2}
    assert report["binding_table_counts_after"] == {HEADER_TABLE: 2, LINE_TABLE: 4}
    assert report["binding_table_count_deltas"] == {HEADER_TABLE: 1, LINE_TABLE: 2}
    assert report["binding_non_target_hashes_before"] == existing_hashes
    assert report["binding_non_target_hashes_after"] == existing_hashes
    assert _binding_counts(db_path, binding_id="B_OTHER") == (1, 2)
    assert _binding_counts(db_path, binding_id="B_TARGET") == (1, 2)


@pytest.mark.parametrize("mutation", ["under", "over"])
def test_binding_over_or_under_insert_rolls_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    _patch_unit_dependencies(monkeypatch)
    db_path = tmp_path / f"{mutation}.db"
    _seed_db(db_path, refreshed_binding_schema=True)
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, _make_manifest(db_path))
    pre_sha = sha256_file(db_path)
    original_insert = applier._insert_binding

    def injected_insert(conn: sqlite3.Connection, **kwargs: object) -> None:
        original_insert(conn, **kwargs)
        binding_id = str(kwargs["manifest"]["binding_id"])
        if mutation == "under":
            conn.execute(
                f"DELETE FROM {LINE_TABLE} WHERE binding_id=? AND line_ordinal=2",
                (binding_id,),
            )
            return
        columns = [str(row[1]) for row in conn.execute(f"PRAGMA table_info({LINE_TABLE})")]
        row = dict(
            zip(
                columns,
                conn.execute(
                    f"SELECT * FROM {LINE_TABLE} WHERE binding_id=? AND line_ordinal=1",
                    (binding_id,),
                ).fetchone(),
            )
        )
        row["line_ordinal"] = 3
        row["source_sale_id"] = 999999
        conn.execute(
            f"INSERT INTO {LINE_TABLE} ({','.join(columns)}) "
            f"VALUES ({','.join('?' for _ in columns)})",
            [row[column] for column in columns],
        )

    monkeypatch.setattr(applier, "_insert_binding", injected_insert)
    with pytest.raises(applier.PublicationBindingApplyError):
        applier.apply_manifest(
            db_path=db_path,
            manifest_path=manifest_path,
            output_path=tmp_path / "apply-report.json",
            backup_dir=tmp_path / "backups",
            apply=True,
            expected_pre_sha256=pre_sha,
            expected_target_count=2,
        )

    assert sha256_file(db_path) == pre_sha
    assert _binding_counts(db_path) == (0, 0)
    assert not (tmp_path / "apply-report.json").exists()


@pytest.mark.parametrize(
    ("mutation", "error_match"),
    [
        ("row", "pre-existing table count changed: audit_marker"),
        ("table", "unexpected additive tables"),
    ],
)
def test_unrelated_table_mutation_still_rolls_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    error_match: str,
) -> None:
    _patch_unit_dependencies(monkeypatch)
    db_path = tmp_path / f"unrelated-{mutation}.db"
    _seed_db(db_path, refreshed_binding_schema=True)
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, _make_manifest(db_path))
    pre_sha = sha256_file(db_path)
    original_insert = applier._insert_binding

    def injected_insert(conn: sqlite3.Connection, **kwargs: object) -> None:
        original_insert(conn, **kwargs)
        if mutation == "row":
            conn.execute("INSERT INTO audit_marker VALUES ('unexpected')")
        else:
            conn.execute("CREATE TABLE unexpected_apply_surface (id INTEGER)")

    monkeypatch.setattr(applier, "_insert_binding", injected_insert)
    with pytest.raises(applier.PublicationBindingApplyError, match=error_match):
        applier.apply_manifest(
            db_path=db_path,
            manifest_path=manifest_path,
            output_path=tmp_path / "apply-report.json",
            backup_dir=tmp_path / "backups",
            apply=True,
            expected_pre_sha256=pre_sha,
            expected_target_count=2,
        )

    assert sha256_file(db_path) == pre_sha
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM audit_marker").fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='unexpected_apply_surface'"
    ).fetchone()[0] == 0
    conn.close()


def test_second_apply_is_exact_idempotent_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_unit_dependencies(monkeypatch)
    db_path = tmp_path / "idempotent.db"
    _seed_db(db_path, refreshed_binding_schema=True)
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, _make_manifest(db_path))
    first_report = _dry_and_apply(db_path=db_path, manifest_path=manifest_path, work_dir=tmp_path)
    first_post_sha = sha256_file(db_path)

    replay = applier.apply_manifest(
        db_path=db_path,
        manifest_path=manifest_path,
        output_path=tmp_path / "replay-report.json",
        backup_dir=tmp_path / "replay-backups",
        apply=True,
        expected_pre_sha256=str(first_report["pre_sha256"]),
        expected_target_count=2,
    )

    assert replay["idempotent_replay"] is True
    assert replay["rows_inserted"] == 0
    assert replay["post_sha256"] == first_post_sha
    assert sha256_file(db_path) == first_post_sha
    assert _binding_counts(db_path, binding_id="B_TARGET") == (1, 2)
    assert not (tmp_path / "replay-backups").exists()


def test_post_commit_failure_restores_exact_copied_preimage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_unit_dependencies(monkeypatch)
    db_path = tmp_path / "post-commit.db"
    _seed_db(db_path, refreshed_binding_schema=True)
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, _make_manifest(db_path))
    pre_sha = sha256_file(db_path)
    output_path = tmp_path / "apply-report.json"
    backup_dir = tmp_path / "backups"

    def fail_post_commit(_path: Path) -> None:
        raise applier.PublicationBindingApplyError("injected post-commit failure")

    monkeypatch.setattr(applier, "_post_commit_barrier", fail_post_commit)
    with pytest.raises(applier.PublicationBindingApplyError, match="restored"):
        applier.apply_manifest(
            db_path=db_path,
            manifest_path=manifest_path,
            output_path=output_path,
            backup_dir=backup_dir,
            apply=True,
            expected_pre_sha256=pre_sha,
            expected_target_count=2,
        )

    assert sha256_file(db_path) == pre_sha
    assert _binding_counts(db_path) == (0, 0)
    assert not output_path.exists()
    rollback_paths = list(backup_dir.glob("ROLLBACK_*.json"))
    assert len(rollback_paths) == 1
    rollback = json.loads(rollback_paths[0].read_text(encoding="utf-8"))
    assert rollback["status"] == "RESTORED_AFTER_POST_COMMIT_FAILURE"
    assert rollback["restore_verified"] is True
    assert rollback["restored_sha256"] == pre_sha


def test_partial_preexisting_binding_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_unit_dependencies(monkeypatch)
    db_path = tmp_path / "partial.db"
    _seed_db(db_path, refreshed_binding_schema=True)
    partial_manifest = _make_manifest(db_path)
    header, _lines = applier._binding_postimages(
        manifest=partial_manifest,
        manifest_path=tmp_path / "partial-seed.json",
        manifest_file_sha256="partial-seed-file-sha",
    )
    conn = sqlite3.connect(db_path)
    columns = list(header)
    conn.execute(
        f"INSERT INTO {HEADER_TABLE} ({','.join(columns)}) "
        f"VALUES ({','.join('?' for _ in columns)})",
        [header[column] for column in columns],
    )
    ensure_sales_truth_views(conn)
    conn.commit()
    conn.close()
    assert _binding_counts(db_path, binding_id="B_TARGET") == (1, 0)

    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, _make_manifest(db_path))
    pre_sha = sha256_file(db_path)
    with pytest.raises(
        applier.PublicationBindingApplyError,
        match="binding_id already exists before first apply",
    ):
        applier.apply_manifest(
            db_path=db_path,
            manifest_path=manifest_path,
            output_path=tmp_path / "apply-report.json",
            backup_dir=tmp_path / "backups",
            apply=True,
            expected_pre_sha256=pre_sha,
            expected_target_count=2,
        )

    assert sha256_file(db_path) == pre_sha
    assert _binding_counts(db_path, binding_id="B_TARGET") == (1, 0)
    assert not (tmp_path / "apply-report.json").exists()
