#!/usr/bin/env python3
"""Validate OD-027 storefront disposition for archived Kaspi stores."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALMATY_TZ = ZoneInfo("Asia/Almaty")

DEFAULT_DECISION = PROJECT_ROOT / "config" / "owner_decisions" / "storefront_disposition_od027_2026_06_18.json"
DEFAULT_OWNER_RECORDED = PROJECT_ROOT / "docs" / "plan" / "green_path_2026-06" / "OWNER_DECISIONS_RECORDED.yaml"
DEFAULT_POLICY = PROJECT_ROOT / "config" / "operational_decision_policy.yaml"
DEFAULT_KASPI_STORES = PROJECT_ROOT / "config" / "kaspi_stores.yaml"
DEFAULT_DAILY_STORES = PROJECT_ROOT / "config" / "stores.yaml"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "storefront_disposition"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _owner_decision(payload: dict[str, Any], decision_id: str) -> dict[str, Any] | None:
    for row in payload.get("decisions") or []:
        if isinstance(row, dict) and row.get("id") == decision_id:
            return row
    return None


def _load_owner_decision_record(path: Path, decision_id: str) -> dict[str, Any] | None:
    text = path.read_text(encoding="utf-8")
    try:
        payload = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        payload = None
    if isinstance(payload, dict):
        row = _owner_decision(payload, decision_id)
        if row:
            return row

    lines = text.splitlines()
    start: int | None = None
    for idx, line in enumerate(lines):
        if re.match(rf"^\s*-\s+id:\s*{re.escape(decision_id)}\s*$", line):
            start = idx
            break
    if start is None:
        return None

    block: list[str] = []
    for line in lines[start:]:
        if block and re.match(r"^\s*-\s+id:\s*\S+", line):
            break
        block.append(line)
    block_text = "\n".join(block)
    answer_match = re.search(r"^\s*answer:\s*([A-Z0-9_-]+)", block_text, flags=re.MULTILINE)
    return {
        "id": decision_id,
        "answer": answer_match.group(1) if answer_match else "",
        "params": {
            "action": "archive_both" if re.search(r"\baction:\s*archive_both\b", block_text) else "",
            "stop_daily_polling": bool(re.search(r"\bstop_daily_polling:\s*true\b", block_text, flags=re.I)),
        },
    }


def _enabled_kaspi_stores(payload: dict[str, Any]) -> list[str]:
    stores = payload.get("stores") or {}
    rows: list[tuple[int, str]] = []
    for code, meta in stores.items():
        if isinstance(meta, dict) and bool(meta.get("sync_enabled", True)):
            rows.append((int(meta.get("priority", 99)), str(code).upper()))
    return [code for _, code in sorted(rows, key=lambda item: (item[0], item[1]))]


def _active_daily_stores(payload: dict[str, Any]) -> list[str]:
    stores = payload.get("stores") or {}
    return [
        str(code).upper()
        for code, meta in stores.items()
        if isinstance(meta, dict) and bool(meta.get("active", True))
    ]


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# G-STORE-01 Storefront Disposition",
        "",
        f"Gate: {report['gate']}",
        f"Status: {report['status']}",
        f"Generated at: {report['generated_at']}",
        f"Decision: {report['decision_id']}",
        "",
        "## Store State",
        "",
        "| store | kaspi_sync_enabled | daily_active | lifecycle_status | owner_decision_id |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in report["stores"]:
        lines.append(
            "| {store} | {kaspi_sync_enabled} | {daily_active} | {lifecycle_status} | {owner_decision_id} |".format(
                **row
            )
        )
    lines.extend(
        [
            "",
            f"Active daily polling stores: {', '.join(report['active_daily_polling_stores'])}",
            f"Sync-enabled Kaspi stores: {', '.join(report['sync_enabled_kaspi_stores'])}",
            f"No external writes performed: {report['no_external_writes_performed']}",
            "",
            "## Checks",
            "",
        ]
    )
    if report["errors"]:
        lines.extend(f"- FAIL: {error}" for error in report["errors"])
    else:
        lines.append("- PASS: owner decision, policy, daily roster, and sync config agree.")
    lines.append("")
    return "\n".join(lines)


def build_report(
    *,
    decision_path: Path = DEFAULT_DECISION,
    owner_recorded_path: Path = DEFAULT_OWNER_RECORDED,
    policy_path: Path = DEFAULT_POLICY,
    kaspi_stores_path: Path = DEFAULT_KASPI_STORES,
    daily_stores_path: Path = DEFAULT_DAILY_STORES,
) -> dict[str, Any]:
    decision = _load_json(decision_path)
    owner_recorded = _load_owner_decision_record(owner_recorded_path, "OD-027")
    policy = _load_yaml(policy_path)
    kaspi_cfg = _load_yaml(kaspi_stores_path)
    daily_cfg = _load_yaml(daily_stores_path)

    errors: list[str] = []
    decision_id = str(decision.get("decision_id") or "")
    archived = {str(store).upper() for store in decision.get("archived_stores") or []}
    active_after = [str(store).upper() for store in decision.get("active_daily_polling_stores_after") or []]
    expected_archived = {"11KZ", "MELVIS"}
    expected_active = {"UNIVERSAL", "ACMEWEAR", "STOREB"}

    if decision_id != "OD-027":
        errors.append(f"decision_id must be OD-027, got {decision_id!r}")
    if decision.get("action") != "archive_both_stop_daily_polling":
        errors.append("decision action must be archive_both_stop_daily_polling")
    if archived != expected_archived:
        errors.append(f"archived stores mismatch: {sorted(archived)}")
    if set(active_after) != expected_active:
        errors.append(f"active_daily_polling_stores_after mismatch: {active_after}")
    if decision.get("scope") != "local_config_and_validation_only":
        errors.append("decision scope must stay local_config_and_validation_only")
    if decision.get("preserve_history") is not True:
        errors.append("decision must preserve history")

    recorded = owner_recorded if decision_id == "OD-027" else None
    if not recorded:
        errors.append("OWNER_DECISIONS_RECORDED.yaml missing OD-027")
    else:
        params = recorded.get("params") or {}
        if recorded.get("answer") != "RECOMMENDED":
            errors.append("OD-027 recorded answer is not RECOMMENDED")
        if params.get("action") != "archive_both":
            errors.append("OD-027 recorded action is not archive_both")
        if params.get("stop_daily_polling") is not True:
            errors.append("OD-027 recorded stop_daily_polling is not true")

    store_scope = policy.get("store_scope") or {}
    if set(store_scope.get("inactive_stores") or []) != expected_archived:
        errors.append("operational policy inactive_stores must be 11KZ and MELVIS")
    if set(store_scope.get("archived_stores") or []) != expected_archived:
        errors.append("operational policy archived_stores must be 11KZ and MELVIS")
    if set(store_scope.get("active_positive_stock_stores") or []) != expected_active:
        errors.append("operational policy active_positive_stock_stores mismatch")
    if store_scope.get("archived_store_decision_id") != "OD-027":
        errors.append("operational policy archived_store_decision_id must be OD-027")

    kaspi_stores = kaspi_cfg.get("stores") or {}
    daily_stores = daily_cfg.get("stores") or {}
    store_rows: list[dict[str, Any]] = []
    for store in sorted(expected_archived):
        kaspi_meta = kaspi_stores.get(store) or {}
        daily_meta = daily_stores.get(store) or {}
        if kaspi_meta.get("sync_enabled", True) is not False:
            errors.append(f"{store} kaspi_stores sync_enabled must be false")
        if daily_meta.get("active", True) is not False:
            errors.append(f"{store} stores.yaml active must be false")
        if kaspi_meta.get("lifecycle_status") != "ARCHIVED":
            errors.append(f"{store} kaspi_stores lifecycle_status must be ARCHIVED")
        if daily_meta.get("lifecycle_status") != "ARCHIVED":
            errors.append(f"{store} stores.yaml lifecycle_status must be ARCHIVED")
        if kaspi_meta.get("owner_decision_id") != "OD-027":
            errors.append(f"{store} kaspi_stores owner_decision_id must be OD-027")
        if daily_meta.get("owner_decision_id") != "OD-027":
            errors.append(f"{store} stores.yaml owner_decision_id must be OD-027")
        if not kaspi_meta.get("token_env") or not daily_meta.get("token_env"):
            errors.append(f"{store} token_env must be preserved")
        if not kaspi_meta.get("merchant_uid"):
            errors.append(f"{store} merchant_uid must be preserved")
        store_rows.append(
            {
                "store": store,
                "kaspi_sync_enabled": bool(kaspi_meta.get("sync_enabled", True)),
                "daily_active": bool(daily_meta.get("active", True)),
                "lifecycle_status": kaspi_meta.get("lifecycle_status") or daily_meta.get("lifecycle_status") or "",
                "owner_decision_id": kaspi_meta.get("owner_decision_id") or daily_meta.get("owner_decision_id") or "",
            }
        )

    enabled_kaspi = _enabled_kaspi_stores(kaspi_cfg)
    active_daily = _active_daily_stores(daily_cfg)
    if set(enabled_kaspi) != expected_active:
        errors.append(f"sync-enabled Kaspi stores mismatch: {enabled_kaspi}")
    if set(active_daily) != expected_active:
        errors.append(f"active daily stores mismatch: {active_daily}")

    required_fresh = set(((kaspi_cfg.get("settings") or {}).get("required_fresh_stores")) or [])
    if required_fresh != expected_active:
        errors.append(f"required_fresh_stores mismatch: {sorted(required_fresh)}")

    generated_at = datetime.now(ALMATY_TZ).isoformat(timespec="seconds")
    return {
        "gate": "GREEN" if not errors else "RED",
        "status": "GREEN" if not errors else "RED",
        "ok": not errors,
        "decision_id": decision_id,
        "generated_at": generated_at,
        "archived_stores": sorted(expected_archived),
        "active_daily_polling_stores": active_daily,
        "sync_enabled_kaspi_stores": enabled_kaspi,
        "stores": store_rows,
        "errors": errors,
        "no_external_writes_performed": True,
        "source_paths": {
            "decision": str(decision_path),
            "owner_recorded": str(owner_recorded_path),
            "policy": str(policy_path),
            "kaspi_stores": str(kaspi_stores_path),
            "daily_stores": str(daily_stores_path),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate OD-027 storefront disposition config.")
    parser.add_argument("--decision", type=Path, default=DEFAULT_DECISION)
    parser.add_argument("--owner-recorded", type=Path, default=DEFAULT_OWNER_RECORDED)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--kaspi-stores", type=Path, default=DEFAULT_KASPI_STORES)
    parser.add_argument("--daily-stores", type=Path, default=DEFAULT_DAILY_STORES)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    report = build_report(
        decision_path=args.decision,
        owner_recorded_path=args.owner_recorded,
        policy_path=args.policy,
        kaspi_stores_path=args.kaspi_stores,
        daily_stores_path=args.daily_stores,
    )

    output_dir = args.output_dir
    if output_dir is None:
        stamp = datetime.now(ALMATY_TZ).strftime("%Y%m%d_%H%M%S")
        output_dir = DEFAULT_OUTPUT_ROOT / stamp
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "storefront_disposition_report.json"
    md_path = output_dir / "storefront_disposition_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")

    print(f"Gate: {report['gate']}")
    print(f"Report: {json_path}")
    if report["errors"]:
        for error in report["errors"]:
            print(f"FAIL: {error}")
    return 0 if (report["ok"] or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
