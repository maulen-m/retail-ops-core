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


def test_start_here_points_to_docs_daily_sop() -> None:
    index_doc = Path("docs/00_START_HERE.md").read_text(encoding="utf-8")
    assert "docs/DAILY_SOP.md" in index_doc
    assert "\n1. `DAILY_SOP.md`\n" not in index_doc


def test_docs_daily_sop_declares_anchor_readme_authority() -> None:
    sop = Path("docs/DAILY_SOP.md").read_text(encoding="utf-8")
    assert "config/anchors/README.md" in sop
    assert "authoritative" in sop.lower()


def test_root_daily_sop_has_no_absolute_workbook_paths() -> None:
    root_sop = Path("DAILY_SOP.md")
    if not root_sop.exists():
        return
    text = root_sop.read_text(encoding="utf-8")
    assert "~/Docs/Autonomous_business/config/anchors/" not in text
    assert "Autonomous_business 2" not in text


def test_stopline_plan_has_no_deprecated_autonomous_business_2_path() -> None:
    plan = Path("docs/PLAN_SINGLE_TRUTH_OPS_STOP_THE_LINE_CLEARING_V2_1_2026-02-18.md").read_text(
        encoding="utf-8"
    )
    assert "Autonomous_business 2" not in plan
    assert "config/anchors/README.md" in plan
