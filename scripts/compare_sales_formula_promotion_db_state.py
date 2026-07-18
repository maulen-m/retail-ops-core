#!/usr/bin/env python3
"""Compare a formula-sidecar copied-DB promotion without exposing row data."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(PROJECT_ROOT))

from scripts.apply_sales_formula_provenance_sidecar import _target_matches_proof  # noqa: E402
from scripts.build_crm_formula_provenance_sidecar import validate_manifest  # noqa: E402
from scripts.build_sales_formula_provenance_sidecar import (  # noqa: E402
    ProvenanceError,
    _canonical_hash,
    _clean,
    _db_row_payload,
    _json_bytes,
    _load_jsonl,
    _write_atomic,
    sha256_file,
)


TARGET_TABLE = "sales_fact_v2"
ALLOWED_TARGET_COLUMNS = {"delivery_fee", "net_rev", "profit"}


class CompareError(RuntimeError):
    """Raised when the comparison cannot prove the requested state."""


def _normal(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"blob_sha256": hashlib.sha256(value).hexdigest(), "length": len(value)}
    return value


def _connect(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise CompareError(f"database missing: {path}")
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _schemas(conn: sqlite3.Connection) -> dict[str, str]:
    return {
        str(row[0]): str(row[1] or "")
        for row in conn.execute(
            """
            SELECT name, sql FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        )
    }


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    result = [str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')]
    if not result:
        raise CompareError(f"table has no columns: {table}")
    return result


def _logical_state(
    conn: sqlite3.Connection,
    table: str,
    *,
    excluded_sale_ids: set[int] | None = None,
) -> dict[str, Any]:
    columns = _columns(conn, table)
    quoted = ",".join(f'"{column}"' for column in columns)
    order = ",".join(f'"{column}"' for column in columns)
    params: tuple[Any, ...] = ()
    where = ""
    if table == TARGET_TABLE and excluded_sale_ids:
        placeholders = ",".join("?" for _ in excluded_sale_ids)
        where = f" WHERE sale_id NOT IN ({placeholders})"
        params = tuple(sorted(excluded_sale_ids))
    digest = hashlib.sha256()
    count = 0
    for row in conn.execute(f'SELECT {quoted} FROM "{table}"{where} ORDER BY {order}', params):
        payload = [_normal(row[column]) for column in columns]
        digest.update(
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        )
        digest.update(b"\n")
        count += 1
    return {"row_count": count, "logical_sha256": digest.hexdigest()}


def _rows_by_sale_id(
    conn: sqlite3.Connection,
    sale_ids: list[int],
) -> dict[int, dict[str, Any]]:
    if not sale_ids:
        return {}
    placeholders = ",".join("?" for _ in sale_ids)
    return {
        int(row["sale_id"]): dict(row)
        for row in conn.execute(
            f"SELECT * FROM sales_fact_v2 WHERE sale_id IN ({placeholders}) ORDER BY sale_id",
            tuple(sale_ids),
        )
    }


def compare(
    *,
    before_path: Path,
    after_path: Path,
    manifest_path: Path,
    expected_manifest_sha256: str,
    mode: str,
) -> dict[str, Any]:
    if mode not in {"baseline", "applied"}:
        raise CompareError(f"unsupported mode: {mode}")
    validation = validate_manifest(manifest_path.resolve())
    if not validation.get("ok"):
        raise CompareError(f"CRM manifest validation failed: {validation.get('errors')}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if _clean(manifest.get("manifest_sha256")) != _clean(expected_manifest_sha256):
        raise CompareError("manifest SHA-256 mismatch")
    proofs = _load_jsonl(Path(manifest["proof_path"]))
    proof_by_sale_id = {int(row["sale_id"]): row for row in proofs}
    if len(proof_by_sale_id) != len(proofs):
        raise CompareError("duplicate proof sale_id")
    sale_ids = sorted(proof_by_sale_id)
    target_set = set(sale_ids)

    before = _connect(before_path.resolve())
    after = _connect(after_path.resolve())
    try:
        before_schemas = _schemas(before)
        after_schemas = _schemas(after)
        missing_after = sorted(set(before_schemas) - set(after_schemas))
        added_after = sorted(set(after_schemas) - set(before_schemas))
        schema_mismatches = sorted(
            table
            for table in set(before_schemas) & set(after_schemas)
            if before_schemas[table] != after_schemas[table]
        )
        common = sorted(set(before_schemas) & set(after_schemas))
        before_states = {table: _logical_state(before, table) for table in common}
        after_states = {table: _logical_state(after, table) for table in common}
        other_table_mismatches = sorted(
            table
            for table in common
            if table != TARGET_TABLE and before_states[table] != after_states[table]
        )
        non_target_before = _logical_state(
            before, TARGET_TABLE, excluded_sale_ids=target_set
        )
        non_target_after = _logical_state(
            after, TARGET_TABLE, excluded_sale_ids=target_set
        )
        before_targets = _rows_by_sale_id(before, sale_ids)
        after_targets = _rows_by_sale_id(after, sale_ids)
        missing_before_targets = sorted(target_set - set(before_targets))
        missing_after_targets = sorted(target_set - set(after_targets))
        preimage_mismatches: list[int] = []
        expected_readback_mismatches: list[int] = []
        unexpected_column_mismatches: dict[str, list[str]] = {}
        changed_target_ids: list[int] = []
        for sale_id in sale_ids:
            old = before_targets.get(sale_id)
            new = after_targets.get(sale_id)
            if old is None or new is None:
                continue
            proof = proof_by_sale_id[sale_id]
            if _db_row_payload(old) != proof.get("db_row"):
                preimage_mismatches.append(sale_id)
            changed_columns = sorted(
                column for column in old if _normal(old[column]) != _normal(new[column])
            )
            if changed_columns:
                changed_target_ids.append(sale_id)
            unexpected = sorted(set(changed_columns) - ALLOWED_TARGET_COLUMNS)
            if unexpected:
                unexpected_column_mismatches[str(sale_id)] = unexpected
            if mode == "applied" and not _target_matches_proof(new, proof):
                expected_readback_mismatches.append(sale_id)

        integrity = {
            "before": str(before.execute("PRAGMA integrity_check").fetchone()[0]),
            "after": str(after.execute("PRAGMA integrity_check").fetchone()[0]),
            "before_quick": str(before.execute("PRAGMA quick_check").fetchone()[0]),
            "after_quick": str(after.execute("PRAGMA quick_check").fetchone()[0]),
        }
        exact_target_change = (
            not changed_target_ids
            if mode == "baseline"
            else set(changed_target_ids) == target_set
        )
        ok = bool(
            not missing_after
            and not added_after
            and not schema_mismatches
            and not other_table_mismatches
            and non_target_before == non_target_after
            and not missing_before_targets
            and not missing_after_targets
            and not preimage_mismatches
            and not expected_readback_mismatches
            and not unexpected_column_mismatches
            and exact_target_change
            and set(integrity.values()) == {"ok"}
        )
        return {
            "schema": "sales_formula_promotion_logical_comparison_v1",
            "gate": "GREEN" if ok else "RED",
            "mode": mode,
            "manifest_path": str(manifest_path.resolve()),
            "manifest_sha256": _clean(manifest.get("manifest_sha256")),
            "before": {"path": str(before_path.resolve()), "sha256": sha256_file(before_path)},
            "after": {"path": str(after_path.resolve()), "sha256": sha256_file(after_path)},
            "application_table_count": len(common),
            "table_states_before": before_states,
            "table_states_after": after_states,
            "missing_after": missing_after,
            "added_after": added_after,
            "schema_mismatches": schema_mismatches,
            "other_table_logical_mismatches": other_table_mismatches,
            "target_count": len(sale_ids),
            "changed_target_count": len(changed_target_ids),
            "changed_target_ids_sha256": _canonical_hash(sorted(changed_target_ids)),
            "exact_target_change": exact_target_change,
            "missing_before_target_count": len(missing_before_targets),
            "missing_after_target_count": len(missing_after_targets),
            "preimage_mismatch_count": len(preimage_mismatches),
            "expected_readback_mismatch_count": len(expected_readback_mismatches),
            "unexpected_column_mismatch_count": len(unexpected_column_mismatches),
            "non_target_sales_before": non_target_before,
            "non_target_sales_after": non_target_after,
            "integrity": integrity,
        }
    finally:
        before.close()
        after.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--mode", choices=("baseline", "applied"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = compare(
            before_path=args.before,
            after_path=args.after,
            manifest_path=args.manifest,
            expected_manifest_sha256=args.expected_manifest_sha256,
            mode=args.mode,
        )
    except (OSError, ValueError, sqlite3.Error, ProvenanceError, CompareError) as exc:
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        return 1
    _write_atomic(args.output.resolve(), _json_bytes(report, pretty=True))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["gate"] == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
