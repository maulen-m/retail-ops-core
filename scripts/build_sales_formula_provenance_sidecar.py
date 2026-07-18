#!/usr/bin/env python3
"""Build a deterministic, read-only sales formula-provenance sidecar.

Version 1 intentionally proves only the conservative OCEAN case where one
selected ``sales_fact_v2`` line represents the complete order/store source
population. Multi-line, mixed-source, ambiguous, or incomplete orders remain
excluded rather than being guessed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sqlite3
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(PROJECT_ROOT))

from core.calc.economics import calc_net_rev  # noqa: E402


BUILD_VERSION = "sales_formula_provenance_v2"
MONEY = Decimal("0.01")
REQUIRED_OCEAN_HEADERS = (
    "№ заказа",
    "Дата поступления заказа",
    "Артикул",
    "Сумма",
    "Количество",
    "Стоимость доставки для продавца",
    "Статус",
    "Причина отмены",
    "mapping_source_store_code",
    "mapped_sku_key",
    "mapped_size",
)
POLICY_PATHS = (
    PROJECT_ROOT / "core" / "calc" / "economics.py",
    PROJECT_ROOT / "core" / "config" / "business_params.py",
    PROJECT_ROOT / "docs" / "validation" / "SALES_ECONOMICS_TRUTH_CONTRACT.md",
)


class ProvenanceError(RuntimeError):
    """Raised when deterministic sidecar construction cannot continue."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value: Any, *, pretty: bool = False) -> bytes:
    if pretty:
        text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    else:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return text.encode("utf-8")


def _canonical_hash(value: Any) -> str:
    return _sha256_bytes(_json_bytes(value))


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _upper(value: Any) -> str:
    return _clean(value).upper()


def _decimal(value: Any, *, field: str) -> Decimal:
    text = _clean(value).replace("\u00a0", "").replace(" ", "").replace(",", ".")
    if not text:
        raise ProvenanceError(f"missing numeric field: {field}")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ProvenanceError(f"invalid numeric field {field}: {value!r}") from exc


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f") if value != 0 else "0"


def _money_text(value: Decimal) -> str:
    return format(_money(value), ".2f")


def _parse_date(value: Any) -> date:
    text = _clean(value)
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass
    raise ProvenanceError(f"invalid source date: {value!r}")


def _connect_readonly(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _selected_view_rows(conn: sqlite3.Connection, since: date, until: date) -> list[dict[str, Any]]:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='view' AND name='view_sales_line_truth'"
    ).fetchone()
    if not exists:
        raise ProvenanceError("view_sales_line_truth is missing")
    rows = conn.execute(
        """
        SELECT
            CAST(order_id AS TEXT) AS order_id,
            date(sale_date) AS sale_date,
            UPPER(TRIM(COALESCE(store_code, 'UNIVERSAL'))) AS store_code,
            CAST(COALESCE(source_sku_key, '') AS TEXT) AS source_sku_key,
            CAST(COALESCE(source_sku_id, '') AS TEXT) AS source_sku_id,
            CAST(COALESCE(my_size, '') AS TEXT) AS my_size,
            CAST(COALESCE(source_units, 0) AS REAL) AS source_units,
            CAST(COALESCE(source_net_rev_kzt, 0) AS REAL) AS source_net_rev_kzt,
            CAST(COALESCE(source_table, '') AS TEXT) AS source_table
        FROM view_sales_line_truth
        WHERE date(sale_date) BETWEEN ? AND ?
          AND LOWER(TRIM(COALESCE(source_table, ''))) = 'sales_fact_v2'
        ORDER BY order_id, store_code, source_sku_key, source_sku_id, my_size,
                 source_units, source_net_rev_kzt
        """,
        (since.isoformat(), until.isoformat()),
    ).fetchall()
    return [dict(row) for row in rows]


def _view_key(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        _clean(row.get("order_id")),
        _upper(row.get("store_code")),
        _clean(row.get("source_sku_key")),
        _clean(row.get("source_sku_id")),
        _upper(row.get("my_size")),
        _decimal_text(Decimal(str(row.get("source_units") or 0))),
        _money_text(Decimal(str(row.get("source_net_rev_kzt") or 0))),
    )


def _db_key(row: dict[str, Any]) -> tuple[str, ...]:
    return (
        _clean(row.get("order_id")),
        _upper(row.get("store_code")),
        _clean(row.get("sku_key")),
        _clean(row.get("sku_id")),
        _upper(row.get("my_size")),
        _decimal_text(Decimal(str(row.get("quantity") or 0))),
        _money_text(Decimal(str(row.get("net_rev") or 0))),
    )


def _selected_db_rows(
    conn: sqlite3.Connection,
    view_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], set[tuple[str, str]]]:
    wanted = Counter(_view_key(row) for row in view_rows)
    order_keys = sorted({(key[0], key[1]) for key in wanted})
    if not order_keys:
        return [], set()
    order_ids = sorted({key[0] for key in order_keys})
    placeholders = ",".join("?" for _ in order_ids)
    rows = conn.execute(
        f"""
        SELECT sale_id, CAST(order_id AS TEXT) AS order_id,
               UPPER(TRIM(COALESCE(store_code, 'UNIVERSAL'))) AS store_code,
               date(order_date) AS order_date, sku_key, sku_id, my_size,
               quantity, sell_price_kzt, delivery_fee, net_rev, cogs, profit,
               source_file, source_entry_id, kaspi_article, line_identity_key
        FROM sales_fact_v2
        WHERE CAST(order_id AS TEXT) IN ({placeholders})
          AND UPPER(COALESCE(status, 'DELIVERED')) = 'DELIVERED'
          AND COALESCE(return_flag, 0) = 0
        ORDER BY order_id, store_code, sale_id
        """,
        order_ids,
    ).fetchall()
    candidates = [dict(row) for row in rows if (_clean(row["order_id"]), _upper(row["store_code"])) in order_keys]
    actual = Counter(_db_key(row) for row in candidates if _db_key(row) in wanted)
    mismatch_orders = {
        (key[0], key[1])
        for key in set(wanted) | set(actual)
        if wanted.get(key, 0) != actual.get(key, 0)
    }
    selected = [
        row
        for row in candidates
        if _db_key(row) in wanted and (_clean(row["order_id"]), _upper(row["store_code"])) not in mismatch_orders
    ]
    return selected, mismatch_orders


def _read_ocean_rows(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = list(reader.fieldnames or [])
        missing = [header for header in REQUIRED_OCEAN_HEADERS if header not in headers]
        if missing:
            raise ProvenanceError(f"OCEAN source missing required headers: {missing}")
        for physical_row, raw in enumerate(reader, start=2):
            canonical = {header: _clean(raw.get(header)) for header in headers}
            canonical_hash = _canonical_hash(canonical)
            rows.append(
                {
                    "physical_row": physical_row,
                    "canonical_row": canonical,
                    "canonical_row_sha256": canonical_hash,
                    "order_id": _clean(raw.get("№ заказа")),
                    "store_code": _upper(raw.get("mapping_source_store_code")),
                    "sku_key": _clean(raw.get("mapped_sku_key")),
                    "size": _upper(raw.get("mapped_size")),
                }
            )
    return rows, headers


def _policy_manifest() -> dict[str, Any]:
    files = []
    for path in POLICY_PATHS:
        if not path.exists():
            raise ProvenanceError(f"policy file missing: {path}")
        files.append({"path": str(path.resolve()), "sha256": sha256_file(path)})
    return {"files": files, "sha256": _canonical_hash(files)}


def _db_row_payload(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
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
    payload: dict[str, Any] = {}
    for key in keys:
        value = row.get(key)
        if isinstance(value, float):
            value = _decimal_text(Decimal(str(value)))
        payload[key] = value
    return payload


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _jsonl_bytes(rows: Iterable[dict[str, Any]]) -> bytes:
    return b"".join(_json_bytes(row) + b"\n" for row in rows)


def _build_proof(
    *,
    db_row: dict[str, Any],
    source_rows: list[dict[str, Any]],
    source_sha256: str,
    source_path: Path,
    policy_sha256: str,
    db_sha256: str,
    view_sha256: str,
) -> dict[str, Any]:
    expected_order_key = (
        _clean(db_row.get("order_id")),
        _upper(db_row.get("store_code")),
    )
    source_order_keys = {
        (
            _clean(row["canonical_row"].get("№ заказа")),
            _upper(row["canonical_row"].get("mapping_source_store_code")),
        )
        for row in source_rows
    }
    if source_order_keys != {expected_order_key}:
        raise ProvenanceError("source and DB order/store identity mismatch")
    source_product_keys = {
        (
            _clean(row["canonical_row"].get("mapped_sku_key")),
            _upper(row["canonical_row"].get("mapped_size")),
        )
        for row in source_rows
    }
    expected_product_key = (
        _clean(db_row.get("sku_key")),
        _upper(db_row.get("my_size")),
    )
    if source_product_keys != {expected_product_key}:
        raise ProvenanceError("source and DB SKU/size identity mismatch")
    source_statuses = {
        _upper(row["canonical_row"].get("Статус"))
        for row in source_rows
    }
    if source_statuses != {"ЗАВЕРШЕН"}:
        raise ProvenanceError("source lifecycle status is not completed")
    if any(_clean(row["canonical_row"].get("Причина отмены")) for row in source_rows):
        raise ProvenanceError("source cancellation reason is nonblank")
    quantity = _decimal(db_row.get("quantity"), field="db.quantity")
    unit_price = _decimal(db_row.get("sell_price_kzt"), field="db.sell_price_kzt")
    raw_quantity = sum(
        (_decimal(row["canonical_row"].get("Количество"), field="source.quantity") for row in source_rows),
        Decimal("0"),
    )
    raw_gross = sum(
        (_decimal(row["canonical_row"].get("Сумма"), field="source.gross") for row in source_rows),
        Decimal("0"),
    )
    fee_values = {
        _money(_decimal(row["canonical_row"].get("Стоимость доставки для продавца"), field="source.seller_fee"))
        for row in source_rows
    }
    if len(fee_values) != 1:
        raise ProvenanceError("conflicting seller delivery fee values")
    seller_fee_total = next(iter(fee_values))
    if raw_quantity != quantity:
        raise ProvenanceError("source and DB quantity mismatch")
    if abs(_money(unit_price * quantity) - _money(raw_gross)) > MONEY:
        raise ProvenanceError("source and DB gross mismatch")
    if quantity <= 0:
        raise ProvenanceError("nonpositive quantity")
    order_date = date.fromisoformat(_clean(db_row.get("order_date"))[:10])
    source_dates = {
        _parse_date(row["canonical_row"].get("Дата поступления заказа"))
        for row in source_rows
    }
    if source_dates != {order_date}:
        raise ProvenanceError("source and DB order date mismatch")
    seller_fee_unit = seller_fee_total / quantity
    canonical_line_net = Decimal(
        str(
            round(
                calc_net_rev(
                    float(unit_price),
                    delivery_fee=float(seller_fee_unit),
                    as_of_date=order_date,
                )
                * float(quantity),
                2,
            )
        )
    )
    source_locators = [f"csv:row:{row['physical_row']}" for row in source_rows]
    source_row_hashes = [row["canonical_row_sha256"] for row in source_rows]
    source_set_sha256 = _canonical_hash(
        [
            {"locator": locator, "row_sha256": row_hash}
            for locator, row_hash in zip(source_locators, source_row_hashes)
        ]
    )
    proof_key = _sha256_bytes(
        (
            f"{BUILD_VERSION}\0OCEAN_CSV\0{source_sha256}\0{source_set_sha256}\0"
            f"{_canonical_hash(_db_row_payload(db_row))}\0{db_sha256}\0"
            f"{view_sha256}\0{policy_sha256}"
        ).encode("utf-8")
    )
    stored_net = _money(_decimal(db_row.get("net_rev"), field="db.net_rev"))
    current_delivery = (
        _money(_decimal(db_row.get("delivery_fee"), field="db.delivery_fee"))
        if _clean(db_row.get("delivery_fee"))
        else None
    )
    return {
        "proof_key": proof_key,
        "source_kind": "OCEAN_CSV",
        "source_packet_path": str(source_path.resolve()),
        "source_packet_sha256": source_sha256,
        "source_locators": source_locators,
        "source_row_sha256s": source_row_hashes,
        "source_row_set_sha256": source_set_sha256,
        "order_id": _clean(db_row.get("order_id")),
        "store_code": _upper(db_row.get("store_code")),
        "sale_id": int(db_row["sale_id"]),
        "order_date": order_date.isoformat(),
        "sku_key": _clean(db_row.get("sku_key")),
        "sku_id": _clean(db_row.get("sku_id")),
        "size": _upper(db_row.get("my_size")),
        "quantity": _decimal_text(quantity),
        "gross_total_kzt": _money_text(raw_gross),
        "unit_sell_price_kzt": _money_text(unit_price),
        "seller_delivery_fee_total_kzt": _money_text(seller_fee_total),
        "seller_delivery_fee_unit_kzt": _money_text(seller_fee_unit),
        "canonical_line_net_rev_kzt": _money_text(canonical_line_net),
        "stored_line_net_rev_kzt": _money_text(stored_net),
        "stored_delivery_fee_total_kzt": _money_text(current_delivery) if current_delivery is not None else None,
        "repair_required": stored_net != canonical_line_net or current_delivery != seller_fee_total,
        "db_row": _db_row_payload(db_row),
        "db_row_sha256": _canonical_hash(_db_row_payload(db_row)),
        "copied_db_sha256": db_sha256,
        "selected_view_multiset_sha256": view_sha256,
        "economics_policy_sha256": policy_sha256,
        "evidence_status": "SOURCE_PROVEN_REPAIR_CANDIDATE"
        if stored_net != canonical_line_net or current_delivery != seller_fee_total
        else "SOURCE_PROVEN_ALREADY_CANONICAL",
    }


def build_sidecar(
    *,
    db_path: Path,
    ocean_csv_path: Path,
    since: date,
    until: date,
    output_dir: Path,
) -> dict[str, Any]:
    db_path = db_path.resolve()
    ocean_csv_path = ocean_csv_path.resolve()
    if not db_path.exists() or not ocean_csv_path.exists():
        raise ProvenanceError("DB and OCEAN source must both exist")
    db_sha_before = sha256_file(db_path)
    source_sha_before = sha256_file(ocean_csv_path)
    policy = _policy_manifest()

    with _connect_readonly(db_path) as conn:
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity.lower() != "ok":
            raise ProvenanceError(f"copied DB integrity failed: {integrity}")
        view_rows = _selected_view_rows(conn, since, until)
        view_sha256 = _canonical_hash(view_rows)
        db_rows, view_mismatch_orders = _selected_db_rows(conn, view_rows)

    source_rows, source_headers = _read_ocean_rows(ocean_csv_path)
    source_by_order: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in source_rows:
        if row["order_id"] and row["store_code"]:
            source_by_order[(row["order_id"], row["store_code"])].append(row)
    db_by_order: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in db_rows:
        db_by_order[(_clean(row["order_id"]), _upper(row["store_code"]))].append(row)

    proofs: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    selected_order_keys = sorted({(_clean(row["order_id"]), _upper(row["store_code"])) for row in view_rows})
    for order_id, store_code in selected_order_keys:
        key = (order_id, store_code)
        reasons: list[str] = []
        selected_lines = db_by_order.get(key, [])
        raw_lines = source_by_order.get(key, [])
        if key in view_mismatch_orders:
            reasons.append("VIEW_SOURCE_MULTISET_MISMATCH")
        if len(selected_lines) != 1:
            reasons.append("SELECTED_DB_LINE_COUNT_NOT_ONE")
        if not raw_lines:
            reasons.append("NO_FROZEN_OCEAN_SOURCE_ROWS")
        if selected_lines and _upper(selected_lines[0].get("source_file")) != "OCEAN_DROP_ANCHOR":
            reasons.append("SOURCE_FILE_NOT_OCEAN_DROP_ANCHOR")
        if raw_lines:
            raw_groups = {(row["sku_key"], row["size"]) for row in raw_lines}
            if len(raw_groups) != 1:
                reasons.append("RAW_SOURCE_MULTI_IDENTITY")
            elif selected_lines:
                raw_sku_key, raw_size = next(iter(raw_groups))
                if raw_sku_key != _clean(selected_lines[0].get("sku_key")) or raw_size != _upper(
                    selected_lines[0].get("my_size")
                ):
                    reasons.append("RAW_TO_DB_IDENTITY_MISMATCH")
        if reasons:
            excluded.append(
                {
                    "order_id": order_id,
                    "store_code": store_code,
                    "reasons": sorted(set(reasons)),
                    "selected_db_line_count": len(selected_lines),
                    "source_row_count": len(raw_lines),
                }
            )
            continue
        try:
            proof = _build_proof(
                db_row=selected_lines[0],
                source_rows=sorted(raw_lines, key=lambda row: int(row["physical_row"])),
                source_sha256=source_sha_before,
                source_path=ocean_csv_path,
                policy_sha256=policy["sha256"],
                db_sha256=db_sha_before,
                view_sha256=view_sha256,
            )
        except (ProvenanceError, ValueError) as exc:
            excluded.append(
                {
                    "order_id": order_id,
                    "store_code": store_code,
                    "reasons": [f"PROOF_BUILD_FAILED:{exc}"],
                    "selected_db_line_count": len(selected_lines),
                    "source_row_count": len(raw_lines),
                }
            )
            continue
        proofs.append(proof)

    proofs.sort(key=lambda row: row["proof_key"])
    excluded.sort(key=lambda row: (row["order_id"], row["store_code"], row["reasons"]))
    proof_bytes = _jsonl_bytes(proofs)
    excluded_bytes = _jsonl_bytes(excluded)
    proof_path = output_dir / "formula_provenance.jsonl"
    excluded_path = output_dir / "excluded.jsonl"
    _write_atomic(proof_path, proof_bytes)
    _write_atomic(excluded_path, excluded_bytes)

    db_sha_after = sha256_file(db_path)
    source_sha_after = sha256_file(ocean_csv_path)
    if db_sha_before != db_sha_after or source_sha_before != source_sha_after:
        raise ProvenanceError("read-only input hash changed during sidecar build")
    repair_candidates = sum(bool(row["repair_required"]) for row in proofs)
    manifest_payload = {
        "schema": BUILD_VERSION,
        "since": since.isoformat(),
        "until": until.isoformat(),
        "db_path": str(db_path),
        "db_sha256": db_sha_before,
        "db_integrity": integrity,
        "source_path": str(ocean_csv_path),
        "source_sha256": source_sha_before,
        "source_headers": source_headers,
        "policy": policy,
        "selected_view_line_count": len(view_rows),
        "selected_view_order_count": len(selected_order_keys),
        "selected_view_multiset_sha256": view_sha256,
        "proof_path": str(proof_path.resolve()),
        "proof_sha256": _sha256_bytes(proof_bytes),
        "proof_count": len(proofs),
        "proof_order_count": len({(row["order_id"], row["store_code"]) for row in proofs}),
        "repair_candidate_count": repair_candidates,
        "excluded_path": str(excluded_path.resolve()),
        "excluded_sha256": _sha256_bytes(excluded_bytes),
        "excluded_count": len(excluded),
        "input_hashes_unchanged": True,
    }
    manifest_payload["manifest_sha256"] = _canonical_hash(manifest_payload)
    manifest_path = output_dir / "manifest.json"
    _write_atomic(manifest_path, _json_bytes(manifest_payload, pretty=True))
    return manifest_payload


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ProvenanceError(f"invalid JSONL at {path}:{line_number}") from exc
            if not isinstance(value, dict):
                raise ProvenanceError(f"non-object JSONL at {path}:{line_number}")
            rows.append(value)
    return rows


def validate_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_manifest_sha = _clean(manifest.get("manifest_sha256"))
    unsigned = dict(manifest)
    unsigned.pop("manifest_sha256", None)
    errors: list[str] = []
    if expected_manifest_sha != _canonical_hash(unsigned):
        errors.append("MANIFEST_HASH_MISMATCH")
    db_path = Path(_clean(manifest.get("db_path")))
    source_path = Path(_clean(manifest.get("source_path")))
    proof_path = Path(_clean(manifest.get("proof_path")))
    excluded_path = Path(_clean(manifest.get("excluded_path")))
    for label, path in (
        ("DB", db_path),
        ("SOURCE", source_path),
        ("PROOF", proof_path),
        ("EXCLUDED", excluded_path),
    ):
        if not path.exists():
            errors.append(f"{label}_PATH_MISSING")
    if db_path.exists() and sha256_file(db_path) != manifest.get("db_sha256"):
        errors.append("DB_HASH_DRIFT")
    if source_path.exists() and sha256_file(source_path) != manifest.get("source_sha256"):
        errors.append("SOURCE_HASH_DRIFT")
    policy = _policy_manifest()
    if policy.get("sha256") != (manifest.get("policy") or {}).get("sha256"):
        errors.append("POLICY_HASH_DRIFT")
    proofs = _load_jsonl(proof_path) if proof_path.exists() else []
    excluded = _load_jsonl(excluded_path) if excluded_path.exists() else []
    if proof_path.exists() and sha256_file(proof_path) != manifest.get("proof_sha256"):
        errors.append("PROOF_HASH_MISMATCH")
    if excluded_path.exists() and sha256_file(excluded_path) != manifest.get("excluded_sha256"):
        errors.append("EXCLUDED_HASH_MISMATCH")
    if len(proofs) != int(manifest.get("proof_count") or 0):
        errors.append("PROOF_COUNT_MISMATCH")
    if len(excluded) != int(manifest.get("excluded_count") or 0):
        errors.append("EXCLUDED_COUNT_MISMATCH")
    if manifest.get("schema") != BUILD_VERSION:
        errors.append("MANIFEST_SCHEMA_MISMATCH")
    if manifest.get("input_hashes_unchanged") is not True:
        errors.append("MANIFEST_INPUT_HASH_ASSERTION_MISSING")
    if sum(bool(row.get("repair_required")) for row in proofs) != int(
        manifest.get("repair_candidate_count") or 0
    ):
        errors.append("REPAIR_CANDIDATE_COUNT_MISMATCH")
    proof_keys = [_clean(row.get("proof_key")) for row in proofs]
    if not all(proof_keys) or len(proof_keys) != len(set(proof_keys)):
        errors.append("PROOF_KEY_DUPLICATE_OR_BLANK")
    if proofs != sorted(proofs, key=lambda row: _clean(row.get("proof_key"))):
        errors.append("PROOF_ORDER_NONDETERMINISTIC")
    independently_rechecked_proofs = 0
    if db_path.exists():
        try:
            since = date.fromisoformat(_clean(manifest.get("since")))
            until = date.fromisoformat(_clean(manifest.get("until")))
            with _connect_readonly(db_path) as conn:
                integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
                if integrity.lower() != "ok":
                    errors.append("DB_INTEGRITY_FAILED")
                view_rows = _selected_view_rows(conn, since, until)
                selected_db_rows, view_mismatch_orders = _selected_db_rows(conn, view_rows)
            if _canonical_hash(view_rows) != manifest.get("selected_view_multiset_sha256"):
                errors.append("SELECTED_VIEW_HASH_DRIFT")
            if len(view_rows) != int(manifest.get("selected_view_line_count") or 0):
                errors.append("SELECTED_VIEW_LINE_COUNT_MISMATCH")
        except (ValueError, sqlite3.Error, ProvenanceError):
            errors.append("SELECTED_VIEW_RECHECK_FAILED")
            view_rows = []
            selected_db_rows = []
            view_mismatch_orders = set()
    else:
        view_rows = []
        selected_db_rows = []
        view_mismatch_orders = set()

    selected_order_keys = {
        (_clean(row.get("order_id")), _upper(row.get("store_code")))
        for row in view_rows
    }
    proof_order_keys = [
        (_clean(row.get("order_id")), _upper(row.get("store_code")))
        for row in proofs
    ]
    excluded_order_keys = [
        (_clean(row.get("order_id")), _upper(row.get("store_code")))
        for row in excluded
    ]
    if any(not order_id or not store_code for order_id, store_code in proof_order_keys):
        errors.append("PROOF_ORDER_IDENTITY_BLANK")
    if any(not order_id or not store_code for order_id, store_code in excluded_order_keys):
        errors.append("EXCLUDED_ORDER_IDENTITY_BLANK")
    if len(proof_order_keys) != len(set(proof_order_keys)):
        errors.append("PROOF_ORDER_IDENTITY_DUPLICATE")
    if len(set(proof_order_keys)) != int(manifest.get("proof_order_count") or 0):
        errors.append("PROOF_ORDER_COUNT_MISMATCH")
    if len(excluded_order_keys) != len(set(excluded_order_keys)):
        errors.append("EXCLUDED_ORDER_IDENTITY_DUPLICATE")
    if set(proof_order_keys) & set(excluded_order_keys):
        errors.append("PROOF_EXCLUDED_ORDER_OVERLAP")
    if selected_order_keys and set(proof_order_keys) | set(excluded_order_keys) != selected_order_keys:
        errors.append("SELECTED_ORDER_COVERAGE_MISMATCH")
    if len(selected_order_keys) != int(manifest.get("selected_view_order_count") or 0):
        errors.append("SELECTED_VIEW_ORDER_COUNT_MISMATCH")
    if set(proof_order_keys) & view_mismatch_orders:
        errors.append("PROOF_CONTAINS_VIEW_MULTISET_MISMATCH")

    if db_path.exists() and source_path.exists() and view_rows:
        try:
            source_rows, actual_source_headers = _read_ocean_rows(source_path)
            if actual_source_headers != manifest.get("source_headers"):
                errors.append("SOURCE_HEADER_MISMATCH")
            source_by_physical_row = {int(row["physical_row"]): row for row in source_rows}
            source_by_order: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
            for source_row in source_rows:
                source_key = (source_row["order_id"], source_row["store_code"])
                if all(source_key):
                    source_by_order[source_key].append(source_row)
            selected_by_sale_id = {int(row["sale_id"]): row for row in selected_db_rows}
            actual_db_sha256 = sha256_file(db_path)
            actual_source_sha256 = sha256_file(source_path)
            actual_policy_sha256 = _policy_manifest()["sha256"]
            actual_view_sha256 = _canonical_hash(view_rows)
            used_source_physical_rows: list[int] = []
            for proof in proofs:
                try:
                    sale_id = int(proof.get("sale_id"))
                    db_row = selected_by_sale_id.get(sale_id)
                    if db_row is None:
                        raise ProvenanceError("proof sale_id is not a selected DB row")
                    locators = proof.get("source_locators")
                    if not isinstance(locators, list) or not locators:
                        raise ProvenanceError("proof source locators missing")
                    proof_source_rows: list[dict[str, Any]] = []
                    for locator in locators:
                        parts = _clean(locator).split(":")
                        if len(parts) != 3 or parts[:2] != ["csv", "row"]:
                            raise ProvenanceError("invalid source locator")
                        source_row = source_by_physical_row.get(int(parts[2]))
                        if source_row is None:
                            raise ProvenanceError("source locator row missing")
                        proof_source_rows.append(source_row)
                        used_source_physical_rows.append(int(source_row["physical_row"]))
                    proof_order_key = (
                        _clean(proof.get("order_id")),
                        _upper(proof.get("store_code")),
                    )
                    expected_source_physical_rows = {
                        int(row["physical_row"])
                        for row in source_by_order.get(proof_order_key, [])
                    }
                    actual_source_physical_rows = {
                        int(row["physical_row"])
                        for row in proof_source_rows
                    }
                    if actual_source_physical_rows != expected_source_physical_rows:
                        raise ProvenanceError("proof does not bind the complete source order set")
                    expected = _build_proof(
                        db_row=db_row,
                        source_rows=proof_source_rows,
                        source_sha256=actual_source_sha256,
                        source_path=source_path,
                        policy_sha256=actual_policy_sha256,
                        db_sha256=actual_db_sha256,
                        view_sha256=actual_view_sha256,
                    )
                    if expected != proof:
                        raise ProvenanceError("proof content differs from source/DB recomputation")
                    independently_rechecked_proofs += 1
                except (KeyError, TypeError, ValueError, ProvenanceError):
                    errors.append("PROOF_CONTENT_RECHECK_FAILED")
            if len(used_source_physical_rows) != len(set(used_source_physical_rows)):
                errors.append("PROOF_SOURCE_LOCATOR_REUSED")
            if independently_rechecked_proofs != len(proofs):
                errors.append("PROOF_INDEPENDENT_RECHECK_COUNT_MISMATCH")
        except (OSError, ValueError, ProvenanceError):
            errors.append("PROOF_SOURCE_RECHECK_FAILED")
    report = {
        "schema": "sales_formula_provenance_validation_v2",
        "manifest_path": str(manifest_path),
        "manifest_sha256": expected_manifest_sha,
        "status": "PASS" if not errors else "FAIL",
        "ok": not errors,
        "errors": sorted(set(errors)),
        "proof_count": len(proofs),
        "independently_rechecked_proof_count": independently_rechecked_proofs,
        "repair_candidate_count": sum(bool(row.get("repair_required")) for row in proofs),
        "excluded_count": len(excluded),
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--ocean-csv", type=Path, required=True)
    parser.add_argument("--since", type=date.fromisoformat, required=True)
    parser.add_argument("--until", type=date.fromisoformat, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        manifest = build_sidecar(
            db_path=args.db,
            ocean_csv_path=args.ocean_csv,
            since=args.since,
            until=args.until,
            output_dir=args.output_dir,
        )
    except (OSError, sqlite3.Error, ProvenanceError, ValueError) as exc:
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        return 1
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
