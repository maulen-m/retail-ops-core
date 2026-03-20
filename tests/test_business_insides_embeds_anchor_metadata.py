from __future__ import annotations

from datetime import datetime

from scripts.generate_business_insides import _render_markdown


def _minimal_sales_metrics() -> dict[str, object]:
    row = {
        "date": "2026-02-26",
        "units_delivered": 1.0,
        "net_rev_kzt": 1000.0,
        "cogs_kzt": None,
        "ads_spend_kzt": None,
        "profit_kzt": None,
        "profit_after_ads_kzt": None,
    }
    return {
        "avg_30d_net_rev_kzt": 1000.0,
        "avg_30d_cogs_kzt": None,
        "avg_30d_profit_kzt": None,
        "avg_30d_ads_spend_kzt": None,
        "avg_30d_profit_after_ads_kzt": None,
        "avg_7d_net_rev_kzt": 1000.0,
        "avg_7d_cogs_kzt": None,
        "avg_7d_profit_kzt": None,
        "avg_7d_ads_spend_kzt": None,
        "avg_7d_profit_after_ads_kzt": None,
        "last_7_days": [row],
        "latest_7_observed_days": [row],
        "observed_days_last_7_calendar": 1,
        "latest_sale_date_available": "2026-02-26",
        "sales_truth_freshness_days": 0,
        "waybill_snapshot": {
            "status": "available",
            "cache_path": "x",
            "target_date": "2026-02-26",
            "include_overdue": True,
            "all_dates": True,
            "stores": {"UNIVERSAL": {"orders": 1, "units": 1}},
            "totals": {"orders": 1, "units": 1},
        },
        "ads": {
            "status": "ok",
            "reason": "ok",
            "mapping_coverage_pct": 100.0,
            "mapped_cost_kzt": 0.0,
            "unmapped_cost_kzt": 0.0,
        },
        "fallback_rows": 0,
        "total_rows": 1,
        "cogs_fallback_coverage_pct": 0.0,
        "unresolved_rows": 0,
        "unresolved_sku_count": 0,
        "economics_volatility_days": 14,
        "economics_missing_days": [],
        "economics_missing_nonvolatile_days": [],
        "profit_publication_locked": True,
        "revenue_fallback_days": 0,
        "archive_orders_fallback_days": 0,
        "archive_orders": {"status": "available", "reason": "ok", "files": ["sample.xlsx"]},
    }


def test_render_markdown_includes_ocean_drop_anchor_metadata() -> None:
    text = _render_markdown(
        generated_at=datetime(2026, 2, 28, 12, 0, 0),
        as_of_date="2026-02-26",
        capital={
            "cash_actual_kzt": 1.0,
            "inventory_on_hand_paid_kzt": 1.0,
            "inventory_inbound_paid_kzt": 1.0,
            "inventory_on_delivery_paid_kzt": 1.0,
            "total_capital_paid_kzt": 4.0,
            "inbound_unpaid_obligations_kzt": 0.0,
        },
        sales_metrics=_minimal_sales_metrics(),
        ocean_drop_anchor={
            "configured": True,
            "registry_path": "/tmp/anchor.json",
            "ocean_drop_path_resolved": "/tmp/ocean_drop.csv",
            "sha256": "abc",
            "sha256_computed": "abc",
            "as_of_end": "2026-02-26",
            "transaction_date_mode": "delivered_status_date",
            "source": "ui_merged",
        },
        external_check={"status": "PASS", "ok": True},
    )
    assert "## Ocean Drop Provenance" in text
    assert "Anchor path: `/tmp/ocean_drop.csv`" in text
    assert "Anchor sha256: `abc` (computed: `abc`)" in text
    assert "Transaction date mode: `delivered_status_date`" in text
