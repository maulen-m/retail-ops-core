from scripts.export_api_orders import filter_rows_by_planned_date


def test_filter_rows_by_planned_date_exact():
    rows = [
        {"Плановая дата передачи курьеру": "01.01.2026"},
        {"Плановая дата передачи курьеру": "03.01.2026"},
    ]

    filtered = filter_rows_by_planned_date(
        rows, target_date="03.01.2026", include_overdue=False
    )

    assert len(filtered) == 1
    assert filtered[0]["Плановая дата передачи курьеру"] == "03.01.2026"


def test_filter_rows_by_planned_date_include_overdue():
    rows = [
        {"Плановая дата передачи курьеру": "01.01.2026"},
        {"Плановая дата передачи курьеру": "03.01.2026"},
        {"Плановая дата передачи курьеру": "05.01.2026"},
    ]

    filtered = filter_rows_by_planned_date(
        rows, target_date="03.01.2026", include_overdue=True
    )

    planned = [row["Плановая дата передачи курьеру"] for row in filtered]
    assert planned == ["01.01.2026", "03.01.2026"]
