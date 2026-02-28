from datetime import date

from scripts.export_kaspi_archive_history import (
    WINDOW_DAYS,
    _hydrate_missing_status_change_dates,
    _order_matches_date_mode,
    date_windows,
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
