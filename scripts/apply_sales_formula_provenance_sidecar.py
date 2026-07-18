#!/usr/bin/env python3
"""Promote a validated formula-provenance sidecar on a copied DB only.

The canonical production ``db/app.db`` is hard-refused. Dry-run is the
default; apply requires both ``--apply`` and
``AB_ALLOW_COPIED_DB_SALES_FORMULA_REPAIR=1``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(PROJECT_ROOT))

from scripts.build_sales_formula_provenance_sidecar import (  # noqa: E402
    ProvenanceError,
    _canonical_hash,
    _clean,
    _db_row_payload,
    _decimal,
    _json_bytes,
    _load_jsonl,
    _money,
    _money_text,
    _write_atomic,
    sha256_file,
    validate_manifest,
)


APPLY_GATE = "AB_ALLOW_COPIED_DB_SALES_FORMULA_REPAIR"
DEFAULT_PRODUCTION_DB = PROJECT_ROOT / "db" / "app.db"
TARGET_COLUMNS = (
    "sale_id",
    "order_id",
    "store_code",
    "order_date",
    "sku_key",
    "sku_id",
    "my_size",
    "quantity",
    "sell_price_kzt",
    "delivery_fee",
    "net_rev",
    "cogs",
    "profit",
    "source_file",
    "source_entry_id",
    "kaspi_article",
    "line_identity_key",
)


class SidecarApplyError(RuntimeError):
    """Raised when copied-DB promotion cannot prove its exact scope."""


def _same_file(left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except OSError:
        return left.resolve() == right.resolve()


def _query_target_row(conn: sqlite3.Connection, sale_id: int) -> dict[str, Any] | None:
    columns = ", ".join(TARGET_COLUMNS)
    row = conn.execute(
        f"SELECT {columns} FROM sales_fact_v2 WHERE sale_id = ?",
        (sale_id,),
    ).fetchone()
    return dict(row) if row is not None else None


def _table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    names = [
        str(row[0])
        for row in conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    ]
    return {name: int(conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]) for name in names}


def _non_target_sales_hash(conn: sqlite3.Connection, target_sale_ids: set[int]) -> str:
    columns = [str(row[1]) for row in conn.execute("PRAGMA table_info(sales_fact_v2)").fetchall()]
    if not columns:
        raise SidecarApplyError("sales_fact_v2 schema missing")
    if target_sale_ids:
        placeholders = ",".join("?" for _ in target_sale_ids)
        sql = f"SELECT * FROM sales_fact_v2 WHERE sale_id NOT IN ({placeholders}) ORDER BY sale_id"
        params: tuple[Any, ...] = tuple(sorted(target_sale_ids))
    else:
        sql = "SELECT * FROM sales_fact_v2 ORDER BY sale_id"
        params = ()
    rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
    return _canonical_hash({"columns": columns, "rows": rows})


def _expected_target_values(proof: dict[str, Any]) -> tuple[Decimal, Decimal, Decimal | None]:
    canonical_net = _money(
        _decimal(proof.get("canonical_line_net_rev_kzt"), field="canonical_line_net_rev_kzt")
    )
    seller_fee_total = _money(
        _decimal(proof.get("seller_delivery_fee_total_kzt"), field="seller_delivery_fee_total_kzt")
    )
    cogs = proof["db_row"].get("cogs")
    canonical_profit = (
        _money(canonical_net - _decimal(cogs, field="db.cogs"))
        if _clean(cogs)
        else None
    )
    return seller_fee_total, canonical_net, canonical_profit


def _target_matches_proof(actual: dict[str, Any], proof: dict[str, Any]) -> bool:
    expected_fee, expected_net, expected_profit = _expected_target_values(proof)
    actual_fee = _money(_decimal(actual.get("delivery_fee"), field="actual.delivery_fee"))
    actual_net = _money(_decimal(actual.get("net_rev"), field="actual.net_rev"))
    if expected_profit is None:
        profit_matches = actual.get("profit") is None
    else:
        profit_matches = _money(_decimal(actual.get("profit"), field="actual.profit")) == expected_profit
    return actual_fee == expected_fee and actual_net == expected_net and profit_matches


def promote_sidecar(
    *,
    manifest_path: Path,
    db_path: Path,
    expected_manifest_sha256: str,
    expected_db_sha256: str,
    apply: bool,
    backup_dir: Path | None = None,
    manifest_validator: Callable[[Path], dict[str, Any]] = validate_manifest,
) -> dict[str, Any]:
    manifest_path = manifest_path.expanduser().resolve()
    db_path = db_path.expanduser().resolve()
    production_db = DEFAULT_PRODUCTION_DB.resolve()
    if not db_path.exists():
        raise SidecarApplyError(f"DB not found: {db_path}")
    if _same_file(db_path, production_db):
        raise SidecarApplyError("canonical production db/app.db is hard-refused")
    if apply and os.environ.get(APPLY_GATE) != "1":
        raise SidecarApplyError(f"apply requires {APPLY_GATE}=1")
    if apply and backup_dir is None:
        raise SidecarApplyError("apply requires --backup-dir")

    validation = manifest_validator(manifest_path)
    if not validation.get("ok"):
        raise SidecarApplyError(f"sidecar validation failed: {validation.get('errors')}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if _clean(manifest.get("manifest_sha256")) != _clean(expected_manifest_sha256):
        raise SidecarApplyError("manifest SHA-256 mismatch")
    pre_sha256 = sha256_file(db_path)
    if pre_sha256 != _clean(expected_db_sha256) or pre_sha256 != _clean(manifest.get("db_sha256")):
        raise SidecarApplyError("copied DB SHA-256 mismatch")

    proofs = _load_jsonl(Path(_clean(manifest.get("proof_path"))))
    if not proofs:
        raise SidecarApplyError("sidecar has no proof rows")
    if any(not bool(row.get("repair_required")) for row in proofs):
        raise SidecarApplyError("sidecar contains a non-repair target")
    sale_ids = [int(row["sale_id"]) for row in proofs]
    if len(sale_ids) != len(set(sale_ids)):
        raise SidecarApplyError("duplicate target sale_id")
    target_sale_ids = set(sale_ids)

    backup_path: Path | None = None
    rollback_artifact_path: Path | None = None
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        if str(conn.execute("PRAGMA integrity_check").fetchone()[0]).lower() != "ok":
            raise SidecarApplyError("copied DB integrity check failed")
        triggers = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='sales_fact_v2'"
        ).fetchall()
        if triggers:
            raise SidecarApplyError("sales_fact_v2 table triggers are not permitted")
        table_counts_before = _table_counts(conn)
        non_target_hash_before = _non_target_sales_hash(conn, target_sale_ids)
        for proof in proofs:
            actual = _query_target_row(conn, int(proof["sale_id"]))
            if actual is None or _db_row_payload(actual) != proof.get("db_row"):
                raise SidecarApplyError(f"target preimage mismatch: sale_id={proof.get('sale_id')}")

    if apply:
        assert backup_dir is not None
        backup_dir = backup_dir.expanduser().resolve()
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup_path = backup_dir / f"app.pre_formula_sidecar_{pre_sha256[:12]}_{stamp}.db"
        shutil.copy2(db_path, backup_path)
        if sha256_file(backup_path) != pre_sha256:
            raise SidecarApplyError("backup SHA-256 mismatch")
        rollback_artifact_path = backup_dir / "PROMOTION_ROLLBACK.json"
        _write_atomic(
            rollback_artifact_path,
            _json_bytes(
                {
                    "schema": "sales_formula_provenance_promotion_rollback_v1",
                    "status": "READY_BEFORE_TRANSACTION",
                    "manifest_path": str(manifest_path),
                    "manifest_sha256": _clean(manifest.get("manifest_sha256")),
                    "target_count": len(proofs),
                    "db_path": str(db_path),
                    "db_pre_sha256": pre_sha256,
                    "backup_path": str(backup_path),
                    "backup_sha256": pre_sha256,
                    "rollback_command": f"cp {backup_path} {db_path}",
                },
                pretty=True,
            ),
        )

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")
            try:
                for proof in proofs:
                    actual = _query_target_row(conn, int(proof["sale_id"]))
                    if actual is None or _db_row_payload(actual) != proof.get("db_row"):
                        raise SidecarApplyError(
                            f"in-transaction target preimage mismatch: sale_id={proof.get('sale_id')}"
                        )
                for proof in proofs:
                    seller_fee_total, canonical_net, canonical_profit = _expected_target_values(proof)
                    cursor = conn.execute(
                        """
                        UPDATE sales_fact_v2
                        SET delivery_fee = ?, net_rev = ?, profit = ?
                        WHERE sale_id = ?
                        """,
                        (
                            float(seller_fee_total),
                            float(canonical_net),
                            float(canonical_profit) if canonical_profit is not None else None,
                            int(proof["sale_id"]),
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise SidecarApplyError(f"target update count mismatch: sale_id={proof.get('sale_id')}")
                if _table_counts(conn) != table_counts_before:
                    raise SidecarApplyError("in-transaction table counts changed")
                if _non_target_sales_hash(conn, target_sale_ids) != non_target_hash_before:
                    raise SidecarApplyError("in-transaction non-target rows changed")
                for proof in proofs:
                    actual = _query_target_row(conn, int(proof["sale_id"]))
                    if actual is None or not _target_matches_proof(actual, proof):
                        raise SidecarApplyError(
                            f"in-transaction target readback mismatch: sale_id={proof.get('sale_id')}"
                        )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        integrity_after = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        table_counts_after = _table_counts(conn)
        non_target_hash_after = _non_target_sales_hash(conn, target_sale_ids)
        target_mismatches: list[int] = []
        for proof in proofs:
            actual = _query_target_row(conn, int(proof["sale_id"]))
            if actual is None:
                target_mismatches.append(int(proof["sale_id"]))
                continue
            if apply and not _target_matches_proof(actual, proof):
                target_mismatches.append(int(proof["sale_id"]))

    post_sha256 = sha256_file(db_path)
    if integrity_after.lower() != "ok":
        raise SidecarApplyError("post-apply DB integrity check failed")
    if table_counts_before != table_counts_after:
        raise SidecarApplyError("table counts changed")
    if non_target_hash_before != non_target_hash_after:
        raise SidecarApplyError("non-target sales_fact_v2 rows changed")
    if target_mismatches:
        raise SidecarApplyError(f"target readback mismatch count={len(target_mismatches)}")
    if not apply and post_sha256 != pre_sha256:
        raise SidecarApplyError("dry-run changed copied DB bytes")

    return {
        "schema": "sales_formula_provenance_copied_db_promotion_v2",
        "mode": "APPLY" if apply else "DRY_RUN",
        "status": "PASS",
        "manifest_path": str(manifest_path),
        "manifest_sha256": _clean(manifest.get("manifest_sha256")),
        "db_path": str(db_path),
        "db_pre_sha256": pre_sha256,
        "db_post_sha256": post_sha256,
        "backup_path": str(backup_path) if backup_path else None,
        "backup_sha256": sha256_file(backup_path) if backup_path else None,
        "target_count": len(proofs),
        "target_readback_mismatch_count": len(target_mismatches),
        "non_target_sales_fact_v2_sha256_before": non_target_hash_before,
        "non_target_sales_fact_v2_sha256_after": non_target_hash_after,
        "table_counts_unchanged": table_counts_before == table_counts_after,
        "db_integrity": integrity_after,
        "rollback_command": f"cp {backup_path} {db_path}" if backup_path else None,
        "rollback_artifact_path": (
            str(rollback_artifact_path) if rollback_artifact_path else None
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--expected-db-sha256", required=True)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = promote_sidecar(
            manifest_path=args.manifest,
            db_path=args.db,
            expected_manifest_sha256=args.expected_manifest_sha256,
            expected_db_sha256=args.expected_db_sha256,
            apply=args.apply,
            backup_dir=args.backup_dir,
        )
    except (OSError, ValueError, sqlite3.Error, ProvenanceError, SidecarApplyError) as exc:
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        return 1
    if args.report:
        _write_atomic(args.report, _json_bytes(report, pretty=True))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
