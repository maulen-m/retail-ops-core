#!/usr/bin/env python3
"""
Run A/B experiment for Kaspi X-Merchant-Uid header.

Captures before/after order states, response status/headers, and request headers
with tokens redacted. Outputs JSONL + CSV + summary MD to exports/diagnostics.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, date
from pathlib import Path
from typing import Any, Optional

from core.integrations.kaspi_api_client import (
    KaspiAPIClient,
    APIResponse,
    _get_store_merchant_uid,
)
from core.utils.kaspi_dates import planned_date_from_order, ALMATY_TZ


REQUEST_ID_KEYS = {
    "x-request-id",
    "x-requestid",
    "x-correlation-id",
    "x-trace-id",
    "x-amzn-trace-id",
}


def _sanitize_headers(headers: dict[str, Any]) -> dict[str, Any]:
    sanitized = {}
    for key, value in (headers or {}).items():
        low = key.lower()
        if low in {"authorization", "x-auth-token", "cookie", "set-cookie"}:
            sanitized[key] = "[REDACTED]"
        else:
            sanitized[key] = value
    return sanitized


def _response_to_dict(response: Optional[APIResponse]) -> Optional[dict[str, Any]]:
    if response is None:
        return None
    raw = response.raw_response
    resp_headers = {}
    req_headers = {}
    request_info = {}
    request_id = None
    if raw is not None:
        resp_headers = _sanitize_headers(dict(raw.headers))
        if raw.request is not None:
            req_headers = _sanitize_headers(dict(raw.request.headers))
            request_info = {
                "method": raw.request.method,
                "url": raw.request.url,
            }
        for key, value in resp_headers.items():
            if key.lower() in REQUEST_ID_KEYS:
                request_id = value
                break
    return {
        "success": response.success,
        "status_code": response.status_code,
        "error": response.error,
        "data": response.data,
        "headers": resp_headers,
        "request_headers": req_headers,
        "request": request_info,
        "request_id": request_id,
    }


def _extract_attrs(detail: Optional[APIResponse]) -> dict[str, Any]:
    if not detail or not detail.success:
        return {}
    data = detail.data
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        return data["data"].get("attributes", {}) or {}
    if isinstance(data, dict):
        return data.get("attributes", {}) or {}
    return {}


def _extract_attrs_from_response_dict(resp: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(resp, dict):
        return {}
    data = resp.get("data")
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        return data["data"].get("attributes", {}) or {}
    if isinstance(data, dict):
        return data.get("attributes", {}) or {}
    return {}


def _redact_order_data(order: dict[str, Any]) -> dict[str, Any]:
    redacted = deepcopy(order)
    attrs = redacted.get("attributes")
    if isinstance(attrs, dict):
        if "customer" in attrs:
            attrs["customer"] = {"redacted": True}
        for key in ("deliveryAddress", "billingAddress", "buyer", "receiver", "phone"):
            if key in attrs:
                attrs[key] = "[REDACTED]"
        delivery = attrs.get("kaspiDelivery")
        if isinstance(delivery, dict):
            for key in ("address", "customer", "receiver", "contact", "phone"):
                if key in delivery:
                    delivery[key] = "[REDACTED]"
    return redacted


def _snapshot(client: KaspiAPIClient, order_code: str, base64_id: Optional[str]) -> dict[str, Any]:
    snap: dict[str, Any] = {"at": datetime.now(ALMATY_TZ).isoformat()}
    if base64_id:
        try:
            detail = client.get_order_by_id(base64_id)
            snap["by_id"] = _response_to_dict(detail)
        except Exception as exc:  # pragma: no cover - best effort
            snap["by_id_error"] = str(exc)
    try:
        detail = client.get_order(order_code)
        snap["by_code"] = _response_to_dict(detail)
    except Exception as exc:  # pragma: no cover - best effort
        snap["by_code_error"] = str(exc)
    return snap


def _resolve_uid(store_code: str, override: Optional[str]) -> Optional[str]:
    if override:
        return override
    env_key = f"KASPI_MERCHANT_UID_{store_code.upper()}"
    env_val = os.environ.get(env_key) or os.environ.get("KASPI_MERCHANT_UID_OVERRIDE")
    if env_val:
        return env_val
    return _get_store_merchant_uid(store_code.upper())


def _select_orders(
    client: KaspiAPIClient,
    target_date: date,
    limit: int,
    order_codes: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    if order_codes:
        result = []
        for code in order_codes:
            detail = client.get_order(code)
            if detail.success and isinstance(detail.data, dict):
                order_obj = detail.data.get("data")
                if isinstance(order_obj, dict):
                    result.append(order_obj)
        return result

    pending = client.get_pending_assembly_orders()
    if not pending.success:
        raise SystemExit(f"Failed to fetch pending orders: {pending.error}")
    orders = []
    for order in pending.data.get("data", []):
        planned = planned_date_from_order(order)
        if planned and planned == target_date:
            orders.append(order)
        if len(orders) >= limit:
            break
    return orders


def _run_experiment(
    store_code: str,
    orders: list[dict[str, Any]],
    target_date: date,
    send_uid: bool,
    merchant_uid: Optional[str],
    label: str,
    output: list[dict[str, Any]],
):
    client = KaspiAPIClient(
        store_code=store_code,
        send_merchant_uid=send_uid,
        merchant_uid=merchant_uid,
    )
    for order in orders:
        attrs = order.get("attributes", {}) or {}
        order_code = attrs.get("code", "")
        base64_id = order.get("id", "")
        before = _snapshot(client, order_code, base64_id)
        assemble_payload = {
            "data": {
                "type": "orders",
                "attributes": {
                    "status": "ASSEMBLE",
                    "numberOfSpace": 1,
                    "code": order_code,
                },
            }
        }
        assemble_resp = client.assemble_order_by_id(base64_id, order_code, 1)
        after = _snapshot(client, order_code, base64_id)
        output.append(
            {
                "timestamp": datetime.now(ALMATY_TZ).isoformat(),
                "run_label": label,
                "store_code": store_code,
                "order_code": order_code,
                "base64_id": base64_id,
                "target_date": target_date.isoformat(),
                "merchant_uid_sent": bool(send_uid and merchant_uid),
                "merchant_uid": merchant_uid if send_uid else None,
                "before": _redact_order_data(before),
                "after": _redact_order_data(after),
                "assemble_response": _response_to_dict(assemble_resp),
                "assemble_payload": assemble_payload,
                "attrs_before": _extract_attrs_from_response_dict(before.get("by_code")) if isinstance(before, dict) else {},
                "attrs_after": _extract_attrs_from_response_dict(after.get("by_code")) if isinstance(after, dict) else {},
            }
        )


def _write_outputs(records: list[dict[str, Any]], diag_dir: Path, ts: str) -> dict[str, Path]:
    jsonl_path = diag_dir / f"xmerchantuid_{ts}_requests.jsonl"
    csv_path = diag_dir / f"xmerchantuid_{ts}_results.csv"
    summary_path = diag_dir / f"xmerchantuid_{ts}_summary.md"

    with jsonl_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    fieldnames = [
        "run_label",
        "store_code",
        "order_code",
        "merchant_uid_sent",
        "status_before",
        "assembled_before",
        "waybill_before",
        "status_after",
        "assembled_after",
        "waybill_after",
        "assemble_status_code",
        "assemble_request_id",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            before_attrs = record.get("attrs_before", {}) or {}
            after_attrs = record.get("attrs_after", {}) or {}
            assemble_resp = record.get("assemble_response") or {}
            row = {
                "run_label": record.get("run_label"),
                "store_code": record.get("store_code"),
                "order_code": record.get("order_code"),
                "merchant_uid_sent": record.get("merchant_uid_sent"),
                "status_before": before_attrs.get("status"),
                "assembled_before": before_attrs.get("assembled"),
                "waybill_before": (before_attrs.get("kaspiDelivery") or {}).get("waybill"),
                "status_after": after_attrs.get("status"),
                "assembled_after": after_attrs.get("assembled"),
                "waybill_after": (after_attrs.get("kaspiDelivery") or {}).get("waybill"),
                "assemble_status_code": assemble_resp.get("status_code"),
                "assemble_request_id": assemble_resp.get("request_id"),
            }
            writer.writerow(row)

    lines = [
        "# X-Merchant-Uid experiment summary",
        "",
        f"- Records: {len(records)}",
        f"- Results CSV: `{csv_path}`",
        f"- JSONL: `{jsonl_path}`",
    ]
    summary_path.write_text("\n".join(lines), encoding="utf-8")

    return {"jsonl": jsonl_path, "csv": csv_path, "summary": summary_path}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Kaspi X-Merchant-Uid A/B experiment (assemble)."
    )
    parser.add_argument("--store", required=True, help="Primary store code (e.g., UNIVERSAL)")
    parser.add_argument("--date", required=True, help="Target date YYYY-MM-DD")
    parser.add_argument("--merchant-uid", help="Merchant UID override (optional)")
    parser.add_argument("--limit", type=int, default=10, help="Max orders per store")
    parser.add_argument("--orders", nargs="*", help="Explicit order codes (optional)")
    parser.add_argument("--control-store", help="Control store code (optional)")
    parser.add_argument("--control-orders", nargs="*", help="Control order codes (optional)")

    args = parser.parse_args()

    target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    store_code = args.store.upper()
    merchant_uid = _resolve_uid(store_code, args.merchant_uid)
    if not merchant_uid:
        raise SystemExit("Merchant UID is required for header test. Provide --merchant-uid or env/config value.")

    diag_dir = Path(__file__).resolve().parents[1] / "exports" / "diagnostics"
    diag_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(ALMATY_TZ).strftime("%Y%m%d_%H%M%S")

    records: list[dict[str, Any]] = []

    base_client = KaspiAPIClient(store_code=store_code)
    primary_orders = _select_orders(
        base_client,
        target_date=target_date,
        limit=args.limit,
        order_codes=args.orders,
    )

    _run_experiment(
        store_code=store_code,
        orders=primary_orders,
        target_date=target_date,
        send_uid=False,
        merchant_uid=merchant_uid,
        label="no_header",
        output=records,
    )

    _run_experiment(
        store_code=store_code,
        orders=primary_orders,
        target_date=target_date,
        send_uid=True,
        merchant_uid=merchant_uid,
        label="with_header",
        output=records,
    )

    if args.control_store:
        control_store = args.control_store.upper()
        control_uid = _resolve_uid(control_store, None)
        control_client = KaspiAPIClient(store_code=control_store)
        control_orders = _select_orders(
            control_client,
            target_date=target_date,
            limit=args.limit,
            order_codes=args.control_orders,
        )
        _run_experiment(
            store_code=control_store,
            orders=control_orders,
            target_date=target_date,
            send_uid=False,
            merchant_uid=control_uid,
            label="no_header",
            output=records,
        )
        _run_experiment(
            store_code=control_store,
            orders=control_orders,
            target_date=target_date,
            send_uid=True,
            merchant_uid=control_uid,
            label="with_header",
            output=records,
        )

    paths = _write_outputs(records, diag_dir, ts)
    print("Wrote:")
    for key, path in paths.items():
        print(f"  {key}: {path}")


if __name__ == "__main__":
    main()
