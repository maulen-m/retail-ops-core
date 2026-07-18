"""Minimal additive schema required by governed sales publication bindings."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any


CONTRACT_SCHEMA_VERSION = "minimal_sales_publication_schema_contract_v1"

COLUMNS: dict[str, dict[str, str]] = {
    "fact_orders_kaspi": {"source_entry_id": "TEXT"},
    "sales_fact_v2": {
        "source_entry_id": "TEXT",
        "kaspi_article": "TEXT",
        "line_identity_key": "TEXT",
    },
    "fact_sales": {
        "source_entry_id": "TEXT",
        "kaspi_article": "TEXT",
        "line_identity_key": "TEXT",
    },
}

REQUIRED_PREEXISTING_COLUMNS: dict[str, set[str]] = {
    "fact_orders_kaspi": {
        "id",
        "order_id",
        "store_code",
        "kaspi_article",
        "line_identity_key",
    },
    "sales_fact_v2": {"sale_id", "order_id", "store_code"},
    "fact_sales": {"id", "order_id", "store_code"},
}

# Reuse migration 031's canonical entry-index identities without running its
# broad article/stock schema or its legacy line-identity normalization.
INDEXES = {
    "fact_orders_kaspi": "ux_fact_orders_kaspi_source_entry_id",
    "sales_fact_v2": "ux_sales_fact_v2_source_entry_id",
    "fact_sales": "ux_fact_sales_source_entry_id",
}


class MinimalPublicationSchemaError(RuntimeError):
    pass


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalized_sql(sql: str) -> str:
    return " ".join(sql.upper().replace('"', "").split())


def expected_index_sql(table: str, index_name: str) -> str:
    return f"""
        CREATE UNIQUE INDEX {_quote(index_name)}
        ON {_quote(table)} (TRIM(source_entry_id))
        WHERE TRIM(COALESCE(source_entry_id, '')) <> ''
    """


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _column_metadata(conn: sqlite3.Connection, table: str) -> dict[str, dict[str, Any]]:
    return {
        str(row[1]): {
            "name": str(row[1]),
            "type": str(row[2] or "").upper(),
            "notnull": int(row[3]),
            "default": row[4],
            "pk": int(row[5]),
        }
        for row in conn.execute(f"PRAGMA table_info({_quote(table)})").fetchall()
    }


def _index_sql(conn: sqlite3.Connection, name: str) -> str | None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
        (name,),
    ).fetchone()
    return None if row is None or row[0] is None else str(row[0])


def _duplicate_source_entry_groups(conn: sqlite3.Connection, table: str) -> int:
    columns = _column_metadata(conn, table)
    if "source_entry_id" not in columns:
        return 0
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


def build_minimal_publication_schema_contract(
    conn: sqlite3.Connection,
) -> dict[str, Any]:
    """Capture exact required column/index state without mutating the DB."""

    table_state: dict[str, Any] = {}
    errors: list[str] = []
    for table, required_additions in COLUMNS.items():
        if not _table_exists(conn, table):
            errors.append(f"missing table: {table}")
            table_state[table] = {"present": False}
            continue
        metadata = _column_metadata(conn, table)
        missing_base = sorted(REQUIRED_PREEXISTING_COLUMNS[table] - set(metadata))
        if missing_base:
            errors.append(f"missing pre-existing columns {table}: {missing_base}")
        required_columns: dict[str, Any] = {}
        for column, declaration in required_additions.items():
            observed = metadata.get(column)
            expected = {
                "name": column,
                "type": declaration,
                "notnull": 0,
                "default": None,
                "pk": 0,
            }
            matches = observed == expected
            if not matches:
                errors.append(f"missing/wrong required column: {table}.{column}")
            required_columns[column] = {
                "expected": expected,
                "observed": observed,
                "matches": matches,
            }

        index_name = INDEXES[table]
        raw_index_sql = _index_sql(conn, index_name)
        expected_sql = expected_index_sql(table, index_name)
        index_matches = bool(
            raw_index_sql
            and _normalized_sql(raw_index_sql) == _normalized_sql(expected_sql)
        )
        if not index_matches:
            errors.append(f"missing/wrong required index: {index_name}")
        duplicate_groups = _duplicate_source_entry_groups(conn, table)
        if duplicate_groups:
            errors.append(
                f"duplicate nonblank source_entry_id groups: {table}={duplicate_groups}"
            )
        table_state[table] = {
            "present": True,
            "required_columns": required_columns,
            "source_entry_index": {
                "name": index_name,
                "raw_sql": raw_index_sql,
                "raw_sql_sha256": (
                    None
                    if raw_index_sql is None
                    else hashlib.sha256(raw_index_sql.encode("utf-8")).hexdigest()
                ),
                "expected_normalized_sql": _normalized_sql(expected_sql),
                "matches": index_matches,
            },
            "duplicate_nonblank_source_entry_groups": duplicate_groups,
        }

    body: dict[str, Any] = {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "required_column_count": sum(len(columns) for columns in COLUMNS.values()),
        "required_index_count": len(INDEXES),
        "required_columns": [
            {"table": table, "column": column, "declaration": declaration}
            for table, columns in COLUMNS.items()
            for column, declaration in columns.items()
        ],
        "required_indexes": [
            {"table": table, "index": index_name}
            for table, index_name in INDEXES.items()
        ],
        "tables": table_state,
        "errors": errors,
        "compatible": not errors,
    }
    body["contract_sha256"] = _canonical_sha256(body)
    return body


def _validate_contract_hash(contract: dict[str, Any]) -> None:
    if contract.get("schema_version") != CONTRACT_SCHEMA_VERSION:
        raise MinimalPublicationSchemaError(
            "unsupported minimal publication schema contract"
        )
    expected = str(contract.get("contract_sha256") or "")
    body = dict(contract)
    body.pop("contract_sha256", None)
    if not expected or _canonical_sha256(body) != expected:
        raise MinimalPublicationSchemaError(
            "minimal publication schema contract internal hash mismatch"
        )


def require_minimal_publication_schema(contract: dict[str, Any]) -> None:
    _validate_contract_hash(contract)
    if not bool(contract.get("compatible")):
        raise MinimalPublicationSchemaError(
            "minimal publication schema is not exact: "
            + "; ".join(str(item) for item in contract.get("errors") or [])
        )


def require_matching_minimal_publication_schema(
    conn: sqlite3.Connection,
    *,
    pinned_contract: dict[str, Any],
) -> dict[str, Any]:
    _validate_contract_hash(pinned_contract)
    current = build_minimal_publication_schema_contract(conn)
    require_minimal_publication_schema(current)
    if current["contract_sha256"] != pinned_contract.get("contract_sha256"):
        raise MinimalPublicationSchemaError(
            "minimal publication prerequisite differs from reviewed manifest; "
            "refresh copied baseline, regenerate manifest, and re-review before apply"
        )
    return current


def install_minimal_publication_schema(conn: sqlite3.Connection) -> None:
    """Install exactly the seven columns and canonical three entry indexes."""

    for table, required in REQUIRED_PREEXISTING_COLUMNS.items():
        if not _table_exists(conn, table):
            raise MinimalPublicationSchemaError(f"missing required table: {table}")
        metadata = _column_metadata(conn, table)
        missing = required - set(metadata)
        if missing:
            raise MinimalPublicationSchemaError(
                f"missing pre-existing columns from {table}: {sorted(missing)}"
            )

    for table, columns in COLUMNS.items():
        metadata = _column_metadata(conn, table)
        for column, declaration in columns.items():
            if column not in metadata:
                conn.execute(
                    f"ALTER TABLE {_quote(table)} "
                    f"ADD COLUMN {_quote(column)} {declaration}"
                )
            else:
                expected = {
                    "name": column,
                    "type": declaration,
                    "notnull": 0,
                    "default": None,
                    "pk": 0,
                }
                if metadata[column] != expected:
                    raise MinimalPublicationSchemaError(
                        f"wrong existing definition: {table}.{column}"
                    )

    for table, index_name in INDEXES.items():
        duplicates = _duplicate_source_entry_groups(conn, table)
        if duplicates:
            raise MinimalPublicationSchemaError(
                f"duplicate nonblank source_entry_id groups: {table}={duplicates}"
            )
        observed_sql = _index_sql(conn, index_name)
        expected_sql = expected_index_sql(table, index_name)
        if observed_sql is None:
            conn.execute(expected_sql)
        elif _normalized_sql(observed_sql) != _normalized_sql(expected_sql):
            raise MinimalPublicationSchemaError(
                f"wrong existing index definition: {index_name}"
            )

    require_minimal_publication_schema(
        build_minimal_publication_schema_contract(conn)
    )
