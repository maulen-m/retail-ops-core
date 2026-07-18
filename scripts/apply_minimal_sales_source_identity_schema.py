#!/usr/bin/env python3
"""Install only the minimal sales source-entry projection schema.

This is the narrow alternative to migration 031 for publication-binding work.
It adds seven nullable columns and three source-entry uniqueness guards.  It
does not infer, normalize, or backfill any legacy article or line identity.

Default: dry-run.  Apply requires an exact pre-SHA, a verified backup, --apply,
and ENABLE_COPIED_MINIMAL_SALES_PUBLICATION_BOOTSTRAP_WRITE=1.  This first
native writer is copy-only and refuses the canonical production DB, aliases,
and targets outside ``runs/tmux_orchestration``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.sales.publication_prerequisites import (  # noqa: E402
    COLUMNS,
    INDEXES,
    REQUIRED_PREEXISTING_COLUMNS,
    build_minimal_publication_schema_contract,
    expected_index_sql,
    install_minimal_publication_schema,
    require_minimal_publication_schema,
)

DEFAULT_DB_PATH = (PROJECT_ROOT / "db" / "app.db").resolve()
PRODUCTION_DB = DEFAULT_DB_PATH
WRITE_ENV_GATE = "ENABLE_COPIED_MINIMAL_SALES_PUBLICATION_BOOTSTRAP_WRITE"


class MinimalSalesIdentitySchemaError(RuntimeError):
    pass


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sidecars(path: Path) -> list[Path]:
    return [
        candidate
        for candidate in (
            Path(str(path) + "-wal"),
            Path(str(path) + "-shm"),
            Path(str(path) + "-journal"),
        )
        if candidate.exists()
    ]


def _integrity(path: Path) -> str:
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    try:
        return str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    finally:
        conn.close()


def _assert_copied_target(path: Path) -> None:
    resolved = path.resolve()
    if resolved == PRODUCTION_DB:
        raise MinimalSalesIdentitySchemaError("refusing canonical production DB")
    if PRODUCTION_DB.exists() and os.path.samefile(resolved, PRODUCTION_DB):
        raise MinimalSalesIdentitySchemaError(
            "refusing hardlink or alias to canonical production DB"
        )
    if "/runs/tmux_orchestration/" not in str(resolved):
        raise MinimalSalesIdentitySchemaError(
            "copied bootstrap target must be inside runs/tmux_orchestration"
        )


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _column_rows(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    return conn.execute(f"PRAGMA table_info({_quote(table)})").fetchall()


def _columns(conn: sqlite3.Connection, table: str) -> dict[str, str]:
    return {str(row[1]): str(row[2] or "").upper() for row in _column_rows(conn, table)}


def _index_sql(conn: sqlite3.Connection, name: str) -> str | None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
        (name,),
    ).fetchone()
    return None if row is None or row[0] is None else str(row[0])


def _normalized_sql(sql: str) -> str:
    return " ".join(sql.upper().replace('"', "").split())


def _projection_hash(
    conn: sqlite3.Connection,
    table: str,
    columns: list[str],
) -> dict[str, Any]:
    selected = ",".join(_quote(name) for name in columns)
    rows = [
        list(row)
        for row in conn.execute(
            f"SELECT {selected} FROM {_quote(table)} ORDER BY rowid"
        ).fetchall()
    ]
    return {"row_count": len(rows), "logical_sha256": canonical_sha256(rows)}


def _schema_objects(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    return {
        str(name): {
            "type": str(kind),
            "sql_sha256": hashlib.sha256(str(sql or "").encode("utf-8")).hexdigest(),
        }
        for kind, name, sql in conn.execute(
            "SELECT type,name,sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        ).fetchall()
    }


def _changed_schema_objects(
    before: dict[str, Any], after: dict[str, Any]
) -> list[str]:
    return sorted(
        name
        for name in set(before) | set(after)
        if before.get(name) != after.get(name)
    )


def _fact_orders_identity_fingerprints(
    conn: sqlite3.Connection,
) -> dict[str, dict[str, Any]]:
    columns = ("id", "order_id", "store_code", "kaspi_article", "line_identity_key")
    selected = ",".join(_quote(name) for name in columns)

    def capture(where: str = "") -> dict[str, Any]:
        rows = [
            list(row)
            for row in conn.execute(
                f"SELECT {selected} FROM fact_orders_kaspi {where} ORDER BY id"
            ).fetchall()
        ]
        return {"row_count": len(rows), "logical_sha256": canonical_sha256(rows)}

    return {
        "full": capture(),
        "article_bearing": capture(
            "WHERE TRIM(COALESCE(kaspi_article, '')) <> ''"
        ),
    }


def _duplicate_source_entry_groups(conn: sqlite3.Connection, table: str) -> int:
    return int(
        conn.execute(
            f"""
            SELECT COUNT(*) FROM (
                SELECT TRIM(source_entry_id)
                FROM {_quote(table)}
                WHERE TRIM(COALESCE(source_entry_id, '')) <> ''
                GROUP BY TRIM(source_entry_id)
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
    )


def _schema_plan(conn: sqlite3.Connection) -> dict[str, Any]:
    missing_tables = [table for table in COLUMNS if not _table_exists(conn, table)]
    if missing_tables:
        raise MinimalSalesIdentitySchemaError(
            f"required tables missing: {missing_tables}"
        )

    columns_to_add: list[dict[str, str]] = []
    indexes_to_add: list[dict[str, str]] = []
    original_columns: dict[str, list[str]] = {}
    for table, additions in COLUMNS.items():
        current = _columns(conn, table)
        missing_base = REQUIRED_PREEXISTING_COLUMNS[table] - set(current)
        if missing_base:
            raise MinimalSalesIdentitySchemaError(
                f"required pre-existing columns missing from {table}: "
                f"{sorted(missing_base)}"
            )
        original_columns[table] = [str(row[1]) for row in _column_rows(conn, table)]
        for column, declaration in additions.items():
            if column not in current:
                columns_to_add.append(
                    {"table": table, "column": column, "declaration": declaration}
                )
            elif current[column] not in ("", "TEXT"):
                raise MinimalSalesIdentitySchemaError(
                    f"wrong existing type for {table}.{column}: {current[column]}"
                )

        if "source_entry_id" in current:
            duplicate_groups = _duplicate_source_entry_groups(conn, table)
            if duplicate_groups:
                raise MinimalSalesIdentitySchemaError(
                    f"duplicate nonblank source_entry_id groups in {table}: "
                    f"{duplicate_groups}"
                )

        index_name = INDEXES[table]
        observed_sql = _index_sql(conn, index_name)
        expected_sql = expected_index_sql(table, index_name)
        if observed_sql is None:
            indexes_to_add.append(
                {"table": table, "index": index_name, "sql": expected_sql}
            )
        elif _normalized_sql(observed_sql) != _normalized_sql(expected_sql):
            raise MinimalSalesIdentitySchemaError(
                f"wrong existing index definition: {index_name}"
            )

    return {
        "columns_to_add": columns_to_add,
        "indexes_to_add": indexes_to_add,
        "original_columns": original_columns,
    }


def apply_minimal_schema(
    *,
    db_path: Path,
    expected_pre_sha256: str | None,
    backup_dir: Path | None,
    report_path: Path | None,
    apply: bool,
) -> dict[str, Any]:
    db_path = db_path.resolve()
    if not db_path.is_file():
        raise MinimalSalesIdentitySchemaError(f"DB does not exist: {db_path}")
    _assert_copied_target(db_path)
    if report_path is not None and report_path.exists():
        raise MinimalSalesIdentitySchemaError(f"report already exists: {report_path}")
    sidecars = _sidecars(db_path)
    if sidecars:
        raise MinimalSalesIdentitySchemaError(
            "refusing DB with SQLite sidecars: " + ", ".join(map(str, sidecars))
        )
    pre_sha = sha256_file(db_path)
    if expected_pre_sha256 and pre_sha != expected_pre_sha256:
        raise MinimalSalesIdentitySchemaError(
            f"pre-SHA mismatch: expected {expected_pre_sha256}, observed {pre_sha}"
        )
    source_integrity = _integrity(db_path)
    if source_integrity.lower() != "ok":
        raise MinimalSalesIdentitySchemaError("source DB integrity_check failed")

    conn = sqlite3.connect(str(db_path))
    try:
        plan = _schema_plan(conn)
        original_hashes_before = {
            table: _projection_hash(conn, table, columns)
            for table, columns in plan["original_columns"].items()
        }
        schema_objects_before = _schema_objects(conn)
        identity_fingerprints_before = _fact_orders_identity_fingerprints(conn)
    finally:
        conn.close()

    planned_changed_schema_objects = sorted(
        {item["table"] for item in plan["columns_to_add"]}
        | {item["index"] for item in plan["indexes_to_add"]}
    )

    report: dict[str, Any] = {
        "status": "PASS",
        "operation": "MINIMAL_SALES_SOURCE_IDENTITY_SCHEMA",
        "mode": "APPLY" if apply else "DRY_RUN",
        "db_path": str(db_path),
        "production_target": False,
        "pre_sha256": pre_sha,
        "columns_to_add": plan["columns_to_add"],
        "indexes_to_add": [
            {
                "table": item["table"],
                "index": item["index"],
                "sql": item["sql"],
                "sql_sha256": hashlib.sha256(item["sql"].encode("utf-8")).hexdigest(),
            }
            for item in plan["indexes_to_add"]
        ],
        "original_columns_before": plan["original_columns"],
        "original_projection_hashes_before": original_hashes_before,
        "fact_orders_identity_fingerprints_before": identity_fingerprints_before,
        "schema_objects_before": schema_objects_before,
        "planned_changed_schema_objects": planned_changed_schema_objects,
        "migration031_non_target_normalizations_performed": 0,
        "data_update_statement_count": 0,
        "integrity_check": source_integrity,
        "write_applied": False,
    }
    if not apply:
        report["post_sha256"] = pre_sha
        if report_path is not None:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        return report

    if not expected_pre_sha256:
        raise MinimalSalesIdentitySchemaError(
            "--expected-pre-sha256 is required with --apply"
        )
    if os.environ.get(WRITE_ENV_GATE) != "1":
        raise MinimalSalesIdentitySchemaError(f"{WRITE_ENV_GATE}=1 is required")
    if backup_dir is None:
        raise MinimalSalesIdentitySchemaError("--backup-dir is required with --apply")

    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = backup_dir / f"{db_path.stem}.before_minimal_identity_{pre_sha[:12]}_{stamp}.db"
    shutil.copy2(db_path, backup_path)
    if sha256_file(backup_path) != pre_sha or _integrity(backup_path).lower() != "ok":
        raise MinimalSalesIdentitySchemaError("byte-valid backup verification failed")

    conn = sqlite3.connect(str(db_path), isolation_level=None)
    traced_statements: list[str] = []
    conn.set_trace_callback(traced_statements.append)
    try:
        conn.execute("BEGIN IMMEDIATE")
        locked_plan = _schema_plan(conn)
        if locked_plan["columns_to_add"] != plan["columns_to_add"] or [
            (item["table"], item["index"])
            for item in locked_plan["indexes_to_add"]
        ] != [
            (item["table"], item["index"])
            for item in plan["indexes_to_add"]
        ]:
            raise MinimalSalesIdentitySchemaError("schema plan drifted after write lock")
        locked_schema_objects = _schema_objects(conn)
        if locked_schema_objects != schema_objects_before:
            raise MinimalSalesIdentitySchemaError(
                "schema objects drifted after preflight and before write lock"
            )

        install_minimal_publication_schema(conn)

        final_plan = _schema_plan(conn)
        if final_plan["columns_to_add"] or final_plan["indexes_to_add"]:
            raise MinimalSalesIdentitySchemaError("schema bootstrap is incomplete")
        exact_contract = build_minimal_publication_schema_contract(conn)
        require_minimal_publication_schema(exact_contract)
        original_hashes_after = {
            table: _projection_hash(conn, table, columns)
            for table, columns in plan["original_columns"].items()
        }
        if original_hashes_after != original_hashes_before:
            raise MinimalSalesIdentitySchemaError(
                "pre-existing table projection changed during schema bootstrap"
            )
        identity_fingerprints_after = _fact_orders_identity_fingerprints(conn)
        if identity_fingerprints_after != identity_fingerprints_before:
            raise MinimalSalesIdentitySchemaError(
                "fact_orders_kaspi article identity changed during schema bootstrap"
            )
        schema_objects_after = _schema_objects(conn)
        changed_schema_objects = _changed_schema_objects(
            schema_objects_before, schema_objects_after
        )
        if changed_schema_objects != planned_changed_schema_objects:
            raise MinimalSalesIdentitySchemaError(
                "schema-object delta differs from exact bootstrap plan: "
                f"planned={planned_changed_schema_objects}, observed={changed_schema_objects}"
            )

        replay_schema_before = _schema_objects(conn)
        replay_hashes_before = original_hashes_after
        replay_identity_before = identity_fingerprints_after
        install_minimal_publication_schema(conn)
        replay_plan = _schema_plan(conn)
        replay_schema_after = _schema_objects(conn)
        replay_hashes_after = {
            table: _projection_hash(conn, table, columns)
            for table, columns in plan["original_columns"].items()
        }
        replay_identity_after = _fact_orders_identity_fingerprints(conn)
        idempotent_schema_delta = _changed_schema_objects(
            replay_schema_before, replay_schema_after
        )
        idempotent_replay = bool(
            not replay_plan["columns_to_add"]
            and not replay_plan["indexes_to_add"]
            and not idempotent_schema_delta
            and replay_hashes_before == replay_hashes_after
            and replay_identity_before == replay_identity_after
        )
        if not idempotent_replay:
            raise MinimalSalesIdentitySchemaError(
                "minimal schema bootstrap is not logically idempotent"
            )
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity.lower() != "ok":
            raise MinimalSalesIdentitySchemaError(
                f"post-apply integrity_check failed: {integrity}"
            )
        conn.execute("COMMIT")
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.set_trace_callback(None)
        conn.close()

    data_statements = [
        statement
        for statement in traced_statements
        if statement.lstrip().upper().startswith(("UPDATE ", "INSERT ", "DELETE ", "REPLACE "))
    ]
    if data_statements:
        raise MinimalSalesIdentitySchemaError(
            "minimal schema bootstrap executed a forbidden data statement"
        )

    post_sha = sha256_file(db_path)
    rollback = {
        "operation": "RESTORE_PREWRITE_DB_BACKUP",
        "target_path": str(db_path),
        "target_post_sha256": post_sha,
        "backup_path": str(backup_path),
        "backup_sha256": pre_sha,
        "command": f"cp -p {json.dumps(str(backup_path))} {json.dumps(str(db_path))}",
    }
    rollback_path = backup_dir / f"ROLLBACK_MINIMAL_SALES_IDENTITY_{stamp}.json"
    rollback_path.write_text(
        json.dumps(rollback, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report.update(
        {
            "write_applied": True,
            "backup_path": str(backup_path),
            "backup_sha256": pre_sha,
            "rollback_path": str(rollback_path),
            "original_projection_hashes_after": original_hashes_after,
            "fact_orders_identity_fingerprints_after": identity_fingerprints_after,
            "schema_objects_after": schema_objects_after,
            "changed_schema_objects": changed_schema_objects,
            "minimal_publication_schema_contract": exact_contract,
            "data_update_statement_count": len(data_statements),
            "idempotent_replay": idempotent_replay,
            "idempotent_schema_delta": idempotent_schema_delta,
            "integrity_check": integrity,
            "post_sha256": post_sha,
        }
    )
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--expected-pre-sha256")
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = apply_minimal_schema(
            db_path=args.db,
            expected_pre_sha256=args.expected_pre_sha256,
            backup_dir=args.backup_dir,
            report_path=args.report,
            apply=bool(args.apply),
        )
    except (MinimalSalesIdentitySchemaError, OSError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": report["status"],
                "mode": report["mode"],
                "write_applied": report["write_applied"],
                "post_sha256": report["post_sha256"],
                "migration031_non_target_normalizations_performed": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
