#!/usr/bin/env python3
"""Helpers for the WebUI chronology authority contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_gate_status(path: Path, fallback_status: str = "FAIL") -> dict[str, Any]:
    if not path.exists():
        return {
            "status": fallback_status,
            "ok": False,
            "reason": f"missing:{path.name}",
            "path": str(path),
            "payload": {},
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    status = str(payload.get("status") or fallback_status).upper()
    ok = bool(payload.get("ok", status == "PASS")) and status == "PASS"
    return {
        "status": status,
        "ok": ok,
        "path": str(path),
        "payload": payload,
    }


def load_webui_chronology_gates(validation_dir: Path) -> tuple[dict[str, dict[str, Any]], bool, dict[str, Any]]:
    decision_gate = load_gate_status(validation_dir / "shipped_day_authority_decision.json")
    decision = str((decision_gate.get("payload") or {}).get("decision") or "").strip()

    if decision == "CRM_REMAINS_CHRONOLOGY_AUTHORITY":
        workbook_gate = load_gate_status(validation_dir / "sales_against_workbook_report.json")
        gates = {
            "shipped_day_authority": decision_gate,
            "workbook_chronology_anchor": workbook_gate,
        }
        return gates, all(bool(item.get("ok")) for item in gates.values()), {
            "decision": decision,
            "mode": "WORKBOOK_ANCHOR",
        }

    if decision == "RULE_PROVEN":
        promotion_gate = load_gate_status(validation_dir / "webui_truth_promotion_report.json")
        gates = {
            "shipped_day_authority": decision_gate,
            "webui_truth_band": promotion_gate,
        }
        return gates, all(bool(item.get("ok")) for item in gates.values()), {
            "decision": decision,
            "mode": "AUTHORITY_PROJECTION",
        }

    legacy_gate = load_gate_status(validation_dir / "webui_truth_promotion_report.json")
    return {"webui_truth_band": legacy_gate}, bool(legacy_gate.get("ok")), {
        "decision": "LEGACY_WEBUI_TRUTH_BAND",
        "mode": "LEGACY",
    }
