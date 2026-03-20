#!/usr/bin/env python3
"""Merge UI status-change dates into locked ocean-drop dataset (row-stable, sha-locked)."""

from __future__ import annotations

import argparse
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.sales.ocean_drop_anchor import DEFAULT_REGISTRY, load_ocean_drop_anchor
from scripts.export_kaspi_archive_ui_history import WAREHOUSE_STORE_MAP

DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "ocean_drop"
DEFAULT_VALIDATION_ROOT = PROJECT_ROOT / "exports" / "validation" / "ocean_drop_merge"
DEFAULT_UI_PACK_ANCHOR = PROJECT_ROOT / "config" / "anchors" / "kaspi_archive_ui_pack.json"
COMPLETED_STATUSES = {"ВЫДАН", "ЗАВЕРШЕН"}


def _parse_date(value: str | None) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            pass
    parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
    if parsed is None or pd.isna(parsed):
        return None
    return parsed.date()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _normalize_store(value: str) -> str:
    text = str(value or "").strip().upper()
    return WAREHOUSE_STORE_MAP.get(text, text)


def _resolve_ui_pack_root(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    if DEFAULT_UI_PACK_ANCHOR.exists():
        payload = json.loads(DEFAULT_UI_PACK_ANCHOR.read_text(encoding="utf-8"))
        pack_root = str(payload.get("pack_root") or payload.get("export_root") or "").strip()
        if pack_root:
            return Path(pack_root).expanduser().resolve()
    env_value = str(os.environ.get("AB_KASPI_ARCHIVE_UI_PACK_ROOT") or "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()
    raise RuntimeError("UI pack root is not configured; pass --ui-pack-root")


def _resolve_ui_range(ui_root: Path) -> tuple[date | None, date | None]:
    manifest = ui_root / "manifest.json"
    if not manifest.exists():
        return None, None
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    since = _parse_date(payload.get("since"))
    until = _parse_date(payload.get("until"))
    return since, until


def _build_ui_status_map(ui_root: Path) -> dict[tuple[str, str], tuple[str, date]]:
    status_map: dict[tuple[str, str], tuple[str, date]] = {}
    for store_dir in sorted(ui_root.glob("store_*")):
        if not store_dir.is_dir():
            continue
        store_code = store_dir.name.replace("store_", "").strip().upper()
        csv_path = store_dir / f"ArchiveOrders_{store_code}.csv"
        if not csv_path.exists():
            continue
        df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        for _, row in df.iterrows():
            order_id = str(row.get("№ заказа") or "").strip()
            status = str(row.get("Статус") or "").strip().upper()
            raw_date = str(row.get("Дата изменения статуса") or "").strip()
            parsed = _parse_date(raw_date)
            if not order_id or status not in COMPLETED_STATUSES or parsed is None:
                continue
            key = (store_code, order_id)
            prev = status_map.get(key)
            if prev is None or parsed >= prev[1]:
                status_map[key] = (raw_date, parsed)
    return status_map


def build_ocean_drop_anchor_dataset(
    *,
    as_of: date,
    ui_pack_root: Path,
    anchor_registry: Path,
    output_root: Path,
    validation_root: Path,
    strict: bool,
    update_registry: bool,
    apply: bool,
) -> dict[str, Any]:
    anchor = load_ocean_drop_anchor(anchor_registry)
    base_path = Path(anchor["ocean_drop_path_resolved"]).resolve()
    ui_root = _resolve_ui_pack_root(ui_pack_root)
    if not ui_root.exists():
        raise RuntimeError(f"ui pack root missing: {ui_root}")

    df = pd.read_csv(base_path, dtype=str, keep_default_na=False)
    before_rows = int(len(df))
    if "№ заказа" not in df.columns or "Склад передачи КД" not in df.columns:
        raise RuntimeError("base ocean-drop file missing required columns: № заказа, Склад передачи КД")
    if "Дата изменения статуса" not in df.columns:
        df["Дата изменения статуса"] = ""
    if "Дата поступления заказа" not in df.columns:
        raise RuntimeError("base ocean-drop file missing column: Дата поступления заказа")
    if "Статус" not in df.columns:
        raise RuntimeError("base ocean-drop file missing column: Статус")

    ui_map = _build_ui_status_map(ui_root)
    ui_since, ui_until = _resolve_ui_range(ui_root)

    filled = 0
    overwritten = 0
    missing_keys: list[dict[str, Any]] = []

    for idx, row in df.iterrows():
        order_id = str(row.get("№ заказа") or "").strip()
        store_code = _normalize_store(row.get("Склад передачи КД") or "")
        if not order_id or not store_code:
            continue
        key = (store_code, order_id)
        current_raw = str(row.get("Дата изменения статуса") or "").strip()
        current_date = _parse_date(current_raw)
        mapped = ui_map.get(key)
        if mapped is None:
            continue
        mapped_raw, mapped_date = mapped
        if current_date is None:
            df.at[idx, "Дата изменения статуса"] = mapped_raw
            filled += 1
        elif mapped_date > current_date:
            df.at[idx, "Дата изменения статуса"] = mapped_raw
            overwritten += 1

    if ui_since is not None and ui_until is not None:
        for _, row in df.iterrows():
            status = str(row.get("Статус") or "").strip().upper()
            if status not in COMPLETED_STATUSES:
                continue
            created = _parse_date(row.get("Дата поступления заказа") or "")
            if created is None or created < ui_since or created > ui_until:
                continue
            status_date = _parse_date(row.get("Дата изменения статуса") or "")
            if status_date is None:
                missing_keys.append(
                    {
                        "order_id": str(row.get("№ заказа") or "").strip(),
                        "store_code": _normalize_store(row.get("Склад передачи КД") or ""),
                        "created_at": created.isoformat(),
                    }
                )

    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = output_root / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    out_csv = out_dir / f"ArchiveOrders_ALL_STORES_ocean_drop_{stamp}.csv"
    df.to_csv(out_csv, index=False, encoding="utf-8")
    after_rows = int(len(df))

    if after_rows != before_rows:
        raise RuntimeError(f"row-count drift detected: before={before_rows} after={after_rows}")

    validation_dir = validation_root.resolve() / as_of.isoformat()
    validation_dir.mkdir(parents=True, exist_ok=True)
    missing_csv = validation_dir / "diff_missing_order_ids.csv"
    pd.DataFrame(missing_keys).to_csv(missing_csv, index=False, encoding="utf-8")
    extra_csv = validation_dir / "diff_extra_order_ids.csv"
    pd.DataFrame([], columns=["order_id", "store_code"]).to_csv(extra_csv, index=False, encoding="utf-8")

    sha = _sha256(out_csv)
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": as_of.isoformat(),
        "status": "PASS" if not missing_keys else "FAIL",
        "base_ocean_drop_path": str(base_path),
        "ui_pack_root": str(ui_root),
        "ui_pack_since": ui_since.isoformat() if ui_since else None,
        "ui_pack_until": ui_until.isoformat() if ui_until else None,
        "before_rows": before_rows,
        "after_rows": after_rows,
        "filled_status_change_dates": filled,
        "overwritten_status_change_dates": overwritten,
        "missing_in_ui_coverage": len(missing_keys),
        "output_csv": str(out_csv),
        "output_sha256": sha,
        "diff_missing_order_ids_csv": str(missing_csv),
        "diff_extra_order_ids_csv": str(extra_csv),
        "anchor_registry_path": str(Path(anchor_registry).resolve()),
    }
    report_json = validation_dir / "merge_report.json"
    report_md = validation_dir / "merge_report.md"
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_md.write_text(
        "\n".join(
            [
                "# Ocean Drop Merge Report",
                "",
                f"- status: `{report['status']}`",
                f"- as_of: `{report['as_of']}`",
                f"- before_rows: `{before_rows}`",
                f"- after_rows: `{after_rows}`",
                f"- filled_status_change_dates: `{filled}`",
                f"- overwritten_status_change_dates: `{overwritten}`",
                f"- missing_in_ui_coverage: `{len(missing_keys)}`",
                f"- output_csv: `{out_csv}`",
                f"- output_sha256: `{sha}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    registry_updated = False
    if update_registry:
        if not apply:
            raise RuntimeError("anchor registry update requested but --apply not set")
        if str(os.environ.get("ENABLE_OCEAN_DROP_ANCHOR_UPDATE") or "").strip() != "1":
            raise RuntimeError("anchor registry update requires ENABLE_OCEAN_DROP_ANCHOR_UPDATE=1")
        registry_payload = json.loads(Path(anchor_registry).read_text(encoding="utf-8"))
        registry_payload["ocean_drop_path"] = str(out_csv)
        registry_payload["sha256"] = sha
        registry_payload["as_of_end"] = as_of.isoformat()
        registry_payload["created_at"] = datetime.now().isoformat(timespec="seconds")
        registry_payload["source"] = "merged_api_ui_statusdate"
        registry_payload["transaction_date_mode"] = "delivered_status_date"
        Path(anchor_registry).write_text(
            json.dumps(registry_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        registry_updated = True

    if strict and missing_keys:
        raise RuntimeError(
            f"missing status-change date rows inside ui coverage window: {len(missing_keys)}"
        )

    report["report_json"] = str(report_json)
    report["report_md"] = str(report_md)
    report["registry_updated"] = registry_updated
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build merged ocean-drop anchor dataset (API rows + UI status dates)")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--ui-pack-root", type=Path, default=None)
    parser.add_argument("--anchor-registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--validation-root", type=Path, default=DEFAULT_VALIDATION_ROOT)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--update-anchor-registry", action="store_true")
    parser.add_argument("--apply", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = build_ocean_drop_anchor_dataset(
        as_of=date.fromisoformat(str(args.as_of)),
        ui_pack_root=args.ui_pack_root,
        anchor_registry=args.anchor_registry.resolve(),
        output_root=args.output_root,
        validation_root=args.validation_root,
        strict=bool(args.strict),
        update_registry=bool(args.update_anchor_registry),
        apply=bool(args.apply),
    )
    print(f"ocean_drop_merge_report_json={report['report_json']}")
    print(f"ocean_drop_merge_report_md={report['report_md']}")
    print(f"output_csv={report['output_csv']}")
    print(f"status={report['status']}")
    print(f"registry_updated={str(bool(report['registry_updated'])).lower()}")
    return 0 if (report["status"] == "PASS" or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())
