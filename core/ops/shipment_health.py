from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HealthState:
    code: str
    exit_code: int
    message: str


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def classify_ship_health(result: dict[str, Any]) -> HealthState:
    shipped = _to_int(result.get("shipped"))
    skipped = _to_int(result.get("skipped"))
    errors = result.get("errors") or []

    if errors:
        return HealthState("api_error", 1, f"shipping errors={len(errors)}")
    if shipped == 0 and skipped == 0:
        return HealthState("no_pending", 0, "no pending orders to ship")
    if shipped > 0 and skipped == 0:
        return HealthState("ok", 0, f"shipped={shipped}")
    return HealthState("partial", 1, f"shipped={shipped} skipped={skipped}")


def classify_waybill_health(result: dict[str, Any]) -> HealthState:
    downloaded = _to_int(result.get("downloaded"))
    already_exists = _to_int(result.get("already_exists"))
    missing_waybill = _to_int(result.get("missing_waybill"))
    invalid_pdf = _to_int(result.get("invalid_pdf"))
    errors = result.get("errors") or []

    if errors:
        return HealthState("api_error", 1, f"download errors={len(errors)}")
    if invalid_pdf > 0:
        return HealthState("invalid_pdf", 1, f"invalid_pdf={invalid_pdf}")
    if missing_waybill > 0 and downloaded == 0 and already_exists == 0:
        return HealthState("delayed", 1, f"missing_waybill={missing_waybill}")
    if missing_waybill > 0:
        return HealthState(
            "partial",
            1,
            f"downloaded={downloaded} already_exists={already_exists} missing_waybill={missing_waybill}",
        )
    if downloaded > 0 or already_exists > 0:
        return HealthState("ok", 0, f"downloaded={downloaded} already_exists={already_exists}")
    return HealthState("no_targets", 0, "no target waybills")
