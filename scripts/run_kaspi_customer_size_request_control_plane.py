#!/usr/bin/env python3
"""Run the local no-send control plane for Kaspi customer size requests.

This runner writes only to a local SQLite ledger under runtime/ by default.
It never sends customer messages, never writes production db/app.db, and never
writes Google Board.
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
    build_request_ledger_plan,
    build_update_plan_from_ledger_snapshot,
    export_customer_size_ledger_snapshot,
    load_missing_size_candidates,
    normalize_request_template,
    record_synthetic_reply_observations,
    request_template_hash,
    sha256_file,
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
        / f"kaspi_customer_size_request_control_plane_{target_date.isoformat()}_{stamp}"
    )


def _safe_file_sha(path: Path) -> str | None:
    return sha256_file(path) if path.exists() else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Persist redacted Kaspi size-request plans to a local no-send ledger "
            "and emit dry-run reply update plans."
        )
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--ledger-db", type=Path, default=DEFAULT_LEDGER_DB)
    parser.add_argument("--target-date", help="YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--lookback-days", type=int, default=3)
    parser.add_argument("--store", action="append", default=[], help="Optional store_code filter.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--template", default=DEFAULT_REQUEST_TEMPLATE)
    parser.add_argument(
        "--synthetic-replies-csv",
        type=Path,
        help=(
            "Optional local CSV with order_ref/reply_text/product_type for dry-run "
            "classification proof. Raw reply text is not emitted."
        ),
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

    app_db_sha_before = _safe_file_sha(db_path)
    ledger_db_sha_before = _safe_file_sha(ledger_path)

    candidates = load_missing_size_candidates(
        db_path,
        target_date=target_date,
        lookback_days=args.lookback_days,
        stores=args.store,
        limit=args.limit,
    )
    candidate_rows = [candidate.to_redacted_dict() for candidate in candidates]
    request_plan_rows = build_request_ledger_plan(candidates, template=template)
    ledger_upsert_stats = upsert_request_ledger_plan(ledger_path, request_plan_rows)

    synthetic_reply_rows = _read_synthetic_replies(args.synthetic_replies_csv)
    reply_stats = {
        "input_rows": 0,
        "matched": 0,
        "unmatched": 0,
        "classification_ready": 0,
    }
    if synthetic_reply_rows:
        reply_stats = record_synthetic_reply_observations(
            ledger_path,
            synthetic_reply_rows,
        )

    ledger_snapshot_rows = export_customer_size_ledger_snapshot(ledger_path)
    update_plan_rows = build_update_plan_from_ledger_snapshot(ledger_snapshot_rows)

    app_db_sha_after = _safe_file_sha(db_path)
    ledger_db_sha_after = _safe_file_sha(ledger_path)

    _write_json(output_dir / "missing_size_candidates_redacted.json", candidate_rows)
    _write_csv(output_dir / "missing_size_candidates_redacted.csv", candidate_rows)
    _write_json(output_dir / "request_ledger_plan_no_send.json", request_plan_rows)
    _write_csv(output_dir / "request_ledger_plan_no_send.csv", request_plan_rows)
    _write_json(output_dir / "ledger_snapshot_redacted.json", ledger_snapshot_rows)
    _write_csv(output_dir / "ledger_snapshot_redacted.csv", ledger_snapshot_rows)
    _write_json(output_dir / "reply_size_update_plan_dry_run.json", update_plan_rows)
    _write_csv(output_dir / "reply_size_update_plan_dry_run.csv", update_plan_rows)

    manifest = {
        "gate": "GREEN_LOCAL_CONTROL_PLANE_NO_SEND",
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "app_db_path": str(db_path),
        "app_db_sha256_before": app_db_sha_before,
        "app_db_sha256_after": app_db_sha_after,
        "app_db_unchanged": app_db_sha_before == app_db_sha_after,
        "ledger_db_path": str(ledger_path),
        "ledger_db_exists": ledger_path.exists(),
        "ledger_db_sha256_before": ledger_db_sha_before,
        "ledger_db_sha256_after": ledger_db_sha_after,
        "ledger_mutation_scope": "local_runtime_control_plane_only",
        "target_date": target_date.isoformat(),
        "lookback_days": args.lookback_days,
        "stores": args.store,
        "candidate_count": len(candidate_rows),
        "request_plan_count": len(request_plan_rows),
        "ledger_upsert_stats": ledger_upsert_stats,
        "ledger_snapshot_count": len(ledger_snapshot_rows),
        "synthetic_reply_count": len(synthetic_reply_rows),
        "synthetic_reply_observation_stats": reply_stats,
        "reply_size_update_plan_count": len(update_plan_rows),
        "template_hash": request_template_hash(template),
        "template_text_not_exported": True,
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "db_write_allowed": False,
        "google_board_write_allowed": False,
        "raw_order_ids_exported": False,
        "raw_reply_text_exported": False,
        "synthetic_reply_source_copied_to_evidence": False,
    }
    _write_json(output_dir / "manifest.json", manifest)

    closeout = "\n".join(
        [
            "# Kaspi Customer Size Request Local Control Plane",
            "",
            "Gate: GREEN_LOCAL_CONTROL_PLANE_NO_SEND",
            "",
            f"- Output folder: {output_dir}",
            f"- Local ledger DB: {ledger_path}",
            f"- Target date: {target_date.isoformat()}",
            f"- Candidate rows: {len(candidate_rows)}",
            f"- Request plan rows: {len(request_plan_rows)}",
            f"- Ledger upsert stats: {json.dumps(ledger_upsert_stats, sort_keys=True)}",
            f"- Ledger snapshot rows: {len(ledger_snapshot_rows)}",
            f"- Synthetic replies observed: {len(synthetic_reply_rows)}",
            f"- Reply update dry-run rows: {len(update_plan_rows)}",
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
