#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# Inventory Capital Radar",
        "",
        f"- as_of: `{payload['as_of']}`",
        f"- status: `{payload['status']}`",
        f"- trust_banner: `{payload['trust_banner']}`",
        f"- decision_scope: `{payload['profit_scope']['decision_scope']}`",
        "",
        "## Planning Snapshot",
        "",
        f"- freshness: `{payload['planning_snapshot'].get('freshness')}`",
        f"- base_stock_date: `{payload['planning_snapshot'].get('base_stock_date')}`",
        f"- cutoff_date: `{payload['planning_snapshot'].get('cutoff_date')}`",
        f"- staleness_days_vs_cutoff: `{payload['planning_snapshot'].get('staleness_days_vs_cutoff')}`",
        "",
    ]
    for title, key in [
        ("Reorder Now", "reorder_now"),
        ("Freeze / Kill Review", "freeze_or_kill_review"),
        ("No Order Needed", "no_order_needed"),
        ("Tied Up Capital", "tied_up_capital"),
    ]:
        lines.extend([f"## {title}", ""])
        rows = payload["action_buckets"].get(key) or []
        if not rows:
            lines.append("- none")
            lines.append("")
            continue
        for row in rows:
            lines.append(f"- `{row.get('sku_key')}` -> `{row}`")
        lines.append("")
    return "\n".join(lines)


def build_inventory_capital_radar(
    *,
    as_of: str,
    owner_truth_summary_path: Path,
    system_health_path: Path,
    po_sku_daily_path: Path,
    owner_profit_daily_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    owner_truth = _read_json(owner_truth_summary_path)
    system_health = _read_json(system_health_path)
    po_sku_daily = _read_json(po_sku_daily_path)
    owner_profit_daily = _read_json(owner_profit_daily_path)

    ok = (
        str(owner_truth.get("status")) == "PASS"
        and str(system_health.get("status")) == "GREEN"
        and str(po_sku_daily.get("status")) == "PASS"
        and str(owner_profit_daily.get("status")) == "PASS"
    )

    payload = {
        "generated_at": _now_utc(),
        "as_of": as_of,
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "trust_banner": (
            "PASS_INVENTORY_CAPITAL_RADAR_MONITORING_ONLY"
            if ok
            else "FAIL_UPSTREAM_OWNER_SURFACES"
        ),
        "planning_snapshot": po_sku_daily.get("planning_snapshot") or {},
        "summary": po_sku_daily.get("summary") or {},
        "action_buckets": po_sku_daily.get("action_buckets") or {},
        "top_real_pos": po_sku_daily.get("top_real_pos") or [],
        "profit_scope": {
            "decision_scope": owner_profit_daily.get("decision_scope"),
            "trust_banner": owner_profit_daily.get("trust_banner"),
            "latest_month": (owner_profit_daily.get("rows") or [])[-1]
            if (owner_profit_daily.get("rows") or [])
            else None,
        },
        "sources": {
            "owner_truth_summary": str(owner_truth_summary_path),
            "system_health": str(system_health_path),
            "po_sku_daily": str(po_sku_daily_path),
            "owner_profit_daily": str(owner_profit_daily_path),
        },
    }

    out_dir = output_root / as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "inventory_capital_radar.json"
    md_path = out_dir / "inventory_capital_radar.md"
    _write_json(json_path, payload)
    md_path.write_text(_render_md(payload), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Build inventory capital radar from owner monitoring surfaces.")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--owner-truth-summary", type=Path, required=True)
    parser.add_argument("--system-health", type=Path, required=True)
    parser.add_argument("--po-sku-daily", type=Path, required=True)
    parser.add_argument("--owner-profit-daily", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("exports/owner"))
    args = parser.parse_args()
    payload = build_inventory_capital_radar(
        as_of=args.as_of,
        owner_truth_summary_path=args.owner_truth_summary,
        system_health_path=args.system_health,
        po_sku_daily_path=args.po_sku_daily,
        owner_profit_daily_path=args.owner_profit_daily,
        output_root=args.output_root,
    )
    out_dir = args.output_root / args.as_of
    print(f"inventory_capital_radar_json={(out_dir / 'inventory_capital_radar.json').resolve()}")
    print(f"inventory_capital_radar_md={(out_dir / 'inventory_capital_radar.md').resolve()}")
    print(f"status={payload['status']}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
