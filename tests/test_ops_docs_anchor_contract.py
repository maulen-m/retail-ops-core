from __future__ import annotations

from pathlib import Path


def test_daily_sop_uses_repo_anchor_paths_only() -> None:
    sop = Path("docs/DAILY_SOP.md").read_text(encoding="utf-8")
    assert "Autonomous_business 2" not in sop
    assert "~/Docs/Autonomous_business/config/anchors/SALES_KSP_CRM_LATEST.xlsx" in sop
    assert "~/Docs/Autonomous_business/config/anchors/INBOUND_CALENDAR_LATEST.xlsx" in sop


def test_anchor_readme_contains_both_canonical_symlink_contracts() -> None:
    readme = Path("config/anchors/README.md").read_text(encoding="utf-8")
    assert "SALES_KSP_CRM_LATEST.xlsx" in readme
    assert "INBOUND_CALENDAR_LATEST.xlsx" in readme
