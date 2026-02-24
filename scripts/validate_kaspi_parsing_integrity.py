#!/usr/bin/env python3
"""Validate parsed Kaspi identity integrity and emit machine-readable reports."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.parsers.kaspi_parser import extract_sku_from_article
from scripts.backfill_line61_kaspi_core import CANONICAL_LINE61_CORE, CANONICAL_LINE61_SKU_KEY


DEFAULT_WORKBOOK = Path("excel_ui/SALES_KSP_CRM_V3.xlsx")
DEFAULT_SHEET = "SALES_KSP_CRM_1"
DEFAULT_REPORT_JSON = Path("logs/kaspi_parsing_integrity_report.json")
DEFAULT_REPORT_MD = Path("logs/kaspi_parsing_integrity_report.md")


def _pick_column(columns: list[str], candidates: list[str]) -> str | None:
    colset = {str(col).strip(): col for col in columns}
    for candidate in candidates:
        if candidate in colset:
            return colset[candidate]
    return None


def _looks_prefixed_article(article: str) -> bool:
    text = str(article or "").strip()
    if not text:
        return False
    return bool(text and text[0].isdigit() and " " in text)


def _empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    return str(value).strip() == ""


def validate_workbook(
    *,
    workbook: Path,
    sheet_name: str = DEFAULT_SHEET,
    strict: bool = False,
    report_json: Path | None = None,
    report_md: Path | None = None,
) -> dict[str, Any]:
    workbook = Path(workbook)
    df = pd.read_excel(workbook, sheet_name=sheet_name)
    columns = list(df.columns)

    article_col = _pick_column(columns, ["Артикул", "Kaspi_article", "SKU_ID_KSP"])
    offer_col = _pick_column(columns, ["Название товара в Kaspi Магазине", "KASPI_OFFER_NAME", "Название товара"])
    sku_key_col = _pick_column(columns, ["SKU_key"])
    core_col = _pick_column(columns, ["Kaspi_name_core"])

    if not article_col:
        raise RuntimeError("Could not find article column (Артикул/Kaspi_article/SKU_ID_KSP)")

    anomalies: dict[str, list[dict[str, Any]]] = {
        "missing_sku_key": [],
        "numeric_prefix_not_cleaned": [],
        "line61_sku_mismatch": [],
        "line61_core_mismatch": [],
    }
    rows_scanned = 0

    for idx, row in df.iterrows():
        article = row.get(article_col)
        offer = row.get(offer_col) if offer_col else ""
        if _empty(article) and _empty(offer):
            continue
        rows_scanned += 1
        article_text = str(article or "").strip()
        parsed = extract_sku_from_article(article_text, str(offer or ""))
        parsed_sku_key = str(parsed.get("sku_key") or "").strip()
        actual_sku_key = str(row.get(sku_key_col) or "").strip() if sku_key_col else ""
        actual_core = str(row.get(core_col) or "").strip() if core_col else ""
        article_upper = article_text.upper()

        if not parsed_sku_key:
            anomalies["missing_sku_key"].append(
                {"row": int(idx) + 2, "article": article_text, "offer": str(offer or "")}
            )

        if _looks_prefixed_article(article_text) and parsed_sku_key and parsed_sku_key[:1].isdigit():
            anomalies["numeric_prefix_not_cleaned"].append(
                {
                    "row": int(idx) + 2,
                    "article": article_text,
                    "parsed_sku_key": parsed_sku_key,
                }
            )

        if article_upper.startswith("OF_SUIT-61_BLK_"):
            if parsed_sku_key != CANONICAL_LINE61_SKU_KEY:
                anomalies["line61_sku_mismatch"].append(
                    {
                        "row": int(idx) + 2,
                        "article": article_text,
                        "parsed_sku_key": parsed_sku_key,
                        "expected_sku_key": CANONICAL_LINE61_SKU_KEY,
                    }
                )
            if actual_core and actual_core != CANONICAL_LINE61_CORE:
                anomalies["line61_core_mismatch"].append(
                    {
                        "row": int(idx) + 2,
                        "article": article_text,
                        "actual_core": actual_core,
                        "expected_core": CANONICAL_LINE61_CORE,
                        "actual_sku_key": actual_sku_key,
                    }
                )

    anomaly_counts = {name: len(items) for name, items in anomalies.items()}
    hard_fail = any(anomaly_counts.values())
    report = {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "workbook": str(workbook),
        "sheet_name": sheet_name,
        "rows_scanned": rows_scanned,
        "anomaly_counts": anomaly_counts,
        "hard_fail": hard_fail,
        "anomalies": anomalies,
    }

    if report_json:
        report_json.parent.mkdir(parents=True, exist_ok=True)
        report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if report_md:
        lines = [
            "# Kaspi Parsing Integrity Report",
            "",
            f"- workbook: `{workbook}`",
            f"- sheet: `{sheet_name}`",
            f"- rows_scanned: `{rows_scanned}`",
            f"- hard_fail: `{hard_fail}`",
            "",
            "## Anomaly Counts",
        ]
        for key, value in anomaly_counts.items():
            lines.append(f"- `{key}`: {value}")
        report_md.parent.mkdir(parents=True, exist_ok=True)
        report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if strict and hard_fail:
        raise RuntimeError(f"Parsing integrity hard-fail: {anomaly_counts}")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Kaspi parsing integrity")
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--sheet", default=DEFAULT_SHEET)
    parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--report-md", type=Path, default=DEFAULT_REPORT_MD)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = validate_workbook(
            workbook=args.workbook,
            sheet_name=args.sheet,
            strict=bool(args.strict),
            report_json=args.report_json,
            report_md=args.report_md,
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1

    print("Kaspi parsing integrity: OK")
    print(f"  rows_scanned: {report['rows_scanned']}")
    print(f"  hard_fail: {report['hard_fail']}")
    print(f"  report_json: {args.report_json}")
    print(f"  report_md: {args.report_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
