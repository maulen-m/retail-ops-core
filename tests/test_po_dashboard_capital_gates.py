from scripts import generate_po_dashboard_data


def _build_fixture_case(sku_key: str, unit_profit: float) -> dict:
    return {
        "sku_key": sku_key,
        "store_code": "UNIVERSAL",
        "size_sales_90d": {"S": 90},
        "size_current_stock": {"S": 0},
        "size_inbound_stock": {"S": 0},
        "size_sales_history": {"S": [1] * 90},
        "size_stock_history": {"S": [10] * 90},
        "unit_cogs": 1000.0,
        "unit_profit": unit_profit,
        "sigma_sku": 1.0,
        "sku_age_days": 120,
    }


def test_apply_po_capital_gates_rules():
    sku_lines = [
        {"sku_key": "SKU_HIGH", "stock": 10, "po_qty_total": 90, "unit_cogs": 1000.0, "roic_pct": 25.0},
        {"sku_key": "SKU_WARN", "stock": 10, "po_qty_total": 10, "unit_cogs": 1000.0, "roic_pct": 15.0},
        {"sku_key": "SKU_LOW", "stock": 10, "po_qty_total": 10, "unit_cogs": 1000.0, "roic_pct": 5.0},
    ]
    preflight = {"ok": False, "reason": "min_cash below floor"}

    summary = generate_po_dashboard_data.apply_po_capital_gates(sku_lines, preflight)

    high = next(row for row in sku_lines if row["sku_key"] == "SKU_HIGH")
    warn = next(row for row in sku_lines if row["sku_key"] == "SKU_WARN")
    low = next(row for row in sku_lines if row["sku_key"] == "SKU_LOW")

    assert high["capital_share_pct"] > 20.0
    assert high["concentration_blocked"] is True

    assert warn["roic_action"] == "ORDER_WITH_FLAG"
    assert low["roic_action"] == "REVIEW_REQUIRED"
    assert "review" in low["roic_reason"].lower()

    assert summary["cashflow_preflight_ok"] is False
    assert summary["cashflow_preflight_reason"] == "min_cash below floor"


def test_generate_po_data_includes_gate_fields():
    fixture_cases = [
        _build_fixture_case("SKU_HIGH", unit_profit=300.0),
        _build_fixture_case("SKU_LOW", unit_profit=50.0),
    ]

    output = generate_po_dashboard_data.generate_po_data(
        fixture_cases=fixture_cases,
        fixture_generated_at="2026-01-01",
        fixture_preflight_ok=False,
        fixture_preflight_reason="fixture preflight fail",
    )

    assert "cashflow_preflight_ok" in output["summary"]
    assert output["summary"]["cashflow_preflight_ok"] is False
    assert output["summary"]["cashflow_preflight_reason"] == "fixture preflight fail"

    for line in output["sku_level"]:
        assert "capital_share_pct" in line
        assert "roic_action" in line
        assert "roic_reason" in line
        assert "concentration_blocked" in line
