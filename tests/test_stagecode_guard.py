from scripts.validate_stagecode_guard import run_guard


def test_stagecode_guard_clean():
    hits = run_guard(
        [
            "core/alerts/order_alerts.py",
            "core/sync/order_sync_engine.py",
            "scripts/build_daily_waybills.py",
            "scripts/download_waybills_api.py",
            "scripts/report_waybill_status.py",
            "scripts/translate_orders_to_cashflow_events.py",
            "scripts/validate_pending_orders.py",
        ]
    )
    assert hits == [], f"StageCode guard hits: {hits}"
