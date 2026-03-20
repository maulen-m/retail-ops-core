from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scripts.generate_po_proposals import generate_po_proposals
from scripts.validate_po_capital_protection import validate_po_capital_protection


def _seed_fact_sku_metrics(db_path: Path, rows: list[dict[str, object]]) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE fact_sku_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                computed_at TEXT,
                sku_key TEXT,
                store_code TEXT,
                status TEXT,
                suggested_order_qty INTEGER,
                roic_monthly REAL,
                k_avg REAL,
                avg_cogs REAL,
                avg_profit REAL,
                d30 REAL,
                days_with_sales INTEGER
            )
            """
        )
        for row in rows:
            conn.execute(
                """
                INSERT INTO fact_sku_metrics (
                    computed_at,
                    sku_key,
                    store_code,
                    status,
                    suggested_order_qty,
                    roic_monthly,
                    k_avg,
                    avg_cogs,
                    avg_profit,
                    d30,
                    days_with_sales
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.get("computed_at"),
                    row.get("sku_key"),
                    row.get("store_code"),
                    row.get("status"),
                    row.get("suggested_order_qty"),
                    row.get("roic_monthly"),
                    row.get("k_avg"),
                    row.get("avg_cogs"),
                    row.get("avg_profit"),
                    row.get("d30"),
                    row.get("days_with_sales"),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def test_generate_po_proposals_uses_rules_roic_formula_when_inputs_available(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _seed_fact_sku_metrics(
        db_path,
        [
            {
                "computed_at": "2026-02-26 08:00:00",
                "sku_key": "SKU-A",
                "store_code": "UNIVERSAL",
                "status": "REORDER",
                "suggested_order_qty": 100,
                "roic_monthly": 9.0,
                "k_avg": 300000.0,
                "avg_cogs": 1000.0,
                "avg_profit": 400.0,
                "d30": 5.0,
                "days_with_sales": 45,
            }
        ],
    )
    report = generate_po_proposals(
        db_path=db_path,
        as_of="2026-02-26",
        output_root=tmp_path / "out",
        strict=True,
    )
    assert report["status"] == "PASS"
    assert report["proposal_count"] == 1
    line = report["lines"][0]
    assert line["roic_source"] == "rules_formula"
    assert line["roic_monthly_pct"] == pytest.approx(20.0, rel=1e-6)
    assert line["capital_at_risk_kzt"] == pytest.approx(100000.0, rel=1e-6)
    assert line["exit_horizon_days"] == 20
    assert line["exit_path"] == "STANDARD_SELL_THROUGH"


def test_validate_po_capital_protection_fails_on_new_sku_cap_breach(tmp_path: Path) -> None:
    as_of = "2026-02-26"
    out_dir = tmp_path / "po" / as_of
    out_dir.mkdir(parents=True)
    proposals_path = out_dir / "po_proposals.json"
    proposals_path.write_text(
        json.dumps(
            {
                "as_of": as_of,
                "lines": [
                    {
                        "sku_key": "SKU-NEW",
                        "store_code": "UNIVERSAL",
                        "suggested_order_qty": 100,
                        "roic_monthly_pct": 22.0,
                        "roic_action": "ORDER_FULL",
                        "capital_at_risk_kzt": 100000.0,
                        "capital_share_pct": 95.0,
                        "is_new_sku": True,
                        "new_sku_cap_limit_pct": 20.0,
                        "new_sku_cap_compliant": False,
                        "exit_horizon_days": 120,
                        "exit_path": "LIQUIDATION_PLAN_REQUIRED",
                    },
                    {
                        "sku_key": "SKU-OLD",
                        "store_code": "UNIVERSAL",
                        "suggested_order_qty": 1,
                        "roic_monthly_pct": 30.0,
                        "roic_action": "ORDER_FULL",
                        "capital_at_risk_kzt": 5000.0,
                        "capital_share_pct": 5.0,
                        "is_new_sku": False,
                        "new_sku_cap_limit_pct": 20.0,
                        "new_sku_cap_compliant": True,
                        "exit_horizon_days": 10,
                        "exit_path": "STANDARD_SELL_THROUGH",
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="capital protection validation failed"):
        validate_po_capital_protection(
            as_of=as_of,
            proposals_json=proposals_path,
            output_root=tmp_path / "validation",
            strict=True,
        )


def test_generate_po_proposals_fails_closed_when_source_table_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.db"
    sqlite3.connect(db_path).close()
    with pytest.raises(RuntimeError, match="po proposal generation failed"):
        generate_po_proposals(
            db_path=db_path,
            as_of="2026-02-26",
            output_root=tmp_path / "out",
            strict=True,
        )
