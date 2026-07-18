#!/usr/bin/env python3
"""Build a deterministic copied-DB promotion manifest from an API sidecar.

The source sidecar proves inputs.  This separate manifest freezes exact
``sales_fact_v2`` preimages and proposed fee/net/profit postimages.  It is
copied-DB-only and contains no production writer or external-system action.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(PROJECT_ROOT))

from scripts.build_api_order_entry_formula_provenance_sidecar import (  # noqa: E402
    BUILD_VERSION as SOURCE_SCHEMA,
    _canonical_bytes,
    _canonical_hash,
    _connect_readonly,
    _decimal,
    _money,
    _money_text,
    _safe_row,
    _sha256_bytes,
    _text,
    _write_atomic,
    sha256_file,
    validate_manifest as validate_source_manifest,
)


SCHEMA_VERSION = "api_order_entry_formula_promotion_manifest_v1"
TARGET_FIELDS = (
    "sale_id",
    "order_id",
    "order_date",
    "store_code",
    "sku_key",
    "sku_id",
    "my_size",
    "quantity",
    "sell_price_kzt",
    "delivery_fee",
    "net_rev",
    "cogs",
    "profit",
    "status",
    "return_flag",
    "source_file",
    "source_entry_id",
    "kaspi_article",
    "line_identity_key",
)


class ApiEntryPromotionManifestError(RuntimeError):
    """Raised when the copied promotion scope is not exact."""


def _same_file(left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except OSError:
        return left.resolve() == right.resolve()


def _load_one_proof(source_manifest_path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    proof_path = source_manifest_path.parent / _text(manifest.get("proof_file"))
    rows = [json.loads(line) for line in proof_path.read_text().splitlines() if line]
    if len(rows) != 1:
        raise ApiEntryPromotionManifestError(f"source proof count is {len(rows)}, expected 1")
    return rows[0]


def _query_target(conn: sqlite3.Connection, sale_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        f"SELECT {', '.join(TARGET_FIELDS)} FROM sales_fact_v2 WHERE sale_id=?",
        (sale_id,),
    ).fetchone()
    return _safe_row(row, TARGET_FIELDS) if row is not None else None


def _table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    names = [
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    return {
        name: int(conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0])
        for name in names
    }


def _non_target_hash(conn: sqlite3.Connection, target_ids: set[int]) -> str:
    columns = [str(row[1]) for row in conn.execute("PRAGMA table_info(sales_fact_v2)")]
    if not columns:
        raise ApiEntryPromotionManifestError("sales_fact_v2 is missing")
    placeholders = ",".join("?" for _ in target_ids)
    rows = [
        dict(row)
        for row in conn.execute(
            f"SELECT * FROM sales_fact_v2 WHERE sale_id NOT IN ({placeholders}) ORDER BY sale_id",
            tuple(sorted(target_ids)),
        )
    ]
    return _canonical_hash({"columns": columns, "rows": rows})


def build_promotion_manifest(
    *,
    source_manifest_path: Path,
    copied_db_path: Path,
    expected_source_manifest_sha256: str,
    expected_copied_db_sha256: str,
    output_path: Path,
) -> dict[str, Any]:
    source_manifest_path = source_manifest_path.resolve()
    copied_db_path = copied_db_path.resolve()
    validation = validate_source_manifest(source_manifest_path)
    if not validation.get("ok"):
        raise ApiEntryPromotionManifestError(
            f"source sidecar validation failed: {validation.get('errors')}"
        )
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    if source_manifest.get("schema_version") != SOURCE_SCHEMA:
        raise ApiEntryPromotionManifestError("unsupported source sidecar schema")
    if _text(source_manifest.get("manifest_sha256")) != _text(expected_source_manifest_sha256):
        raise ApiEntryPromotionManifestError("source manifest internal SHA-256 mismatch")
    if source_manifest.get("production_apply_authorized") is not False:
        raise ApiEntryPromotionManifestError("source manifest production boundary is invalid")
    db_sha_before = sha256_file(copied_db_path)
    if db_sha_before != _text(expected_copied_db_sha256):
        raise ApiEntryPromotionManifestError("copied DB SHA-256 mismatch")
    if db_sha_before != _text(source_manifest.get("copied_db_sha256")):
        raise ApiEntryPromotionManifestError("source sidecar is bound to a different copied DB")
    proof = _load_one_proof(source_manifest_path, source_manifest)
    provisional_economic_date = bool(proof.get("provisional_economic_date"))
    line_proofs = list(proof.get("line_proofs") or [])
    if len(line_proofs) != int(source_manifest.get("line_count") or 0):
        raise ApiEntryPromotionManifestError("source line proof count mismatch")
    targets: list[dict[str, Any]] = []
    with _connect_readonly(copied_db_path) as conn:
        if _text(conn.execute("PRAGMA integrity_check").fetchone()[0]).lower() != "ok":
            raise ApiEntryPromotionManifestError("copied DB integrity failed")
        triggers = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='sales_fact_v2'"
        ).fetchall()
        if triggers:
            raise ApiEntryPromotionManifestError("sales_fact_v2 triggers are not permitted")
        seen: set[int] = set()
        for line in line_proofs:
            sale_id = int(line["sale_id"])
            if sale_id in seen:
                raise ApiEntryPromotionManifestError("duplicate target sale_id")
            seen.add(sale_id)
            actual = _query_target(conn, sale_id)
            before = line.get("selected_row_preimage")
            if actual is None or actual != before:
                raise ApiEntryPromotionManifestError(
                    f"target preimage mismatch: sale_id={sale_id}"
                )
            fee = _money(
                _decimal(
                    line.get("seller_delivery_fee_line_kzt"),
                    field="seller_delivery_fee_line_kzt",
                )
            )
            net = _money(
                _decimal(line.get("canonical_line_net_rev_kzt"), field="canonical_line_net_rev_kzt")
            )
            cogs = before.get("cogs")
            profit = (
                _money(net - _decimal(cogs, field="before.cogs"))
                if cogs is not None and _text(cogs)
                else None
            )
            current_fee = (
                _money(_decimal(before.get("delivery_fee"), field="before.delivery_fee"))
                if before.get("delivery_fee") is not None
                else None
            )
            current_net = (
                _money(_decimal(before.get("net_rev"), field="before.net_rev"))
                if before.get("net_rev") is not None
                else None
            )
            if current_fee == fee and current_net == net and before.get("profit") == profit:
                raise ApiEntryPromotionManifestError(
                    f"target is already at proposed values: sale_id={sale_id}"
                )
            after = dict(before)
            after["delivery_fee"] = float(fee)
            after["net_rev"] = float(net)
            after["profit"] = float(profit) if profit is not None else None
            after.pop("safe_row_sha256", None)
            after["safe_row_sha256"] = _canonical_hash(after)
            target = {
                "sale_id": sale_id,
                "source_entry_id": _text(line.get("entry_id")),
                "line_identity_key": _text(line.get("line_identity_key")),
                "source_line_proof_sha256": _text(line.get("line_proof_sha256")),
                "before": before,
                "after": after,
                "changed_columns": ["delivery_fee", "net_rev", "profit"],
            }
            target["target_sha256"] = _canonical_hash(target)
            targets.append(target)
        target_ids = {int(row["sale_id"]) for row in targets}
        counts = _table_counts(conn)
        non_target = _non_target_hash(conn, target_ids)
    db_sha_after = sha256_file(copied_db_path)
    if db_sha_after != db_sha_before:
        raise ApiEntryPromotionManifestError("copied DB changed during manifest build")
    core = {
        "schema_version": SCHEMA_VERSION,
        "operation": "COPIED_DB_SALES_FORMULA_PROMOTION_CANDIDATE",
        "source_sidecar_manifest_path": str(source_manifest_path),
        "source_sidecar_manifest_file_sha256": sha256_file(source_manifest_path),
        "source_sidecar_manifest_sha256": _text(source_manifest.get("manifest_sha256")),
        "source_proof_key": _text(proof.get("proof_key")),
        "source_proof_file_sha256": _text(source_manifest.get("proof_file_sha256")),
        "copied_db_path": str(copied_db_path),
        "copied_db_sha256": db_sha_before,
        "order_id": _text(proof.get("order_id")),
        "store_code": _text(proof.get("store_code")),
        "target_count": len(targets),
        "target_sale_ids": sorted(target_ids),
        "targets": sorted(targets, key=lambda row: int(row["sale_id"])),
        "table_counts_before": counts,
        "table_counts_sha256": _canonical_hash(counts),
        "non_target_sales_fact_v2_sha256": non_target,
        "provisional_economic_date": provisional_economic_date,
        "publication_binding_authorized": bool(
            proof.get("publication_binding_authorized", True)
        ),
        "decision_grade_date_authorized": bool(
            proof.get("decision_grade_date_authorized", True)
        ),
        "production_apply_authorized": False,
        "copied_apply_ready": not provisional_economic_date,
        "blocked_reasons": (
            ["PRE_CUTOVER_CREATION_DATE_IS_PROVISIONAL_NOT_STATUS_CHANGE_PROOF"]
            if provisional_economic_date
            else []
        ),
        "cash_or_stock_write_authorized": False,
        "rollback_requirement": "BYTE_VALID_PREWRITE_SQLITE_BACKUP",
    }
    core["manifest_sha256"] = _canonical_hash(core)
    output_path = output_path.resolve()
    proof_path = source_manifest_path.parent / _text(source_manifest.get("proof_file"))
    source_db_path = Path(_text(source_manifest.get("source_db_path"))).resolve()
    protected = (source_manifest_path, proof_path.resolve(), copied_db_path, source_db_path)
    if any(_same_file(output_path, item) for item in protected):
        raise ApiEntryPromotionManifestError(
            "output path collides with a protected source or database"
        )
    if output_path.exists() and not output_path.is_file():
        raise ApiEntryPromotionManifestError("output path is not a regular file")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_atomic(output_path, _canonical_bytes(core, pretty=True))
    return core


def validate_promotion_manifest(path: Path) -> dict[str, Any]:
    path = path.resolve()
    manifest = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    internal = manifest.get("manifest_sha256")
    core = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if internal != _canonical_hash(core):
        errors.append("MANIFEST_HASH_MISMATCH")
    source_path = Path(_text(manifest.get("source_sidecar_manifest_path")))
    if (
        not source_path.exists()
        or sha256_file(source_path) != manifest.get("source_sidecar_manifest_file_sha256")
    ):
        errors.append("SOURCE_SIDECAR_FILE_HASH_DRIFT")
    elif not validate_source_manifest(source_path).get("ok"):
        errors.append("SOURCE_SIDECAR_VALIDATION_FAILED")
    else:
        try:
            source_manifest = json.loads(source_path.read_text(encoding="utf-8"))
            proof = _load_one_proof(source_path, source_manifest)
            provisional = bool(proof.get("provisional_economic_date"))
            if bool(manifest.get("provisional_economic_date")) != provisional:
                errors.append("PROVISIONAL_DATE_BOUNDARY_MISMATCH")
            if bool(manifest.get("copied_apply_ready")) == provisional:
                errors.append("COPIED_APPLY_BOUNDARY_MISMATCH")
            if (
                "publication_binding_authorized" in manifest
                or "publication_binding_authorized" in proof
            ) and bool(manifest.get("publication_binding_authorized")) != bool(
                proof.get("publication_binding_authorized", True)
            ):
                errors.append("PUBLICATION_BOUNDARY_MISMATCH")
        except (OSError, ValueError, json.JSONDecodeError, ApiEntryPromotionManifestError):
            errors.append("SOURCE_PROOF_BOUNDARY_READ_FAILED")
    db_path = Path(_text(manifest.get("copied_db_path")))
    if not db_path.exists() or sha256_file(db_path) != manifest.get("copied_db_sha256"):
        errors.append("COPIED_DB_HASH_DRIFT")
    elif not errors:
        try:
            with _connect_readonly(db_path) as conn:
                targets = list(manifest.get("targets") or [])
                for target in targets:
                    actual = _query_target(conn, int(target["sale_id"]))
                    if actual != target.get("before"):
                        errors.append("TARGET_PREIMAGE_DRIFT")
                        break
                target_ids = {int(target["sale_id"]) for target in targets}
                if _table_counts(conn) != manifest.get("table_counts_before"):
                    errors.append("TABLE_COUNT_DRIFT")
                if _non_target_hash(conn, target_ids) != manifest.get(
                    "non_target_sales_fact_v2_sha256"
                ):
                    errors.append("NON_TARGET_HASH_DRIFT")
        except (sqlite3.Error, ValueError, ApiEntryPromotionManifestError):
            errors.append("COPIED_DB_READBACK_FAILED")
    if len(manifest.get("targets") or []) != manifest.get("target_count"):
        errors.append("TARGET_COUNT_MISMATCH")
    for target in manifest.get("targets") or []:
        expected = target.get("target_sha256")
        target_core = {key: value for key, value in target.items() if key != "target_sha256"}
        if expected != _canonical_hash(target_core):
            errors.append("TARGET_HASH_MISMATCH")
            break
    return {"ok": not errors, "errors": sorted(set(errors)), "manifest_sha256": internal}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-manifest", type=Path)
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--copied-db", type=Path)
    parser.add_argument("--expected-source-manifest-sha256")
    parser.add_argument("--expected-copied-db-sha256")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.validate_manifest:
        report = validate_promotion_manifest(args.validate_manifest)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report["ok"] else 1
    required = {
        "source_manifest": args.source_manifest,
        "copied_db": args.copied_db,
        "expected_source_manifest_sha256": args.expected_source_manifest_sha256,
        "expected_copied_db_sha256": args.expected_copied_db_sha256,
        "output": args.output,
    }
    missing = sorted(key for key, value in required.items() if value is None)
    if missing:
        parser.error("missing build arguments: " + ", ".join(missing))
    manifest = build_promotion_manifest(
        source_manifest_path=args.source_manifest,
        copied_db_path=args.copied_db,
        expected_source_manifest_sha256=args.expected_source_manifest_sha256,
        expected_copied_db_sha256=args.expected_copied_db_sha256,
        output_path=args.output,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
