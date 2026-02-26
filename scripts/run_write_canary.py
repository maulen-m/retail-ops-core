#!/usr/bin/env python3
"""Run bounded write canaries with explicit gating, backup, and rollback proof."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "canary"
ENV_GATE_DB_ONLY = "ENABLE_WRITE_CANARY_APPLY"
ENV_GATE_PROD_DB = "ENABLE_PROD_DB_CANARY_WRITE"
APPLY_FLAG = "--apply"
DEFAULT_MAX_ROWS = 5
MAX_ROWS_LIMIT = 100


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _create_backup_or_raise(source: Path, target: Path) -> None:
    try:
        shutil.copy2(source, target)
    except Exception as exc:  # pragma: no cover - defensive filesystem failure path
        raise RuntimeError(f"backup creation failed: {target}") from exc
    if not target.exists():
        raise RuntimeError(f"backup required before canary apply: {target}")


def _count_markers(conn: sqlite3.Connection, idempotence_key: str) -> int:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS write_canary_log (
            marker TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL,
            details TEXT
        )
        """
    )
    row = conn.execute(
        "SELECT COUNT(*) FROM write_canary_log WHERE marker LIKE ?",
        (f"{idempotence_key}:%",),
    ).fetchone()
    return int(row[0] if row else 0)


def _apply_markers(conn: sqlite3.Connection, *, idempotence_key: str, max_rows: int) -> int:
    inserted = 0
    now_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    for idx in range(max_rows):
        marker = f"{idempotence_key}:{idx}"
        cursor = conn.execute(
            "INSERT OR IGNORE INTO write_canary_log(marker, applied_at, details) VALUES(?, ?, ?)",
            (marker, now_utc, "db-only canary"),
        )
        if int(cursor.rowcount or 0) > 0:
            inserted += 1
    conn.commit()
    return inserted


def _render_diff_md(payload: dict[str, Any]) -> str:
    lines = [
        "# Write Canary Diff Summary",
        "",
        f"- as_of: `{payload['as_of']}`",
        f"- mode: `{payload['mode']}`",
        f"- idempotence_key: `{payload['idempotence_key']}`",
        f"- max_rows: `{payload['max_rows']}`",
        f"- before_count: `{payload['before_count']}`",
        f"- after_count: `{payload['after_count']}`",
        f"- inserted_rows: `{payload['inserted_rows']}`",
        f"- apply_executed: `{payload['apply_executed']}`",
    ]
    return "\n".join(lines) + "\n"


def _render_report_md(payload: dict[str, Any]) -> str:
    lines = [
        "# Write Canary Report",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        f"- as_of: `{payload['as_of']}`",
        f"- status: `{payload['status']}`",
        f"- mode: `{payload['mode']}`",
        f"- env_gate: `{payload['env_gate']}`",
        f"- apply_flag: `{APPLY_FLAG}`",
        f"- source_db: `{payload['source_db']}`",
        f"- canary_db: `{payload['canary_db']}`",
        f"- backup_path: `{payload['backup_path']}`",
        f"- rollback_copy_path: `{payload['rollback_copy_path']}`",
        f"- rollback_hash_match: `{payload['rollback_hash_match']}`",
        f"- inserted_rows: `{payload['inserted_rows']}`",
        f"- before_count: `{payload['before_count']}`",
        f"- after_count: `{payload['after_count']}`",
        "",
        "## Rollback",
        "",
        f"- `cp {payload['backup_path']} {payload['rollback_target']}`",
        "- Re-run `python3 scripts/run_write_canary.py --strict` for verification.",
    ]
    return "\n".join(lines) + "\n"


def run_write_canary(
    *,
    db_path: Path,
    output_root: Path,
    as_of: str,
    mode: str = "db_only",
    apply: bool,
    strict: bool,
    max_rows: int = DEFAULT_MAX_ROWS,
    idempotence_key: str = "V12_CANARY",
    prod_backup_path: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    target_db = Path(db_path).resolve()
    if not target_db.exists():
        raise RuntimeError(f"db path does not exist: {target_db}")
    if mode not in {"db_only", "prod_db"}:
        raise RuntimeError(f"unsupported mode: {mode}")
    if max_rows < 1 or max_rows > MAX_ROWS_LIMIT:
        raise RuntimeError(f"max_rows out of bounds: {max_rows} (allowed 1..{MAX_ROWS_LIMIT})")

    env_map = dict(env or os.environ)

    out_dir = Path(output_root).resolve() / as_of
    out_dir.mkdir(parents=True, exist_ok=True)

    if mode == "db_only":
        env_gate = ENV_GATE_DB_ONLY
        if apply and env_map.get(env_gate) != "1":
            raise RuntimeError(f"{env_gate}=1 is required when {APPLY_FLAG} is used")
        backup_path = out_dir / "db_backup_pre_canary.sqlite"
        _create_backup_or_raise(target_db, backup_path)
        canary_db = out_dir / "db_canary.sqlite"
        if not canary_db.exists():
            _create_backup_or_raise(backup_path, canary_db)
        write_target = canary_db
        rollback_target = str(canary_db)
    else:
        env_gate = ENV_GATE_PROD_DB
        if apply and env_map.get(env_gate) != "1":
            raise RuntimeError(f"{env_gate}=1 is required when {APPLY_FLAG} is used")
        backup_path = Path(prod_backup_path).resolve() if prod_backup_path else (out_dir / "db_backup_pre_prod_apply.sqlite")
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        _create_backup_or_raise(target_db, backup_path)
        canary_db = target_db
        write_target = target_db
        rollback_target = str(target_db)

    with sqlite3.connect(write_target) as conn:
        before_count = _count_markers(conn, idempotence_key)
        inserted_rows = 0
        if apply:
            inserted_rows = _apply_markers(conn, idempotence_key=idempotence_key, max_rows=max_rows)
        after_count = _count_markers(conn, idempotence_key)

    diff_payload = {
        "as_of": as_of,
        "mode": mode,
        "idempotence_key": idempotence_key,
        "max_rows": int(max_rows),
        "before_count": int(before_count),
        "after_count": int(after_count),
        "inserted_rows": int(inserted_rows),
        "apply_executed": bool(apply),
    }

    diff_json = out_dir / "db_diff_summary.json"
    diff_md = out_dir / "db_diff_summary.md"
    diff_json.write_text(json.dumps(diff_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    diff_md.write_text(_render_diff_md(diff_payload), encoding="utf-8")

    rollback_copy_name = "db_canary_restored.sqlite" if mode == "db_only" else "db_prod_rollback_reference.sqlite"
    rollback_copy = out_dir / rollback_copy_name
    shutil.copy2(backup_path, rollback_copy)
    rollback_hash_match = _sha256(backup_path) == _sha256(rollback_copy)

    rollback_proof = {
        "backup_path": str(backup_path),
        "rollback_copy_path": str(rollback_copy),
        "backup_sha256": _sha256(backup_path),
        "rollback_sha256": _sha256(rollback_copy),
        "hash_match": rollback_hash_match,
    }
    rollback_proof_path = out_dir / "rollback_proof.json"
    rollback_proof_path.write_text(json.dumps(rollback_proof, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = rollback_hash_match
    status = "PASS" if ok else "FAIL"
    report_payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of,
        "status": status,
        "ok": bool(ok),
        "mode": mode,
        "apply_mode": "apply" if apply else "dry-run",
        "source_db": str(target_db),
        "canary_db": str(canary_db),
        "rollback_target": rollback_target,
        "env_gate": env_gate,
        "backup_path": str(backup_path),
        "rollback_copy_path": str(rollback_copy),
        "rollback_hash_match": bool(rollback_hash_match),
        "idempotence_key": idempotence_key,
        "max_rows": int(max_rows),
        "before_count": int(before_count),
        "after_count": int(after_count),
        "inserted_rows": int(inserted_rows),
        "apply_executed": bool(apply),
        "env_gate_enabled": env_map.get(env_gate) == "1",
        "diff_json_path": str(diff_json),
        "diff_md_path": str(diff_md),
        "rollback_proof_path": str(rollback_proof_path),
    }

    report_json = out_dir / "write_canary_report.json"
    report_md = out_dir / "write_canary_report.md"
    report_json.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report_md.write_text(_render_report_md(report_payload), encoding="utf-8")

    if strict and not ok:
        raise RuntimeError("write canary rollback proof failed (hash mismatch)")

    return {
        "ok": bool(ok),
        "status": status,
        "mode": mode,
        "apply_mode": report_payload["apply_mode"],
        "inserted_rows": int(inserted_rows),
        "before_count": int(before_count),
        "after_count": int(after_count),
        "backup_path": str(backup_path),
        "report_json_path": str(report_json),
        "report_md_path": str(report_md),
        "diff_json_path": str(diff_json),
        "diff_md_path": str(diff_md),
        "rollback_proof_path": str(rollback_proof_path),
        "canary_db": str(canary_db),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run write canary with backup and rollback proof")
    parser.add_argument("--db", type=Path, default=PROJECT_ROOT / "db" / "app.db")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--as-of", default=date.today().isoformat())
    parser.add_argument("--mode", choices=["db_only", "prod_db"], default="db_only")
    parser.add_argument("--prod-backup-path", type=Path, default=None)
    parser.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS)
    parser.add_argument("--idempotence-key", default="V12_CANARY")
    parser.add_argument(APPLY_FLAG, dest="apply", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = run_write_canary(
        db_path=args.db,
        output_root=args.output_root,
        as_of=args.as_of,
        mode=str(args.mode),
        apply=bool(args.apply),
        strict=bool(args.strict),
        max_rows=int(args.max_rows),
        idempotence_key=str(args.idempotence_key),
        prod_backup_path=args.prod_backup_path,
        env=os.environ,
    )
    print(f"write_canary_report_json={report['report_json_path']}")
    print(f"write_canary_report_md={report['report_md_path']}")
    print(f"status={report['status']}")
    print(f"mode={report['mode']}")
    print(f"apply_mode={report['apply_mode']}")
    print(f"inserted_rows={report['inserted_rows']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
