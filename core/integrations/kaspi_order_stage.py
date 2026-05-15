"""Kaspi order stage classification (API state/status -> internal StageCode)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class StageCode(str, Enum):
    SIGN_REQUIRED = "SIGN_REQUIRED"
    NEW_APPROVED = "NEW_APPROVED"
    PREORDER_IN_TRANSIT = "PREORDER_IN_TRANSIT"
    ACCEPTED_PENDING_ASSEMBLY = "ACCEPTED_PENDING_ASSEMBLY"
    ASSEMBLED_PENDING_HANDOVER = "ASSEMBLED_PENDING_HANDOVER"
    IN_DELIVERY = "IN_DELIVERY"
    ISSUED_COMPLETED = "ISSUED_COMPLETED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"
    RETURN_REQUESTED = "RETURN_REQUESTED"
    RETURNED = "RETURNED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class KaspiStageInputs:
    state: str
    status: str
    signature_required: bool
    pre_order: bool
    assembled: bool
    courier_transmission_date: bool
    delivery_mode: str
    is_kaspi_delivery: bool
    returned_to_warehouse: bool


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in {"", "0", "false", "no", "n", "f"}:
        return False
    if text in {"1", "true", "yes", "y", "t"}:
        return True
    # Treat any other non-empty string (e.g., date) as truthy.
    return True


def _norm(value: Any) -> str:
    return str(value or "").strip().upper()


def _get_attrs(order: Mapping[str, Any]) -> Mapping[str, Any]:
    attrs = order.get("attributes")
    if isinstance(attrs, Mapping):
        return attrs
    return order


def _extract_stage_inputs(order: Mapping[str, Any]) -> KaspiStageInputs:
    attrs = _get_attrs(order)
    state = _norm(attrs.get("state"))
    status = _norm(attrs.get("status"))
    signature_required = _as_bool(
        attrs.get("signatureRequired")
        or attrs.get("signature_required")
        or attrs.get("signature")
    )
    pre_order = _as_bool(attrs.get("preOrder") or attrs.get("pre_order"))
    assembled = _as_bool(attrs.get("assembled"))
    delivery = attrs.get("kaspiDelivery") or attrs.get("delivery") or {}
    waybill = None
    if isinstance(delivery, Mapping):
        courier_transmission_date = delivery.get("courierTransmissionDate")
        waybill = delivery.get("waybill") or delivery.get("waybillNumber")
    else:
        courier_transmission_date = None
    if not assembled and waybill:
        assembled = True
    if not assembled and attrs.get("waybill"):
        assembled = True
    courier_transmission_date = (
        courier_transmission_date
        or attrs.get("courierTransmissionDate")
        or attrs.get("actualShipmentDate")
    )
    courier_transmission_date = _as_bool(courier_transmission_date)
    delivery_mode = _norm(attrs.get("deliveryMode") or attrs.get("delivery_mode"))
    is_kaspi_delivery = delivery_mode == "DELIVERY"
    returned_to_warehouse = _as_bool(
        attrs.get("returnedToWarehouse") or attrs.get("returned_to_warehouse")
    )
    return KaspiStageInputs(
        state=state,
        status=status,
        signature_required=signature_required,
        pre_order=pre_order,
        assembled=assembled,
        courier_transmission_date=courier_transmission_date,
        delivery_mode=delivery_mode,
        is_kaspi_delivery=is_kaspi_delivery,
        returned_to_warehouse=returned_to_warehouse,
    )


def classify_kaspi_order_stage(order: Mapping[str, Any]) -> StageCode:
    """Return StageCode based on Kaspi API payload fields."""
    inputs = _extract_stage_inputs(order)

    if inputs.status == "RETURNED":
        return StageCode.RETURNED
    if inputs.status == "KASPI_DELIVERY_RETURN_REQUESTED":
        return StageCode.RETURN_REQUESTED
    if inputs.status == "CANCELLED":
        return StageCode.CANCELLED
    if inputs.status == "CANCELLING":
        return StageCode.CANCELLING
    if inputs.status == "COMPLETED":
        return StageCode.ISSUED_COMPLETED

    if inputs.signature_required or inputs.state == "SIGN_REQUIRED":
        return StageCode.SIGN_REQUIRED

    if inputs.pre_order:
        return StageCode.PREORDER_IN_TRANSIT

    if inputs.state == "NEW" and inputs.status == "APPROVED_BY_BANK":
        return StageCode.NEW_APPROVED

    if inputs.state == "KASPI_DELIVERY":
        if inputs.courier_transmission_date:
            return StageCode.IN_DELIVERY
        if inputs.assembled:
            return StageCode.ASSEMBLED_PENDING_HANDOVER
        return StageCode.ACCEPTED_PENDING_ASSEMBLY

    if inputs.state in {"DELIVERY", "PICKUP"}:
        return StageCode.IN_DELIVERY

    if inputs.state == "ARCHIVE":
        return StageCode.ISSUED_COMPLETED

    if inputs.status == "ACCEPTED_BY_MERCHANT":
        return StageCode.ACCEPTED_PENDING_ASSEMBLY

    return StageCode.UNKNOWN


STAGE_INTERNAL_STATUS = {
    StageCode.SIGN_REQUIRED: "NEW",
    StageCode.NEW_APPROVED: "NEW",
    StageCode.PREORDER_IN_TRANSIT: "NEW",
    StageCode.ACCEPTED_PENDING_ASSEMBLY: "ACCEPTED",
    StageCode.ASSEMBLED_PENDING_HANDOVER: "READY",
    StageCode.IN_DELIVERY: "SHIPPED",
    StageCode.ISSUED_COMPLETED: "COMPLETED",
    StageCode.CANCELLING: "CANCELLED",
    StageCode.CANCELLED: "CANCELLED",
    StageCode.RETURN_REQUESTED: "RETURNING",
    StageCode.RETURNED: "RETURNED",
    StageCode.UNKNOWN: "NEW",
}

INTERNAL_STATUS_STAGE = {
    "NEW": StageCode.NEW_APPROVED,
    "ACCEPTED": StageCode.ACCEPTED_PENDING_ASSEMBLY,
    "READY": StageCode.ASSEMBLED_PENDING_HANDOVER,
    "SHIPPED": StageCode.IN_DELIVERY,
    "ON_DELIVERY": StageCode.IN_DELIVERY,
    "DELIVERED": StageCode.ISSUED_COMPLETED,
    "COMPLETED": StageCode.ISSUED_COMPLETED,
    "ISSUED": StageCode.ISSUED_COMPLETED,
    "CANCELLING": StageCode.CANCELLING,
    "CANCELLED": StageCode.CANCELLED,
    "RETURNING": StageCode.RETURN_REQUESTED,
    "RETURN_REQUESTED": StageCode.RETURN_REQUESTED,
    "RETURNED": StageCode.RETURNED,
}

KASPI_STATUS_RU = {
    "NEW": "Новый",
    "APPROVED_BY_BANK": "Одобрен банком",
    "ACCEPTED_BY_MERCHANT": "Принят продавцом",
    "ASSEMBLY": "Собирается",
    "KASPI_DELIVERY": "Ожидает передачи курьеру",
    "DELIVERY": "Доставляется",
    "PICKUP": "Готов к выдаче",
    "COMPLETED": "Завершен",
    "CANCELLED": "Отменен",
    "CANCELLING": "Отменяется",
    "RETURNING": "Возвращается",
    "RETURNED": "Возвращен",
    "ARCHIVE": "Завершен",
}


def kaspi_order_to_russian_status(order: Mapping[str, Any]) -> str:
    """Return CRM status string using live stage truth."""
    attrs = _get_attrs(order)
    stage = classify_kaspi_order_stage(order)
    if stage in {StageCode.ACCEPTED_PENDING_ASSEMBLY, StageCode.ASSEMBLED_PENDING_HANDOVER}:
        return "Ожидает передачи курьеру"
    if stage == StageCode.IN_DELIVERY:
        return "Передан курьеру"
    if stage == StageCode.ISSUED_COMPLETED:
        return "Завершен"
    if stage == StageCode.CANCELLED:
        return "Отменен"
    if stage == StageCode.CANCELLING:
        return "Отменяется"
    if stage == StageCode.RETURN_REQUESTED:
        return "Возвращается"
    if stage == StageCode.RETURNED:
        return "Возвращен"
    state = _norm(attrs.get("state"))
    status = _norm(attrs.get("status"))
    return KASPI_STATUS_RU.get(status) or KASPI_STATUS_RU.get(state) or status or state


def stage_to_crm_indicators(stage: StageCode) -> dict[str, str]:
    """Return CRM indicator flags (Принял/Выдал/Отменил) from StageCode."""
    accepted = {
        StageCode.ACCEPTED_PENDING_ASSEMBLY,
        StageCode.ASSEMBLED_PENDING_HANDOVER,
        StageCode.IN_DELIVERY,
        StageCode.ISSUED_COMPLETED,
    }
    issued = {StageCode.IN_DELIVERY, StageCode.ISSUED_COMPLETED}
    cancelled = {StageCode.CANCELLED, StageCode.CANCELLING, StageCode.RETURN_REQUESTED, StageCode.RETURNED}
    return {
        "Принял": "Да" if stage in accepted else "",
        "Выдал": "Да" if stage in issued else "",
        "Отменил": "Да" if stage in cancelled else "",
    }


def stage_to_internal_status(stage: StageCode) -> str:
    return STAGE_INTERNAL_STATUS.get(stage, "NEW")


def classify_kaspi_stage_from_db_row(row: Mapping[str, Any]) -> StageCode:
    if not hasattr(row, "get"):
        row = dict(row)
    attrs = {
        "state": row.get("kaspi_status") or row.get("state"),
        "status": row.get("kaspi_status_detail") or row.get("status"),
        "signatureRequired": row.get("signature_required") or row.get("signatureRequired"),
        "preOrder": row.get("pre_order") or row.get("preOrder"),
        "assembled": bool(row.get("waybill_url")),
        "deliveryMode": row.get("delivery_mode") or row.get("deliveryMode"),
        "returnedToWarehouse": row.get("returned_to_warehouse") or row.get("returnedToWarehouse"),
        "courierTransmissionDate": row.get("courier_transmission_date")
        or row.get("actual_shipment_date")
    }
    stage = classify_kaspi_order_stage({"attributes": attrs})
    internal_stage = INTERNAL_STATUS_STAGE.get(
        _norm(row.get("internal_status") or row.get("status_internal")),
        StageCode.UNKNOWN,
    )
    has_api_status_detail = bool(
        _norm(row.get("kaspi_status_detail") or row.get("status"))
    )
    if (
        not has_api_status_detail
        and attrs["state"] == "KASPI_DELIVERY"
        and internal_stage != StageCode.UNKNOWN
    ):
        return internal_stage
    if stage != StageCode.UNKNOWN:
        return stage
    return internal_stage


KASPI_DELIVERY_STATE = "KASPI_DELIVERY"


def api_state_filter_for_stage(stage: StageCode) -> str | None:
    if stage in {
        StageCode.ACCEPTED_PENDING_ASSEMBLY,
        StageCode.ASSEMBLED_PENDING_HANDOVER,
        StageCode.IN_DELIVERY,
    }:
        return KASPI_DELIVERY_STATE
    if stage == StageCode.SIGN_REQUIRED:
        return "SIGN_REQUIRED"
    if stage == StageCode.NEW_APPROVED:
        return "NEW"
    return None
