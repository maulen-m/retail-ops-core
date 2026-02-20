#!/usr/bin/env python3
"""
Sync canonical OPEX schedule artifacts from protocol XLSX and optionally apply to DB.

Default: DRY RUN for DB writes.
APPLY requires ENABLE_CASHFLOW_WRITE=1 and --apply.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.import_opex_protocol import _parse_protocol_xlsx

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_XLSX = Path(
    "~/Documents/useful tables/Main crm spreadsheets/main tables/Protocols/"
    "OPEX_protocol_26.01.2026.xlsx"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "config" / "opex"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        is not None
    )


def _normalize_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in entries:
        normalized.append(
            {
                "commit_date": str(row.get("commit_date") or ""),
                "commit_type": str(row.get("commit_type") or "OPEX"),
                "amount_kzt": round(float(row.get("amount_kzt") or 0.0), 2),
                "scenario_tag": str(row.get("scenario_tag") or "base"),
                "ref_id": str(row.get("ref_id") or "OPEX_PROTOCOL"),
                "notes": str(row.get("notes") or "OPEX protocol import"),
            }
        )
    normalized.sort(
        key=lambda r: (
            r["commit_date"],
            r["commit_type"],
            r["scenario_tag"],
            r["ref_id"],
            r["amount_kzt"],
        )
    )
    return normalized


def _write_commitments_csv(entries: list[dict[str, Any]], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "commit_date",
                "commit_type",
                "amount_kzt",
                "scenario_tag",
                "ref_id",
                "notes",
            ],
        )
        writer.writeheader()
        for row in entries:
            writer.writerow(row)


def _write_schedule_yaml(
    *,
    xlsx_path: Path,
    entries: list[dict[str, Any]],
    horizon_days: int,
    yaml_path: Path,
) -> None:
    payload = {
        "source_xlsx": str(xlsx_path),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "horizon_days": int(horizon_days),
        "rows_generated": len(entries),
        "columns": [
            "commit_date",
            "commit_type",
            "amount_kzt",
            "scenario_tag",
            "ref_id",
            "notes",
        ],
    }
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def sync_opex_schedule(
    *,
    xlsx_path: Path,
    db_path: Path,
    output_dir: Path,
    apply: bool,
    replace_existing: bool,
    horizon_days: int,
) -> dict[str, Any]:
    if not xlsx_path.exists():
        raise FileNotFoundError(f"xlsx not found: {xlsx_path}")
    if not db_path.exists():
        raise FileNotFoundError(f"db not found: {db_path}")

    parsed = _parse_protocol_xlsx(xlsx_path, horizon_days)
    entries = _normalize_entries(parsed)
    csv_path = output_dir / "opex_commitments.csv"
    yaml_path = output_dir / "opex_schedule.yaml"
    _write_commitments_csv(entries, csv_path)
    _write_schedule_yaml(
        xlsx_path=xlsx_path,
        entries=entries,
        horizon_days=horizon_days,
        yaml_path=yaml_path,
    )

    inserted = 0
    skipped_existing = 0
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if not _table_exists(conn, "fact_cashflow_commitments"):
            raise RuntimeError("fact_cashflow_commitments missing; run migrate_018_cashflow_calendar.py")

        if apply and os.environ.get("ENABLE_CASHFLOW_WRITE") != "1":
            raise RuntimeError("ENABLE_CASHFLOW_WRITE=1 is required to apply cashflow writes.")

        if apply and replace_existing:
            conn.execute("DELETE FROM fact_cashflow_commitments WHERE commit_type='OPEX'")
            conn.commit()

        existing = {
            (row[0], row[1], float(row[2]), row[3], row[4])
            for row in conn.execute(
                """
                SELECT commit_date, commit_type, amount_kzt, scenario_tag, ref_id
                FROM fact_cashflow_commitments
                """
            ).fetchall()
        }

        new_rows = [
            row
            for row in entries
            if (
                row["commit_date"],
                row["commit_type"],
                float(row["amount_kzt"]),
                row["scenario_tag"],
                row["ref_id"],
            )
            not in existing
        ]
        skipped_existing = len(entries) - len(new_rows)

        if apply:
            for row in new_rows:
                conn.execute(
                    """
                    INSERT INTO fact_cashflow_commitments (
                        commit_date, commit_type, amount_kzt, probability, scenario_tag, ref_id, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["commit_date"],
                        row["commit_type"],
                        row["amount_kzt"],
                        None,
                        row["scenario_tag"],
                        row["ref_id"],
                        row["notes"],
                    ),
                )
            conn.commit()
            inserted = len(new_rows)

    return {
        "rows_generated": len(entries),
        "db_rows_inserted": inserted,
        "db_existing_skipped": skipped_existing,
        "csv_path": str(csv_path),
        "yaml_path": str(yaml_path),
        "apply": bool(apply),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync OPEX schedule from protocol XLSX")
    parser.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--horizon-days", type=int, default=365)
    parser.add_argument("--replace-existing", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    result = sync_opex_schedule(
        xlsx_path=args.xlsx,
        db_path=args.db,
        output_dir=args.output_dir,
        apply=args.apply,
        replace_existing=args.replace_existing,
        horizon_days=args.horizon_days,
    )
    print(f"rows_generated={result['rows_generated']}")
    print(f"db_rows_inserted={result['db_rows_inserted']}")
    print(f"db_existing_skipped={result['db_existing_skipped']}")
    print(f"csv_path={result['csv_path']}")
    print(f"yaml_path={result['yaml_path']}")
    print("APPLY" if args.apply else "DRY RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
