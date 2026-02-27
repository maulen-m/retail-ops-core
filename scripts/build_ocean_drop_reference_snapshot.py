#!/usr/bin/env python3
"""Build Ocean Drop reference snapshot and optionally apply into sales_fact_v2 (gated)."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.parsers.kaspi_parser import extract_sku_from_article


DEFAULT_DB = PROJECT_ROOT / "db" / "app.db"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "sales_ocean_drop_parity"
DEFAULT_BACKUP_ROOT = PROJECT_ROOT / "runtime" / "backups"

STORE_MAP = {
    "30000001_PP1": "UNIVERSAL",
    "30137883_PP1": "ACMEWEAR",
    "30000002_PP1": "STOREB",
    "30290083_PP1": "11KZ",
    "30362323_PP1": "MELVIS",
}

DELIVERED_STATUSES = {"ЗАВЕРШЕН", "ВЫДАН", "DELIVERED", "COMPLETED"}
RETURN_STATUSES = {"ВОЗВРАЩЕН", "RETURNED", "RETURN", "RETURNING"}
CANCEL_STATUSES = {"ОТМЕНЕН", "CANCELLED", "CANCELED"}

REQUIRED_COLUMNS = {
    "№ заказа",
    "Статус",
    "Количество",
    "Сумма",
    "Склад передачи КД",
    "Дата поступления заказа",
}


class SnapshotError(RuntimeError):
    pass


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
    if parsed is None or pd.isna(parsed):
        return None
    return parsed.date().isoformat()


def _to_number(value: Any, default: float = 0.0) -> float:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none"}:
        return float(default)
    text = text.replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return float(default)


def _normalize_status(value: Any) -> tuple[str, int]:
    raw = str(value or "").strip()
    upper = raw.upper()
    if upper in DELIVERED_STATUSES:
        return "DELIVERED", 0
    if upper in RETURN_STATUSES:
        return "RETURNED", 1
    if upper in CANCEL_STATUSES:
        return "CANCELLED", 0
    return "OTHER", 0


def _load_crm_lookup(path: Path | None) -> dict[str, tuple[str, str]]:
    if path is None:
        return {}
    if not path.exists():
        raise SnapshotError(f"crm archive lookup file missing: {path}")

    df = pd.read_csv(path, dtype=str)

    order_col = None
    for cand in ("norm_order_id", "OrderID", "№ заказа"):
        if cand in df.columns:
            order_col = cand
            break
    if order_col is None:
        raise SnapshotError("crm archive lookup missing order id column")

    sku_col = None
    for cand in ("norm_sku_key", "SKU_key", "sku_key"):
        if cand in df.columns:
            sku_col = cand
            break

    size_col = None
    for cand in ("MY_SIZE", "norm_my_size", "mapped_size"):
        if cand in df.columns:
            size_col = cand
            break

    lookup: dict[str, tuple[str, str]] = {}
    for _, row in df.iterrows():
        oid = str(row.get(order_col) or "").strip()
        if not oid:
            continue
        sku = str(row.get(sku_col) or "").strip().upper() if sku_col else ""
        size = str(row.get(size_col) or "").strip().upper() if size_col else ""
        if oid not in lookup:
            lookup[oid] = (sku, size)
        else:
            prev_sku, prev_size = lookup[oid]
            if not prev_sku and sku:
                prev_sku = sku
            if not prev_size and size:
                prev_size = size
            lookup[oid] = (prev_sku, prev_size)
    return lookup


def build_ocean_drop_snapshot_dataframe(
    *,
    ocean_drop_path: Path,
    as_of: date,
    crm_archive_lookup_path: Path | None = None,
    include_as_of_day: bool = True,
    strict: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not ocean_drop_path.exists():
        raise SnapshotError(f"ocean drop file missing: {ocean_drop_path}")

    df = pd.read_csv(ocean_drop_path, dtype=str)
    missing_cols = sorted(REQUIRED_COLUMNS - set(df.columns))
    if missing_cols:
        raise SnapshotError(f"ocean drop missing required columns: {', '.join(missing_cols)}")

    crm_lookup = _load_crm_lookup(crm_archive_lookup_path)

    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    date_source_counter = {"status_change_date": 0, "creation_date": 0}
    sku_source_counter = {"mapped": 0, "article_parse": 0, "crm_lookup": 0, "missing": 0}
    size_source_counter = {"mapped": 0, "article_parse": 0, "crm_lookup": 0, "missing": 0}

    cutoff = as_of if include_as_of_day else (as_of - timedelta(days=1))

    for idx, row in df.iterrows():
        order_id = str(row.get("№ заказа") or "").strip()
        if not order_id:
            errors.append(f"row={idx+2}: empty order id")
            continue

        status_internal, return_flag = _normalize_status(row.get("Статус"))
        if status_internal == "OTHER":
            # Ignore non-terminal statuses in strict parity baseline.
            continue

        sale_date = _parse_date(row.get("Дата изменения статуса"))
        date_source = "status_change_date"
        if not sale_date:
            sale_date = _parse_date(row.get("Дата поступления заказа"))
            date_source = "creation_date"
        if not sale_date:
            errors.append(f"row={idx+2} order_id={order_id}: missing sale date")
            continue
        if date.fromisoformat(sale_date) > cutoff:
            continue
        date_source_counter[date_source] += 1

        warehouse = str(row.get("Склад передачи КД") or "").strip().upper()
        store_code = STORE_MAP.get(warehouse, "UNKNOWN")
        if strict and store_code == "UNKNOWN":
            errors.append(f"row={idx+2} order_id={order_id}: unknown warehouse '{warehouse}'")
            continue

        offer_name = str(row.get("Название в системе продавца") or row.get("Название товара в Kaspi Магазине") or "").strip()
        article = str(row.get("Артикул") or "").strip().upper()

        mapped_sku = str(row.get("mapped_sku_key") or "").strip().upper()
        mapped_size = str(row.get("mapped_size") or "").strip().upper()

        sku_key = mapped_sku
        sku_source = "mapped" if sku_key else ""
        size = mapped_size
        size_source = "mapped" if size else ""

        if not sku_key or not size:
            parsed = extract_sku_from_article(article, offer_name)
            parsed_key = str(parsed.get("sku_key") or "").strip().upper()
            parsed_size = str(parsed.get("my_size") or "").strip().upper()
            if not sku_key and parsed_key:
                sku_key = parsed_key
                sku_source = "article_parse"
            if not size and parsed_size:
                size = parsed_size
                size_source = "article_parse"

        if not sku_key or not size:
            crm_sku, crm_size = crm_lookup.get(order_id, ("", ""))
            if not sku_key and crm_sku:
                sku_key = crm_sku
                sku_source = "crm_lookup"
            if not size and crm_size:
                size = crm_size
                size_source = "crm_lookup"

        if not sku_key:
            sku_source = "missing"
        if not size:
            size_source = "missing"

        sku_source_counter[sku_source] += 1
        size_source_counter[size_source] += 1

        if strict and (not sku_key or not size) and status_internal == "DELIVERED":
            errors.append(f"row={idx+2} order_id={order_id}: missing delivered identity sku_key/size")
            continue

        qty = _to_number(row.get("Количество"), default=1.0)
        if qty <= 0:
            qty = 1.0

        gross = _to_number(row.get("Сумма"), default=0.0)
        seller_delivery = _to_number(row.get("Стоимость доставки для продавца"), default=0.0)
        delivery_comp = _to_number(row.get("Компенсация за доставку"), default=0.0)
        net_delivery = seller_delivery - delivery_comp

        if not sku_key:
            sku_key = article or f"UNKNOWN_{store_code}"
        sku_id = f"{sku_key}_{size}" if size else sku_key

        fingerprint = "|".join(
            [
                order_id,
                sale_date,
                store_code,
                sku_id,
                str(qty),
                str(gross),
                status_internal,
                offer_name,
            ]
        )
        line_id = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:32]

        rows.append(
            {
                "line_id": line_id,
                "order_id": order_id,
                "sale_date": sale_date,
                "store_code": store_code,
                "kd_warehouse": warehouse,
                "status_internal": status_internal,
                "return_flag": int(return_flag),
                "quantity": float(qty),
                "gross_rev_kzt": float(gross),
                "net_delivery_fee_kzt": float(net_delivery),
                "net_rev_kzt": float(gross),
                "sku_key": sku_key,
                "sku_id": sku_id,
                "my_size": size,
                "offer_name": offer_name,
                "article": article,
                "date_source": date_source,
                "sku_source": sku_source,
                "size_source": size_source,
            }
        )

    if strict and errors:
        raise SnapshotError("; ".join(errors[:20]))

    out_df = pd.DataFrame(rows)
    if not out_df.empty:
        out_df = out_df.sort_values(["sale_date", "store_code", "order_id", "sku_id"]).reset_index(drop=True)

    meta = {
        "rows_total": int(len(df)),
        "rows_snapshot": int(len(out_df)),
        "errors_count": int(len(errors)),
        "errors_sample": errors[:50],
        "date_source_counter": date_source_counter,
        "sku_source_counter": sku_source_counter,
        "size_source_counter": size_source_counter,
        "stores": sorted({str(v) for v in out_df["store_code"].unique()}) if not out_df.empty else [],
    }
    return out_df, meta


def _backup_db(db_path: Path, backup_root: Path) -> Path:
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_root / f"app_db_before_ocean_drop_apply_{stamp}.sqlite"
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(backup_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return backup_path


def _apply_to_sales_fact_v2(*, db_path: Path, snapshot_df: pd.DataFrame, as_of: date, backup_root: Path) -> dict[str, Any]:
    if str(os.environ.get("ENABLE_OCEAN_DROP_APPLY") or "").strip() != "1":
        raise SnapshotError("apply requested, but ENABLE_OCEAN_DROP_APPLY=1 is required")

    if snapshot_df.empty:
        raise SnapshotError("snapshot is empty, refusing apply")

    backup_path = _backup_db(db_path, backup_root)
    conn = sqlite3.connect(str(db_path))
    try:
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sales_fact_v2'"
        ).fetchone()
        if not has_table:
            raise SnapshotError("sales_fact_v2 table missing")

        stores = sorted({str(v).upper() for v in snapshot_df["store_code"].tolist() if str(v).strip()})
        placeholders = ",".join("?" for _ in stores)
        delete_sql = f"""
            DELETE FROM sales_fact_v2
            WHERE date(order_date) <= ?
              AND UPPER(COALESCE(store_code, '')) IN ({placeholders})
        """
        conn.execute(delete_sql, (as_of.isoformat(), *stores))

        rows = []
        grouped = (
            snapshot_df.fillna("")
            .groupby(
                [
                    "order_id",
                    "sale_date",
                    "store_code",
                    "sku_key",
                    "sku_id",
                    "my_size",
                    "offer_name",
                    "status_internal",
                    "return_flag",
                ],
                dropna=False,
                as_index=False,
            )
            .agg(
                quantity=("quantity", "sum"),
                gross_rev_kzt=("gross_rev_kzt", "sum"),
                net_delivery_fee_kzt=("net_delivery_fee_kzt", "sum"),
            )
        )

        for _, r in grouped.iterrows():
            status_internal = str(r["status_internal"])
            if status_internal not in {"DELIVERED", "CANCELLED", "RETURNED"}:
                continue
            qty = float(r["quantity"])
            gross = float(r["gross_rev_kzt"])
            sell_price = gross / qty if qty > 0 else gross
            rows.append(
                (
                    str(r["order_id"]),
                    str(r["sale_date"]),
                    str(r["sku_key"]),
                    str(r["sku_id"]),
                    str(r.get("my_size") or ""),
                    str(r.get("offer_name") or r.get("article") or r["sku_key"]),
                    str(r["store_code"]),
                    int(round(qty)),
                    float(sell_price),
                    float(r.get("net_delivery_fee_kzt") or 0.0),
                    None,
                    float(gross),
                    None,
                    status_internal,
                    int(r.get("return_flag") or 0),
                    str(r["sale_date"]) if status_internal == "RETURNED" else None,
                    "OCEAN_DROP_ANCHOR",
                    None,
                )
            )

        conn.executemany(
            """
            INSERT INTO sales_fact_v2 (
                order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name, store_code,
                quantity, sell_price_kzt, delivery_fee, cogs, net_rev, profit,
                status, return_flag, return_date, source_file, api_updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(order_id, sku_id, store_code, kaspi_offer_name)
            DO UPDATE SET
                order_date=excluded.order_date,
                quantity=excluded.quantity,
                sell_price_kzt=excluded.sell_price_kzt,
                delivery_fee=excluded.delivery_fee,
                cogs=excluded.cogs,
                net_rev=excluded.net_rev,
                profit=excluded.profit,
                status=excluded.status,
                return_flag=excluded.return_flag,
                return_date=excluded.return_date,
                source_file=excluded.source_file,
                api_updated_at=excluded.api_updated_at,
                ingested_at=CURRENT_TIMESTAMP
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "backup_path": str(backup_path),
        "rows_applied": int(len(rows)),
        "as_of": as_of.isoformat(),
    }


def _render_report_md(report: dict[str, Any]) -> str:
    lines = [
        "# Ocean Drop Reference Snapshot",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- as_of: `{report['as_of']}`",
        f"- include_as_of_day: `{str(report['include_as_of_day']).lower()}`",
        f"- status: `{report['status']}`",
        f"- rows_snapshot: `{report['rows_snapshot']}`",
        f"- rows_delivered: `{report['rows_delivered']}`",
        f"- errors_count: `{report['errors_count']}`",
        f"- apply_status: `{report['apply_status']}`",
        "",
        "## Outputs",
        f"- snapshot_csv: `{report['snapshot_csv']}`",
        f"- delivered_csv: `{report['delivered_csv']}`",
        f"- manifest_json: `{report['manifest_json']}`",
        f"- report_json: `{report['report_json']}`",
    ]
    if report.get("db_backup_path"):
        lines.append(f"- db_backup_path: `{report['db_backup_path']}`")
    if report.get("errors_sample"):
        lines.extend(["", "## Errors (sample)"])
        for err in report["errors_sample"][:30]:
            lines.append(f"- {err}")
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build Ocean Drop reference snapshot")
    p.add_argument("--ocean-drop", type=Path, required=True)
    p.add_argument("--crm-archive-lookup", type=Path, default=None)
    p.add_argument("--as-of", type=str, required=True)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    p.add_argument("--include-as-of-day", action="store_true")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--apply", action="store_true")
    return p


def main() -> int:
    args = _build_parser().parse_args()
    as_of = date.fromisoformat(str(args.as_of))
    out_dir = args.output_root.resolve() / as_of.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)

    snapshot_df, meta = build_ocean_drop_snapshot_dataframe(
        ocean_drop_path=args.ocean_drop.resolve(),
        as_of=as_of,
        crm_archive_lookup_path=args.crm_archive_lookup.resolve() if args.crm_archive_lookup else None,
        include_as_of_day=bool(args.include_as_of_day),
        strict=bool(args.strict),
    )

    snapshot_csv = out_dir / "ocean_drop_reference_snapshot.csv"
    delivered_csv = out_dir / "ocean_drop_reference_snapshot_delivered.csv"
    manifest_json = out_dir / "ocean_drop_reference_snapshot_manifest.json"
    report_json = out_dir / "ocean_drop_reference_snapshot_report.json"
    report_md = out_dir / "ocean_drop_reference_snapshot_report.md"

    snapshot_df.to_csv(snapshot_csv, index=False, encoding="utf-8")
    delivered_df = snapshot_df[
        (snapshot_df["status_internal"] == "DELIVERED") & (snapshot_df["return_flag"] == 0)
    ].copy() if not snapshot_df.empty else snapshot_df.copy()
    delivered_df.to_csv(delivered_csv, index=False, encoding="utf-8")

    manifest = {
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z"),
        "as_of": as_of.isoformat(),
        "include_as_of_day": bool(args.include_as_of_day),
        "ocean_drop": str(args.ocean_drop.resolve()),
        "ocean_drop_sha256": _file_sha256(args.ocean_drop.resolve()),
        "crm_archive_lookup": str(args.crm_archive_lookup.resolve()) if args.crm_archive_lookup else None,
        "crm_archive_lookup_sha256": _file_sha256(args.crm_archive_lookup.resolve()) if args.crm_archive_lookup else None,
        "rows_snapshot": int(len(snapshot_df)),
        "rows_delivered": int(len(delivered_df)),
        "meta": meta,
    }
    manifest_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    apply_status = "DRY_RUN"
    db_backup_path = None
    rows_applied = 0
    if args.apply:
        apply = _apply_to_sales_fact_v2(
            db_path=args.db.resolve(),
            snapshot_df=snapshot_df,
            as_of=as_of,
            backup_root=args.backup_root.resolve(),
        )
        apply_status = "APPLIED"
        db_backup_path = apply["backup_path"]
        rows_applied = int(apply["rows_applied"])

    status = "PASS"
    if args.strict and meta.get("errors_count", 0):
        status = "FAIL"

    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z"),
        "as_of": as_of.isoformat(),
        "include_as_of_day": bool(args.include_as_of_day),
        "status": status,
        "rows_snapshot": int(len(snapshot_df)),
        "rows_delivered": int(len(delivered_df)),
        "errors_count": int(meta.get("errors_count", 0)),
        "errors_sample": meta.get("errors_sample", []),
        "snapshot_csv": str(snapshot_csv),
        "delivered_csv": str(delivered_csv),
        "manifest_json": str(manifest_json),
        "report_json": str(report_json),
        "apply_status": apply_status,
        "rows_applied": rows_applied,
        "db_backup_path": db_backup_path,
    }
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_md.write_text(_render_report_md(report), encoding="utf-8")

    print(f"ocean_drop_snapshot_csv={snapshot_csv}")
    print(f"ocean_drop_snapshot_delivered_csv={delivered_csv}")
    print(f"ocean_drop_snapshot_manifest={manifest_json}")
    print(f"ocean_drop_snapshot_report={report_json}")
    print(f"apply_status={apply_status}")
    if db_backup_path:
        print(f"db_backup_path={db_backup_path}")

    if args.strict and status != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
