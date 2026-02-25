from __future__ import annotations

from pathlib import Path

from scripts.lint_docs_active_scope import lint_active_docs


def test_active_docs_no_schedule_contradictions(tmp_path: Path) -> None:
    bad_doc = tmp_path / "bad_active_doc.md"
    bad_doc.write_text(
        "# Bad Active Doc\n\nCurrent scheduler contract: 11:00 and 16:05.\n",
        encoding="utf-8",
    )
    report = lint_active_docs(
        project_root=Path(".").resolve(),
        docs=[bad_doc],
        strict=False,
    )
    assert report["ok"] is False
    assert any("16:05" in err for err in report["errors"])


def test_active_docs_lint_passes_on_repo_scope() -> None:
    report = lint_active_docs(
        project_root=Path(".").resolve(),
        docs=None,
        strict=False,
    )
    assert report["ok"] is True

