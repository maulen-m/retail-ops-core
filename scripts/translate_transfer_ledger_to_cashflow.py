#!/usr/bin/env python3
"""Translate transfer ledger to cashflow events with idempotence proof artifacts."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.import_transfer_ledger_cashflow import import_transfer_ledger

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "daily"


def _count_events(db_path: Path) -> int:
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute("SELECT COUNT(*) FROM fact_cashflow_events").fetchone()
        return int(row[0] if row else 0)


def _render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# Transfer Ledger Translation Report",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        f"- as_of: `{payload['as_of']}`",
        f"- mode: `{payload['mode']}`",
        f"- status: `{payload['status']}`",
        f"- dry_run_first_count: `{payload['dry_run_first_count']}`",
        f"- dry_run_second_count: `{payload['dry_run_second_count']}`",
        f"- applied_count: `{payload['applied_count']}`",
        f"- post_apply_dry_run_count: `{payload['post_apply_dry_run_count']}`",
    ]
    if payload.get("backup_path"):
        lines.append(f"- backup_path: `{payload['backup_path']}`")
    if payload.get("errors"):
        lines.extend(["", "## Errors"])
        for err in payload["errors"]:
            lines.append(f"- {err}")
    return "\n".join(lines) + "\n"


def translate_transfer_ledger_to_cashflow(
    *,
    db_path: Path,
    as_of: str,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    since: date | None = None,
    until: date | None = None,
    apply: bool = False,
    backup_path: Path | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    if not db_path.exists():
        raise FileNotFoundError(f"db not found: {db_path}")

    if apply:
        if os.environ.get("ENABLE_CASHFLOW_WRITE") != "1":
            raise RuntimeError("ENABLE_CASHFLOW_WRITE=1 is required for --apply")
        if backup_path is None:
            raise RuntimeError("--backup-path is required for --apply")
        if not backup_path.exists():
            raise RuntimeError(f"backup path does not exist: {backup_path}")

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    before_count = _count_events(db_path)

    dry_run_first = import_transfer_ledger(
        db_path=db_path,
        since=since,
        until=until,
        apply=False,
        run_id=f"{run_id}_preview1",
    )
    dry_run_second = import_transfer_ledger(
        db_path=db_path,
        since=since,
        until=until,
        apply=False,
        run_id=f"{run_id}_preview2",
    )
    if dry_run_first != dry_run_second:
        errors.append(
            f"dry-run idempotence mismatch: first={dry_run_first} second={dry_run_second}"
        )

    applied_count = 0
    post_apply_dry_run = dry_run_second
    if apply:
        applied_count = import_transfer_ledger(
            db_path=db_path,
            since=since,
            until=until,
            apply=True,
            run_id=f"{run_id}_apply",
        )
        post_apply_dry_run = import_transfer_ledger(
            db_path=db_path,
            since=since,
            until=until,
            apply=False,
            run_id=f"{run_id}_post_apply_preview",
        )
        if post_apply_dry_run != 0:
            errors.append(
                "post-apply dry-run must be zero for idempotence proof"
            )

    after_count = _count_events(db_path)
    if apply and (after_count - before_count) < applied_count:
        errors.append(
            f"event count drift: before={before_count} after={after_count} applied={applied_count}"
        )

    ok = len(errors) == 0
    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of,
        "mode": "apply" if apply else "dry-run",
        "status": "GREEN" if ok else "RED",
        "ok": ok,
        "db_path": str(db_path),
        "backup_path": str(backup_path) if backup_path else None,
        "dry_run_first_count": int(dry_run_first),
        "dry_run_second_count": int(dry_run_second),
        "applied_count": int(applied_count),
        "post_apply_dry_run_count": int(post_apply_dry_run),
        "before_event_count": int(before_count),
        "after_event_count": int(after_count),
        "errors": errors,
    }

    out_dir = Path(output_root).resolve() / as_of
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "transfer_ledger_translation_report.json"
    md_path = out_dir / "transfer_ledger_translation_report.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_md(payload), encoding="utf-8")

    return {
        "ok": ok,
        "exit_code": 0 if (ok or not strict) else 1,
        "json_path": str(json_path),
        "md_path": str(md_path),
        "payload": payload,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Translate transfer ledger to cashflow events")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--since", type=str, default=None)
    parser.add_argument("--until", type=str, default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-path", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    since = date.fromisoformat(args.since) if args.since else None
    until = date.fromisoformat(args.until) if args.until else None
    report = translate_transfer_ledger_to_cashflow(
        db_path=args.db,
        as_of=args.as_of,
        output_root=args.output_root,
        since=since,
        until=until,
        apply=bool(args.apply),
        backup_path=args.backup_path,
        strict=bool(args.strict),
    )
    print(f"transfer_translation_json={report['json_path']}")
    print(f"transfer_translation_md={report['md_path']}")
    print(f"status={'PASS' if report['ok'] else 'FAIL'}")
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
