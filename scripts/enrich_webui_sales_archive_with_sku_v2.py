#!/usr/bin/env python3
"""Append canonical SKU mapping columns to a raw WebUI merged archive CSV."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import re
import sys
from typing import Any, Iterable

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.parsers.kaspi_parser import extract_sku_from_article  # noqa: E402
from core.sales.kaspi_etl_reference import _load_offer_identity_map_from_db  # noqa: E402
from core.utils.sku_normalize import normalize_size  # noqa: E402
from scripts.export_kaspi_archive_ui_history import WAREHOUSE_STORE_MAP  # noqa: E402


DEFAULT_DB_PATH = PROJECT_ROOT / "db" / "app.db"
MAPPING_APPEND_COLUMNS = (
    "mapped_sku_key",
    "mapped_size",
    "mapping_status",
    "mapping_method",
    "mapping_source_store_code",
)
REQUIRED_SOURCE_COLUMNS = {
    "store_code",
    "article",
    "kaspi_offer_name",
    "seller_system_name",
    "order_id",
}
NUMERIC_TOKEN_RE = re.compile(r"\d{6,}")


class EnrichmentError(RuntimeError):
    """Raised when the requested v2 enrichment cannot be completed safely."""


@dataclass(frozen=True)
class MappingDecision:
    sku_key: str
    size: str
    source_store_code: str


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_upper(value: Any) -> str:
    return _normalize_text(value).upper()


def _normalize_size_value(value: Any) -> str:
    raw = _normalize_upper(value)
    if not raw:
        return ""
    normalized = normalize_size(raw, product_type="CL")
    return _normalize_upper(normalized or raw)


def _derive_size_from_sku_id(*, sku_key: str, sku_id: str) -> str:
    key = _normalize_upper(sku_key)
    sid = _normalize_upper(sku_id)
    if not key or not sid:
        return ""
    prefix = f"{key}_"
    if sid.startswith(prefix):
        return _normalize_size_value(sid[len(prefix) :])
    return ""


def _default_output_path(source_csv: Path) -> Path:
    stem = source_csv.stem
    return source_csv.with_name(f"{stem}_v2{source_csv.suffix}")


def _default_historical_root(source_csv: Path) -> Path:
    try:
        base_root = source_csv.parents[2]
    except IndexError as exc:  # pragma: no cover - defensive only
        raise EnrichmentError(f"cannot infer historical mapped-data root from {source_csv}") from exc
    return base_root / "Sales_archive" / "mapped_data"


def _pick_best(counter: Counter[MappingDecision]) -> MappingDecision | None:
    if not counter:
        return None
    return sorted(
        counter.items(),
        key=lambda item: (
            -item[1],
            item[0].sku_key,
            item[0].size,
            item[0].source_store_code,
        ),
    )[0][0]


def _choose_db_cross_store_candidate(
    article: str,
    article_token_map: dict[tuple[str, str], tuple[str, str]],
    *,
    valid_sku_keys: set[str],
) -> MappingDecision | None:
    candidates: Counter[MappingDecision] = Counter()
    for token in NUMERIC_TOKEN_RE.findall(article):
        for (source_store, mapped_token), (sku_key, sku_id) in article_token_map.items():
            if mapped_token != token:
                continue
            key = _normalize_upper(sku_key)
            if not key:
                continue
            if valid_sku_keys and key not in valid_sku_keys:
                continue
            size = _derive_size_from_sku_id(sku_key=key, sku_id=sku_id)
            candidates[MappingDecision(key, size, _normalize_upper(source_store))] += 1
    return _pick_best(candidates)


def _read_csv_dict_rows(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        yield from csv.DictReader(fh)


def _historical_row_store_code(row: dict[str, str]) -> str:
    source_store = _normalize_upper(row.get("mapping_source_store_code"))
    if source_store:
        return source_store
    store = _normalize_upper(row.get("store_code"))
    if store:
        return store
    warehouse = _normalize_upper(row.get("Склад передачи КД"))
    return _normalize_upper(WAREHOUSE_STORE_MAP.get(warehouse, warehouse))


def _load_historical_mapped_indices(
    root: Path,
    *,
    valid_sku_keys: set[str],
) -> tuple[
    dict[tuple[str, str], MappingDecision],
    dict[tuple[str, str], MappingDecision],
    dict[tuple[str, str], MappingDecision],
    dict[tuple[str, str], MappingDecision],
]:
    article_counter: dict[tuple[str, str], Counter[MappingDecision]] = {}
    offer_counter: dict[tuple[str, str], Counter[MappingDecision]] = {}
    seller_counter: dict[tuple[str, str], Counter[MappingDecision]] = {}
    token_counter: dict[tuple[str, str], Counter[MappingDecision]] = {}
    if not root.exists():
        return {}, {}, {}, {}

    for csv_path in sorted(root.rglob("*.csv")):
        for row in _read_csv_dict_rows(csv_path):
            sku_key = _normalize_upper(row.get("mapped_sku_key"))
            if not sku_key:
                continue
            if valid_sku_keys and sku_key not in valid_sku_keys:
                continue
            source_store = _historical_row_store_code(row)
            if not source_store:
                continue
            size = _normalize_size_value(row.get("mapped_size"))
            decision = MappingDecision(
                sku_key=sku_key,
                size=size,
                source_store_code=source_store,
            )

            article = _normalize_upper(row.get("Артикул"))
            if article:
                article_counter.setdefault((source_store, article), Counter())[decision] += 1
                for token in NUMERIC_TOKEN_RE.findall(article):
                    token_counter.setdefault((source_store, token), Counter())[decision] += 1

            offer_name = _normalize_upper(row.get("Название товара в Kaspi Магазине"))
            if offer_name:
                offer_counter.setdefault((source_store, offer_name), Counter())[decision] += 1

            seller_name = _normalize_upper(row.get("Название в системе продавца"))
            if seller_name:
                seller_counter.setdefault((source_store, seller_name), Counter())[decision] += 1

    def _freeze(
        source: dict[tuple[str, str], Counter[MappingDecision]],
    ) -> dict[tuple[str, str], MappingDecision]:
        out: dict[tuple[str, str], MappingDecision] = {}
        for key, decisions in source.items():
            best = _pick_best(decisions)
            if best is not None:
                out[key] = best
        return out

    return (
        _freeze(article_counter),
        _freeze(offer_counter),
        _freeze(seller_counter),
        _freeze(token_counter),
    )


def _resolve_row_mapping(
    row: dict[str, str],
    *,
    offer_identity_map: dict[tuple[str, str], tuple[str, str]],
    article_token_map: dict[tuple[str, str], tuple[str, str]],
    valid_sku_keys: set[str],
    historical_article_map: dict[tuple[str, str], MappingDecision],
    historical_offer_map: dict[tuple[str, str], MappingDecision],
    historical_seller_map: dict[tuple[str, str], MappingDecision],
    historical_token_map: dict[tuple[str, str], MappingDecision],
) -> dict[str, str]:
    store_code = _normalize_upper(row.get("store_code"))
    article = _normalize_upper(row.get("article"))
    kaspi_offer_name = _normalize_upper(row.get("kaspi_offer_name"))
    seller_system_name = _normalize_upper(row.get("seller_system_name"))

    parsed = extract_sku_from_article(article, kaspi_offer_name or seller_system_name)
    parsed_sku_key = _normalize_upper(parsed.get("sku_key"))
    parsed_size = _normalize_size_value(parsed.get("my_size"))
    if parsed_sku_key and (not valid_sku_keys or parsed_sku_key in valid_sku_keys):
        return {
            "mapped_sku_key": parsed_sku_key,
            "mapped_size": parsed_size,
            "mapping_status": "resolved",
            "mapping_method": "parser",
            "mapping_source_store_code": store_code,
        }

    mapped = offer_identity_map.get((store_code, kaspi_offer_name))
    if mapped:
        mapped_sku_key = _normalize_upper(mapped[0])
        if mapped_sku_key and (not valid_sku_keys or mapped_sku_key in valid_sku_keys):
            mapped_size = parsed_size or _derive_size_from_sku_id(
                sku_key=mapped_sku_key,
                sku_id=_normalize_upper(mapped[1]),
            )
            return {
                "mapped_sku_key": mapped_sku_key,
                "mapped_size": mapped_size,
                "mapping_status": "resolved",
                "mapping_method": "db_offer",
                "mapping_source_store_code": store_code,
            }

    token_candidates = Counter()
    for token in NUMERIC_TOKEN_RE.findall(article):
        mapped = article_token_map.get((store_code, token))
        if mapped is None:
            continue
        mapped_sku_key = _normalize_upper(mapped[0])
        if not mapped_sku_key:
            continue
        if valid_sku_keys and mapped_sku_key not in valid_sku_keys:
            continue
        token_candidates[
            MappingDecision(
                sku_key=mapped_sku_key,
                size=_derive_size_from_sku_id(
                    sku_key=mapped_sku_key,
                    sku_id=_normalize_upper(mapped[1]),
                ),
                source_store_code=store_code,
            )
        ] += 1
    db_store_token = _pick_best(token_candidates)
    if db_store_token is not None:
        return {
            "mapped_sku_key": db_store_token.sku_key,
            "mapped_size": parsed_size or db_store_token.size,
            "mapping_status": "resolved",
            "mapping_method": "db_token_store",
            "mapping_source_store_code": db_store_token.source_store_code,
        }

    db_cross_token = _choose_db_cross_store_candidate(
        article,
        article_token_map,
        valid_sku_keys=valid_sku_keys,
    )
    if db_cross_token is not None:
        return {
            "mapped_sku_key": db_cross_token.sku_key,
            "mapped_size": parsed_size or db_cross_token.size,
            "mapping_status": "resolved",
            "mapping_method": "db_token_cross",
            "mapping_source_store_code": db_cross_token.source_store_code,
        }

    historical = historical_article_map.get((store_code, article))
    if historical is not None:
        return {
            "mapped_sku_key": historical.sku_key,
            "mapped_size": parsed_size or historical.size,
            "mapping_status": "resolved",
            "mapping_method": "hist_article_exact",
            "mapping_source_store_code": historical.source_store_code,
        }

    historical = historical_offer_map.get((store_code, kaspi_offer_name))
    if historical is not None:
        return {
            "mapped_sku_key": historical.sku_key,
            "mapped_size": parsed_size or historical.size,
            "mapping_status": "resolved",
            "mapping_method": "hist_offer_exact",
            "mapping_source_store_code": historical.source_store_code,
        }

    historical = historical_seller_map.get((store_code, seller_system_name))
    if historical is not None:
        return {
            "mapped_sku_key": historical.sku_key,
            "mapped_size": parsed_size or historical.size,
            "mapping_status": "resolved",
            "mapping_method": "hist_seller_exact",
            "mapping_source_store_code": historical.source_store_code,
        }

    hist_token_candidates = Counter()
    for token in NUMERIC_TOKEN_RE.findall(article):
        historical = historical_token_map.get((store_code, token))
        if historical is None:
            continue
        hist_token_candidates[historical] += 1
    hist_store_token = _pick_best(hist_token_candidates)
    if hist_store_token is not None:
        return {
            "mapped_sku_key": hist_store_token.sku_key,
            "mapped_size": parsed_size or hist_store_token.size,
            "mapping_status": "resolved",
            "mapping_method": "hist_token_store",
            "mapping_source_store_code": hist_store_token.source_store_code,
        }

    return {
        "mapped_sku_key": "",
        "mapped_size": "",
        "mapping_status": "unresolved",
        "mapping_method": "unresolved",
        "mapping_source_store_code": "",
    }


def enrich_webui_sales_archive_with_sku_v2(
    *,
    source_csv: Path,
    output_csv: Path | None = None,
    db_path: Path | None = DEFAULT_DB_PATH,
    historical_mapped_root: Path | None = None,
) -> dict[str, Any]:
    source_csv = source_csv.expanduser().resolve()
    if not source_csv.exists():
        raise EnrichmentError(f"source csv missing: {source_csv}")

    output_csv = (output_csv or _default_output_path(source_csv)).expanduser().resolve()
    historical_mapped_root = (
        historical_mapped_root.expanduser().resolve()
        if historical_mapped_root is not None
        else _default_historical_root(source_csv)
    )
    db_path = db_path.expanduser().resolve() if db_path is not None else None

    source_df = pd.read_csv(source_csv, dtype=str, keep_default_na=False)
    missing = sorted(REQUIRED_SOURCE_COLUMNS - set(source_df.columns))
    if missing:
        raise EnrichmentError(f"source csv missing required columns: {', '.join(missing)}")

    offer_identity_map, article_token_map, valid_sku_keys = _load_offer_identity_map_from_db(db_path=db_path)
    (
        historical_article_map,
        historical_offer_map,
        historical_seller_map,
        historical_token_map,
    ) = _load_historical_mapped_indices(
        historical_mapped_root,
        valid_sku_keys=valid_sku_keys,
    )

    source_records = source_df.to_dict("records")
    mapping_rows = [
        _resolve_row_mapping(
            row,
            offer_identity_map=offer_identity_map,
            article_token_map=article_token_map,
            valid_sku_keys=valid_sku_keys,
            historical_article_map=historical_article_map,
            historical_offer_map=historical_offer_map,
            historical_seller_map=historical_seller_map,
            historical_token_map=historical_token_map,
        )
        for row in source_records
    ]
    mapping_df = pd.DataFrame(mapping_rows, columns=MAPPING_APPEND_COLUMNS)

    output_df = source_df.copy()
    for column in MAPPING_APPEND_COLUMNS:
        output_df[column] = mapping_df[column].fillna("").astype(str)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_df.to_csv(output_csv, index=False, encoding="utf-8-sig")
    readback_df = pd.read_csv(output_csv, dtype=str, keep_default_na=False)
    if readback_df.columns.tolist() != output_df.columns.tolist():
        raise EnrichmentError("output readback column mismatch")
    if len(readback_df) != len(output_df):
        raise EnrichmentError("output readback row count mismatch")

    method_counts = (
        mapping_df["mapping_method"].value_counts(dropna=False).sort_index().to_dict()
        if not mapping_df.empty
        else {}
    )
    resolved_rows = int(mapping_df["mapping_status"].eq("resolved").sum()) if not mapping_df.empty else 0
    unresolved_rows = int(mapping_df["mapping_status"].eq("unresolved").sum()) if not mapping_df.empty else 0
    return {
        "source_csv": str(source_csv),
        "output_csv": str(output_csv),
        "db_path": str(db_path) if db_path is not None else "",
        "historical_mapped_root": str(historical_mapped_root),
        "rows_total": int(len(output_df)),
        "resolved_rows": resolved_rows,
        "unresolved_rows": unresolved_rows,
        "method_counts": method_counts,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Append canonical SKU mapping columns to a raw WebUI merged archive CSV."
    )
    parser.add_argument("--source-csv", required=True, type=Path, help="Path to raw ArchiveOrders_WEBUI_MERGED_ALL_STORES.csv")
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help="Output path. Defaults to <source>_v2.csv in the same directory.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"SQLite DB path for dim_kaspi_article_map lookup. Default: {DEFAULT_DB_PATH}",
    )
    parser.add_argument(
        "--historical-mapped-root",
        type=Path,
        default=None,
        help="Historical mapped-data root. Defaults to ../../Sales_archive/mapped_data relative to source.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    report = enrich_webui_sales_archive_with_sku_v2(
        source_csv=args.source_csv,
        output_csv=args.output_csv,
        db_path=args.db_path,
        historical_mapped_root=args.historical_mapped_root,
    )
    print(f"Source: {report['source_csv']}")
    print(f"Output: {report['output_csv']}")
    print(f"Rows: {report['rows_total']}")
    print(f"Resolved: {report['resolved_rows']}")
    print(f"Unresolved: {report['unresolved_rows']}")
    for method, count in sorted(report["method_counts"].items()):
        print(f"{method}: {count}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
