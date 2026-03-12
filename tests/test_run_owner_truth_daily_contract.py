from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pytest

import scripts.run_owner_truth_daily as runner_mod
from scripts.run_owner_truth_daily import OwnerTruthDailyError, run_owner_truth_daily


def _seed_crm_anchor(project_root: Path) -> Path:
    anchor = project_root / "config" / "anchors" / "SALES_KSP_CRM_LATEST.xlsx"
    anchor.parent.mkdir(parents=True, exist_ok=True)
    anchor.write_text("anchor", encoding="utf-8")
    return anchor


def test_run_owner_truth_daily_requires_env_for_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENABLE_OWNER_TRUTH_APPLY", raising=False)
    with pytest.raises(OwnerTruthDailyError):
        run_owner_truth_daily(
            as_of=date(2026, 3, 4),
            since=date(2025, 6, 6),
            north_star_start=date(2026, 1, 1),
            north_star_end=date(2026, 2, 28),
            project_root=tmp_path,
            output_root=tmp_path / "out",
            summary_root=tmp_path / "daily",
            strict=True,
            apply=True,
        )


def test_run_owner_truth_daily_writes_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    _seed_crm_anchor(tmp_path)

    def fake_run(cmd: str, *, cwd: Path, env=None):
        calls.append(cmd)
        if "backup_db.py" in cmd:
            return 0, "Backup created: runtime/backups/app_2026-03-05_010101.db.gz", 0.01
        return 0, "status=PASS", 0.01

    monkeypatch.setenv("ENABLE_OWNER_TRUTH_APPLY", "1")
    monkeypatch.setattr(runner_mod, "_run", fake_run)

    summary = run_owner_truth_daily(
        as_of=date(2026, 3, 4),
        since=date(2025, 6, 6),
        north_star_start=date(2026, 1, 1),
        north_star_end=date(2026, 2, 28),
        project_root=tmp_path,
        output_root=tmp_path / "out",
        summary_root=tmp_path / "daily",
        strict=True,
        apply=True,
        runtime_mode="live",
    )
    assert summary["status"] == "PASS"
    assert summary["backup_path"] is not None
    assert (tmp_path / "daily" / "2026-03-04" / "owner_truth_summary.json").exists()
    assert (tmp_path / "out" / "2026-03-04" / "full_run_transcript.md").exists()
    assert any("build_owner_pnl_report.py" in cmd for cmd in calls)


def test_run_owner_truth_daily_webui_includes_webui_contract_steps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    _seed_crm_anchor(tmp_path)

    def fake_run(cmd: str, *, cwd: Path, env=None):
        calls.append(cmd)
        return 0, "status=PASS", 0.01

    monkeypatch.setattr(runner_mod, "_run", fake_run)

    summary = run_owner_truth_daily(
        as_of=date(2026, 3, 6),
        since=date(2025, 6, 6),
        north_star_start=date(2026, 1, 1),
        north_star_end=date(2026, 2, 28),
        project_root=tmp_path,
        output_root=tmp_path / "out",
        summary_root=tmp_path / "daily",
        strict=True,
        apply=False,
        truth_source="webui_archive",
        validation_dir=tmp_path / "validation",
        pack_root=tmp_path / "pack",
        ledger_root=tmp_path / "ledger",
        download_run_id="download_run",
        runtime_mode="live",
    )

    assert summary["status"] == "PASS"
    joined = "\n".join(calls)
    assert "validate_webui_archive_pack_integrity.py" in joined
    assert "validate_status_ledger_continuity.py" in joined
    assert "validate_webui_crm_shipped_day_authority.py" in joined
    assert "validate_sales_against_workbook.py" in joined
    assert "validate_order_status_audit_history.py" in joined
    assert "--truth-source webui_archive" in joined
    reference_cmd = next(cmd for cmd in calls if "validate_reference_freshness.py" in cmd)
    assert "--statusdate-cutover 2026-02-27" in reference_cmd


def test_run_owner_truth_daily_applies_workbook_catalog_sync_before_truth_steps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, str] | None]] = []
    _seed_crm_anchor(tmp_path)

    def fake_run(cmd: str, *, cwd: Path, env=None):
        calls.append((cmd, env))
        if "backup_db.py" in cmd:
            return 0, "Backup created: runtime/backups/app_2026-03-08_010101.db.gz", 0.01
        return 0, "status=PASS", 0.01

    monkeypatch.setenv("ENABLE_OWNER_TRUTH_APPLY", "1")
    monkeypatch.setattr(runner_mod, "_run", fake_run)

    summary = run_owner_truth_daily(
        as_of=date(2026, 3, 8),
        since=date(2025, 6, 6),
        north_star_start=date(2026, 1, 1),
        north_star_end=date(2026, 2, 28),
        project_root=tmp_path,
        output_root=tmp_path / "out",
        summary_root=tmp_path / "daily",
        strict=True,
        apply=True,
        truth_source="webui_archive",
        validation_dir=tmp_path / "validation",
        pack_root=tmp_path / "pack",
        ledger_root=tmp_path / "ledger",
        download_run_id="download_run",
        runtime_mode="live",
    )

    assert summary["status"] == "PASS"
    commands = [cmd for cmd, _env in calls]
    sync_idx = next(i for i, cmd in enumerate(commands) if "import_kaspi_article_map_from_crm.py" in cmd)
    doctor_idx = next(i for i, cmd in enumerate(commands) if "system_doctor.py" in cmd)
    assert sync_idx < doctor_idx
    sync_env = calls[sync_idx][1]
    assert sync_env is not None
    assert sync_env["ENABLE_KASPI_WORKBOOK_MAP_SYNC"] == "1"


def test_run_owner_truth_daily_parser_default_north_star_end_is_valid() -> None:
    parser = runner_mod._build_parser()
    args = parser.parse_args(["--as-of", "2026-03-08"])

    assert args.north_star_end == "2026-02-28"
    assert args.truth_source == "webui_archive"


def test_run_owner_truth_daily_db_uses_workbook_anchor_not_legacy_crm_validator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    _seed_crm_anchor(tmp_path)

    def fake_run(cmd: str, *, cwd: Path, env=None):
        calls.append(cmd)
        return 0, "status=PASS", 0.01

    monkeypatch.setattr(runner_mod, "_run", fake_run)

    summary = run_owner_truth_daily(
        as_of=date(2026, 3, 8),
        since=date(2025, 6, 6),
        north_star_start=date(2026, 1, 1),
        north_star_end=date(2026, 2, 28),
        project_root=tmp_path,
        output_root=tmp_path / "out",
        summary_root=tmp_path / "daily",
        strict=True,
        apply=False,
        truth_source="db",
        validation_dir=tmp_path / "validation",
    )

    assert summary["status"] == "PASS"
    joined = "\n".join(calls)
    assert "validate_sales_against_workbook.py" in joined
    assert "validate_sales_truth_vs_crm_north_star.py" not in joined


def test_run_owner_truth_daily_emits_daily_ops_artifact_after_live_ops_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    _seed_crm_anchor(tmp_path)

    def fake_run(cmd: str, *, cwd: Path, env=None):
        calls.append(cmd)
        if "run_kaspi_daily_ops.py" in cmd:
            return 1, "summary_md=/tmp/daily_ops_summary.md", 0.01
        return 0, "status=PASS", 0.01

    monkeypatch.setattr(runner_mod, "_run", fake_run)

    with pytest.raises(OwnerTruthDailyError, match="RUN_KASPI_DAILY_OPS_FAIL"):
        run_owner_truth_daily(
            as_of=date(2026, 3, 9),
            since=date(2025, 6, 6),
            north_star_start=date(2026, 1, 1),
            north_star_end=date(2026, 2, 28),
            project_root=tmp_path,
            output_root=tmp_path / "out",
            summary_root=tmp_path / "daily",
            strict=True,
            apply=False,
            runtime_mode="live",
        )

    joined = "\n".join(calls)
    assert "run_kaspi_daily_ops.py" in joined
    assert "generate_daily_ops_report.py" in joined
    assert "validate_daily_ops_report.py" in joined


def test_run_owner_truth_daily_live_uses_live_ads_readiness_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    _seed_crm_anchor(tmp_path)

    def fake_run(cmd: str, *, cwd: Path, env=None):
        calls.append(cmd)
        return 0, "status=PASS", 0.01

    monkeypatch.setattr(runner_mod, "_run", fake_run)

    summary = run_owner_truth_daily(
        as_of=date(2026, 3, 9),
        since=date(2025, 6, 6),
        north_star_start=date(2026, 1, 1),
        north_star_end=date(2026, 2, 28),
        project_root=tmp_path,
        output_root=tmp_path / "out",
        summary_root=tmp_path / "daily",
        strict=True,
        apply=False,
        runtime_mode="live",
    )

    assert summary["status"] == "PASS"
    ads_cmd = next(cmd for cmd in calls if "validate_ads_sidecar_readiness.py" in cmd)
    assert "--readiness-mode live" in ads_cmd


def test_run_owner_truth_daily_uses_publication_fallback_validation_dir_for_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    _seed_crm_anchor(tmp_path)

    def fake_run(cmd: str, *, cwd: Path, env=None):
        calls.append(cmd)
        return 0, "status=PASS", 0.01

    monkeypatch.setattr(runner_mod, "_run", fake_run)

    publication_dir = tmp_path / "exports" / "north_star_owner_review" / "2026-03-08"
    publication_dir.mkdir(parents=True, exist_ok=True)
    fallback_validation = tmp_path / "exports" / "validation" / "ads_scope_closeout" / "2026-03-08"
    fallback_validation.mkdir(parents=True, exist_ok=True)
    report_path = fallback_validation / "sales_against_workbook_report.json"
    report_path.write_text(
        json.dumps({"status": "PASS", "ok": True}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (publication_dir / "publication_readiness.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "truth_source": "webui_archive",
                "gates": {
                    "workbook_chronology_anchor": {
                        "status": "PASS",
                        "path": str(report_path),
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    summary = run_owner_truth_daily(
        as_of=date(2026, 3, 8),
        since=date(2025, 6, 6),
        north_star_start=date(2026, 1, 1),
        north_star_end=date(2026, 2, 28),
        project_root=tmp_path,
        output_root=tmp_path / "out",
        summary_root=tmp_path / "daily",
        strict=True,
        apply=False,
        truth_source="db",
        runtime_mode="live",
    )

    assert summary["status"] == "PASS"
    doctor_cmd = next(cmd for cmd in calls if "system_doctor.py" in cmd)
    assert "ads_scope_closeout/2026-03-08" in doctor_cmd


def test_run_owner_truth_daily_prefers_publication_validation_dir_for_webui(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    _seed_crm_anchor(tmp_path)

    def fake_run(cmd: str, *, cwd: Path, env=None):
        calls.append(cmd)
        return 0, "status=PASS", 0.01

    monkeypatch.setattr(runner_mod, "_run", fake_run)

    default_validation = tmp_path / "exports" / "validation" / "webui_archive_single_truth" / "2026-03-08"
    default_validation.mkdir(parents=True, exist_ok=True)
    publication_dir = tmp_path / "exports" / "north_star_owner_review" / "2026-03-08"
    publication_dir.mkdir(parents=True, exist_ok=True)
    fallback_validation = tmp_path / "exports" / "validation" / "ads_scope_closeout" / "2026-03-08"
    fallback_validation.mkdir(parents=True, exist_ok=True)
    report_path = fallback_validation / "sales_against_workbook_report.json"
    report_path.write_text(
        json.dumps({"status": "PASS", "ok": True}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (publication_dir / "publication_readiness.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "truth_source": "webui_archive",
                "gates": {
                    "workbook_chronology_anchor": {
                        "status": "PASS",
                        "path": str(report_path),
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    summary = run_owner_truth_daily(
        as_of=date(2026, 3, 8),
        since=date(2025, 6, 6),
        north_star_start=date(2026, 1, 1),
        north_star_end=date(2026, 2, 28),
        project_root=tmp_path,
        output_root=tmp_path / "out",
        summary_root=tmp_path / "daily",
        strict=True,
        apply=False,
        truth_source="webui_archive",
        pack_root=tmp_path / "pack",
        ledger_root=tmp_path / "ledger",
        download_run_id="download_run",
        runtime_mode="live",
    )

    assert summary["status"] == "PASS"
    doctor_cmd = next(cmd for cmd in calls if "system_doctor.py" in cmd)
    assert "ads_scope_closeout/2026-03-08" in doctor_cmd


def test_run_owner_truth_daily_defaults_to_webui_full_parse_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    _seed_crm_anchor(tmp_path)

    def fake_run(cmd: str, *, cwd: Path, env=None):
        calls.append(cmd)
        return 0, "status=PASS", 0.01

    monkeypatch.setattr(runner_mod, "_run", fake_run)

    ledger_root = tmp_path / "exports" / "order_status_ledger" / "webui_status_ledger_20260306_full_parse"
    ledger_root.mkdir(parents=True, exist_ok=True)
    pack_root = tmp_path / "exports" / "webui_archive_full_parse_runs" / "run_a" / "pack_outputs" / "pack_a"
    pack_root.mkdir(parents=True, exist_ok=True)
    (ledger_root / "ledger_manifest.json").write_text(
        json.dumps({"pack_roots": [str(pack_root)]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = run_owner_truth_daily(
        as_of=date(2026, 3, 8),
        since=date(2025, 6, 6),
        north_star_start=date(2026, 1, 1),
        north_star_end=date(2026, 2, 28),
        project_root=tmp_path,
        output_root=tmp_path / "out",
        summary_root=tmp_path / "daily",
        strict=True,
        apply=False,
        runtime_mode="live",
    )

    assert summary["status"] == "PASS"
    joined = "\n".join(calls)
    assert "--truth-source webui_archive" in joined
    assert str(ledger_root) in joined
    assert str(pack_root) in joined


def test_run_owner_truth_daily_resolves_repo_local_pack_root_from_imported_ledger_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    _seed_crm_anchor(tmp_path)

    def fake_run(cmd: str, *, cwd: Path, env=None):
        calls.append(cmd)
        return 0, "status=PASS", 0.01

    monkeypatch.setattr(runner_mod, "_run", fake_run)

    pack_id = "webui_archive_full_parse_2024-06-06_to_2026-03-05_20260306_2211_pack"
    ledger_root = tmp_path / "exports" / "order_status_ledger" / "webui_status_ledger_20260306_full_parse"
    ledger_root.mkdir(parents=True, exist_ok=True)
    local_pack_root = (
        tmp_path
        / "exports"
        / "webui_archive_full_parse_runs"
        / "webui_archive_full_parse_2024-06-06_to_2026-03-05_20260306_2211"
        / "pack_outputs"
        / pack_id
    )
    local_pack_root.mkdir(parents=True, exist_ok=True)
    (ledger_root / "ledger_manifest.json").write_text(
        json.dumps(
            {
                "pack_roots": [
                    "~/Docs/Autonomous_business/exports/webui_archive_full_parse_runs/webui_archive_full_parse_2024-06-06_to_2026-03-05_20260306_2211/pack_outputs/webui_archive_full_parse_2024-06-06_to_2026-03-05_20260306_2211_pack"
                ],
                "pack_ids": [pack_id],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    summary = run_owner_truth_daily(
        as_of=date(2026, 3, 8),
        since=date(2025, 6, 6),
        north_star_start=date(2026, 1, 1),
        north_star_end=date(2026, 2, 28),
        project_root=tmp_path,
        output_root=tmp_path / "out",
        summary_root=tmp_path / "daily",
        strict=True,
        apply=False,
        runtime_mode="live",
    )

    assert summary["status"] == "PASS"
    joined = "\n".join(calls)
    assert str(local_pack_root) in joined
    assert "~/Docs/Autonomous_business/" not in joined


def test_run_owner_truth_daily_resolves_external_download_run_when_local_default_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    _seed_crm_anchor(tmp_path)

    def fake_run(cmd: str, *, cwd: Path, env=None):
        calls.append(cmd)
        return 0, "status=PASS", 0.01

    monkeypatch.setattr(runner_mod, "_run", fake_run)

    pack_id = "webui_archive_full_parse_2024-06-06_to_2026-03-05_20260306_2211_pack"
    external_root = tmp_path / "external_repo"
    external_pack_root = (
        external_root
        / "exports"
        / "webui_archive_full_parse_runs"
        / "webui_archive_full_parse_2024-06-06_to_2026-03-05_20260306_2211"
        / "pack_outputs"
        / pack_id
    )
    external_pack_root.mkdir(parents=True, exist_ok=True)
    external_download_root = external_root / "exports" / "webui_archive_download_runs" / "webui_archive_download_20260306"
    external_download_root.mkdir(parents=True, exist_ok=True)
    (external_download_root / "run_manifest.json").write_text("{}", encoding="utf-8")

    ledger_root = tmp_path / "exports" / "order_status_ledger" / "webui_status_ledger_20260306_full_parse"
    ledger_root.mkdir(parents=True, exist_ok=True)
    (ledger_root / "ledger_manifest.json").write_text(
        json.dumps(
            {
                "pack_roots": [str(external_pack_root)],
                "pack_ids": [pack_id],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    summary = run_owner_truth_daily(
        as_of=date(2026, 3, 8),
        since=date(2025, 6, 6),
        north_star_start=date(2026, 1, 1),
        north_star_end=date(2026, 2, 28),
        project_root=tmp_path,
        output_root=tmp_path / "out",
        summary_root=tmp_path / "daily",
        strict=True,
        apply=False,
        runtime_mode="live",
    )

    assert summary["status"] == "PASS"
    joined = "\n".join(calls)
    assert str(external_download_root) in joined


def test_run_owner_truth_daily_builds_owner_review_after_validation_and_owner_pnl(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    _seed_crm_anchor(tmp_path)

    def fake_run(cmd: str, *, cwd: Path, env=None):
        calls.append(cmd)
        return 0, "status=PASS", 0.01

    monkeypatch.setattr(runner_mod, "_run", fake_run)

    summary = run_owner_truth_daily(
        as_of=date(2026, 3, 8),
        since=date(2025, 6, 6),
        north_star_start=date(2026, 1, 1),
        north_star_end=date(2026, 2, 28),
        project_root=tmp_path,
        output_root=tmp_path / "out",
        summary_root=tmp_path / "daily",
        strict=True,
        apply=False,
        truth_source="webui_archive",
        validation_dir=tmp_path / "validation",
        pack_root=tmp_path / "pack",
        ledger_root=tmp_path / "ledger",
        download_run_id="download_run",
        runtime_mode="live",
    )

    assert summary["status"] == "PASS"
    validate_idx = next(i for i, cmd in enumerate(calls) if "validate_sales_against_workbook.py" in cmd)
    doctor_idx = next(i for i, cmd in enumerate(calls) if "system_doctor.py" in cmd)
    pnl_idx = next(i for i, cmd in enumerate(calls) if "build_owner_pnl_report.py" in cmd)
    review_idx = next(i for i, cmd in enumerate(calls) if "build_north_star_owner_review.py" in cmd)
    triage_idx = next(i for i, cmd in enumerate(calls) if "triage_owner_truth_stoplines.py" in cmd)

    assert validate_idx < doctor_idx < pnl_idx < review_idx < triage_idx


def test_run_owner_truth_daily_runs_webui_db_gate_before_ads_validators(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    _seed_crm_anchor(tmp_path)

    def fake_run(cmd: str, *, cwd: Path, env=None):
        calls.append(cmd)
        return 0, "status=PASS", 0.01

    monkeypatch.setattr(runner_mod, "_run", fake_run)

    summary = run_owner_truth_daily(
        as_of=date(2026, 3, 8),
        since=date(2025, 6, 6),
        north_star_start=date(2026, 1, 1),
        north_star_end=date(2026, 2, 28),
        project_root=tmp_path,
        output_root=tmp_path / "out",
        summary_root=tmp_path / "daily",
        strict=True,
        apply=False,
        truth_source="webui_archive",
        validation_dir=tmp_path / "validation",
        pack_root=tmp_path / "pack",
        ledger_root=tmp_path / "ledger",
        download_run_id="download_run",
        runtime_mode="live",
    )

    assert summary["status"] == "PASS"
    db_gate_idx = next(i for i, cmd in enumerate(calls) if "validate_webui_archive_vs_current_db.py" in cmd)
    ads_coverage_idx = next(i for i, cmd in enumerate(calls) if "validate_ads_offer_universe_coverage.py" in cmd)
    ads_spend_idx = next(i for i, cmd in enumerate(calls) if "validate_ads_spend_reality.py" in cmd)
    assert db_gate_idx < ads_coverage_idx < ads_spend_idx


def test_run_owner_truth_daily_emits_full_range_webui_db_gate_before_owner_pnl(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    _seed_crm_anchor(tmp_path)

    def fake_run(cmd: str, *, cwd: Path, env=None):
        calls.append(cmd)
        return 0, "status=PASS", 0.01

    monkeypatch.setattr(runner_mod, "_run", fake_run)

    summary = run_owner_truth_daily(
        as_of=date(2026, 3, 9),
        since=date(2025, 6, 6),
        north_star_start=date(2026, 1, 1),
        north_star_end=date(2026, 2, 28),
        project_root=tmp_path,
        output_root=tmp_path / "out",
        summary_root=tmp_path / "daily",
        strict=True,
        apply=False,
        truth_source="webui_archive",
        validation_dir=tmp_path / "validation",
        pack_root=tmp_path / "pack",
        ledger_root=tmp_path / "ledger",
        download_run_id="download_run",
        runtime_mode="live",
    )

    assert summary["status"] == "PASS"
    full_range_cmd = next(
        cmd
        for cmd in calls
        if "validate_webui_archive_vs_current_db.py" in cmd and "full_range_db_gate" in cmd
    )
    assert "--start 2025-06-06" in full_range_cmd
    assert "--end 2026-03-09" in full_range_cmd
    assert "--range-policy full_range_owner_truth" in full_range_cmd
    assert "--statusdate-cutover 2026-02-27" in full_range_cmd
    full_range_idx = calls.index(full_range_cmd)
    pnl_idx = next(i for i, cmd in enumerate(calls) if "build_owner_pnl_report.py" in cmd)
    assert full_range_idx < pnl_idx


def test_run_owner_truth_daily_skips_ads_sidecar_sync_when_apply_false(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    _seed_crm_anchor(tmp_path)

    def fake_run(cmd: str, *, cwd: Path, env=None):
        calls.append(cmd)
        return 0, "status=PASS", 0.01

    monkeypatch.setattr(runner_mod, "_run", fake_run)

    summary = run_owner_truth_daily(
        as_of=date(2026, 3, 9),
        since=date(2025, 6, 6),
        north_star_start=date(2026, 1, 1),
        north_star_end=date(2026, 2, 28),
        project_root=tmp_path,
        output_root=tmp_path / "out",
        summary_root=tmp_path / "daily",
        strict=True,
        apply=False,
        truth_source="webui_archive",
        validation_dir=tmp_path / "validation",
        pack_root=tmp_path / "pack",
        ledger_root=tmp_path / "ledger",
        download_run_id="download_run",
        runtime_mode="live",
    )

    assert summary["status"] == "PASS"
    assert not any("sync_ads_sidecar.py" in cmd for cmd in calls)


def test_run_owner_truth_daily_runs_ads_sidecar_sync_only_with_apply_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, str] | None]] = []
    _seed_crm_anchor(tmp_path)
    monkeypatch.setenv("ENABLE_OWNER_TRUTH_APPLY", "1")

    def fake_run(cmd: str, *, cwd: Path, env=None):
        calls.append((cmd, env))
        return 0, "status=PASS", 0.01

    monkeypatch.setattr(runner_mod, "_run", fake_run)

    summary = run_owner_truth_daily(
        as_of=date(2026, 3, 9),
        since=date(2025, 6, 6),
        north_star_start=date(2026, 1, 1),
        north_star_end=date(2026, 2, 28),
        project_root=tmp_path,
        output_root=tmp_path / "out",
        summary_root=tmp_path / "daily",
        strict=True,
        apply=True,
        truth_source="webui_archive",
        validation_dir=tmp_path / "validation",
        pack_root=tmp_path / "pack",
        ledger_root=tmp_path / "ledger",
        download_run_id="download_run",
        runtime_mode="live",
    )

    assert summary["status"] == "PASS"
    sync_call = next((item for item in calls if "sync_ads_sidecar.py" in item[0]), None)
    assert sync_call is not None
    assert sync_call[1] is not None
    assert sync_call[1]["ENABLE_CASHFLOW_WRITE"] == "1"


def test_run_owner_truth_daily_replay_mode_regenerates_deterministic_outputs_from_frozen_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_run(cmd: str, *, cwd: Path, env=None):
        calls.append(cmd)
        return 0, "status=PASS", 0.01

    monkeypatch.setattr(runner_mod, "_run", fake_run)

    summary_json = tmp_path / "exports" / "validation" / "board_v8_runtime" / "2026-03-08" / "daily_ops_summary.json"
    summary_json.parent.mkdir(parents=True, exist_ok=True)
    summary_json.write_text(
        json.dumps(
            {
                "generated_at": "2026-03-08T18:00:00Z",
                "as_of": "2026-03-08",
                "status": "GREEN",
                "ok": True,
                "profile": "catch-up",
                "steps": [],
                "store_results": {},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    seed_json = tmp_path / "exports" / "validation" / "board_v8_runtime" / "2026-03-08" / "ops_selection_seed.json"
    seed_json.write_text(
        json.dumps(
            {
                "as_of": "2026-03-08",
                "import_orders": 69,
                "shipped_orders": 78,
                "selected_count": 78,
                "copied_waybills": 78,
                "missing_waybills": 0,
                "stores": {
                    "STOREB": ["845000001"],
                    "ACMEWEAR": ["846000001"],
                    "UNIVERSAL": ["847000001"],
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    summary = run_owner_truth_daily(
        as_of=date(2026, 3, 8),
        since=date(2025, 6, 6),
        north_star_start=date(2026, 1, 1),
        north_star_end=date(2026, 2, 28),
        project_root=tmp_path,
        output_root=tmp_path / "out",
        summary_root=tmp_path / "daily",
        strict=True,
        apply=False,
        truth_source="webui_archive",
        validation_dir=tmp_path / "validation",
        pack_root=tmp_path / "pack",
        ledger_root=tmp_path / "ledger",
        download_run_id="download_run",
        runtime_mode="replay",
    )

    assert summary["status"] == "PASS"
    joined = "\n".join(calls)
    assert "export_sales_archive_statusdate_mapped.py" in joined
    assert "generate_business_insides.py" in joined
    assert "generate_daily_ops_report.py" in joined
    assert "generate_ops_selection_artifacts.py" in joined
    assert "generate_owner_truth_exceptions.py" in joined
    assert "build_owner_pnl_report.py" in joined
    assert "build_north_star_owner_review.py" in joined
    assert "validate_webui_archive_pack_integrity.py" not in joined
    assert "system_doctor.py" not in joined
    assert "run_kaspi_daily_ops.py" not in joined

    export_idx = next(i for i, cmd in enumerate(calls) if "export_sales_archive_statusdate_mapped.py" in cmd)
    bi_idx = next(i for i, cmd in enumerate(calls) if "generate_business_insides.py" in cmd)
    report_idx = next(i for i, cmd in enumerate(calls) if "generate_daily_ops_report.py" in cmd)
    ops_selection_idx = next(i for i, cmd in enumerate(calls) if "generate_ops_selection_artifacts.py" in cmd)
    exceptions_idx = next(i for i, cmd in enumerate(calls) if "generate_owner_truth_exceptions.py" in cmd)
    pnl_idx = next(i for i, cmd in enumerate(calls) if "build_owner_pnl_report.py" in cmd)
    review_idx = next(i for i, cmd in enumerate(calls) if "build_north_star_owner_review.py" in cmd)
    assert export_idx < ops_selection_idx < bi_idx < report_idx < exceptions_idx < pnl_idx < review_idx


def test_run_owner_truth_daily_live_mode_forces_daily_ops_even_when_summary_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    _seed_crm_anchor(tmp_path)

    def fake_run(cmd: str, *, cwd: Path, env=None):
        calls.append(cmd)
        return 0, "status=PASS", 0.01

    monkeypatch.setattr(runner_mod, "_run", fake_run)

    runtime_root = tmp_path / "exports" / "validation" / "board_v8_runtime" / "2026-03-08"
    runtime_root.mkdir(parents=True, exist_ok=True)
    (runtime_root / "daily_ops_summary.json").write_text(
        json.dumps({"as_of": "2026-03-08", "ok": True, "status": "PASS"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (runtime_root / "ops_selection_seed.json").write_text(
        json.dumps({"as_of": "2026-03-08", "stores": {"ACMEWEAR": ["1"]}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = run_owner_truth_daily(
        as_of=date(2026, 3, 8),
        since=date(2025, 6, 6),
        north_star_start=date(2026, 1, 1),
        north_star_end=date(2026, 2, 28),
        project_root=tmp_path,
        output_root=tmp_path / "out",
        summary_root=tmp_path / "daily",
        strict=True,
        apply=False,
        truth_source="webui_archive",
        validation_dir=tmp_path / "validation",
        pack_root=tmp_path / "pack",
        ledger_root=tmp_path / "ledger",
        download_run_id="download_run",
        runtime_mode="live",
    )

    assert summary["status"] == "PASS"
    joined = "\n".join(calls)
    assert "run_kaspi_daily_ops.py" in joined
    assert "generate_ops_selection_artifacts.py" not in joined


def test_run_owner_truth_daily_live_passes_workbook_anchor_to_system_doctor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, str] | None]] = []
    anchor = _seed_crm_anchor(tmp_path)

    def fake_run(cmd: str, *, cwd: Path, env=None):
        calls.append((cmd, env))
        return 0, "status=PASS", 0.01

    monkeypatch.setattr(runner_mod, "_run", fake_run)

    summary = run_owner_truth_daily(
        as_of=date(2026, 3, 9),
        since=date(2025, 6, 6),
        north_star_start=date(2026, 1, 1),
        north_star_end=date(2026, 2, 28),
        project_root=tmp_path,
        output_root=tmp_path / "out",
        summary_root=tmp_path / "daily",
        strict=True,
        apply=False,
        runtime_mode="live",
    )

    assert summary["status"] == "PASS"
    doctor_cmd, doctor_env = next((cmd, env) for cmd, env in calls if "system_doctor.py" in cmd)
    assert "--as-of 2026-03-09" in doctor_cmd
    assert doctor_env is not None
    assert doctor_env["AB_CRM_WORKBOOK_PATH"] == str(anchor.resolve())


def test_run_owner_truth_daily_live_requires_bootstrapped_workbook_anchor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_run(cmd: str, *, cwd: Path, env=None):
        calls.append(cmd)
        return 0, "status=PASS", 0.01

    monkeypatch.setattr(runner_mod, "_run", fake_run)

    with pytest.raises(OwnerTruthDailyError, match="AB_CRM_WORKBOOK_PATH"):
        run_owner_truth_daily(
            as_of=date(2026, 3, 9),
            since=date(2025, 6, 6),
            north_star_start=date(2026, 1, 1),
            north_star_end=date(2026, 2, 28),
            project_root=tmp_path,
            output_root=tmp_path / "out",
            summary_root=tmp_path / "daily",
            strict=True,
            apply=False,
            runtime_mode="live",
        )

    assert calls == []


def test_run_owner_truth_daily_parser_defaults_to_live_mode() -> None:
    parser = runner_mod._build_parser()
    args = parser.parse_args(["--as-of", "2026-03-08"])

    assert args.mode == "live"
