#!/usr/bin/env python3
"""Apply owner-approved Stage-B OPEX commitments.

Default: DRY RUN for DB writes. Apply requires ENABLE_CASHFLOW_WRITE=1
and --apply. Production DB apply also requires an expected pre-SHA and backup
directory.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.cashflow.opex_owner_input import (  # noqa: E402
    COMMITMENT_COLUMNS,
    DEFAULT_HORIZON_DAYS,
    NormalizedOpexLine,
    build_variant_commitments,
    normalize_workbook,
    write_commitments_csv,
)
from scripts.backup_db import backup_database  # noqa: E402


DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_WORKBOOK = (
    PROJECT_ROOT
    / "exports"
    / "opex_owner_input"
    / "2026-07-02"
    / "OPEX_and_Loans_OWNER_INPUT_MINIMAL_20260702.xlsx"
)
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "config" / "opex"
DEFAULT_OWNER_DECISION = (
    PROJECT_ROOT
    / "config"
    / "owner_decisions"
    / "opex_loans_floor_refresh_2026_07_02.json"
)
DEFAULT_AS_OF = date(2026, 7, 2)
DEFAULT_VARIANT = "V2_owner80k"
REPLACE_BOUNDARY = date(2026, 7, 2)
PROD_WRITE_ENV_GATE = "ENABLE_CASHFLOW_WRITE"


class OpexOwnerApplyError(RuntimeError):
    """Raised when Stage-B owner OPEX apply cannot proceed safely."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_integrity_check(path: Path) -> str:
    with sqlite3.connect(str(path)) as conn:
        row = conn.execute("PRAGMA integrity_check").fetchone()
    return str(row[0]) if row else "missing"


def _is_production_db(db_path: Path) -> bool:
    return db_path.resolve() == DEFAULT_DB.resolve()


def _sidecar_paths(db_path: Path) -> list[Path]:
    return [db_path.with_name(db_path.name + suffix) for suffix in ("-wal", "-shm", "-journal")]


def _fail_on_sqlite_sidecars(db_path: Path) -> None:
    existing = [path for path in _sidecar_paths(db_path) if path.exists()]
    if existing:
        joined = ", ".join(str(path) for path in existing)
        raise OpexOwnerApplyError(f"refusing apply while SQLite sidecars exist: {joined}")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _append_flags(line: NormalizedOpexLine, *flags: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys([*line.flags, *[flag for flag in flags if flag]]))


def _without_flags(line: NormalizedOpexLine, *flags: str) -> tuple[str, ...]:
    remove = set(flags)
    return tuple(flag for flag in line.flags if flag not in remove)


def _apply_owner_stage_b_overrides(normalized: dict[str, Any]) -> dict[str, Any]:
    updated: list[NormalizedOpexLine] = []
    for line in normalized["opex_lines"]:
        if line.name == "Gym_memberships":
            updated.append(
                replace(
                    line,
                    owner_monthly_kzt=30000.0,
                    monthly_amount_kzt=30000.0,
                    amount_authority="owner_decision_source_monthly_kzt",
                    flags=(
                        *_without_flags(line, "OWNER_SOURCE_DELTA"),
                        "OWNER_APPROVED_SOURCE_VALUE_30000",
                    ),
                    owner_action_required=False,
                )
            )
            continue
        if line.name == "GOLD_Acmewear":
            updated.append(
                replace(
                    line,
                    owner_monthly_kzt=126693.0,
                    monthly_amount_kzt=126693.0,
                    amount_authority="owner_decision_interim_monthly_kzt",
                    flags=_append_flags(
                        line,
                        "OWNER_APPROVED_INTERIM_126693",
                        "OWNER_INTERIM_REVISIT_20260703",
                    ),
                    owner_action_required=False,
                )
            )
            continue
        if line.name == "GOLD_store-d":
            updated.append(
                replace(
                    line,
                    flags=_append_flags(line, "OWNER_APPROVED_VARIANT_V2_80000"),
                    owner_action_required=False,
                )
            )
            continue
        updated.append(line)

    patched = dict(normalized)
    patched["opex_lines"] = updated
    patched["stage_b_owner_overrides"] = {
        "variant": DEFAULT_VARIANT,
        "Gym_memberships": 30000.0,
        "GOLD_Acmewear": 126693.0,
        "GOLD_store-d": 80000.0,
        "provenance_flag": "OWNER_INTERIM_REVISIT_20260703",
    }
    return patched


def build_owner_approved_commitments(
    *,
    workbook_path: Path,
    as_of: date,
    horizon_days: int,
    variant: str = DEFAULT_VARIANT,
) -> list[dict[str, Any]]:
    normalized = normalize_workbook(workbook_path, as_of=as_of, horizon_days=horizon_days)
    normalized = _apply_owner_stage_b_overrides(normalized)
    rows = build_variant_commitments(
        normalized,
        variant,
        as_of=as_of,
        horizon_days=horizon_days,
        scenario_tag="base",
    )
    return rows


def _write_schedule_yaml(
    *,
    path: Path,
    workbook_path: Path,
    owner_decision_path: Path,
    as_of: date,
    horizon_days: int,
    rows: list[dict[str, Any]],
    variant: str,
) -> None:
    payload = {
        "source_xlsx": str(workbook_path),
        "owner_decision": str(owner_decision_path),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_of": as_of.isoformat(),
        "variant": variant,
        "horizon_days": int(horizon_days),
        "rows_generated": len(rows),
        "replace_boundary": {
            "commit_type": "OPEX",
            "commit_date_gte": REPLACE_BOUNDARY.isoformat(),
            "history_preserved_before": REPLACE_BOUNDARY.isoformat(),
        },
        "columns": COMMITMENT_COLUMNS,
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_outputs(
    *,
    output_dir: Path,
    rows: list[dict[str, Any]],
    workbook_path: Path,
    owner_decision_path: Path,
    as_of: date,
    horizon_days: int,
    variant: str,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "opex_commitments.csv"
    yaml_path = output_dir / "opex_schedule.yaml"
    write_commitments_csv(csv_path, rows)
    _write_schedule_yaml(
        path=yaml_path,
        workbook_path=workbook_path,
        owner_decision_path=owner_decision_path,
        as_of=as_of,
        horizon_days=horizon_days,
        rows=rows,
        variant=variant,
    )
    return csv_path, yaml_path


def _prepare_apply_guard(
    *,
    db_path: Path,
    expected_pre_sha256: str | None,
    backup_dir: Path | None,
) -> dict[str, Any]:
    if os.environ.get(PROD_WRITE_ENV_GATE) != "1":
        raise OpexOwnerApplyError(f"{PROD_WRITE_ENV_GATE}=1 is required to apply cashflow writes.")

    pre_sha = _sha256_file(db_path)
    metadata: dict[str, Any] = {
        "production_apply": _is_production_db(db_path),
        "pre_sha256": pre_sha,
    }
    if expected_pre_sha256 and pre_sha != expected_pre_sha256:
        raise OpexOwnerApplyError(
            f"DB SHA mismatch before OPEX apply: expected {expected_pre_sha256}, observed {pre_sha}"
        )
    if not metadata["production_apply"]:
        return metadata

    if not expected_pre_sha256:
        raise OpexOwnerApplyError("--expected-pre-sha256 is required for production OPEX apply.")
    if backup_dir is None:
        raise OpexOwnerApplyError("--backup-dir is required for production OPEX apply.")

    _fail_on_sqlite_sidecars(db_path)
    pre_integrity = _sqlite_integrity_check(db_path)
    if pre_integrity.lower() != "ok":
        raise OpexOwnerApplyError(f"production DB integrity_check failed before OPEX apply: {pre_integrity}")
    backup_path = backup_database(db_path, backup_dir, compress=False)
    backup_integrity = _sqlite_integrity_check(backup_path)
    if backup_integrity.lower() != "ok":
        raise OpexOwnerApplyError(f"OPEX apply backup integrity_check failed: {backup_integrity}")

    metadata.update(
        {
            "expected_pre_sha256": expected_pre_sha256,
            "backup_path": str(backup_path),
            "backup_sha256": _sha256_file(backup_path),
            "pre_integrity_check": pre_integrity,
            "backup_integrity_check": backup_integrity,
        }
    )
    return metadata


def apply_opex_owner_input_schedule(
    *,
    workbook_path: Path,
    db_path: Path,
    output_dir: Path,
    owner_decision_path: Path,
    as_of: date,
    horizon_days: int,
    apply: bool,
    variant: str = DEFAULT_VARIANT,
    expected_pre_sha256: str | None = None,
    backup_dir: Path | None = None,
) -> dict[str, Any]:
    if not workbook_path.exists():
        raise FileNotFoundError(f"workbook not found: {workbook_path}")
    if not db_path.exists():
        raise FileNotFoundError(f"db not found: {db_path}")
    if not owner_decision_path.exists():
        raise FileNotFoundError(f"owner decision not found: {owner_decision_path}")

    rows = build_owner_approved_commitments(
        workbook_path=workbook_path,
        as_of=as_of,
        horizon_days=horizon_days,
        variant=variant,
    )
    csv_path, yaml_path = _write_outputs(
        output_dir=output_dir,
        rows=rows,
        workbook_path=workbook_path,
        owner_decision_path=owner_decision_path,
        as_of=as_of,
        horizon_days=horizon_days,
        variant=variant,
    )

    apply_metadata: dict[str, Any] = {}
    if apply:
        apply_metadata = _prepare_apply_guard(
            db_path=db_path,
            expected_pre_sha256=expected_pre_sha256,
            backup_dir=backup_dir,
        )

    with sqlite3.connect(str(db_path)) as conn:
        if not _table_exists(conn, "fact_cashflow_commitments"):
            raise OpexOwnerApplyError("fact_cashflow_commitments missing; run migrate_018_cashflow_calendar.py")
        pre_replace_rows = conn.execute(
            """
            SELECT COUNT(*)
            FROM fact_cashflow_commitments
            WHERE commit_type='OPEX'
              AND commit_date >= ?
            """,
            (REPLACE_BOUNDARY.isoformat(),),
        ).fetchone()[0]
        history_rows = conn.execute(
            """
            SELECT COUNT(*)
            FROM fact_cashflow_commitments
            WHERE commit_type='OPEX'
              AND commit_date < ?
            """,
            (REPLACE_BOUNDARY.isoformat(),),
        ).fetchone()[0]

        inserted = 0
        deleted = 0
        if apply:
            before_changes = conn.total_changes
            conn.execute(
                """
                DELETE FROM fact_cashflow_commitments
                WHERE commit_type='OPEX'
                  AND commit_date >= ?
                """,
                (REPLACE_BOUNDARY.isoformat(),),
            )
            deleted = conn.total_changes - before_changes
            for row in rows:
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
                inserted += 1
            conn.commit()

    if apply_metadata.get("production_apply"):
        post_integrity = _sqlite_integrity_check(db_path)
        if post_integrity.lower() != "ok":
            raise OpexOwnerApplyError(f"production DB integrity_check failed after OPEX apply: {post_integrity}")
        apply_metadata["post_sha256"] = _sha256_file(db_path)
        apply_metadata["post_integrity_check"] = post_integrity

    monthly_window_end = as_of.fromordinal(as_of.toordinal() + 30)
    monthly_opex = round(
        sum(
            float(row["amount_kzt"] or 0.0)
            for row in rows
            if as_of <= date.fromisoformat(row["commit_date"]) <= monthly_window_end
        ),
        2,
    )
    return {
        "apply": bool(apply),
        "variant": variant,
        "as_of": as_of.isoformat(),
        "replace_boundary": REPLACE_BOUNDARY.isoformat(),
        "rows_generated": len(rows),
        "monthly_opex_kzt": monthly_opex,
        "db_rows_would_delete": int(pre_replace_rows),
        "db_rows_deleted": int(deleted),
        "db_rows_inserted": int(inserted),
        "history_rows_preserved": int(history_rows),
        "csv_path": str(csv_path),
        "yaml_path": str(yaml_path),
        "apply_metadata": apply_metadata,
    }


def _write_report(path: Path | None, report: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply owner-approved 2026-07-02 OPEX owner input schedule")
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--owner-decision", type=Path, default=DEFAULT_OWNER_DECISION)
    parser.add_argument("--as-of", default=DEFAULT_AS_OF.isoformat())
    parser.add_argument("--horizon-days", type=int, default=DEFAULT_HORIZON_DAYS)
    parser.add_argument("--variant", default=DEFAULT_VARIANT)
    parser.add_argument("--expected-pre-sha256", default=None)
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument("--report-json", type=Path, default=None)
    parser.add_argument("--apply", action="store_true", help="Write DB changes; requires ENABLE_CASHFLOW_WRITE=1")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = apply_opex_owner_input_schedule(
            workbook_path=args.workbook.expanduser(),
            db_path=args.db.expanduser(),
            output_dir=args.output_dir.expanduser(),
            owner_decision_path=args.owner_decision.expanduser(),
            as_of=date.fromisoformat(str(args.as_of)),
            horizon_days=int(args.horizon_days),
            variant=str(args.variant),
            apply=bool(args.apply),
            expected_pre_sha256=args.expected_pre_sha256,
            backup_dir=args.backup_dir.expanduser() if args.backup_dir else None,
        )
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1

    _write_report(args.report_json, report)
    print(f"rows_generated={report['rows_generated']}")
    print(f"monthly_opex_kzt={report['monthly_opex_kzt']}")
    print(f"db_rows_would_delete={report['db_rows_would_delete']}")
    print(f"db_rows_deleted={report['db_rows_deleted']}")
    print(f"db_rows_inserted={report['db_rows_inserted']}")
    print(f"history_rows_preserved={report['history_rows_preserved']}")
    print(f"csv_path={report['csv_path']}")
    print(f"yaml_path={report['yaml_path']}")
    if report["apply_metadata"].get("backup_path"):
        print(f"backup_path={report['apply_metadata']['backup_path']}")
    print("APPLY" if args.apply else "DRY RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
