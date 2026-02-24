from __future__ import annotations

from pathlib import Path

import pytest

from scripts import run_crm_identity_repair_canary as canary_mod


def test_canary_blocks_apply_when_dry_run_exceeds_threshold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[bool] = []

    def fake_run_patch(**kwargs):
        calls.append(bool(kwargs.get("apply")))
        return {
            "mode": "DRY_RUN",
            "rows_scanned": 10,
            "rows_updated": 6,
            "backup_path": "",
            "report": str(tmp_path / "report.csv"),
        }

    monkeypatch.setattr(canary_mod, "run_patch", fake_run_patch)

    with pytest.raises(RuntimeError, match="rows_updated exceeds max_updates"):
        canary_mod.run_canary(
            workbook=tmp_path / "crm.xlsx",
            sheet_name="Sheet1",
            report=tmp_path / "report.csv",
            backup_dir=tmp_path / "backups",
            proof_path=tmp_path / "rollback.md",
            only_line61=True,
            max_updates=5,
            apply=True,
        )

    assert calls == [False]


def test_canary_apply_writes_rollback_proof_when_backup_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup = tmp_path / "backup.xlsx"
    backup.write_bytes(b"dummy")
    calls: list[bool] = []

    def fake_run_patch(**kwargs):
        apply = bool(kwargs.get("apply"))
        calls.append(apply)
        if not apply:
            return {
                "mode": "DRY_RUN",
                "rows_scanned": 12,
                "rows_updated": 2,
                "backup_path": "",
                "report": str(tmp_path / "report.csv"),
            }
        return {
            "mode": "APPLY",
            "rows_scanned": 12,
            "rows_updated": 2,
            "backup_path": str(backup),
            "report": str(tmp_path / "report.csv"),
        }

    monkeypatch.setattr(canary_mod, "run_patch", fake_run_patch)

    proof = tmp_path / "rollback_proof.md"
    result = canary_mod.run_canary(
        workbook=tmp_path / "crm.xlsx",
        sheet_name="Sheet1",
        report=tmp_path / "report.csv",
        backup_dir=tmp_path / "backups",
        proof_path=proof,
        only_line61=True,
        max_updates=5,
        apply=True,
    )

    assert calls == [False, True]
    assert result["mode"] == "APPLY"
    assert result["backup_path"] == str(backup)
    assert proof.exists()
    text = proof.read_text(encoding="utf-8")
    assert str(backup) in text
    assert "Rollback command" in text
