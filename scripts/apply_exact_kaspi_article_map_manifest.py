#!/usr/bin/env python3
"""Apply a SHA-pinned exact ``dim_kaspi_article_map`` manifest.

Dry-run is the default and opens the target database read-only. Apply mode is
limited to manifest-listed inserts/updates, requires an environment gate, an
exact manifest hash, an exact pre-write DB hash, and a backup directory.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any


ENV_GATE = "ENABLE_KASPI_ARTICLE_MAP_MANIFEST_WRITE"
TABLE = "dim_kaspi_article_map"
KEY_FIELDS = ("store_code", "kaspi_article")
WRITABLE_FIELDS = (
    "store_code",
    "merchant_id",
    "kaspi_article",
    "kaspi_offer_name",
    "kaspi_name_core",
    "sku_key",
    "sku_id",
    "model",
    "brand",
    "source",
    "active_flag",
)


class ExactArticleMapManifestError(RuntimeError):
    """Raised when a manifest or DB stopline is not satisfied."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def _row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _fetch_target(
    conn: sqlite3.Connection, store_code: str, kaspi_article: str
) -> dict[str, Any] | None:
    rows = conn.execute(
        f"SELECT * FROM {TABLE} WHERE store_code=? AND kaspi_article=? ORDER BY id",
        (store_code, kaspi_article),
    ).fetchall()
    if len(rows) > 1:
        raise ExactArticleMapManifestError(
            f"duplicate target rows for {store_code}/{kaspi_article}: {len(rows)}"
        )
    return _row_dict(rows[0]) if rows else None


def _normalized_existing(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {field: row.get(field) for field in WRITABLE_FIELDS}


def _canonical_rows_hash(
    conn: sqlite3.Connection, excluded_keys: set[tuple[str, str]]
) -> str:
    rows = conn.execute(f"SELECT * FROM {TABLE} ORDER BY store_code, kaspi_article, id").fetchall()
    payload = [
        dict(row)
        for row in rows
        if (str(row["store_code"]), str(row["kaspi_article"])) not in excluded_keys
    ]
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_manifest(path: Path, expected_sha256: str) -> dict[str, Any]:
    if not path.is_file():
        raise ExactArticleMapManifestError(f"manifest not found: {path}")
    observed_sha = sha256_file(path)
    if observed_sha != expected_sha256:
        raise ExactArticleMapManifestError(
            f"manifest SHA mismatch: expected={expected_sha256} observed={observed_sha}"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ExactArticleMapManifestError("manifest schema_version must be 1")
    if payload.get("operation") != "EXACT_DIM_KASPI_ARTICLE_MAP_UPSERT":
        raise ExactArticleMapManifestError("unsupported manifest operation")
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ExactArticleMapManifestError("manifest rows must be a non-empty list")
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(rows):
        if not isinstance(item, dict) or "old_row" not in item or "new_row" not in item:
            raise ExactArticleMapManifestError(f"row {index} lacks old_row/new_row")
        new_row = item["new_row"]
        if not isinstance(new_row, dict):
            raise ExactArticleMapManifestError(f"row {index} new_row must be an object")
        missing = [field for field in WRITABLE_FIELDS if field not in new_row]
        extras = sorted(set(new_row) - set(WRITABLE_FIELDS))
        if missing or extras:
            raise ExactArticleMapManifestError(
                f"row {index} field mismatch: missing={missing} extras={extras}"
            )
        key = tuple(_clean(new_row.get(field)) for field in KEY_FIELDS)
        if not all(key):
            raise ExactArticleMapManifestError(f"row {index} has a blank target key")
        if key in seen:
            raise ExactArticleMapManifestError(f"duplicate manifest target: {key}")
        seen.add(key)
        if int(new_row.get("active_flag") or 0) != 1:
            raise ExactArticleMapManifestError(f"row {index} must remain active_flag=1")
        if not _clean(new_row.get("kaspi_name_core")):
            raise ExactArticleMapManifestError(f"row {index} lacks kaspi_name_core")
        if not _clean(new_row.get("sku_key")) or not _clean(new_row.get("sku_id")):
            raise ExactArticleMapManifestError(f"row {index} lacks exact sku_key/sku_id")
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or len(evidence) < 2:
            raise ExactArticleMapManifestError(
                f"row {index} requires at least two evidence records"
            )
        for evidence_index, record in enumerate(evidence):
            if not isinstance(record, dict) or not _clean(record.get("source")):
                raise ExactArticleMapManifestError(
                    f"row {index} evidence {evidence_index} lacks source"
                )
            source_path = _clean(record.get("path"))
            source_sha = _clean(record.get("sha256"))
            if source_path:
                candidate = Path(source_path).expanduser()
                if not candidate.is_file():
                    raise ExactArticleMapManifestError(
                        f"row {index} evidence path missing: {candidate}"
                    )
                if source_sha and sha256_file(candidate) != source_sha:
                    raise ExactArticleMapManifestError(
                        f"row {index} evidence SHA mismatch: {candidate}"
                    )
    return payload


def _validate_database_shape(conn: sqlite3.Connection) -> None:
    required_tables = {"dim_store", "dim_sku", "dim_sku_size", TABLE}
    present = {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    missing = sorted(required_tables - present)
    if missing:
        raise ExactArticleMapManifestError(f"required DB tables missing: {missing}")
    columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({TABLE})")}
    required_columns = set(WRITABLE_FIELDS) | {"id", "created_at", "updated_at"}
    missing_columns = sorted(required_columns - columns)
    if missing_columns:
        raise ExactArticleMapManifestError(
            f"{TABLE} columns missing: {missing_columns}"
        )


def _validate_target_identity(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    store = conn.execute(
        "SELECT active_flag FROM dim_store WHERE store_code=?", (row["store_code"],)
    ).fetchone()
    if store is None or int(store[0] or 0) != 1:
        raise ExactArticleMapManifestError(
            f"inactive or missing store: {row['store_code']}"
        )
    sku = conn.execute(
        "SELECT active_flag FROM dim_sku WHERE sku_key=?", (row["sku_key"],)
    ).fetchone()
    if sku is None or int(sku[0] or 0) != 1:
        raise ExactArticleMapManifestError(f"inactive or missing sku_key: {row['sku_key']}")
    size = conn.execute(
        "SELECT sku_key, active_flag FROM dim_sku_size WHERE sku_id=?",
        (row["sku_id"],),
    ).fetchone()
    if size is None or str(size[0]) != str(row["sku_key"]) or int(size[1] or 0) != 1:
        raise ExactArticleMapManifestError(
            f"sku_id is missing, inactive, or belongs to another sku_key: {row['sku_id']}"
        )


def _sqlite_backup(source: sqlite3.Connection, backup_path: Path) -> None:
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    if backup_path.exists():
        raise ExactArticleMapManifestError(f"backup already exists: {backup_path}")
    destination = sqlite3.connect(str(backup_path))
    try:
        source.backup(destination)
        check = destination.execute("PRAGMA integrity_check").fetchone()
        if check is None or str(check[0]).lower() != "ok":
            raise ExactArticleMapManifestError(
                f"backup integrity_check failed: {check[0] if check else 'missing'}"
            )
    finally:
        destination.close()


def _foreign_key_check(conn: sqlite3.Connection) -> tuple[str, list[dict[str, Any]], str]:
    try:
        errors = [dict(row) for row in conn.execute("PRAGMA foreign_key_check")]
    except sqlite3.OperationalError as exc:
        message = str(exc)
        known = 'foreign key mismatch - "fact_po_execution" referencing "fact_po_lines"'
        if message != known:
            raise ExactArticleMapManifestError(
                f"foreign_key_check could not run: {message}"
            ) from exc
        return "UNAVAILABLE_PREEXISTING_PO_SCHEMA_MISMATCH", [], message
    if errors:
        raise ExactArticleMapManifestError(
            f"foreign_key_check failed: {errors[:5]}"
        )
    return "PASS", [], ""


def _upsert(conn: sqlite3.Connection, row: dict[str, Any]) -> str:
    existing = _fetch_target(conn, row["store_code"], row["kaspi_article"])
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    if existing is None:
        columns = [*WRITABLE_FIELDS, "created_at", "updated_at"]
        values = [row[field] for field in WRITABLE_FIELDS] + [now, now]
        conn.execute(
            f"INSERT INTO {TABLE} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
            values,
        )
        return "INSERT"
    assignments = [f"{field}=?" for field in WRITABLE_FIELDS] + ["updated_at=?"]
    conn.execute(
        f"UPDATE {TABLE} SET {', '.join(assignments)} WHERE id=?",
        [*[row[field] for field in WRITABLE_FIELDS], now, existing["id"]],
    )
    return "UPDATE"


def run(
    *,
    db_path: Path,
    manifest_path: Path,
    expected_manifest_sha256: str,
    output_path: Path,
    apply: bool,
    expected_pre_sha256: str = "",
    backup_dir: Path | None = None,
) -> dict[str, Any]:
    db_path = db_path.expanduser().resolve()
    manifest_path = manifest_path.expanduser().resolve()
    expected_manifest_sha256 = expected_manifest_sha256.strip().lower()
    if len(expected_manifest_sha256) != 64:
        raise ExactArticleMapManifestError("a 64-character manifest SHA-256 is required")
    manifest = _validate_manifest(manifest_path, expected_manifest_sha256)
    if not db_path.is_file():
        raise ExactArticleMapManifestError(f"DB not found: {db_path}")
    if apply:
        if os.environ.get(ENV_GATE) != "1":
            raise ExactArticleMapManifestError(f"{ENV_GATE}=1 is required with --apply")
        if len(expected_pre_sha256.strip()) != 64:
            raise ExactArticleMapManifestError(
                "--expected-pre-sha256 is required with --apply"
            )
        observed_pre_sha = sha256_file(db_path)
        if observed_pre_sha != expected_pre_sha256.strip().lower():
            raise ExactArticleMapManifestError(
                f"DB pre-SHA mismatch: expected={expected_pre_sha256} observed={observed_pre_sha}"
            )
        if backup_dir is None:
            raise ExactArticleMapManifestError("--backup-dir is required with --apply")
        conn = sqlite3.connect(str(db_path))
    else:
        observed_pre_sha = sha256_file(db_path)
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    target_keys = {
        (str(item["new_row"]["store_code"]), str(item["new_row"]["kaspi_article"]))
        for item in manifest["rows"]
    }
    backup_path: Path | None = None
    changes: list[dict[str, Any]] = []
    try:
        _validate_database_shape(conn)
        before_count = int(conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0])
        before_non_target_hash = _canonical_rows_hash(conn, target_keys)
        before_rows: list[dict[str, Any] | None] = []
        for item in manifest["rows"]:
            row = item["new_row"]
            _validate_target_identity(conn, row)
            existing = _fetch_target(conn, row["store_code"], row["kaspi_article"])
            observed_old = _normalized_existing(existing)
            if observed_old != item["old_row"]:
                raise ExactArticleMapManifestError(
                    f"old_row mismatch for {row['store_code']}/{row['kaspi_article']}: "
                    f"expected={item['old_row']} observed={observed_old}"
                )
            before_rows.append(existing)

        if apply:
            timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir.expanduser().resolve() / (
                f"{db_path.stem}.pre_exact_article_map_{timestamp}{db_path.suffix}"
            )
            _sqlite_backup(conn, backup_path)
            conn.execute("BEGIN IMMEDIATE")
            locked_pre_sha = sha256_file(db_path)
            if locked_pre_sha != observed_pre_sha:
                raise ExactArticleMapManifestError(
                    "DB file changed between backup and write-lock acquisition"
                )
            locked_non_target_hash = _canonical_rows_hash(conn, target_keys)
            if locked_non_target_hash != before_non_target_hash:
                raise ExactArticleMapManifestError(
                    "non-target article-map state changed before write-lock acquisition"
                )
            for item, expected_before in zip(
                manifest["rows"], before_rows, strict=True
            ):
                row = item["new_row"]
                locked_before = _fetch_target(
                    conn, row["store_code"], row["kaspi_article"]
                )
                if _normalized_existing(locked_before) != _normalized_existing(
                    expected_before
                ):
                    raise ExactArticleMapManifestError(
                        f"target changed before write-lock acquisition: "
                        f"{row['store_code']}/{row['kaspi_article']}"
                    )
            for item in manifest["rows"]:
                row = item["new_row"]
                action = _upsert(conn, row)
                changes.append(
                    {
                        "action": action,
                        "store_code": row["store_code"],
                        "kaspi_article": row["kaspi_article"],
                    }
                )

        after_rows = [
            _fetch_target(
                conn, item["new_row"]["store_code"], item["new_row"]["kaspi_article"]
            )
            for item in manifest["rows"]
        ]
        if apply:
            for item, observed in zip(manifest["rows"], after_rows, strict=True):
                if _normalized_existing(observed) != item["new_row"]:
                    raise ExactArticleMapManifestError(
                        f"post-write row mismatch for {item['new_row']['store_code']}/"
                        f"{item['new_row']['kaspi_article']}"
                    )
        after_count = int(conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0])
        after_non_target_hash = _canonical_rows_hash(conn, target_keys)
        if before_non_target_hash != after_non_target_hash:
            raise ExactArticleMapManifestError("non-target article-map hash changed")
        expected_delta = sum(1 for row in before_rows if row is None) if apply else 0
        if after_count != before_count + expected_delta:
            raise ExactArticleMapManifestError(
                f"article-map count mismatch: before={before_count} after={after_count} "
                f"expected_delta={expected_delta}"
            )
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or str(integrity[0]).lower() != "ok":
            raise ExactArticleMapManifestError("production integrity_check failed")
        foreign_key_status, foreign_key_errors, foreign_key_error = _foreign_key_check(conn)
        if apply:
            conn.commit()
    except Exception:
        if apply:
            conn.rollback()
        raise
    finally:
        conn.close()

    observed_post_sha = sha256_file(db_path)
    report = {
        "schema_version": 1,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": "APPLIED" if apply else "DRY_RUN_VALID",
        "db_path": str(db_path),
        "db_pre_sha256": observed_pre_sha,
        "db_post_sha256": observed_post_sha,
        "manifest_path": str(manifest_path),
        "manifest_sha256": expected_manifest_sha256,
        "target_count": len(manifest["rows"]),
        "before_table_count": before_count,
        "after_table_count": after_count,
        "before_non_target_hash": before_non_target_hash,
        "after_non_target_hash": after_non_target_hash,
        "before_rows": before_rows,
        "after_rows": after_rows,
        "changes": changes,
        "backup_path": str(backup_path) if backup_path else "",
        "backup_sha256": sha256_file(backup_path) if backup_path else "",
        "integrity_check": "ok",
        "foreign_key_check_status": foreign_key_status,
        "foreign_key_check_count": len(foreign_key_errors),
        "foreign_key_check_error": foreign_key_error,
        "rollback_command": (
            f"cp '{backup_path}' '{db_path}'" if backup_path is not None else ""
        ),
    }
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-pre-sha256", default="")
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    report = run(
        db_path=args.db,
        manifest_path=args.manifest,
        expected_manifest_sha256=args.expected_manifest_sha256,
        output_path=args.output,
        apply=bool(args.apply),
        expected_pre_sha256=args.expected_pre_sha256,
        backup_dir=args.backup_dir,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
