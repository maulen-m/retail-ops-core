#!/usr/bin/env python3
"""Build a non-applying terminal-observation publication candidate manifest.

The input is the read-only publication/anchor reconciliation packet. Only rows
classified ``RECOMPUTE_SOURCE_FORMULA_AT_TERMINAL_OBSERVATION_CANDIDATE_DATE``
are considered. The
builder opens SQLite read-only, revalidates the terminal lifecycle preimages,
proves one exact ``sales_fact_v2`` source line, recomputes canonical net revenue
at the candidate observation date, and emits detached inactive header/line
candidates. Observation dates are never represented as exact status-change or
approved publication dates. The builder never edits source chronology, a
database, a workbook, or an external system.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.calc.economics import calc_net_rev  # noqa: E402
from scripts.build_publication_anchor_reconciliation_packet import (  # noqa: E402
    CANONICAL_HASH_VERSION,
    _load_lifecycle_evidence,
    _terminal_resolution,
)


ACTION = "RECOMPUTE_SOURCE_FORMULA_AT_TERMINAL_OBSERVATION_CANDIDATE_DATE"
OPERATION = "CANDIDATE_ONLY_INSERT_PUBLICATION_BINDING_HEADER_AND_LINES"
SCHEMA = "terminal_observation_publication_candidate_manifest_v2"
BINDING_VERSION = "publication-binding-candidate-v2"
AMOUNT_TOLERANCE = Decimal("0.01")
SOURCE_FIELDS = (
    "sale_id",
    "order_id",
    "order_date",
    "sku_key",
    "sku_id",
    "my_size",
    "kaspi_offer_name",
    "store_code",
    "quantity",
    "sell_price_kzt",
    "delivery_fee",
    "cogs",
    "net_rev",
    "profit",
    "status",
    "return_flag",
    "return_date",
    "ingested_at",
    "source_file",
    "api_updated_at",
    "source_entry_id",
    "kaspi_article",
    "line_identity_key",
)
SELECTED_FIELDS = (
    "source_table",
    "source_sku_key",
    "source_sku_id",
    "my_size",
    "source_units",
    "source_net_rev_kzt",
    "sale_date",
    "units",
    "net_rev_kzt",
)
POLICY_PATHS = (
    PROJECT_ROOT / "core/calc/economics.py",
    PROJECT_ROOT / "core/config/business_params.py",
    PROJECT_ROOT / "docs/inventory/Master_Inventory_Rules_v9.md",
    PROJECT_ROOT / "docs/validation/SALES_ECONOMICS_TRUTH_CONTRACT.md",
)


class ManifestError(RuntimeError):
    """Raised when a pinned input or exact-scope invariant changes."""


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _bool(value: Any) -> bool:
    return _text(value).lower() in {"1", "true", "yes"}


def _integer(value: Any) -> int:
    try:
        return int(_text(value))
    except (TypeError, ValueError) as exc:
        raise ManifestError(f"invalid integer value: {value!r}") from exc


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _connect_read_only(path: Path) -> sqlite3.Connection:
    resolved = path.expanduser().resolve()
    conn = sqlite3.connect(f"file:{resolved}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _read_packet(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {
        "order_id",
        "store_code",
        "source_formula_proven",
        "selected_sale_dates",
        "source_dates",
        "anchor_present",
        "anchor_row_sha256",
        "terminal_date_status",
        "terminal_date",
        "terminal_rank",
        "terminal_direct",
        "terminal_date_semantics",
        "terminal_activation_eligible",
        "terminal_evidence_count",
        "terminal_evidence_sha256",
        "terminal_all_positive_evidence_count",
        "terminal_all_positive_evidence_sha256",
        "terminal_later_positive_evidence_count",
        "terminal_later_positive_evidence_sha256",
        "terminal_negative_evidence_count",
        "terminal_negative_evidence_sha256",
        "canonical_hash_version",
        "negative_after_or_on_terminal",
        "next_action",
    }
    if not rows or not required.issubset(rows[0]):
        raise ManifestError("packet schema is missing required fields")
    return [row for row in rows if _text(row.get("next_action")) == ACTION]


def _normalized_source_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    return {field: row[field] for field in SOURCE_FIELDS}


def _normalized_selected_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    return {field: row[field] for field in SELECTED_FIELDS}


def _policy_evidence() -> tuple[list[dict[str, str]], str]:
    evidence: list[dict[str, str]] = []
    for path in POLICY_PATHS:
        if not path.is_file():
            raise ManifestError(f"policy input missing: {path}")
        evidence.append({"path": str(path.resolve()), "sha256": _sha256(path)})
    return evidence, _canonical_sha(evidence)


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"invalid {label}: {path}") from exc
    if not isinstance(value, dict):
        raise ManifestError(f"{label} is not a JSON object: {path}")
    return value


def _load_crm_provenance(
    *,
    proof_path: Path | None,
    manifest_path: Path | None,
    apply_report_path: Path | None,
    current_db_sha256: str,
) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, Any] | None]:
    supplied = [proof_path is not None, manifest_path is not None, apply_report_path is not None]
    if any(supplied) and not all(supplied):
        raise ManifestError(
            "CRM provenance requires proof JSONL, manifest, and copied-DB apply report"
        )
    if not any(supplied):
        return {}, None
    assert proof_path is not None
    assert manifest_path is not None
    assert apply_report_path is not None
    proof_path = proof_path.expanduser().resolve()
    manifest_path = manifest_path.expanduser().resolve()
    apply_report_path = apply_report_path.expanduser().resolve()
    for path in (proof_path, manifest_path, apply_report_path):
        if not path.is_file():
            raise ManifestError(f"CRM provenance input missing: {path}")

    manifest = _read_json(manifest_path, "CRM provenance manifest")
    apply_report = _read_json(apply_report_path, "CRM provenance apply report")
    proof_sha = _sha256(proof_path)
    manifest_file_sha = _sha256(manifest_path)
    apply_report_sha = _sha256(apply_report_path)
    if _text(manifest.get("schema")) != "sales_formula_provenance_crm_v4":
        raise ManifestError("CRM provenance schema is not v4")
    if Path(_text(manifest.get("proof_path"))).expanduser().resolve() != proof_path:
        raise ManifestError("CRM provenance proof path changed")
    if _text(manifest.get("proof_sha256")) != proof_sha:
        raise ManifestError("CRM provenance proof SHA-256 changed")
    if Path(_text(apply_report.get("manifest_path"))).expanduser().resolve() != manifest_path:
        raise ManifestError("CRM provenance apply manifest path changed")
    unsigned_manifest = dict(manifest)
    manifest_sha = _text(unsigned_manifest.pop("manifest_sha256", None))
    if manifest_sha != _canonical_sha(unsigned_manifest):
        raise ManifestError("CRM provenance internal manifest hash changed")
    if _text(apply_report.get("manifest_sha256")) != manifest_sha:
        raise ManifestError("CRM provenance apply manifest SHA-256 changed")
    if _text(apply_report.get("status")) != "PASS" or _text(
        apply_report.get("mode")
    ) != "APPLY":
        raise ManifestError("CRM copied-DB promotion was not a terminal PASS apply")
    if _text(apply_report.get("db_post_sha256")) != current_db_sha256:
        raise ManifestError("CRM promotion post-DB SHA-256 does not bind current copy")
    if _text(apply_report.get("db_pre_sha256")) != _text(manifest.get("db_sha256")):
        raise ManifestError("CRM provenance pre-DB lineage changed")
    if not bool(apply_report.get("table_counts_unchanged")):
        raise ManifestError("CRM promotion table counts were not preserved")
    readback_mismatch_count = apply_report.get("target_readback_mismatch_count")
    if int(readback_mismatch_count if readback_mismatch_count is not None else -1) != 0:
        raise ManifestError("CRM promotion target readback was not exact")
    if _text(apply_report.get("non_target_sales_fact_v2_sha256_before")) != _text(
        apply_report.get("non_target_sales_fact_v2_sha256_after")
    ):
        raise ManifestError("CRM promotion non-target source rows changed")

    workbook_path = Path(_text(manifest.get("workbook_path"))).expanduser().resolve()
    if not workbook_path.is_file():
        raise ManifestError(f"pinned CRM workbook is missing: {workbook_path}")
    workbook_sha = _sha256(workbook_path)
    if workbook_sha != _text(manifest.get("workbook_sha256")):
        raise ManifestError("pinned CRM workbook SHA-256 changed")

    proofs: dict[tuple[str, str], dict[str, Any]] = {}
    with proof_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                proof = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ManifestError(
                    f"invalid CRM proof JSONL line {line_number}"
                ) from exc
            key = (
                _text(proof.get("order_id")),
                _text(proof.get("store_code")).upper(),
            )
            if not all(key) or key in proofs:
                raise ManifestError(f"duplicate or blank CRM proof key: {key}")
            proofs[key] = proof
    proof_count = int(manifest.get("proof_count") or -1)
    if len(proofs) != proof_count:
        raise ManifestError(
            f"CRM proof count changed: {len(proofs)}/{proof_count}"
        )
    if int(apply_report.get("target_count") or -1) != proof_count:
        raise ManifestError("CRM promotion target count changed")
    context = {
        "schema": _text(manifest.get("schema")),
        "proof_path": str(proof_path),
        "proof_sha256": proof_sha,
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha,
        "manifest_file_sha256": manifest_file_sha,
        "apply_report_path": str(apply_report_path),
        "apply_report_sha256": apply_report_sha,
        "promotion_db_pre_sha256": _text(apply_report.get("db_pre_sha256")),
        "promotion_db_post_sha256": _text(apply_report.get("db_post_sha256")),
        "promotion_target_count": int(apply_report.get("target_count") or 0),
        "workbook_path": str(workbook_path),
        "workbook_sha256": workbook_sha,
        "workbook_sheet": _text(manifest.get("workbook_sheet")),
    }
    return proofs, context


def _same_decimal(left: Any, right: Any) -> bool:
    left_decimal = _decimal(left)
    right_decimal = _decimal(right)
    return (
        left_decimal is not None
        and right_decimal is not None
        and left_decimal == right_decimal
    )


def _crm_physical_identity(
    *,
    proof: dict[str, Any],
    source: dict[str, Any],
    context: dict[str, Any],
    delivery_total: Decimal,
    stored_net: Decimal,
) -> dict[str, Any]:
    if _text(proof.get("source_kind")) != "CRM_XLSX_PHYSICAL_ROW":
        raise ManifestError("CRM source identity kind changed")
    if _text(proof.get("evidence_status")) != "SOURCE_PROVEN_REPAIR_CANDIDATE":
        raise ManifestError("CRM source proof is not a repair candidate")
    if not bool(proof.get("repair_required")):
        raise ManifestError("CRM source proof was not promoted")
    if _text(proof.get("source_workbook_sha256")) != context["workbook_sha256"]:
        raise ManifestError("CRM source workbook identity changed")
    if Path(_text(proof.get("source_workbook_path"))).expanduser().resolve() != Path(
        context["workbook_path"]
    ):
        raise ManifestError("CRM source workbook path changed")
    if _text(proof.get("source_sheet")) != context["workbook_sheet"]:
        raise ManifestError("CRM source sheet changed")
    try:
        physical_row = int(proof.get("source_physical_row"))
    except (TypeError, ValueError) as exc:
        raise ManifestError("CRM physical row is invalid") from exc
    if physical_row <= 0:
        raise ManifestError("CRM physical row is invalid")
    for field in (
        "proof_key",
        "source_formula_row_sha256",
        "source_allowlisted_row_sha256",
        "db_row_sha256",
    ):
        if len(_text(proof.get(field))) != 64:
            raise ManifestError(f"CRM source proof field is invalid: {field}")
    proof_db_row = proof.get("db_row")
    if not isinstance(proof_db_row, dict) or _canonical_sha(proof_db_row) != _text(
        proof.get("db_row_sha256")
    ):
        raise ManifestError("CRM source DB preimage hash changed")

    exact_pairs = (
        (proof.get("sale_id"), source["sale_id"], "sale_id"),
        (proof.get("order_id"), source["order_id"], "order_id"),
        (proof.get("order_date"), _text(source["order_date"])[:10], "order_date"),
        (proof.get("store_code"), source["store_code"], "store_code"),
        (proof.get("sku_key"), source["sku_key"], "sku_key"),
        (proof.get("sku_id"), source["sku_id"], "sku_id"),
        (proof.get("size"), source["my_size"], "size"),
    )
    for expected, observed, label in exact_pairs:
        if _text(expected).upper() != _text(observed).upper():
            raise ManifestError(f"CRM source identity changed: {label}")
    for expected, observed, label in (
        (proof.get("quantity"), source["quantity"], "quantity"),
        (proof.get("unit_sell_price_kzt"), source["sell_price_kzt"], "sell_price"),
    ):
        if not _same_decimal(expected, observed):
            raise ManifestError(f"CRM source numeric identity changed: {label}")

    immutable_db_fields = (
        "sale_id",
        "order_id",
        "order_date",
        "sku_key",
        "sku_id",
        "my_size",
        "store_code",
        "source_file",
        "source_entry_id",
        "kaspi_article",
        "line_identity_key",
    )
    for field in immutable_db_fields:
        if _text(proof_db_row.get(field)).upper() != _text(source[field]).upper():
            raise ManifestError(f"CRM promoted source preimage changed: {field}")
    for field in ("quantity", "sell_price_kzt", "cogs"):
        left = proof_db_row.get(field)
        right = source[field]
        if left is None and right is None:
            continue
        if not _same_decimal(left, right):
            raise ManifestError(f"CRM promoted source numeric preimage changed: {field}")
    if not _same_decimal(proof.get("seller_delivery_fee_total_kzt"), delivery_total):
        raise ManifestError("CRM promoted delivery-fee readback changed")
    if not _same_decimal(proof.get("canonical_line_net_rev_kzt"), stored_net):
        raise ManifestError("CRM promoted canonical-net readback changed")

    return {
        "kind": "CRM_XLSX_PHYSICAL_ROW",
        "source_workbook_sha256": context["workbook_sha256"],
        "source_sheet": context["workbook_sheet"],
        "source_physical_row": physical_row,
        "source_formula_row_sha256": _text(
            proof.get("source_formula_row_sha256")
        ),
        "source_allowlisted_row_sha256": _text(
            proof.get("source_allowlisted_row_sha256")
        ),
        "proof_key": _text(proof.get("proof_key")),
        "proof_preimage": proof,
        "proof_preimage_sha256": _canonical_sha(proof),
        "proof_jsonl_sha256": context["proof_sha256"],
        "promotion_apply_report_sha256": context["apply_report_sha256"],
    }


def _validate_terminal_packet(
    packet: dict[str, str], terminal: dict[str, Any]
) -> None:
    if _text(packet["canonical_hash_version"]) != CANONICAL_HASH_VERSION:
        raise ManifestError("canonical hash version changed")
    exact_values = (
        (_text(packet["terminal_date_status"]), _text(terminal["status"]), "status"),
        (_text(packet["terminal_date"]), _text(terminal["canonical_date"]), "date"),
        (_text(packet["terminal_rank"]), _text(terminal["rank"]), "rank"),
    )
    for expected, observed, label in exact_values:
        if expected != observed:
            raise ManifestError(f"terminal {label} preimage changed")
    if _bool(packet["terminal_direct"]) != bool(terminal["direct"]):
        raise ManifestError("terminal direct flag changed")
    if _text(packet["terminal_date_semantics"]) != _text(
        terminal["date_semantics"]
    ):
        raise ManifestError("terminal date semantics changed")
    if _bool(packet["terminal_activation_eligible"]) != bool(
        terminal["activation_eligible"]
    ):
        raise ManifestError("terminal activation eligibility changed")
    if _bool(packet["negative_after_or_on_terminal"]) != bool(
        terminal["negative_after_or_on_terminal"]
    ):
        raise ManifestError("terminal negative guard changed")
    if _integer(packet["terminal_evidence_count"]) != len(terminal["evidence"]):
        raise ManifestError("terminal positive evidence count changed")
    if _text(packet["terminal_evidence_sha256"]) != _canonical_sha(
        terminal["evidence"]
    ):
        raise ManifestError("terminal positive evidence preimage changed")
    if _integer(packet["terminal_all_positive_evidence_count"]) != len(
        terminal["all_positive_evidence"]
    ):
        raise ManifestError("terminal all-positive evidence count changed")
    if _text(packet["terminal_all_positive_evidence_sha256"]) != _canonical_sha(
        terminal["all_positive_evidence"]
    ):
        raise ManifestError("terminal all-positive evidence preimage changed")
    if _integer(packet["terminal_later_positive_evidence_count"]) != len(
        terminal["later_positive_evidence"]
    ):
        raise ManifestError("terminal later-positive evidence count changed")
    if _text(packet["terminal_later_positive_evidence_sha256"]) != _canonical_sha(
        terminal["later_positive_evidence"]
    ):
        raise ManifestError("terminal later-positive evidence preimage changed")
    if _integer(packet["terminal_negative_evidence_count"]) != len(
        terminal["negative_evidence"]
    ):
        raise ManifestError("terminal negative evidence count changed")
    if _text(packet["terminal_negative_evidence_sha256"]) != _canonical_sha(
        terminal["negative_evidence"]
    ):
        raise ManifestError("terminal negative evidence preimage changed")


def build_manifest(
    *,
    db_path: Path,
    packet_csv: Path,
    output_path: Path,
    source_provenance_jsonl: Path | None = None,
    source_provenance_manifest: Path | None = None,
    source_provenance_apply_report: Path | None = None,
    expected_db_sha256: str | None = None,
    expected_packet_sha256: str | None = None,
    expected_target_count: int | None = None,
    expected_eligible_count: int | None = None,
    expected_cross_month_transition_count: int | None = None,
) -> dict[str, Any]:
    for path in (db_path, packet_csv):
        if not path.is_file():
            raise ManifestError(f"required input missing: {path}")
    db_sha_before = _sha256(db_path)
    packet_sha = _sha256(packet_csv)
    if expected_db_sha256 and db_sha_before != expected_db_sha256:
        raise ManifestError(
            f"DB SHA-256 changed: {db_sha_before}/{expected_db_sha256}"
        )
    if expected_packet_sha256 and packet_sha != expected_packet_sha256:
        raise ManifestError(
            f"packet SHA-256 changed: {packet_sha}/{expected_packet_sha256}"
        )

    packet_rows = _read_packet(packet_csv)
    keys = [
        (_text(row["order_id"]), _text(row["store_code"]).upper())
        for row in packet_rows
    ]
    if len(set(keys)) != len(keys):
        raise ManifestError("packet contains duplicate order/store target keys")
    if expected_target_count is not None and len(packet_rows) != expected_target_count:
        raise ManifestError(
            f"target count changed: {len(packet_rows)}/{expected_target_count}"
        )

    policy_evidence, policy_sha = _policy_evidence()
    crm_proofs, crm_provenance = _load_crm_provenance(
        proof_path=source_provenance_jsonl,
        manifest_path=source_provenance_manifest,
        apply_report_path=source_provenance_apply_report,
        current_db_sha256=db_sha_before,
    )
    targets: list[dict[str, Any]] = []
    exclusions: list[dict[str, str]] = []
    integrity = ""

    with _connect_read_only(db_path) as conn:
        integrity = _text(conn.execute("PRAGMA integrity_check").fetchone()[0])
        if integrity != "ok":
            raise ManifestError(f"DB integrity failed: {integrity}")
        required_objects = {
            ("table", "sales_fact_v2"),
            ("table", "fact_sales_workbook_anchor"),
            ("view", "view_sales_line_truth"),
        }
        for kind, name in required_objects:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type=? AND name=?", (kind, name)
            ).fetchone()
            if not exists:
                raise ManifestError(f"required {kind} missing: {name}")

        lifecycle = _load_lifecycle_evidence(conn, set(keys))
        key_tokens = [f"{order_id}|{store_code}" for order_id, store_code in keys]
        placeholders = ",".join("?" for _ in key_tokens)
        anchor_map: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
        source_map: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
        selected_map: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
        for row in conn.execute(
            "SELECT * FROM fact_sales_workbook_anchor WHERE "
            "(CAST(order_id AS TEXT) || '|' || UPPER(TRIM(store_code))) "
            f"IN ({placeholders})",
            key_tokens,
        ):
            anchor_map[(_text(row["order_id"]), _text(row["store_code"]).upper())].append(
                row
            )
        for row in conn.execute(
            "SELECT * FROM sales_fact_v2 WHERE "
            "(CAST(order_id AS TEXT) || '|' || UPPER(TRIM(store_code))) "
            f"IN ({placeholders})",
            key_tokens,
        ):
            source_map[(_text(row["order_id"]), _text(row["store_code"]).upper())].append(
                row
            )
        for row in conn.execute(
            "SELECT order_id, store_code, source_table, source_sku_key, "
            "source_sku_id, my_size, source_units, source_net_rev_kzt, "
            "sale_date, units, net_rev_kzt FROM view_sales_line_truth WHERE "
            "(CAST(order_id AS TEXT) || '|' || UPPER(TRIM(store_code))) "
            f"IN ({placeholders})",
            key_tokens,
        ):
            selected_map[
                (_text(row["order_id"]), _text(row["store_code"]).upper())
            ].append(row)
        for packet in sorted(
            packet_rows,
            key=lambda row: (
                _text(row["store_code"]).upper(),
                _text(row["order_id"]),
            ),
        ):
            order_id = _text(packet["order_id"])
            store_code = _text(packet["store_code"]).upper()
            try:
                if not order_id or not store_code:
                    raise ManifestError("blank order/store identity")
                if not _bool(packet["source_formula_proven"]):
                    raise ManifestError("source formula is not proven")
                if not _bool(packet["anchor_present"]):
                    raise ManifestError("workbook anchor is missing")

                terminal = _terminal_resolution(
                    lifecycle.get((order_id, store_code), [])
                )
                _validate_terminal_packet(packet, terminal)
                if (
                    terminal["status"]
                    != "DIRECT_TERMINAL_OBSERVATION_DATE_CANDIDATE"
                ):
                    raise ManifestError(
                        "terminal evidence is not a direct observation-date candidate"
                    )
                if not bool(terminal["direct"]):
                    raise ManifestError("terminal date direct flag is false")
                if bool(terminal["activation_eligible"]):
                    raise ManifestError(
                        "observation-date candidate unexpectedly activation eligible"
                    )
                if (
                    _text(terminal["date_semantics"])
                    != "TERMINAL_OBSERVATION_DATE_CANDIDATE"
                ):
                    raise ManifestError("terminal date semantics are not observational")
                if bool(terminal["negative_after_or_on_terminal"]):
                    raise ManifestError(
                        "negative lifecycle evidence conflicts with terminal date"
                    )
                candidate_date = date.fromisoformat(
                    _text(terminal["canonical_date"])
                )

                source_dates = set(
                    filter(None, _text(packet["source_dates"]).split("|"))
                )
                selected_dates = set(
                    filter(None, _text(packet["selected_sale_dates"]).split("|"))
                )
                if len(source_dates) != 1 or len(selected_dates) != 1:
                    raise ManifestError("source or selected date is not singular")
                source_date = date.fromisoformat(next(iter(source_dates)))
                selected_date = date.fromisoformat(next(iter(selected_dates)))
                if candidate_date <= source_date:
                    raise ManifestError(
                        "terminal observation candidate date does not advance source date"
                    )

                anchor_rows = anchor_map.get((order_id, store_code), [])
                if len(anchor_rows) != 1:
                    raise ManifestError(
                        f"workbook anchor count is not one: {len(anchor_rows)}"
                    )
                anchor = dict(anchor_rows[0])
                anchor_sha = _canonical_sha(anchor)
                if anchor_sha != _text(packet["anchor_row_sha256"]):
                    raise ManifestError("workbook anchor preimage hash changed")

                selected_rows = selected_map.get((order_id, store_code), [])
                if len(selected_rows) != 1:
                    raise ManifestError(
                        "selected published source-line count is not one: "
                        f"{len(selected_rows)}"
                    )
                selected = _normalized_selected_row(selected_rows[0])
                if _text(selected["source_table"]).lower() != "sales_fact_v2":
                    raise ManifestError("selected source is not sales_fact_v2")
                if _text(selected["sale_date"])[:10] != selected_date.isoformat():
                    raise ManifestError("selected publication date changed")
                selected_multiset = [selected]
                selected_multiset_sha = _canonical_sha(selected_multiset)

                source_rows = source_map.get((order_id, store_code), [])
                if len(source_rows) != 1:
                    raise ManifestError(
                        f"sales_fact_v2 source-line count is not one: {len(source_rows)}"
                    )
                source = _normalized_source_row(source_rows[0])
                if _text(source["order_date"])[:10] != source_date.isoformat():
                    raise ManifestError("source order date changed")
                if _text(source["status"]).upper() != "DELIVERED" or int(
                    source["return_flag"] or 0
                ) != 0:
                    raise ManifestError(
                        "source lifecycle is not delivered/non-returned"
                    )
                identity_pairs = (
                    (source["sku_key"], selected["source_sku_key"]),
                    (source["sku_id"], selected["source_sku_id"]),
                    (source["my_size"], selected["my_size"]),
                )
                if any(
                    _text(left) != _text(right) for left, right in identity_pairs
                ):
                    raise ManifestError("selected/source SKU identity changed")

                quantity = _decimal(source["quantity"])
                price = _decimal(source["sell_price_kzt"])
                delivery_total = _decimal(source["delivery_fee"])
                stored_net = _decimal(source["net_rev"])
                selected_source_units = _decimal(selected["source_units"])
                selected_source_net = _decimal(selected["source_net_rev_kzt"])
                if (
                    quantity is None
                    or quantity <= 0
                    or price is None
                    or delivery_total is None
                    or stored_net is None
                    or selected_source_units != quantity
                    or selected_source_net != stored_net
                ):
                    raise ManifestError(
                        "formula inputs or selected/source values changed"
                    )

                delivery_unit = delivery_total / quantity
                canonical_source = Decimal(
                    str(
                        round(
                            calc_net_rev(
                                float(price),
                                delivery_fee=float(delivery_unit),
                                as_of_date=source_date,
                            )
                            * float(quantity),
                            2,
                        )
                    )
                )
                if abs(canonical_source - stored_net) > AMOUNT_TOLERANCE:
                    raise ManifestError(
                        "source formula no longer reproduces stored net"
                    )
                canonical_candidate = Decimal(
                    str(
                        round(
                            calc_net_rev(
                                float(price),
                                delivery_fee=float(delivery_unit),
                                as_of_date=candidate_date,
                            )
                            * float(quantity),
                            2,
                        )
                    )
                )
                if _text(source["source_entry_id"]) and _text(
                    source["line_identity_key"]
                ):
                    source_identity = {
                        "kind": "API_ENTRY_AND_LINE_IDENTITY",
                        "source_entry_id": _text(source["source_entry_id"]),
                        "line_identity_key": _text(source["line_identity_key"]),
                    }
                else:
                    proof = crm_proofs.get((order_id, store_code))
                    if proof is None or crm_provenance is None:
                        raise ManifestError(
                            "immutable source identity is absent and no pinned CRM "
                            "physical-row proof is available"
                        )
                    source_identity = _crm_physical_identity(
                        proof=proof,
                        source=source,
                        context=crm_provenance,
                        delivery_total=delivery_total,
                        stored_net=stored_net,
                    )
                source_line_sha = _canonical_sha(source)
                source_multiset = [
                    {
                        "source_table": "sales_fact_v2",
                        "source_physical_row_id": {
                            "column": "sale_id",
                            "value": source["sale_id"],
                        },
                        "immutable_source_identity_sha256": _canonical_sha(
                            source_identity
                        ),
                        "source_row_sha256": source_line_sha,
                    }
                ]
                source_multiset_sha = _canonical_sha(source_multiset)
                selected_month = selected_date.strftime("%Y-%m")
                source_month = source_date.strftime("%Y-%m")
                candidate_month = candidate_date.strftime("%Y-%m")

                binding_header = {
                    "binding_version": BINDING_VERSION,
                    "binding_status": "CANDIDATE_VALIDATED_UNAPPLIED",
                    "provisional_flag": True,
                    "activation_eligible": False,
                    "activation_blocker": (
                        "TERMINAL_EFFECTIVE_DATE_POLICY_UNRESOLVED"
                    ),
                    "order_id": order_id,
                    "store_code": store_code,
                    "reason": ACTION,
                    "candidate_publication_date": candidate_date.isoformat(),
                    "terminal_date_semantics": terminal["date_semantics"],
                    "workbook_anchor_sha256": anchor_sha,
                    "selected_source_line_multiset_sha256": selected_multiset_sha,
                    "source_line_multiset_sha256": source_multiset_sha,
                    "terminal_evidence_sha256": _canonical_sha(
                        terminal["evidence"]
                    ),
                    "terminal_all_positive_evidence_sha256": _canonical_sha(
                        terminal["all_positive_evidence"]
                    ),
                    "terminal_later_positive_evidence_sha256": _canonical_sha(
                        terminal["later_positive_evidence"]
                    ),
                    "terminal_negative_evidence_sha256": _canonical_sha(
                        terminal["negative_evidence"]
                    ),
                    "terminal_rank": terminal["rank"],
                    "policy_sha256": policy_sha,
                    "copied_db_sha256": db_sha_before,
                    "canonical_hash_version": CANONICAL_HASH_VERSION,
                }
                binding_line = {
                    "line_ordinal": 1,
                    "source_table": "sales_fact_v2",
                    "source_physical_row_id": {
                        "column": "sale_id",
                        "value": source["sale_id"],
                    },
                    "source_entry_id": _text(source["source_entry_id"]),
                    "line_identity_key": _text(source["line_identity_key"]),
                    "immutable_source_identity": source_identity,
                    "immutable_source_identity_sha256": _canonical_sha(
                        source_identity
                    ),
                    "source_row_preimage": source,
                    "source_row_sha256": source_line_sha,
                    "source_original_date": source_date.isoformat(),
                    "candidate_publication_date": candidate_date.isoformat(),
                    "candidate_units": _decimal_text(quantity),
                    "candidate_net_rev_kzt": _decimal_text(canonical_candidate),
                    "stored_source_net_rev_kzt": _decimal_text(stored_net),
                    "canonical_source_date_net_rev_kzt": _decimal_text(
                        canonical_source
                    ),
                }
                targets.append(
                    {
                        "target_key": {
                            "order_id": order_id,
                            "store_code": store_code,
                        },
                        "operation": OPERATION,
                        "source_rows_immutable": True,
                        "workbook_anchor_preimage": anchor,
                        "workbook_anchor_sha256": anchor_sha,
                        "selected_source_line_preimages": selected_multiset,
                        "selected_source_line_multiset_sha256": selected_multiset_sha,
                        "terminal_evidence": {
                            "candidate_date": candidate_date.isoformat(),
                            "status": terminal["status"],
                            "rank": terminal["rank"],
                            "direct": terminal["direct"],
                            "date_semantics": terminal["date_semantics"],
                            "activation_eligible": False,
                            "activation_blocker": (
                                "TERMINAL_EFFECTIVE_DATE_POLICY_UNRESOLVED"
                            ),
                            "top_rank_positive_preimages": terminal["evidence"],
                            "top_rank_positive_sha256": _canonical_sha(
                                terminal["evidence"]
                            ),
                            "all_positive_preimages": terminal[
                                "all_positive_evidence"
                            ],
                            "all_positive_sha256": _canonical_sha(
                                terminal["all_positive_evidence"]
                            ),
                            "later_positive_preimages": terminal[
                                "later_positive_evidence"
                            ],
                            "later_positive_sha256": _canonical_sha(
                                terminal["later_positive_evidence"]
                            ),
                            "negative_preimages": terminal["negative_evidence"],
                            "negative_sha256": _canonical_sha(
                                terminal["negative_evidence"]
                            ),
                            "negative_after_or_on_terminal": terminal[
                                "negative_after_or_on_terminal"
                            ],
                        },
                        "binding_header_candidate": binding_header,
                        "binding_line_candidates": [binding_line],
                        "cohort_transition": {
                            "selected_publication_month_before": selected_month,
                            "source_chronology_month_unchanged": source_month,
                            "candidate_publication_month": candidate_month,
                            "selected_to_candidate_cross_month": selected_month
                            != candidate_month,
                            "source_to_candidate_cross_month": source_month
                            != candidate_month,
                            "candidate_transition_only": True,
                        },
                        "formula": {
                            "source_date": source_date.isoformat(),
                            "candidate_terminal_observation_date": (
                                candidate_date.isoformat()
                            ),
                            "quantity": _decimal_text(quantity),
                            "sell_price_kzt": _decimal_text(price),
                            "delivery_fee_line_total_kzt": _decimal_text(
                                delivery_total
                            ),
                            "delivery_fee_unit_kzt": _decimal_text(delivery_unit),
                            "stored_net_rev_kzt": _decimal_text(stored_net),
                            "canonical_source_date_net_rev_kzt": _decimal_text(
                                canonical_source
                            ),
                            "canonical_candidate_observation_date_net_rev_kzt": _decimal_text(
                                canonical_candidate
                            ),
                            "candidate_minus_source_net_rev_kzt": _decimal_text(
                                canonical_candidate - canonical_source
                            ),
                        },
                    }
                )
            except (ManifestError, ValueError) as exc:
                exclusions.append(
                    {
                        "order_id": order_id,
                        "store_code": store_code,
                        "reason": str(exc),
                    }
                )

    db_sha_after = _sha256(db_path)
    if db_sha_after != db_sha_before:
        raise ManifestError("DB bytes changed during read-only manifest build")
    if expected_eligible_count is not None and len(targets) != expected_eligible_count:
        raise ManifestError(
            f"eligible count changed: {len(targets)}/{expected_eligible_count}; "
            f"exclusions={len(exclusions)}"
        )

    physical_ids = [
        (
            target["binding_line_candidates"][0]["source_table"],
            target["binding_line_candidates"][0]["source_physical_row_id"]["value"],
        )
        for target in targets
    ]
    if len(physical_ids) != len(set(physical_ids)):
        raise ManifestError("source physical row identity is not unique")
    immutable_line_ids = [
        target["binding_line_candidates"][0][
            "immutable_source_identity_sha256"
        ]
        for target in targets
    ]
    if len(immutable_line_ids) != len(set(immutable_line_ids)):
        raise ManifestError("immutable source line identity is not unique")

    cross_month_count = sum(
        bool(target["cohort_transition"]["selected_to_candidate_cross_month"])
        for target in targets
    )
    if (
        expected_cross_month_transition_count is not None
        and cross_month_count != expected_cross_month_transition_count
    ):
        raise ManifestError(
            "cross-month transition count changed: "
            f"{cross_month_count}/{expected_cross_month_transition_count}"
        )
    transition_counts = Counter(
        (
            target["cohort_transition"]["selected_publication_month_before"],
            target["cohort_transition"]["candidate_publication_month"],
        )
        for target in targets
    )
    transition_summary = {
        f"{before}->{after}": count
        for (before, after), count in sorted(transition_counts.items())
    }
    target_keys = [
        [target["target_key"]["order_id"], target["target_key"]["store_code"]]
        for target in targets
    ]
    binding_payload = {
        "schema": SCHEMA,
        "canonical_hash_version": CANONICAL_HASH_VERSION,
        "operation": OPERATION,
        "candidate_transition_only": True,
        "activation_eligible_count": 0,
        "activation_blocked_count": len(targets),
        "db_sha256": db_sha_before,
        "packet_csv_sha256": packet_sha,
        "policy_sha256": policy_sha,
        "crm_source_provenance": crm_provenance,
        "target_key_sha256": _canonical_sha(target_keys),
        "targets": targets,
    }
    binding_payload_sha = _canonical_sha(binding_payload)
    for target in targets:
        target["binding_header_candidate"][
            "originating_manifest_payload_sha256"
        ] = binding_payload_sha

    result: dict[str, Any] = {
        "schema": SCHEMA,
        "canonical_hash_version": CANONICAL_HASH_VERSION,
        "binding_version": BINDING_VERSION,
        "generated_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "read_only_builder": True,
        "production_write_authorized": False,
        "writer_or_apply_path_exists": False,
        "operation": OPERATION,
        "candidate_transition_only": True,
        "activation_eligible_count": 0,
        "activation_blocked_count": len(targets),
        "source_rows_immutable": True,
        "db_path": str(db_path.resolve()),
        "db_sha256_before": db_sha_before,
        "db_sha256_after": db_sha_after,
        "db_integrity": integrity,
        "packet_csv": str(packet_csv.resolve()),
        "packet_csv_sha256": packet_sha,
        "policy_evidence": policy_evidence,
        "policy_sha256": policy_sha,
        "crm_source_provenance": crm_provenance,
        "target_count": len(packet_rows),
        "eligible_count": len(targets),
        "exclusion_count": len(exclusions),
        "line_count": sum(
            len(target["binding_line_candidates"]) for target in targets
        ),
        "cross_month_transition_count": cross_month_count,
        "candidate_cross_month_transition_count": cross_month_count,
        "cohort_transition_counts": transition_summary,
        "target_key_sha256": _canonical_sha(target_keys),
        "binding_payload_sha256": binding_payload_sha,
        "scope_note": (
            "This exact target cohort is one selected and one source line per "
            "order/store. Any multi-line order requires explicit child-line "
            "candidates and is outside this manifest."
        ),
        "targets": targets,
        "exclusions": exclusions,
    }
    result["manifest_sha256"] = _canonical_sha(
        {
            key: value
            for key, value in result.items()
            if key not in {"generated_at", "manifest_sha256"}
        }
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--packet-csv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-provenance-jsonl", type=Path)
    parser.add_argument("--source-provenance-manifest", type=Path)
    parser.add_argument("--source-provenance-apply-report", type=Path)
    parser.add_argument("--expected-db-sha256")
    parser.add_argument("--expected-packet-sha256")
    parser.add_argument("--expected-target-count", type=int)
    parser.add_argument("--expected-eligible-count", type=int)
    parser.add_argument("--expected-cross-month-transition-count", type=int)
    return parser


def main() -> int:
    args = _parser().parse_args()
    result = build_manifest(
        db_path=args.db,
        packet_csv=args.packet_csv,
        output_path=args.output,
        source_provenance_jsonl=args.source_provenance_jsonl,
        source_provenance_manifest=args.source_provenance_manifest,
        source_provenance_apply_report=args.source_provenance_apply_report,
        expected_db_sha256=args.expected_db_sha256,
        expected_packet_sha256=args.expected_packet_sha256,
        expected_target_count=args.expected_target_count,
        expected_eligible_count=args.expected_eligible_count,
        expected_cross_month_transition_count=args.expected_cross_month_transition_count,
    )
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "manifest_sha256": result["manifest_sha256"],
                "target_count": result["target_count"],
                "eligible_count": result["eligible_count"],
                "exclusion_count": result["exclusion_count"],
                "cross_month_transition_count": result[
                    "cross_month_transition_count"
                ],
                "production_write_authorized": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
