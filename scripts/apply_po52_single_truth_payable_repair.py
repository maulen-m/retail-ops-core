#!/usr/bin/env python3
"""Exact-row PO-5.2 payable repair for single-truth parity.

This is narrower than the full PO workbook sync. It may update only
po_part.to_pay_base_kzt for PO-5.2, and only when the anchored workbook and DB
prove the known one-row mismatch.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_single_truth_system import (  # noqa: E402
    DEFAULT_DASHBOARD,
    DEFAULT_DB,
    resolve_po_part_scope_contract,
    resolve_workbook_path,
    validate_system,
    _load_workbook_parts,
)

ENV_GATE = "ENABLE_PO52_SINGLE_TRUTH_REPAIR_WRITE"
PO_PART_ID = "PO-5.2"
EXPECTED_DB_TO_PAY_BASE_KZT = 3_342_312.0
TARGET_TO_PAY_BASE_KZT = 2_118_312.0
TOL_KZT = 0.01
EXPECTED_SINGLE_TRUTH_ERROR = (
    f"{PO_PART_ID}: To_pay_BASE_KZT workbook={TARGET_TO_PAY_BASE_KZT} "
    f"db={EXPECTED_DB_TO_PAY_BASE_KZT}"
)


class PO52RepairError(RuntimeError):
    """Raised when the PO-5.2 repair cannot proceed safely."""


@dataclass(frozen=True)
class PO52Row:
    po_part_id: str
    po_id: str
    status: str
    is_paid_base: int
    to_pay_base_kzt: float
    to_pay_dlv_kzt: float
    updated_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "po_part_id": self.po_part_id,
            "po_id": self.po_id,
            "status": self.status,
            "is_paid_base": self.is_paid_base,
            "to_pay_base_kzt": self.to_pay_base_kzt,
            "to_pay_dlv_kzt": self.to_pay_dlv_kzt,
            "updated_at": self.updated_at,
        }


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _connect_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def _sqlite_integrity_check(path: Path) -> str:
    conn = _connect_readonly(path)
    try:
        row = conn.execute("PRAGMA integrity_check;").fetchone()
    finally:
        conn.close()
    return str(row[0] if row else "")


def _sqlite_backup(src_path: Path, dst_path: Path) -> Path:
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    src = _connect_readonly(src_path)
    dst = sqlite3.connect(str(dst_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    integrity = _sqlite_integrity_check(dst_path)
    if integrity.lower() != "ok":
        raise PO52RepairError(f"backup integrity_check failed for {dst_path}: {integrity}")
    return dst_path


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "po_part_id",
        "po_id",
        "status",
        "is_paid_base",
        "to_pay_base_kzt",
        "to_pay_dlv_kzt",
        "updated_at",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _load_po52_row(db_path: Path) -> PO52Row:
    conn = _connect_readonly(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT
                po_part_id,
                po_id,
                COALESCE(status, '') AS status,
                COALESCE(is_paid_base, 0) AS is_paid_base,
                COALESCE(to_pay_base_kzt, 0) AS to_pay_base_kzt,
                COALESCE(to_pay_dlv_kzt, 0) AS to_pay_dlv_kzt,
                COALESCE(updated_at, '') AS updated_at
            FROM po_part
            WHERE po_part_id = ?
            """,
            (PO_PART_ID,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise PO52RepairError(f"{PO_PART_ID} missing from po_part")
    return PO52Row(
        po_part_id=str(row["po_part_id"]),
        po_id=str(row["po_id"]),
        status=str(row["status"]),
        is_paid_base=int(row["is_paid_base"] or 0),
        to_pay_base_kzt=float(row["to_pay_base_kzt"] or 0.0),
        to_pay_dlv_kzt=float(row["to_pay_dlv_kzt"] or 0.0),
        updated_at=str(row["updated_at"] or ""),
    )


def _assert_close(label: str, observed: float, expected: float) -> None:
    if abs(float(observed) - float(expected)) > TOL_KZT:
        raise PO52RepairError(f"{label} mismatch: observed={observed} expected={expected}")


def _expected_pre_errors(errors: list[str]) -> list[str]:
    return [err for err in errors if "To_pay_BASE_KZT" in err or PO_PART_ID in err]


def _validate_preconditions(
    *,
    db_path: Path,
    workbook_path: Path,
    dashboard_path: Path,
    scope_contract_path: Path | None,
) -> dict[str, Any]:
    workbook_parts = _load_workbook_parts(workbook_path)
    workbook_row = workbook_parts.get(PO_PART_ID)
    if workbook_row is None:
        raise PO52RepairError(f"{PO_PART_ID} missing from workbook {workbook_path}")
    workbook_value = float(workbook_row["to_pay_base_kzt"])
    _assert_close("workbook PO-5.2 To_pay_BASE_KZT", workbook_value, TARGET_TO_PAY_BASE_KZT)

    before_row = _load_po52_row(db_path)
    _assert_close("db PO-5.2 current To_pay_BASE_KZT", before_row.to_pay_base_kzt, EXPECTED_DB_TO_PAY_BASE_KZT)

    errors = validate_system(
        db_path=db_path,
        workbook_path=workbook_path,
        dashboard_path=dashboard_path,
        po_part_scope_contract=scope_contract_path,
    )
    if errors != [EXPECTED_SINGLE_TRUTH_ERROR]:
        raise PO52RepairError(
            "single-truth precondition mismatch: expected only "
            f"{EXPECTED_SINGLE_TRUTH_ERROR!r}, observed={errors!r}"
        )

    return {
        "workbook_to_pay_base_kzt": workbook_value,
        "db_to_pay_base_kzt": before_row.to_pay_base_kzt,
        "single_truth_errors": errors,
        "single_truth_po52_errors": _expected_pre_errors(errors),
    }


def _apply_update(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.execute(
            """
            UPDATE po_part
            SET to_pay_base_kzt = ?
            WHERE po_part_id = ?
              AND ABS(COALESCE(to_pay_base_kzt, 0) - ?) <= ?
            """,
            (TARGET_TO_PAY_BASE_KZT, PO_PART_ID, EXPECTED_DB_TO_PAY_BASE_KZT, TOL_KZT),
        )
        changed = int(cur.rowcount or 0)
        if changed != 1:
            conn.rollback()
            raise PO52RepairError(f"expected exactly one PO-5.2 row update, observed {changed}")
        conn.commit()
        return changed
    finally:
        conn.close()


def _validate_post(
    *,
    db_path: Path,
    workbook_path: Path,
    dashboard_path: Path,
    scope_contract_path: Path | None,
) -> dict[str, Any]:
    after_row = _load_po52_row(db_path)
    _assert_close("db PO-5.2 repaired To_pay_BASE_KZT", after_row.to_pay_base_kzt, TARGET_TO_PAY_BASE_KZT)
    errors = validate_system(
        db_path=db_path,
        workbook_path=workbook_path,
        dashboard_path=dashboard_path,
        po_part_scope_contract=scope_contract_path,
    )
    if errors:
        raise PO52RepairError(f"single-truth post validation failed: {errors!r}")
    return {
        "row": after_row.as_dict(),
        "single_truth_errors": errors,
    }


def run_repair(
    *,
    db_path: Path = DEFAULT_DB,
    workbook_path: Path | None = None,
    dashboard_path: Path = DEFAULT_DASHBOARD,
    output_dir: Path,
    apply: bool = False,
    backup_dir: Path | None = None,
    expected_pre_sha256: str | None = None,
    po_part_scope_contract: Path | None = None,
) -> dict[str, Any]:
    db_path = Path(db_path)
    workbook_path = resolve_workbook_path(workbook_path)
    dashboard_path = Path(dashboard_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not db_path.exists():
        raise PO52RepairError(f"db not found: {db_path}")
    if not workbook_path.exists():
        raise PO52RepairError(f"workbook not found: {workbook_path}")
    if not dashboard_path.exists():
        raise PO52RepairError(f"dashboard not found: {dashboard_path}")
    scope_contract_path = resolve_po_part_scope_contract(po_part_scope_contract)

    if apply:
        if os.environ.get(ENV_GATE) != "1":
            raise PO52RepairError(f"{ENV_GATE}=1 is required for --apply")
        if backup_dir is None:
            raise PO52RepairError("--backup-dir is required for --apply")

    pre_sha = _sha256_file(db_path)
    if expected_pre_sha256 and expected_pre_sha256 != pre_sha:
        raise PO52RepairError(
            f"pre-SHA mismatch: expected={expected_pre_sha256} observed={pre_sha}"
        )

    preconditions = _validate_preconditions(
        db_path=db_path,
        workbook_path=workbook_path,
        dashboard_path=dashboard_path,
        scope_contract_path=scope_contract_path,
    )
    before_row = _load_po52_row(db_path)
    _write_csv(output_dir / "po52_before.csv", [before_row.as_dict()])

    gate: dict[str, Any] = {
        "env_gate": ENV_GATE,
        "apply": bool(apply),
        "pre_sha256": pre_sha,
        "backup_path": None,
        "backup_sha256": None,
    }

    if apply:
        backup_path = _sqlite_backup(
            db_path,
            Path(backup_dir) / "app_db_before_po52_single_truth_payable_repair.sqlite",
        )
        gate["backup_path"] = str(backup_path)
        gate["backup_sha256"] = _sha256_file(backup_path)
        rows_updated = _apply_update(db_path)
        post = _validate_post(
            db_path=db_path,
            workbook_path=workbook_path,
            dashboard_path=dashboard_path,
            scope_contract_path=scope_contract_path,
        )
        after_row = _load_po52_row(db_path)
        status = "APPLIED"
    else:
        simulation_db = _sqlite_backup(db_path, output_dir / "simulation.db")
        rows_updated = _apply_update(simulation_db)
        post = _validate_post(
            db_path=simulation_db,
            workbook_path=workbook_path,
            dashboard_path=dashboard_path,
            scope_contract_path=scope_contract_path,
        )
        after_row = _load_po52_row(simulation_db)
        status = "DRY_RUN"
        gate["simulation_db"] = str(simulation_db)

    _write_csv(output_dir / "po52_after.csv", [after_row.as_dict()])
    post_sha = _sha256_file(db_path)
    report = {
        "status": status,
        "po_part_id": PO_PART_ID,
        "target_table": "po_part",
        "target_column": "to_pay_base_kzt",
        "target_value": TARGET_TO_PAY_BASE_KZT,
        "expected_previous_value": EXPECTED_DB_TO_PAY_BASE_KZT,
        "rows_updated": rows_updated,
        "inputs": {
            "db_path": str(db_path),
            "workbook_path": str(workbook_path),
            "dashboard_path": str(dashboard_path),
            "po_part_scope_contract": str(scope_contract_path) if scope_contract_path else None,
        },
        "gate": gate,
        "preconditions": preconditions,
        "before_row": before_row.as_dict(),
        "after_row": after_row.as_dict(),
        "post": post,
        "post_sha256": post_sha,
        "db_sha256_changed": pre_sha != post_sha,
        "rollback": {
            "restore_from_backup": (
                f"sqlite3 {db_path} \".restore {gate['backup_path']}\""
                if gate.get("backup_path")
                else None
            )
        },
    }
    _write_json(output_dir / "report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply exact-row PO-5.2 payable repair")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--workbook", type=Path, default=None)
    parser.add_argument("--dashboard", type=Path, default=DEFAULT_DASHBOARD)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument("--po-part-scope-contract", type=Path, default=None)
    parser.add_argument("--expected-pre-sha256", default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    try:
        report = run_repair(
            db_path=args.db,
            workbook_path=args.workbook,
            dashboard_path=args.dashboard,
            output_dir=args.output_dir,
            backup_dir=args.backup_dir,
            expected_pre_sha256=args.expected_pre_sha256,
            po_part_scope_contract=args.po_part_scope_contract,
            apply=args.apply,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
