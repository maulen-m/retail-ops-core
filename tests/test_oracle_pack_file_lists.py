from pathlib import Path


def test_primary_pack_includes_workbook_anchor_comparator_chain() -> None:
    content = Path("Oracle_listings/oracle_pack_file_lists.md").read_text(encoding="utf-8")
    assert "scripts/validate_sales_vs_workbook_anchor.py" in content
    assert "scripts/validate_sales_against_workbook.py" in content
