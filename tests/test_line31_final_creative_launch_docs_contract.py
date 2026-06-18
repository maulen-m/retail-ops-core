from __future__ import annotations

from pathlib import Path


DOC_PATHS = [
    Path("docs/validation/LINE31_FINAL_CREATIVE_LAUNCH_READINESS_CONTRACT.md"),
    Path("docs/parallel_runs/2026-06-01_line31_final_creative_meta_publish/PLAN.md"),
    Path(
        "docs/agent_handoffs/LINE31_FINAL_CREATIVE_META_PUBLISH_20260601_STARTERS/"
        "01_AGENT_1__FINAL_CREATIVE_META_PUBLISH__SERIAL.md"
    ),
]


def test_line31_final_creative_docs_require_drop_validator() -> None:
    for path in DOC_PATHS:
        text = path.read_text(encoding="utf-8")

        assert "validate_line31_final_creative_drop_intake.py" in text, path
        assert "validate_line31_current_final_creative_drop.py" in text, path


def test_line31_final_creative_contract_has_no_old_demo_urls() -> None:
    contract = DOC_PATHS[0].read_text(encoding="utf-8")

    assert "example-cdn" not in contract
    assert "kaspi.kz/shop/..." not in contract
    assert "REPLACE_WITH_FINAL_VIDEO" in contract
    assert "REPLACE_WITH_FINAL_LINE31_PRODUCT_SLUG" in contract


def test_line31_final_creative_handoff_uses_current_matrix_not_stale_round3() -> None:
    handoff = DOC_PATHS[2].read_text(encoding="utf-8")

    assert "CURRENT_NONCREATIVE_GATE_MATRIX.json" in handoff
    assert "do not stop solely because the older Round 3 historical matrix" in handoff
    assert "stop before publish if it remains `YELLOW`" not in handoff


def test_line31_final_creative_docs_list_owner_source_freshness_verifier() -> None:
    for path in DOC_PATHS:
        text = path.read_text(encoding="utf-8")

        assert "validate_line31_owner_objective_source_freshness.py --json" in text, path


def test_line31_final_creative_contract_requires_explicit_reserve_proof() -> None:
    contract = DOC_PATHS[0].read_text(encoding="utf-8")

    assert "protected reserve proof" in contract
    assert "expected_min_kzt=800000" in contract


def test_line31_final_creative_contract_requires_preflight_source_freshness_artifact() -> None:
    contract = DOC_PATHS[0].read_text(encoding="utf-8")

    assert "owner_objective_source_freshness.json" in contract
    assert "line31_launch_preflight_summary.md" in contract


def test_line31_final_creative_contract_requires_tracking_redirect_qa_evidence() -> None:
    contract = DOC_PATHS[0].read_text(encoding="utf-8")

    assert "--tracking-qa-evidence-file" in contract
    assert "tracking_redirect_qa.evidence_sha256" in contract
    assert "fake-ecommerce fail-closed checks" in contract


def test_line31_final_creative_docs_separate_advisory_repo_health_from_line31_blockers() -> None:
    for path in DOC_PATHS:
        text = path.read_text(encoding="utf-8")

        assert "repo_wide_advisory" in text, path
        assert "LINE31 launch" in text, path


def test_line31_final_creative_docs_list_current_status_writer() -> None:
    for path in DOC_PATHS:
        text = path.read_text(encoding="utf-8")

        assert "write_line31_current_launch_status.py --json" in text, path


def test_line31_final_creative_docs_route_through_latest_drop_checklist() -> None:
    for path in DOC_PATHS:
        text = path.read_text(encoding="utf-8")

        assert "LINE31_LAUNCH_CURRENT_STATUS.json" in text, path
        assert "latest_drop_intake.checklist_path" in text, path
        assert "FINAL_CREATIVE_DROP_CHECKLIST.json" in text, path
        assert "do not hard-code an older timestamped drop" in text, path
