#!/usr/bin/env python3
"""Validate dashboard PLAN vs REAL PO labeling contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sqlite3
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_DASHBOARD = PROJECT_ROOT / "exports" / "po_dashboard_data.json"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _is_valid_part_id(raw: Any) -> bool:
    txt = str(raw or "").strip().upper()
    if not txt:
        return False
    return bool(re.match(r"^(PO[-_].+|ARC[-_].+|.+_PO-\d+)$", txt))


def _is_legacy_archive_key(value: str) -> bool:
    return bool(re.match(r"^.+_PO-\d+$", str(value or "").strip().upper()))


def _load_real_ids(db_path: Path) -> set[str]:
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if _table_exists(conn, "po_part"):
            rows = conn.execute(
                """
                SELECT po_part_id
                FROM po_part
                WHERE COALESCE(TRIM(po_part_id), '') <> ''
                """
            ).fetchall()
            ids = {str(row["po_part_id"]).strip() for row in rows if _is_valid_part_id(row["po_part_id"])}
            if ids:
                return ids
        if _table_exists(conn, "po_header"):
            rows = conn.execute(
                """
                SELECT po_id
                FROM po_header
                WHERE po_id LIKE 'PO-%'
                """
            ).fetchall()
            return {str(row["po_id"]).strip() for row in rows if str(row["po_id"] or "").strip()}
    return set()


def validate_dashboard_plan_real_contract(*, db_path: Path, dashboard_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    if not db_path.exists():
        errors.append(f"db not found: {db_path}")
        return {"ok": False, "errors": errors}
    if not dashboard_path.exists():
        errors.append(f"dashboard not found: {dashboard_path}")
        return {"ok": False, "errors": errors}

    payload = json.loads(dashboard_path.read_text(encoding="utf-8"))
    pos = payload.get("pos") or {}
    if not isinstance(pos, dict):
        errors.append("dashboard pos must be an object")
        return {"ok": False, "errors": errors}

    archived_pos = set(str(v) for v in (payload.get("archived_pos") or []))
    real_pos_rows = payload.get("real_pos") or []
    if not isinstance(real_pos_rows, list):
        errors.append("dashboard real_pos must be a list")
        return {"ok": False, "errors": errors}

    real_ids = _load_real_ids(db_path)
    dashboard_real_ids: set[str] = set()
    for idx, row in enumerate(real_pos_rows):
        if not isinstance(row, dict):
            errors.append(f"real_pos[{idx}] must be an object")
            continue
        po_id = str(row.get("po_id") or "").strip()
        if not po_id:
            errors.append(f"real_pos[{idx}] missing po_id")
            continue
        dashboard_real_ids.add(po_id)
        if po_id.startswith("PLAN-"):
            errors.append(f"{po_id}: PLAN id must not appear in real_pos")
        if real_ids and po_id not in real_ids:
            errors.append(f"{po_id}: real_pos id missing from materialized PO ids")

    for po_key, po_payload in pos.items():
        if not isinstance(po_payload, dict):
            errors.append(f"pos[{po_key}] must be an object")
            continue
        po_kind = str(po_payload.get("po_kind") or "").strip()
        if po_key.startswith("PLAN-"):
            if po_kind != "PLAN":
                errors.append(f"{po_key}: expected po_kind=PLAN, got {po_kind or 'EMPTY'}")
        else:
            if po_kind != "REAL_ARCHIVE":
                errors.append(f"{po_key}: expected po_kind=REAL_ARCHIVE, got {po_kind or 'EMPTY'}")
            if po_key not in archived_pos:
                errors.append(f"{po_key}: missing from archived_pos")
            if real_ids and po_key not in real_ids and not _is_legacy_archive_key(po_key):
                errors.append(f"{po_key}: non-PLAN key missing from materialized PO ids")

    result = {
        "ok": len(errors) == 0,
        "errors": errors,
        "real_ids_count": len(real_ids),
        "dashboard_real_ids_count": len(dashboard_real_ids),
    }
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate dashboard PLAN vs REAL PO contract")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--dashboard", type=Path, default=DEFAULT_DASHBOARD)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = validate_dashboard_plan_real_contract(db_path=args.db, dashboard_path=args.dashboard)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("dashboard_plan_real: OK" if report["ok"] else "dashboard_plan_real: FAIL")
        for err in report["errors"]:
            print(f"- {err}")
    if args.strict and not report["ok"]:
        return 1
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
