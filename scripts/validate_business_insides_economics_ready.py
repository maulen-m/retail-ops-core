#!/usr/bin/env python3
"""Fail-closed economics readiness validator for BUSINESS_INSIDES."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.generate_business_insides import compute_sales_metrics


DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "business_insides_economics"
DEFAULT_BUSINESS_DIR = PROJECT_ROOT / "config" / "business_insides"


def _resolve_snapshot_json(*, business_dir: Path, as_of: str) -> Path | None:
    direct = business_dir / f"BUSINESS_INSIDES_{as_of}.json"
    if direct.exists():
        return direct
    alt = business_dir / "snapshots" / f"BUSINESS_INSIDES_{as_of}.json"
    if alt.exists():
        return alt
    return None


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# BUSINESS_INSIDES Economics Readiness",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- status: `{report['status']}`",
        f"- snapshot_json: `{report.get('snapshot_json')}`",
        f"- profit_publication_locked: `{str(bool(report.get('profit_publication_locked'))).lower()}`",
        f"- economics_volatility_days: `{report.get('economics_volatility_days')}`",
        "",
        "| check | status | details |",
        "|---|---:|---|",
    ]
    for row in report["checks"]:
        lines.append(f"| `{row['check']}` | {'PASS' if row['ok'] else 'FAIL'} | {row['details']} |")
    if report["errors"]:
        lines.extend(["", "## Errors", ""])
        for err in report["errors"]:
            lines.append(f"- {err}")
    return "\n".join(lines) + "\n"


def validate_business_insides_economics_ready(
    *,
    db_path: Path,
    as_of: str,
    output_root: Path,
    business_dir: Path,
    snapshot_json_path: Path | None,
    strict: bool,
    volatility_days: int | None = None,
    metrics_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    checks: list[dict[str, Any]] = []
    as_of_date = date.fromisoformat(as_of)

    snapshot_path = snapshot_json_path.resolve() if snapshot_json_path else _resolve_snapshot_json(
        business_dir=business_dir.resolve(),
        as_of=as_of,
    )
    snapshot_payload = _read_json(snapshot_path)
    if snapshot_payload is None:
        errors.append(
            f"missing BUSINESS_INSIDES JSON snapshot for as_of={as_of} in {business_dir.resolve()}"
        )
    else:
        snapshot_as_of = str(snapshot_payload.get("as_of") or "").strip()
        ok = snapshot_as_of == as_of
        checks.append(
            {
                "check": "snapshot_as_of_match",
                "ok": ok,
                "details": f"expected={as_of} actual={snapshot_as_of or '<missing>'}",
            }
        )
        if not ok:
            errors.append(
                f"snapshot as_of mismatch: expected {as_of}, got {snapshot_as_of or '<missing>'}"
            )

    metrics = metrics_override or compute_sales_metrics(
        db_path=db_path.resolve(),
        as_of=as_of_date,
        # Match strict BUSINESS_INSIDES semantics: do not backfill revenue from
        # completed-order fallbacks when validating decision-grade readiness.
        allow_completed_revenue_fallback=False,
    )

    missing_days = sorted(str(day) for day in metrics.get("economics_missing_days") or [])
    nonvolatile_missing = sorted(
        str(day) for day in metrics.get("economics_missing_nonvolatile_days") or []
    )
    metrics_volatility = int(metrics.get("economics_volatility_days") or 0)
    if volatility_days is not None:
        metrics_volatility = int(volatility_days)

    locked = bool(metrics.get("profit_publication_locked"))
    checks.append(
        {
            "check": "economics_lock_if_missing_days",
            "ok": (not missing_days) or locked,
            "details": f"missing_days={len(missing_days)} locked={locked}",
        }
    )
    if missing_days and not locked:
        errors.append("economics missing days detected while profit publication lock is OFF")

    checks.append(
        {
            "check": "nonvolatile_missing_days_zero",
            "ok": len(nonvolatile_missing) == 0,
            "details": ",".join(nonvolatile_missing) if nonvolatile_missing else "none",
        }
    )
    if nonvolatile_missing:
        errors.append(
            "nonvolatile economics gaps detected for days: " + ", ".join(nonvolatile_missing)
        )

    if snapshot_payload is not None:
        perf = snapshot_payload.get("performance") or {}
        perf_cogs = perf.get("avg_30d_cogs_kzt")
        perf_profit = perf.get("avg_30d_profit_kzt")
        if locked and (perf_cogs is not None or perf_profit is not None):
            errors.append(
                "profit publication lock is ON but BUSINESS_INSIDES performance still exposes COGS/profit"
            )
            checks.append(
                {
                    "check": "locked_snapshot_masks_profit_fields",
                    "ok": False,
                    "details": f"avg_30d_cogs_kzt={perf_cogs} avg_30d_profit_kzt={perf_profit}",
                }
            )
        else:
            checks.append(
                {
                    "check": "locked_snapshot_masks_profit_fields",
                    "ok": True,
                    "details": f"avg_30d_cogs_kzt={perf_cogs} avg_30d_profit_kzt={perf_profit}",
                }
            )

    ok = len(errors) == 0
    out_dir = output_root.resolve() / as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of,
        "status": "PASS" if ok else "FAIL",
        "ok": bool(ok),
        "snapshot_json": str(snapshot_path) if snapshot_path else None,
        "db_path": str(db_path.resolve()),
        "economics_volatility_days": int(metrics_volatility),
        "economics_missing_days": missing_days,
        "economics_missing_nonvolatile_days": nonvolatile_missing,
        "profit_publication_locked": locked,
        "checks": checks,
        "errors": errors,
    }
    json_path = out_dir / "economics_ready_report.json"
    md_path = out_dir / "economics_ready_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)

    if strict and not ok:
        raise RuntimeError("business insides economics readiness failed")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate BUSINESS_INSIDES economics readiness (fail-closed)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--business-dir", type=Path, default=DEFAULT_BUSINESS_DIR)
    parser.add_argument("--snapshot-json", type=Path, default=None)
    parser.add_argument("--volatility-days", type=int, default=None)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = validate_business_insides_economics_ready(
        db_path=args.db,
        as_of=str(args.as_of),
        output_root=args.output_root,
        business_dir=args.business_dir,
        snapshot_json_path=args.snapshot_json,
        strict=bool(args.strict),
        volatility_days=args.volatility_days,
    )
    print(f"business_insides_economics_json={report['json_path']}")
    print(f"business_insides_economics_md={report['md_path']}")
    print(f"status={report['status']}")
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
