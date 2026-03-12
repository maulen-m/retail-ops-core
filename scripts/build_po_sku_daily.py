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
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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
        "",
        "| PO ID | Supplier | Units | Cost CNY | Status |",
        "|---|---|---:|---:|---|",
    ]
    for row in payload["top_real_pos"]:
        lines.append(
            f"| `{row['po_id']}` | `{row['supplier_code']}` | {row['units_total']} | {row['total_cost_cny']:.2f} | `{row['status']}` |"
        )
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
    top_real_pos = sorted(
        [
            {
                "po_id": str(row.get("po_id") or ""),
                "supplier_code": str(row.get("supplier_code") or ""),
                "units_total": int(float(row.get("units_total") or 0)),
                "total_cost_cny": round(float(row.get("total_cost_cny") or 0.0), 2),
                "status": str(row.get("status") or ""),
            }
            for row in real_pos
        ],
        key=lambda row: (row["total_cost_cny"], row["units_total"]),
        reverse=True,
    )[:max_rows]
    payload = {
        "generated_at": _now_utc(),
        "as_of": as_of,
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "trust_banner": "PASS_GREEN_LIVE_CHAIN" if ok else "FAIL_UPSTREAM_GATES",
        "summary": {
            "total_skus": summary.get("total_skus"),
            "total_units": summary.get("total_units"),
            "total_po_cogs_kzt": summary.get("total_po_cogs_kzt"),
            "priority_skus": summary.get("priority_skus"),
        },
        "top_real_pos": top_real_pos,
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
