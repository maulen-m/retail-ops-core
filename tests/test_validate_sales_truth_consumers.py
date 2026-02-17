from __future__ import annotations

from pathlib import Path

import yaml

from scripts.validate_sales_truth_consumers import (
    load_consumer_contract,
    validate_sales_truth_consumers,
)


def _write_contract(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "disallowed_tables": [
                    "fact_sales",
                    "sales_fact_v2",
                    "fact_sales_daily",
                    "fact_sales_daily_size",
                ],
                "production_scripts": [
                    "scripts/generate_po_dashboard_data.py",
                    "scripts/generate_business_insides.py",
                ],
                "allow_raw_read_scripts": [
                    "scripts/rebuild_fact_sales.py",
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_contract_loader_reads_required_keys(tmp_path: Path) -> None:
    contract_path = tmp_path / "contract.yaml"
    _write_contract(contract_path)
    contract = load_consumer_contract(contract_path)
    assert "fact_sales" in contract["disallowed_tables"]
    assert "scripts/generate_po_dashboard_data.py" in contract["production_scripts"]


def test_validator_flags_disallowed_reads_in_production(tmp_path: Path) -> None:
    contract_path = tmp_path / "contract.yaml"
    _write_contract(contract_path)
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "generate_po_dashboard_data.py").write_text(
        "conn.execute('SELECT * FROM fact_sales')\n",
        encoding="utf-8",
    )
    (scripts_dir / "generate_business_insides.py").write_text(
        "conn.execute('SELECT * FROM view_sales_daily_truth')\n",
        encoding="utf-8",
    )
    (scripts_dir / "rebuild_fact_sales.py").write_text(
        "conn.execute('SELECT * FROM fact_sales')\n",
        encoding="utf-8",
    )

    report = validate_sales_truth_consumers(
        project_root=tmp_path,
        contract_path=contract_path,
    )

    assert report["ok"] is False
    assert any("generate_po_dashboard_data.py" in err for err in report["errors"])
    assert all("rebuild_fact_sales.py" not in err for err in report["errors"])


def test_validator_passes_when_production_scripts_use_published_views(tmp_path: Path) -> None:
    contract_path = tmp_path / "contract.yaml"
    _write_contract(contract_path)
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "generate_po_dashboard_data.py").write_text(
        "conn.execute('SELECT * FROM view_sales_line_truth')\n",
        encoding="utf-8",
    )
    (scripts_dir / "generate_business_insides.py").write_text(
        "conn.execute('SELECT * FROM view_sales_daily_truth')\n",
        encoding="utf-8",
    )
    (scripts_dir / "rebuild_fact_sales.py").write_text(
        "conn.execute('SELECT * FROM fact_sales')\n",
        encoding="utf-8",
    )

    report = validate_sales_truth_consumers(
        project_root=tmp_path,
        contract_path=contract_path,
    )

    assert report["ok"] is True
    assert report["errors"] == []
