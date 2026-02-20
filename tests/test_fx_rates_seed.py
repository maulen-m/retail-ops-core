from datetime import date
from pathlib import Path
import sqlite3

from scripts.upsert_fx_rates import build_fx_input, upsert_fx_rates
from scripts import validate_params as vp


def test_upsert_fx_rates_seed_and_validate(tmp_path):
    db_path = Path(tmp_path) / "app.db"
    db_path.touch()

    fx = build_fx_input(
        effective_date=date.today(),
        usdt_kzt=510.0,
        usdt_cny=6.80,
        usd_kzt=514.0,
        dlv_rate_usd_kg=2.66,
        cny_kzt=None,
        provider="MANUAL",
        source="pytest",
        force=False,
    )
    upsert_fx_rates(fx, db_path=db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        count = conn.execute("SELECT COUNT(*) FROM dim_fx_rates").fetchone()[0]
        assert count == 1

        result = vp.ValidationResult()
        vp.validate_fx_rates(conn, result)
        assert not result.has_errors
        assert not result.has_warnings
    finally:
        conn.close()
