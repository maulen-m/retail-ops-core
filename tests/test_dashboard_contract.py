"""Contract tests for dashboard output (Phase 3)."""

from pathlib import Path
import sqlite3

import pytest

from core.validation.dashboard_contract import (
    DEFAULT_FIXTURE,
    DEFAULT_PO_CONTRACT,
    load_cases,
    build_drafts,
    generate_dashboard_output,
    validate_dashboard_output,
    hash_output,
)
from core.validation.tolerances import parse_po_contract_tolerances


DB_PATH = Path(__file__).resolve().parents[1] / "db" / "app.db"


def _skip_if_db_missing() -> None:
    if not DB_PATH.exists():
        pytest.skip("db/app.db missing; skipping dashboard contract tests")
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            result = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                ("fact_inventory_snapshot_size",),
            ).fetchone()
    except sqlite3.Error as exc:
        pytest.skip(f"db/app.db unreadable ({exc}); skipping dashboard contract tests")
    if result is None:
        pytest.skip("db/app.db missing fact_inventory_snapshot_size; skipping dashboard contract tests")


def test_dashboard_contract_fixture():
    _skip_if_db_missing()
    cases = load_cases(DEFAULT_FIXTURE)
    drafts = build_drafts(cases)
    output = generate_dashboard_output(cases)
    tolerances = parse_po_contract_tolerances(DEFAULT_PO_CONTRACT)

    errors = validate_dashboard_output(output, drafts, tolerances)
    assert not errors, "\n".join(errors)


def test_dashboard_contract_deterministic_hash():
    _skip_if_db_missing()
    cases = load_cases(DEFAULT_FIXTURE)
    output_a = generate_dashboard_output(cases)
    output_b = generate_dashboard_output(cases)

    assert hash_output(output_a) == hash_output(output_b)
