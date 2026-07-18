from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts.validate_sales_archive_statusdate_mapped import (
    _build_parser,
    validate_sales_archive_statusdate_mapped,
)


def _write_dataset(root: Path, *, since: str, until: str) -> None:
    out = root / f"{since}_to_{until}"
    out.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        [
            {
                "line_id": "L1",
                "order_id": "O1",
                "transaction_date": "2026-02-10",
                "transaction_month": "2026-02",
                "transaction_date_source": "creation_date_fallback",
                "store_code": "STOREB",
                "status_internal": "DELIVERED",
                "return_flag": "0",
                "quantity": "1",
                "gross_rev_kzt": "1000",
                "net_rev_kzt": "1000",
                "mapped_sku_key": "SKU_A",
                "mapped_sku_id": "SKU_A_XL",
                "mapped_size": "XL",
            },
            {
                "line_id": "L2",
                "order_id": "O2",
                "transaction_date": "2026-02-10",
                "transaction_month": "2026-02",
                "transaction_date_source": "status_change_date",
                "store_code": "UNIVERSAL",
                "status_internal": "CANCELLED",
                "return_flag": "0",
                "quantity": "1",
                "gross_rev_kzt": "1000",
                "net_rev_kzt": "0",
                "mapped_sku_key": "SKU_B",
                "mapped_sku_id": "SKU_B_M",
                "mapped_size": "M",
            },
            {
                "line_id": "L3",
                "order_id": "O3",
                "transaction_date": "2026-02-10",
                "transaction_month": "2026-02",
                "transaction_date_source": "status_change_date",
                "store_code": "ACMEWEAR",
                "status_internal": "RETURNED",
                "return_flag": "1",
                "quantity": "1",
                "gross_rev_kzt": "1000",
                "net_rev_kzt": "0",
                "mapped_sku_key": "SKU_C",
                "mapped_sku_id": "SKU_C_L",
                "mapped_size": "L",
            },
            {
                "line_id": "L4",
                "order_id": "O4",
                "transaction_date": "2026-02-10",
                "transaction_month": "2026-02",
                "transaction_date_source": "status_change_date",
                "store_code": "MELVIS",
                "status_internal": "CANCELLED",
                "return_flag": "0",
                "quantity": "1",
                "gross_rev_kzt": "1000",
                "net_rev_kzt": "0",
                "mapped_sku_key": "SKU_D",
                "mapped_sku_id": "SKU_D_S",
                "mapped_size": "S",
            },
            {
                "line_id": "L5",
                "order_id": "O5",
                "transaction_date": "2026-02-10",
                "transaction_month": "2026-02",
                "transaction_date_source": "status_change_date",
                "store_code": "11KZ",
                "status_internal": "CANCELLED",
                "return_flag": "0",
                "quantity": "1",
                "gross_rev_kzt": "1000",
                "net_rev_kzt": "0",
                "mapped_sku_key": "SKU_E",
                "mapped_sku_id": "SKU_E_XL",
                "mapped_size": "XL",
            },
        ]
    )
    csv_path = out / "ArchiveSales_ALL_STORES_statusdate_mapped.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8")

    schema = {
        "columns": {
            "line_id": "str",
            "order_id": "str",
            "transaction_date": "date",
            "transaction_month": "yyyy-mm",
            "transaction_date_source": "str",
            "store_code": "str",
            "status_internal": "str",
            "return_flag": "int",
            "quantity": "float",
            "gross_rev_kzt": "float",
            "net_rev_kzt": "float",
            "mapped_sku_key": "str",
            "mapped_sku_id": "str",
            "mapped_size": "str",
        }
    }
    (out / "schema.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"output": {"rows": int(len(df))}}
    (out / "source_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def test_validate_sales_archive_statusdate_mapped_parser_default_cutover() -> None:
    parser = _build_parser()
    args = parser.parse_args(["--since", "2025-06-06", "--until", "2026-03-04"])
    assert args.strict_statusdate_required_since == "2026-02-27"


def test_validate_sales_archive_statusdate_mapped_requires_sku_id_column(
    tmp_path: Path,
) -> None:
    since = "2026-02-01"
    until = "2026-02-28"
    data_root = tmp_path / "data"
    _write_dataset(data_root, since=since, until=until)
    range_dir = data_root / f"{since}_to_{until}"

    csv_path = range_dir / "ArchiveSales_ALL_STORES_statusdate_mapped.csv"
    frame = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    frame.drop(columns=["mapped_sku_id"]).to_csv(csv_path, index=False, encoding="utf-8")

    schema_path = range_dir / "schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    del schema["columns"]["mapped_sku_id"]
    schema_path.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    report = validate_sales_archive_statusdate_mapped(
        since=date.fromisoformat(since),
        until=date.fromisoformat(until),
        data_root=data_root,
        output_root=tmp_path / "out",
        strict=False,
        strict_statusdate_required_since=date(2026, 2, 27),
        min_delivered_mapping_coverage=0.5,
    )

    assert report["status"] == "FAIL"
    assert "csv missing required columns: mapped_sku_id" in report["errors"]
    assert "schema missing required columns: mapped_sku_id" in report["errors"]


def test_validate_sales_archive_statusdate_mapped_cutover_controls_fallback_gate(tmp_path: Path) -> None:
    since = "2025-06-06"
    until = "2026-03-04"
    _write_dataset(tmp_path / "data", since=since, until=until)
    output_root = tmp_path / "out"

    with pytest.raises(RuntimeError):
        validate_sales_archive_statusdate_mapped(
            since=date.fromisoformat(since),
            until=date.fromisoformat(until),
            data_root=tmp_path / "data",
            output_root=output_root,
            strict=True,
            strict_statusdate_required_since=date(2026, 1, 1),
            min_delivered_mapping_coverage=0.5,
        )

    report = validate_sales_archive_statusdate_mapped(
        since=date.fromisoformat(since),
        until=date.fromisoformat(until),
        data_root=tmp_path / "data",
        output_root=output_root,
        strict=True,
        strict_statusdate_required_since=date(2026, 2, 20),
        min_delivered_mapping_coverage=0.5,
    )
    assert report["status"] == "PASS"
