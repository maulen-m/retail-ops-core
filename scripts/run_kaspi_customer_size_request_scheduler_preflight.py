#!/usr/bin/env python3
"""Prepare a no-send scheduler preflight for Kaspi customer size requests.

This script is safe to run repeatedly. It refreshes active missing-size orders
into the local control-plane ledger and writes redacted next-action artifacts.
It does not install a scheduler and does not send or write external systems.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from core.ops.customer_size_request import (
    DEFAULT_REQUEST_TEMPLATE,
    build_customer_size_next_actions,
    build_request_ledger_plan,
    build_update_plan_from_ledger_snapshot,
    export_customer_size_ledger_snapshot,
    load_missing_size_candidates,
    normalize_request_template,
    request_template_hash,
    sha256_file,
    summarize_customer_size_ledger,
    upsert_request_ledger_plan,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "db" / "app.db"
DEFAULT_LEDGER_DB = (
    REPO_ROOT
    / "runtime"
    / "customer_size_request_ledger"
    / "no_send_customer_size_request_ledger.sqlite"
)
DEFAULT_RECOMMENDED_CADENCE_MINUTES = 10


def _parse_date(value: str | None) -> date:
    if not value:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (list, dict))
                    else value
                    for key, value in row.items()
                }
            )


def _safe_sha(path: Path) -> str | None:
    return sha256_file(path) if path.exists() else None


def _default_output_dir(target_date: date) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (
        REPO_ROOT
        / "exports"
        / "validation"
        / f"kaspi_customer_size_request_scheduler_preflight_{target_date.isoformat()}_{stamp}"
    )


def _write_scheduler_proposal(
    path: Path,
    *,
    command: str,
    cadence_minutes: int,
    output_dir: Path,
) -> None:
    text = "\n".join(
        [
            "# Kaspi Customer Size Request Scheduler Proposal",
            "",
            "Gate: PROPOSAL_ONLY_NO_SCHEDULER_CHANGE",
            "",
            f"- Recommended cadence: every {cadence_minutes} minutes during active shipping/order intake windows.",
            "- Purpose: detect newly imported missing-size orders early, keep the local no-send ledger fresh, and expose next actions.",
            "- This proposal does not install LaunchAgents, cron entries, or scheduler state.",
            "",
            "Suggested command shape:",
            "",
            "```bash",
            command,
            "```",
            "",
            f"- Evidence folder for this preflight: {output_dir}",
            "",
            "Hard stoplines:",
            "",
            "- No customer messages without a separate live-send approval.",
            "- No Kaspi chat/API write without a separate approval.",
            "- No Google Board write without a separate approval.",
            "- No production DB write without the existing DB apply gate.",
            "",
        ]
    )
    path.write_text(text, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build repeated no-send scheduler preflight artifacts for Kaspi size requests."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--ledger-db", type=Path, default=DEFAULT_LEDGER_DB)
    parser.add_argument("--target-date", help="YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--lookback-days", type=int, default=3)
    parser.add_argument("--store", action="append", default=[], help="Optional store_code filter.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--template", default=DEFAULT_REQUEST_TEMPLATE)
    parser.add_argument(
        "--recommended-cadence-minutes",
        type=int,
        default=DEFAULT_RECOMMENDED_CADENCE_MINUTES,
    )
    parser.add_argument("--output-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    target_date = _parse_date(args.target_date)
    output_dir = args.output_dir or _default_output_dir(target_date)
    output_dir.mkdir(parents=True, exist_ok=True)

    db_path = args.db.resolve()
    ledger_path = args.ledger_db.resolve()
    template = normalize_request_template(args.template)
    app_db_sha_before = _safe_sha(db_path)
    ledger_sha_before = _safe_sha(ledger_path)

    candidates = load_missing_size_candidates(
        db_path,
        target_date=target_date,
        lookback_days=args.lookback_days,
        stores=args.store,
        limit=args.limit,
    )
    request_plan_rows = build_request_ledger_plan(candidates, template=template)
    ledger_upsert_stats = upsert_request_ledger_plan(ledger_path, request_plan_rows)
    ledger_snapshot_rows = export_customer_size_ledger_snapshot(ledger_path)
    next_action_rows = build_customer_size_next_actions(ledger_snapshot_rows)
    google_board_size_fill_rows = build_update_plan_from_ledger_snapshot(ledger_snapshot_rows)
    summary = summarize_customer_size_ledger(ledger_snapshot_rows)

    app_db_sha_after = _safe_sha(db_path)
    ledger_sha_after = _safe_sha(ledger_path)

    _write_json(output_dir / "request_ledger_plan_no_send.json", request_plan_rows)
    _write_csv(output_dir / "request_ledger_plan_no_send.csv", request_plan_rows)
    _write_json(output_dir / "ledger_snapshot_redacted.json", ledger_snapshot_rows)
    _write_csv(output_dir / "ledger_snapshot_redacted.csv", ledger_snapshot_rows)
    _write_json(output_dir / "next_actions_redacted.json", next_action_rows)
    _write_csv(output_dir / "next_actions_redacted.csv", next_action_rows)
    _write_json(
        output_dir / "google_board_size_fill_plan_dry_run.json",
        google_board_size_fill_rows,
    )
    _write_csv(
        output_dir / "google_board_size_fill_plan_dry_run.csv",
        google_board_size_fill_rows,
    )
    _write_json(output_dir / "scheduler_summary.json", summary)

    command = (
        f"PYTHONPATH=. .venv/bin/python {REPO_ROOT / 'scripts' / 'run_kaspi_customer_size_request_scheduler_preflight.py'} "
        f"--db {db_path} --ledger-db {ledger_path} "
        "--target-date today --lookback-days 3"
    )
    _write_scheduler_proposal(
        output_dir / "scheduler_proposal_no_apply.md",
        command=command,
        cadence_minutes=args.recommended_cadence_minutes,
        output_dir=output_dir,
    )

    manifest = {
        "gate": "GREEN_SCHEDULER_PREFLIGHT_NO_SEND_READY",
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "target_date": target_date.isoformat(),
        "lookback_days": args.lookback_days,
        "stores": args.store,
        "candidate_count": len(request_plan_rows),
        "ledger_snapshot_count": len(ledger_snapshot_rows),
        "next_action_count": len(next_action_rows),
        "google_board_size_fill_plan_dry_run_count": len(google_board_size_fill_rows),
        "scheduler_summary": summary,
        "ledger_upsert_stats": ledger_upsert_stats,
        "recommended_cadence_minutes": args.recommended_cadence_minutes,
        "scheduler_installed": False,
        "scheduler_change_allowed": False,
        "app_db_path": str(db_path),
        "app_db_sha256_before": app_db_sha_before,
        "app_db_sha256_after": app_db_sha_after,
        "app_db_unchanged": app_db_sha_before == app_db_sha_after,
        "ledger_db_path": str(ledger_path),
        "ledger_db_sha256_before": ledger_sha_before,
        "ledger_db_sha256_after": ledger_sha_after,
        "ledger_mutation_scope": "local_runtime_control_plane_only",
        "template_hash": request_template_hash(template),
        "template_text_not_exported": True,
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "raw_order_ids_exported": False,
        "raw_reply_text_exported": False,
    }
    _write_json(output_dir / "manifest.json", manifest)

    closeout = "\n".join(
        [
            "# Kaspi Customer Size Request Scheduler Preflight",
            "",
            "Gate: GREEN_SCHEDULER_PREFLIGHT_NO_SEND_READY",
            "",
            f"- Output folder: {output_dir}",
            f"- Local ledger DB: {ledger_path}",
            f"- Target date: {target_date.isoformat()}",
            f"- Missing-size request plan rows refreshed: {len(request_plan_rows)}",
            f"- Ledger snapshot rows: {len(ledger_snapshot_rows)}",
            f"- Next-action rows: {len(next_action_rows)}",
            f"- Google Board size-fill dry-run rows: {len(google_board_size_fill_rows)}",
            f"- Scheduler installed: False",
            f"- Recommended cadence: every {args.recommended_cadence_minutes} minutes",
            f"- App DB unchanged: {app_db_sha_before == app_db_sha_after}",
            "",
            "No customer messages were sent. No Kaspi UI/API, Google Board,",
            "production DB, Telegram, WhatsApp, workbook, scheduler, or external",
            "writes were performed. The only write is the local runtime control",
            "plane ledger.",
            "",
        ]
    )
    (output_dir / "closeout.md").write_text(closeout, encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
