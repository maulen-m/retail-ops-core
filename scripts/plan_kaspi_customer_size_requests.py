#!/usr/bin/env python3
"""Plan Kaspi customer size requests without sending messages or writing DB."""
from __future__ import annotations

import argparse
import csv
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from core.ops.customer_size_request import (
    DEFAULT_REQUEST_TEMPLATE,
    build_google_board_update_plan,
    build_live_ui_canary_targets,
    build_request_ledger_plan,
    load_missing_size_candidates,
    normalize_request_template,
    request_template_hash,
    summarize_live_ui_targets_by_store,
    sha256_file,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "db" / "app.db"


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


def _read_synthetic_replies(path: Path | None) -> list[dict[str, Any]]:
    if not path:
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _default_output_dir(target_date: date) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (
        REPO_ROOT
        / "exports"
        / "validation"
        / f"kaspi_customer_size_request_no_send_{target_date.isoformat()}_{stamp}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a redacted no-send plan for Kaspi customer size requests."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--target-date", help="YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--lookback-days", type=int, default=3)
    parser.add_argument("--store", action="append", default=[], help="Optional store_code filter.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--template", default=DEFAULT_REQUEST_TEMPLATE)
    parser.add_argument(
        "--synthetic-replies-csv",
        type=Path,
        help="Optional local CSV with reply_text for parser/update-plan proof. Raw text is not emitted.",
    )
    parser.add_argument("--output-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    target_date = _parse_date(args.target_date)
    output_dir = args.output_dir or _default_output_dir(target_date)
    output_dir.mkdir(parents=True, exist_ok=True)

    db_path = args.db.resolve()
    db_sha_before = sha256_file(db_path) if db_path.exists() else None
    template = normalize_request_template(args.template)

    candidates = load_missing_size_candidates(
        db_path,
        target_date=target_date,
        lookback_days=args.lookback_days,
        stores=args.store,
        limit=args.limit,
    )
    candidate_rows = [candidate.to_redacted_dict() for candidate in candidates]
    ledger_rows = build_request_ledger_plan(candidates, template=template)
    live_ui_target_rows = build_live_ui_canary_targets(candidates)
    live_ui_store_summary_rows = summarize_live_ui_targets_by_store(live_ui_target_rows)
    reply_rows = _read_synthetic_replies(args.synthetic_replies_csv)
    update_plan_rows = build_google_board_update_plan(reply_rows)
    db_sha_after = sha256_file(db_path) if db_path.exists() else None

    _write_json(output_dir / "missing_size_candidates_redacted.json", candidate_rows)
    _write_csv(output_dir / "missing_size_candidates_redacted.csv", candidate_rows)
    _write_json(output_dir / "request_ledger_plan_no_send.json", ledger_rows)
    _write_csv(output_dir / "request_ledger_plan_no_send.csv", ledger_rows)
    _write_json(output_dir / "live_ui_canary_targets_redacted.json", live_ui_target_rows)
    _write_csv(output_dir / "live_ui_canary_targets_redacted.csv", live_ui_target_rows)
    _write_json(output_dir / "live_ui_canary_targets_by_store.json", live_ui_store_summary_rows)
    _write_csv(output_dir / "live_ui_canary_targets_by_store.csv", live_ui_store_summary_rows)
    _write_json(output_dir / "google_board_update_plan_dry_run.json", update_plan_rows)
    _write_csv(output_dir / "google_board_update_plan_dry_run.csv", update_plan_rows)

    manifest = {
        "gate": "GREEN_NO_SEND_PLAN_GENERATED",
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "db_path": str(db_path),
        "db_sha256_before": db_sha_before,
        "db_sha256_after": db_sha_after,
        "db_unchanged": db_sha_before == db_sha_after,
        "target_date": target_date.isoformat(),
        "lookback_days": args.lookback_days,
        "stores": args.store,
        "candidate_count": len(candidate_rows),
        "ledger_plan_count": len(ledger_rows),
        "live_ui_canary_target_count": len(live_ui_target_rows),
        "live_ui_canary_store_status_bucket_count": len(live_ui_store_summary_rows),
        "synthetic_reply_count": len(reply_rows),
        "google_board_update_plan_count": len(update_plan_rows),
        "template_hash": request_template_hash(template),
        "template_text_not_exported": True,
        "customer_send_allowed": False,
        "db_write_allowed": False,
        "google_board_write_allowed": False,
        "raw_order_ids_exported": False,
        "raw_reply_text_exported": False,
        "live_ui_canary_requires_matching_merchant_account": True,
    }
    _write_json(output_dir / "manifest.json", manifest)

    closeout = "\n".join(
        [
            "# Kaspi Customer Size Request No-Send Plan",
            "",
            "Gate: GREEN_NO_SEND_PLAN_GENERATED",
            "",
            f"- Output folder: {output_dir}",
            f"- Target date: {target_date.isoformat()}",
            f"- Candidate count: {len(candidate_rows)}",
            f"- Request ledger rows planned: {len(ledger_rows)}",
            f"- Live UI canary target rows: {len(live_ui_target_rows)}",
            f"- Live UI store/status buckets: {len(live_ui_store_summary_rows)}",
            f"- Synthetic replies parsed: {len(reply_rows)}",
            f"- Google Board dry-run update rows: {len(update_plan_rows)}",
            f"- DB unchanged: {db_sha_before == db_sha_after}",
            "",
            "No customer messages were sent. No Kaspi, Google Board, DB, Telegram,",
            "WhatsApp, workbook, scheduler, or external writes were performed.",
            "",
        ]
    )
    (output_dir / "closeout.md").write_text(closeout, encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
