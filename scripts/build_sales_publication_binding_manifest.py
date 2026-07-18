#!/usr/bin/env python3
"""Build an exact, read-only multi-line sales publication binding manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.sales.truth_view_contract import (  # noqa: E402
    TruthViewContractError,
    build_truth_view_contract,
    require_manifest_build_compatible,
)
from core.sales.publication_prerequisites import (  # noqa: E402
    MinimalPublicationSchemaError,
    build_minimal_publication_schema_contract,
    require_minimal_publication_schema,
)


CANONICAL_HASH_VERSION = "canonical-json-v1-sort-keys-utf8-no-whitespace"
SCHEMA_VERSION = "sales_publication_binding_manifest_v2"
OLD_PUBLIC_COLUMNS = [
    "order_id",
    "sale_date",
    "store_code",
    "sku_key",
    "sku_id",
    "my_size",
    "units",
    "net_rev_kzt",
    "cogs_kzt",
    "profit_kzt",
    "cogs_source",
    "source_table",
    "source_sku_key",
    "source_sku_id",
    "source_units",
    "source_net_rev_kzt",
    "source_cogs_kzt",
    "source_profit_kzt",
]


class PublicationBindingManifestError(RuntimeError):
    pass


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


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PublicationBindingManifestError(f"expected JSON object: {path}")
    return value


def _load_single_jsonl(path: Path) -> dict[str, Any]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != 1 or not isinstance(rows[0], dict):
        raise PublicationBindingManifestError(f"expected exactly one JSONL proof row: {path}")
    return rows[0]


def _verify_internal_hash(payload: dict[str, Any], field: str, *, label: str) -> None:
    expected = str(payload.get(field) or "")
    if not expected:
        raise PublicationBindingManifestError(f"{label} lacks {field}")
    body = dict(payload)
    body.pop(field, None)
    observed = canonical_sha256(body)
    if observed != expected:
        raise PublicationBindingManifestError(
            f"{label} internal hash mismatch: expected {expected}, observed {observed}"
        )


def _db_sha256(path: Path) -> str:
    return sha256_file(path)


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _multiset_hash(rows: list[dict[str, Any]], *, sort_fields: tuple[str, ...]) -> str:
    ordered = sorted(rows, key=lambda row: tuple(str(row.get(field) or "") for field in sort_fields))
    return canonical_sha256(ordered)


def _completion_timestamp(header: dict[str, Any]) -> tuple[str, str]:
    attributes = header.get("attributes") or {}
    millis = attributes.get("completionDate")
    if not isinstance(millis, (int, float)):
        raise PublicationBindingManifestError("safe API header lacks numeric completionDate")
    completed = datetime.fromtimestamp(float(millis) / 1000.0, tz=timezone.utc)
    return completed.date().isoformat(), completed.isoformat(timespec="microseconds")


def build_manifest(
    *,
    db_path: Path,
    order_id: str,
    store_code: str,
    source_sidecar_manifest_path: Path,
    source_proof_path: Path,
    promotion_manifest_path: Path,
    promotion_apply_report_path: Path,
    api_header_path: Path,
) -> dict[str, Any]:
    db_path = db_path.resolve()
    store_code = store_code.strip().upper()
    prerequisite_conn = sqlite3.connect(
        f"file:{db_path}?mode=ro",
        uri=True,
    )
    try:
        minimal_publication_schema_contract = (
            build_minimal_publication_schema_contract(prerequisite_conn)
        )
        require_minimal_publication_schema(
            minimal_publication_schema_contract
        )
    except MinimalPublicationSchemaError as exc:
        raise PublicationBindingManifestError(str(exc)) from exc
    finally:
        prerequisite_conn.close()
    try:
        truth_view_runtime_contract = build_truth_view_contract(db_path)
        require_manifest_build_compatible(truth_view_runtime_contract)
    except TruthViewContractError as exc:
        raise PublicationBindingManifestError(str(exc)) from exc

    source_manifest = _load_json(source_sidecar_manifest_path)
    source_proof = _load_single_jsonl(source_proof_path)
    promotion_manifest = _load_json(promotion_manifest_path)
    promotion_apply_report = _load_json(promotion_apply_report_path)
    api_header = _load_json(api_header_path)

    _verify_internal_hash(source_manifest, "manifest_sha256", label="source manifest")
    _verify_internal_hash(promotion_manifest, "manifest_sha256", label="promotion manifest")

    expected_identity = (order_id, store_code)
    for label, payload in (
        ("source manifest", source_manifest),
        ("source proof", source_proof),
        ("promotion manifest", promotion_manifest),
        ("API header", api_header),
    ):
        observed = (str(payload.get("order_id") or ""), str(payload.get("store_code") or "").upper())
        if observed != expected_identity:
            raise PublicationBindingManifestError(
                f"{label} identity mismatch: expected {expected_identity}, observed {observed}"
            )

    if not bool(source_manifest.get("decision_grade_date_authorized")):
        raise PublicationBindingManifestError("source manifest does not authorize decision-grade date")
    if bool(source_manifest.get("provisional_economic_date")):
        raise PublicationBindingManifestError("provisional source date cannot activate a binding")
    if not bool(source_manifest.get("publication_binding_authorized")):
        raise PublicationBindingManifestError("source manifest does not authorize publication binding")
    if not bool(promotion_manifest.get("copied_apply_ready")):
        raise PublicationBindingManifestError("source promotion manifest is not copied-apply-ready")
    if str(promotion_apply_report.get("status") or "").upper() != "PASS":
        raise PublicationBindingManifestError("source promotion apply report is not PASS")

    policy = source_manifest.get("economics_policy") or {}
    for item in policy.get("files") or []:
        policy_path = Path(str(item.get("path") or ""))
        expected_policy_sha = str(item.get("sha256") or "")
        if not policy_path.is_file() or sha256_file(policy_path) != expected_policy_sha:
            raise PublicationBindingManifestError(
                f"economics policy file drift: {policy_path}"
            )

    proof_terminal = source_proof.get("terminal_evidence") or {}
    terminal_date, terminal_ts = _completion_timestamp(api_header)
    if proof_terminal.get("terminal_date") != terminal_date:
        raise PublicationBindingManifestError("source proof terminal date differs from API completionDate")
    if proof_terminal.get("terminal_date_semantics") != "STATUS_CHANGE_TIMESTAMP_PROVEN":
        raise PublicationBindingManifestError("terminal status-change timestamp is not directly proven")
    if not bool(proof_terminal.get("publication_binding_authorized")):
        raise PublicationBindingManifestError("terminal evidence does not authorize publication binding")

    promotion_targets = promotion_manifest.get("targets") or []
    proof_lines = source_proof.get("line_proofs") or []
    if not promotion_targets or len(promotion_targets) != len(proof_lines):
        raise PublicationBindingManifestError("promotion/proof line count mismatch")
    promotion_by_sale = {int(row["sale_id"]): row for row in promotion_targets}
    proof_by_sale = {int(row["sale_id"]): row for row in proof_lines}
    if set(promotion_by_sale) != set(proof_by_sale):
        raise PublicationBindingManifestError("promotion/proof sale-id set mismatch")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity.lower() != "ok":
            raise PublicationBindingManifestError(f"copied DB integrity_check failed: {integrity}")
        anchors = conn.execute(
            """
            SELECT * FROM fact_sales_workbook_anchor
            WHERE CAST(order_id AS TEXT)=? AND UPPER(TRIM(store_code))=?
            """,
            (order_id, store_code),
        ).fetchall()
        if len(anchors) != 1:
            raise PublicationBindingManifestError(f"expected one workbook anchor, observed {len(anchors)}")
        anchor = _row_dict(anchors[0])

        sale_ids = sorted(promotion_by_sale)
        placeholders = ",".join("?" for _ in sale_ids)
        source_rows_raw = conn.execute(
            f"SELECT * FROM sales_fact_v2 WHERE sale_id IN ({placeholders}) ORDER BY sale_id",
            sale_ids,
        ).fetchall()
        if len(source_rows_raw) != len(sale_ids):
            raise PublicationBindingManifestError("current source sale-id set is incomplete")
        source_rows = [_row_dict(row) for row in source_rows_raw]

        old_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(view_sales_line_truth)")}
        if not set(OLD_PUBLIC_COLUMNS).issubset(old_columns):
            raise PublicationBindingManifestError("current selected view lacks required unbound columns")
        selected_all = [
            _row_dict(row)
            for row in conn.execute(
                f"SELECT {','.join(OLD_PUBLIC_COLUMNS)} FROM view_sales_line_truth"
            ).fetchall()
        ]
    finally:
        conn.close()

    targets: list[dict[str, Any]] = []
    selected_targets: list[dict[str, Any]] = []
    source_targets: list[dict[str, Any]] = []
    membership_rows: list[dict[str, Any]] = []
    bound_old_rows: list[dict[str, Any]] = []
    source_by_sale = {int(row["sale_id"]): row for row in source_rows}
    for ordinal, sale_id in enumerate(sale_ids, start=1):
        source_row = source_by_sale[sale_id]
        promotion = promotion_by_sale[sale_id]
        proof = proof_by_sale[sale_id]
        expected_after = promotion.get("after") or {}
        for field in (
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
            "status",
            "return_flag",
            "source_entry_id",
            "line_identity_key",
        ):
            if str(source_row.get(field)) != str(expected_after.get(field)):
                raise PublicationBindingManifestError(
                    f"source preimage drift for sale {sale_id} field {field}: "
                    f"{source_row.get(field)!r} != {expected_after.get(field)!r}"
                )

        matches = [
            row
            for row in selected_all
            if str(row.get("order_id")) == order_id
            and str(row.get("store_code") or "").upper() == store_code
            and str(row.get("source_table")) == "sales_fact_v2"
            and str(row.get("source_sku_key")) == str(source_row.get("sku_key"))
            and str(row.get("source_sku_id")) == str(source_row.get("sku_id"))
            and str(row.get("my_size")) == str(source_row.get("my_size"))
            and abs(float(row.get("source_units") or 0) - float(source_row.get("quantity") or 0)) <= 0.0001
            and abs(float(row.get("source_net_rev_kzt") or 0) - float(source_row.get("net_rev") or 0)) <= 0.01
        ]
        if len(matches) != 1:
            raise PublicationBindingManifestError(
                f"expected one current selected source line for sale {sale_id}, observed {len(matches)}"
            )
        selected = matches[0]
        selected_targets.append(selected)
        source_targets.append(source_row)
        membership_rows.append(
            {
                "order_id": order_id,
                "store_code": store_code,
                "source_table": "sales_fact_v2",
                "source_sku_key": selected["source_sku_key"],
                "source_sku_id": selected["source_sku_id"],
                "my_size": selected["my_size"],
                "source_units": selected["source_units"],
            }
        )
        bound_row = dict(selected)
        bound_row["sale_date"] = terminal_date
        bound_row["units"] = float(source_row["quantity"])
        bound_row["net_rev_kzt"] = round(float(source_row["net_rev"]), 2)
        bound_row["profit_kzt"] = (
            None
            if selected.get("cogs_kzt") is None
            else round(bound_row["net_rev_kzt"] - float(selected["cogs_kzt"]), 2)
        )
        bound_old_rows.append(bound_row)
        targets.append(
            {
                "line_ordinal": ordinal,
                "sale_id": sale_id,
                "source_entry_id": source_row.get("source_entry_id"),
                "line_identity_key": source_row.get("line_identity_key"),
                "source_row_preimage": source_row,
                "source_row_preimage_sha256": canonical_sha256(source_row),
                "unbound_selected_preimage": selected,
                "unbound_selected_preimage_sha256": canonical_sha256(selected),
                "entry_evidence_sha256": proof.get("entry_evidence_sha256"),
                "source_line_proof_sha256": proof.get("line_proof_sha256"),
                "promotion_target_sha256": promotion.get("target_sha256"),
                "publication": {
                    "sale_date": terminal_date,
                    "units": float(source_row["quantity"]),
                    "net_rev_kzt": round(float(source_row["net_rev"]), 2),
                },
                "expected_bound_old_columns": bound_row,
                "expected_bound_old_columns_sha256": canonical_sha256(bound_row),
            }
        )

    target_keys = {
        (
            str(row["order_id"]),
            str(row["store_code"]).upper(),
            str(row["source_table"]),
            str(row["source_sku_id"]),
            str(row["my_size"]),
        )
        for row in selected_targets
    }
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

    source_manifest_file_sha = sha256_file(source_sidecar_manifest_path)
    source_proof_file_sha = sha256_file(source_proof_path)
    promotion_manifest_file_sha = sha256_file(promotion_manifest_path)
    promotion_apply_file_sha = sha256_file(promotion_apply_report_path)
    api_header_sha = sha256_file(api_header_path)
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "operation": "COPIED_DB_EXACT_SALES_PUBLICATION_BINDING",
        "production_apply_authorized": False,
        "copied_apply_ready": True,
        "order_id": order_id,
        "store_code": store_code,
        "binding_id": f"PB-{order_id}-{store_code}-{terminal_date}-v1",
        "canonical_hash_version": CANONICAL_HASH_VERSION,
        "copied_db_path": str(db_path),
        "copied_db_sha256": _db_sha256(db_path),
        "copied_db_integrity_check": integrity,
        "publication_effective_date": terminal_date,
        "terminal_event_ts": terminal_ts,
        "terminal_date_semantics": "STATUS_CHANGE_TIMESTAMP_PROVEN",
        "provisional_flag": False,
        "expected_line_count": len(targets),
        "anchor_preimage": anchor,
        "anchor_preimage_sha256": canonical_sha256(anchor),
        "source_rows_multiset_sha256": _multiset_hash(source_targets, sort_fields=("sale_id",)),
        "unbound_selected_multiset_sha256": _multiset_hash(
            selected_targets,
            sort_fields=("order_id", "store_code", "source_sku_id", "my_size"),
        ),
        "target_membership_sha256": _multiset_hash(
            membership_rows,
            sort_fields=("order_id", "store_code", "source_sku_id", "my_size"),
        ),
        "expected_bound_old_columns_multiset_sha256": _multiset_hash(
            bound_old_rows,
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
        "truth_view_runtime_contract": truth_view_runtime_contract,
        "minimal_publication_schema_contract": (
            minimal_publication_schema_contract
        ),
        "economics_policy_sha256": source_manifest.get("economics_policy", {}).get("sha256"),
        "economics_policy_files": source_manifest.get("economics_policy", {}).get("files") or [],
        "source_proof_key": source_proof.get("proof_key"),
        "source_sidecar_manifest_path": str(source_sidecar_manifest_path.resolve()),
        "source_sidecar_manifest_file_sha256": source_manifest_file_sha,
        "source_sidecar_manifest_internal_sha256": source_manifest.get("manifest_sha256"),
        "source_proof_file_path": str(source_proof_path.resolve()),
        "source_proof_file_sha256": source_proof_file_sha,
        "promotion_manifest_path": str(promotion_manifest_path.resolve()),
        "promotion_manifest_file_sha256": promotion_manifest_file_sha,
        "promotion_manifest_internal_sha256": promotion_manifest.get("manifest_sha256"),
        "promotion_apply_report_path": str(promotion_apply_report_path.resolve()),
        "promotion_apply_report_sha256": promotion_apply_file_sha,
        "api_header_path": str(api_header_path.resolve()),
        "api_header_sha256": api_header_sha,
        "terminal_evidence_sha256": proof_terminal.get("safe_evidence_sha256"),
        "targets": targets,
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--order-id", required=True)
    parser.add_argument("--store-code", required=True)
    parser.add_argument("--source-sidecar-manifest", type=Path, required=True)
    parser.add_argument("--source-proof-file", type=Path, required=True)
    parser.add_argument("--promotion-manifest", type=Path, required=True)
    parser.add_argument("--promotion-apply-report", type=Path, required=True)
    parser.add_argument("--api-header", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(
        db_path=args.db,
        order_id=args.order_id,
        store_code=args.store_code,
        source_sidecar_manifest_path=args.source_sidecar_manifest,
        source_proof_path=args.source_proof_file,
        promotion_manifest_path=args.promotion_manifest,
        promotion_apply_report_path=args.promotion_apply_report,
        api_header_path=args.api_header,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "output": str(args.output), "manifest_sha256": manifest["manifest_sha256"], "target_count": len(manifest["targets"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
