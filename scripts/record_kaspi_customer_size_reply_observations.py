#!/usr/bin/env python3
"""Record redacted Kaspi customer size reply observations into the local ledger.

The input CSV may contain raw reply text, but this script does not copy that CSV
or emit raw reply text. It writes only parsed facts, hashes, and no-write update
plans for Google Board / DB follow-up gates.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from core.ops.customer_size_request import (
    build_update_plan_from_ledger_snapshot,
    export_customer_size_ledger_snapshot,
    record_customer_reply_observations,
    sha256_file,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER_DB = (
    REPO_ROOT
    / "runtime"
    / "customer_size_request_ledger"
    / "no_send_customer_size_request_ledger.sqlite"
)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _read_reply_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _default_output_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "exports" / "validation" / f"kaspi_customer_size_reply_observations_{stamp}"


def _safe_sha(path: Path) -> str | None:
    return sha256_file(path) if path.exists() else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger-db", type=Path, default=DEFAULT_LEDGER_DB)
    parser.add_argument(
        "--reply-csv",
        type=Path,
        required=True,
        help="Transient CSV with order_ref or db_row_id plus reply_text. The CSV is not copied to evidence.",
    )
    parser.add_argument("--product-type-default", default="CL")
    parser.add_argument("--output-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = args.output_dir or _default_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = args.ledger_db.resolve()
    reply_csv_path = args.reply_csv.resolve()

    ledger_sha_before = _safe_sha(ledger_path)
    reply_rows = _read_reply_csv(reply_csv_path)
    stats, observations = record_customer_reply_observations(
        ledger_path,
        reply_rows,
        product_type_default=args.product_type_default,
    )
    ledger_snapshot = export_customer_size_ledger_snapshot(ledger_path)
    update_plan = build_update_plan_from_ledger_snapshot(ledger_snapshot)
    ledger_sha_after = _safe_sha(ledger_path)
    ready_rows = [row for row in observations if row.get("planned_size")]
    no_signal_rows = [
        row
        for row in observations
        if row.get("matched") is True and not row.get("planned_size")
    ]
    unmatched_rows = [row for row in observations if row.get("matched") is not True]
    gate = (
        "GREEN_CUSTOMER_SIZE_REPLY_OBSERVATIONS_CLASSIFICATION_READY_NO_EXTERNAL_WRITE"
        if ready_rows and not unmatched_rows
        else "YELLOW_CUSTOMER_SIZE_REPLY_OBSERVATIONS_REVIEW_NEEDED_NO_EXTERNAL_WRITE"
    )

    _write_json(output_dir / "reply_observations_redacted.json", observations)
    _write_csv(output_dir / "reply_observations_redacted.csv", observations)
    _write_json(output_dir / "ledger_snapshot_redacted.json", ledger_snapshot)
    _write_json(output_dir / "reply_size_update_plan_dry_run.json", update_plan)
    _write_csv(output_dir / "reply_size_update_plan_dry_run.csv", update_plan)

    manifest = {
        "gate": gate,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "ledger_db_path": str(ledger_path),
        "ledger_db_sha256_before": ledger_sha_before,
        "ledger_db_sha256_after": ledger_sha_after,
        "ledger_mutation_scope": "local_runtime_control_plane_only",
        "reply_csv_path_not_copied_to_evidence": True,
        "input_reply_rows": len(reply_rows),
        "observation_stats": stats,
        "classification_ready_rows": len(ready_rows),
        "no_size_signal_rows": len(no_signal_rows),
        "unmatched_rows": len(unmatched_rows),
        "reply_size_update_plan_count": len(update_plan),
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "google_board_write_allowed": False,
        "db_write_allowed": False,
        "telegram_send_allowed": False,
        "raw_order_id_exported": False,
        "raw_reply_text_exported": False,
    }
    _write_json(output_dir / "manifest.json", manifest)
    closeout = "\n".join(
        [
            "# Kaspi Customer Size Reply Observations",
            "",
            f"Gate: {gate}",
            "",
            f"- Output folder: {output_dir}",
            f"- Local ledger DB: {ledger_path}",
            f"- Input reply rows: {len(reply_rows)}",
            f"- Observation stats: {json.dumps(stats, sort_keys=True)}",
            f"- Classification-ready rows: {len(ready_rows)}",
            f"- No-size-signal rows: {len(no_signal_rows)}",
            f"- Unmatched rows: {len(unmatched_rows)}",
            f"- Reply update dry-run rows: {len(update_plan)}",
            "",
            "The input CSV may contain raw reply text, but it was not copied into",
            "the evidence packet. The ledger stores only parsed facts and reply hashes.",
            "",
            "No customer messages, Kaspi UI/API writes, Google Board writes,",
            "production DB writes, Telegram/WhatsApp sends, workbook writes,",
            "scheduler changes, or external writes were performed.",
            "",
        ]
    )
    (output_dir / "closeout.md").write_text(closeout, encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
