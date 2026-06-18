from __future__ import annotations

from pathlib import Path


def test_lint_docs_blocks_deprecated_autonomous_business_2_reference() -> None:
    lint_script = Path("scripts/lint_docs.sh").read_text(encoding="utf-8")
    assert "Autonomous_business 2" in lint_script


def test_lint_docs_blocks_user_specific_absolute_paths_except_anchor_readme() -> None:
    lint_script = Path("scripts/lint_docs.sh").read_text(encoding="utf-8")
    assert "~/" in lint_script
    assert "config/anchors/README.md" in lint_script


def test_lint_docs_allows_green_path_numeric_evidence_only() -> None:
    lint_script = Path("scripts/lint_docs.sh").read_text(encoding="utf-8")
    assert "LEGACY_NUMERIC_PATTERNS" in lint_script
    assert "GREEN_PATH_PLAN_NUMERIC_ALLOWLIST" in lint_script
    assert "!docs/plan/green_path_2026-06/**" in lint_script
