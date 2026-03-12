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
    return "\n".join(
        [
            "# Cash Risk Daily",
            "",
            f"- as_of: `{payload['as_of']}`",
            f"- status: `{payload['status']}`",
            f"- trust_banner: `{payload['trust_banner']}`",
            f"- base_min_cash_kzt: `{payload['base_min_cash_kzt']}` on `{payload['base_min_cash_date']}`",
            f"- conservative_min_cash_kzt: `{payload['conservative_min_cash_kzt']}` on `{payload['conservative_min_cash_date']}`",
            f"- opex_monthly_kzt: `{payload['opex_monthly_kzt']}`",
            f"- po_total_cogs_kzt: `{payload['po_total_cogs_kzt']}`",
            f"- real_pos_count: `{payload['real_pos_count']}`",
            "",
        ]
    ) + "\n"


def build_cash_risk_daily(
    *,
    as_of: str,
    owner_truth_summary_path: Path,
    system_health_path: Path,
    cashfloor_gate_path: Path,
    po_dashboard_path: Path,
    output_root: Path,
    validation_root: Path,
) -> dict[str, Any]:
    owner_truth = _read_json(owner_truth_summary_path)
    system_health = _read_json(system_health_path)
    cashfloor = _read_json(cashfloor_gate_path)
    po_dashboard = _read_json(po_dashboard_path)
    ok = (
        str(owner_truth.get("status")) == "PASS"
        and str(system_health.get("status")) == "GREEN"
        and bool(cashfloor.get("ok"))
    )
    summary = po_dashboard.get("summary") or {}
    real_pos = po_dashboard.get("real_pos") or []
    payload = {
        "generated_at": _now_utc(),
        "as_of": as_of,
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "trust_banner": "PASS_GREEN_LIVE_CHAIN" if ok else "FAIL_UPSTREAM_GATES",
        "base_min_cash_kzt": cashfloor.get("base_min_cash_kzt"),
        "base_min_cash_date": cashfloor.get("base_min_cash_date"),
        "conservative_min_cash_kzt": cashfloor.get("conservative_min_cash_kzt"),
        "conservative_min_cash_date": cashfloor.get("conservative_min_cash_date"),
        "opex_monthly_kzt": cashfloor.get("opex_monthly_kzt"),
        "po_total_cogs_kzt": summary.get("total_po_cogs_kzt"),
        "po_total_base_cost_kzt": summary.get("total_po_base_cost_kzt"),
        "po_total_dlv_kzt": summary.get("total_po_dlv_kzt"),
        "real_pos_count": len(real_pos),
        "sources": {
            "owner_truth_summary": str(owner_truth_summary_path),
            "system_health": str(system_health_path),
            "cashfloor_gate": str(cashfloor_gate_path),
            "po_dashboard": str(po_dashboard_path),
        },
    }
    out_dir = output_root / as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "cash_risk_daily.json"
    md_path = out_dir / "cash_risk_daily.md"
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
    parser = argparse.ArgumentParser(description="Build cash risk daily surface.")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--owner-truth-summary", type=Path, required=True)
    parser.add_argument("--system-health", type=Path, required=True)
    parser.add_argument("--cashfloor-gate", type=Path, required=True)
    parser.add_argument("--po-dashboard", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("exports/owner"))
    parser.add_argument("--validation-root", type=Path, default=Path("exports/validation/cash_risk_daily"))
    args = parser.parse_args()
    payload = build_cash_risk_daily(
        as_of=args.as_of,
        owner_truth_summary_path=args.owner_truth_summary,
        system_health_path=args.system_health,
        cashfloor_gate_path=args.cashfloor_gate,
        po_dashboard_path=args.po_dashboard,
        output_root=args.output_root,
        validation_root=args.validation_root,
    )
    print(f"cash_risk_daily_json={(args.output_root / args.as_of / 'cash_risk_daily.json').resolve()}")
    print(f"cash_risk_daily_md={(args.output_root / args.as_of / 'cash_risk_daily.md').resolve()}")
    print(f"status={payload['status']}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
