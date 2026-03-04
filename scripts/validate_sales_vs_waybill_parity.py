#!/usr/bin/env python3
"""Fail-closed parity guard between BUSINESS_INSIDES waybill metrics and waybill selection cache."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.generate_business_insides import (
    DEFAULT_SHIPPED_TRUTH_ROOT,
    load_shipped_truth_snapshot,
    load_waybill_selection_snapshot,
)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _resolve_business_snapshot_json(project_root: Path, as_of: str) -> Path | None:
    candidates = [
        project_root / "config" / "business_insides" / f"BUSINESS_INSIDES_{as_of}.json",
        project_root / "config" / "business_insides" / "snapshots" / f"BUSINESS_INSIDES_{as_of}.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _normalize_store_key(value: str) -> str:
    text = str(value or "").strip().upper()
    compact = re.sub(r"[^A-Z0-9]", "", text)
    aliases = {
        "UNIVERSAL": "UNIVERSAL",
        "ACMEWEAR": "ACMEWEAR",
        "11KZ": "11KZ",
        "MELVIS": "MELVIS",
        "STOREB": "STOREB",
    }
    return aliases.get(compact, compact or text)


def _normalize_store_totals(raw: dict[str, Any]) -> dict[str, dict[str, float]]:
    normalized: dict[str, dict[str, float]] = {}
    for store_raw, values in (raw or {}).items():
        key = _normalize_store_key(str(store_raw))
        row = values if isinstance(values, dict) else {}
        orders = int(float(row.get("orders") or 0))
        units = float(row.get("units") or 0.0)
        bucket = normalized.setdefault(key, {"orders": 0.0, "units": 0.0})
        bucket["orders"] += float(orders)
        bucket["units"] += float(units)
    return normalized


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Sales vs Waybill Parity",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- status: `{report['status']}`",
        f"- business_snapshot_json: `{report.get('business_snapshot_json')}`",
        f"- selection_cache_path: `{report.get('selection_cache_path')}`",
        "",
        "| store | business_orders | source_orders | business_units | source_units | status |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in report["store_checks"]:
        lines.append(
            f"| `{row['store']}` | {row['business_orders']} | {row['source_orders']} | "
            f"{row['business_units']} | {row['source_units']} | {'PASS' if row['ok'] else 'FAIL'} |"
        )
    if report["errors"]:
        lines.extend(["", "## Errors", ""])
        for err in report["errors"]:
            lines.append(f"- {err}")
    return "\n".join(lines) + "\n"


def validate_sales_vs_waybill_parity(
    *,
    project_root: Path,
    as_of: str,
    db_path: Path,
    selection_cache_path: Path,
    output_root: Path,
    business_snapshot_json: Path | None = None,
    strict: bool,
) -> dict[str, Any]:
    root = project_root.resolve()
    as_of_date = date.fromisoformat(as_of)
    errors: list[str] = []

    resolved_business_snapshot = (
        business_snapshot_json.resolve()
        if business_snapshot_json is not None
        else _resolve_business_snapshot_json(root, as_of)
    )
    business_payload = _read_json(resolved_business_snapshot) if resolved_business_snapshot else None
    business_waybill = business_payload.get("waybill_snapshot") if isinstance(business_payload, dict) else None

    if resolved_business_snapshot is None or business_payload is None:
        errors.append(
            "missing BUSINESS_INSIDES JSON snapshot "
            f"for as_of={as_of}; expected config/business_insides/BUSINESS_INSIDES_{as_of}.json"
        )
    else:
        business_as_of = str(
            business_payload.get("as_of") or business_payload.get("as_of_date") or ""
        ).strip()
        if business_as_of != as_of:
            errors.append(
                "BUSINESS_INSIDES as_of mismatch: "
                f"expected {as_of}, got {business_as_of or '<missing>'}"
            )
        if not isinstance(business_waybill, dict):
            errors.append("BUSINESS_INSIDES payload missing waybill_snapshot section")

    business_source_status = (
        str((business_waybill or {}).get("status") or "").strip().lower()
        if isinstance(business_waybill, dict)
        else ""
    )
    source_mode = "waybill_selection"
    source_waybill = None
    if business_source_status == "available_shipped_truth":
        source_mode = "shipped_truth_primary"
        shipped_snapshot = load_shipped_truth_snapshot(
            as_of_date=as_of_date,
            shipped_truth_root=DEFAULT_SHIPPED_TRUTH_ROOT.resolve(),
        )
        if shipped_snapshot is None:
            errors.append(
                "BUSINESS_INSIDES uses shipped-truth source but shipped-truth summary "
                f"is missing for as_of={as_of}"
            )
            source_waybill = {
                "status": "missing",
                "reason": "shipped_truth_summary_missing",
                "target_date": as_of,
                "stores": {},
            }
        else:
            source_waybill = shipped_snapshot
    else:
        source_waybill = load_waybill_selection_snapshot(
            db_path=db_path.resolve(),
            as_of_date=as_of_date,
            selection_cache_path=selection_cache_path.resolve(),
        )
    source_status = str(source_waybill.get("status") or "missing")
    source_target_date = str(source_waybill.get("target_date") or "").strip()
    allowed_statuses = {"available", "available_archive"}
    source_label = "waybill selection"
    if source_mode == "shipped_truth_primary":
        allowed_statuses = {"available_shipped_truth"}
        source_label = "shipped-truth"

    if source_status not in allowed_statuses:
        errors.append(
            f"{source_label} snapshot unavailable for parity validation: "
            f"status={source_status} reason={source_waybill.get('reason')}"
        )
    elif source_target_date != as_of:
        errors.append(
            f"waybill selection target_date mismatch: expected {as_of}, got {source_target_date or '<missing>'}"
        )

    business_stores = _normalize_store_totals(
        (business_waybill.get("stores") if isinstance(business_waybill, dict) else {}) or {}
    )
    source_stores = _normalize_store_totals(
        (source_waybill.get("stores") or {}) if isinstance(source_waybill, dict) else {}
    )
    store_keys = sorted(set(business_stores.keys()) | set(source_stores.keys()))

    store_checks: list[dict[str, Any]] = []
    for store in store_keys:
        business_row = business_stores.get(store) or {}
        source_row = source_stores.get(store) or {}
        business_orders = int(float(business_row.get("orders") or 0))
        source_orders = int(float(source_row.get("orders") or 0))
        business_units = round(float(business_row.get("units") or 0.0), 2)
        source_units = round(float(source_row.get("units") or 0.0), 2)
        ok = business_orders <= source_orders and business_units <= source_units + 1e-9
        store_checks.append(
            {
                "store": store,
                "business_orders": business_orders,
                "source_orders": source_orders,
                "business_units": business_units,
                "source_units": source_units,
                "ok": bool(ok),
            }
        )
        if not ok:
            errors.append(
                "parity breach for store "
                f"{store}: business_orders={business_orders} source_orders={source_orders}; "
                f"business_units={business_units} source_units={source_units}"
            )

    overall_ok = len(errors) == 0
    out_dir = output_root.resolve() / as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of,
        "status": "PASS" if overall_ok else "FAIL",
        "ok": bool(overall_ok),
        "project_root": str(root),
        "business_snapshot_json": str(resolved_business_snapshot) if resolved_business_snapshot else None,
        "selection_cache_path": str(selection_cache_path.resolve()),
        "source_mode": source_mode,
        "source_status": source_status,
        "source_reason": source_waybill.get("reason"),
        "store_checks": store_checks,
        "errors": errors,
    }
    json_path = out_dir / "sales_vs_waybill_parity.json"
    md_path = out_dir / "sales_vs_waybill_parity.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)

    if strict and not overall_ok:
        raise RuntimeError("sales vs waybill parity validation failed")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate BUSINESS_INSIDES shipment parity against waybill snapshot")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--db", type=Path, default=PROJECT_ROOT / "db" / "app.db")
    parser.add_argument(
        "--selection-cache",
        type=Path,
        default=PROJECT_ROOT / "excel_ui" / "ActiveOrders" / "waybills" / "_waybill_selection_orders.json",
    )
    parser.add_argument("--business-snapshot-json", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "exports" / "daily")
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = validate_sales_vs_waybill_parity(
        project_root=args.project_root,
        as_of=str(args.as_of),
        db_path=args.db,
        selection_cache_path=args.selection_cache,
        output_root=args.output_root,
        business_snapshot_json=args.business_snapshot_json,
        strict=bool(args.strict),
    )
    print(f"sales_vs_waybill_parity_json={report['json_path']}")
    print(f"sales_vs_waybill_parity_md={report['md_path']}")
    print(f"status={report['status']}")
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
