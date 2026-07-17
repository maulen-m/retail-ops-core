"""Durable cross-day obligations for the employee waybill workflow.

An order becomes an unresolved shipping obligation when fresh Kaspi truth says it is
still waiting for assembly or physical courier handover.  The obligation has no age
expiry.  It is discharged only by explicit physical-handover or terminal source truth;
an API error, absence, or malformed response retains the obligation and blocks the
current closeout rather than silently dropping the order.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.alerts.ops_alert_outbox import enqueue_alert
from core.integrations.kaspi_order_stage import StageCode, classify_kaspi_order_stage


SCHEMA_VERSION = 1
REQUIRED_ORDERS_SCHEMA_VERSION = 3
STATUS_UNRESOLVED = "unresolved"
STATUS_SUSPENDED = "suspended"
STATUS_DISCHARGED = "discharged"
OPEN_STATUSES = {STATUS_UNRESOLVED, STATUS_SUSPENDED}
ALL_STATUSES = {STATUS_UNRESOLVED, STATUS_SUSPENDED, STATUS_DISCHARGED}
KNOWN_STORE_CODES = {"UNIVERSAL", "ACMEWEAR", "STOREB", "11KZ", "MELVIS"}
PACKABLE_STAGES = {
    StageCode.ACCEPTED_PENDING_ASSEMBLY,
    StageCode.ASSEMBLED_PENDING_HANDOVER,
}
TRANSITIONAL_NO_PACK_STAGES = {
    StageCode.CANCELLING,
    StageCode.RETURN_REQUESTED,
}
DISCHARGE_STAGES = {
    StageCode.IN_DELIVERY,
    StageCode.ISSUED_COMPLETED,
    StageCode.CANCELLED,
    StageCode.RETURNED,
}


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def normalize_store_code(value: Any) -> str:
    raw = _clean(value).upper().replace(" ", "")
    aliases = {
        "STORE-B": "STOREB",
        "STORE_B": "STOREB",
        "30137883_PP1": "ACMEWEAR",
        "30000001_PP1": "UNIVERSAL",
        "30290083_PP1": "11KZ",
        "30000002_PP1": "STOREB",
        "30362323_PP1": "MELVIS",
        "PP1": "ACMEWEAR",
        "PP2": "ACMEWEAR",
    }
    return aliases.get(raw, raw)


def obligation_key(store_code: Any, order_id: Any) -> str:
    store = normalize_store_code(store_code)
    order = _clean(order_id)
    if not store or not order:
        raise ValueError("shipping obligation requires store_code and order_id")
    return f"{store}:{order}"


def normalize_required_line(
    raw_line: Mapping[str, Any],
    *,
    default_store_code: Any = "",
    default_order_id: Any = "",
) -> dict[str, Any]:
    """Normalize one immutable DB line/size identity for hashing and comparison."""
    quantity_raw = raw_line.get("quantity")
    try:
        quantity = int(quantity_raw if quantity_raw is not None else 1)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"required line has invalid quantity={quantity_raw!r}") from exc
    line = {
        "db_row_id": _clean(raw_line.get("db_row_id") or raw_line.get("source_row_id")),
        "store_code": normalize_store_code(
            raw_line.get("store_code") or default_store_code
        ),
        "order_id": _clean(raw_line.get("order_id") or default_order_id),
        "sku_key": _clean(raw_line.get("sku_key")),
        "sku_id": _clean(raw_line.get("sku_id")),
        "kaspi_offer_name": _clean(raw_line.get("kaspi_offer_name")),
        "kaspi_name_core": _clean(raw_line.get("kaspi_name_core")),
        "quantity": quantity,
        "final_size": _clean(raw_line.get("final_size") or raw_line.get("my_size")),
    }
    missing = [
        key
        for key in ("db_row_id", "store_code", "order_id", "final_size")
        if not line[key]
    ]
    if missing:
        raise ValueError("required line is missing " + ",".join(missing))
    if not any(line[field] for field in ("sku_key", "sku_id", "kaspi_offer_name")):
        raise ValueError("required line is missing product identity")
    if not line["kaspi_name_core"] or line["kaspi_name_core"].lower() == "unknown":
        raise ValueError("required line is missing resolved kaspi_name_core")
    if quantity <= 0:
        raise ValueError("required line quantity must be positive")
    return line


def required_line_scope_hash(lines: Iterable[Mapping[str, Any]]) -> str:
    """Hash an exact, duplicate-free set of DB line identities and final sizes."""
    normalized: list[dict[str, Any]] = []
    seen_row_ids: set[str] = set()
    for raw_line in lines:
        line = normalize_required_line(raw_line)
        row_id = line["db_row_id"]
        if row_id in seen_row_ids:
            raise ValueError(f"required line scope has duplicate db_row_id={row_id}")
        seen_row_ids.add(row_id)
        normalized.append(line)
    normalized.sort(
        key=lambda item: (
            item["store_code"],
            item["order_id"],
            item["db_row_id"],
        )
    )
    return hashlib.sha256(
        json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def empty_shipping_obligation_ledger() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "updated_at": None,
        "request_identity": {},
        "entries": {},
    }


def load_shipping_obligation_ledger(path: Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return empty_shipping_obligation_ledger()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"shipping obligation ledger must be a JSON object: {path}")
    if int(payload.get("schema_version") or 0) != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported shipping obligation schema_version={payload.get('schema_version')!r}"
        )
    if not isinstance(payload.get("entries"), dict):
        raise ValueError("shipping obligation ledger entries must be an object")
    for raw_key, raw_entry in payload["entries"].items():
        if not isinstance(raw_entry, dict):
            raise ValueError(f"shipping obligation entry must be an object: {raw_key}")
        store_code = normalize_store_code(raw_entry.get("store_code"))
        order_id = _clean(raw_entry.get("order_id"))
        status = _clean(raw_entry.get("status"))
        if not store_code or not order_id:
            raise ValueError(f"shipping obligation entry identity is incomplete: {raw_key}")
        if store_code not in KNOWN_STORE_CODES:
            raise ValueError(
                f"shipping obligation entry has unknown store_code={store_code!r}: {raw_key}"
            )
        if status not in ALL_STATUSES:
            raise ValueError(
                f"shipping obligation entry has unknown status={status!r}: {raw_key}"
            )
        canonical_key = obligation_key(store_code, order_id)
        if str(raw_key) != canonical_key:
            raise ValueError(
                "shipping obligation entry key/identity mismatch: "
                f"key={raw_key!r} canonical={canonical_key!r}"
            )
    return payload


def save_shipping_obligation_ledger(path: Path, payload: Mapping[str, Any]) -> Path:
    """Atomically persist the local obligation ledger."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)
    return path


def _normalized_order_ids_by_store(
    values: Mapping[str, Iterable[Any]] | None,
) -> dict[str, set[str]]:
    normalized: dict[str, set[str]] = defaultdict(set)
    for raw_store, raw_ids in dict(values or {}).items():
        store = normalize_store_code(raw_store)
        if not store:
            continue
        for raw_id in raw_ids or []:
            order_id = _clean(raw_id)
            if order_id:
                normalized[store].add(order_id)
    return {store: set(order_ids) for store, order_ids in sorted(normalized.items())}


def active_obligation_ids_by_store(ledger: Mapping[str, Any]) -> dict[str, set[str]]:
    active: dict[str, set[str]] = defaultdict(set)
    for raw_entry in dict(ledger.get("entries") or {}).values():
        entry = dict(raw_entry or {})
        if _clean(entry.get("status")) != STATUS_UNRESOLVED:
            continue
        store = normalize_store_code(entry.get("store_code"))
        order_id = _clean(entry.get("order_id"))
        if store and order_id:
            active[store].add(order_id)
    return {store: set(order_ids) for store, order_ids in sorted(active.items())}


def open_obligation_keys_needing_detail(
    ledger: Mapping[str, Any],
    current_active_order_ids_by_store: Mapping[str, Iterable[Any]] | None,
) -> list[str]:
    current = _normalized_order_ids_by_store(current_active_order_ids_by_store)
    result: list[str] = []
    for raw_key, raw_entry in sorted(dict(ledger.get("entries") or {}).items()):
        entry = dict(raw_entry or {})
        if _clean(entry.get("status")) not in OPEN_STATUSES:
            continue
        store = normalize_store_code(entry.get("store_code"))
        order_id = _clean(entry.get("order_id"))
        if not store or not order_id:
            result.append(str(raw_key))
            continue
        if order_id not in current.get(store, set()):
            result.append(obligation_key(store, order_id))
    return result


def _detail_order_id(order: Mapping[str, Any]) -> str:
    attrs = order.get("attributes") if isinstance(order.get("attributes"), Mapping) else order
    return _clean(attrs.get("code") or attrs.get("orderCode") or order.get("order_id"))


def _detail_stage_inputs(order: Mapping[str, Any]) -> tuple[str, str, bool]:
    attrs = order.get("attributes") if isinstance(order.get("attributes"), Mapping) else order
    state = _clean(attrs.get("state")).upper()
    status = _clean(attrs.get("status")).upper()
    returned_raw = attrs.get("returnedToWarehouse") or attrs.get("returned_to_warehouse")
    returned_to_warehouse = returned_raw is True or _clean(returned_raw).casefold() in {
        "1",
        "true",
        "yes",
        "y",
        "да",
    }
    return state, status, returned_to_warehouse


def reconcile_shipping_obligations(
    *,
    prior_ledger: Mapping[str, Any],
    current_active_order_ids_by_store: Mapping[str, Iterable[Any]] | None,
    detail_results: Mapping[str, Mapping[str, Any]] | None,
    target_date: date,
    ready_set_at: str,
    now: datetime,
    uncertainty_waiver_ids_by_store: Mapping[str, Iterable[Any]] | None = None,
    enqueue_uncertainty_warnings: bool = False,
) -> dict[str, Any]:
    """Reconcile prior obligations against fresh read-only Kaspi truth.

    ``detail_results`` is required for every prior open obligation not present in
    the current paginated active selector.  A result is ``{"order": <payload>}``
    or ``{"error": <reason>}``.  Errors and unknown states retain the obligation
    and make ``ok`` false unless the obligation is in the explicitly supplied
    validated exclusion scope.  Omitting ``uncertainty_waiver_ids_by_store``
    preserves the legacy result contract and fail-closed behavior.
    """
    ledger = copy.deepcopy(dict(prior_ledger or empty_shipping_obligation_ledger()))
    if int(ledger.get("schema_version") or SCHEMA_VERSION) != SCHEMA_VERSION:
        raise ValueError("unsupported shipping obligation ledger schema")
    entries = ledger.setdefault("entries", {})
    if not isinstance(entries, dict):
        raise ValueError("shipping obligation ledger entries must be an object")

    current = _normalized_order_ids_by_store(current_active_order_ids_by_store)
    details = {str(key): dict(value or {}) for key, value in dict(detail_results or {}).items()}
    waiver_scope_enabled = uncertainty_waiver_ids_by_store is not None
    uncertainty_waivers = _normalized_order_ids_by_store(
        uncertainty_waiver_ids_by_store
    )
    now_iso = now.isoformat()
    target_iso = target_date.isoformat()
    issues: list[dict[str, str]] = []
    blocking_issues: list[dict[str, str]] = []
    uncertainty_scope_counts = {"covered": 0, "uncovered": 0}

    def record_uncertainty(
        *,
        store: str,
        order_id: str,
        key: str,
        detail: str,
        uncovered_code: str,
    ) -> None:
        covered = order_id in uncertainty_waivers.get(store, set())
        if covered:
            issue = {
                "code": "obligation_api_uncertain_excluded_scope",
                "key": key,
                "detail": detail,
            }
            issues.append(issue)
            uncertainty_scope_counts["covered"] += 1
            if enqueue_uncertainty_warnings:
                enqueue_alert(
                    title="Shipping obligation uncertainty in prepacked exclusion scope",
                    lines=[
                        f"Target date: {target_iso}",
                        f"Obligation: {key}",
                        f"Detail: {detail}",
                        "The obligation remains unresolved; only this validated exclusion scope is non-blocking.",
                    ],
                    severity="WARN",
                    dedup_key=(
                        "shipping_obligation_uncertainty_excluded_scope:"
                        f"{target_iso}:{key}"
                    ),
                )
            return
        issue = {
            "code": uncovered_code,
            "key": key,
            "detail": detail,
        }
        issues.append(issue)
        blocking_issues.append(issue)
        uncertainty_scope_counts["uncovered"] += 1

    detail_keys = set(open_obligation_keys_needing_detail(ledger, current))
    for store, order_ids in sorted(current.items()):
        for order_id in sorted(order_ids):
            key = obligation_key(store, order_id)
            if key not in details:
                continue
            entry = dict(entries.get(key) or {})
            entry.update(
                {
                    "store_code": store,
                    "order_id": order_id,
                    "status": _clean(entry.get("status")) or STATUS_UNRESOLVED,
                    "first_seen_target_date": _clean(
                        entry.get("first_seen_target_date")
                    )
                    or target_iso,
                }
            )
            entries[key] = entry
            detail_keys.add(key)

    processed_detail_keys: set[str] = set()
    for raw_key in sorted(detail_keys):
        entry = dict(entries.get(raw_key) or {})
        store = normalize_store_code(entry.get("store_code"))
        order_id = _clean(entry.get("order_id"))
        canonical_key = obligation_key(store, order_id) if store and order_id else str(raw_key)
        processed_detail_keys.add(canonical_key)
        detail = details.get(canonical_key) or details.get(str(raw_key)) or {}
        error = _clean(detail.get("error"))
        order = detail.get("order")
        if error or not isinstance(order, Mapping):
            issue_detail = error or "missing exact API detail result"
            entry.update(
                {
                    "status": STATUS_UNRESOLVED,
                    "last_checked_at": now_iso,
                    "last_api_error": issue_detail,
                }
            )
            entries[canonical_key] = entry
            if canonical_key != raw_key:
                entries.pop(raw_key, None)
            record_uncertainty(
                store=store,
                order_id=order_id,
                key=canonical_key,
                detail=issue_detail,
                uncovered_code="obligation_api_uncertain",
            )
            continue

        observed_order_id = _detail_order_id(order)
        if observed_order_id != order_id:
            detail_text = f"identity mismatch: expected={order_id} observed={observed_order_id or 'blank'}"
            entry.update(
                {
                    "status": STATUS_UNRESOLVED,
                    "last_checked_at": now_iso,
                    "last_api_error": detail_text,
                }
            )
            entries[canonical_key] = entry
            issue = {
                "code": "obligation_api_identity_mismatch",
                "key": canonical_key,
                "detail": detail_text,
            }
            issues.append(issue)
            blocking_issues.append(issue)
            continue

        source_state, source_status, returned_to_warehouse = _detail_stage_inputs(order)
        if returned_to_warehouse:
            stage = StageCode.RETURNED
        elif source_status in {"RETURN_REQUESTED", "KASPI_DELIVERY_RETURN_REQUESTED"}:
            stage = StageCode.RETURN_REQUESTED
        elif source_state == "ARCHIVE" and source_status not in {
            "COMPLETED",
            "CANCELLED",
            "RETURNED",
            "CANCELLING",
            "RETURN_REQUESTED",
            "KASPI_DELIVERY_RETURN_REQUESTED",
        }:
            # ARCHIVE is a container state, not proof that the employee no longer
            # needs to pack this exact order.  Keep the obligation and block until
            # exact status or physical-handover truth resolves the ambiguity.
            stage = StageCode.UNKNOWN
        else:
            stage = classify_kaspi_order_stage(order)
        entry.update(
            {
                "store_code": store,
                "order_id": order_id,
                "last_checked_at": now_iso,
                "last_stage": stage.value,
                "last_api_error": "",
            }
        )
        if stage in PACKABLE_STAGES:
            entry.update(
                {
                    "status": STATUS_UNRESOLVED,
                    "last_seen_target_date": target_iso,
                    "discharged_at": "",
                    "discharge_reason": "",
                }
            )
        elif stage in TRANSITIONAL_NO_PACK_STAGES:
            entry.update(
                {
                    "status": STATUS_SUSPENDED,
                    "last_seen_target_date": target_iso,
                    "suspension_reason": stage.value,
                }
            )
        elif stage in DISCHARGE_STAGES:
            entry.update(
                {
                    "status": STATUS_DISCHARGED,
                    "discharged_at": now_iso,
                    "discharge_reason": stage.value,
                }
            )
        else:
            entry.update(
                {
                    "status": STATUS_UNRESOLVED,
                    "last_seen_target_date": target_iso,
                }
            )
            record_uncertainty(
                store=store,
                order_id=order_id,
                key=canonical_key,
                detail=(
                    "ARCHIVE_UNDIFFERENTIATED"
                    if source_state == "ARCHIVE"
                    else stage.value
                ),
                uncovered_code="obligation_api_stage_uncertain",
            )
        entries[canonical_key] = entry
        if canonical_key != raw_key:
            entries.pop(raw_key, None)

    for store, order_ids in sorted(current.items()):
        for order_id in sorted(order_ids):
            key = obligation_key(store, order_id)
            if key in processed_detail_keys:
                continue
            entry = dict(entries.get(key) or {})
            entry.update(
                {
                    "store_code": store,
                    "order_id": order_id,
                    "status": STATUS_UNRESOLVED,
                    "first_seen_target_date": _clean(entry.get("first_seen_target_date")) or target_iso,
                    "last_seen_target_date": target_iso,
                    "last_checked_at": now_iso,
                    "last_stage": _clean(entry.get("last_stage")) or "API_ACTIVE_SELECTOR",
                    "last_api_error": "",
                    "discharged_at": "",
                    "discharge_reason": "",
                }
            )
            entries[key] = entry

    request_identity = {
        "target_date": target_iso,
        "ready_set_at": _clean(ready_set_at),
    }
    ledger.update(
        {
            "schema_version": SCHEMA_VERSION,
            "updated_at": now_iso,
            "request_identity": request_identity,
            "entries": dict(sorted(entries.items())),
        }
    )
    result = {
        "ok": not blocking_issues,
        "issues": issues,
        "ledger": ledger,
        "active_order_ids_by_store": active_obligation_ids_by_store(ledger),
    }
    if waiver_scope_enabled:
        result["uncertainty_scope_counts"] = uncertainty_scope_counts
    return result


def load_required_orders_file(path: Path, *, target_date: date) -> dict[str, Any]:
    """Load and identity-lock the exact downstream order set for one Ready request."""
    path = Path(path)
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"required orders file must contain a JSON object: {path}")
    observed_target = _clean(payload.get("target_date"))
    if observed_target != target_date.isoformat():
        raise ValueError(
            f"required orders target_date mismatch: {observed_target or 'blank'} != {target_date.isoformat()}"
        )

    expected_ids = {
        order_id
        for order_id in (_clean(value) for value in payload.get("expected_order_ids") or [])
        if order_id
    }
    schema_version = int(payload.get("schema_version") or 1)
    if schema_version not in {1, REQUIRED_ORDERS_SCHEMA_VERSION}:
        raise ValueError(f"unsupported required orders schema_version={schema_version}")

    mapped: dict[str, set[str]] = defaultdict(set)
    stores_by_order: dict[str, set[str]] = defaultdict(set)
    required_lines: list[dict[str, Any]] = []
    package_counts_by_order: dict[str, int] = {}
    for raw_row in payload.get("orders") or []:
        if not isinstance(raw_row, Mapping):
            continue
        order_id = _clean(raw_row.get("order_id"))
        store = normalize_store_code(raw_row.get("store_code"))
        if not order_id or not store:
            continue
        mapped[store].add(order_id)
        stores_by_order[order_id].add(store)
        if schema_version >= REQUIRED_ORDERS_SCHEMA_VERSION:
            raw_lines = raw_row.get("lines")
            if not isinstance(raw_lines, list) or not raw_lines:
                raise ValueError(
                    f"required order {store}:{order_id} has no immutable line scope"
                )
            for raw_line in raw_lines:
                if not isinstance(raw_line, Mapping):
                    raise ValueError(
                        f"required order {store}:{order_id} has malformed line scope"
                    )
                normalized_line = normalize_required_line(
                    raw_line,
                    default_store_code=store,
                    default_order_id=order_id,
                )
                if normalized_line["store_code"] != store or normalized_line["order_id"] != order_id:
                    raise ValueError(
                        f"required order {store}:{order_id} has a child line with mismatched identity"
                    )
                required_lines.append(normalized_line)
            try:
                package_count = int(raw_row.get("package_count") or 0)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"required order {store}:{order_id} has invalid package_count"
                ) from exc
            if package_count <= 0:
                raise ValueError(
                    f"required order {store}:{order_id} has invalid package_count"
                )
            package_counts_by_order[order_id] = package_count

    multi_store = sorted(order_id for order_id, stores in stores_by_order.items() if len(stores) != 1)
    if multi_store:
        raise ValueError("required orders have ambiguous store mapping: " + ",".join(multi_store))
    mapped_ids = set(stores_by_order)
    if expected_ids != mapped_ids:
        missing = sorted(expected_ids - mapped_ids)
        extra = sorted(mapped_ids - expected_ids)
        raise ValueError(
            "required orders mapping mismatch: "
            f"unmapped={','.join(missing) or '-'} extra={','.join(extra) or '-'}"
        )

    request_identity = payload.get("request_identity") or {}
    if not isinstance(request_identity, Mapping):
        raise ValueError("required orders request_identity must be an object")
    if _clean(request_identity.get("target_date")) != observed_target:
        raise ValueError("required orders request_identity target_date mismatch")
    if not _clean(request_identity.get("ready_set_at")):
        raise ValueError("required orders request_identity ready_set_at is missing")

    line_scope_hash = ""
    if schema_version >= REQUIRED_ORDERS_SCHEMA_VERSION:
        line_scope_hash = required_line_scope_hash(required_lines)
        declared_line_scope_hash = _clean(payload.get("line_scope_hash"))
        if declared_line_scope_hash != line_scope_hash:
            raise ValueError(
                "required orders line_scope_hash mismatch: "
                f"declared={declared_line_scope_hash or 'blank'} computed={line_scope_hash}"
            )

    return {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "payload": payload,
        "request_identity": dict(request_identity),
        "schema_version": schema_version,
        "orders_by_store": {
            store: set(order_ids) for store, order_ids in sorted(mapped.items())
        },
        "order_ids": expected_ids,
        "line_scope_required": schema_version >= REQUIRED_ORDERS_SCHEMA_VERSION,
        "line_scope": required_lines,
        "line_scope_hash": line_scope_hash,
        "package_counts_by_order": package_counts_by_order,
    }
