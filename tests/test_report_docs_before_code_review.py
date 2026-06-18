from __future__ import annotations

from scripts.report_docs_before_code_review import classify_review, is_reviewable_source


def test_classify_review_passes_when_domain_doc_changed() -> None:
    report = classify_review(
        [
            "core/calc/economics.py",
            "docs/inventory/Sales_Data_Model_V16.md",
        ]
    )

    assert report["ok"] is True
    assert report["blockers"] == []
    assert report["domains"][0]["domain"] == "sales_cogs_profit"
    assert report["domains"][0]["status"] == "doc_updated"


def test_classify_review_blocks_when_domain_doc_missing() -> None:
    report = classify_review(["core/calc/economics.py"])

    assert report["ok"] is False
    assert "sales_cogs_profit: no owning doc changed" in report["blockers"]


def test_classify_review_blocks_unmatched_source_file() -> None:
    report = classify_review(["core/new_domain/rules.py"])

    assert report["ok"] is False
    assert "unmatched business-rule source/config: core/new_domain/rules.py" in report["blockers"]


def test_classify_review_ignores_docs_tests_and_runtime() -> None:
    changed = [
        "docs/validation/SOME_DOC.md",
        "tests/test_something.py",
        "runtime/playwright/session.json",
    ]
    report = classify_review(changed)

    assert report["ok"] is True
    assert report["reviewable_source_files"] == []
    assert all(not is_reviewable_source(path) for path in changed)


def test_config_json_source_is_reviewable_before_generic_json_ignore() -> None:
    assert is_reviewable_source("config/business_automation_manifest.json") is True

    report = classify_review(
        [
            "config/business_automation_manifest.json",
            "docs/validation/DOCS_BEFORE_CODE_CHANGE_REVIEW.md",
        ]
    )

    assert report["ok"] is True
    assert report["domains"][0]["domain"] == "repo_guard_docs"
