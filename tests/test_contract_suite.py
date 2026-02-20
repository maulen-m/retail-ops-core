from pathlib import Path

from scripts import run_contract_suite


def test_fixture_db_has_required_tables(tmp_path: Path) -> None:
    fixture_paths = run_contract_suite.build_fixture_dbs("small", tmp_path)

    for name, db_path in fixture_paths.items():
        missing = run_contract_suite.missing_tables(
            db_path, run_contract_suite.FIXTURE_TABLES[name]
        )
        assert missing == [], f"{name} missing tables: {missing}"


def test_stagecode_fixture_has_required_columns(tmp_path: Path) -> None:
    fixture_paths = run_contract_suite.build_fixture_dbs("small", tmp_path)
    db_path = fixture_paths["stagecode_waybill"]

    cols = run_contract_suite.list_columns(db_path, "fact_orders_kaspi")
    missing = run_contract_suite.STAGECODE_REQUIRED_COLUMNS - cols
    assert missing == set(), f"fact_orders_kaspi missing columns: {sorted(missing)}"


def test_contract_suite_deterministic(tmp_path: Path) -> None:
    run1 = run_contract_suite.run_contract_suite("small", work_dir=tmp_path / "run1")
    run2 = run_contract_suite.run_contract_suite("small", work_dir=tmp_path / "run2")

    assert run1["ok"] is True
    assert run2["ok"] is True
    assert run1["summary"]["po_dashboard_invariants"]["ok"] is True
    assert run1["suite_hash"] == run2["suite_hash"]
