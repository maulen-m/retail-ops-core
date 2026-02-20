from datetime import date

from scripts.update_cashflow_dashboard import Commitment, _build_forecast_rows


def test_commitments_roll_forward_dates():
    history = [
        {
            "date": "2026-01-01",
            "cash_close": 1000.0,
            "receivables_close": 0.0,
            "inventory_cost_close": 0.0,
            "sales_accrued_kzt": 0.0,
            "cogs_kzt": 0.0,
        }
    ]
    commitments = [
        Commitment(
            commit_date="2026-01-03",
            commit_type="PO_PAYMENT",
            amount_kzt=150.0,
            scenario_tag="base",
            ref_id="PO-TEST",
            notes=None,
        )
    ]
    rows = _build_forecast_rows(history, commitments, days=3, payout_lag_days=0, run_id="test")
    rows_by_date = {row["date"]: row for row in rows}

    assert rows_by_date["2026-01-02"]["po_payments_kzt"] == 0.0
    assert rows_by_date["2026-01-03"]["po_payments_kzt"] == 150.0
    assert rows_by_date["2026-01-03"]["cash_flow_kzt"] == -150.0
