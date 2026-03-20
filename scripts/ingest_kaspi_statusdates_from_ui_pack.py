#!/usr/bin/env python3
"""Ingest UI status-change dates into fact_orders_kaspi (dry-run default, guarded apply)."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.export_kaspi_archive_ui_history import WAREHOUSE_STORE_MAP

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_BACKUP_ROOT = PROJECT_ROOT / "runtime" / "backups"
DEFAULT_APPLY_MANIFEST_ROOT = PROJECT_ROOT / "exports" / "apply_manifests"
DEFAULT_UI_PACK_ANCHOR = PROJECT_ROOT / "config" / "anchors" / "kaspi_archive_ui_pack.json"


def _normalize_store(value: str) -> str:
    text = str(value or "").strip().upper()
    return WAREHOUSE_STORE_MAP.get(text, text)


def _parse_status_date(value: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
    if parsed is None or pd.isna(parsed):
        return None
    return parsed.date().isoformat()


def _resolve_ui_pack_root(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    if DEFAULT_UI_PACK_ANCHOR.exists():
        payload = json.loads(DEFAULT_UI_PACK_ANCHOR.read_text(encoding="utf-8"))
        pack_root = str(payload.get("pack_root") or "").strip()
        if pack_root:
            return Path(pack_root).expanduser().resolve()
    env_value = str(os.environ.get("AB_KASPI_ARCHIVE_UI_PACK_ROOT") or "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()
    raise RuntimeError("UI pack root is not configured; pass --ui-pack-root")


def _collect_status_map(ui_pack_root: Path) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    for store_dir in sorted(ui_pack_root.glob("store_*")):
        if not store_dir.is_dir():
            continue
        store_code = store_dir.name.replace("store_", "").strip().upper()
        csv_path = store_dir / f"ArchiveOrders_{store_code}.csv"
        if not csv_path.exists():
            continue
        df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        for _, row in df.iterrows():
            order_id = str(row.get("№ заказа") or "").strip()
            status_date = _parse_status_date(row.get("Дата изменения статуса") or "")
            if not order_id or not status_date:
                continue
            row_store = _normalize_store(row.get("Склад передачи КД") or store_code)
            if not row_store:
                row_store = store_code
            key = (row_store, order_id)
            prev = out.get(key)
            if prev is None or status_date >= prev:
                out[key] = status_date
    return out


def _backup_db(db_path: Path, backup_root: Path) -> Path:
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_root / f"app_db_before_statusdate_ingest_{stamp}.sqlite"
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(backup_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return backup_path


def ingest_kaspi_statusdates_from_ui_pack(
    *,
    db_path: Path,
    ui_pack_root: Path | None,
    apply: bool,
    strict: bool,
    backup_root: Path,
    apply_manifest_root: Path,
) -> dict[str, Any]:
    db_path = db_path.resolve()
    if not db_path.exists():
        raise RuntimeError(f"db not found: {db_path}")
    pack_root = _resolve_ui_pack_root(ui_pack_root)
    if not pack_root.exists():
        raise RuntimeError(f"ui pack root missing: {pack_root}")

    status_map = _collect_status_map(pack_root)
    if strict and not status_map:
        raise RuntimeError("status map is empty from UI pack")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, UPPER(COALESCE(store_code, '')) AS store_code, CAST(order_id AS TEXT) AS order_id, COALESCE(status_updated_at, '') AS status_updated_at
            FROM fact_orders_kaspi
            """
        ).fetchall()

        updates: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str]] = set()
        row_index: dict[tuple[str, str], list[sqlite3.Row]] = {}
        for row in rows:
            key = (str(row["store_code"]), str(row["order_id"]))
            row_index.setdefault(key, []).append(row)

        for key, status_date in status_map.items():
            matched = row_index.get(key, [])
            if not matched:
                missing.append({"store_code": key[0], "order_id": key[1], "status_date": status_date})
                continue
            seen_keys.add(key)
            for row in matched:
                current = str(row["status_updated_at"] or "").strip()
                current_date = current[:10] if len(current) >= 10 else ""
                if current_date and current_date >= status_date:
                    continue
                updates.append(
                    {
                        "id": int(row["id"]),
                        "store_code": key[0],
                        "order_id": key[1],
                        "before_status_updated_at": current,
                        "after_status_updated_at": status_date,
                    }
                )

        backup_path: Path | None = None
        if apply:
            if str(os.environ.get("ENABLE_STATUSDATE_INGEST_APPLY") or "").strip() != "1":
                raise RuntimeError("apply requires ENABLE_STATUSDATE_INGEST_APPLY=1")
            backup_path = _backup_db(db_path, backup_root.resolve())
            conn.executemany(
                "UPDATE fact_orders_kaspi SET status_updated_at = ? WHERE id = ?",
                [(row["after_status_updated_at"], row["id"]) for row in updates],
            )
            conn.commit()

    finally:
        conn.close()

    apply_manifest_root = apply_manifest_root.resolve()
    apply_manifest_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    manifest_path = apply_manifest_root / f"statusdate_ingest_{stamp}.json"
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "db_path": str(db_path),
        "ui_pack_root": str(pack_root),
        "apply": bool(apply),
        "backup_path": str(backup_path) if backup_path else None,
        "status_map_keys": len(status_map),
        "updates_planned": len(updates),
        "missing_in_db": len(missing),
        "updates_sample": updates[:200],
        "missing_sample": missing[:200],
        "manifest_path": str(manifest_path),
    }
    manifest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if strict and apply and backup_path is None:
        raise RuntimeError("apply requested but backup was not created")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest UI status-change dates into fact_orders_kaspi")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--ui-pack-root", type=Path, default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument("--apply-manifest-root", type=Path, default=DEFAULT_APPLY_MANIFEST_ROOT)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = ingest_kaspi_statusdates_from_ui_pack(
        db_path=args.db,
        ui_pack_root=args.ui_pack_root,
        apply=bool(args.apply),
        strict=bool(args.strict),
        backup_root=args.backup_root,
        apply_manifest_root=args.apply_manifest_root,
    )
    print(f"statusdate_ingest_manifest={report['manifest_path']}")
    print(f"updates_planned={report['updates_planned']}")
    print(f"missing_in_db={report['missing_in_db']}")
    print(f"apply={str(bool(report['apply'])).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
