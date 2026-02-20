from scripts.update_cashflow_dashboard import _max_sync_age


def test_max_sync_age():
    assert _max_sync_age({"A": 1.2, "B": 0.5}) == 1.2
    assert _max_sync_age({}) is None
