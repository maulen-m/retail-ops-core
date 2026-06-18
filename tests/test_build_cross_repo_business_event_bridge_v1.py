from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.build_cross_repo_business_event_bridge_v1 import BridgeError, build_packet, sha256_file


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def make_v4_root(tmp_path: Path, *, bad_recorded_hash: bool = False) -> Path:
    v4_root = tmp_path / "v4"
    v4_root.mkdir()
    (v4_root / "v4_line31_inbound_integration_proposal.md").write_text("# V4 proposal\n", encoding="utf-8")
    source_file = tmp_path / "source" / "event_summary.md"
    source_file.parent.mkdir()
    source_file.write_text("source proof\n", encoding="utf-8")

    inbound_rows = [
        {
            "route_label": "PO1A_NON_OLIVE_ARRIVED_ASTANA",
            "product_family_alias_rule": "LINE31_EQUALS_LINE31S_OWNER_CONFIRMED",
            "source_set_color": "Starry Black 3-piece Set",
            "sku_key_candidate": "CL_OF_ARC_WM_LINE31_C-023_STARRY-BLACK",
            "size": "M",
            "quantity": "5",
            "exists_in_v3_256_anchor_rows": "yes",
            "mapping_status": "DIRECT_TO_EXISTING_256_ROW",
            "mapping_note": "DIRECT_MATCH_EXISTING_LINE31_ANCHOR_SKU",
            "physical_stock_treatment": "CANDIDATE_POST_ANCHOR_INBOUND_ADD_TO_PHYSICAL_WAREHOUSE_AFTER_OWNER_ACCEPTANCE_AND_MAPPING",
            "economic_stock_treatment": "CANDIDATE_POST_ANCHOR_INBOUND_ADD_TO_ECONOMIC_STOCK_AFTER_RECEIPT_ACCEPTANCE_RULE",
            "capital_treatment": "ARRIVED_STOCK_CAPITAL_ADD_IF_NOT_ALREADY_IN_CURRENT_REBUILD",
            "freight_treatment": "FREIGHT_PAYMENT_STATUS_NOT_ESTABLISHED_BY_THIS_PROPOSAL",
            "source_event_time": "2026-05-24 10:00 GMT+5 Astana cargo pickup arrival",
            "confidence": "HIGH",
            "blocker": "",
        },
        {
            "route_label": "PO1O_CARDAMOM_OLIVE_IN_TRANSIT_BASE_PAID",
            "product_family_alias_rule": "LINE31_EQUALS_LINE31S_OWNER_CONFIRMED",
            "source_set_color": "Cardamom Green / Olive Green Mixed Set",
            "sku_key_candidate": "CL_OF_ARC_WM_LINE31_B-C-005_CARDAMOM-GREEN",
            "size": "S",
            "quantity": "2",
            "exists_in_v3_256_anchor_rows": "no",
            "mapping_status": "QUARANTINE_INBOUND_ROW_PENDING_ANCHOR_OR_OFFER_MAPPING",
            "mapping_note": "PARTIAL_MATCH_S_SIZE_MISSING_IN_256_ANCHOR",
            "physical_stock_treatment": "DO_NOT_ADD_TO_PHYSICAL_WAREHOUSE_UNTIL_FINAL_ASTANA_RECEIPT",
            "economic_stock_treatment": "DO_NOT_ADD_TO_CURRENT_ECONOMIC_STOCK_UNTIL_ACCEPTED_RECEIPT_OR_OWNER_RULE",
            "capital_treatment": "IN_TRANSIT_INVENTORY_BASE_COST_PAID_TRACK_SEPARATELY_FROM_WAREHOUSE_STOCK",
            "freight_treatment": "FINAL_INTERNATIONAL_FREIGHT_ASTANA_RECEIVING_OPEN_AND_NOT_YET_PAID",
            "source_event_time": "2026-05-19 14:30 GMT+8 Cargo 525 Yiwu receipt",
            "confidence": "MEDIUM",
            "blocker": "ANCHOR_SIZE_OR_COLOR_ROW_ABSENT_FROM_V3_256_ROWS__OWNER_MAPPING_REVIEW_NEEDED",
        },
    ]
    write_csv(v4_root / "v4_line31_inbound_candidates.csv", inbound_rows)

    packaging_rows = [
        {
            "route_label": "NEXT_BRANDED_LINE31_INTERNAL_PO1B_PACKAGING_ADVANCE",
            "line_item": "advance paid and supplier acknowledged",
            "amount_cny": "5000",
            "basis": "owner payment proof 2026-05-20; Tracy acknowledgement 2026-05-21",
            "supplier_confirmed_state": "PAYMENT_RECEIVED_BAGS_ARRANGED",
            "v4_treatment": "prepayment/payables lane, not PO-1O, not stock quantity",
        },
        {
            "route_label": "NEXT_BRANDED_LINE31_INTERNAL_PO1B_PACKAGING_ADVANCE",
            "line_item": "working balance due after advance",
            "amount_cny": "21600",
            "basis": "26600 - 5000",
            "supplier_confirmed_state": "WORKING_ESTIMATE_SUBJECT_TO_FINAL_SCOPE",
            "v4_treatment": "working payable estimate only",
        },
    ]
    write_csv(v4_root / "v4_line31_next_branded_packaging_advance.csv", packaging_rows)

    manifest = {
        "owner_current_turn_truth": {
            "po1o_paid_total_cny_attributable": 12463,
            "po1o_payment_state": "supplier_side_garment_base_cost_fully_paid_and_acknowledged",
            "po1o_freight_payment_state": "not yet paid in repo evidence per owner clarification",
            "next_branded_line31_po1b_timing_risk_note": {
                "owner_reported_unverified_point": "7-day stock reservation lead needs screenshot evidence",
                "verification_state": "OWNER_REPORTED_NEEDS_SCREENSHOT_BACKED_EVENT_INGESTION",
                "payment_implication": {"safest_cash_target_ready_cny": 21600},
            },
        },
        "source_summary": {
            "po1o_qty_total": 242,
            "po1o_internal_freight_estimate_usd": 365.75,
            "po1o_internal_freight_estimate_kzt": 179217.5,
            "po1o_internal_eta_planning_only": "2026-06-04 planning only",
        },
        "source_files": [
            {
                "path": str(source_file),
                "sha256": "bad" if bad_recorded_hash else sha256_file(source_file),
            }
        ],
    }
    (v4_root / "v4_line31_source_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return v4_root


def read_jsonl(path: Path) -> list[dict[str, str]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_bridge_packet_builds_review_inbox_and_events(tmp_path: Path) -> None:
    v4_root = make_v4_root(tmp_path)
    manifest = build_packet(v4_root, tmp_path / "out", "test_run")
    output_dir = Path(manifest["output_dir"])

    events = read_jsonl(output_dir / "business_events.jsonl")

    assert manifest["gate"] == "YELLOW"
    assert manifest["source_missing_count"] == 0
    assert manifest["source_hash_mismatch_count"] == 0
    assert manifest["events_by_type"]["PO_INBOUND_ASTANA_CANDIDATE"] == 1
    assert manifest["events_by_type"]["SOURCE_MAPPING_QUARANTINE"] == 1
    assert manifest["events_by_type"]["PO1O_FREIGHT_PAYABLE_OPEN"] == 1
    assert {event["event_schema_version"] for event in events} == {"cross_repo_business_event_v1"}
    assert (output_dir / "review_inbox.md").exists()
    assert (output_dir / "source_files_manifest.csv").exists()
    assert "2 inbound sets remain in mapping quarantine" in "\n".join(manifest["review_notes"])


def test_bridge_strict_fails_on_source_hash_mismatch(tmp_path: Path) -> None:
    v4_root = make_v4_root(tmp_path, bad_recorded_hash=True)

    with pytest.raises(BridgeError, match="strict source validation failed"):
        build_packet(v4_root, tmp_path / "out", "strict_run", strict=True)
