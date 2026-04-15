from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from scripts.triage_owner_truth_stoplines import triage_owner_truth_stoplines


def _write_pass_json(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"status": "PASS", "ok": True}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_triage_allows_missing_publication_readiness_when_explicit(tmp_path: Path) -> None:
    as_of = "2026-03-08"
    validation_dir = tmp_path / "exports" / "validation" / "ads_scope_closeout" / as_of
    validation_dir.mkdir(parents=True, exist_ok=True)
    for name in [
        "ads_offer_universe_report.json",
        "ads_spend_reality_report.json",
        "cogs_completeness_report.json",
        "cogs_realism_report.json",
        "order_status_audit_report.json",
        "sales_against_workbook_report.json",
        "webui_vs_db_report.json",
    ]:
        _write_pass_json(validation_dir / name)
    (validation_dir / "shipped_day_authority_decision.json").write_text(
        json.dumps(
            {"status": "PASS", "ok": True, "decision": "CRM_REMAINS_CHRONOLOGY_AUTHORITY"},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    for path in [
        tmp_path / "exports" / "validation" / "identity_stabilization" / as_of / "validate_reference_freshness.json",
        tmp_path / "exports" / "validation" / "identity_stabilization" / as_of / "validate_external_snapshot_parity.json",
        tmp_path / "exports" / "validation" / "identity_stabilization" / as_of / "validate_recent_identity_coverage.json",
        tmp_path / "exports" / "validation" / "identity_stabilization" / as_of / "validate_order_entries_freshness.json",
        tmp_path / "exports" / "validation" / "ads_sidecar_readiness" / as_of / "ads_sidecar_readiness_report.json",
        tmp_path / "exports" / "validation" / "opex_readiness" / as_of / "opex_readiness_report.json",
        tmp_path / "exports" / "validation" / "returns_economics" / as_of / "returns_economics_report.json",
        tmp_path / "exports" / "validation" / "cash_reconciliation" / as_of / "cash_reconciliation_report.json",
        tmp_path / "exports" / "owner_pnl" / as_of / "OWNER_PNL.json",
        tmp_path / "exports" / "webui_archive_packs" / "pack" / "integrity_report.json",
        tmp_path / "exports" / "order_status_ledger" / "ledger" / "continuity_report.json",
        tmp_path / "exports" / "webui_archive_download_runs" / "run" / "download_validation.json",
    ]:
        _write_pass_json(path)

    report = triage_owner_truth_stoplines(
        as_of=date.fromisoformat(as_of),
        project_root=tmp_path,
        truth_source="webui_archive",
        validation_dir=validation_dir,
        pack_root=tmp_path / "exports" / "webui_archive_packs" / "pack",
        ledger_root=tmp_path / "exports" / "order_status_ledger" / "ledger",
        download_run_id=str(tmp_path / "exports" / "webui_archive_download_runs" / "run"),
        output_path=tmp_path / "exports" / "daily" / as_of / "owner_truth_summary.json",
        strict=True,
        allow_missing_publication_readiness=True,
    )

    assert report["status"] == "PASS"
    publication_row = next(row for row in report["checks"] if row["check"] == "north_star_publication_readiness")
    assert publication_row["status"] == "SKIPPED"
    assert publication_row["ok"] is True


def test_triage_requires_publication_readiness_without_allowance(tmp_path: Path) -> None:
    as_of = "2026-03-08"
    validation_dir = tmp_path / "exports" / "validation" / "ads_scope_closeout" / as_of
    validation_dir.mkdir(parents=True, exist_ok=True)

    with pytest.raises(RuntimeError, match="owner truth stoplines present"):
        triage_owner_truth_stoplines(
            as_of=date.fromisoformat(as_of),
            project_root=tmp_path,
            truth_source="webui_archive",
            validation_dir=validation_dir,
            pack_root=None,
            ledger_root=None,
            download_run_id=None,
            output_path=tmp_path / "exports" / "daily" / as_of / "owner_truth_summary.json",
            strict=True,
            allow_missing_publication_readiness=False,
        )


def test_triage_replay_mode_uses_identity_replay_anchor_instead_of_live_identity_artifacts(tmp_path: Path) -> None:
    as_of = "2026-03-19"
    validation_dir = tmp_path / "exports" / "validation" / "webui_archive_single_truth" / as_of
    validation_dir.mkdir(parents=True, exist_ok=True)
    for name in [
        "ads_offer_universe_report.json",
        "ads_spend_reality_report.json",
        "cogs_completeness_report.json",
        "cogs_realism_report.json",
        "order_status_audit_report.json",
        "sales_against_workbook_report.json",
        "webui_vs_db_report.json",
    ]:
        _write_pass_json(validation_dir / name)
    (validation_dir / "shipped_day_authority_decision.json").write_text(
        json.dumps(
            {"status": "PASS", "ok": True, "decision": "CRM_REMAINS_CHRONOLOGY_AUTHORITY"},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    for path in [
        tmp_path / "exports" / "validation" / "identity_stabilization" / as_of / "validate_reference_freshness.json",
        tmp_path / "exports" / "validation" / "identity_replay_anchor" / as_of / "validate_identity_replay_anchor.json",
        tmp_path / "exports" / "validation" / "ads_sidecar_readiness" / as_of / "ads_sidecar_readiness_report.json",
        tmp_path / "exports" / "validation" / "opex_readiness" / as_of / "opex_readiness_report.json",
        tmp_path / "exports" / "validation" / "returns_economics" / as_of / "returns_economics_report.json",
        tmp_path / "exports" / "validation" / "cash_reconciliation" / as_of / "cash_reconciliation_report.json",
        tmp_path / "exports" / "owner_pnl" / as_of / "OWNER_PNL.json",
        tmp_path / "exports" / "north_star_owner_review" / as_of / "publication_readiness.json",
        tmp_path / "exports" / "webui_archive_packs" / "pack" / "integrity_report.json",
        tmp_path / "exports" / "order_status_ledger" / "ledger" / "continuity_report.json",
        tmp_path / "exports" / "webui_archive_download_runs" / "run" / "download_validation.json",
    ]:
        _write_pass_json(path)

    report = triage_owner_truth_stoplines(
        as_of=date.fromisoformat(as_of),
        project_root=tmp_path,
        truth_source="webui_archive",
        validation_dir=validation_dir,
        pack_root=tmp_path / "exports" / "webui_archive_packs" / "pack",
        ledger_root=tmp_path / "exports" / "order_status_ledger" / "ledger",
        download_run_id=str(tmp_path / "exports" / "webui_archive_download_runs" / "run"),
        output_path=tmp_path / "exports" / "daily" / as_of / "owner_truth_summary.json",
        strict=True,
        allow_missing_publication_readiness=False,
        runtime_mode="replay",
    )

    assert report["status"] == "PASS"
    check_names = {row["check"] for row in report["checks"]}
    assert "identity_replay_anchor" in check_names
    assert "external_snapshot_parity" not in check_names
    assert "recent_identity_coverage" not in check_names
    assert "order_entries_freshness" not in check_names
