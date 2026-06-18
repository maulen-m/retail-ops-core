import sqlite3

from scripts import apply_line31_whale_blue_owner_stock as whale


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE dim_sku_size (
            sku_id TEXT,
            sku_key TEXT,
            my_size TEXT,
            active_flag INTEGER
        );
        CREATE TABLE stock_ledger (
            ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_date TEXT,
            event_time TEXT,
            event_type TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            store_code TEXT,
            qty_change INTEGER,
            reference_id TEXT,
            reference_type TEXT,
            kaspi_offer_name TEXT,
            notes TEXT,
            input_source TEXT,
            created_by TEXT,
            idempotency_key TEXT
        );
        """
    )
    for size in ("M", "L", "XL", "2XL", "S"):
        conn.execute(
            "INSERT INTO dim_sku_size VALUES (?, ?, ?, 1)",
            (f"{whale.SKU_KEY}_{size}", whale.SKU_KEY, size),
        )
    return conn


def _seed_old_ab_whale_blue_balance(conn: sqlite3.Connection) -> None:
    for size, qty in {"M": 5, "L": 5, "XL": 10, "2XL": 5}.items():
        conn.execute(
            """
            INSERT INTO stock_ledger (
                event_date, event_type, sku_key, sku_id, my_size, store_code,
                qty_change, reference_id, reference_type, input_source, idempotency_key
            )
            VALUES ('2026-04-03', 'INITIAL', ?, ?, ?, 'UNIVERSAL', ?, 'OLD_ANCHOR', 'STOCK_ANCHOR', 'OWNER_APPROVED_ANCHOR', ?)
            """,
            (whale.SKU_KEY, f"{whale.SKU_KEY}_{size}", size, qty, f"OLD:{size}"),
        )
    for size, qty in {"M": -1, "L": -1, "XL": -2, "2XL": -1}.items():
        conn.execute(
            """
            INSERT INTO stock_ledger (
                event_date, event_type, sku_key, sku_id, my_size, store_code,
                qty_change, reference_id, reference_type, input_source, idempotency_key
            )
            VALUES ('2026-04-04', 'ADJUSTMENT', ?, ?, ?, 'UNIVERSAL', ?, 'OLD_BASELINE', 'BASELINE_20PCT_DECREASE', 'OWNER_APPROVED_BASELINE_20PCT', ?)
            """,
            (whale.SKU_KEY, f"{whale.SKU_KEY}_{size}", size, qty, f"BASELINE:{size}"),
        )
    conn.commit()


def test_plan_converges_old_ab_balance_to_owner_target() -> None:
    conn = _conn()
    _seed_old_ab_whale_blue_balance(conn)

    plan = whale.build_plan(conn)

    assert plan.blockers == []
    assert plan.current_balance == {"S": 0, "M": 4, "L": 4, "XL": 8, "2XL": 4, "3XL": 0}
    assert plan.predicted_balance == whale.FINAL_TARGET
    assert len(plan.insert_candidates) == 7
    assert sum(row.qty_change for row in plan.insert_candidates) == 30


def test_plan_is_idempotent_after_owner_events_exist() -> None:
    conn = _conn()
    _seed_old_ab_whale_blue_balance(conn)
    plan = whale.build_plan(conn)
    for candidate in plan.insert_candidates:
        whale._insert_candidate(conn, candidate)
    conn.commit()

    rerun = whale.build_plan(conn)

    assert rerun.blockers == []
    assert rerun.current_balance == whale.FINAL_TARGET
    assert rerun.predicted_balance == whale.FINAL_TARGET
    assert len(rerun.insert_candidates) == 0
    assert len([row for row in rerun.candidates if row.action == "EXISTS"]) == 7


def test_plan_blocks_canonical_sales_evidence() -> None:
    conn = _conn()
    _seed_old_ab_whale_blue_balance(conn)
    conn.execute(
        """
        CREATE TABLE sales_fact_v2 (
            order_id TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            kaspi_offer_name TEXT,
            quantity INTEGER
        )
        """
    )
    conn.execute(
        "INSERT INTO sales_fact_v2 VALUES ('ORDER1', ?, ?, 'M', 'Whale Blue', 1)",
        (whale.SKU_KEY, f"{whale.SKU_KEY}_M"),
    )
    conn.commit()

    plan = whale.build_plan(conn)

    assert any("sales_fact_v2" in blocker for blocker in plan.blockers)
