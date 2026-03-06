#!/usr/bin/env python3
"""Generate deterministic daily GREEN/RED report from orchestrator summary."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SUMMARY_ROOT = PROJECT_ROOT / "exports" / "validation" / "board_v8_runtime"
DEFAULT_DAILY_ROOT = PROJECT_ROOT / "exports" / "daily"


def _render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# Daily Ops Report",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        f"- as_of: `{payload['as_of']}`",
        f"- status: `{payload['status']}`",
        f"- profile: `{payload['profile']}`",
        f"- steps_failed: `{payload['steps_failed']}` / `{payload['steps_total']}`",
        f"- stores_red: `{payload['stores_red']}` / `{payload['stores_total']}`",
        "",
        "## Shipping Backlog",
    ]
    shipping_backlog = payload.get("shipping_backlog") or {}
    if shipping_backlog.get("present"):
        lines.extend(
            [
                f"- scope: `{shipping_backlog.get('scope', '')}`",
                f"- initial_overdue_pending: `{shipping_backlog.get('initial_overdue_pending', 0)}`",
                f"- initial_stale_pending: `{shipping_backlog.get('initial_stale_pending', 0)}`",
                f"- remaining_overdue_pending: `{shipping_backlog.get('remaining_overdue_pending', 0)}`",
                f"- remaining_stale_pending: `{shipping_backlog.get('remaining_stale_pending', 0)}`",
                f"- report_md: `{shipping_backlog.get('md_path', '')}`",
            ]
        )
    else:
        lines.append("- present: `False`")
    lines.extend(
        [
            "",
        "## Store Results",
        ]
    )
    for store, meta in sorted(payload["store_results"].items()):
        state = "GREEN" if meta.get("ok") else "RED"
        lines.append(f"- `{store}`: {state} rc={meta.get('rc')} | {meta.get('summary', '')}")
    return "\n".join(lines) + "\n"


def generate_daily_ops_report(*, summary_json: Path, output_dir: Path) -> dict[str, Any]:
    summary = json.loads(summary_json.read_text(encoding="utf-8"))
    as_of = str(summary.get("as_of") or "")
    if not as_of:
        raise RuntimeError("daily ops summary missing as_of")

    store_results = summary.get("store_results") or {}
    if not isinstance(store_results, dict):
        raise RuntimeError("daily ops summary store_results must be an object")

    steps = summary.get("steps") or []
    if not isinstance(steps, list):
        raise RuntimeError("daily ops summary steps must be a list")

    if not store_results:
        for row in steps:
            step = str(row.get("step") or "")
            if not step.startswith("waybill_status_"):
                continue
            store = step.replace("waybill_status_", "", 1)
            store_results[store] = {
                "ok": bool(row.get("ok", False)),
                "rc": int(row.get("rc", 1)),
                "summary": str(row.get("summary", "")),
            }

    stores_total = len(store_results)
    stores_red = sum(1 for meta in store_results.values() if not bool(meta.get("ok", False)))
    stores_green = stores_total - stores_red
    steps_total = len(steps)
    steps_failed = sum(1 for row in steps if not bool(row.get("ok", False)))

    ok = bool(summary.get("ok", False)) and stores_red == 0
    status = "GREEN" if ok else "RED"
    shipping_backlog = summary.get("shipping_backlog_latest") or {
        "present": False,
        "scope": "",
        "json_path": "",
        "md_path": "",
        "initial_overdue_pending": 0,
        "initial_stale_pending": 0,
        "remaining_overdue_pending": 0,
        "remaining_stale_pending": 0,
    }

    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of,
        "status": status,
        "ok": ok,
        "exit_code": int(summary.get("exit_code", 1)),
        "profile": str(summary.get("profile", "")),
        "steps_total": steps_total,
        "steps_failed": steps_failed,
        "stores_total": stores_total,
        "stores_red": stores_red,
        "stores_green": stores_green,
        "store_results": store_results,
        "shipping_backlog": shipping_backlog,
        "summary_json": str(summary_json),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "daily_ops_report.json"
    md_path = output_dir / "daily_ops_report.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_md(payload), encoding="utf-8")

    return {
        "json_path": str(json_path),
        "md_path": str(md_path),
        "status": status,
        "as_of": as_of,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate daily ops GREEN/RED report")
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--summary-json", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    summary_json = args.summary_json or (DEFAULT_SUMMARY_ROOT / args.as_of / "daily_ops_summary.json")
    output_dir = args.output_dir or (DEFAULT_DAILY_ROOT / args.as_of)
    result = generate_daily_ops_report(summary_json=summary_json, output_dir=output_dir)
    print(f"daily_report_json={result['json_path']}")
    print(f"daily_report_md={result['md_path']}")
    print(f"status={result['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
