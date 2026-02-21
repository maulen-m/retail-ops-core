from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scripts import validate_profit_publication_integrity as vppi


def _build_dashboard(path: Path) -> None:
    payload = {
        "sku_level": [
            {
                "sku_key": "SKU_A",
                "cogs_unresolved_rows": 2,
                "profit_publishable": False,
                "profit_unit": None,
                "monthly_profit": None,
                "roic_pct": None,
                "profit_margin_pct": None,
            }
        ]
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_validator_flags_business_insides_profit_metrics_when_unresolved(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "app.db"
    sqlite3.connect(db_path).close()

    dashboard = tmp_path / "po_dashboard_data.json"
    _build_dashboard(dashboard)

    business_insides = tmp_path / "BUSINESS_INSIDES_2026-02-08.md"
    business_insides.write_text(
        "\n".join(
            [
                "## Performance",
                "| Metric | Value |",
                "| Avg 7d Profit | ₸123,000 |",
                "- Unresolved COGS rows: `2`.",
                "- Unresolved SKU count: `1`.",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(vppi, "_load_unresolved_from_db", lambda *args, **kwargs: {"SKU_A": 2})

    report = vppi.validate_profit_publication_integrity(
        db_path=db_path,
        as_of="2026-02-08",
        days=7,
        business_insides_path=business_insides,
        po_dashboard_path=dashboard,
    )

    assert report["ok"] is False
    assert any("must be n/a" in err.lower() for err in report["errors"])
