from core.po.dashboard_math import round_half_up_1dp


def test_round_doc_half_up_ties() -> None:
    assert round_half_up_1dp(29.95) == 30.0
    assert round_half_up_1dp(60.75) == 60.8
    assert round_half_up_1dp(60.74) == 60.7
