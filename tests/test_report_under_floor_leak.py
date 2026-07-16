from __future__ import annotations

import csv
import json
from pathlib import Path
import sqlite3
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from report_under_floor_leak import build_under_floor_leak_report


def _make_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE sales_fact_v2 (
                order_id TEXT NOT NULL,
                order_date DATE NOT NULL,
                sku_key TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                my_size TEXT NOT NULL,
                kaspi_offer_name TEXT NOT NULL,
                store_code TEXT DEFAULT 'UNIVERSAL',
                quantity INTEGER NOT NULL,
                sell_price_kzt REAL,
                status TEXT DEFAULT 'DELIVERED'
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO sales_fact_v2 (
                order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
                store_code, quantity, sell_price_kzt, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("1", "2026-06-18", "LINE52", "LINE52_M", "M", "print", "UNIVERSAL", 1, 8000, "DELIVERED"),
                ("2", "2026-06-18", "LINE52", "LINE52_L", "L", "print", "UNIVERSAL", 1, 9000, "DELIVERED"),
                ("3", "2026-06-18", "LINE52", "LINE52_XL", "XL", "print", "UNIVERSAL", 1, 1, "CANCELLED"),
                ("4", "2026-06-18", "MISSING", "MISSING_M", "M", "missing", "STOREB", 2, 10000, "RETURNED"),
                ("5", "2026-06-18", "SUIT-31-TS", "SUIT-31-TS_XL", "XL", "suit", "ACMEWEAR", 1, 9490, "DELIVERED"),
            ],
        )


def _write_floor_csv(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["SKU_key", "COGS", "Wt_kg", "AvgPrc_v7", "Min_price_35pct", "floor_source"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "SKU_key": "LINE52",
                "COGS": "5006",
                "Wt_kg": "0.95",
                "AvgPrc_v7": "9000",
                "Min_price_35pct": "8845",
                "floor_source": "fixture",
            }
        )
        writer.writerow(
            {
                "SKU_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                "COGS": "5919",
                "Wt_kg": "1.1",
                "AvgPrc_v7": "15990",
                "Min_price_35pct": "10769",
                "floor_source": "fixture",
            }
        )
        writer.writerow(
            {
                "SKU_key": "CL_NEW-CLO_KID_ROMBIK_BLACK",
                "COGS": "5447",
                "Wt_kg": "0.93",
                "AvgPrc_v7": "10910",
                "Min_price_35pct": "7608",
                "floor_source": "fixture_v8_5pct",
            }
        )
        writer.writerow(
            {
                "SKU_key": "CL_NEW-CLO_MEN_TAICI_BLACK",
                "COGS": "568",
                "Wt_kg": "0.13",
                "AvgPrc_v7": "970",
                "Min_price_35pct": "767",
                "floor_source": "fixture_v8_5pct",
            }
        )


def _write_config(
    path: Path,
    db_path: Path,
    floor_path: Path,
    *,
    include_scoring_authority: bool = False,
    selloff_wa_path: Path | None = None,
    selloff_fallback_path: Path | None = None,
) -> None:
    config = {
        "db_path": str(db_path),
        "floor_csv_path": str(floor_path),
        "floor_version": "fixture",
        "window_days": 7,
        "max_sales_data_lag_days": 2,
        "excluded_status_tokens": ["CANCEL"],
        "floor_aliases": {
            "SUIT-31-LS": {
                "floor_sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                "source": "fixture_alias",
            },
            "SUIT-31-TS": {
                "floor_sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                "source": "fixture_alias",
            },
        },
        "strict_missing_floor_blocks_green": True,
        "strict_missing_price_blocks_green": True,
    }
    if selloff_wa_path is not None or selloff_fallback_path is not None:
        assert selloff_wa_path is not None
        assert selloff_fallback_path is not None
        config["selloff_price_protect"] = {
            "wa_path": str(selloff_wa_path),
            "local_fallback_path": str(selloff_fallback_path),
            "required_never_raise": True,
        }
    if include_scoring_authority:
        config["scoring_exception_authority"] = {
            "schema_version": "under_floor_leak.scoring_exception_authority.v1",
            "entries": [
                {
                    "id": "fixture_strategic_suit31_ts",
                    "class": "STRATEGIC_BRAND_PRICING",
                    "action": "EXCLUDE_FROM_LEAK_SCORING",
                    "store_code": "ACMEWEAR",
                    "sku_keys": ["SUIT-31-TS"],
                    "decision_ref": "OD2-B 2026-07-02",
                    "decision_record": "docs/plan/green_path_2026-06/green_path_run/OWNER_APPROVALS_20260702_RESUME.md#OD2-B",
                    "reason": "fixture strategic row",
                },
                {
                    "id": "fixture_ls31_blk_carveout",
                    "class": "STRATEGIC_BRAND_PRICING",
                    "action": "ENFORCE_FLOOR",
                    "store_code": "ACMEWEAR",
                    "sku_keys": ["SUIT-31-LS", "LS31-BLK"],
                    "decision_ref": "OD2-B 2026-07-02",
                    "decision_record": "docs/plan/green_path_2026-06/green_path_run/OWNER_APPROVALS_20260702_RESUME.md#OD2-B",
                    "reason": "fixture LS31-BLK carve-out",
                },
            ],
        }
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _replace_sales_rows(path: Path, rows: list[tuple[object, ...]]) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("DELETE FROM sales_fact_v2")
        conn.executemany(
            """
            INSERT INTO sales_fact_v2 (
                order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
                store_code, quantity, sell_price_kzt, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def _write_selloff_yaml(path: Path) -> None:
    path.write_text(
        """schema_version: web_auto.selloff_price_protect.v1
sku_key_prefixes:
  - CL_NEW-CLO_KID_ROMBIK_
product_codes:
  - \"135222379\"
  - \"128541983\"
never_raise: true
owner_decision: fixture owner decision
""",
        encoding="utf-8",
    )


def _write_selloff_json(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "web_auto.selloff_price_protect.v1",
                "sku_key_prefixes": ["CL_NEW-CLO_KID_ROMBIK_"],
                "product_codes": ["135222379", "128541983"],
                "never_raise": True,
                "owner_decision": "fixture owner decision",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_under_floor_report_detects_leaks_missing_floor_and_aliases(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    floor_path = tmp_path / "floor.csv"
    config_path = tmp_path / "config.json"
    output_dir = tmp_path / "out"
    _make_db(db_path)
    _write_floor_csv(floor_path)
    _write_config(config_path, db_path, floor_path)

    report = build_under_floor_leak_report(
        config_path=config_path,
        output_root=output_dir,
        as_of="2026-06-18",
    )

    assert report["gate"] == "RED"
    assert report["sales_source_table"] == "sales_fact_v2"
    assert report["sales_row_count_total"] == 5
    assert report["non_cancelled_row_count"] == 4
    assert report["under_floor_units"] == 2
    assert report["missing_floor_row_count"] == 1
    assert report["under_floor_gap_kzt"] == "2124.00"
    assert report["strategic_brand_pricing_excluded_row_count"] == 0
    assert report["strategic_brand_pricing_excluded_units"] == 0
    assert Path(report["artifacts"]["under_floor_sales_csv"]).exists()
    assert Path(report["artifacts"]["strategic_brand_pricing_excluded_csv"]).exists()
    assert Path(report["artifacts"]["missing_floor_sales_csv"]).exists()


def test_under_floor_report_green_when_no_leaks_and_full_floor_coverage(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    floor_path = tmp_path / "floor.csv"
    config_path = tmp_path / "config.json"
    output_dir = tmp_path / "out"
    _make_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE sales_fact_v2 SET sell_price_kzt = 12000 WHERE status <> 'CANCELLED'")
        conn.execute("UPDATE sales_fact_v2 SET sku_key = 'LINE52', sku_id = 'LINE52_M' WHERE sku_key = 'MISSING'")
    _write_floor_csv(floor_path)
    _write_config(config_path, db_path, floor_path)

    report = build_under_floor_leak_report(
        config_path=config_path,
        output_root=output_dir,
        as_of="2026-06-18",
    )

    assert report["gate"] == "GREEN"
    assert report["under_floor_units"] == 0
    assert report["missing_floor_row_count"] == 0
    assert report["strategic_brand_pricing_excluded_row_count"] == 0
    assert all(check["ok"] for check in report["checks"])


def test_strategic_brand_pricing_exception_is_visible_and_ls31_stays_counted(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    floor_path = tmp_path / "floor.csv"
    config_path = tmp_path / "config.json"
    output_dir = tmp_path / "out"
    _make_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sales_fact_v2 (
                order_id, order_date, sku_key, sku_id, my_size, kaspi_offer_name,
                store_code, quantity, sell_price_kzt, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "6",
                "2026-06-18",
                "SUIT-31-LS",
                "SUIT-31-LS_L",
                "L",
                "LS31-BLK RUSH 3-in-1",
                "ACMEWEAR",
                1,
                8990,
                "DELIVERED",
            ),
        )
    _write_floor_csv(floor_path)
    _write_config(config_path, db_path, floor_path, include_scoring_authority=True)

    report = build_under_floor_leak_report(
        config_path=config_path,
        output_root=output_dir,
        as_of="2026-06-18",
    )

    assert report["gate"] == "RED"
    assert report["non_cancelled_row_count"] == 5
    assert report["under_floor_units"] == 2
    assert report["under_floor_gap_kzt"] == "2624.00"
    assert report["strategic_brand_pricing_excluded_row_count"] == 1
    assert report["strategic_brand_pricing_excluded_units"] == 1
    assert report["strategic_brand_pricing_excluded_gap_kzt"] == "1279.00"
    assert report["strategic_brand_pricing_excluded_rows"][0]["sku_key"] == "SUIT-31-TS"
    assert report["strategic_brand_pricing_excluded_rows"][0]["exception_eval_status"] == "under_floor_excluded"

    under_floor_rows = _read_csv(Path(report["artifacts"]["under_floor_sales_csv"]))
    under_floor_skus = {row["sku_key"] for row in under_floor_rows}
    assert "LINE52" in under_floor_skus
    assert "SUIT-31-LS" in under_floor_skus
    assert "SUIT-31-TS" not in under_floor_skus

    excluded_rows = _read_csv(Path(report["artifacts"]["strategic_brand_pricing_excluded_csv"]))
    assert [row["sku_key"] for row in excluded_rows] == ["SUIT-31-TS"]
    assert excluded_rows[0]["decision_ref"] == "OD2-B 2026-07-02"
    assert excluded_rows[0]["exception_action"] == "EXCLUDE_FROM_LEAK_SCORING"


def test_default_config_records_owner_approved_compact_beli_ts_aliases() -> None:
    config = json.loads((ROOT / "config" / "validation" / "under_floor_leak.json").read_text(encoding="utf-8"))
    aliases = config["floor_aliases"]

    for sku_key in ("LINE-21-TS", "LINE-31-TS"):
        alias = aliases[sku_key]
        assert alias["floor_sku_key"] == "CL_OC_MEN_LINE51_WHITE"
        assert "OWNER_APPROVAL_2026_06_18_OA_PRICE03_LINE" in alias["source"]
        assert "no price-write or external-write authority" in alias["source"]


def test_default_config_records_od2_b_strategic_brand_pricing_authority() -> None:
    config = json.loads((ROOT / "config" / "validation" / "under_floor_leak.json").read_text(encoding="utf-8"))
    entries = config["scoring_exception_authority"]["entries"]
    by_id = {entry["id"]: entry for entry in entries}

    assert by_id["OD2_B_20260702_ACMEWEAR_LINE31_CURRENT"]["action"] == "EXCLUDE_FROM_LEAK_SCORING"
    assert by_id["OD2_B_20260702_ACMEWEAR_LINE61_PARENT_CURRENT"]["sku_keys"] == [
        "CL_NEW-CLO2_MEN_SUIT-61_BLACK"
    ]
    assert by_id["OD2_B_20260702_ACMEWEAR_LINE61_SUBBUNDLE_TS_CURRENT"]["sku_keys"] == ["SUIT-31-TS"]
    assert by_id["OD2_B_20260702_ACMEWEAR_LINE51_SUBBUNDLE_TS_CURRENT"]["sku_keys"] == [
        "LINE-21-TS",
        "LINE-31-TS",
    ]
    assert by_id["OD2_B_20260702_ACMEWEAR_LS31_BLK_CARVEOUT_CURRENT"]["action"] == "ENFORCE_FLOOR"
    assert "SUIT-31-LS" in by_id["OD2_B_20260702_ACMEWEAR_LS31_BLK_CARVEOUT_CURRENT"]["sku_keys"]

    for entry in entries:
        assert entry["class"] == "STRATEGIC_BRAND_PRICING"
        assert entry["store_code"] == "ACMEWEAR"
        assert entry["decision_ref"] == "OD2-B 2026-07-02"
        assert (
            entry["decision_record"]
            == "docs/plan/green_path_2026-06/green_path_run/OWNER_APPROVALS_20260702_RESUME.md#OD2-B"
        )
        assert entry.get("sku_keys") or entry.get("sku_key_prefixes")


def test_kid_rombik_7990_is_above_v8_floor_and_not_a_lift_candidate(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    floor_path = tmp_path / "floor.csv"
    config_path = tmp_path / "config.json"
    output_dir = tmp_path / "out"
    _make_db(db_path)
    _replace_sales_rows(
        db_path,
        [
            (
                "kid-above",
                "2026-07-17",
                "CL_NEW-CLO_KID_ROMBIK_BLACK",
                "CL_NEW-CLO_KID_ROMBIK_BLACK_2XL",
                "2XL",
                "KID ROMBIK",
                "UNIVERSAL",
                1,
                7990,
                "DELIVERED",
            )
        ],
    )
    _write_floor_csv(floor_path)
    _write_config(config_path, db_path, floor_path)

    report = build_under_floor_leak_report(config_path=config_path, output_root=output_dir, as_of="2026-07-17")

    assert report["gate"] == "GREEN"
    assert report["under_floor_row_count"] == 0
    by_sku = _read_csv(Path(report["artifacts"]["under_floor_by_sku_csv"]))
    assert by_sku[0]["floor_min_price_kzt"] == "7608.00"
    assert by_sku[0]["under_floor_rows"] == "0"


def test_kid_rombik_7000_is_selloff_protected_not_a_lift_candidate(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    floor_path = tmp_path / "floor.csv"
    config_path = tmp_path / "config.json"
    protect_path = tmp_path / "selloff_price_protect.yaml"
    fallback_path = tmp_path / "selloff_price_protect.local.json"
    output_dir = tmp_path / "out"
    _make_db(db_path)
    _replace_sales_rows(
        db_path,
        [
            (
                "kid-protected",
                "2026-07-17",
                "CL_NEW-CLO_KID_ROMBIK_BLACK",
                "CL_NEW-CLO_KID_ROMBIK_BLACK_2XL",
                "2XL",
                "KID ROMBIK",
                "STOREB",
                1,
                7000,
                "DELIVERED",
            )
        ],
    )
    _write_floor_csv(floor_path)
    _write_selloff_yaml(protect_path)
    _write_selloff_json(fallback_path)
    _write_config(
        config_path,
        db_path,
        floor_path,
        selloff_wa_path=protect_path,
        selloff_fallback_path=fallback_path,
    )

    report = build_under_floor_leak_report(config_path=config_path, output_root=output_dir, as_of="2026-07-17")

    assert report["gate"] == "GREEN"
    assert report["under_floor_row_count"] == 0
    assert report["selloff_protected"]["row_count"] == 1
    protected = report["selloff_protected"]["rows"][0]
    assert protected["floor_min_price_kzt"] == "7608.00"
    assert protected["protection_eval_status"] == "under_floor_protected"
    assert _read_csv(Path(report["artifacts"]["under_floor_sales_csv"])) == []
    assert _read_csv(Path(report["artifacts"]["under_floor_by_sku_csv"])) == []


def test_unprotected_taici_700_is_a_v8_lift_candidate(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    floor_path = tmp_path / "floor.csv"
    config_path = tmp_path / "config.json"
    protect_path = tmp_path / "selloff_price_protect.yaml"
    fallback_path = tmp_path / "selloff_price_protect.local.json"
    output_dir = tmp_path / "out"
    _make_db(db_path)
    _replace_sales_rows(
        db_path,
        [
            (
                "taici-below",
                "2026-07-17",
                "CL_NEW-CLO_MEN_TAICI_BLACK",
                "CL_NEW-CLO_MEN_TAICI_BLACK_M",
                "M",
                "TAICI BLACK",
                "UNIVERSAL",
                1,
                700,
                "DELIVERED",
            )
        ],
    )
    _write_floor_csv(floor_path)
    _write_selloff_yaml(protect_path)
    _write_selloff_json(fallback_path)
    _write_config(
        config_path,
        db_path,
        floor_path,
        selloff_wa_path=protect_path,
        selloff_fallback_path=fallback_path,
    )

    report = build_under_floor_leak_report(config_path=config_path, output_root=output_dir, as_of="2026-07-17")

    assert report["gate"] == "RED"
    assert report["selloff_protected"]["row_count"] == 0
    assert report["under_floor_row_count"] == 1
    lift_rows = _read_csv(Path(report["artifacts"]["under_floor_sales_csv"]))
    assert lift_rows[0]["sku_key"] == "CL_NEW-CLO_MEN_TAICI_BLACK"
    assert lift_rows[0]["floor_min_price_kzt"] == "767.00"
    by_sku = _read_csv(Path(report["artifacts"]["under_floor_by_sku_csv"]))
    assert by_sku[0]["under_floor_rows"] == "1"


def test_missing_wa_yaml_uses_local_fallback_and_emits_warning(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    floor_path = tmp_path / "floor.csv"
    config_path = tmp_path / "config.json"
    missing_wa_path = tmp_path / "missing" / "selloff_price_protect.yaml"
    fallback_path = tmp_path / "selloff_price_protect.local.json"
    output_dir = tmp_path / "out"
    _make_db(db_path)
    _replace_sales_rows(
        db_path,
        [
            (
                "kid-fallback",
                "2026-07-17",
                "UNMAPPED_SELLOFF_PRODUCT",
                "135222379",
                "2XL",
                "KID ROMBIK",
                "UNIVERSAL",
                1,
                7000,
                "DELIVERED",
            )
        ],
    )
    _write_floor_csv(floor_path)
    _write_selloff_json(fallback_path)
    _write_config(
        config_path,
        db_path,
        floor_path,
        selloff_wa_path=missing_wa_path,
        selloff_fallback_path=fallback_path,
    )

    with pytest.warns(RuntimeWarning, match="using AB-local fallback"):
        report = build_under_floor_leak_report(config_path=config_path, output_root=output_dir, as_of="2026-07-17")

    assert report["gate"] == "GREEN"
    assert report["selloff_protected"]["source_kind"] == "ab_local_fallback"
    assert report["selloff_protected"]["source_path"] == str(fallback_path)
    assert report["selloff_protected"]["warnings"]
    assert report["selloff_protected"]["rows"][0]["protection_match"] == "product_code:135222379"
    protect_check = next(check for check in report["checks"] if check["check"] == "selloff_price_protect_config_valid")
    assert protect_check["ok"] is True
    assert "warnings=1" in protect_check["details"]
