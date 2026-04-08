#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import posixpath
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict, Optional
import xml.etree.ElementTree as ET

from openpyxl.utils import get_column_letter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.paths import data_path
from scripts.import_orders_to_crm import _resolve_crm_template_path, restore_crm_workbook_from_template


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

DEFAULT_WORKBOOK = data_path("excel_ui", "SALES_KSP_CRM_V3.xlsx")
SENTINEL_CF_FORMULA = '$M2="CL_OC_MEN_LINE52_BLACK"'


def _backup_file(target: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = backup_dir / f"{target.stem}.sku_formula_contract_{ts}.bak"
    shutil.copy2(target, out)
    return out


def _normalize_header(value: str) -> str:
    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())


def _norm_target(base_path: str, target: str) -> str:
    base = posixpath.dirname(base_path)
    return posixpath.normpath(posixpath.join(base, target)).lstrip("/")


def _write_xml(path: Path, root: ET.Element) -> None:
    path.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))


def _rewrite_zip_from_tree(src_root: Path, out_path: Path) -> None:
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(src_root.rglob("*")):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(src_root).as_posix())


def _discover_table_to_sheet(root_dir: Path) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    worksheets_dir = root_dir / "xl" / "worksheets"
    for ws_path in sorted(worksheets_dir.glob("sheet*.xml")):
        rels_path = worksheets_dir / "_rels" / f"{ws_path.name}.rels"
        rel_map: Dict[str, str] = {}
        if rels_path.exists():
            rels_root = ET.fromstring(rels_path.read_bytes())
            rel_map = {
                rel.attrib.get("Id", ""): rel.attrib.get("Target", "")
                for rel in rels_root.findall(f"{{{PKG_REL_NS}}}Relationship")
            }

        ws_root = ET.fromstring(ws_path.read_bytes())
        table_parts = ws_root.find(f"{{{MAIN_NS}}}tableParts")
        if table_parts is None:
            continue
        for part in table_parts.findall(f"{{{MAIN_NS}}}tablePart"):
            rid = part.attrib.get(f"{{{REL_NS}}}id", "")
            target = rel_map.get(rid)
            if not target:
                continue
            table_rel = _norm_target(f"xl/worksheets/{ws_path.name}", target)
            mapping[table_rel] = ws_path.relative_to(root_dir).as_posix()
    return mapping


def _repair_table_contract(
    table_root: ET.Element,
    *,
    worksheet_path: Optional[Path],
    apply: bool,
) -> dict[str, object]:
    table_ref = table_root.attrib.get("ref", "")
    start_ref, end_ref = table_ref.split(":")
    start_col_letters = "".join(ch for ch in start_ref if ch.isalpha())
    start_row = int("".join(ch for ch in start_ref if ch.isdigit()))
    end_row = int("".join(ch for ch in end_ref if ch.isdigit()))
    start_col_num = 0
    for ch in start_col_letters:
        start_col_num = start_col_num * 26 + (ord(ch) - 64)

    columns_parent = table_root.find(f"{{{MAIN_NS}}}tableColumns")
    table_columns = columns_parent.findall(f"{{{MAIN_NS}}}tableColumn") if columns_parent is not None else []
    sku_col_idx = None
    sku_col_node = None
    for idx, table_col in enumerate(table_columns, start=1):
        if _normalize_header(table_col.attrib.get("name", "")) == "skukey":
            sku_col_idx = idx
            sku_col_node = table_col
            break

    stats: dict[str, object] = {
        "table_ref": table_ref,
        "sku_key_table_formula_array": False,
        "sku_key_array_cells": 0,
        "sku_key_formula_text": "",
        "tables_repaired": 0,
        "worksheet_patched": False,
    }
    if sku_col_idx is None or sku_col_node is None:
        return stats

    calc_formula = sku_col_node.find(f"{{{MAIN_NS}}}calculatedColumnFormula")
    calc_formula_text = (calc_formula.text or "").strip() if calc_formula is not None and calc_formula.text else ""
    if calc_formula_text.startswith("="):
        calc_formula_text = calc_formula_text[1:]
    if calc_formula is not None and calc_formula.attrib.get("array") in {"1", "true", "True"}:
        stats["sku_key_table_formula_array"] = True

    first_formula_text = ""
    if worksheet_path is not None and worksheet_path.exists():
        ws_root = ET.fromstring(worksheet_path.read_bytes())
        target_col_letters = get_column_letter(start_col_num + sku_col_idx - 1)
        for cell in ws_root.findall(f".//{{{MAIN_NS}}}c"):
            cell_ref = cell.attrib.get("r", "")
            if not cell_ref.startswith(target_col_letters):
                continue
            row_num_text = cell_ref[len(target_col_letters):]
            if not row_num_text.isdigit():
                continue
            row_num = int(row_num_text)
            if row_num < start_row + 1 or row_num > end_row:
                continue
            formula = cell.find(f"{{{MAIN_NS}}}f")
            if formula is None:
                continue
            formula_text = (formula.text or "").strip()
            if formula_text.startswith("="):
                formula_text = formula_text[1:]
            if formula.attrib.get("t") == "array":
                stats["sku_key_array_cells"] = int(stats["sku_key_array_cells"]) + 1
                if apply:
                    formula.attrib.pop("t", None)
                    formula.attrib.pop("ref", None)
                    stats["worksheet_patched"] = True
            if formula_text and not first_formula_text:
                first_formula_text = formula_text

        if apply and stats["worksheet_patched"]:
            _write_xml(worksheet_path, ws_root)

    formula_text = calc_formula_text or first_formula_text
    stats["sku_key_formula_text"] = formula_text
    if apply:
        if calc_formula is None and formula_text:
            calc_formula = ET.SubElement(sku_col_node, f"{{{MAIN_NS}}}calculatedColumnFormula")
            stats["tables_repaired"] = int(stats["tables_repaired"]) + 1
        if calc_formula is not None:
            if calc_formula.attrib.pop("array", None) is not None:
                stats["tables_repaired"] = int(stats["tables_repaired"]) + 1
            current_text = (calc_formula.text or "").strip()
            if current_text.startswith("="):
                current_text = current_text[1:]
            if formula_text and current_text != formula_text:
                calc_formula.text = formula_text
                stats["tables_repaired"] = int(stats["tables_repaired"]) + 1
            elif current_text.startswith("="):
                calc_formula.text = current_text
    return stats


def inspect_formula_contract(workbook_path: Path) -> dict[str, object]:
    summary: dict[str, object] = {
        "path": str(workbook_path),
        "sku_key_table_formula_array": False,
        "sku_key_array_cells": 0,
        "sku_key_formula_text": "",
        "has_kaspi_name_core_cf_sentinel": False,
        "tables_repaired": 0,
        "worksheet_patched": False,
    }
    with TemporaryDirectory() as td:
        td_path = Path(td)
        with zipfile.ZipFile(workbook_path, "r") as zf:
            zf.extractall(td_path)

        table_to_sheet = _discover_table_to_sheet(td_path)
        tables_dir = td_path / "xl" / "tables"
        for table_path in sorted(tables_dir.glob("table*.xml")):
            table_root = ET.fromstring(table_path.read_bytes())
            rel_table_path = table_path.relative_to(td_path).as_posix()
            worksheet_rel = table_to_sheet.get(rel_table_path)
            worksheet_path = td_path / worksheet_rel if worksheet_rel else None
            table_stats = _repair_table_contract(
                table_root,
                worksheet_path=worksheet_path,
                apply=False,
            )
            if table_stats.get("sku_key_formula_text") and not summary["sku_key_formula_text"]:
                summary["sku_key_formula_text"] = table_stats["sku_key_formula_text"]
            summary["sku_key_table_formula_array"] = bool(
                summary["sku_key_table_formula_array"] or table_stats["sku_key_table_formula_array"]
            )
            summary["sku_key_array_cells"] = int(summary["sku_key_array_cells"]) + int(
                table_stats["sku_key_array_cells"]
            )

        worksheets_dir = td_path / "xl" / "worksheets"
        for sales_sheet in sorted(worksheets_dir.glob("sheet*.xml")):
            sheet_xml = sales_sheet.read_text(encoding="utf-8")
            if SENTINEL_CF_FORMULA in sheet_xml:
                summary["has_kaspi_name_core_cf_sentinel"] = True
                break

    return summary


def _restore_target_from_reference(
    *,
    target_path: Path,
    reference_path: Path,
    is_template: bool,
) -> None:
    if is_template:
        shutil.copy2(reference_path, target_path)
        return

    restore_crm_workbook_from_template(
        workbook_path=target_path,
        template_path=reference_path,
        output_path=target_path,
        verbose=False,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Restore the working CRM formula/style contract from a known-good reference workbook")
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--template", type=Path, default=None)
    parser.add_argument("--reference", type=Path, default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", type=Path, default=data_path("excel_ui", "backups"))
    parser.add_argument("--summary-out", type=Path, default=None)
    args = parser.parse_args(argv)

    workbook = args.workbook.expanduser().resolve()
    template = _resolve_crm_template_path(args.template, required=False)
    reference = (
        Path(args.reference).expanduser().resolve()
        if args.reference
        else (template.resolve() if template is not None else None)
    )
    targets = [("workbook", workbook)]
    if template is not None:
        targets.append(("template", template.resolve()))

    payload: dict[str, object] = {
        "apply": bool(args.apply),
        "targets": {},
        "backups": {},
    }

    for label, target in targets:
        if not target.exists():
            continue
        if args.apply:
            if reference is None or not reference.exists():
                raise FileNotFoundError(
                    "Reference workbook is required for --apply. "
                    "Pass --reference /path/to/known-good.xlsx."
                )
            payload["backups"][label] = str(_backup_file(target, args.backup_dir))
            _restore_target_from_reference(
                target_path=target,
                reference_path=reference,
                is_template=(label == "template"),
            )
        payload["targets"][label] = inspect_formula_contract(target)

    if args.summary_out:
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
