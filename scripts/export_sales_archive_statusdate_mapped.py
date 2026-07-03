#!/usr/bin/env python3
"""Build canonical status-date mapped sales archive dataset (all stores, deterministic)."""

from __future__ import annotations

import argparse
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.sales.ocean_drop_anchor import (  # noqa: E402
    DEFAULT_REGISTRY as DEFAULT_OCEAN_DROP_REGISTRY,
    resolve_ocean_drop_path,
)
from scripts.build_ocean_drop_reference_snapshot import (  # noqa: E402
    DELIVERED_STATUSES,
    build_ocean_drop_snapshot_dataframe,
)
from scripts.export_kaspi_archive_ui_history import WAREHOUSE_STORE_MAP  # noqa: E402


DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "sales_archive_statusdate_mapped"
DEFAULT_UI_ANCHOR = PROJECT_ROOT / "config" / "anchors" / "kaspi_archive_ui_pack.json"

REQUIRED_BASE_COLUMNS = {
    "№ заказа",
    "Дата поступления заказа",
    "Дата изменения статуса",
    "Статус",
    "Количество",
    "Сумма",
    "Склад передачи КД",
}

TERMINAL_STATUSES = {
    "ВЫДАН",
    "ЗАВЕРШЕН",
    "ОТМЕНЕН",
    "ВОЗВРАЩЕН",
    "DELIVERED",
    "COMPLETED",
    "CANCELLED",
    "CANCELED",
    "RETURNED",
    "RETURN",
}

STORE_ALIASES = {
    "STORE-B": "STOREB",
    "M GROUP": "STOREB",
    "ONLY FIT": "ACMEWEAR",
    "ONLY-FIT": "ACMEWEAR",
}

CANONICAL_STORE_WAREHOUSE = {
    "UNIVERSAL": "30000001_PP1",
    "ACMEWEAR": "30137883_PP1",
    "11KZ": "30290083_PP1",
    "MELVIS": "30362323_PP1",
    "STOREB": "30000002_PP1",
}


class ExportError(RuntimeError):
    """Raised when source contracts are violated."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        try:
            return date.fromisoformat(text[:10]).isoformat()
        except ValueError:
            pass
    parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
    if parsed is None or pd.isna(parsed):
        return None
    return parsed.date().isoformat()


def _format_date_for_ocean_drop(iso_date: str) -> str:
    return date.fromisoformat(iso_date).strftime("%d.%m.%Y")


def _normalize_store(value: Any) -> str:
    raw = str(value or "").strip().upper()
    if not raw:
        return "UNKNOWN"
    if raw in STORE_ALIASES:
        return STORE_ALIASES[raw]
    spaced = " ".join(raw.replace("-", " ").split())
    if spaced in STORE_ALIASES:
        return STORE_ALIASES[spaced]
    return WAREHOUSE_STORE_MAP.get(raw, raw)


def _row_store_for_status_overlay(row: pd.Series, fallback: str | None = None) -> str:
    for column in (
        "Склад передачи КД",
        "warehouse_code",
        "mapping_source_store_code",
        "Оформил",
        "store_code",
    ):
        if column not in row.index:
            continue
        store = _normalize_store(row.get(column))
        if store and store != "UNKNOWN":
            return store
    return _normalize_store(fallback)


def _first_existing(columns: pd.Index, candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def _load_frame(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    if path.suffix.lower() in {".xlsx", ".xlsm", ".xls"}:
        return pd.read_excel(path, dtype=str).fillna("")
    raise ExportError(f"unsupported source file extension: {path}")


def _resolve_default_ui_source() -> Path | None:
    if not DEFAULT_UI_ANCHOR.exists():
        return None
    payload = json.loads(DEFAULT_UI_ANCHOR.read_text(encoding="utf-8"))
    root = str(payload.get("pack_root") or payload.get("export_root") or "").strip()
    if not root:
        return None
    return Path(root).expanduser().resolve()


def _collect_source_files(source: Path) -> list[Path]:
    src = source.expanduser().resolve()
    if not src.exists():
        raise ExportError(f"ui source path missing: {src}")
    if src.is_file():
        return [src]

    files: list[Path] = []
    preferred = list(src.glob("store_*/ArchiveOrders_*.csv"))
    if preferred:
        files.extend(preferred)
    else:
        for pattern in ("*.csv", "*.xlsx", "*.xlsm", "*.xls"):
            files.extend(src.rglob(pattern))
    # deterministic order
    return sorted({f.resolve() for f in files if f.is_file()})


def _extract_store_from_path(path: Path) -> str | None:
    parent = path.parent.name
    if parent.upper().startswith("STORE_"):
        return parent[6:].upper()
    stem = path.stem.upper()
    if stem.startswith("ARCHIVEORDERS_"):
        store = stem.replace("ARCHIVEORDERS_", "").strip()
        if "ALL_STORES" in store or store.startswith("WEBUI_MERGED"):
            return None
        return store
    return None


def _build_ui_status_map(
    ui_sources: list[Path],
) -> tuple[dict[tuple[str, str], tuple[str, str, str, str]], list[dict[str, Any]]]:
    status_map: dict[tuple[str, str], tuple[str, str, str, str]] = {}
    manifest_rows: list[dict[str, Any]] = []

    for source in ui_sources:
        files = _collect_source_files(source)
        if not files:
            raise ExportError(f"ui source has no readable csv/xlsx files: {source}")

        for file_path in files:
            frame = _load_frame(file_path)
            order_col = _first_existing(frame.columns, ("№ заказа", "order_id"))
            status_col = _first_existing(frame.columns, ("Статус", "status_raw", "status_internal"))
            status_date_col = _first_existing(frame.columns, ("Дата изменения статуса", "status_change_at"))
            if order_col is None or status_col is None or status_date_col is None:
                continue

            store_fallback = _extract_store_from_path(file_path)
            row_count = int(len(frame))
            seen = 0
            for _, row in frame.iterrows():
                order_id = str(row.get(order_col) or "").strip()
                if not order_id:
                    continue
                status = str(row.get(status_col) or "").strip().upper()
                if status not in TERMINAL_STATUSES:
                    continue
                status_raw = str(row.get(status_date_col) or "").strip()
                status_iso = _parse_date(status_raw)
                if status_iso is None:
                    continue
                store_code = _row_store_for_status_overlay(row, store_fallback)
                if store_code == "UNKNOWN":
                    continue
                key = (store_code, order_id)
                prev = status_map.get(key)
                if prev is None or status_iso > prev[1]:
                    status_map[key] = (
                        status_raw,
                        status_iso,
                        str(row.get(status_col) or "").strip(),
                        store_code,
                    )
                seen += 1

            manifest_rows.append(
                {
                    "path": str(file_path),
                    "sha256": _sha256(file_path),
                    "rows": row_count,
                    "mapped_rows": seen,
                }
            )

    return status_map, manifest_rows


def _overlay_status_dates(
    base_df: pd.DataFrame,
    status_map: dict[tuple[str, str], tuple[str, str, str, str]],
) -> tuple[pd.DataFrame, int, int, int]:
    merged = base_df.copy()
    if "Дата изменения статуса" not in merged.columns:
        merged["Дата изменения статуса"] = ""
    if "Статус" not in merged.columns:
        merged["Статус"] = ""

    filled = 0
    status_updates = 0
    warehouse_backfills = 0
    order_ids = merged["№ заказа"].astype(str).str.strip()

    for idx, order_id in order_ids.items():
        store_code = _row_store_for_status_overlay(merged.loc[idx])
        key = (store_code, order_id)
        override = status_map.get(key)
        if override is None:
            continue
        current = str(merged.at[idx, "Дата изменения статуса"] or "").strip()
        current_iso = _parse_date(current)
        override_raw, override_iso, override_status, override_store = override
        if current_iso is None or override_iso > current_iso:
            merged.at[idx, "Дата изменения статуса"] = _format_date_for_ocean_drop(override_iso)
            filled += 1
        if override_status:
            current_status = str(merged.at[idx, "Статус"] or "").strip().upper()
            new_status = str(override_status).strip()
            if current_status != new_status.upper():
                merged.at[idx, "Статус"] = new_status
                status_updates += 1
        if not str(merged.at[idx, "Склад передачи КД"] or "").strip():
            canonical_warehouse = CANONICAL_STORE_WAREHOUSE.get(override_store)
            if canonical_warehouse:
                merged.at[idx, "Склад передачи КД"] = canonical_warehouse
                warehouse_backfills += 1

    return merged, filled, status_updates, warehouse_backfills


def _schema() -> dict[str, Any]:
    return {
        "primary_key": ["line_id"],
        "columns": {
            "line_id": "str",
            "order_id": "str",
            "transaction_date": "date",
            "transaction_month": "yyyy-mm",
            "transaction_date_source": "enum(status_change_date,ui_override_status_date,creation_date_fallback)",
            "store_code": "str",
            "status_internal": "str",
            "return_flag": "int",
            "quantity": "float",
            "gross_rev_kzt": "float",
            "net_rev_kzt": "float",
            "net_delivery_fee_kzt": "float",
            "mapped_sku_key": "str",
            "mapped_sku_id": "str",
            "mapped_size": "str",
            "sku_source": "str",
            "size_source": "str",
            "kd_warehouse": "str",
            "offer_name": "str",
            "article": "str",
        },
    }


def export_sales_archive_statusdate_mapped(
    *,
    since: date,
    until: date,
    ocean_drop_path: Path,
    output_root: Path,
    ui_sources: list[Path],
    strict: bool,
) -> dict[str, Any]:
    if until < since:
        raise ExportError("until must be >= since")

    base_df = pd.read_csv(ocean_drop_path, dtype=str, keep_default_na=False)
    missing = sorted(REQUIRED_BASE_COLUMNS - set(base_df.columns))
    if missing:
        raise ExportError(f"ocean-drop source missing required columns: {', '.join(missing)}")

    status_map: dict[tuple[str, str], tuple[str, str, str, str]] = {}
    ui_manifest_rows: list[dict[str, Any]] = []
    if ui_sources:
        status_map, ui_manifest_rows = _build_ui_status_map(ui_sources)
    elif strict:
        raise ExportError("strict export requires at least one UI source for status-date enrichment")

    merged_df, ui_filled_count, ui_status_updates, ui_warehouse_backfills = _overlay_status_dates(base_df, status_map)

    out_dir = output_root.resolve() / f"{since.isoformat()}_to_{until.isoformat()}"
    out_dir.mkdir(parents=True, exist_ok=True)
    merged_input_csv = out_dir / "_merged_input.csv"
    merged_df.to_csv(merged_input_csv, index=False, encoding="utf-8")

    snapshot_df, snapshot_meta = build_ocean_drop_snapshot_dataframe(
        ocean_drop_path=merged_input_csv,
        as_of=until,
        include_as_of_day=True,
        strict=False,
    )

    if snapshot_df.empty:
        raise ExportError("snapshot build returned 0 rows")

    snapshot_df = snapshot_df[
        (snapshot_df["sale_date"] >= since.isoformat()) & (snapshot_df["sale_date"] <= until.isoformat())
    ].copy()

    if snapshot_df.empty:
        raise ExportError("snapshot has 0 rows inside requested date range")

    override_keys = {
        (str(_row_store_for_status_overlay(row)), str(row.get("№ заказа") or "").strip())
        for _, row in merged_df.iterrows()
        if str(row.get("Дата изменения статуса") or "").strip() and str(row.get("№ заказа") or "").strip()
    }

    def map_date_source(row: pd.Series) -> str:
        base = str(row.get("date_source") or "")
        if base == "creation_date":
            return "creation_date_fallback"
        if base == "status_change_date":
            key = (str(row.get("store_code") or "").upper(), str(row.get("order_id") or "").strip())
            if key in override_keys:
                return "ui_override_status_date"
            return "status_change_date"
        return "creation_date_fallback"

    out_df = pd.DataFrame(
        {
            "line_id": snapshot_df["line_id"].astype(str),
            "order_id": snapshot_df["order_id"].astype(str),
            "transaction_date": snapshot_df["sale_date"].astype(str),
            "transaction_month": pd.to_datetime(snapshot_df["sale_date"], errors="coerce").dt.to_period("M").astype(str),
            "transaction_date_source": snapshot_df.apply(map_date_source, axis=1),
            "store_code": snapshot_df["store_code"].astype(str).str.upper(),
            "status_internal": snapshot_df["status_internal"].astype(str),
            "return_flag": snapshot_df["return_flag"].astype(int),
            "quantity": snapshot_df["quantity"].astype(float),
            "gross_rev_kzt": snapshot_df["gross_rev_kzt"].astype(float),
            "net_rev_kzt": snapshot_df["net_rev_kzt"].astype(float),
            "net_delivery_fee_kzt": snapshot_df["net_delivery_fee_kzt"].astype(float),
            "mapped_sku_key": snapshot_df["sku_key"].astype(str),
            "mapped_sku_id": snapshot_df["sku_id"].astype(str),
            "mapped_size": snapshot_df["my_size"].astype(str),
            "sku_source": snapshot_df["sku_source"].astype(str),
            "size_source": snapshot_df["size_source"].astype(str),
            "kd_warehouse": snapshot_df["kd_warehouse"].astype(str),
            "offer_name": snapshot_df["offer_name"].astype(str),
            "article": snapshot_df["article"].astype(str),
        }
    )
    out_df = out_df.sort_values(["transaction_date", "store_code", "order_id", "mapped_sku_id", "line_id"]).reset_index(drop=True)

    delivered_mask = (out_df["status_internal"] == "DELIVERED") & (out_df["return_flag"] == 0)
    summary_by_store_month = (
        out_df[delivered_mask]
        .groupby(["transaction_month", "store_code", "transaction_date_source"], dropna=False)
        .agg(
            delivered_rows=("line_id", "count"),
            delivered_orders=("order_id", "nunique"),
            units=("quantity", "sum"),
            net_rev_kzt=("net_rev_kzt", "sum"),
        )
        .reset_index()
        .sort_values(["transaction_month", "store_code", "transaction_date_source"])
    )

    output_csv = out_dir / "ArchiveSales_ALL_STORES_statusdate_mapped.csv"
    schema_json = out_dir / "schema.json"
    manifest_json = out_dir / "source_manifest.json"
    summary_csv = out_dir / "summary_by_store_month.csv"

    out_df.to_csv(output_csv, index=False, encoding="utf-8")
    summary_by_store_month.to_csv(summary_csv, index=False, encoding="utf-8")
    schema_json.write_text(json.dumps(_schema(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "since": since.isoformat(),
        "until": until.isoformat(),
        "source_ocean_drop": {
            "path": str(ocean_drop_path.resolve()),
            "sha256": _sha256(ocean_drop_path),
            "rows": int(len(base_df)),
        },
        "ui_sources": ui_manifest_rows,
        "ui_status_map_keys": int(len(status_map)),
        "ui_status_dates_filled": int(ui_filled_count),
        "ui_status_values_updated": int(ui_status_updates),
        "ui_blank_warehouses_backfilled": int(ui_warehouse_backfills),
        "snapshot_meta": snapshot_meta,
        "output": {
            "csv": str(output_csv.resolve()),
            "schema": str(schema_json.resolve()),
            "summary_by_store_month": str(summary_csv.resolve()),
            "rows": int(len(out_df)),
            "sha256": _sha256(output_csv),
        },
        "delivered_rows": int(delivered_mask.sum()),
        "delivered_status_date_rows": int(
            (
                delivered_mask
                & out_df["transaction_date_source"].isin(["status_change_date", "ui_override_status_date"])
            ).sum()
        ),
        "delivered_creation_fallback_rows": int(
            (delivered_mask & (out_df["transaction_date_source"] == "creation_date_fallback")).sum()
        ),
        "stores": sorted(out_df["store_code"].unique().tolist()),
    }
    manifest_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # The merged temp is a build helper only.
    merged_input_csv.unlink(missing_ok=True)

    return {
        "output_dir": str(out_dir.resolve()),
        "output_csv": str(output_csv.resolve()),
        "schema_json": str(schema_json.resolve()),
        "manifest_json": str(manifest_json.resolve()),
        "summary_csv": str(summary_csv.resolve()),
        "rows": int(len(out_df)),
        "delivered_rows": int(delivered_mask.sum()),
        "delivered_creation_fallback_rows": int(
            (delivered_mask & (out_df["transaction_date_source"] == "creation_date_fallback")).sum()
        ),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export canonical status-date mapped sales archive dataset")
    parser.add_argument("--since", required=True, help="YYYY-MM-DD")
    parser.add_argument("--until", required=True, help="YYYY-MM-DD")
    parser.add_argument("--ocean-drop", type=Path, default=None, help="Explicit ocean-drop csv (must match locked anchor)")
    parser.add_argument("--anchor-registry", type=Path, default=DEFAULT_OCEAN_DROP_REGISTRY)
    parser.add_argument("--ui-source", action="append", type=Path, default=[], help="UI source dir/file (csv/xlsx). Can repeat.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    since = date.fromisoformat(args.since)
    until = date.fromisoformat(args.until)

    ocean_drop_path = resolve_ocean_drop_path(
        explicit_path=args.ocean_drop,
        registry_path=args.anchor_registry,
    )

    ui_sources = [p.expanduser().resolve() for p in args.ui_source]
    if not ui_sources:
        default_ui = _resolve_default_ui_source()
        if default_ui is not None:
            ui_sources = [default_ui]

    report = export_sales_archive_statusdate_mapped(
        since=since,
        until=until,
        ocean_drop_path=ocean_drop_path,
        output_root=args.output_root,
        ui_sources=ui_sources,
        strict=bool(args.strict),
    )
    print(f"sales_archive_statusdate_mapped_dir={report['output_dir']}")
    print(f"sales_archive_statusdate_mapped_csv={report['output_csv']}")
    print(f"schema_json={report['schema_json']}")
    print(f"source_manifest_json={report['manifest_json']}")
    print(f"summary_by_store_month_csv={report['summary_csv']}")
    print(f"rows={report['rows']}")
    print(f"delivered_rows={report['delivered_rows']}")
    print(f"delivered_creation_fallback_rows={report['delivered_creation_fallback_rows']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
