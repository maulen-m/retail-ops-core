from __future__ import annotations

from pathlib import Path


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
