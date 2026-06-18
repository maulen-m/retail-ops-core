from __future__ import annotations

from pathlib import Path

from scripts.generate_po_dashboard_data import drop_zero_size_demand_aliases


def test_po_dashboard_generator_does_not_read_raw_sales_tables() -> None:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "generate_po_dashboard_data.py"
    text = script_path.read_text(encoding="utf-8")

    disallowed_markers = [
        "FROM fact_sales",
        "from fact_sales",
        "FROM sales_fact_v2",
        "from sales_fact_v2",
        "FROM fact_sales_daily",
        "from fact_sales_daily",
        "FROM fact_sales_daily_size",
        "from fact_sales_daily_size",
    ]

    violations = [marker for marker in disallowed_markers if marker in text]

    assert not violations, f"raw sales sources detected in PO dashboard generator: {violations}"


def test_zero_demand_size_aliases_do_not_overwrite_real_size_demand() -> None:
    demands, sales = drop_zero_size_demand_aliases(
        {
            "S": 0.42,
            "42": 0.0,
            "M": 0.58,
        },
        {
            "S": 38,
            "42": 0,
            "M": 52,
        },
    )

    assert demands == {"S": 0.42, "M": 0.58}
    assert sales == {"S": 38, "M": 52}
