import sqlite3
from pathlib import Path
from types import SimpleNamespace

from scripts import validate_inventory_cost_drift


SNAPSHOT_DATE = "2026-02-05"


def _seed_snapshot(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE fact_inventory_snapshot_size (
            snapshot_date TEXT,
            sku_key TEXT,
            current_stock REAL,
            inbound_stock REAL
        );

        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            cogs_kzt REAL,
            base_cost_cny REAL,
            weight_kg REAL
        );
        """
    )
    conn.execute(
        """
        INSERT INTO fact_inventory_snapshot_size (snapshot_date, sku_key, current_stock, inbound_stock)
        VALUES (?, 'SKU_1', 10, 20)
        """,
        (SNAPSHOT_DATE,),
    )
    conn.execute(
        """
        INSERT INTO dim_sku (sku_key, cogs_kzt, base_cost_cny, weight_kg)
        VALUES ('SKU_1', 100.0, 0.0, 0.0)
        """
    )
    conn.commit()
    conn.close()


def _seed_cashflow_row(
    db_path: Path,
    on_hand: float,
    inbound: float,
    on_delivery: float | None,
    inventory_cost_close: float,
) -> None:
    conn = sqlite3.connect(str(db_path))
    if on_delivery is None:
        conn.executescript(
            """
            CREATE TABLE fact_cashflow_daily (
                date TEXT PRIMARY KEY,
                inventory_on_hand_close REAL,
                inventory_inbound_close REAL,
                inventory_cost_close REAL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO fact_cashflow_daily (
                date, inventory_on_hand_close, inventory_inbound_close, inventory_cost_close
            ) VALUES (?, ?, ?, ?)
            """,
            (SNAPSHOT_DATE, on_hand, inbound, inventory_cost_close),
        )
    else:
        conn.executescript(
            """
            CREATE TABLE fact_cashflow_daily (
                date TEXT PRIMARY KEY,
                inventory_on_hand_close REAL,
                inventory_inbound_close REAL,
                inventory_on_delivery_close REAL,
                inventory_cost_close REAL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO fact_cashflow_daily (
                date,
                inventory_on_hand_close,
                inventory_inbound_close,
                inventory_on_delivery_close,
                inventory_cost_close
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (SNAPSHOT_DATE, on_hand, inbound, on_delivery, inventory_cost_close),
        )
    conn.commit()
    conn.close()


def _patch_fx(monkeypatch) -> None:
    monkeypatch.setattr(
        validate_inventory_cost_drift,
        "get_fx_rates",
        lambda *_args, **_kwargs: SimpleNamespace(
            cny_kzt=75.0,
            dlv_rate_usd_kg=2.66,
            usd_kzt=520.0,
        ),
    )


def test_drift_uses_all_inventory_components_including_on_delivery(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "app.db"
    _seed_snapshot(db_path)
    _seed_cashflow_row(
        db_path=db_path,
        on_hand=1000.0,
        inbound=1000.0,
        on_delivery=1000.0,
        inventory_cost_close=3000.0,
    )
    _patch_fx(monkeypatch)

    rc = validate_inventory_cost_drift.validate_drift(
        db_path=db_path,
        as_of=SNAPSHOT_DATE,
        tolerance_pct=0.0,
        tolerance_kzt=0.0,
    )

    assert rc == 0


def test_drift_fails_when_total_inventory_components_outside_tolerance(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "app.db"
    _seed_snapshot(db_path)
    _seed_cashflow_row(
        db_path=db_path,
        on_hand=1000.0,
        inbound=1000.0,
        on_delivery=500.0,
        inventory_cost_close=2500.0,
    )
    _patch_fx(monkeypatch)

    rc = validate_inventory_cost_drift.validate_drift(
        db_path=db_path,
        as_of=SNAPSHOT_DATE,
        tolerance_pct=0.0,
        tolerance_kzt=0.0,
    )

    assert rc == 1


def test_drift_fallback_to_inventory_cost_close_when_components_zero(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "app.db"
    _seed_snapshot(db_path)
    _seed_cashflow_row(
        db_path=db_path,
        on_hand=0.0,
        inbound=0.0,
        on_delivery=0.0,
        inventory_cost_close=3000.0,
    )
    _patch_fx(monkeypatch)

    rc = validate_inventory_cost_drift.validate_drift(
        db_path=db_path,
        as_of=SNAPSHOT_DATE,
        tolerance_pct=0.0,
        tolerance_kzt=0.0,
    )

    assert rc == 0


def test_drift_handles_missing_on_delivery_column_with_safe_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "app.db"
    _seed_snapshot(db_path)
    _seed_cashflow_row(
        db_path=db_path,
        on_hand=1000.0,
        inbound=2000.0,
        on_delivery=None,
        inventory_cost_close=3000.0,
    )
    _patch_fx(monkeypatch)

    rc = validate_inventory_cost_drift.validate_drift(
        db_path=db_path,
        as_of=SNAPSHOT_DATE,
        tolerance_pct=0.0,
        tolerance_kzt=0.0,
    )

    assert rc == 0
