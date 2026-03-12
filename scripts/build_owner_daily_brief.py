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


def _latest_profit_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    return sorted(rows, key=lambda row: str(row.get("sale_month") or ""))[-1]


def _render_md(payload: dict[str, Any]) -> str:
    profit = payload["sections"]["profit"]
    cash = payload["sections"]["cash_risk"]
    po_sku = payload["sections"]["po_sku"]
    latest_month = profit.get("latest_month") or {}
    lines = [
        "# Owner Daily Brief",
        "",
        f"- as_of: `{payload['as_of']}`",
        f"- status: `{payload['status']}`",
        f"- trust_banner: `{payload['trust_banner']}`",
        "",
        "## Profit",
        "",
        f"- trust_banner: `{profit['trust_banner']}`",
        f"- production_acceptable: `{str(bool(profit['production_acceptable'])).lower()}`",
        f"- decision_scope: `{profit['decision_scope']}`",
        f"- latest_sale_month: `{latest_month.get('sale_month')}`",
        f"- latest_net_rev_kzt: `{latest_month.get('net_rev_kzt')}`",
        f"- latest_profit_after_ads_kzt: `{latest_month.get('profit_after_ads_kzt')}`",
        f"- latest_profit_after_ads_and_opex_kzt: `{latest_month.get('profit_after_ads_and_opex_kzt')}`",
        "",
        "## Cash Risk",
        "",
        f"- trust_banner: `{cash['trust_banner']}`",
        f"- base_min_cash_kzt: `{cash['base_min_cash_kzt']}`",
        f"- conservative_min_cash_kzt: `{cash['conservative_min_cash_kzt']}`",
        f"- po_total_cogs_kzt: `{cash['po_total_cogs_kzt']}`",
        f"- real_pos_count: `{cash['real_pos_count']}`",
        "",
        "## PO / SKU",
        "",
        f"- trust_banner: `{po_sku['trust_banner']}`",
        f"- total_skus: `{po_sku['summary'].get('total_skus')}`",
        f"- total_units: `{po_sku['summary'].get('total_units')}`",
        f"- total_po_cogs_kzt: `{po_sku['summary'].get('total_po_cogs_kzt')}`",
        "",
        "| PO ID | Supplier | Units | Cost CNY |",
        "|---|---|---:|---:|",
    ]
    for row in po_sku["top_real_pos"]:
        lines.append(
            f"| `{row.get('po_id')}` | `{row.get('supplier_code')}` | {row.get('units_total')} | {row.get('total_cost_cny')} |"
        )
    return "\n".join(lines) + "\n"


def build_owner_daily_brief(
    *,
    as_of: str,
    owner_profit_path: Path,
    cash_risk_path: Path,
    po_sku_path: Path,
    output_root: Path,
    validation_root: Path,
) -> dict[str, Any]:
    owner_profit = _read_json(owner_profit_path)
    cash_risk = _read_json(cash_risk_path)
    po_sku = _read_json(po_sku_path)

    profit_ok = str(owner_profit.get("status")) == "PASS" and bool(owner_profit.get("production_acceptable"))
    cash_ok = str(cash_risk.get("status")) == "PASS"
    po_ok = str(po_sku.get("status")) == "PASS"
    ok = profit_ok and cash_ok and po_ok

    payload = {
        "generated_at": _now_utc(),
        "as_of": as_of,
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "trust_banner": "PASS_OWNER_DAILY_BRIEF_READY" if ok else "FAIL_OWNER_DAILY_BRIEF_BLOCKED",
        "sections": {
            "profit": {
                "trust_banner": owner_profit.get("trust_banner"),
                "production_acceptable": bool(owner_profit.get("production_acceptable")),
                "decision_scope": owner_profit.get("decision_scope"),
                "latest_month": _latest_profit_row(owner_profit.get("rows") or []),
                "rows": owner_profit.get("rows") or [],
                "source_path": str(owner_profit_path),
            },
            "cash_risk": {
                "trust_banner": cash_risk.get("trust_banner"),
                "base_min_cash_kzt": cash_risk.get("base_min_cash_kzt"),
                "conservative_min_cash_kzt": cash_risk.get("conservative_min_cash_kzt"),
                "po_total_cogs_kzt": cash_risk.get("po_total_cogs_kzt"),
                "real_pos_count": cash_risk.get("real_pos_count"),
                "source_path": str(cash_risk_path),
            },
            "po_sku": {
                "trust_banner": po_sku.get("trust_banner"),
                "summary": po_sku.get("summary") or {},
                "top_real_pos": po_sku.get("top_real_pos") or [],
                "source_path": str(po_sku_path),
            },
        },
    }

    out_dir = output_root / as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "owner_daily_brief.json"
    md_path = out_dir / "owner_daily_brief.md"
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
    parser = argparse.ArgumentParser(description="Build combined owner daily brief.")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--owner-profit", type=Path, required=True)
    parser.add_argument("--cash-risk", type=Path, required=True)
    parser.add_argument("--po-sku", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("exports/owner"))
    parser.add_argument("--validation-root", type=Path, default=Path("exports/validation/owner_daily_brief"))
    args = parser.parse_args()
    payload = build_owner_daily_brief(
        as_of=args.as_of,
        owner_profit_path=args.owner_profit,
        cash_risk_path=args.cash_risk,
        po_sku_path=args.po_sku,
        output_root=args.output_root,
        validation_root=args.validation_root,
    )
    print(f"owner_daily_brief_json={(args.output_root / args.as_of / 'owner_daily_brief.json').resolve()}")
    print(f"owner_daily_brief_md={(args.output_root / args.as_of / 'owner_daily_brief.md').resolve()}")
    print(f"status={payload['status']}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
