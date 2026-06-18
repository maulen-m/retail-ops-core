from pathlib import Path

import pandas as pd

from core.excel.dim_sku_light_parser import parse_dim_sku_light


def _write_dim_sku_light(path: Path) -> None:
    df = pd.DataFrame(
        [
            {
                "SKU_key": "CL_OC_MEN_LINE52_BLACK",
                "Type": "CL",
                "Wt (kg)": 0.95,
                "CNY": 47,
                "AvgPrc": 9392,
                "Active": 1,
            },
            {
                "SKU_key": "CL_OC_MEN_LINE52_BLACK",
                "Type": "CL",
                "Wt (kg)": 0.07,
                "CNY": 0.19,
                "AvgPrc": 0.2,
                "Active": 1,
            },
            {
                "SKU_key": "OF_SUIT-61_BLK_XL_50",
                "Type": "CL",
                "Wt (kg)": 1.0,
                "CNY": 74,
                "AvgPrc": 25990,
                "Active": 1,
            },
            {
                "SKU_key": "CL_OC_MEN_LINE51_WHITE",
                "Type": "CL",
                "Wt (kg)": 1.1,
                "CNY": 60,
                "AvgPrc": 11990,
                "Active": 0,
            },
            {
                "SKU_key": "CL_OC_MEN_LINE51_WHITE",
                "Type": "CL",
                "Wt (kg)": 1.2,
                "CNY": 62,
                "AvgPrc": 12990,
                "Active": 1,
            },
        ]
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="DIM_SKU_light_v7", index=False, startrow=2)


def test_parser_ignores_helper_rows_with_micro_cny_and_weight(tmp_path: Path) -> None:
    path = tmp_path / "dim_light.xlsx"
    _write_dim_sku_light(path)

    rows, diagnostics = parse_dim_sku_light(path, sheet_name="DIM_SKU_light_v7")

    sku = rows["CL_OC_MEN_LINE52_BLACK"]
    assert sku["base_cost_cny"] == 47.0
    assert sku["weight_kg"] == 0.95
    assert diagnostics["filtered_helper_rows"] >= 1


def test_parser_handles_duplicate_sku_rows_and_selects_canonical_row(tmp_path: Path) -> None:
    path = tmp_path / "dim_light.xlsx"
    _write_dim_sku_light(path)

    rows, diagnostics = parse_dim_sku_light(path, sheet_name="DIM_SKU_light_v7")

    sku = rows["CL_OC_MEN_LINE51_WHITE"]
    assert sku["weight_kg"] == 1.2
    assert sku["base_cost_cny"] == 62.0
    assert diagnostics["duplicate_sku_keys"] >= 1


def test_parser_rejects_rows_without_valid_sku_key_pattern(tmp_path: Path) -> None:
    path = tmp_path / "dim_light.xlsx"
    _write_dim_sku_light(path)

    rows, _ = parse_dim_sku_light(path, sheet_name="DIM_SKU_light_v7")

    assert "OF_SUIT-61_BLK_XL_50" not in rows


def test_parser_emits_source_row_index_for_traceability(tmp_path: Path) -> None:
    path = tmp_path / "dim_light.xlsx"
    _write_dim_sku_light(path)

    rows, _ = parse_dim_sku_light(path, sheet_name="DIM_SKU_light_v7")

    assert rows["CL_OC_MEN_LINE52_BLACK"]["source_row_index"] == 4


def test_parser_accepts_markdown_pipe_table_sheet(tmp_path: Path) -> None:
    path = tmp_path / "dim_light_markdown.xlsx"
    df = pd.DataFrame(
        [
            ["# DIM_SKU_light_v7"],
            ["fallback planning anchor, not operational truth"],
            ["| SKU_key | Type | Wt kg | CNY | Base_KZT | Freight | COGS | AvgPrc | D_final | Demand_basis | Active | Ads/day | Min_price_35pct | Notes |"],
            ["| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: | --- | --- |"],
            ["| CL_OC_MEN_LINE52_BLACK | CL | 0.95 | 47 | 3666 | 1340 | 5006 | 9392 | 3 | FALLBACK_ANCHOR | True | 0 | ~7200 | current markdown-style v7 row |"],
            ["| OF_SUIT-61_BLK_XL_50 | CL | 1.0 | 74 | 0 | 0 | 0 | 25990 | 1 | invalid prefix guard | True | 0 | 0 | helper row |"],
            ["| CL_OC_MEN_LINE51_WHITE | CL | 1.20 | 62 | 0 | 0 | 0 | 12990 | 1 | FALLBACK_ANCHOR | True | 0 | 0 | active canonical row |"],
        ]
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="DIM_SKU_light_v7", index=False, header=False)

    rows, diagnostics = parse_dim_sku_light(path, sheet_name="DIM_SKU_light_v7")

    assert rows["CL_OC_MEN_LINE52_BLACK"]["base_cost_cny"] == 47.0
    assert rows["CL_OC_MEN_LINE52_BLACK"]["weight_kg"] == 0.95
    assert rows["CL_OC_MEN_LINE52_BLACK"]["source_row_index"] == 5
    assert "OF_SUIT-61_BLK_XL_50" not in rows
    assert diagnostics["source_format"] == "markdown_pipe_table"
