#!/usr/bin/env python3
"""Import Web_automation snapshot identity as read-only local reference (dry-run by default)."""

from __future__ import annotations

import argparse
from datetime import date, datetime
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.identity_stabilization_common import (
    DEFAULT_ACTIVE_STORES,
    WEB_AUTOMATION_ROOT,
    WEB_SNAPSHOT_ROOT,
    IdentityPlanError,
    StatusError,
    ensure_required_columns,
    normalize_offer_name,
    normalize_store_code,
    parse_iso_date,
    parse_snapshot_date_from_name,
    read_snapshot_frame,
    resolve_latest_snapshot_files,
    sha256_path,
    write_json,
)

DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "identity_stabilization"
DEFAULT_BACKUP_ROOT = PROJECT_ROOT / "runtime" / "backups"
DEFAULT_REF_ROOT = PROJECT_ROOT / "exports" / "external_identity" / "web_automation"
DEFAULT_OVERRIDE_CSV = PROJECT_ROOT / "config" / "identity" / "external_offer_identity_overrides.csv"

_REQUIRED_COLUMNS = [
    "SKU",
    "resolved_kaspi_offer_name",
    "resolved_sku_key",
    "effective_sku_key",
    "effective_final_size",
    "mapping_status",
    "mapping_method",
    "identity_status",
]

_OVERRIDE_REQUIRED_COLUMNS = [
    "store_code",
    "sku_id_ksp",
    "effective_sku_key",
    "effective_size",
]


def _parse_snapshot_sku_field(value: Any) -> tuple[str, str]:
    raw = str(value or "").strip()
    if not raw:
        return "", ""

    if "\t" in raw:
        head, tail = raw.split("\t", 1)
        head = head.strip()
        if head.isdigit():
            return head, tail.strip()

    parts = raw.split()
    if len(parts) >= 2 and parts[0].isdigit():
        return parts[0], " ".join(parts[1:]).strip()

    return raw, ""


def _backup_db(db_path: Path, backup_root: Path) -> Path:
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = backup_root / f"app.db.pre_external_identity_import_{stamp}.sqlite"
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(out))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return out


def _collect_source_files(
    *,
    snapshot_files: list[Path],
    snapshot_root: Path,
    active_stores: tuple[str, ...],
) -> dict[str, Path]:
    if snapshot_files:
        mapping: dict[str, Path] = {}
        for path in snapshot_files:
            resolved = path.expanduser().resolve()
            if not resolved.exists():
                raise StatusError("EXTERNAL_MAPPING_STALE", f"snapshot file missing: {resolved}")
            store = normalize_store_code(resolved.name.split("_snapshot_")[0])
            if store in active_stores:
                mapping[store] = resolved
        if not mapping:
            raise StatusError(
                "EXTERNAL_MAPPING_STALE",
                "no active-store snapshot files matched from --snapshot-file",
            )
        return mapping

    latest = resolve_latest_snapshot_files(snapshot_root=snapshot_root, stores=active_stores)
    if set(active_stores) - set(latest):
        missing = sorted(set(active_stores) - set(latest))
        raise StatusError(
            "EXTERNAL_MAPPING_STALE",
            f"missing latest snapshots for active stores: {', '.join(missing)}",
        )
    return latest


def _build_reference_rows(source_files: dict[str, Path]) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    manifest_sources: list[dict[str, Any]] = []

    for store_code in sorted(source_files):
        src = source_files[store_code]
        df = read_snapshot_frame(src)
        ensure_required_columns(df, _REQUIRED_COLUMNS, source=src)

        snap_date = parse_snapshot_date_from_name(src)
        if snap_date is None:
            raise StatusError(
                "EXTERNAL_MAPPING_STALE",
                f"cannot parse snapshot date from file name: {src.name}",
            )

        for _, row in df.iterrows():
            sku_id_ksp, sku_inline_offer_name = _parse_snapshot_sku_field(row.get("SKU"))
            if not sku_id_ksp:
                continue

            resolved_url = str(row.get("resolved_url") or "").strip()
            kaspi_offer_name = str(row.get("resolved_kaspi_offer_name") or "").strip()
            if not kaspi_offer_name:
                kaspi_offer_name = sku_inline_offer_name
            resolved_sku_key = str(row.get("resolved_sku_key") or "").strip()
            effective_sku_key = str(row.get("effective_sku_key") or "").strip()
            effective_size = str(row.get("effective_final_size") or "").strip().upper()
            mapping_status = str(row.get("mapping_status") or "").strip().lower()
            mapping_method = str(row.get("mapping_method") or "").strip()
            identity_status = str(row.get("identity_status") or "").strip().lower()
            human_edit_sku_key = str(row.get("Human_edit_sku_key") or "").strip()
            human_edit_size = str(row.get("Human_edit_size") or "").strip().upper()

            source = "external_snapshot"
            confidence = "high"
            if human_edit_sku_key:
                source = "external_snapshot_human_edit"
            if mapping_status == "deprecated" or identity_status not in {"matched", ""}:
                confidence = "low"
            elif mapping_method.startswith("manual"):
                confidence = "medium"

            record = {
                "store_code": store_code,
                "snapshot_date": snap_date.isoformat(),
                "sku_id_ksp": sku_id_ksp,
                "resolved_url": resolved_url,
                "kaspi_offer_name": kaspi_offer_name,
                "kaspi_offer_name_norm": normalize_offer_name(kaspi_offer_name),
                "resolved_sku_key": resolved_sku_key,
                "effective_sku_key": effective_sku_key,
                "effective_size": effective_size,
                "mapping_status": mapping_status,
                "mapping_method": mapping_method,
                "identity_status": identity_status,
                "human_edit_sku_key": human_edit_sku_key,
                "human_edit_size": human_edit_size,
                "source": source,
                "confidence": confidence,
                "snapshot_file": str(src),
            }
            rows.append(record)

            unresolved_reason = ""
            if not effective_sku_key:
                unresolved_reason = "missing_effective_sku_key"
            elif mapping_status == "deprecated":
                unresolved_reason = "deprecated_mapping_status"
            elif identity_status and identity_status != "matched":
                unresolved_reason = f"identity_status_{identity_status}"

            if unresolved_reason:
                rec2 = dict(record)
                rec2["unresolved_reason"] = unresolved_reason
                unresolved.append(rec2)

        manifest_sources.append(
            {
                "path": str(src),
                "sha256": sha256_path(src),
                "rows": int(len(df)),
                "snapshot_date": snap_date.isoformat(),
                "store_code": store_code,
            }
        )

    if not rows:
        raise StatusError("EXTERNAL_MAPPING_STALE", "reference import produced zero rows")

    ref_df = pd.DataFrame(rows)
    ref_df = ref_df.sort_values(["store_code", "snapshot_date", "sku_id_ksp", "resolved_url"]).reset_index(drop=True)

    unresolved_df = pd.DataFrame(unresolved)
    if not unresolved_df.empty:
        unresolved_df = unresolved_df.sort_values(["store_code", "snapshot_date", "sku_id_ksp"]).reset_index(drop=True)

    return ref_df, unresolved_df, manifest_sources


def _load_override_map(override_csv: Path | None) -> dict[tuple[str, str], dict[str, str]]:
    if override_csv is None:
        return {}
    path = override_csv.expanduser().resolve()
    if not path.exists():
        raise StatusError("EXTERNAL_MAPPING_STALE", f"override csv missing: {path}")
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    ensure_required_columns(df, _OVERRIDE_REQUIRED_COLUMNS, source=path)
    mapping: dict[tuple[str, str], dict[str, str]] = {}
    for _, row in df.iterrows():
        store = normalize_store_code(str(row.get("store_code") or "").strip())
        sku_id = str(row.get("sku_id_ksp") or "").strip()
        effective_key = str(row.get("effective_sku_key") or "").strip()
        effective_size = str(row.get("effective_size") or "").strip().upper()
        note = str(row.get("note") or "").strip()
        if not store or not sku_id or not effective_key:
            continue
        mapping[(store, sku_id)] = {
            "effective_sku_key": effective_key,
            "effective_size": effective_size,
            "note": note,
        }
    return mapping


def _apply_overrides(ref_df: pd.DataFrame, override_map: dict[tuple[str, str], dict[str, str]]) -> tuple[pd.DataFrame, int]:
    if not override_map:
        return ref_df, 0
    out = ref_df.copy()
    applied = 0
    for idx, row in out.iterrows():
        key = (str(row.get("store_code") or ""), str(row.get("sku_id_ksp") or ""))
        override = override_map.get(key)
        if not override:
            continue
        out.at[idx, "effective_sku_key"] = override["effective_sku_key"]
        if override["effective_size"]:
            out.at[idx, "effective_size"] = override["effective_size"]
        if not str(row.get("resolved_sku_key") or "").strip():
            out.at[idx, "resolved_sku_key"] = override["effective_sku_key"]
        out.at[idx, "mapping_status"] = "matched"
        out.at[idx, "mapping_method"] = "repo_override"
        out.at[idx, "identity_status"] = "matched"
        out.at[idx, "source"] = "repo_override"
        out.at[idx, "confidence"] = "medium"
        applied += 1
    return out, applied


def _build_unresolved_rows(ref_df: pd.DataFrame) -> pd.DataFrame:
    unresolved: list[dict[str, Any]] = []
    for _, row in ref_df.iterrows():
        effective_sku_key = str(row.get("effective_sku_key") or "").strip()
        mapping_status = str(row.get("mapping_status") or "").strip().lower()
        identity_status = str(row.get("identity_status") or "").strip().lower()

        unresolved_reason = ""
        if not effective_sku_key:
            unresolved_reason = "missing_effective_sku_key"
        elif mapping_status == "deprecated":
            unresolved_reason = "deprecated_mapping_status"
        elif identity_status and identity_status != "matched":
            unresolved_reason = f"identity_status_{identity_status}"

        if unresolved_reason:
            rec = dict(row)
            rec["unresolved_reason"] = unresolved_reason
            unresolved.append(rec)

    out = pd.DataFrame(unresolved)
    if not out.empty:
        out = out.sort_values(["store_code", "snapshot_date", "sku_id_ksp"]).reset_index(drop=True)
    return out


def _upsert_reference_table(
    *,
    db_path: Path,
    as_of: date,
    ref_df: pd.DataFrame,
) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dim_offer_identity_external (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                as_of_date TEXT NOT NULL,
                store_code TEXT NOT NULL,
                snapshot_date TEXT NOT NULL,
                sku_id_ksp TEXT,
                resolved_url TEXT,
                kaspi_offer_name TEXT,
                kaspi_offer_name_norm TEXT,
                resolved_sku_key TEXT,
                effective_sku_key TEXT,
                effective_size TEXT,
                mapping_status TEXT,
                mapping_method TEXT,
                identity_status TEXT,
                source TEXT,
                confidence TEXT,
                snapshot_file TEXT,
                imported_at TEXT NOT NULL
            )
            """
        )
        conn.execute("DELETE FROM dim_offer_identity_external WHERE as_of_date = ?", (as_of.isoformat(),))

        stamp = datetime.now().isoformat(timespec="seconds")
        rows = [
            (
                as_of.isoformat(),
                str(r.store_code),
                str(r.snapshot_date),
                str(r.sku_id_ksp),
                str(r.resolved_url),
                str(r.kaspi_offer_name),
                str(r.kaspi_offer_name_norm),
                str(r.resolved_sku_key),
                str(r.effective_sku_key),
                str(r.effective_size),
                str(r.mapping_status),
                str(r.mapping_method),
                str(r.identity_status),
                str(r.source),
                str(r.confidence),
                str(r.snapshot_file),
                stamp,
            )
            for r in ref_df.itertuples(index=False)
        ]
        conn.executemany(
            """
            INSERT INTO dim_offer_identity_external (
                as_of_date, store_code, snapshot_date, sku_id_ksp, resolved_url,
                kaspi_offer_name, kaspi_offer_name_norm, resolved_sku_key,
                effective_sku_key, effective_size, mapping_status, mapping_method,
                identity_status, source, confidence, snapshot_file, imported_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


def import_web_automation_offer_identity(
    *,
    as_of: date,
    web_root: Path,
    snapshot_files: list[Path],
    output_root: Path,
    reference_root: Path,
    db_path: Path,
    apply: bool,
    strict: bool,
    backup_root: Path,
    override_csv: Path | None,
) -> dict[str, Any]:
    snapshot_root = (web_root / "exports" / "pricelist_snapshots").resolve()
    source_files = _collect_source_files(
        snapshot_files=snapshot_files,
        snapshot_root=snapshot_root,
        active_stores=DEFAULT_ACTIVE_STORES,
    )

    ref_df, _unresolved_from_source, manifest_sources = _build_reference_rows(source_files)
    override_map = _load_override_map(override_csv)
    ref_df, overrides_applied = _apply_overrides(ref_df, override_map)
    unresolved_df = _build_unresolved_rows(ref_df)

    latest_snapshot_date = max(date.fromisoformat(row["snapshot_date"]) for row in manifest_sources)
    max_snapshot_age_days = (as_of - latest_snapshot_date).days
    if strict and max_snapshot_age_days > 3:
        raise StatusError(
            "EXTERNAL_MAPPING_STALE",
            f"latest external snapshot is stale by {max_snapshot_age_days} day(s); refresh Web_automation snapshots",
        )

    out_dir = output_root.resolve() / as_of.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    ref_dir = reference_root.resolve() / as_of.isoformat()
    ref_dir.mkdir(parents=True, exist_ok=True)

    ref_csv = out_dir / "offer_identity_reference.csv"
    unresolved_csv = out_dir / "unresolved_rows.csv"
    manifest_json = out_dir / "source_manifest.json"
    report_json = out_dir / "import_report.json"
    report_md = out_dir / "import_report.md"

    ref_df.to_csv(ref_csv, index=False, encoding="utf-8")
    if unresolved_df.empty:
        pd.DataFrame(columns=[*ref_df.columns, "unresolved_reason"]).to_csv(
            unresolved_csv,
            index=False,
            encoding="utf-8",
        )
    else:
        unresolved_df.to_csv(unresolved_csv, index=False, encoding="utf-8")

    shutil.copy2(ref_csv, ref_dir / ref_csv.name)
    shutil.copy2(unresolved_csv, ref_dir / unresolved_csv.name)

    manifest_payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of.isoformat(),
        "sources": manifest_sources,
        "reference_rows": int(len(ref_df)),
        "unresolved_rows": int(len(unresolved_df)),
        "reference_sha256": sha256_path(ref_csv),
        "unresolved_sha256": sha256_path(unresolved_csv),
        "latest_snapshot_date": latest_snapshot_date.isoformat(),
        "max_snapshot_age_days": int(max_snapshot_age_days),
        "override_csv": str(override_csv.resolve()) if override_csv else "",
        "overrides_applied": int(overrides_applied),
    }
    write_json(manifest_json, manifest_payload)

    apply_backup = None
    imported_rows = 0
    apply_manifest_path = out_dir / "apply_manifest.json"
    if apply:
        if str(os.environ.get("ENABLE_DB_WRITE") or "").strip() != "1":
            raise StatusError("EXTERNAL_MAPPING_STALE", "ENABLE_DB_WRITE=1 is required for --apply")
        apply_backup = _backup_db(db_path.resolve(), backup_root.resolve())
        imported_rows = _upsert_reference_table(
            db_path=db_path.resolve(),
            as_of=as_of,
            ref_df=ref_df,
        )
        write_json(
            apply_manifest_path,
            {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "as_of": as_of.isoformat(),
                "db_path": str(db_path.resolve()),
                "backup_path": str(apply_backup),
                "rows_inserted": int(imported_rows),
                "reference_csv": str(ref_csv.resolve()),
                "reference_sha256": sha256_path(ref_csv),
            },
        )

    report_payload = {
        "status": "PASS",
        "error_code": "",
        "as_of": as_of.isoformat(),
        "reference_csv": str(ref_csv.resolve()),
        "unresolved_csv": str(unresolved_csv.resolve()),
        "source_manifest_json": str(manifest_json.resolve()),
        "reference_rows": int(len(ref_df)),
        "unresolved_rows": int(len(unresolved_df)),
        "max_snapshot_age_days": int(max_snapshot_age_days),
        "apply": bool(apply),
        "apply_manifest": str(apply_manifest_path.resolve()) if apply and apply_manifest_path.exists() else "",
        "db_backup_path": str(apply_backup) if apply_backup else "",
        "db_rows_inserted": int(imported_rows),
        "override_csv": str(override_csv.resolve()) if override_csv else "",
        "overrides_applied": int(overrides_applied),
    }
    write_json(report_json, report_payload)
    report_md.write_text(
        "\n".join(
            [
                "# External Offer Identity Import",
                "",
                f"- as_of: `{as_of.isoformat()}`",
                f"- status: `{report_payload['status']}`",
                f"- reference_rows: `{report_payload['reference_rows']}`",
                f"- unresolved_rows: `{report_payload['unresolved_rows']}`",
                f"- max_snapshot_age_days: `{report_payload['max_snapshot_age_days']}`",
                f"- overrides_applied: `{report_payload['overrides_applied']}`",
                f"- apply: `{str(bool(apply)).lower()}`",
                f"- reference_csv: `{report_payload['reference_csv']}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return report_payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import Web_automation external offer identity snapshot")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--web-root", type=Path, default=WEB_AUTOMATION_ROOT)
    parser.add_argument("--snapshot-file", action="append", type=Path, default=[])
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--reference-root", type=Path, default=DEFAULT_REF_ROOT)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument("--override-csv", type=Path, default=DEFAULT_OVERRIDE_CSV)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = import_web_automation_offer_identity(
            as_of=parse_iso_date(args.as_of, field="as_of"),
            web_root=args.web_root.expanduser().resolve(),
            snapshot_files=[p.expanduser().resolve() for p in args.snapshot_file],
            output_root=args.output_root,
            reference_root=args.reference_root,
            db_path=args.db,
            apply=bool(args.apply),
            strict=bool(args.strict),
            backup_root=args.backup_root,
            override_csv=args.override_csv if args.override_csv else None,
        )
    except StatusError as exc:
        print(f"status={exc.code}")
        print(f"error_code={exc.code}")
        print(f"message={exc.message}")
        return 1
    except Exception as exc:  # pragma: no cover
        print("status=FAIL")
        print("error_code=FAIL")
        print(f"message={exc}")
        return 1

    print(f"offer_identity_reference_csv={report['reference_csv']}")
    print(f"unresolved_rows_csv={report['unresolved_csv']}")
    print(f"source_manifest_json={report['source_manifest_json']}")
    print(f"status={report['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
