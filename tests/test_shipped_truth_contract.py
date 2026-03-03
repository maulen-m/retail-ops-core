from pathlib import Path


def test_shipped_truth_contract_exists_and_locks_state_scope() -> None:
    doc = Path("docs/validation/SHIPPED_TRUTH_CRM_WAYBILL_CONTRACT.md")
    assert doc.exists(), "missing shipped truth contract"
    text = doc.read_text(encoding="utf-8")
    assert "courierTransmissionDate" in text
    assert "KASPI_DELIVERY" in text
    assert "ARCHIVE" in text
    assert "not `CANCELLED`/`RETURNED`" in text
    assert "detail fallback" in text.lower()
    assert "ActiveOrders/waybills" in text
    assert "waybill URL/number" in text


def test_shipped_truth_contract_declares_today_provisional_rule() -> None:
    text = Path("docs/validation/SHIPPED_TRUTH_CRM_WAYBILL_CONTRACT.md").read_text(encoding="utf-8")
    assert "today" in text.lower()
    assert "provisional" in text.lower()
    assert "hard-fail" in text.lower()


def test_shipped_truth_contract_defines_cancel_drift_on_shipped_universe() -> None:
    text = Path("docs/validation/SHIPPED_TRUTH_CRM_WAYBILL_CONTRACT.md").read_text(encoding="utf-8")
    assert "api_cancelled_shipped_set" in text
    assert "crm_cancelled_shipped_set" in text
    assert "∩ api_secondary_set" in text


def test_shipped_truth_contract_locks_volatility_window_and_lookback() -> None:
    text = Path("docs/validation/SHIPPED_TRUTH_CRM_WAYBILL_CONTRACT.md").read_text(encoding="utf-8")
    assert "Volatility window" in text
    assert "14" in text
    assert "api-creation-lookback-days" in text
    assert "SHIFTED" in text
    assert "API final cancellation status is authoritative" in text
    assert "rows still `NEW/ACCEPTED` without shipped marker are excluded" in text
