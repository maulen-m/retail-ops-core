"""Approved manual warehouse stock count manifest helpers."""

from __future__ import annotations

import json
import csv
import argparse
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
APPROVED_MANIFEST_DIR = PROJECT_ROOT / "config" / "anchors" / "manual_stock_counts"
DEFAULT_MANIFEST_PATH = (
    APPROVED_MANIFEST_DIR
    / "astana_warehouse_manual_stock_count_2026_05_30_2026_06_02.approved.json"
)


class ManualStockCountManifestError(ValueError):
    """Raised when the approved manual count manifest is unsafe to consume."""


@dataclass(frozen=True)
class ManualStockAggregate:
    batch_id: str
    count_timestamp_at_almaty: str
    timestamp_folder: str
    stock_pool_id: str
    model_label: str
    sku_key: str
    sku_id: str
    applies_to_sku_ids: tuple[str, ...]
    canonical_size: str
    ocr_size_label: str
    color_or_pattern: str
    quantity: int
    source_images: tuple[str, ...]
    source_row_count: int
    counting_policy: str
    precedence_rank: int
    quarantine_returns_included: bool
    cancellation_units_included: bool


def load_approved_manual_stock_manifest(path: Path | None = None) -> dict[str, Any]:
    manifest_path = path or DEFAULT_MANIFEST_PATH
    with manifest_path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    validate_manual_stock_manifest(data)
    return data


def load_approved_manual_stock_manifests(paths: Iterable[Path] | None = None) -> list[dict[str, Any]]:
    manifest_paths = list(paths or sorted(APPROVED_MANIFEST_DIR.glob("*.approved.json")))
    return [load_approved_manual_stock_manifest(path) for path in manifest_paths]


def aggregate_manual_stock_counts(data: dict[str, Any]) -> list[ManualStockAggregate]:
    count_scope = data["count_scope"]
    precedence_rank = int(data["precedence"]["rank"])
    groups: dict[tuple[str, ...], dict[str, Any]] = {}

    for row in data["rows"]:
        key = (
            data["batch_id"],
            row["count_timestamp_at_almaty"],
            row["timestamp_folder"],
            row["stock_pool_id"],
            row["sku_key"],
            row["sku_id"],
            row["canonical_size"],
            row["color_or_pattern"],
        )
        if key not in groups:
            groups[key] = {
                "batch_id": data["batch_id"],
                "count_timestamp_at_almaty": row["count_timestamp_at_almaty"],
                "timestamp_folder": row["timestamp_folder"],
                "stock_pool_id": row["stock_pool_id"],
                "model_label": row["model_label"],
                "sku_key": row["sku_key"],
                "sku_id": row["sku_id"],
                "applies_to_sku_ids": tuple(row["applies_to_sku_ids"]),
                "canonical_size": row["canonical_size"],
                "ocr_size_label": row["ocr_size_label"],
                "color_or_pattern": row["color_or_pattern"],
                "quantity": 0,
                "source_images": [],
                "source_row_count": 0,
                "counting_policy": row["counting_policy"],
                "precedence_rank": precedence_rank,
                "quarantine_returns_included": bool(count_scope["quarantine_returns_included"]),
                "cancellation_units_included": bool(count_scope["cancellation_units_included"]),
            }

        group = groups[key]
        group["quantity"] += int(row["quantity"])
        group["source_images"].append(row["source_image"])
        group["source_row_count"] += 1

    aggregates: list[ManualStockAggregate] = []
    for group in groups.values():
        group["source_images"] = tuple(dict.fromkeys(group["source_images"]))
        aggregates.append(ManualStockAggregate(**group))
    return sorted(
        aggregates,
        key=lambda row: (
            row.count_timestamp_at_almaty,
            row.sku_key,
            row.canonical_size,
            row.color_or_pattern,
            row.stock_pool_id,
        ),
    )


def manual_stock_overrides_by_sku_id(data: dict[str, Any]) -> dict[str, ManualStockAggregate]:
    """Return latest approved override by sku_id, expanding shared-pool aliases.

    Shared-pool aliases deliberately point at the same aggregate quantity. Global
    inventory totals must group by stock_pool_id to avoid double counting aliases.
    """
    overrides: dict[str, ManualStockAggregate] = {}
    for aggregate in aggregate_manual_stock_counts(data):
        for sku_id in aggregate.applies_to_sku_ids:
            current = overrides.get(sku_id)
            if current is None or aggregate.count_timestamp_at_almaty > current.count_timestamp_at_almaty:
                overrides[sku_id] = aggregate
    return overrides


def latest_manual_stock_overrides_by_sku_id(
    manifests: Iterable[dict[str, Any]],
) -> dict[str, ManualStockAggregate]:
    """Return latest approved override by sku_id across multiple manifests."""
    overrides: dict[str, ManualStockAggregate] = {}
    for data in manifests:
        for aggregate in aggregate_manual_stock_counts(data):
            for sku_id in aggregate.applies_to_sku_ids:
                current = overrides.get(sku_id)
                if current is None:
                    overrides[sku_id] = aggregate
                    continue
                current_key = (current.count_timestamp_at_almaty, current.precedence_rank)
                candidate_key = (aggregate.count_timestamp_at_almaty, aggregate.precedence_rank)
                if candidate_key > current_key:
                    overrides[sku_id] = aggregate
    return overrides


def write_manual_stock_aggregate_csv(data: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "batch_id",
        "count_timestamp_at_almaty",
        "timestamp_folder",
        "location",
        "stock_pool_id",
        "model_label",
        "sku_key",
        "sku_id",
        "applies_to_sku_ids",
        "canonical_size",
        "ocr_size_label",
        "color_or_pattern",
        "quantity",
        "source_images",
        "source_row_count",
        "counting_policy",
        "quarantine_returns_included",
        "cancellation_units_included",
        "precedence_rank",
        "status",
    ]
    aggregates = aggregate_manual_stock_counts(data)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in aggregates:
            writer.writerow(
                {
                    "batch_id": row.batch_id,
                    "count_timestamp_at_almaty": row.count_timestamp_at_almaty,
                    "timestamp_folder": row.timestamp_folder,
                    "location": data["location"]["warehouse"],
                    "stock_pool_id": row.stock_pool_id,
                    "model_label": row.model_label,
                    "sku_key": row.sku_key,
                    "sku_id": row.sku_id,
                    "applies_to_sku_ids": ";".join(row.applies_to_sku_ids),
                    "canonical_size": row.canonical_size,
                    "ocr_size_label": row.ocr_size_label,
                    "color_or_pattern": row.color_or_pattern,
                    "quantity": row.quantity,
                    "source_images": ";".join(row.source_images),
                    "source_row_count": row.source_row_count,
                    "counting_policy": row.counting_policy,
                    "quarantine_returns_included": str(row.quarantine_returns_included).lower(),
                    "cancellation_units_included": str(row.cancellation_units_included).lower(),
                    "precedence_rank": row.precedence_rank,
                    "status": data["status"],
                }
            )


def validate_manual_stock_manifest(data: dict[str, Any]) -> None:
    errors: list[str] = []

    if data.get("schema_version") != "manual_warehouse_stock_count_manifest_v1":
        errors.append("unexpected schema_version")
    if data.get("status") != "OWNER_APPROVED":
        errors.append("manifest status must be OWNER_APPROVED")

    count_scope = data.get("count_scope") or {}
    if count_scope.get("quarantine_returns_included") is not False:
        errors.append("quarantine_returns_included must be false")
    if count_scope.get("cancellation_units_included") is not False:
        errors.append("cancellation_units_included must be false")
    if "do_not_infer_zero" not in str(count_scope.get("missing_size_policy", "")):
        errors.append("missing_size_policy must forbid inferring zero for absent sizes")

    rows = data.get("rows") or []
    expected = data.get("expected_totals") or {}
    if len(rows) != int(expected.get("raw_row_count", -1)):
        errors.append(f"raw row count mismatch: {len(rows)} != {expected.get('raw_row_count')}")

    row_ids: set[str] = set()
    raw_total = 0
    folder_totals: dict[str, int] = defaultdict(int)
    product_totals: dict[str, int] = defaultdict(int)
    correction_hits: dict[str, bool] = {
        str(idx): False for idx, _correction in enumerate(data.get("known_corrections") or [], start=1)
    }

    for row in rows:
        row_id = str(row.get("row_id", ""))
        if not row_id:
            errors.append("row missing row_id")
        if row_id in row_ids:
            errors.append(f"duplicate row_id: {row_id}")
        row_ids.add(row_id)

        try:
            quantity = int(row["quantity"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"row {row_id} has invalid quantity")
            continue
        if quantity < 0:
            errors.append(f"row {row_id} has negative quantity")
        raw_total += quantity
        folder_totals[str(row.get("timestamp_folder", ""))] += quantity
        product_totals[str(row.get("model_label", ""))] += quantity

        if not row.get("sku_key") or not row.get("sku_id"):
            errors.append(f"row {row_id} missing sku_key/sku_id")
        applies_to = row.get("applies_to_sku_ids") or []
        if not isinstance(applies_to, list) or not applies_to:
            errors.append(f"row {row_id} missing applies_to_sku_ids")

        for idx, correction in enumerate(data.get("known_corrections") or [], start=1):
            if (
                row.get("source_image") == correction.get("source_image")
                and row.get("model_label") == correction.get("model_label")
                and row.get("canonical_size") == correction.get("canonical_size")
                and quantity == int(correction.get("correct_value", -1))
            ):
                correction_hits[str(idx)] = True

    for idx, seen in correction_hits.items():
        if not seen:
            errors.append(f"known correction {idx} is not represented by a matching row")

    if raw_total != int(expected.get("total_units", -1)):
        errors.append(f"total unit mismatch: {raw_total} != {expected.get('total_units')}")

    for folder, expected_qty in (expected.get("folder_totals") or {}).items():
        if folder_totals.get(folder, 0) != int(expected_qty):
            errors.append(f"folder total mismatch for {folder}: {folder_totals.get(folder, 0)} != {expected_qty}")

    for product, expected_qty in (expected.get("product_totals") or {}).items():
        if product_totals.get(product, 0) != int(expected_qty):
            errors.append(f"product total mismatch for {product}: {product_totals.get(product, 0)} != {expected_qty}")

    aggregates = aggregate_manual_stock_counts(data) if rows else []
    if len(aggregates) != int(expected.get("aggregate_stock_pool_row_count", -1)):
        errors.append(
            f"aggregate row count mismatch: {len(aggregates)} != {expected.get('aggregate_stock_pool_row_count')}"
        )
    aggregate_total = sum(row.quantity for row in aggregates)
    if aggregate_total != int(expected.get("total_units", -1)):
        errors.append(f"aggregate total mismatch: {aggregate_total} != {expected.get('total_units')}")

    if errors:
        raise ManualStockCountManifestError("; ".join(errors))


def _summary_lines(aggregates: Iterable[ManualStockAggregate]) -> list[str]:
    rows = list(aggregates)
    return [
        f"aggregate_rows={len(rows)}",
        f"total_units={sum(row.quantity for row in rows)}",
        "quarantine_returns_included=false",
        "cancellation_units_included=false",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate approved manual stock count manifests")
    parser.add_argument("--manifest", action="append", type=Path, help="Manifest path to validate; may repeat")
    parser.add_argument("--all", action="store_true", help="Validate all approved manifests in the anchor directory")
    parser.add_argument("--write-aggregate-csv", type=Path, help="Write aggregate CSV for a single manifest")
    args = parser.parse_args()

    if args.all:
        data_set = load_approved_manual_stock_manifests()
    elif args.manifest:
        data_set = [load_approved_manual_stock_manifest(path) for path in args.manifest]
    else:
        data_set = [load_approved_manual_stock_manifest()]

    if args.write_aggregate_csv:
        if len(data_set) != 1:
            raise ManualStockCountManifestError("--write-aggregate-csv requires exactly one manifest")
        write_manual_stock_aggregate_csv(data_set[0], args.write_aggregate_csv)

    for data in data_set:
        print(f"batch_id={data['batch_id']}")
        for line in _summary_lines(aggregate_manual_stock_counts(data)):
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
