from scripts.report_waybill_status import compute_stopline_exit_code


def test_stopline_non_strict_mode_never_blocks() -> None:
    rc = compute_stopline_exit_code(
        strict_stopline=False,
        api_errors={"UNIVERSAL"},
        totals={"MISS_SIZE": 10, "MISS_PDF": 2, "MISS_BUNDLE": 1},
    )
    assert rc == 0


def test_stopline_blocks_on_api_error() -> None:
    rc = compute_stopline_exit_code(
        strict_stopline=True,
        api_errors={"UNIVERSAL"},
        totals={"MISS_SIZE": 0, "MISS_PDF": 0, "MISS_BUNDLE": 0},
    )
    assert rc == 1


def test_stopline_blocks_on_missing_waybill_artifacts() -> None:
    rc = compute_stopline_exit_code(
        strict_stopline=True,
        api_errors=set(),
        totals={"MISS_SIZE": 0, "MISS_PDF": 3, "MISS_BUNDLE": 0},
    )
    assert rc == 1


def test_stopline_passes_when_no_errors_and_no_missing() -> None:
    rc = compute_stopline_exit_code(
        strict_stopline=True,
        api_errors=set(),
        totals={"MISS_SIZE": 0, "MISS_PDF": 0, "MISS_BUNDLE": 0},
    )
    assert rc == 0
