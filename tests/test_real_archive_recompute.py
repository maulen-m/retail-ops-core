import sqlite3
from pathlib import Path
from types import SimpleNamespace

import scripts.generate_po_dashboard_data as dashboard


def _init_snapshot_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE fact_inventory_snapshot_size (
            snapshot_date TEXT,
            sku_key TEXT,
            my_size TEXT,
            current_stock REAL,
            inbound_stock REAL
        );
        """
    )
    rows = [
        ("2026-01-21", "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "2XL", 25, 240),
        ("2026-01-21", "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "3XL", 15, 185),
        ("2026-01-21", "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "4XL", 5, 60),
        ("2026-01-21", "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "L", 25, 240),
        ("2026-01-21", "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "M", 10, 110),
        ("2026-01-21", "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "S", 5, 45),
        ("2026-01-21", "CL_NEW-CLO2_MEN_SUIT-61_BLACK", "XL", 30, 335),
    ]
    conn.executemany(
        """
        INSERT INTO fact_inventory_snapshot_size (
            snapshot_date, sku_key, my_size, current_stock, inbound_stock
        ) VALUES (?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()


def _base_template() -> dict:
    return {
        "generated_at": "2026-02-06",
        "po_name": "PLAN-0",
        "summary": {"total_units": 0, "skus_with_orders": 0, "skus_without_orders": 1},
        "sku_level": [
            {
                "sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                "sku_name": "SUIT-61 BLACK",
                "stock": 115,
                "inbound": 1215,
                "active_inbound": 0,
                "inbound_total": 1215,
                "stock_at_msg": 1330.0,
                "days_until_arrival": 35,
                "effective_L": 35,
                "consumption_until_arrival": 700.0,
                "pre_arrival": 770,
                "d_sku": 20.0,
                "po_qty_total": 0,
                "target": 577.0,
                "pre_arr_doc": 38.5,
                "post_arr_doc": 38.5,
                "prep_days": 14,
                "po_message_date": "2026-01-21",
                "po_send_date": "2026-02-04",
                "est_arr_date": "2026-02-25",
                "size_orders": {},
                "po_weight_kg": 0.0,
                "weight_per_unit_kg": 1.0,
                "base_cost_cny": 10.0,
                "base_cost_kzt": 780.0,
                "unit_cogs": 1200.0,
                "po_base_cost_cny": 0.0,
                "po_base_cost_kzt": 0.0,
                "po_dlv_usd": 0.0,
                "po_dlv_kzt": 0.0,
                "po_cogs_kzt": 0.0,
                "roic_pct": 56.5,
                "notes": "",
            }
        ],
        "size_level": [
            {
                "sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                "sku_id": "CL_NEW-CLO2_MEN_SUIT-61_BLACK_2XL",
                "size": "2XL",
                "stock": 25,
                "inbound": 240,
                "active_inbound": 0,
                "inbound_total": 240,
                "stock_at_msg": 265.0,
                "days_until_arrival": 35,
                "effective_L": 35,
                "consumption_until_arrival": 138.8,
                "pre_arrival": 126,
                "d_size": 3.9653,
                "order_qty": 0,
                "weight_kg": 0.0,
                "pre_arr_doc": 31.8,
                "post_arr_doc": 31.8,
                "prep_days": 14,
                "po_message_date": "2026-01-21",
                "po_send_date": "2026-02-04",
                "est_arr_date": "2026-02-25",
                "target": 0,
                "rop_size": 0,
                "deficit_size": 0,
                "roic_pct": 56.5,
                "notes": "",
            }
        ],
    }


def _po_actual() -> dict:
    return {
        "po_id": "PO-5",
        "message_date": "2026-01-21",
        "ship_date_seller": "2026-02-04",
        "status": "SHIPPED_CARGO",
        "orders_by_sku": {
            "CL_NEW-CLO2_MEN_SUIT-61_BLACK": {
                "2XL": 240,
                "3XL": 185,
                "4XL": 60,
                "L": 240,
                "M": 110,
                "S": 45,
                "XL": 335,
            }
        },
    }


def _po_actual_with_parts() -> dict:
    po = _po_actual()
    po["orders_by_sku_parts"] = {
        "CL_NEW-CLO2_MEN_SUIT-61_BLACK": {
            "2XL": [{"po_part_id": "PO-5.2", "qty": 240}],
            "3XL": [{"po_part_id": "PO-5.2", "qty": 185}],
            "4XL": [{"po_part_id": "PO-5.2", "qty": 60}],
            "L": [{"po_part_id": "PO-5.2", "qty": 240}],
            "M": [{"po_part_id": "PO-5.2", "qty": 110}],
            "S": [{"po_part_id": "PO-5.2", "qty": 45}],
            "XL": [{"po_part_id": "PO-5.2", "qty": 335}],
        }
    }
    return po


def test_real_archive_recomputes_from_message_snapshot_excluding_self_inbound(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _init_snapshot_db(db_path)

    out = dashboard.build_real_archive_data(
        _base_template(),
        _po_actual(),
        params=SimpleNamespace(L=21),
        fx_rates=SimpleNamespace(dlv_rate_usd_kg=2.66, usd_kzt=520.0),
        db_path=db_path,
    )
    sku = out["sku_level"][0]
    assert sku["baseline_snapshot_date"] == "2026-01-21"
    assert sku["stock_at_msg"] == 115.0
    assert sku["inbound"] == 0
    assert sku["pre_arrival"] == 0
    assert sku["pre_arr_doc"] == 0.0


def test_real_archive_post_doc_uses_recomputed_pre_arrival_not_stale_plan_value(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _init_snapshot_db(db_path)

    out = dashboard.build_real_archive_data(
        _base_template(),
        _po_actual(),
        params=SimpleNamespace(L=21),
        fx_rates=SimpleNamespace(dlv_rate_usd_kg=2.66, usd_kzt=520.0),
        db_path=db_path,
    )
    sku = out["sku_level"][0]
    assert sku["post_arr_doc"] == 60.8
    assert sku["post_arr_doc"] != 99.2


def test_real_archive_size_sum_matches_sku_total_and_doc_monotonicity(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _init_snapshot_db(db_path)

    out = dashboard.build_real_archive_data(
        _base_template(),
        _po_actual(),
        params=SimpleNamespace(L=21),
        fx_rates=SimpleNamespace(dlv_rate_usd_kg=2.66, usd_kzt=520.0),
        db_path=db_path,
    )
    sku = out["sku_level"][0]
    size_rows = [r for r in out["size_level"] if r["sku_key"] == sku["sku_key"]]
    assert sum(int(r["order_qty"]) for r in size_rows) == int(sku["po_qty_total"])
    assert sku["post_arr_doc"] > sku["pre_arr_doc"]


def test_real_archive_adds_consumption_capped_field(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_snapshot_db(db_path)

    out = dashboard.build_real_archive_data(
        _base_template(),
        _po_actual(),
        params=SimpleNamespace(L=21),
        fx_rates=SimpleNamespace(dlv_rate_usd_kg=2.66, usd_kzt=520.0),
        db_path=db_path,
    )
    sku = out["sku_level"][0]
    assert sku["consumption_until_arrival"] == 700.0
    assert sku["consumption_until_arrival_capped"] == 115.0


def test_real_archive_propagates_po_part_id_to_size_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _init_snapshot_db(db_path)

    out = dashboard.build_real_archive_data(
        _base_template(),
        _po_actual_with_parts(),
        params=SimpleNamespace(L=21),
        fx_rates=SimpleNamespace(dlv_rate_usd_kg=2.66, usd_kzt=520.0),
        db_path=db_path,
    )
    rows = [r for r in out["size_level"] if int(r.get("order_qty", 0) or 0) > 0]
    assert rows
    assert {r.get("po_part_id") for r in rows} == {"PO-5.2"}
