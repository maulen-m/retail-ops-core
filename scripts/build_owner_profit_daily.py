#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _to_float(value: Any) -> float | None:
    if value in (None, "", "nan", "NaN"):
        return None
    return round(float(value), 2)


def _boolish(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# Owner Profit Daily",
        "",
        f"- as_of: `{payload['as_of']}`",
        f"- status: `{payload['status']}`",
        f"- trust_banner: `{payload['trust_banner']}`",
        f"- semantics_mode: `{payload['semantics_mode']}`",
        f"- semantics_contract: `{payload['semantics_contract']}`",
        f"- derived_profit_rows: `{payload['derived_profit_rows']}`",
        f"- owner_truth_status: `{payload['sources']['owner_truth_summary']['status']}`",
        f"- system_health_status: `{payload['sources']['system_health']['status']}`",
        f"- publication_readiness_status: `{payload['sources']['publication_readiness']['status']}`",
        "",
        "| Month | Revenue | COGS | Ads | OPEX | Profit After Ads | Profit After Ads+OPEX | Provisional | Source Locked |",
        "|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in payload["rows"]:
        lines.append(
            f"| `{row['sale_month']}` | {row['net_rev_kzt']:.2f} | {row['cogs_kzt']:.2f} | "
            f"{row['ads_kzt']:.2f} | {row['opex_kzt']:.2f} | {row['profit_after_ads_kzt']:.2f} | "
            f"{row['profit_after_ads_and_opex_kzt']:.2f} | `{str(bool(row['provisional'])).lower()}` | "
            f"`{str(bool(row['source_profit_locked'])).lower()}` |"
        )
    return "\n".join(lines) + "\n"


def build_owner_profit_daily(
    *,
    as_of: str,
    owner_truth_summary_path: Path,
    system_health_path: Path,
    review_dir: Path,
    output_root: Path,
    validation_root: Path,
) -> dict[str, Any]:
    owner_truth = _read_json(owner_truth_summary_path)
    system_health = _read_json(system_health_path)
    publication_readiness = _read_json(review_dir / "publication_readiness.json")
    monthly_rows = _read_csv_rows(review_dir / "monthly_totals_review.csv")

    out_rows: list[dict[str, Any]] = []
    derived_profit_rows = 0
    for row in monthly_rows:
        net_rev = _to_float(row.get("net_rev_kzt")) or 0.0
        cogs = _to_float(row.get("cogs_kzt")) or 0.0
        ads = _to_float(row.get("ads_kzt")) or 0.0
        opex = _to_float(row.get("opex_kzt")) or 0.0
        profit_after_ads = _to_float(row.get("profit_after_ads_kzt"))
        profit_after_ads_opex = _to_float(row.get("profit_after_ads_and_opex_kzt"))
        derived = False
        if profit_after_ads is None:
            profit_after_ads = round(net_rev - cogs - ads, 2)
            derived = True
        if profit_after_ads_opex is None:
            profit_after_ads_opex = round(profit_after_ads - opex, 2)
            derived = True
        if derived:
            derived_profit_rows += 1
        out_rows.append(
            {
                "sale_month": row.get("sale_month"),
                "orders": int(float(row.get("orders") or 0)),
                "units": _to_float(row.get("units")) or 0.0,
                "net_rev_kzt": net_rev,
                "cogs_kzt": cogs,
                "ads_kzt": ads,
                "opex_kzt": opex,
                "profit_after_ads_kzt": profit_after_ads,
                "profit_after_ads_and_opex_kzt": profit_after_ads_opex,
                "provisional": _boolish(row.get("provisional")),
                "source_profit_locked": _boolish(row.get("profit_locked")),
                "derived_profit": derived,
            }
        )

    ok = (
        str(owner_truth.get("status")) == "PASS"
        and str(system_health.get("status")) == "GREEN"
        and str(publication_readiness.get("status")) == "PASS"
    )
    semantics_contract = "docs/validation/OWNER_PROFIT_DAILY_SEMANTICS_CONTRACT.md"
    semantics_mode = (
        "PROVISIONAL_DERIVED_FROM_LOCKED_MONTHLY_REVIEW"
        if ok and derived_profit_rows > 0
        else ("GREEN_LIVE_CHAIN_DECISION_GRADE" if ok else "FAIL_UPSTREAM_GATES")
    )
    trust_banner = (
        "PASS_PROVISIONAL_DERIVED_FROM_GREEN_LIVE_CHAIN"
        if ok and derived_profit_rows > 0
        else ("PASS_GREEN_LIVE_CHAIN" if ok else "FAIL_UPSTREAM_GATES")
    )
    payload = {
        "generated_at": _now_utc(),
        "as_of": as_of,
        "status": "PASS" if ok else "FAIL",
        "ok": ok,
        "trust_banner": trust_banner,
        "semantics_mode": semantics_mode,
        "semantics_contract": semantics_contract,
        "derived_profit_rows": derived_profit_rows,
        "sources": {
            "owner_truth_summary": {"path": str(owner_truth_summary_path), "status": owner_truth.get("status")},
            "system_health": {"path": str(system_health_path), "status": system_health.get("status")},
            "publication_readiness": {
                "path": str((review_dir / "publication_readiness.json").resolve()),
                "status": publication_readiness.get("status"),
            },
            "monthly_review_csv": str((review_dir / "monthly_totals_review.csv").resolve()),
        },
        "rows": out_rows,
    }

    out_dir = output_root / as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "owner_profit_daily.json"
    md_path = out_dir / "owner_profit_daily.md"
    _write_json(json_path, payload)
    md_path.write_text(_render_md(payload), encoding="utf-8")

    trust_dir = validation_root / as_of
    trust_report = {
        "generated_at": _now_utc(),
        "status": "PASS" if ok else "FAIL",
        "trust_banner": trust_banner,
        "semantics_mode": semantics_mode,
        "semantics_contract": semantics_contract,
        "derived_profit_rows": derived_profit_rows,
        "json_path": str(json_path.resolve()),
        "md_path": str(md_path.resolve()),
    }
    _write_json(trust_dir / "trust_report.json", trust_report)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Build owner profit daily surface.")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--owner-truth-summary", type=Path, required=True)
    parser.add_argument("--system-health", type=Path, required=True)
    parser.add_argument("--review-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("exports/owner"))
    parser.add_argument("--validation-root", type=Path, default=Path("exports/validation/owner_profit_daily"))
    args = parser.parse_args()
    payload = build_owner_profit_daily(
        as_of=args.as_of,
        owner_truth_summary_path=args.owner_truth_summary,
        system_health_path=args.system_health,
        review_dir=args.review_dir,
        output_root=args.output_root,
        validation_root=args.validation_root,
    )
    print(f"owner_profit_daily_json={(args.output_root / args.as_of / 'owner_profit_daily.json').resolve()}")
    print(f"owner_profit_daily_md={(args.output_root / args.as_of / 'owner_profit_daily.md').resolve()}")
    print(f"status={payload['status']}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
