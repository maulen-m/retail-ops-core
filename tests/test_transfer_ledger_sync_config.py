import yaml
from pathlib import Path
import sqlite3

from scripts import validate_transfer_ledger_sync_freshness


def test_transfer_ledger_sync_required_sources():
    config_path = Path(__file__).resolve().parents[1] / "config" / "transfer_ledger_sync.yaml"
    data = yaml.safe_load(config_path.read_text())
    settings = data.get("settings") or {}
    required = settings.get("required_sources") or []
    assert required == ["exchanger_emails"], "Binance sources must be removed from sync freshness gate"
    fallback = settings.get("manual_cash_snapshot_fallback") or {}
    assert fallback.get("enabled") is True
    assert "exchanger_emails" in (fallback.get("accepted_for_sources") or [])


def test_transfer_freshness_accepts_current_cash_balances_fallback(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE transfer_ledger_sync_log (
            source TEXT PRIMARY KEY,
            last_success_ts TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO transfer_ledger_sync_log (source, last_success_ts) VALUES (?, ?)",
        ("exchanger_emails", "2026-02-10T10:00:00"),
    )
    conn.commit()
    conn.close()

    project_root = tmp_path
    config_dir = project_root / "config"
    config_dir.mkdir()
    (config_dir / "transfer_ledger_sync.yaml").write_text(
        """
settings:
  max_age_hours: 25
  required_sources:
    - exchanger_emails
  manual_cash_snapshot_fallback:
    enabled: true
    accepted_for_sources:
      - exchanger_emails
    snapshot_path: config/bank_accounts.yaml
    history_path: config/bank_accounts_history.yaml
    source_contains: Cash_Balances
""",
        encoding="utf-8",
    )
    (config_dir / "bank_accounts.yaml").write_text(
        "as_of: 2026-06-01 09:06:51 GMT+5\nstores: {}\n",
        encoding="utf-8",
    )
    (config_dir / "bank_accounts_history.yaml").write_text(
        """
entries:
- as_of: 2026-06-01 09:06:51 GMT+5
  source: manual snapshot (Cash_Balances)
  balances: []
""",
        encoding="utf-8",
    )

    class FixedDateTime:
        @classmethod
        def now(cls):
            from datetime import datetime

            return datetime(2026, 6, 1, 12, 0, 0)

        @classmethod
        def fromisoformat(cls, value):
            from datetime import datetime

            return datetime.fromisoformat(value)

        @classmethod
        def strptime(cls, value, fmt):
            from datetime import datetime

            return datetime.strptime(value, fmt)

    monkeypatch.setattr(validate_transfer_ledger_sync_freshness, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(
        validate_transfer_ledger_sync_freshness,
        "CONFIG_PATH",
        config_dir / "transfer_ledger_sync.yaml",
    )
    monkeypatch.setattr(validate_transfer_ledger_sync_freshness, "datetime", FixedDateTime)

    assert validate_transfer_ledger_sync_freshness.validate(db_path) == 0
    out = capsys.readouterr().out
    assert "sync stale" in out
    assert "accepted via manual Cash_Balances snapshot" in out


def test_transfer_freshness_rejects_stale_cash_balances_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE transfer_ledger_sync_log (
            source TEXT PRIMARY KEY,
            last_success_ts TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO transfer_ledger_sync_log (source, last_success_ts) VALUES (?, ?)",
        ("exchanger_emails", "2026-02-10T10:00:00"),
    )
    conn.commit()
    conn.close()

    project_root = tmp_path
    config_dir = project_root / "config"
    config_dir.mkdir()
    (config_dir / "transfer_ledger_sync.yaml").write_text(
        """
settings:
  max_age_hours: 25
  required_sources:
    - exchanger_emails
  manual_cash_snapshot_fallback:
    enabled: true
    accepted_for_sources:
      - exchanger_emails
    snapshot_path: config/bank_accounts.yaml
    history_path: config/bank_accounts_history.yaml
    source_contains: Cash_Balances
""",
        encoding="utf-8",
    )
    (config_dir / "bank_accounts.yaml").write_text(
        "as_of: 2026-05-20 09:06:51 GMT+5\nstores: {}\n",
        encoding="utf-8",
    )
    (config_dir / "bank_accounts_history.yaml").write_text(
        """
entries:
- as_of: 2026-05-20 09:06:51 GMT+5
  source: manual snapshot (Cash_Balances)
  balances: []
""",
        encoding="utf-8",
    )

    class FixedDateTime:
        @classmethod
        def now(cls):
            from datetime import datetime

            return datetime(2026, 6, 1, 12, 0, 0)

        @classmethod
        def fromisoformat(cls, value):
            from datetime import datetime

            return datetime.fromisoformat(value)

        @classmethod
        def strptime(cls, value, fmt):
            from datetime import datetime

            return datetime.strptime(value, fmt)

    monkeypatch.setattr(validate_transfer_ledger_sync_freshness, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(
        validate_transfer_ledger_sync_freshness,
        "CONFIG_PATH",
        config_dir / "transfer_ledger_sync.yaml",
    )
    monkeypatch.setattr(validate_transfer_ledger_sync_freshness, "datetime", FixedDateTime)

    assert validate_transfer_ledger_sync_freshness.validate(db_path) == 1
