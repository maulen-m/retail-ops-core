from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import scripts.apply_minimal_sales_source_identity_schema as schema_writer


def _seed(path: Path, *, existing_identity_columns: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    source_column = ", source_entry_id TEXT" if existing_identity_columns else ""
    sales_columns = (
        ", source_entry_id TEXT, kaspi_article TEXT, line_identity_key TEXT"
        if existing_identity_columns
        else ""
    )
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            f"""
            CREATE TABLE fact_orders_kaspi (
                id INTEGER PRIMARY KEY,
                order_id TEXT NOT NULL,
                store_code TEXT NOT NULL,
                kaspi_article TEXT,
                line_identity_key TEXT,
                payload TEXT
                {source_column}
            );
            CREATE TABLE sales_fact_v2 (
                sale_id INTEGER PRIMARY KEY,
                order_id TEXT NOT NULL,
                store_code TEXT NOT NULL,
                payload TEXT
                {sales_columns}
            );
            CREATE TABLE fact_sales (
                id INTEGER PRIMARY KEY,
                order_id TEXT NOT NULL,
                store_code TEXT NOT NULL,
                payload TEXT
                {sales_columns}
            );
            INSERT INTO fact_orders_kaspi(
                id, order_id, store_code, kaspi_article, line_identity_key,
                payload{', source_entry_id' if existing_identity_columns else ''}
            ) VALUES (
                1, 'O1', 'ACMEWEAR', 'ARTICLE-OLD', 'LEGACY-UNCHANGED',
                'orders'{", 'ENTRY-1'" if existing_identity_columns else ''}
            );
            INSERT INTO sales_fact_v2(
                sale_id, order_id, store_code, payload
                {', source_entry_id, kaspi_article, line_identity_key' if existing_identity_columns else ''}
            ) VALUES (
                1, 'O1', 'ACMEWEAR', 'v2'
                {", 'ENTRY-1', 'ARTICLE-OLD', 'LEGACY-UNCHANGED'" if existing_identity_columns else ''}
            );
            INSERT INTO fact_sales(
                id, order_id, store_code, payload
                {', source_entry_id, kaspi_article, line_identity_key' if existing_identity_columns else ''}
            ) VALUES (
                1, 'O1', 'ACMEWEAR', 'legacy'
                {", 'ENTRY-1', 'ARTICLE-OLD', 'LEGACY-UNCHANGED'" if existing_identity_columns else ''}
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def _column_names(path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def _index_names(path: Path) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
    finally:
        conn.close()


def _copied_db(tmp_path: Path, name: str) -> Path:
    return tmp_path / "runs" / "tmux_orchestration" / name


def test_dry_run_reports_exact_plan_without_mutation(tmp_path: Path) -> None:
    db = _copied_db(tmp_path, "dry.db")
    _seed(db)
    pre_sha = schema_writer.sha256_file(db)
    report = schema_writer.apply_minimal_schema(
        db_path=db,
        expected_pre_sha256=pre_sha,
        backup_dir=None,
        report_path=tmp_path / "dry.json",
        apply=False,
    )
    assert len(report["columns_to_add"]) == 7
    assert len(report["indexes_to_add"]) == 3
    assert report["write_applied"] is False
    assert report["integrity_check"] == "ok"
    assert report["data_update_statement_count"] == 0
    assert report["planned_changed_schema_objects"] == [
        "fact_orders_kaspi",
        "fact_sales",
        "sales_fact_v2",
        "ux_fact_orders_kaspi_source_entry_id",
        "ux_fact_sales_source_entry_id",
        "ux_sales_fact_v2_source_entry_id",
    ]
    assert report["fact_orders_identity_fingerprints_before"]["article_bearing"][
        "row_count"
    ] == 1
    assert report["migration031_non_target_normalizations_performed"] == 0
    assert schema_writer.sha256_file(db) == pre_sha


def test_apply_adds_only_seven_columns_and_three_indexes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _copied_db(tmp_path, "apply.db")
    _seed(db)
    pre_sha = schema_writer.sha256_file(db)
    monkeypatch.setenv(schema_writer.WRITE_ENV_GATE, "1")
    report = schema_writer.apply_minimal_schema(
        db_path=db,
        expected_pre_sha256=pre_sha,
        backup_dir=tmp_path / "backups",
        report_path=tmp_path / "apply.json",
        apply=True,
    )

    assert report["write_applied"] is True
    assert report["integrity_check"] == "ok"
    assert report["minimal_publication_schema_contract"]["compatible"] is True
    assert report["data_update_statement_count"] == 0
    assert report["changed_schema_objects"] == report[
        "planned_changed_schema_objects"
    ]
    assert report["fact_orders_identity_fingerprints_before"] == report[
        "fact_orders_identity_fingerprints_after"
    ]
    assert report["idempotent_replay"] is True
    assert report["idempotent_schema_delta"] == []
    assert report["original_projection_hashes_before"] == report[
        "original_projection_hashes_after"
    ]
    assert Path(report["backup_path"]).is_file()
    assert schema_writer.sha256_file(Path(report["backup_path"])) == pre_sha
    assert Path(report["rollback_path"]).is_file()
    assert _column_names(db, "fact_orders_kaspi") >= {"source_entry_id"}
    assert _column_names(db, "sales_fact_v2") >= {
        "source_entry_id",
        "kaspi_article",
        "line_identity_key",
    }
    assert _column_names(db, "fact_sales") >= {
        "source_entry_id",
        "kaspi_article",
        "line_identity_key",
    }
    assert set(schema_writer.INDEXES.values()) <= _index_names(db)
    conn = sqlite3.connect(db)
    try:
        assert conn.execute(
            "SELECT kaspi_article, line_identity_key FROM fact_orders_kaspi"
        ).fetchone() == ("ARTICLE-OLD", "LEGACY-UNCHANGED")
    finally:
        conn.close()


def test_apply_requires_exact_pre_sha(tmp_path: Path) -> None:
    db = _copied_db(tmp_path, "wrong-sha.db")
    _seed(db)
    with pytest.raises(schema_writer.MinimalSalesIdentitySchemaError, match="pre-SHA"):
        schema_writer.apply_minimal_schema(
            db_path=db,
            expected_pre_sha256="0" * 64,
            backup_dir=tmp_path / "backups",
            report_path=None,
            apply=True,
        )


def test_canonical_production_is_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _copied_db(tmp_path, "production-alias.db")
    _seed(db)
    pre_sha = schema_writer.sha256_file(db)
    monkeypatch.setattr(schema_writer, "PRODUCTION_DB", db.resolve())
    monkeypatch.setenv(schema_writer.WRITE_ENV_GATE, "1")
    with pytest.raises(
        schema_writer.MinimalSalesIdentitySchemaError,
        match="canonical production",
    ):
        schema_writer.apply_minimal_schema(
            db_path=db,
            expected_pre_sha256=pre_sha,
            backup_dir=tmp_path / "backups",
            report_path=None,
            apply=True,
        )
    assert schema_writer.sha256_file(db) == pre_sha
    assert not (tmp_path / "backups").exists()


def test_apply_without_write_gate_fails_before_backup_or_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _copied_db(tmp_path, "missing-gate.db")
    _seed(db)
    pre_sha = schema_writer.sha256_file(db)
    monkeypatch.delenv(schema_writer.WRITE_ENV_GATE, raising=False)

    with pytest.raises(
        schema_writer.MinimalSalesIdentitySchemaError,
        match=schema_writer.WRITE_ENV_GATE,
    ):
        schema_writer.apply_minimal_schema(
            db_path=db,
            expected_pre_sha256=pre_sha,
            backup_dir=tmp_path / "backups",
            report_path=tmp_path / "apply.json",
            apply=True,
        )

    assert schema_writer.sha256_file(db) == pre_sha
    assert not (tmp_path / "backups").exists()
    assert not (tmp_path / "apply.json").exists()


def test_hardlink_to_production_is_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    production = tmp_path / "production.db"
    _seed(production)
    alias = _copied_db(tmp_path, "production-hardlink.db")
    alias.parent.mkdir(parents=True, exist_ok=True)
    alias.hardlink_to(production)
    monkeypatch.setattr(schema_writer, "PRODUCTION_DB", production.resolve())

    with pytest.raises(
        schema_writer.MinimalSalesIdentitySchemaError,
        match="hardlink or alias",
    ):
        schema_writer.apply_minimal_schema(
            db_path=alias,
            expected_pre_sha256=schema_writer.sha256_file(alias),
            backup_dir=tmp_path / "backups",
            report_path=None,
            apply=True,
        )

    assert not (tmp_path / "backups").exists()


def test_target_outside_run_tree_is_refused(tmp_path: Path) -> None:
    db = tmp_path / "outside.db"
    _seed(db)

    with pytest.raises(
        schema_writer.MinimalSalesIdentitySchemaError,
        match="inside runs/tmux_orchestration",
    ):
        schema_writer.apply_minimal_schema(
            db_path=db,
            expected_pre_sha256=schema_writer.sha256_file(db),
            backup_dir=tmp_path / "backups",
            report_path=None,
            apply=False,
        )


def test_existing_sqlite_sidecar_is_refused(tmp_path: Path) -> None:
    db = _copied_db(tmp_path, "sidecar.db")
    _seed(db)
    sidecar = Path(str(db) + "-wal")
    sidecar.write_bytes(b"preserve")

    with pytest.raises(
        schema_writer.MinimalSalesIdentitySchemaError,
        match="SQLite sidecars",
    ):
        schema_writer.apply_minimal_schema(
            db_path=db,
            expected_pre_sha256=schema_writer.sha256_file(db),
            backup_dir=tmp_path / "backups",
            report_path=None,
            apply=False,
        )

    assert sidecar.read_bytes() == b"preserve"


def test_duplicate_nonblank_source_entries_roll_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _copied_db(tmp_path, "duplicates.db")
    _seed(db, existing_identity_columns=True)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO sales_fact_v2 VALUES "
            "(2, 'O2', 'ACMEWEAR', 'v2-2', 'ENTRY-1', 'A2', 'L2')"
        )
        conn.commit()
    finally:
        conn.close()
    pre_sha = schema_writer.sha256_file(db)
    monkeypatch.setenv(schema_writer.WRITE_ENV_GATE, "1")
    with pytest.raises(
        schema_writer.MinimalSalesIdentitySchemaError,
        match="duplicate nonblank",
    ):
        schema_writer.apply_minimal_schema(
            db_path=db,
            expected_pre_sha256=pre_sha,
            backup_dir=tmp_path / "backups",
            report_path=tmp_path / "apply.json",
            apply=True,
        )
    assert schema_writer.sha256_file(db) == pre_sha
    assert not (tmp_path / "apply.json").exists()
    assert set(schema_writer.INDEXES.values()).isdisjoint(_index_names(db))


def test_existing_report_is_refused_before_any_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _copied_db(tmp_path, "report-collision.db")
    _seed(db)
    pre_sha = schema_writer.sha256_file(db)
    report_path = tmp_path / "existing.json"
    report_path.write_text("preserve\n", encoding="utf-8")
    monkeypatch.setenv(schema_writer.WRITE_ENV_GATE, "1")
    with pytest.raises(
        schema_writer.MinimalSalesIdentitySchemaError,
        match="report already exists",
    ):
        schema_writer.apply_minimal_schema(
            db_path=db,
            expected_pre_sha256=pre_sha,
            backup_dir=tmp_path / "backups",
            report_path=report_path,
            apply=True,
        )
    assert schema_writer.sha256_file(db) == pre_sha
    assert report_path.read_text(encoding="utf-8") == "preserve\n"
    assert not (tmp_path / "backups").exists()


def test_idempotent_schema_replay_has_zero_planned_additions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _copied_db(tmp_path, "idempotent.db")
    _seed(db)
    monkeypatch.setenv(schema_writer.WRITE_ENV_GATE, "1")
    first_sha = schema_writer.sha256_file(db)
    schema_writer.apply_minimal_schema(
        db_path=db,
        expected_pre_sha256=first_sha,
        backup_dir=tmp_path / "first-backups",
        report_path=None,
        apply=True,
    )
    second_sha = schema_writer.sha256_file(db)
    report = schema_writer.apply_minimal_schema(
        db_path=db,
        expected_pre_sha256=second_sha,
        backup_dir=tmp_path / "second-backups",
        report_path=None,
        apply=True,
    )
    assert report["columns_to_add"] == []
    assert report["indexes_to_add"] == []
    assert report["changed_schema_objects"] == []
    assert report["idempotent_replay"] is True
    assert report["original_projection_hashes_before"] == report[
        "original_projection_hashes_after"
    ]
