#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import Any


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _to_float(value: Any) -> float:
    return round(float(value or 0.0), 2)


def _to_int(value: Any) -> int:
    return int(float(value or 0))


def _normalize_sku_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sku_key": str(row.get("sku_key") or ""),
        "sku_name": str(row.get("sku_name") or ""),
        "po_qty_total": _to_int(row.get("po_qty_total")),
        "deficit_total": _to_int(row.get("deficit_total")),
        "stock": _to_int(row.get("stock")),
        "monthly_profit": _to_float(row.get("monthly_profit")),
        "roic_pct": _to_float(row.get("roic_pct")),
        "roic_below_threshold": bool(row.get("roic_below_threshold")),
        "po_cogs_kzt": _to_float(row.get("po_cogs_kzt")),
        "oos_type": str(row.get("oos_type") or ""),
        "notes": str(row.get("notes") or ""),
    }


def _days_between(start: Any, end: Any) -> int | None:
    if not start or not end:
        return None
    return (date.fromisoformat(str(end)) - date.fromisoformat(str(start))).days


def _render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# PO / SKU Daily",
        "",
        f"- as_of: `{payload['as_of']}`",
        f"- status: `{payload['status']}`",
        f"- trust_banner: `{payload['trust_banner']}`",
        f"- total_skus: `{payload['summary']['total_skus']}`",
        f"- total_units: `{payload['summary']['total_units']}`",
        f"- total_po_cogs_kzt: `{payload['summary']['total_po_cogs_kzt']}`",
        f"- low_roic_skus: `{payload['summary'].get('low_roic_skus')}`",
        f"- no_order_needed: `{payload['summary'].get('no_order_needed')}`",
        "",
        "## Planning Snapshot",
        "",
        f"- base_stock_date: `{payload['planning_snapshot'].get('base_stock_date')}`",
        f"- cutoff_date: `{payload['planning_snapshot'].get('cutoff_date')}`",
        f"- freshness: `{payload['planning_snapshot'].get('freshness')}`",
        f"- staleness_days_vs_cutoff: `{payload['planning_snapshot'].get('staleness_days_vs_cutoff')}`",
        "",
        "| PO ID | Supplier | Units | Cost CNY | Status |",
        "|---|---|---:|---:|---|",
    ]
    for row in payload["top_real_pos"]:
        lines.append(
            f"| `{row['po_id']}` | `{row['supplier_code']}` | {row['units_total']} | {row['total_cost_cny']:.2f} | `{row['status']}` |"
        )
    for title, rows, fields in [
        ("Reorder Now", payload["action_buckets"]["reorder_now"], ["sku_key", "po_qty_total", "deficit_total", "po_cogs_kzt"]),
        ("Freeze / Kill Review", payload["action_buckets"]["freeze_or_kill_review"], ["sku_key", "monthly_profit", "roic_pct", "po_cogs_kzt"]),
        ("No Order Needed", payload["action_buckets"]["no_order_needed"], ["sku_key", "stock", "notes"]),
        ("Tied Up Capital", payload["action_buckets"]["tied_up_capital"], ["sku_key", "po_cogs_kzt", "po_qty_total"]),
    ]:
        lines.extend(["", f"## {title}", ""])
        if not rows:
            lines.append("- none")
            continue
        for row in rows:
            pieces = [f"`{field}`={row.get(field)}" for field in fields if field != "sku_key"]
            lines.append(f"- `{row.get('sku_key')}`: " + ", ".join(pieces))
    return "\n".join(lines) + "\n"


def build_po_sku_daily(
    *,
    as_of: str,
    owner_truth_summary_path: Path,
    system_health_path: Path,
    po_dashboard_path: Path,
    output_root: Path,
    validation_root: Path,
    max_rows: int = 10,
) -> dict[str, Any]:
    owner_truth = _read_json(owner_truth_summary_path)
    system_health = _read_json(system_health_path)
    po_dashboard = _read_json(po_dashboard_path)
    ok = str(owner_truth.get("status")) == "PASS" and str(system_health.get("status")) == "GREEN"
    summary = po_dashboard.get("summary") or {}
    real_pos = po_dashboard.get("real_pos") or []
    sku_level = (((po_dashboard.get("pos") or {}).get("PLAN-0") or {}).get("sku_level") or [])
    normalized_skus = [_normalize_sku_row(row) for row in sku_level]
    top_real_pos = sorted(
        [
            {
                "po_id": str(row.get("po_id") or ""),
                "supplier_code": str(row.get("supplier_code") or ""),
                "units_total": _to_int(row.get("units_total")),
                "total_cost_cny": _to_float(row.get("total_cost_cny")),
                "status": str(row.get("status") or ""),
            }
            for row in real_pos
        ],
        key=lambda row: (row["total_cost_cny"], row["units_total"]),
        reverse=True,
    )[:max_rows]
    reorder_now = sorted(
        [row for row in normalized_skus if row["po_qty_total"] > 0 and row["deficit_total"] > 0 and not row["roic_below_threshold"]],
        key=lambda row: row["po_cogs_kzt"],
        reverse=True,
    )[:5]
    freeze_or_kill_review = sorted(
        [row for row in normalized_skus if row["roic_below_threshold"]],
        key=lambda row: row["po_cogs_kzt"],
        reverse=True,
    )[:5]
    no_order_needed = sorted(
        [
            row
            for row in normalized_skus
            if row["po_qty_total"] == 0 or ("NO_ORDER_NEEDED" in row["notes"] and row["po_cogs_kzt"] == 0)
        ],
        key=lambda row: row["stock"],
        reverse=True,
    )[:5]
    tied_up_capital = sorted(normalized_skus, key=lambda row: row["po_cogs_kzt"], reverse=True)[:5]
    base_stock_date = po_dashboard.get("base_stock_date")
    cutoff_date = po_dashboard.get("cutoff_date")
    staleness_days_vs_cutoff = _days_between(base_stock_date, cutoff_date)
    freshness = "FRESH"
    if staleness_days_vs_cutoff is not None and staleness_days_vs_cutoff > 0:
        freshness = "STALE_VS_CUTOFF"
    trust_banner = "PASS_GREEN_LIVE_CHAIN_WITH_STALE_PO_SNAPSHOT" if ok and freshness != "FRESH" else (
        "PASS_GREEN_LIVE_CHAIN" if ok else "FAIL_UPSTREAM_GATES"
    )
    payload = {
        "generated_at": _now_utc(),
        "as_of": as_of,
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "trust_banner": trust_banner,
        "summary": {
            "total_skus": summary.get("total_skus"),
            "total_units": summary.get("total_units"),
            "total_po_cogs_kzt": summary.get("total_po_cogs_kzt"),
            "priority_skus": summary.get("priority_skus"),
            "low_roic_skus": summary.get("low_roic_skus"),
            "no_order_needed": summary.get("no_order_needed"),
        },
        "top_real_pos": top_real_pos,
        "planning_snapshot": {
            "base_stock_date": base_stock_date,
            "cutoff_date": cutoff_date,
            "freshness": freshness,
            "staleness_days_vs_cutoff": staleness_days_vs_cutoff,
        },
        "action_buckets": {
            "reorder_now": reorder_now,
            "freeze_or_kill_review": freeze_or_kill_review,
            "no_order_needed": no_order_needed,
            "tied_up_capital": tied_up_capital,
        },
        "sources": {
            "owner_truth_summary": str(owner_truth_summary_path),
            "system_health": str(system_health_path),
            "po_dashboard": str(po_dashboard_path),
        },
    }
    out_dir = output_root / as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "po_sku_daily.json"
    md_path = out_dir / "po_sku_daily.md"
    _write_json(json_path, payload)
    md_path.write_text(_render_md(payload), encoding="utf-8")
    _write_json(
        validation_root / as_of / "trust_report.json",
        {
            "generated_at": _now_utc(),
            "status": payload["status"],
            "trust_banner": payload["trust_banner"],
            "json_path": str(json_path.resolve()),
            "md_path": str(md_path.resolve()),
        },
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Build PO / SKU daily surface.")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--owner-truth-summary", type=Path, required=True)
    parser.add_argument("--system-health", type=Path, required=True)
    parser.add_argument("--po-dashboard", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("exports/owner"))
    parser.add_argument("--validation-root", type=Path, default=Path("exports/validation/po_sku_daily"))
    parser.add_argument("--max-rows", type=int, default=10)
    args = parser.parse_args()
    payload = build_po_sku_daily(
        as_of=args.as_of,
        owner_truth_summary_path=args.owner_truth_summary,
        system_health_path=args.system_health,
        po_dashboard_path=args.po_dashboard,
        output_root=args.output_root,
        validation_root=args.validation_root,
        max_rows=args.max_rows,
    )
    print(f"po_sku_daily_json={(args.output_root / args.as_of / 'po_sku_daily.json').resolve()}")
    print(f"po_sku_daily_md={(args.output_root / args.as_of / 'po_sku_daily.md').resolve()}")
    print(f"status={payload['status']}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
