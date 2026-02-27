from datetime import date

from scripts.export_kaspi_archive_history import WINDOW_DAYS, date_windows


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
