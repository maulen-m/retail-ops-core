#!/usr/bin/env python3
"""Build a review-only cross-repo business event packet."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "exports" / "validation"
V4_GLOB = "inventory_capital_po_decision_v4_line31_inbound_integration_proposal_*"
SCHEMA_VERSION = "cross_repo_business_event_v1"
PROTECTED_SURFACES = [
    REPO_ROOT / "db" / "app.db",
    REPO_ROOT / "excel_ui" / "SALES_KSP_CRM_V3.xlsx",
]

INBOUND_EVENT_TYPES = {
    "PO1A_NON_OLIVE_ARRIVED_ASTANA": "PO_INBOUND_ASTANA_CANDIDATE",
    "PO1O_CARDAMOM_OLIVE_IN_TRANSIT_BASE_PAID": "PO_IN_TRANSIT_YIWU_RECEIPT_CANDIDATE",
}

PACKAGING_EVENT_TYPES = {
    "advance paid and supplier acknowledged": "SUPPLIER_PREPAYMENT_ACKED",
    "1000 branded outer bags": "PACKAGING_MATERIAL_ALLOCATION_CONFIRMED",
    "2000 universal W3 hangtags/cards": "PACKAGING_MATERIAL_ALLOCATION_PENDING_CONFIRMATION",
    "material subtotal": "PACKAGING_MATERIAL_SUBTOTAL_WORKING",
    "unused after materials": "PACKAGING_ADVANCE_CREDIT_WORKING",
    "strict unallocated until hangtag confirmed": "PACKAGING_ADVANCE_UNALLOCATED_STRICT",
    "hangtag/bag-changing labor": "PACKAGING_LABOR_RESERVE_WORKING",
    "3-in-1 outer-bag packing labor": "PACKAGING_LABOR_RESERVE_WORKING",
    "packaging plus labor subtotal": "PACKAGING_AND_LABOR_RESERVE_WORKING",
    "unused after material plus labor reserve": "PACKAGING_ADVANCE_CREDIT_WORKING",
    "working next-branded LINE31 total": "WORKING_PO_TOTAL_ESTIMATE",
    "working balance due after advance": "WORKING_BALANCE_DUE_ESTIMATE",
}

EVENT_COLUMNS = [
    "event_id",
    "event_schema_version",
    "bridge_run_id",
    "created_at",
    "event_type",
    "event_time",
    "event_time_basis",
    "source_repo",
    "source_path",
    "source_sha256",
    "source_exists",
    "source_ref",
    "po_id",
    "po_line_id",
    "product_family",
    "sku_key",
    "sku_id",
    "size",
    "color",
    "quantity",
    "unit",
    "amount",
    "currency",
    "amount_kzt",
    "fx_basis",
    "counterparty",
    "location",
    "status",
    "inventory_treatment",
    "cash_treatment",
    "confidence",
    "gate",
    "requires_owner_action",
    "notes",
    "raw_payload",
]


class BridgeError(RuntimeError):
    """Raised when a bridge packet cannot be safely generated."""


@dataclass(frozen=True)
class SourceRecord:
    path: str
    source_repo: str
    exists: bool
    sha256: str
    recorded_sha256: str
    hash_matches_recorded: bool | None
    size_bytes: int
    mtime_ns: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def infer_source_repo(path: Path) -> str:
    text = str(path)
    if "/Docs/Autonomous_business/" in text:
        return "Autonomous_business"
    if "/Cowork/Projects/Sourcing-Research/" in text:
        return "Sourcing-Research"
    if "/Cowork/Projects/E-commerce/" in text:
        return "E-commerce"
    return "UNKNOWN"


def source_record(path: Path, recorded_sha256: str = "") -> SourceRecord:
    resolved = path.expanduser().resolve()
    exists = resolved.exists()
    current_sha = sha256_file(resolved) if exists and resolved.is_file() else ""
    stat = resolved.stat() if exists else None
    hash_matches: bool | None
    if not recorded_sha256:
        hash_matches = None
    else:
        hash_matches = exists and current_sha == recorded_sha256
    return SourceRecord(
        path=str(resolved),
        source_repo=infer_source_repo(resolved),
        exists=exists,
        sha256=current_sha,
        recorded_sha256=recorded_sha256,
        hash_matches_recorded=hash_matches,
        size_bytes=stat.st_size if stat else 0,
        mtime_ns=stat.st_mtime_ns if stat else 0,
    )


def find_latest_v4_root(output_root: Path) -> Path:
    candidates = sorted(path for path in output_root.glob(V4_GLOB) if path.is_dir())
    if not candidates:
        raise BridgeError(f"no V4 proposal folder found under {output_root}")
    return candidates[-1]


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise BridgeError(f"missing required CSV: {path}")
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise BridgeError(f"missing required manifest: {path}")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def stable_event_id(event: dict[str, str]) -> str:
    stable_fields = {
        key: event.get(key, "")
        for key in (
            "event_type",
            "source_path",
            "source_ref",
            "po_id",
            "po_line_id",
            "sku_key",
            "size",
            "quantity",
            "amount",
            "currency",
            "raw_payload",
        )
    }
    payload = json.dumps(stable_fields, ensure_ascii=True, sort_keys=True)
    return "cbev1_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def event_gate(confidence: str, blocker: str, status: str, treatment: str) -> tuple[str, bool]:
    combined = " ".join([confidence, blocker, status, treatment]).upper()
    needs_owner = bool(blocker) or "PENDING" in combined or "UNVERIFIED" in combined or "REVIEW" in combined
    if "RED" in combined:
        return "RED", True
    if needs_owner or confidence.upper() in {"LOW", "MEDIUM"} or "WORKING" in combined or "ESTIMATE" in combined:
        return "YELLOW", needs_owner
    return "GREEN", False


def make_event(
    *,
    run_id: str,
    created_at: str,
    event_type: str,
    source: SourceRecord,
    source_ref: str,
    event_time: str = "",
    event_time_basis: str = "",
    po_id: str = "",
    po_line_id: str = "",
    product_family: str = "",
    sku_key: str = "",
    sku_id: str = "",
    size: str = "",
    color: str = "",
    quantity: str = "",
    unit: str = "",
    amount: str = "",
    currency: str = "",
    amount_kzt: str = "",
    fx_basis: str = "",
    counterparty: str = "",
    location: str = "",
    status: str = "",
    inventory_treatment: str = "",
    cash_treatment: str = "",
    confidence: str = "HIGH",
    gate: str | None = None,
    requires_owner_action: bool | None = None,
    notes: str = "",
    raw_payload: dict[str, Any] | None = None,
) -> dict[str, str]:
    raw = raw_payload or {}
    if gate is None or requires_owner_action is None:
        computed_gate, computed_owner = event_gate(confidence, notes, status, " ".join([inventory_treatment, cash_treatment]))
        gate = gate or computed_gate
        requires_owner_action = computed_owner if requires_owner_action is None else requires_owner_action
    event = {
        "event_id": "",
        "event_schema_version": SCHEMA_VERSION,
        "bridge_run_id": run_id,
        "created_at": created_at,
        "event_type": event_type,
        "event_time": event_time,
        "event_time_basis": event_time_basis,
        "source_repo": source.source_repo,
        "source_path": source.path,
        "source_sha256": source.sha256,
        "source_exists": str(source.exists).lower(),
        "source_ref": source_ref,
        "po_id": po_id,
        "po_line_id": po_line_id,
        "product_family": product_family,
        "sku_key": sku_key,
        "sku_id": sku_id,
        "size": size,
        "color": color,
        "quantity": quantity,
        "unit": unit,
        "amount": amount,
        "currency": currency,
        "amount_kzt": amount_kzt,
        "fx_basis": fx_basis,
        "counterparty": counterparty,
        "location": location,
        "status": status,
        "inventory_treatment": inventory_treatment,
        "cash_treatment": cash_treatment,
        "confidence": confidence,
        "gate": gate,
        "requires_owner_action": str(bool(requires_owner_action)).lower(),
        "notes": notes,
        "raw_payload": json.dumps(raw, ensure_ascii=True, sort_keys=True),
    }
    event["event_id"] = stable_event_id(event)
    return event


def build_source_records(v4_root: Path, source_manifest: dict[str, Any]) -> list[SourceRecord]:
    rows: list[SourceRecord] = []
    for name in [
        "v4_line31_inbound_integration_proposal.md",
        "v4_line31_inbound_candidates.csv",
        "v4_line31_next_branded_packaging_advance.csv",
        "v4_line31_source_manifest.json",
    ]:
        rows.append(source_record(v4_root / name))
    for source in source_manifest.get("source_files", []):
        rows.append(source_record(Path(source["path"]), source.get("sha256", "")))
    return rows


def source_by_path(records: Iterable[SourceRecord]) -> dict[str, SourceRecord]:
    return {record.path: record for record in records}


def build_inbound_events(
    rows: list[dict[str, str]],
    *,
    run_id: str,
    created_at: str,
    source: SourceRecord,
) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    for idx, row in enumerate(rows, start=1):
        route = row["route_label"]
        event_type = INBOUND_EVENT_TYPES.get(route, "PO_INBOUND_SOURCE_ROW")
        mapping_status = row.get("mapping_status", "")
        blocker = row.get("blocker", "")
        confidence = row.get("confidence", "HIGH")
        gate, needs_owner = event_gate(
            confidence,
            blocker,
            mapping_status,
            " ".join([row.get("physical_stock_treatment", ""), row.get("economic_stock_treatment", "")]),
        )
        po_id = "PO1A_NON_OLIVE" if route == "PO1A_NON_OLIVE_ARRIVED_ASTANA" else "PO1O_CARDAMOM_OLIVE"
        location = "Astana cargo pickup warehouse" if route == "PO1A_NON_OLIVE_ARRIVED_ASTANA" else "Cargo 525 Yiwu"
        events.append(
            make_event(
                run_id=run_id,
                created_at=created_at,
                event_type=event_type,
                source=source,
                source_ref=route,
                event_time=row.get("source_event_time", ""),
                event_time_basis="source_event_time from V4 inbound candidate sidecar",
                po_id=po_id,
                po_line_id=f"{route}:{idx:03d}",
                product_family="LINE31",
                sku_key=row.get("sku_key_candidate", ""),
                size=row.get("size", ""),
                color=row.get("source_set_color", ""),
                quantity=row.get("quantity", ""),
                unit="sets",
                location=location,
                status=mapping_status,
                inventory_treatment=row.get("physical_stock_treatment", ""),
                cash_treatment=row.get("capital_treatment", ""),
                confidence=confidence,
                gate=gate,
                requires_owner_action=needs_owner,
                notes=blocker or row.get("mapping_note", ""),
                raw_payload=row,
            )
        )
        if mapping_status.startswith("QUARANTINE"):
            events.append(
                make_event(
                    run_id=run_id,
                    created_at=created_at,
                    event_type="SOURCE_MAPPING_QUARANTINE",
                    source=source,
                    source_ref=route,
                    event_time=row.get("source_event_time", ""),
                    event_time_basis="same source row as quarantined inbound candidate",
                    po_id=po_id,
                    po_line_id=f"{route}:{idx:03d}:quarantine",
                    product_family="LINE31",
                    sku_key=row.get("sku_key_candidate", ""),
                    size=row.get("size", ""),
                    color=row.get("source_set_color", ""),
                    quantity=row.get("quantity", ""),
                    unit="sets",
                    location=location,
                    status=mapping_status,
                    inventory_treatment="keep out of applied stock until owner/rebuild mapping review",
                    cash_treatment="keep capital treatment visible but not applied",
                    confidence="MEDIUM",
                    gate="YELLOW",
                    requires_owner_action=True,
                    notes=blocker or row.get("mapping_note", ""),
                    raw_payload=row,
                )
            )
    return events


def package_gate(row: dict[str, str], event_type: str) -> tuple[str, bool]:
    status = row.get("supplier_confirmed_state", "")
    line = row.get("line_item", "")
    treatment = row.get("v4_treatment", "")
    combined = " ".join([event_type, status, line, treatment]).upper()
    if "ACKNOWLEDGED" in combined or "STRICTLY_CONFIRMED" in combined:
        return "GREEN", False
    if "PENDING" in combined or "WORKING" in combined or "RESERVE" in combined or "ESTIMATE" in combined:
        return "YELLOW", True
    return "YELLOW", False


def build_packaging_events(
    rows: list[dict[str, str]],
    *,
    run_id: str,
    created_at: str,
    source: SourceRecord,
) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    for idx, row in enumerate(rows, start=1):
        line_item = row.get("line_item", "")
        event_type = PACKAGING_EVENT_TYPES.get(line_item, "PACKAGING_SOURCE_ROW")
        gate, needs_owner = package_gate(row, event_type)
        events.append(
            make_event(
                run_id=run_id,
                created_at=created_at,
                event_type=event_type,
                source=source,
                source_ref=row.get("route_label", "NEXT_BRANDED_LINE31_INTERNAL_PO1B_PACKAGING_ADVANCE"),
                event_time="2026-05-20/2026-05-21",
                event_time_basis="payment proof visible 2026-05-20 and supplier acknowledgement visible 2026-05-21 where applicable",
                po_id="NEXT_BRANDED_LINE31_INTERNAL_PO1B",
                po_line_id=f"PACKAGING_ADVANCE:{idx:03d}",
                product_family="LINE31",
                amount=row.get("amount_cny", ""),
                currency="CNY",
                fx_basis="no KZT conversion in bridge packet; downstream cash ledger must provide canonical FX",
                counterparty="Juyitang/ARC via Tracy",
                status=row.get("supplier_confirmed_state", ""),
                inventory_treatment="not stock quantity; packaging/prepayment/payables lane only",
                cash_treatment=row.get("v4_treatment", ""),
                confidence="HIGH" if gate == "GREEN" else "MEDIUM",
                gate=gate,
                requires_owner_action=needs_owner,
                notes=f"{line_item}: {row.get('basis', '')}",
                raw_payload=row,
            )
        )
    return events


def build_summary_events(
    manifest: dict[str, Any],
    *,
    run_id: str,
    created_at: str,
    source: SourceRecord,
) -> list[dict[str, str]]:
    owner_truth = manifest.get("owner_current_turn_truth", {})
    source_summary = manifest.get("source_summary", {})
    timing_note = owner_truth.get("next_branded_line31_po1b_timing_risk_note", {})
    return [
        make_event(
            run_id=run_id,
            created_at=created_at,
            event_type="PO1O_SUPPLIER_BASE_PAYMENT_ACKED",
            source=source,
            source_ref="owner_current_turn_truth.po1o_payment_state",
            event_time="2026-05-11",
            event_time_basis="supplier acknowledgement source is included in V4 manifest",
            po_id="PO1O_CARDAMOM_OLIVE",
            product_family="LINE31",
            quantity=str(source_summary.get("po1o_qty_total", "")),
            unit="sets",
            amount=str(owner_truth.get("po1o_paid_total_cny_attributable", "")),
            currency="CNY",
            counterparty="Juyitang/ARC via Tracy",
            location="supplier side",
            status=str(owner_truth.get("po1o_payment_state", "")),
            inventory_treatment="in-transit inventory base cost paid; not warehouse stock until Astana receipt",
            cash_treatment="do not subtract base cost again if latest cash snapshot already reflects paid cash",
            confidence="HIGH",
            gate="GREEN",
            requires_owner_action=False,
            notes="PO-1O supplier-side garment/base cost is recorded as fully paid and acknowledged.",
            raw_payload={"owner_current_turn_truth": owner_truth},
        ),
        make_event(
            run_id=run_id,
            created_at=created_at,
            event_type="PO1O_FREIGHT_PAYABLE_OPEN",
            source=source,
            source_ref="source_summary.po1o_internal_freight_estimate",
            event_time=str(source_summary.get("po1o_internal_eta_planning_only", "")),
            event_time_basis="planning ETA only; not final Astana receipt truth",
            po_id="PO1O_CARDAMOM_OLIVE",
            product_family="LINE31",
            quantity=str(source_summary.get("po1o_qty_total", "")),
            unit="sets",
            amount=str(source_summary.get("po1o_internal_freight_estimate_usd", "")),
            currency="USD",
            amount_kzt=str(source_summary.get("po1o_internal_freight_estimate_kzt", "")),
            fx_basis="internal freight estimate from V4 source summary; final invoice/payment open",
            counterparty="Cargo 525 / international freight",
            location="Yiwu to Astana",
            status=str(owner_truth.get("po1o_freight_payment_state", "")),
            inventory_treatment="delivery component remains provisional until final freight evidence",
            cash_treatment="open payable estimate; not paid in repo evidence",
            confidence="MEDIUM",
            gate="YELLOW",
            requires_owner_action=True,
            notes="Final international freight and Astana receiving remain open.",
            raw_payload={"source_summary": source_summary},
        ),
        make_event(
            run_id=run_id,
            created_at=created_at,
            event_type="OWNER_REPORTED_TIMING_RULE_PENDING_EVIDENCE",
            source=source,
            source_ref="owner_current_turn_truth.next_branded_line31_po1b_timing_risk_note",
            event_time="2026-05-29/2026-05-30",
            event_time_basis="owner-reported 7-day garment reservation lead; screenshot-backed source still needed",
            po_id="NEXT_BRANDED_LINE31_INTERNAL_PO1B",
            product_family="LINE31",
            amount=str(timing_note.get("payment_implication", {}).get("safest_cash_target_ready_cny", "")),
            currency="CNY",
            counterparty="Juyitang/ARC via Tracy",
            status=str(timing_note.get("verification_state", "")),
            inventory_treatment="timing risk only; not stock",
            cash_treatment="cash readiness planning signal only; not payment authority",
            confidence="LOW",
            gate="YELLOW",
            requires_owner_action=True,
            notes=str(timing_note.get("owner_reported_unverified_point", "")),
            raw_payload={"timing_note": timing_note},
        ),
    ]


def write_jsonl(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def write_review_inbox(path: Path, manifest: dict[str, Any]) -> None:
    lines = [
        "# Cross-Repo Business Event Bridge V1 Review Inbox",
        "",
        f"Run ID: `{manifest['run_id']}`",
        f"Created: `{manifest['created_at']}`",
        f"Gate: `{manifest['gate']}`",
        "",
        "## What This Packet Is",
        "",
        "This is a review-only normalized event packet. It can be inspected by owner, CodeCaptain, or a later write-gated lane. It is not production truth and was not applied to DB, workbook, source pointers, external systems, stock, price, cash, PO, or ads.",
        "",
        "## Files",
        "",
        "- `business_events.jsonl`",
        "- `business_events.csv`",
        "- `event_bridge_manifest.json`",
        "- `source_files_manifest.csv`",
        "- `review_inbox.md`",
        "- `closeout.md`",
        "",
        "## Counts",
        "",
        f"- events: `{manifest['event_count']}`",
        f"- source files: `{manifest['source_file_count']}`",
        f"- missing source files: `{manifest['source_missing_count']}`",
        f"- source hash mismatches: `{manifest['source_hash_mismatch_count']}`",
        "",
        "## Events By Type",
        "",
    ]
    for event_type, count in sorted(manifest["events_by_type"].items()):
        lines.append(f"- `{event_type}`: `{count}`")
    lines.extend(["", "## Events By Gate", ""])
    for gate, count in sorted(manifest["events_by_gate"].items()):
        lines.append(f"- `{gate}`: `{count}`")
    lines.extend(["", "## Review Notes", ""])
    for note in manifest["review_notes"]:
        lines.append(f"- {note}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_closeout(path: Path, manifest: dict[str, Any]) -> None:
    text = f"""# Cross-Repo Business Event Bridge V1 Closeout

Gate: {manifest['gate']}

Run ID: `{manifest['run_id']}`
Output folder: `{manifest['output_dir']}`

## Result

Created a review-only cross-repo business-event packet from the V4 LINE31 inbound integration proposal and its Sourcing-Research / E-commerce source manifest.

## Counts

- business events: `{manifest['event_count']}`
- source files hashed: `{manifest['source_file_count']}`
- missing source files: `{manifest['source_missing_count']}`
- source hash mismatches: `{manifest['source_hash_mismatch_count']}`

## Boundary

No production DB write, workbook write, source-pointer write, scheduler change, Web_automation write, Kaspi/API/WebUI write, external write, supplier message, payment, PO commitment, stock change, price change, ads change, owner publication, production preflight, or production apply was performed.

## Retained Review Conditions

"""
    for note in manifest["review_notes"]:
        text += f"- {note}\n"
    path.write_text(text, encoding="utf-8")


def protected_surface_sample() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in PROTECTED_SURFACES:
        record = source_record(path)
        rows.append(
            {
                "path": record.path,
                "exists": record.exists,
                "sha256": record.sha256,
                "size_bytes": record.size_bytes,
                "mtime_ns": record.mtime_ns,
            }
        )
    return rows


def build_packet(v4_root: Path, output_root: Path, run_id: str, strict: bool = False) -> dict[str, Any]:
    v4_root = v4_root.expanduser().resolve()
    output_root = output_root.expanduser().resolve()
    inbound_csv = v4_root / "v4_line31_inbound_candidates.csv"
    packaging_csv = v4_root / "v4_line31_next_branded_packaging_advance.csv"
    manifest_path = v4_root / "v4_line31_source_manifest.json"

    source_manifest = load_manifest(manifest_path)
    source_records = build_source_records(v4_root, source_manifest)
    record_by_path = source_by_path(source_records)
    inbound_source = record_by_path[str(inbound_csv.resolve())]
    packaging_source = record_by_path[str(packaging_csv.resolve())]
    manifest_source = record_by_path[str(manifest_path.resolve())]

    created_at = datetime.now().astimezone().isoformat(timespec="seconds")
    inbound_rows = read_csv_rows(inbound_csv)
    packaging_rows = read_csv_rows(packaging_csv)

    events: list[dict[str, str]] = []
    events.extend(build_inbound_events(inbound_rows, run_id=run_id, created_at=created_at, source=inbound_source))
    events.extend(build_packaging_events(packaging_rows, run_id=run_id, created_at=created_at, source=packaging_source))
    events.extend(build_summary_events(source_manifest, run_id=run_id, created_at=created_at, source=manifest_source))

    source_missing = [record for record in source_records if not record.exists]
    source_mismatches = [record for record in source_records if record.hash_matches_recorded is False]
    if strict and (source_missing or source_mismatches):
        raise BridgeError(
            f"strict source validation failed: missing={len(source_missing)} mismatches={len(source_mismatches)}"
        )

    output_dir = output_root / f"cross_repo_business_event_bridge_v1_{run_id}"
    output_dir.mkdir(parents=True, exist_ok=False)

    write_jsonl(output_dir / "business_events.jsonl", events)
    write_csv(output_dir / "business_events.csv", events, EVENT_COLUMNS)

    source_rows = [
        {
            "path": record.path,
            "source_repo": record.source_repo,
            "exists": str(record.exists).lower(),
            "sha256": record.sha256,
            "recorded_sha256": record.recorded_sha256,
            "hash_matches_recorded": "" if record.hash_matches_recorded is None else str(record.hash_matches_recorded).lower(),
            "size_bytes": record.size_bytes,
            "mtime_ns": record.mtime_ns,
        }
        for record in source_records
    ]
    write_csv(
        output_dir / "source_files_manifest.csv",
        source_rows,
        [
            "path",
            "source_repo",
            "exists",
            "sha256",
            "recorded_sha256",
            "hash_matches_recorded",
            "size_bytes",
            "mtime_ns",
        ],
    )

    events_by_type = Counter(event["event_type"] for event in events)
    events_by_gate = Counter(event["gate"] for event in events)
    gate = "RED" if events_by_gate.get("RED") else "YELLOW" if events_by_gate.get("YELLOW") else "GREEN"
    review_notes = []
    if source_missing:
        review_notes.append(f"{len(source_missing)} source files are missing; packet cannot be promoted without source repair.")
    if source_mismatches:
        review_notes.append(f"{len(source_mismatches)} source files changed compared with the upstream V4 manifest.")
    quarantine_qty = sum(int(event["quantity"] or "0") for event in events if event["event_type"] == "SOURCE_MAPPING_QUARANTINE")
    if quarantine_qty:
        review_notes.append(f"{quarantine_qty} inbound sets remain in mapping quarantine and need owner/rebuild review before apply.")
    if events_by_type.get("PO1O_FREIGHT_PAYABLE_OPEN"):
        review_notes.append("PO-1O freight remains an open payable estimate until final freight/Astana receipt evidence exists.")
    if events_by_type.get("OWNER_REPORTED_TIMING_RULE_PENDING_EVIDENCE"):
        review_notes.append("The 7-day stock-reservation timing rule is owner-reported and still needs screenshot-backed event ingestion.")
    if events_by_type.get("WORKING_BALANCE_DUE_ESTIMATE"):
        review_notes.append("Next-branded LINE31 balance due is a working estimate only, not PO/payment authority.")
    if not review_notes:
        review_notes.append("All emitted events are source-backed and ready for review.")

    packet_manifest = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "created_at": created_at,
        "gate": gate,
        "output_dir": str(output_dir),
        "v4_root": str(v4_root),
        "event_count": len(events),
        "events_by_type": dict(sorted(events_by_type.items())),
        "events_by_gate": dict(sorted(events_by_gate.items())),
        "source_file_count": len(source_records),
        "source_missing_count": len(source_missing),
        "source_hash_mismatch_count": len(source_mismatches),
        "source_files": source_rows,
        "protected_surface_sample": protected_surface_sample(),
        "review_notes": review_notes,
        "authority": "review_only_no_production_or_external_writes",
    }
    (output_dir / "event_bridge_manifest.json").write_text(
        json.dumps(packet_manifest, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_review_inbox(output_dir / "review_inbox.md", packet_manifest)
    write_closeout(output_dir / "closeout.md", packet_manifest)
    return packet_manifest


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a review-only Cross-Repo Business Event Bridge V1 packet.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--v4-root",
        type=Path,
        default=None,
        help="V4 LINE31 inbound integration proposal folder. Defaults to the latest matching exports/validation folder.",
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT, help="Folder where the run folder is created.")
    parser.add_argument("--run-id", default="", help="Run ID suffix. Defaults to current local timestamp.")
    parser.add_argument("--strict", action="store_true", help="Fail when upstream source files are missing or hash-mismatched.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable run summary to stdout.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        v4_root = args.v4_root or find_latest_v4_root(args.output_root)
        run_id = args.run_id or datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        manifest = build_packet(v4_root, args.output_root, run_id, strict=args.strict)
    except BridgeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(manifest, indent=2, ensure_ascii=True, sort_keys=True))
    else:
        print(f"Gate: {manifest['gate']}")
        print(f"Output: {manifest['output_dir']}")
        print(f"Events: {manifest['event_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
