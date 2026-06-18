import hashlib
import sqlite3
from pathlib import Path

from scripts import validate_business_insides as module


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_validate_business_insides_uses_temp_db_copy(tmp_path: Path, monkeypatch) -> None:
    source_db = tmp_path / "app.db"
    sqlite3.connect(str(source_db)).close()
    bank_accounts = tmp_path / "bank_accounts.yaml"
    bank_accounts.write_text("accounts: []\n", encoding="utf-8")
    output_dir = tmp_path / "business_insides"
    output_dir.mkdir()
    (output_dir / "BUSINESS_INSIDES_2026-02-08.md").write_text("snapshot\n", encoding="utf-8")

    def fake_compute_sales_metrics(*, db_path: Path, as_of, **_kwargs):
        assert db_path != source_db
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("CREATE TABLE validator_local_marker (id INTEGER)")
        return {
            "total_rows": 1,
            "avg_30d_net_rev_kzt": 1000.0,
        }

    def fake_compute_paid_capital_truth(*, db_path: Path, bank_accounts_path: Path, as_of):
        assert db_path != source_db
        return {
            "cash_actual_kzt": 100.0,
            "inventory_on_hand_paid_kzt": 200.0,
            "inventory_inbound_paid_kzt": 300.0,
            "inventory_on_delivery_paid_kzt": 400.0,
            "total_capital_paid_kzt": 1000.0,
        }

    monkeypatch.setattr(module, "compute_sales_metrics", fake_compute_sales_metrics)
    monkeypatch.setattr(module, "compute_paid_capital_truth", fake_compute_paid_capital_truth)
    before = _sha(source_db)

    errors = module.validate_business_insides(
        db_path=source_db,
        bank_accounts_path=bank_accounts,
        output_dir=output_dir,
        as_of="2026-02-08",
    )

    assert errors == []
    assert _sha(source_db) == before
    with sqlite3.connect(str(source_db)) as conn:
        marker = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name='validator_local_marker'"
        ).fetchone()[0]
    assert marker == 0
