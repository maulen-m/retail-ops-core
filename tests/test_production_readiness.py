"""Tests for production readiness validation."""

from core.validation.production_readiness import evaluate_production_readiness


def _make_output(sku_level, stock_date="2026-01-02", cutoff_date="2026-01-02"):
    return {
        "summary": {
            "total_skus": len(sku_level),
            "skus_with_orders": sum(1 for sku in sku_level if sku.get("po_qty_total", 0) > 0),
            "total_units": sum(int(sku.get("po_qty_total", 0)) for sku in sku_level),
            "no_demand_estimate": 0,
        },
        "sku_level": sku_level,
        "stock_date": stock_date,
        "cutoff_date": cutoff_date,
    }


def test_readiness_blocks_missing_stock_for_ordered_sku():
    output = _make_output(
        [
            {"sku_key": "SKU1", "po_qty_total": 5, "notes": "NO_STOCK_SNAPSHOT"},
            {"sku_key": "SKU2", "po_qty_total": 0, "notes": ""},
        ]
    )
    report = evaluate_production_readiness(output, db_path=None)

    assert not report.ok
    assert any("Missing stock snapshot" in b for b in report.blockers)


def test_readiness_blocks_stale_stock_date():
    output = _make_output(
        [{"sku_key": "SKU1", "po_qty_total": 0, "notes": ""}],
        stock_date="2026-01-01",
        cutoff_date="2026-01-03",
    )
    report = evaluate_production_readiness(output, db_path=None)

    assert not report.ok
    assert any("Stock snapshot stale" in b for b in report.blockers)


def test_readiness_ok_when_clean():
    output = _make_output(
        [{"sku_key": "SKU1", "po_qty_total": 0, "notes": ""}],
        stock_date="2026-01-02",
        cutoff_date="2026-01-02",
    )
    report = evaluate_production_readiness(output, db_path=None)

    assert report.ok
