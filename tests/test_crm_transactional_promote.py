from __future__ import annotations

from pathlib import Path

import pytest

from scripts.import_orders_to_crm import _promote_candidate_workbook


def test_promote_candidate_workbook_replaces_source_on_success(monkeypatch, tmp_path: Path):
    source = tmp_path / "source.xlsx"
    candidate = tmp_path / "candidate.xlsx"
    failed_dir = tmp_path / "failed"
    source.write_text("old", encoding="utf-8")
    candidate.write_text("new", encoding="utf-8")

    monkeypatch.setattr(
        "scripts.import_orders_to_crm._verify_candidate_workbook",
        lambda *_args, **_kwargs: None,
        raising=False,
    )
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._excel_open_probe",
        lambda *_args, **_kwargs: (True, "OK"),
        raising=False,
    )

    _promote_candidate_workbook(
        source_path=source,
        candidate_path=candidate,
        failed_dir=failed_dir,
        strict_excel=True,
        verbose=False,
    )

    assert source.read_text(encoding="utf-8") == "new"
    assert not candidate.exists()


def test_promote_candidate_workbook_keeps_source_and_moves_failed_candidate(monkeypatch, tmp_path: Path):
    source = tmp_path / "source.xlsx"
    candidate = tmp_path / "candidate.xlsx"
    failed_dir = tmp_path / "failed"
    source.write_text("stable", encoding="utf-8")
    candidate.write_text("bad", encoding="utf-8")

    def _raise_verify(*_args, **_kwargs):
        raise RuntimeError("integrity failed")

    monkeypatch.setattr(
        "scripts.import_orders_to_crm._verify_candidate_workbook",
        _raise_verify,
        raising=False,
    )

    with pytest.raises(RuntimeError, match="integrity failed"):
        _promote_candidate_workbook(
            source_path=source,
            candidate_path=candidate,
            failed_dir=failed_dir,
            strict_excel=True,
            verbose=False,
        )

    assert source.read_text(encoding="utf-8") == "stable"
    failed_candidates = sorted(failed_dir.glob("candidate.failed_*.xlsx"))
    assert failed_candidates
    assert not candidate.exists()


def test_promote_candidate_workbook_probes_promoted_source_path_on_macos(monkeypatch, tmp_path: Path):
    source = tmp_path / "source.xlsx"
    candidate = tmp_path / "source.candidate.xlsx"
    failed_dir = tmp_path / "failed"
    source.write_text("old", encoding="utf-8")
    candidate.write_text("new", encoding="utf-8")

    seen: dict[str, object] = {}

    def _verify(candidate_path, strict_excel=True, **_kwargs):
        seen["verify_path"] = Path(candidate_path)
        seen["verify_strict_excel"] = strict_excel

    def _probe(workbook_path, attempts=3, timeout_sec=45):
        seen["probe_path"] = Path(workbook_path)
        seen["probe_attempts"] = attempts
        seen["probe_timeout_sec"] = timeout_sec
        return True, "OK"

    monkeypatch.setattr(
        "scripts.import_orders_to_crm._verify_candidate_workbook",
        _verify,
        raising=False,
    )
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._excel_open_probe",
        _probe,
        raising=False,
    )
    monkeypatch.setattr("scripts.import_orders_to_crm.sys.platform", "darwin", raising=False)

    _promote_candidate_workbook(
        source_path=source,
        candidate_path=candidate,
        failed_dir=failed_dir,
        strict_excel=True,
        verbose=False,
    )

    assert source.read_text(encoding="utf-8") == "new"
    assert seen == {
        "verify_path": candidate,
        "verify_strict_excel": False,
        "probe_path": source,
        "probe_attempts": 2,
        "probe_timeout_sec": 35,
    }


def test_promote_candidate_workbook_raises_when_post_promotion_source_probe_fails_on_macos(
    monkeypatch, tmp_path: Path
):
    source = tmp_path / "source.xlsx"
    candidate = tmp_path / "source.candidate.xlsx"
    failed_dir = tmp_path / "failed"
    source.write_text("old", encoding="utf-8")
    candidate.write_text("new", encoding="utf-8")

    monkeypatch.setattr(
        "scripts.import_orders_to_crm._verify_candidate_workbook",
        lambda *_args, **_kwargs: None,
        raising=False,
    )
    monkeypatch.setattr(
        "scripts.import_orders_to_crm._excel_open_probe",
        lambda *_args, **_kwargs: (False, "ERR:-10000:Grant Access"),
        raising=False,
    )
    monkeypatch.setattr("scripts.import_orders_to_crm.sys.platform", "darwin", raising=False)

    with pytest.raises(RuntimeError, match="Promoted workbook Excel open probe failed"):
        _promote_candidate_workbook(
            source_path=source,
            candidate_path=candidate,
            failed_dir=failed_dir,
            strict_excel=True,
            verbose=False,
        )

    assert source.read_text(encoding="utf-8") == "new"
