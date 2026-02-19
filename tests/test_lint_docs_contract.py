from __future__ import annotations

from pathlib import Path


def test_lint_docs_blocks_deprecated_autonomous_business_2_reference() -> None:
    lint_script = Path("scripts/lint_docs.sh").read_text(encoding="utf-8")
    assert "Autonomous_business 2" in lint_script
