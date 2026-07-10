from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXCLUSIONS_PATH = (
    PROJECT_ROOT
    / "config"
    / "owner_decisions"
    / "waybill_send_exclusions_2026_07_10.json"
)


def load_waybill_send_exclusions(
    path: Path = DEFAULT_EXCLUSIONS_PATH,
) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "autonomous_business.waybill_send_exclusions.v1":
        raise RuntimeError("Unsupported waybill send-exclusion policy schema")
    decisions = payload.get("decisions")
    if not isinstance(decisions, list):
        raise RuntimeError("Waybill send-exclusion policy decisions must be a list")
    return payload


def blocked_live_action_for_manifest(
    manifest: Mapping[str, Any],
    *,
    action: str,
    policy_path: Path = DEFAULT_EXCLUSIONS_PATH,
) -> dict[str, Any] | None:
    target_date_text = str(manifest.get("target_date") or "").strip()
    try:
        date.fromisoformat(target_date_text)
    except ValueError:
        return {
            "target_date": target_date_text,
            "action": "invalid_manifest_target_date",
            "reason": "Live delivery requires an ISO manifest target_date",
            "blocked_live_actions": [action],
        }

    policy = load_waybill_send_exclusions(policy_path)
    for decision in policy.get("decisions") or []:
        if not isinstance(decision, dict):
            continue
        if str(decision.get("target_date") or "") != target_date_text:
            continue
        blocked_actions = {
            str(value)
            for value in decision.get("blocked_live_actions") or []
            if str(value)
        }
        if action in blocked_actions:
            return dict(decision)
    return None
