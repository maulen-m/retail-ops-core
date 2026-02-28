#!/usr/bin/env python3
"""Fail-closed validator proving sales engine parity without reference overlays."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import shutil
import sqlite3
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.sales.ocean_drop_anchor import (  # noqa: E402
    DEFAULT_REGISTRY as DEFAULT_ANCHOR_REGISTRY,
    OceanDropAnchorError,
    resolve_ocean_drop_path,
)
from scripts.rebuild_sales_fact_v2_from_kaspi_entries import (  # noqa: E402
    _upsert,
    build_rebuild_plan,
    build_sales_fact_v2_rows_from_entries,
)
from scripts.validate_sales_truth_ocean_drop_parity import (  # noqa: E402
    validate_sales_truth_ocean_drop_parity,
)


DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "sales_engine_self_sufficient"


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Sales Engine Self-Sufficient Report",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- status: `{report['status']}`",
        f"- source_db: `{report['source_db']}`",
        f"- temp_db: `{report['temp_db']}`",
        f"- window_days: `{report['window_days']}`",
        f"- pre_wipe_rows: `{report['pre_wipe_rows']}`",
        f"- rebuilt_rows: `{report['rebuilt_rows']}`",
        f"- rows_applied: `{report['rows_applied']}`",
        f"- parity_status: `{report['parity_status']}`",
        f"- nonvolatile_mismatch_count: `{report['nonvolatile_mismatch_count']}`",
        f"- parity_report_json: `{report.get('parity_report_json')}`",
        "",
    ]
    if report.get("errors"):
        lines.extend(["## Errors", ""])
        for err in report["errors"]:
            lines.append(f"- {err}")
    return "\n".join(lines) + "\n"


def validate_sales_engine_self_sufficient(
    *,
    db_path: Path,
    as_of: date,
    ocean_drop_path: Path,
    output_root: Path,
    strict: bool,
    crm_archive_lookup_path: Path | None,
    window_days: int,
) -> dict[str, Any]:
    if not db_path.exists():
        raise RuntimeError(f"db not found: {db_path}")

    out_dir = output_root.resolve() / as_of.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    temp_db = out_dir / "self_sufficient_temp.db"
    shutil.copy2(db_path, temp_db)

    errors: list[str] = []
    pre_wipe_rows = 0
    rebuilt_rows = 0
    rows_applied = 0

    conn = sqlite3.connect(str(temp_db))
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sales_fact_v2'").fetchone()
        if row is None:
            raise RuntimeError("missing table in temp db: sales_fact_v2")

        pre_wipe_rows = int(conn.execute("SELECT COUNT(*) FROM sales_fact_v2").fetchone()[0])
        conn.execute("DELETE FROM sales_fact_v2")
        conn.commit()

        rows, _summary = build_sales_fact_v2_rows_from_entries(
            conn,
            as_of=as_of,
            strict=True,
        )
        rebuilt_rows = len(rows)
        plan = build_rebuild_plan(rows=rows, conn=conn)
        rows_applied = _upsert(conn, plan["rows_insert"] + plan["rows_update"])
        conn.commit()
    finally:
        conn.close()

    parity_output_root = out_dir / "parity"
    parity_status = "FAIL"
    parity_report_json = None
    nonvolatile_mismatch_count = -1
    try:
        parity = validate_sales_truth_ocean_drop_parity(
            db_path=temp_db,
            as_of=as_of,
            ocean_drop_path=ocean_drop_path,
            output_root=parity_output_root,
            volatility_days=14,
            strict=False,
            crm_archive_lookup_path=crm_archive_lookup_path,
            window_days=window_days,
        )
        parity_status = str(parity.get("status") or "FAIL")
        parity_report_json = str((parity_output_root / as_of.isoformat() / "parity_report.json").resolve())
        nonvolatile_mismatch_count = int(parity.get("nonvolatile_mismatch_count") or 0)
    except Exception as exc:
        errors.append(str(exc))

    ok = parity_status == "PASS" and nonvolatile_mismatch_count == 0 and not errors
    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of.isoformat(),
        "status": "PASS" if ok else "FAIL",
        "ok": bool(ok),
        "source_db": str(db_path.resolve()),
        "temp_db": str(temp_db.resolve()),
        "ocean_drop_path": str(ocean_drop_path.resolve()),
        "window_days": int(window_days),
        "pre_wipe_rows": int(pre_wipe_rows),
        "rebuilt_rows": int(rebuilt_rows),
        "rows_applied": int(rows_applied),
        "parity_status": parity_status,
        "nonvolatile_mismatch_count": int(nonvolatile_mismatch_count),
        "parity_report_json": parity_report_json,
        "errors": errors,
    }

    json_path = out_dir / "self_sufficient_report.json"
    md_path = out_dir / "self_sufficient_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_render_md(report), encoding="utf-8")
    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)

    if strict and not ok:
        raise RuntimeError("sales engine self-sufficient validation failed")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate sales engine self-sufficiency against ocean-drop reference")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--ocean-drop", type=Path, default=None)
    parser.add_argument("--anchor-registry", type=Path, default=DEFAULT_ANCHOR_REGISTRY)
    parser.add_argument("--crm-archive-lookup", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--window-days", type=int, default=14)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--strict-if-configured", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        ocean_drop_path = resolve_ocean_drop_path(
            explicit_path=args.ocean_drop,
            registry_path=args.anchor_registry,
        )
    except OceanDropAnchorError as exc:
        if args.strict_if_configured:
            raise RuntimeError(str(exc)) from exc
        print(f"sales_engine_self_sufficient_skip={exc}")
        return 0

    report = validate_sales_engine_self_sufficient(
        db_path=args.db,
        as_of=date.fromisoformat(str(args.as_of)),
        ocean_drop_path=ocean_drop_path,
        output_root=args.output_root,
        strict=bool(args.strict),
        crm_archive_lookup_path=args.crm_archive_lookup,
        window_days=int(args.window_days),
    )
    print(f"sales_engine_self_sufficient_json={report['json_path']}")
    print(f"sales_engine_self_sufficient_md={report['md_path']}")
    print(f"status={report['status']}")
    return 0 if report["ok"] or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
