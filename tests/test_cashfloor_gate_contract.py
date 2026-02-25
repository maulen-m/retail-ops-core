from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from scripts.validate_cashfloor import validate_cashfloor


def _seed_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE fact_cashflow_commitments (
            commit_date TEXT,
            commit_type TEXT,
            amount_kzt REAL,
            scenario_tag TEXT,
            ref_id TEXT,
            notes TEXT
        );
        """
    )
    conn.execute(
        """
        INSERT INTO fact_cashflow_commitments (
            commit_date, commit_type, amount_kzt, scenario_tag, ref_id, notes
        ) VALUES ('2026-02-26', 'OPEX', 1000000, 'base', 'OPEX-1', 'fixture')
        """
    )
    conn.commit()
    conn.close()


def test_cashfloor_gate_green_when_base_and_conservative_pass(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)

    import scripts.cashflow_preflight_po as preflight

    monkeypatch.setattr(preflight, "_load_scenarios_config", lambda: {})
    monkeypatch.setattr(
        preflight,
        "evaluate_preflight",
        lambda **_kwargs: SimpleNamespace(ok=True, min_cash=2_000_000.0, min_cash_date="2026-02-27", reason=None),
    )

    report = validate_cashfloor(
        db_path=db_path,
        as_of="2026-02-26",
        output_root=tmp_path,
        strict=True,
    )
    assert report["ok"] is True
    assert report["exit_code"] == 0
    assert report["payload"]["status"] == "GREEN"


def test_cashfloor_gate_red_when_conservative_fails(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "app.db"
    _seed_db(db_path)

    import scripts.cashflow_preflight_po as preflight

    monkeypatch.setattr(preflight, "_load_scenarios_config", lambda: {})

    def fake_eval(**kwargs):
        scenario = kwargs.get("scenario")
        if scenario == "conservative":
            return SimpleNamespace(
                ok=False,
                min_cash=-1000.0,
                min_cash_date="2026-03-01",
                reason="min_cash -1000.00 below threshold 2000000.00",
            )
        return SimpleNamespace(ok=True, min_cash=100.0, min_cash_date="2026-02-27", reason=None)

    monkeypatch.setattr(preflight, "evaluate_preflight", fake_eval)

    report = validate_cashfloor(
        db_path=db_path,
        as_of="2026-02-26",
        output_root=tmp_path,
        strict=True,
    )
    assert report["ok"] is False
    assert report["exit_code"] == 1
    assert report["payload"]["status"] == "RED"
    assert "below threshold" in str(report["payload"]["reason"])
