from __future__ import annotations

from pathlib import Path


def test_board_v4_canonical_reference_docs_exist() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    required_paths = [
        repo_root / "docs" / "ops" / "STOCK_SNAPSHOT_RUNBOOK.md",
        repo_root / "docs" / "marketing" / "ADS_SIDECAR_OPS_RUNBOOK.md",
        repo_root / "docs" / "offer" / "OFFER_LINKAGE_STRICT_CUTOVER_PLAN.md",
        repo_root / "docs" / "ops" / "WRITE_CANARY_PLAN_V1.md",
    ]
    missing = [str(path) for path in required_paths if not path.exists()]
    assert not missing, "missing V4 canonical docs: " + ", ".join(missing)


def test_board_v4_new_ops_docs_do_not_use_personal_absolute_paths() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    doc_paths = [
        repo_root / "docs" / "ops" / "STOCK_SNAPSHOT_RUNBOOK.md",
        repo_root / "docs" / "marketing" / "ADS_SIDECAR_OPS_RUNBOOK.md",
        repo_root / "docs" / "offer" / "OFFER_LINKAGE_STRICT_CUTOVER_PLAN.md",
        repo_root / "docs" / "ops" / "WRITE_CANARY_PLAN_V1.md",
        repo_root / "docs" / "po" / "PO_MONEY_GATE_CONTRACT.md",
    ]
    for doc_path in doc_paths:
        text = doc_path.read_text(encoding="utf-8")
        assert "/Users/" not in text, f"personal absolute path found in {doc_path}"
