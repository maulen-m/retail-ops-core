#!/usr/bin/env python3
"""Read-only physical handover checker for daily waybill operations."""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.kaspi_api_client import KaspiAPIClient  # noqa: E402
from core.integrations.kaspi_order_stage import StageCode, classify_kaspi_order_stage  # noqa: E402
from core.utils.kaspi_dates import planned_date_from_order  # noqa: E402
from scripts.returns_pickup_report import format_table  # noqa: E402


ALMATY_TZ = ZoneInfo("Asia/Almaty")
DEFAULT_LEDGER_ROOTS = [PROJECT_ROOT / "excel_ui" / "Kaspi_orders"]
STORE_DISPLAY = {
    "ACMEWEAR": "AcmeWear",
    "UNIVERSAL": "Universal",
    "STOREB": "STORE-B",
    "11KZ": "11KZ",
    "MELVIS": "Store-C",
}


def _now() -> datetime:
    return datetime.now(ALMATY_TZ)


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() not in {"", "0", "false", "no", "n", "none", "null"}


def _load_env_file(path: Path = PROJECT_ROOT / ".env") -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip("'").strip('"')


def _parse_target_date(value: Any) -> date | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _store_display(store_code: str) -> str:
    return STORE_DISPLAY.get(_clean(store_code).upper(), _clean(store_code) or "UNKNOWN")


def _attrs(order: Mapping[str, Any]) -> Mapping[str, Any]:
    attrs = order.get("attributes")
    return attrs if isinstance(attrs, Mapping) else order


def _delivery_attrs(order: Mapping[str, Any]) -> Mapping[str, Any]:
    attrs = _attrs(order)
    delivery = attrs.get("kaspiDelivery") or attrs.get("delivery") or {}
    return delivery if isinstance(delivery, Mapping) else {}


def _order_id(order: Mapping[str, Any]) -> str:
    attrs = _attrs(order)
    return _clean(attrs.get("code") or order.get("code") or attrs.get("orderCode") or order.get("order_id"))


def _courier_transmission_value(order: Mapping[str, Any]) -> str:
    attrs = _attrs(order)
    delivery = _delivery_attrs(order)
    return _clean(
        delivery.get("courierTransmissionDate")
        or attrs.get("courierTransmissionDate")
        or attrs.get("actualShipmentDate")
    )


def _is_pending_physical_handover(order: Mapping[str, Any]) -> bool:
    if classify_kaspi_order_stage(order) != StageCode.ASSEMBLED_PENDING_HANDOVER:
        return False
    return not _truthy(_courier_transmission_value(order))


def _resolve_store_codes(explicit: Iterable[str] | None = None) -> list[str]:
    if explicit:
        return [str(item).strip().upper() for item in explicit if str(item).strip()]
    env_value = os.environ.get("WAYBILL_HANDOVER_STORE_CODES", "").strip()
    if env_value:
        return [item.strip().upper() for item in env_value.split(",") if item.strip()]

    config_path = PROJECT_ROOT / "config" / "kaspi_stores.yaml"
    if config_path.exists():
        try:
            import yaml

            payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            configured = list(((payload.get("settings") or {}).get("required_fresh_stores")) or [])
            if configured:
                return [str(item).strip().upper() for item in configured if str(item).strip()]
        except Exception:
            pass
    return ["UNIVERSAL", "STOREB", "ACMEWEAR"]


def build_telegram_confirmation_index(ledger_roots: Iterable[Path] | None = None) -> dict[str, dict[str, Any]]:
    """Index confirmed Telegram ledger entries by order ID."""
    roots = [Path(root) for root in (ledger_roots or DEFAULT_LEDGER_ROOTS)]
    index: dict[str, dict[str, Any]] = {}
    for root in roots:
        if not root.exists():
            continue
        ledger_paths = [root] if root.name == "telegram_send_ledger.json" else sorted(root.rglob("telegram_send_ledger.json"))
        for ledger_path in ledger_paths:
            try:
                payload = json.loads(ledger_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            batch_label = _clean(payload.get("batch_label"))
            for pdf_key, entry_raw in dict(payload.get("entries") or {}).items():
                entry = dict(entry_raw or {})
                order_ids = [_clean(value) for value in list(entry.get("order_ids") or []) if _clean(value)]
                for order_id in order_ids:
                    existing = index.get(order_id) or {}
                    existing_message = _clean(existing.get("telegram_message_id"))
                    message_id = _clean(entry.get("telegram_message_id"))
                    if existing and existing_message and message_id and existing_message > message_id:
                        continue
                    index[order_id] = {
                        "telegram_state": _clean(entry.get("state")),
                        "telegram_message_id": message_id,
                        "telegram_filename": _clean(entry.get("filename")),
                        "telegram_batch_label": batch_label,
                        "telegram_ledger_path": str(ledger_path),
                        "pdf_key": str(pdf_key),
                    }
    return index


def _format_day(value: date | None) -> str:
    return value.isoformat() if value else ""


def build_handover_report_from_orders(
    *,
    target_date: date,
    store_orders_by_code: Mapping[str, list[Mapping[str, Any]]],
    ledger_roots: Iterable[Path] | None = None,
    lookback_days: int = 7,
    now: datetime | None = None,
    api_errors: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build a deterministic report from already-fetched Kaspi orders."""
    local_now = now or _now()
    if local_now.tzinfo is None:
        local_now = local_now.replace(tzinfo=ALMATY_TZ)
    min_date = target_date - timedelta(days=max(0, int(lookback_days)))
    telegram_index = build_telegram_confirmation_index(ledger_roots)
    pending_rows: list[dict[str, Any]] = []
    scanned = 0
    unknown_planned = 0

    for store_code, orders in store_orders_by_code.items():
        display = _store_display(store_code)
        for order in orders:
            scanned += 1
            order_id = _order_id(order)
            if not order_id or not _is_pending_physical_handover(order):
                continue
            planned = planned_date_from_order(dict(order), store_code=store_code)
            if planned is None:
                unknown_planned += 1
            elif planned > target_date or planned < min_date:
                continue
            telegram = telegram_index.get(order_id) or {}
            pending_rows.append(
                {
                    "store_code": _clean(store_code).upper(),
                    "store": display,
                    "order_id": order_id,
                    "planned_date": _format_day(planned),
                    "delay_days": "" if planned is None else str(max(0, (target_date - planned).days)),
                    "telegram_state": _clean(telegram.get("telegram_state")),
                    "telegram_message_id": _clean(telegram.get("telegram_message_id")),
                    "telegram_filename": _clean(telegram.get("telegram_filename")),
                    "telegram_batch_label": _clean(telegram.get("telegram_batch_label")),
                    "telegram_ledger_path": _clean(telegram.get("telegram_ledger_path")),
                }
            )

    pending_rows.sort(
        key=lambda row: (
            row["planned_date"] or "9999-99-99",
            row["store"],
            row["order_id"],
        )
    )
    by_store_counter = Counter(row["store"] for row in pending_rows)
    by_store = {store: int(by_store_counter[store]) for store in sorted(by_store_counter)}
    errors = {str(key): str(value) for key, value in dict(api_errors or {}).items() if str(value)}
    status = "PHYSICAL_HANDOVER_COMPLETE"
    ok = True
    if errors:
        status = "PHYSICAL_HANDOVER_CHECK_ERROR"
        ok = False
    if pending_rows:
        status = "PHYSICAL_HANDOVER_PENDING"
        ok = False
    return {
        "ok": ok,
        "status": status,
        "target_date": target_date.isoformat(),
        "lookback_days": int(lookback_days),
        "as_of": local_now.isoformat(),
        "scanned_orders": scanned,
        "pending_count": len(pending_rows),
        "unknown_planned_pending_count": unknown_planned,
        "by_store": by_store,
        "pending_orders": pending_rows,
        "api_errors": errors,
    }


def _fetch_store_awaiting_handover_orders(
    *,
    store_code: str,
    since: date,
) -> list[dict[str, Any]]:
    client = KaspiAPIClient(store_code=store_code)
    return client.list_all_orders(
        state="KASPI_DELIVERY",
        status="ACCEPTED_BY_MERCHANT",
        since=since.isoformat(),
        include_orders="user",
    )


def build_waybill_handover_report(
    *,
    target_date: date | None = None,
    lookback_days: int = 7,
    store_codes: Iterable[str] | None = None,
    ledger_roots: Iterable[Path] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Fetch current Kaspi API state and report pending physical handover rows."""
    _load_env_file()
    local_now = now or _now()
    resolved_target = target_date or local_now.date()
    since = resolved_target - timedelta(days=max(1, int(lookback_days)))
    resolved_stores = _resolve_store_codes(store_codes)
    store_orders: dict[str, list[Mapping[str, Any]]] = {}
    api_errors: dict[str, str] = {}
    for store_code in resolved_stores:
        try:
            store_orders[store_code] = _fetch_store_awaiting_handover_orders(store_code=store_code, since=since)
        except Exception as exc:
            api_errors[store_code] = str(exc)
            store_orders[store_code] = []
    return build_handover_report_from_orders(
        target_date=resolved_target,
        store_orders_by_code=store_orders,
        ledger_roots=ledger_roots,
        lookback_days=lookback_days,
        now=local_now,
        api_errors=api_errors,
    )


def format_handover_status_message(report: Mapping[str, Any]) -> str:
    status = _clean(report.get("status")) or "PHYSICAL_HANDOVER_UNKNOWN"
    as_of = _clean(report.get("as_of")).replace("T", " ")[:19]
    pending_count = int(report.get("pending_count") or 0)
    target_date = _clean(report.get("target_date"))
    lines = [
        "<b>Physical Courier Handover Check</b>",
        f"Gate: <code>{html.escape(status)}</code>",
        f"Target date: <code>{html.escape(target_date)}</code> | As of: <code>{html.escape(as_of)}</code>",
    ]
    errors = dict(report.get("api_errors") or {})
    if errors:
        lines.append("API errors: <code>" + html.escape(json.dumps(errors, ensure_ascii=False)[:1200]) + "</code>")

    if pending_count <= 0 and not errors:
        lines.append("No assembled orders are still waiting in Kaspi Передача for the checked window.")
        return "\n".join(lines)

    lines.append(f"Pending handover rows: <code>{pending_count}</code>")
    rows = []
    for row in list(report.get("pending_orders") or [])[:40]:
        telegram = _clean(row.get("telegram_message_id"))
        telegram_state = _clean(row.get("telegram_state")) or "-"
        tg_cell = f"{telegram_state}:{telegram}" if telegram else telegram_state
        rows.append(
            [
                _clean(row.get("store")),
                _clean(row.get("planned_date")) or "-",
                _clean(row.get("delay_days")) or "-",
                _clean(row.get("order_id")),
                tg_cell,
            ]
        )
    if rows:
        lines.append("<pre>" + html.escape(format_table(["STORE", "PLANNED", "DELAY", "ORDER_ID", "TG"], rows)) + "</pre>")
    remaining = pending_count - len(rows)
    if remaining > 0:
        lines.append(f"... and <code>{remaining}</code> more pending rows.")
    lines.append("If parcels were just handed over, wait about one minute and press <code>Передал курьеру</code> again.")
    return "\n".join(lines)


def _parse_report_day(value: Any) -> date | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _format_as_of_minute(value: Any) -> str:
    text = _clean(value)
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return text.replace("T", " ")[:16]
    return parsed.astimezone(ALMATY_TZ).strftime("%H:%M")


def _format_order_id_list(order_ids: list[str], *, limit: int = 8) -> str:
    visible = [html.escape(order_id) for order_id in order_ids[:limit]]
    suffix = f" +{len(order_ids) - limit}" if len(order_ids) > limit else ""
    return "<code>" + ", ".join(visible) + html.escape(suffix) + "</code>"


def format_handover_compact_status_message(report: Mapping[str, Any]) -> str:
    """Compact employee-facing handover status for Telegram chat."""
    status = _clean(report.get("status")) or "PHYSICAL_HANDOVER_UNKNOWN"
    as_of = _format_as_of_minute(report.get("as_of"))
    pending_count = int(report.get("pending_count") or 0)
    target_date = _parse_report_day(report.get("target_date"))
    errors = dict(report.get("api_errors") or {})

    if pending_count <= 0 and not errors:
        suffix = f" | <code>{html.escape(as_of)}</code>" if as_of else ""
        return "Передача: OK" + suffix + "\nNo pending parcels in Kaspi Передача."

    rows = [dict(row) for row in list(report.get("pending_orders") or [])]
    overdue_rows: list[dict[str, Any]] = []
    today_rows = 0
    unknown_rows = 0
    for row in rows:
        planned = _parse_report_day(row.get("planned_date"))
        if target_date and planned and planned < target_date:
            overdue_rows.append(row)
        elif target_date and planned == target_date:
            today_rows += 1
        else:
            unknown_rows += 1
    overdue_count = len(overdue_rows)
    if not rows:
        overdue_count = 0
        today_rows = pending_count

    lines = [
        "Передача: НЕ ЗАКРЫТО",
        (
            f"pending: <code>{pending_count}</code> | "
            f"overdue: <code>{overdue_count}</code> | "
            f"today: <code>{today_rows}</code>"
            + (f" | unknown: <code>{unknown_rows}</code>" if unknown_rows else "")
            + (f" | <code>{html.escape(as_of)}</code>" if as_of else "")
        ),
    ]
    by_store = dict(report.get("by_store") or {})
    if by_store:
        lines.append(
            " | ".join(
                f"{html.escape(str(store))}: <code>{int(count)}</code>"
                for store, count in sorted(by_store.items())
            )
        )
    if errors:
        lines.append("API errors: <code>" + html.escape(json.dumps(errors, ensure_ascii=False)[:500]) + "</code>")

    if overdue_rows:
        lines.append("")
        lines.append("Overdue to ship today:")
        by_overdue_store: dict[str, list[str]] = {}
        for row in overdue_rows:
            store = _clean(row.get("store")) or "UNKNOWN"
            order_id = _clean(row.get("order_id"))
            if order_id:
                by_overdue_store.setdefault(store, []).append(order_id)
        for store, order_ids in sorted(by_overdue_store.items()):
            lines.append(f"{html.escape(store)}: {_format_order_id_list(order_ids)}")

    lines.append("")
    lines.append("Full list: <code>/hfull</code>")
    lines.append("After handover: <code>Передал курьеру</code>")
    return "\n".join(lines)


def _parse_iso_date(value: str) -> date:
    parsed = _parse_target_date(value)
    if parsed is None:
        raise argparse.ArgumentTypeError(f"Invalid ISO date: {value!r}")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Kaspi physical courier handover state after waybill delivery")
    parser.add_argument("--target-date", type=_parse_iso_date, default=None)
    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument("--store", action="append", dest="stores", default=None)
    parser.add_argument("--ledger-root", action="append", type=Path, default=None)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)

    report = build_waybill_handover_report(
        target_date=args.target_date,
        lookback_days=args.lookback_days,
        store_codes=args.stores,
        ledger_roots=args.ledger_root,
    )
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(format_handover_status_message(report))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
