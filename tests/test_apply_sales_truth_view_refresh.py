import json
from pathlib import Path

import pytest

import scripts.apply_sales_truth_view_refresh as refresh
from scripts.apply_sales_truth_view_refresh import sha256_file
from tests.test_apply_sales_publication_binding_manifest import _seed_db


def _allow_tmp_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(refresh, "_assert_copied_target", lambda path: Path(path).resolve())


def _legacy_db(tmp_path: Path) -> Path:
    path = tmp_path / "legacy.db"
    _seed_db(path, refreshed_binding_schema=False)
    return path


def test_plan_is_read_only_and_emits_exact_delta_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_tmp_copy(monkeypatch)
    db_path = _legacy_db(tmp_path)
    before = sha256_file(db_path)
    plan_path = tmp_path / "plan.json"

    plan = refresh.write_plan(db_path=db_path, plan_path=plan_path)

    assert sha256_file(db_path) == before
    assert plan["schema_version"] == refresh.PLAN_SCHEMA_VERSION
    assert plan["applier_code_pin"] == refresh._applier_code_pin()
    assert plan["only_before"]["row_count"] >= 0
    assert plan["only_after"]["row_count"] >= 0
    refresh._validate_plan(json.loads(plan_path.read_text(encoding="utf-8")))
    for item in plan["evidence_files"].values():
        path = Path(plan["evidence_directory"]) / item["filename"]
        assert path.is_file()
        assert sha256_file(path) == item["sha256"]


def test_apply_without_gate_fails_before_backup_or_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_tmp_copy(monkeypatch)
    db_path = _legacy_db(tmp_path)
    plan_path = tmp_path / "plan.json"
    refresh.write_plan(db_path=db_path, plan_path=plan_path)
    backup_dir = tmp_path / "backups"
    report_path = tmp_path / "report.json"
    monkeypatch.delenv(refresh.WRITE_ENV_GATE, raising=False)

    with pytest.raises(refresh.SalesTruthViewRefreshError, match="is required"):
        refresh.apply_reviewed_plan(
            db_path=db_path,
            reviewed_plan_path=plan_path,
            expected_plan_file_sha256=sha256_file(plan_path),
            expected_pre_sha256=sha256_file(db_path),
            backup_dir=backup_dir,
            report_path=report_path,
        )

    assert not backup_dir.exists()
    assert not report_path.exists()


def test_changed_applier_code_pin_fails_before_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_tmp_copy(monkeypatch)
    monkeypatch.setenv(refresh.WRITE_ENV_GATE, "1")
    db_path = _legacy_db(tmp_path)
    plan_path = tmp_path / "plan.json"
    refresh.write_plan(db_path=db_path, plan_path=plan_path)
    backup_dir = tmp_path / "backups"
    monkeypatch.setattr(
        refresh,
        "_applier_code_pin",
        lambda: {"path": "scripts/apply_sales_truth_view_refresh.py", "file_sha256": "0" * 64},
    )

    with pytest.raises(refresh.SalesTruthViewRefreshError, match="applier code differs"):
        refresh.apply_reviewed_plan(
            db_path=db_path,
            reviewed_plan_path=plan_path,
            expected_plan_file_sha256=sha256_file(plan_path),
            expected_pre_sha256=sha256_file(db_path),
            backup_dir=backup_dir,
            report_path=tmp_path / "report.json",
        )

    assert not backup_dir.exists()


def test_apply_exact_reviewed_plan_is_backup_first_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_tmp_copy(monkeypatch)
    monkeypatch.setenv(refresh.WRITE_ENV_GATE, "1")
    db_path = _legacy_db(tmp_path)
    pre_sha = sha256_file(db_path)
    plan_path = tmp_path / "plan.json"
    plan = refresh.write_plan(db_path=db_path, plan_path=plan_path)
    report_path = tmp_path / "report.json"
    backup_dir = tmp_path / "backups"

    report = refresh.apply_reviewed_plan(
        db_path=db_path,
        reviewed_plan_path=plan_path,
        expected_plan_file_sha256=sha256_file(plan_path),
        expected_pre_sha256=pre_sha,
        backup_dir=backup_dir,
        report_path=report_path,
    )

    assert report["status"] == "PASS"
    assert report["write_applied"] is True
    assert report["preexisting_tables_unchanged"] is True
    assert report["idempotent_replay"] is True
    assert sha256_file(Path(report["backup_path"])) == pre_sha
    assert report["only_before"] == plan["only_before"]
    assert report["only_after"] == plan["only_after"]
    assert refresh.build_refresh_plan(db_path)[0]["legacy_truth_view_contract"]["compatible"] is True


def test_post_commit_verification_failure_restores_exact_preimage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_tmp_copy(monkeypatch)
    monkeypatch.setenv(refresh.WRITE_ENV_GATE, "1")
    db_path = _legacy_db(tmp_path)
    pre_sha = sha256_file(db_path)
    plan_path = tmp_path / "plan.json"
    refresh.write_plan(db_path=db_path, plan_path=plan_path)
    backup_dir = tmp_path / "backups"
    report_path = tmp_path / "report.json"

    def fail_post_commit(*args, **kwargs):
        raise refresh.SalesTruthViewRefreshError("injected post-commit failure")

    monkeypatch.setattr(refresh, "_verify_post_commit_state", fail_post_commit)

    with pytest.raises(refresh.SalesTruthViewRefreshError, match="restored"):
        refresh.apply_reviewed_plan(
            db_path=db_path,
            reviewed_plan_path=plan_path,
            expected_plan_file_sha256=sha256_file(plan_path),
            expected_pre_sha256=pre_sha,
            backup_dir=backup_dir,
            report_path=report_path,
        )

    assert sha256_file(db_path) == pre_sha
    assert not report_path.exists()
    rollback_paths = list(backup_dir.glob("ROLLBACK_SALES_TRUTH_VIEW_REFRESH_*.json"))
    assert len(rollback_paths) == 1
    rollback = json.loads(rollback_paths[0].read_text(encoding="utf-8"))
    assert rollback["status"] == "RESTORED_AFTER_POST_COMMIT_FAILURE"
    assert rollback["restore_verified"] is True
    assert rollback["restored_sha256"] == pre_sha


def test_idempotence_failure_rolls_back_before_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_tmp_copy(monkeypatch)
    monkeypatch.setenv(refresh.WRITE_ENV_GATE, "1")
    db_path = _legacy_db(tmp_path)
    pre_sha = sha256_file(db_path)
    plan_path = tmp_path / "plan.json"
    refresh.write_plan(db_path=db_path, plan_path=plan_path)
    backup_dir = tmp_path / "backups"

    def fail_replay(*args, **kwargs):
        raise refresh.SalesTruthViewRefreshError("injected replay failure")

    monkeypatch.setattr(
        refresh,
        "_verify_idempotent_replay_in_transaction",
        fail_replay,
    )

    with pytest.raises(refresh.SalesTruthViewRefreshError, match="injected replay"):
        refresh.apply_reviewed_plan(
            db_path=db_path,
            reviewed_plan_path=plan_path,
            expected_plan_file_sha256=sha256_file(plan_path),
            expected_pre_sha256=pre_sha,
            backup_dir=backup_dir,
            report_path=tmp_path / "report.json",
        )

    assert sha256_file(db_path) == pre_sha
    rollback_paths = list(backup_dir.glob("ROLLBACK_SALES_TRUTH_VIEW_REFRESH_*.json"))
    assert len(rollback_paths) == 1
    rollback = json.loads(rollback_paths[0].read_text(encoding="utf-8"))
    assert rollback["status"] == "TRANSACTION_ROLLED_BACK"
    assert rollback["restore_verified"] is True


def test_apply_rejects_changed_evidence_before_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_tmp_copy(monkeypatch)
    monkeypatch.setenv(refresh.WRITE_ENV_GATE, "1")
    db_path = _legacy_db(tmp_path)
    plan_path = tmp_path / "plan.json"
    plan = refresh.write_plan(db_path=db_path, plan_path=plan_path)
    evidence = Path(plan["evidence_directory"]) / plan["evidence_files"]["only_before"]["filename"]
    evidence.write_text(evidence.read_text(encoding="utf-8") + "tamper\n", encoding="utf-8")
    backup_dir = tmp_path / "backups"

    with pytest.raises(refresh.SalesTruthViewRefreshError, match="missing or changed"):
        refresh.apply_reviewed_plan(
            db_path=db_path,
            reviewed_plan_path=plan_path,
            expected_plan_file_sha256=sha256_file(plan_path),
            expected_pre_sha256=sha256_file(db_path),
            backup_dir=backup_dir,
            report_path=tmp_path / "report.json",
        )

    assert not backup_dir.exists()


def test_refreshed_plan_apply_is_noop_without_second_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_tmp_copy(monkeypatch)
    monkeypatch.setenv(refresh.WRITE_ENV_GATE, "1")
    db_path = _legacy_db(tmp_path)
    first_plan = tmp_path / "first_plan.json"
    refresh.write_plan(db_path=db_path, plan_path=first_plan)
    refresh.apply_reviewed_plan(
        db_path=db_path,
        reviewed_plan_path=first_plan,
        expected_plan_file_sha256=sha256_file(first_plan),
        expected_pre_sha256=sha256_file(db_path),
        backup_dir=tmp_path / "first_backups",
        report_path=tmp_path / "first_report.json",
    )

    second_plan = tmp_path / "second_plan.json"
    plan = refresh.write_plan(
        db_path=db_path,
        plan_path=second_plan,
        evidence_dir=tmp_path / "second_evidence",
    )
    second_backup = tmp_path / "second_backups"
    report = refresh.apply_reviewed_plan(
        db_path=db_path,
        reviewed_plan_path=second_plan,
        expected_plan_file_sha256=sha256_file(second_plan),
        expected_pre_sha256=sha256_file(db_path),
        backup_dir=second_backup,
        report_path=tmp_path / "second_report.json",
    )

    assert plan["only_before"]["row_count"] == 0
    assert plan["only_after"]["row_count"] == 0
    assert report["mode"] == "APPLY_NOOP_ALREADY_REFRESHED"
    assert report["write_applied"] is False
    assert report["backup_created"] is False
    assert not second_backup.exists()
