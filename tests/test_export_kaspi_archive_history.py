from datetime import date

from scripts.export_kaspi_archive_history import (
    WINDOW_DAYS,
    _flatten_order,
    _hydrate_missing_status_change_dates,
    _order_matches_date_mode,
    date_windows,
    process_store,
)


def test_date_windows_exact_coverage_no_gaps_or_overlaps():
    start = date(2024, 6, 6)
    end = date(2026, 2, 26)

    windows = date_windows(start, end, WINDOW_DAYS)

    assert windows[0][0] == start
    assert windows[-1][1] == end

    for idx in range(1, len(windows)):
        prev_end = windows[idx - 1][1]
        cur_start = windows[idx][0]
        assert (cur_start - prev_end).days == 1

    for ws, we in windows:
        assert (we - ws).days + 1 <= WINDOW_DAYS


def test_date_windows_single_day():
    d = date(2026, 2, 26)
    windows = date_windows(d, d, WINDOW_DAYS)
    assert windows == [(d, d)]


def test_date_windows_invalid_range_raises():
    start = date(2026, 2, 27)
    end = date(2026, 2, 26)
    try:
        date_windows(start, end, WINDOW_DAYS)
    except ValueError as exc:
        assert "end date" in str(exc)
    else:
        raise AssertionError("Expected ValueError for inverted date range")


def test_order_matches_status_change_mode_uses_status_change_date():
    order = {
        "id": "x1",
        "attributes": {
            "creationDate": 1740441600000,      # 2025-02-25
            "statusChangeDate": 1740614400000,  # 2025-02-27
        },
    }
    assert _order_matches_date_mode(
        order=order,
        mode="statusChangeDate",
        since=date(2025, 2, 27),
        until=date(2025, 2, 27),
    )
    assert not _order_matches_date_mode(
        order=order,
        mode="statusChangeDate",
        since=date(2025, 2, 25),
        until=date(2025, 2, 25),
    )


def test_hydrate_missing_status_change_dates_only_fetches_missing():
    orders = [
        {"id": "A", "attributes": {"statusChangeDate": None, "code": "100"}},
        {"id": "B", "attributes": {"statusChangeDate": 1740441600000, "code": "101"}},
        {"id": "C", "attributes": {"statusChangeDate": "", "code": "102"}},
    ]
    calls: list[str] = []

    def fetcher(order_id: str, order_code: str):
        calls.append(order_id or order_code)
        if order_id == "A":
            return {"id": "A", "attributes": {"statusChangeDate": 1740528000000}}
        if order_id == "C":
            return {"id": "C", "attributes": {"statusChangeDate": 1740614400000}}
        return None

    stats = _hydrate_missing_status_change_dates(
        orders=orders,
        fetch_order_detail=fetcher,
        max_workers=1,
        probe_limit=0,
    )

    assert stats["attempted"] == 2
    assert stats["hydrated"] == 2
    assert sorted(calls) == ["A", "C"]
    assert orders[0]["attributes"]["statusChangeDate"] == 1740528000000
    assert orders[2]["attributes"]["statusChangeDate"] == 1740614400000


def test_process_store_status_date_mode_no_shadow_crash(tmp_path, monkeypatch):
    class DummyClient:
        def __init__(self, store_code: str):
            self.store_code = store_code

    monkeypatch.setattr("scripts.export_kaspi_archive_history.KaspiAPIClient", DummyClient)
    monkeypatch.setattr(
        "scripts.export_kaspi_archive_history._fetch_orders_window",
        lambda **_: [],
    )

    result = process_store(
        store_code="UNIVERSAL",
        windows=[(date(2026, 2, 20), date(2026, 2, 26))],
        since=date(2026, 2, 20),
        until=date(2026, 2, 26),
        out_root=tmp_path,
        fetch_entries=False,
        entry_workers=1,
        detail_workers=1,
        fetch_masterproduct=False,
        date_mode="statusChangeDate",
        hydrate_missing_status_change_date=True,
        require_status_change_date_for_completed=True,
        retries=1,
        retry_sleep=0.0,
        strict=True,
    )

    assert result.success is True
    assert result.windows_ok == 1
    assert result.orders_dedup == 0
    assert result.rows_exported == 0


def test_flatten_order_includes_courier_transmission_date():
    flat = _flatten_order(
        {
            "id": "oid-1",
            "type": "orders",
            "attributes": {
                "code": "123456789",
                "creationDate": 1740441600000,
                "statusChangeDate": 1740614400000,
                "kaspiDelivery": {
                    "courierTransmissionPlanningDate": 1740700800000,
                    "courierTransmissionDate": 1740787200000,
                },
            },
            "relationships": {"entries": {"data": []}},
        },
        "UNIVERSAL",
    )

    assert "courier_transmission_date" in flat
    assert flat["courier_transmission_date"] != ""
