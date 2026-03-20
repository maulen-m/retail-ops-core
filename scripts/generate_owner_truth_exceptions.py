#!/usr/bin/env python3
"""Generate deterministic owner-truth exceptions artifacts from governance prereqs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DAILY_ROOT = PROJECT_ROOT / "exports" / "daily"
DEFAULT_EXCEPTIONS_ROOT = PROJECT_ROOT / "exports" / "exceptions"


def _render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# Owner Truth Exceptions",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        f"- as_of: `{payload['as_of']}`",
        f"- status: `{payload['status']}`",
        f"- critical_count: `{payload['critical_count']}`",
        "",
    ]
    exceptions = payload.get("exceptions") or []
    if not exceptions:
        lines.extend(
            [
                "## Exceptions",
                "",
                "None.",
                "",
            ]
        )
        return "\n".join(lines)

    lines.extend(
        [
            "## Exceptions",
            "",
            "| id | step | domain | severity | rc | reason |",
            "|---|---|---|---|---:|---|",
        ]
    )
    for row in exceptions:
        lines.append(
            f"| `{row['id']}` | `{row['step']}` | `{row['domain']}` | `{row['severity']}` | "
            f"{row['rc']} | {row['reason']} |"
        )
    return "\n".join(lines) + "\n"


def generate_owner_truth_exceptions(
    *,
    as_of: str,
    daily_report_json: Path,
    output_dir: Path,
    strict: bool,
) -> dict[str, Any]:
    report_path = daily_report_json.resolve()
    payload: dict[str, Any]

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        ok = False
        status = "RED"
        exceptions = [
            {
                "id": "daily_ops_report_missing_or_invalid",
                "step": "daily_ops_report",
                "domain": "runtime",
                "severity": "critical",
                "owner": "ops-codex",
                "recommended_action": "Regenerate the daily ops report for the same as_of before rerunning doctor.",
                "evidence_paths": [str(report_path)],
                "rc": 1,
                "reason": f"daily_ops_report unreadable: {exc}",
            }
        ]
        steps = []
    else:
        ok = bool(report.get("ok", False)) and str(report.get("status", "")).upper() == "GREEN"
        status = "GREEN" if ok else "RED"
        steps = [
            {
                "step": "daily_ops_report",
                "ok": ok,
                "rc": 0 if ok else 1,
                "summary": f"status={str(report.get('status', 'UNKNOWN')).upper()}",
            }
        ]
        exceptions = []
        if not ok:
            exceptions.append(
                {
                    "id": "daily_ops_report_red",
                    "step": "daily_ops_report",
                    "domain": "runtime",
                    "severity": "critical",
                    "owner": "ops-codex",
                    "recommended_action": "Inspect the daily ops report and rerun scripts/run_kaspi_daily_ops.py for the same as_of before publication.",
                    "evidence_paths": [str(report_path)],
                    "rc": 1,
                    "reason": f"daily_ops_report status={str(report.get('status', 'UNKNOWN')).upper()}",
                }
            )

    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of,
        "status": status,
        "ok": ok,
        "schema_version": "v1",
        "steps": steps,
        "exceptions": exceptions,
        "critical_count": sum(1 for row in exceptions if str(row.get("severity", "")).lower() == "critical"),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "exceptions.json"
    md_path = output_dir / "exceptions.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_md(payload), encoding="utf-8")

    return {
        "ok": ok,
        "status": status,
        "exit_code": 0 if (ok or not strict) else 1,
        "json_path": str(json_path),
        "md_path": str(md_path),
        "payload": payload,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate deterministic owner-truth exceptions artifacts")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--daily-report-json", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    daily_report_json = args.daily_report_json or (DEFAULT_DAILY_ROOT / args.as_of / "daily_ops_report.json")
    output_dir = args.output_dir or (DEFAULT_EXCEPTIONS_ROOT / args.as_of)
    report = generate_owner_truth_exceptions(
        as_of=args.as_of,
        daily_report_json=daily_report_json,
        output_dir=output_dir,
        strict=bool(args.strict),
    )
    print(f"exceptions_json={report['json_path']}")
    print(f"exceptions_md={report['md_path']}")
    print(f"status={'PASS' if report['ok'] else 'FAIL'}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
