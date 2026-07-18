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
DEFAULT_PAYMENT_OVERRIDE = (
    PROJECT_ROOT
    / "config"
    / "owner_decisions"
    / "july_payment_commitments_2026_07_17.json"
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


def _load_payment_override_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "cashflow_commitment_owner_override.v1":
        raise OpexOwnerApplyError(f"unsupported payment override schema: {payload.get('schema_version')}")
    for key in ("decision_id", "run_id", "source_file", "window_start", "window_end"):
        if not str(payload.get(key) or "").strip():
            raise OpexOwnerApplyError(f"payment override missing {key}")

    source_path = PROJECT_ROOT / str(payload["source_file"])
    if not source_path.exists():
        raise OpexOwnerApplyError(f"payment override source file not found: {source_path}")

    obligations = payload.get("obligations")
    if not isinstance(obligations, list) or not obligations:
        raise OpexOwnerApplyError("payment override obligations must be a non-empty list")
    expected_count = int(payload.get("expected_obligation_count") or 0)
    if len(obligations) != expected_count:
        raise OpexOwnerApplyError(
            f"payment override count mismatch: expected {expected_count}, observed {len(obligations)}"
        )
    expected_total = float(payload.get("expected_total_kzt") or 0.0)
    observed_total = sum(float(item.get("amount_kzt") or 0.0) for item in obligations)
    if observed_total != expected_total:
        raise OpexOwnerApplyError(
            f"payment override total mismatch: expected {expected_total}, observed {observed_total}"
        )
    return payload


def _apply_payment_override_manifest(
    rows: list[dict[str, Any]],
    manifest_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    manifest = _load_payment_override_manifest(manifest_path)
    window_start = date.fromisoformat(str(manifest["window_start"]))
    window_end = date.fromisoformat(str(manifest["window_end"]))
    if window_end < window_start:
        raise OpexOwnerApplyError("payment override window_end precedes window_start")

    matched_indexes: set[int] = set()
    removed_rows: list[dict[str, Any]] = []
    inserted_rows: list[dict[str, Any]] = []
    new_ref_ids: set[str] = set()

    for obligation in manifest["obligations"]:
        for key in (
            "obligation_id",
            "display_name",
            "category",
            "commit_date",
            "amount_kzt",
            "commit_type",
            "scenario_tag",
            "ref_id",
            "supersedes",
        ):
            if obligation.get(key) in (None, "", []):
                raise OpexOwnerApplyError(
                    f"payment override obligation {obligation.get('obligation_id')} missing {key}"
                )

        commit_date = date.fromisoformat(str(obligation["commit_date"]))
        if not window_start <= commit_date <= window_end:
            raise OpexOwnerApplyError(
                f"payment override date outside governed window: {obligation['commit_date']}"
            )
        amount_kzt = float(obligation["amount_kzt"])
        if amount_kzt <= 0:
            raise OpexOwnerApplyError("payment override amount_kzt must be positive")
        if obligation["commit_type"] != "OPEX":
            raise OpexOwnerApplyError("payment override commit_type must be OPEX")

        minimum_withdrawal = obligation.get("minimum_bank_withdrawal_date")
        if obligation["category"] == "loan_payment":
            if not minimum_withdrawal:
                raise OpexOwnerApplyError(
                    f"loan payment {obligation['obligation_id']} missing minimum_bank_withdrawal_date"
                )
            withdrawal_date = date.fromisoformat(str(minimum_withdrawal))
            if (withdrawal_date - commit_date).days < 1:
                raise OpexOwnerApplyError(
                    f"loan payment {obligation['obligation_id']} violates owner pay-date convention"
                )

        ref_id = str(obligation["ref_id"])
        if ref_id in new_ref_ids or any(str(row.get("ref_id") or "") == ref_id for row in rows):
            raise OpexOwnerApplyError(f"payment override ref_id is not unique: {ref_id}")
        new_ref_ids.add(ref_id)

        superseded_labels: list[str] = []
        for selector in obligation["supersedes"]:
            selector_date = str(selector.get("commit_date") or "")
            selector_ref = str(selector.get("ref_id") or "")
            selector_amount = float(selector.get("amount_kzt") or 0.0)
            matches = [
                index
                for index, row in enumerate(rows)
                if index not in matched_indexes
                and row.get("commit_date") == selector_date
                and str(row.get("ref_id") or "") == selector_ref
                and float(row.get("amount_kzt") or 0.0) == selector_amount
            ]
            if len(matches) != 1:
                raise OpexOwnerApplyError(
                    "payment override preimage mismatch for "
                    f"{selector_ref}@{selector_date}:{selector_amount:g}; matches={len(matches)}"
                )
            match_index = matches[0]
            matched_indexes.add(match_index)
            removed_rows.append(dict(rows[match_index]))
            superseded_labels.append(f"{selector_ref}@{selector_date}:{selector_amount:g}")

        notes_parts = [
            f"{obligation['category']}: {obligation['display_name']}",
            "source=owner_stated_pay_date",
            f"planned_outflow_date={obligation['commit_date']}",
            "tags=owner_stated_pay_date",
            f"run_id={manifest['run_id']}",
            f"owner_decision={manifest['decision_id']}",
            f"supersedes={','.join(superseded_labels)}",
        ]
        if minimum_withdrawal:
            notes_parts.append(f"minimum_bank_withdrawal_date={minimum_withdrawal}")
            notes_parts.append("owner_pay_date_convention=at_least_1_day_before_bank_withdrawal")
        else:
            notes_parts.append("owner_pay_date_convention=planned_outflow_date")

        inserted_rows.append(
            {
                "commit_date": obligation["commit_date"],
                "commit_type": obligation["commit_type"],
                "amount_kzt": amount_kzt,
                "scenario_tag": obligation["scenario_tag"],
                "ref_id": ref_id,
                "notes": "; ".join(notes_parts),
            }
        )

    output_rows = [row for index, row in enumerate(rows) if index not in matched_indexes]
    output_rows.extend(inserted_rows)
    output_rows.sort(
        key=lambda row: (
            str(row.get("commit_date") or ""),
            str(row.get("ref_id") or ""),
            float(row.get("amount_kzt") or 0.0),
        )
    )
    report = {
        "path": str(manifest_path),
        "sha256": _sha256_file(manifest_path),
        "decision_id": manifest["decision_id"],
        "run_id": manifest["run_id"],
        "owner_pay_date_convention": manifest["owner_pay_date_convention"],
        "obligation_count": len(inserted_rows),
        "obligation_total_kzt": sum(float(row["amount_kzt"]) for row in inserted_rows),
        "removed_count": len(removed_rows),
        "removed_rows": removed_rows,
        "inserted_rows": inserted_rows,
    }
    return output_rows, report


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


def _build_owner_approved_commitments_with_report(
    *,
    workbook_path: Path,
    as_of: date,
    horizon_days: int,
    variant: str = DEFAULT_VARIANT,
    payment_override_path: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    normalized = normalize_workbook(workbook_path, as_of=as_of, horizon_days=horizon_days)
    normalized = _apply_owner_stage_b_overrides(normalized)
    rows = build_variant_commitments(
        normalized,
        variant,
        as_of=as_of,
        horizon_days=horizon_days,
        scenario_tag="base",
    )
    payment_override_report: dict[str, Any] = {}
    if payment_override_path is not None:
        rows, payment_override_report = _apply_payment_override_manifest(rows, payment_override_path)
    return rows, payment_override_report


def build_owner_approved_commitments(
    *,
    workbook_path: Path,
    as_of: date,
    horizon_days: int,
    variant: str = DEFAULT_VARIANT,
    payment_override_path: Path | None = None,
) -> list[dict[str, Any]]:
    rows, _ = _build_owner_approved_commitments_with_report(
        workbook_path=workbook_path,
        as_of=as_of,
        horizon_days=horizon_days,
        variant=variant,
        payment_override_path=payment_override_path,
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
    payment_override_report: dict[str, Any],
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
    if payment_override_report:
        payload["payment_override"] = {
            "path": payment_override_report["path"],
            "sha256": payment_override_report["sha256"],
            "decision_id": payment_override_report["decision_id"],
            "run_id": payment_override_report["run_id"],
            "obligation_count": payment_override_report["obligation_count"],
            "obligation_total_kzt": payment_override_report["obligation_total_kzt"],
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
    payment_override_report: dict[str, Any],
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
        payment_override_report=payment_override_report,
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
    payment_override_path: Path | None = None,
    expected_pre_sha256: str | None = None,
    backup_dir: Path | None = None,
) -> dict[str, Any]:
    if not workbook_path.exists():
        raise FileNotFoundError(f"workbook not found: {workbook_path}")
    if not db_path.exists():
        raise FileNotFoundError(f"db not found: {db_path}")
    if not owner_decision_path.exists():
        raise FileNotFoundError(f"owner decision not found: {owner_decision_path}")
    if payment_override_path is not None and not payment_override_path.exists():
        raise FileNotFoundError(f"payment override not found: {payment_override_path}")

    rows, payment_override_report = _build_owner_approved_commitments_with_report(
        workbook_path=workbook_path,
        as_of=as_of,
        horizon_days=horizon_days,
        variant=variant,
        payment_override_path=payment_override_path,
    )
    csv_path, yaml_path = _write_outputs(
        output_dir=output_dir,
        rows=rows,
        workbook_path=workbook_path,
        owner_decision_path=owner_decision_path,
        as_of=as_of,
        horizon_days=horizon_days,
        variant=variant,
        payment_override_report=payment_override_report,
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
        "payment_override": payment_override_report,
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
    parser.add_argument("--payment-override", type=Path, default=DEFAULT_PAYMENT_OVERRIDE)
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
            payment_override_path=args.payment_override.expanduser() if args.payment_override else None,
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
    if report["payment_override"]:
        print(f"payment_override_run_id={report['payment_override']['run_id']}")
        print(f"payment_override_total_kzt={report['payment_override']['obligation_total_kzt']}")
    print("APPLY" if args.apply else "DRY RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
