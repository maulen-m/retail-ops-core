from core.integrations.kaspi_order_stage import (
    StageCode,
    classify_kaspi_order_stage,
    classify_kaspi_stage_from_db_row,
)


def _make_order(state=None, status=None, **extra):
    attrs = {}
    if state is not None:
        attrs["state"] = state
    if status is not None:
        attrs["status"] = status
    attrs.update(extra)
    return {"attributes": attrs}


def test_new_order_classification():
    order = _make_order(state="NEW", status="APPROVED_BY_BANK")
    assert classify_kaspi_order_stage(order) == StageCode.NEW_APPROVED


def test_signature_required_classification_by_state():
    order = _make_order(state="SIGN_REQUIRED", status="APPROVED_BY_BANK")
    assert classify_kaspi_order_stage(order) == StageCode.SIGN_REQUIRED


def test_signature_required_classification_by_flag():
    order = _make_order(state="NEW", status="APPROVED_BY_BANK", signatureRequired=True)
    assert classify_kaspi_order_stage(order) == StageCode.SIGN_REQUIRED


def test_completion_mapping():
    order = _make_order(state="ARCHIVE", status="COMPLETED")
    assert classify_kaspi_order_stage(order) == StageCode.ISSUED_COMPLETED


def test_cancellation_mapping():
    cancelling = _make_order(state="KASPI_DELIVERY", status="CANCELLING")
    cancelled = _make_order(state="KASPI_DELIVERY", status="CANCELLED")
    assert classify_kaspi_order_stage(cancelling) == StageCode.CANCELLING
    assert classify_kaspi_order_stage(cancelled) == StageCode.CANCELLED


def test_handover_to_delivery_mapping():
    order = _make_order(
        state="KASPI_DELIVERY",
        status="ACCEPTED_BY_MERCHANT",
        assembled=True,
        kaspiDelivery={"courierTransmissionDate": 1700000000000},
    )
    assert classify_kaspi_order_stage(order) == StageCode.IN_DELIVERY


def test_return_mapping():
    requested = _make_order(state="KASPI_DELIVERY", status="KASPI_DELIVERY_RETURN_REQUESTED")
    requested_alias = _make_order(state="KASPI_DELIVERY", status="RETURN_REQUESTED")
    returned = _make_order(state="ARCHIVE", status="RETURNED")
    returned_to_warehouse = _make_order(
        state="KASPI_DELIVERY",
        status="ACCEPTED_BY_MERCHANT",
        returnedToWarehouse=True,
    )
    assert classify_kaspi_order_stage(requested) == StageCode.RETURN_REQUESTED
    assert classify_kaspi_order_stage(requested_alias) == StageCode.RETURN_REQUESTED
    assert classify_kaspi_order_stage(returned) == StageCode.RETURNED
    assert classify_kaspi_order_stage(returned_to_warehouse) == StageCode.RETURNED


def test_preorder_mapping():
    order = _make_order(state="NEW", status="ACCEPTED_BY_MERCHANT", preOrder=True)
    assert classify_kaspi_order_stage(order) == StageCode.PREORDER_IN_TRANSIT


def test_accepted_pending_assembly_mapping():
    order = _make_order(state="KASPI_DELIVERY", status="ACCEPTED_BY_MERCHANT", assembled=False)
    assert classify_kaspi_order_stage(order) == StageCode.ACCEPTED_PENDING_ASSEMBLY


def test_assembled_pending_handover_mapping():
    order = _make_order(state="KASPI_DELIVERY", status="ACCEPTED_BY_MERCHANT", assembled=True)
    assert classify_kaspi_order_stage(order) == StageCode.ASSEMBLED_PENDING_HANDOVER


def test_delivery_state_mapping():
    order = _make_order(state="DELIVERY", status="ACCEPTED_BY_MERCHANT")
    assert classify_kaspi_order_stage(order) == StageCode.IN_DELIVERY


def test_courier_transmission_date_string_marks_in_delivery():
    order = _make_order(
        state="KASPI_DELIVERY",
        status="ACCEPTED_BY_MERCHANT",
        assembled=False,
        kaspiDelivery={"courierTransmissionDate": "2026-01-01"},
    )
    assert classify_kaspi_order_stage(order) == StageCode.IN_DELIVERY


def test_waybill_presence_marks_assembled():
    order = _make_order(
        state="KASPI_DELIVERY",
        status="ACCEPTED_BY_MERCHANT",
        assembled=False,
        kaspiDelivery={"waybill": "WB-123"},
    )
    assert classify_kaspi_order_stage(order) == StageCode.ASSEMBLED_PENDING_HANDOVER


def test_db_row_planning_date_does_not_mark_in_delivery():
    row = {
        "kaspi_status": "KASPI_DELIVERY",
        "kaspi_status_detail": "ACCEPTED_BY_MERCHANT",
        "signature_required": 0,
        "pre_order": 0,
        "waybill_url": None,
        "delivery_mode": "DELIVERY",
        "returned_to_warehouse": 0,
        "courier_transmission_date": None,
        "actual_shipment_date": None,
        "courier_transmission_planning_date": "2026-02-07",
    }
    assert classify_kaspi_stage_from_db_row(row) == StageCode.ACCEPTED_PENDING_ASSEMBLY
