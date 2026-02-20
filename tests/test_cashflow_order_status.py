from core.cashflow.order_status import normalize_order_status


def test_shipped_maps_on_delivery():
    assert normalize_order_status("SHIPPED", None, {}) == "ON_DELIVERY"


def test_kaspi_courier_maps_on_delivery():
    assert normalize_order_status(None, "Передан курьеру", {}) == "ON_DELIVERY"


def test_completed_maps_completed():
    assert normalize_order_status("COMPLETED", None, {}) == "COMPLETED"
