from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from scripts.triage_owner_truth_stoplines import triage_owner_truth_stoplines


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_triage_owner_truth_stoplines_pass(tmp_path: Path) -> None:
    as_of = "2026-03-04"
    _write(tmp_path / "exports" / "validation" / "identity_stabilization" / as_of / "validate_reference_freshness.json", {"status": "PASS", "ok": True})
    _write(tmp_path / "exports" / "validation" / "identity_stabilization" / as_of / "validate_external_snapshot_parity.json", {"status": "PASS", "ok": True})
    _write(tmp_path / "exports" / "validation" / "identity_stabilization" / as_of / "validate_recent_identity_coverage.json", {"status": "PASS", "ok": True})
    _write(tmp_path / "exports" / "validation" / "identity_stabilization" / as_of / "validate_order_entries_freshness.json", {"status": "PASS", "ok": True})
    _write(tmp_path / "exports" / "validation" / "ads_sidecar_readiness" / as_of / "ads_sidecar_readiness_report.json", {"status": "PASS", "ok": True})
    _write(tmp_path / "exports" / "validation" / "opex_readiness" / as_of / "opex_readiness_report.json", {"status": "PASS", "ok": True})
    _write(tmp_path / "exports" / "validation" / "returns_economics" / as_of / "returns_economics_report.json", {"status": "PASS", "ok": True})
    _write(tmp_path / "exports" / "validation" / "cash_reconciliation" / as_of / "cash_reconciliation_report.json", {"status": "PASS", "ok": True})
    _write(tmp_path / "exports" / "owner_pnl" / as_of / "OWNER_PNL.json", {"status": "PASS", "ok": True})
    _write(tmp_path / "exports" / "validation" / "crm_north_star_restate" / as_of / "sales_truth_vs_crm_report.json", {"status": "PASS", "ok": True})
    _write(tmp_path / "exports" / "validation" / "crm_north_star_restate" / as_of / "ads_offer_universe_report.json", {"status": "PASS", "ok": True})
    _write(tmp_path / "exports" / "validation" / "crm_north_star_restate" / as_of / "ads_spend_reality_report.json", {"status": "PASS", "ok": True})
    _write(tmp_path / "exports" / "validation" / "crm_north_star_restate" / as_of / "cogs_completeness_report.json", {"status": "PASS", "ok": True})
    _write(tmp_path / "exports" / "validation" / "crm_north_star_restate" / as_of / "cogs_realism_report.json", {"status": "PASS", "ok": True})
    _write(tmp_path / "exports" / "north_star_owner_review" / as_of / "publication_readiness.json", {"status": "PASS", "ok": True})

    summary = triage_owner_truth_stoplines(
        as_of=date(2026, 3, 4),
        project_root=tmp_path,
        truth_source="db",
        validation_dir=None,
        pack_root=None,
        ledger_root=None,
        download_run_id=None,
        output_path=None,
        strict=True,
    )
    assert summary["status"] == "PASS"
    assert summary["stopline_count"] == 0


def test_triage_owner_truth_stoplines_fails_when_missing(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        triage_owner_truth_stoplines(
            as_of=date(2026, 3, 4),
            project_root=tmp_path,
            truth_source="db",
            validation_dir=None,
            pack_root=None,
            ledger_root=None,
            download_run_id=None,
            output_path=None,
            strict=True,
        )


def test_triage_owner_truth_stoplines_webui_pass(tmp_path: Path) -> None:
    as_of = "2026-03-06"
    for name in [
        "validate_reference_freshness.json",
        "validate_external_snapshot_parity.json",
        "validate_recent_identity_coverage.json",
        "validate_order_entries_freshness.json",
    ]:
        _write(tmp_path / "exports" / "validation" / "identity_stabilization" / as_of / name, {"status": "PASS", "ok": True})
    for rel in [
        ("ads_sidecar_readiness", "ads_sidecar_readiness_report.json"),
        ("opex_readiness", "opex_readiness_report.json"),
        ("returns_economics", "returns_economics_report.json"),
        ("cash_reconciliation", "cash_reconciliation_report.json"),
    ]:
        _write(tmp_path / "exports" / "validation" / rel[0] / as_of / rel[1], {"status": "PASS", "ok": True})
    _write(tmp_path / "exports" / "owner_pnl" / as_of / "OWNER_PNL.json", {"status": "PASS", "ok": True})
    _write(tmp_path / "exports" / "north_star_owner_review" / as_of / "publication_readiness.json", {"status": "PASS", "ok": True})

    validation = tmp_path / "exports" / "validation" / "webui_archive_single_truth" / as_of
    for name in [
        "webui_truth_promotion_report.json",
        "webui_vs_db_report.json",
        "ads_offer_universe_report.json",
        "ads_spend_reality_report.json",
        "cogs_completeness_report.json",
        "cogs_realism_report.json",
        "order_status_audit_report.json",
    ]:
        _write(validation / name, {"status": "PASS", "ok": True})

    pack = tmp_path / "exports" / "webui_archive_packs" / "pack1"
    ledger = tmp_path / "exports" / "order_status_ledger" / "ledger1"
    run = tmp_path / "exports" / "webui_archive_download_runs" / "run1"
    _write(pack / "integrity_report.json", {"status": "PASS", "ok": True})
    _write(ledger / "continuity_report.json", {"status": "PASS", "ok": True})
    _write(run / "download_validation.json", {"status": "PASS", "ok": True})

    summary = triage_owner_truth_stoplines(
        as_of=date(2026, 3, 6),
        project_root=tmp_path,
        truth_source="webui_archive",
        validation_dir=validation,
        pack_root=pack,
        ledger_root=ledger,
        download_run_id=str(run),
        output_path=None,
        strict=True,
    )
    assert summary["status"] == "PASS"


def test_triage_owner_truth_stoplines_webui_fallback_contract_pass(tmp_path: Path) -> None:
    as_of = "2026-03-07"
    for name in [
        "validate_reference_freshness.json",
        "validate_external_snapshot_parity.json",
        "validate_recent_identity_coverage.json",
        "validate_order_entries_freshness.json",
    ]:
        _write(tmp_path / "exports" / "validation" / "identity_stabilization" / as_of / name, {"status": "PASS", "ok": True})
    for rel in [
        ("ads_sidecar_readiness", "ads_sidecar_readiness_report.json"),
        ("opex_readiness", "opex_readiness_report.json"),
        ("returns_economics", "returns_economics_report.json"),
        ("cash_reconciliation", "cash_reconciliation_report.json"),
    ]:
        _write(tmp_path / "exports" / "validation" / rel[0] / as_of / rel[1], {"status": "PASS", "ok": True})
    _write(tmp_path / "exports" / "owner_pnl" / as_of / "OWNER_PNL.json", {"status": "PASS", "ok": True})
    _write(tmp_path / "exports" / "north_star_owner_review" / as_of / "publication_readiness.json", {"status": "PASS", "ok": True})

    validation = tmp_path / "exports" / "validation" / "webui_archive_single_truth" / as_of
    _write(validation / "shipped_day_authority_decision.json", {"status": "PASS", "ok": True, "decision": "CRM_REMAINS_CHRONOLOGY_AUTHORITY"})
    _write(validation / "sales_against_workbook_report.json", {"status": "PASS", "ok": True})
    for name in [
        "webui_vs_db_report.json",
        "ads_offer_universe_report.json",
        "ads_spend_reality_report.json",
        "cogs_completeness_report.json",
        "cogs_realism_report.json",
        "order_status_audit_report.json",
    ]:
        _write(validation / name, {"status": "PASS", "ok": True})

    pack = tmp_path / "exports" / "webui_archive_packs" / "pack1"
    ledger = tmp_path / "exports" / "order_status_ledger" / "ledger1"
    run = tmp_path / "exports" / "webui_archive_download_runs" / "run1"
    _write(pack / "integrity_report.json", {"status": "PASS", "ok": True})
    _write(ledger / "continuity_report.json", {"status": "PASS", "ok": True})
    _write(run / "download_validation.json", {"status": "PASS", "ok": True})

    summary = triage_owner_truth_stoplines(
        as_of=date(2026, 3, 7),
        project_root=tmp_path,
        truth_source="webui_archive",
        validation_dir=validation,
        pack_root=pack,
        ledger_root=ledger,
        download_run_id=str(run),
        output_path=None,
        strict=True,
    )
    assert summary["status"] == "PASS"


def test_triage_owner_truth_stoplines_db_uses_publication_validation_fallback(tmp_path: Path) -> None:
    as_of = "2026-03-07"
    for name in [
        "validate_reference_freshness.json",
        "validate_external_snapshot_parity.json",
        "validate_recent_identity_coverage.json",
        "validate_order_entries_freshness.json",
    ]:
        _write(tmp_path / "exports" / "validation" / "identity_stabilization" / as_of / name, {"status": "PASS", "ok": True})
    for rel in [
        ("ads_sidecar_readiness", "ads_sidecar_readiness_report.json"),
        ("opex_readiness", "opex_readiness_report.json"),
        ("returns_economics", "returns_economics_report.json"),
        ("cash_reconciliation", "cash_reconciliation_report.json"),
    ]:
        _write(tmp_path / "exports" / "validation" / rel[0] / as_of / rel[1], {"status": "PASS", "ok": True})
    _write(tmp_path / "exports" / "owner_pnl" / as_of / "OWNER_PNL.json", {"status": "PASS", "ok": True})

    fallback_validation = tmp_path / "exports" / "validation" / "ads_scope_closeout" / "2026-03-08"
    for name in [
        "sales_against_workbook_report.json",
        "ads_offer_universe_report.json",
        "ads_spend_reality_report.json",
        "cogs_completeness_report.json",
        "cogs_realism_report.json",
    ]:
        _write(fallback_validation / name, {"status": "PASS", "ok": True})

    _write(
        tmp_path / "exports" / "north_star_owner_review" / as_of / "publication_readiness.json",
        {
            "status": "PASS",
            "ok": True,
            "truth_source": "webui_archive",
            "gates": {
                "workbook_chronology_anchor": {
                    "status": "PASS",
                    "ok": True,
                    "path": str(fallback_validation / "sales_against_workbook_report.json"),
                },
                "ads_offer_universe": {
                    "status": "PASS",
                    "ok": True,
                    "path": str(fallback_validation / "ads_offer_universe_report.json"),
                },
                "ads_spend_reality": {
                    "status": "PASS",
                    "ok": True,
                    "path": str(fallback_validation / "ads_spend_reality_report.json"),
                },
                "cogs_completeness": {
                    "status": "PASS",
                    "ok": True,
                    "path": str(fallback_validation / "cogs_completeness_report.json"),
                },
                "cogs_realism": {
                    "status": "PASS",
                    "ok": True,
                    "path": str(fallback_validation / "cogs_realism_report.json"),
                },
            },
        },
    )

    summary = triage_owner_truth_stoplines(
        as_of=date(2026, 3, 7),
        project_root=tmp_path,
        truth_source="db",
        validation_dir=None,
        pack_root=None,
        ledger_root=None,
        download_run_id=None,
        output_path=None,
        strict=True,
    )

    assert summary["status"] == "PASS"
    assert summary["validation_dir"].endswith("/exports/validation/ads_scope_closeout/2026-03-08")
