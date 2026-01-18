#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.paths import get_data_root


ATTR_KEYS = [
    "deliveryMode",
    "paymentMode",
    "express",
    "signatureRequired",
]


def _pick_detail(snapshot: dict[str, Any]) -> Optional[dict[str, Any]]:
    for key in ("by_id", "by_code"):
        detail = snapshot.get(key)
        if isinstance(detail, dict) and detail.get("success"):
            return detail
    for key in ("by_id", "by_code"):
        detail = snapshot.get(key)
        if isinstance(detail, dict):
            return detail
    return None


def _extract_attrs(detail: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not detail or not isinstance(detail, dict):
        return {}
    data = detail.get("data")
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        return data["data"].get("attributes", {}) or {}
    if isinstance(data, dict):
        return data.get("attributes", {}) or {}
    return {}


def _extract_waybill(attrs: dict[str, Any]) -> bool:
    try:
        kaspi_delivery = attrs.get("kaspiDelivery", {}) or {}
        return bool(kaspi_delivery.get("waybill"))
    except Exception:
        return False


def _attempt_by_label(attempts: list[dict[str, Any]], label_prefix: str) -> Optional[dict[str, Any]]:
    for attempt in attempts:
        label = str(attempt.get("label", ""))
        if label.startswith(label_prefix):
            return attempt
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize assemble_noop diagnostics into CSV + correlation markdown."
    )
    parser.add_argument("--date", help="Filter diagnostics by YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    target_date = args.date or datetime.now().strftime("%Y-%m-%d")
    data_root = get_data_root()
    diag_dir = data_root / "exports" / "diagnostics"
    diag_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for path in sorted(diag_dir.glob("assemble_noop_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        ts = str(payload.get("timestamp") or "")
        if ts and not ts.startswith(target_date):
            continue
        before = payload.get("before", {}) or {}
        after = payload.get("after", {}) or {}
        before_detail = _pick_detail(before) or {}
        after_detail = _pick_detail(after) or {}
        before_attrs = _extract_attrs(before_detail)
        after_attrs = _extract_attrs(after_detail)
        attempts = payload.get("attempts", []) or []

        primary_attempt = _attempt_by_label(attempts, "primary")
        fallback_attempt = _attempt_by_label(attempts, "fallback")

        result = payload.get("result", {}) or {}
        shipped = bool(result.get("shipped"))

        row = {
            "timestamp": payload.get("timestamp"),
            "store_code": payload.get("store_code"),
            "order_code": payload.get("order_code"),
            "planned_date": payload.get("planned_date"),
            "state_before": before_attrs.get("state"),
            "status_before": before_attrs.get("status"),
            "assembled_before": before_attrs.get("assembled"),
            "waybill_before": int(_extract_waybill(before_attrs)),
            "state_after": after_attrs.get("state"),
            "status_after": after_attrs.get("status"),
            "assembled_after": after_attrs.get("assembled"),
            "waybill_after": int(_extract_waybill(after_attrs)),
            "primary_status_code": (primary_attempt or {}).get("response", {}).get("status_code"),
            "primary_success": (primary_attempt or {}).get("response", {}).get("success"),
            "primary_error": (primary_attempt or {}).get("response", {}).get("error"),
            "primary_request_id": (primary_attempt or {}).get("response", {}).get("request_id"),
            "fallback_status_code": (fallback_attempt or {}).get("response", {}).get("status_code"),
            "fallback_success": (fallback_attempt or {}).get("response", {}).get("success"),
            "fallback_error": (fallback_attempt or {}).get("response", {}).get("error"),
            "fallback_request_id": (fallback_attempt or {}).get("response", {}).get("request_id"),
            "result_shipped": shipped,
            "result_error": result.get("error"),
        }
        for key in ATTR_KEYS:
            row[key] = before_attrs.get(key)
        rows.append(row)

    summary_path = diag_dir / f"assemble_summary_{target_date}.csv"
    fieldnames = [
        "timestamp",
        "store_code",
        "order_code",
        "planned_date",
        "state_before",
        "status_before",
        "assembled_before",
        "waybill_before",
        "state_after",
        "status_after",
        "assembled_after",
        "waybill_after",
        *ATTR_KEYS,
        "primary_status_code",
        "primary_success",
        "primary_error",
        "primary_request_id",
        "fallback_status_code",
        "fallback_success",
        "fallback_error",
        "fallback_request_id",
        "result_shipped",
        "result_error",
    ]

    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    total = len(rows)
    shipped_count = sum(1 for row in rows if row["result_shipped"])
    noop_count = total - shipped_count

    diff_lines = [
        f"# Assemble Attribute Diff ({target_date})",
        "",
        f"- Total records: {total}",
        f"- Shipped: {shipped_count}",
        f"- No-op / failed: {noop_count}",
        "",
    ]

    for key in ATTR_KEYS:
        buckets: dict[str, dict[str, int]] = defaultdict(lambda: {"shipped": 0, "noop": 0, "total": 0})
        for row in rows:
            value = row.get(key)
            value_label = "UNKNOWN" if value is None else str(value)
            buckets[value_label]["total"] += 1
            if row["result_shipped"]:
                buckets[value_label]["shipped"] += 1
            else:
                buckets[value_label]["noop"] += 1
        sorted_vals = sorted(
            buckets.items(),
            key=lambda item: (
                (item[1]["noop"] / item[1]["total"]) if item[1]["total"] else 0,
                item[1]["total"],
            ),
            reverse=True,
        )
        diff_lines.append(f"## {key}")
        diff_lines.append("")
        diff_lines.append("| value | shipped | no_op | no_op_rate | total |")
        diff_lines.append("| --- | --- | --- | --- | --- |")
        for value, stats in sorted_vals[:5]:
            rate = stats["noop"] / stats["total"] if stats["total"] else 0
            diff_lines.append(
                f"| {value} | {stats['shipped']} | {stats['noop']} | {rate:.2%} | {stats['total']} |"
            )
        diff_lines.append("")

    diff_path = diag_dir / f"assemble_attribute_diff_{target_date}.md"
    diff_path.write_text("\n".join(diff_lines), encoding="utf-8")

    print(f"Wrote {summary_path}")
    print(f"Wrote {diff_path}")


if __name__ == "__main__":
    main()
