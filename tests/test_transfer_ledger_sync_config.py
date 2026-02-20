import yaml
from pathlib import Path


def test_transfer_ledger_sync_required_sources():
    config_path = Path(__file__).resolve().parents[1] / "config" / "transfer_ledger_sync.yaml"
    data = yaml.safe_load(config_path.read_text())
    settings = data.get("settings") or {}
    required = settings.get("required_sources") or []
    assert required == ["exchanger_emails"], "Binance sources must be removed from sync freshness gate"
