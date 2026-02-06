from pathlib import Path


def test_safe_ship_runs_transfer_ledger_validator():
    script = Path("scripts/safe_ship.sh").read_text(encoding="utf-8")
    assert "python3 scripts/validate_transfer_ledger.py --strict" in script
