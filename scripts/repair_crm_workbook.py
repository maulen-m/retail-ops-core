#!/usr/bin/env python3
"""
Repair Excel workbook package metadata that can trigger "We found a problem with some content".

Safe operations:
- remove externalLink parts + workbook references
- remove broken defined names containing #REF!

Data sheets are not modified.
"""
from __future__ import annotations

import argparse
import posixpath
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict
from lxml import etree as ET
from openpyxl.utils.cell import get_column_letter, range_boundaries


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
CRM_SALES_SHEET_NAME = "SALES_KSP_CRM_1"
CRM_SALES_TABLE_NAME = "tb_SalesRaw"


def _normalize_header(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _load_rels_map(zf: zipfile.ZipFile, rels_path: str) -> Dict[str, str]:
    root = ET.fromstring(zf.read(rels_path))
    return {rel.attrib.get("Id", ""): rel.attrib.get("Target", "") for rel in root.findall(f"{{{PKG_REL_NS}}}Relationship")}


def _norm_target(base_path: str, target: str) -> str:
    base = posixpath.dirname(base_path)
    normalized = posixpath.normpath(posixpath.join(base, target))
    return normalized.lstrip("/")


def _resolve_sales_sheet_package_contract(
    workbook_path: Path,
    *,
    sheet_name: str = CRM_SALES_SHEET_NAME,
    table_name: str = CRM_SALES_TABLE_NAME,
) -> tuple[str, str, int, int] | None:
    with zipfile.ZipFile(workbook_path, "r") as zf:
        names = set(zf.namelist())
        workbook_xml_path = "xl/workbook.xml"
        workbook_rels_path = "xl/_rels/workbook.xml.rels"
        if workbook_xml_path not in names or workbook_rels_path not in names:
            return None

        wb_root = ET.fromstring(zf.read(workbook_xml_path))
        rel_map = _load_rels_map(zf, workbook_rels_path)

        sheet_xml_path = None
        for sheet in wb_root.findall(f".//{{{MAIN_NS}}}sheet"):
            if sheet.attrib.get("name") != sheet_name:
                continue
            rid = sheet.attrib.get(f"{{{REL_NS}}}id", "")
            target = rel_map.get(rid)
            if target:
                sheet_xml_path = _norm_target(workbook_xml_path, target)
                break
        if not sheet_xml_path or sheet_xml_path not in names:
            return None

        sheet_xml = ET.fromstring(zf.read(sheet_xml_path))
        table_parts = sheet_xml.find(f"{{{MAIN_NS}}}tableParts")
        if table_parts is None:
            return None
        sheet_rels_path = posixpath.join(
            posixpath.dirname(sheet_xml_path),
            "_rels",
            f"{posixpath.basename(sheet_xml_path)}.rels",
        )
        if sheet_rels_path not in names:
            return None
        sheet_rel_map = _load_rels_map(zf, sheet_rels_path)

        table_xml_path = None
        for table_part in table_parts.findall(f"{{{MAIN_NS}}}tablePart"):
            rid = table_part.attrib.get(f"{{{REL_NS}}}id", "")
            target = sheet_rel_map.get(rid)
            if not target:
                continue
            candidate_path = _norm_target(sheet_xml_path, target)
            if candidate_path not in names:
                continue
            table_root = ET.fromstring(zf.read(candidate_path))
            candidate_name = table_root.attrib.get("displayName") or table_root.attrib.get("name") or ""
            if candidate_name == table_name:
                table_xml_path = candidate_path
                break
        if table_xml_path is None:
            return None

        table_root = ET.fromstring(zf.read(table_xml_path))
        table_ref = table_root.attrib.get("ref", "")
        if not table_ref:
            return None
        start_col, start_row, _end_col, end_row = range_boundaries(table_ref)
        if end_row < start_row + 1:
            return None

        table_columns = table_root.find(f"{{{MAIN_NS}}}tableColumns")
        if table_columns is None:
            return None
        sku_index = None
        for idx, table_col in enumerate(table_columns.findall(f"{{{MAIN_NS}}}tableColumn"), start=1):
            if _normalize_header(table_col.attrib.get("name", "")) == "skukey":
                sku_index = idx
                break
        if sku_index is None:
            return None
        sku_col_letters = get_column_letter(start_col + sku_index - 1)
        return sheet_xml_path, sku_col_letters, start_row + 1, end_row


def normalize_sales_sheet_sku_key_array_formula_refs(
    workbook_path: Path,
    *,
    sheet_name: str = CRM_SALES_SHEET_NAME,
    table_name: str = CRM_SALES_TABLE_NAME,
) -> int:
    workbook_path = Path(workbook_path)
    contract = _resolve_sales_sheet_package_contract(
        workbook_path,
        sheet_name=sheet_name,
        table_name=table_name,
    )
    if contract is None:
        return 0

    sheet_path, sku_col_letters, data_start_row, data_end_row = contract
    try:
        with zipfile.ZipFile(workbook_path, "r") as zin:
            sheet_xml_bytes = zin.read(sheet_path)
    except KeyError:
        return 0

    try:
        sheet_root = ET.fromstring(sheet_xml_bytes)
    except ET.XMLSyntaxError:
        return 0

    target_col = sku_col_letters.upper()
    normalized = 0
    for cell in sheet_root.findall(f".//{{{MAIN_NS}}}c"):
        cell_ref = cell.attrib.get("r", "")
        match = re.match(r"^([A-Z]+)(\d+)$", cell_ref)
        if not match:
            continue
        col_letters, row_num = match.group(1), int(match.group(2))
        if col_letters != target_col or row_num < data_start_row or row_num > data_end_row:
            continue
        formula = cell.find(f"{{{MAIN_NS}}}f")
        if formula is None or formula.attrib.get("t") != "array":
            continue
        current_ref = str(formula.attrib.get("ref", "") or "").strip()
        if current_ref == cell_ref:
            continue
        formula.attrib["ref"] = cell_ref
        normalized += 1
    if normalized <= 0:
        return 0
    updated_sheet_xml = ET.tostring(sheet_root, encoding="UTF-8", xml_declaration=True)

    tmp_path = workbook_path.with_name(f".{workbook_path.name}.arrayref_fix")
    with zipfile.ZipFile(workbook_path, "r") as zin:
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename == sheet_path:
                    zout.writestr(item, updated_sheet_xml)
                else:
                    zout.writestr(item, zin.read(item.filename))
    shutil.move(str(tmp_path), str(workbook_path))
    return normalized


def prune_stale_calcchain_refs(workbook_path: Path) -> int:
    workbook_path = Path(workbook_path)
    try:
        with zipfile.ZipFile(workbook_path, "r") as zin:
            names = set(zin.namelist())
            if (
                "xl/calcChain.xml" not in names
                or "xl/workbook.xml" not in names
                or "xl/_rels/workbook.xml.rels" not in names
            ):
                return 0

            wb_root = ET.fromstring(zin.read("xl/workbook.xml"))
            rel_map = _load_rels_map(zin, "xl/_rels/workbook.xml.rels")
            formula_cells_by_sheet_id: Dict[str, set[str]] = {}
            for sheet in wb_root.findall(f".//{{{MAIN_NS}}}sheet"):
                sheet_id = str(sheet.attrib.get("sheetId", "") or "").strip()
                if not sheet_id:
                    continue
                rid = sheet.attrib.get(f"{{{REL_NS}}}id", "")
                target = rel_map.get(rid)
                if not target:
                    continue
                sheet_path = _norm_target("xl/workbook.xml", target)
                if sheet_path not in names:
                    continue
                ws_root = ET.fromstring(zin.read(sheet_path))
                formula_cells_by_sheet_id[sheet_id] = {
                    cell.attrib.get("r", "")
                    for cell in ws_root.findall(f".//{{{MAIN_NS}}}c")
                    if cell.find(f"{{{MAIN_NS}}}f") is not None
                }

            calc_chain_root = ET.fromstring(zin.read("xl/calcChain.xml"))
    except (KeyError, ET.XMLSyntaxError, zipfile.BadZipFile):
        return 0

    removed = 0
    current_sheet_id: str | None = None
    for node in list(calc_chain_root.findall(f".//{{{MAIN_NS}}}c")):
        sheet_id = str(node.attrib.get("i", "") or "").strip()
        if sheet_id:
            current_sheet_id = sheet_id
        ref = str(node.attrib.get("r", "") or "").strip()
        if not current_sheet_id or not ref:
            continue
        formula_refs = formula_cells_by_sheet_id.get(current_sheet_id)
        if formula_refs is None:
            continue
        if ref not in formula_refs:
            calc_chain_root.remove(node)
            removed += 1
    if removed <= 0:
        return 0

    updated_calcchain = ET.tostring(calc_chain_root, encoding="UTF-8", xml_declaration=True)
    tmp_path = workbook_path.with_name(f".{workbook_path.name}.calcchain_fix")
    with zipfile.ZipFile(workbook_path, "r") as zin:
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename == "xl/calcChain.xml":
                    zout.writestr(item, updated_calcchain)
                else:
                    zout.writestr(item, zin.read(item.filename))
    shutil.move(str(tmp_path), str(workbook_path))
    return removed


def _parse_xml(path: Path) -> ET._ElementTree:
    parser = ET.XMLParser(remove_blank_text=False)
    return ET.parse(str(path), parser)


def _write_xml(tree: ET._ElementTree, path: Path) -> None:
    tree.write(str(path), encoding="UTF-8", xml_declaration=True, standalone=True)


def _backup_file(target: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = backup_dir / f"CRM_backup_repair_{ts}.xlsx"
    shutil.copy2(target, out)
    return out


def repair_workbook_package(src_path: Path, out_path: Path) -> Dict[str, int]:
    stats = {
        "external_links_removed": 0,
        "workbook_rel_external_removed": 0,
        "content_types_external_removed": 0,
        "broken_defined_names_removed": 0,
        "sku_key_array_refs_normalized": 0,
        "stale_calcchain_refs_removed": 0,
    }

    with TemporaryDirectory() as td:
        td_path = Path(td)
        with zipfile.ZipFile(src_path, "r") as zf:
            zf.extractall(td_path)

        wb_xml = td_path / "xl" / "workbook.xml"
        wb_tree = _parse_xml(wb_xml)
        wb_root = wb_tree.getroot()

        # remove broken defined names
        dns = wb_root.find(f"{{{MAIN_NS}}}definedNames")
        if dns is not None:
            remove_nodes = []
            for dn in list(dns):
                text = (dn.text or "").strip()
                if "#REF!" in text:
                    remove_nodes.append(dn)
            for dn in remove_nodes:
                dns.remove(dn)
            stats["broken_defined_names_removed"] = len(remove_nodes)

        # remove external references node
        ext_refs = wb_root.find(f"{{{MAIN_NS}}}externalReferences")
        if ext_refs is not None:
            wb_root.remove(ext_refs)

        _write_xml(wb_tree, wb_xml)

        # remove externalLink relationships from workbook rels
        rels_xml = td_path / "xl" / "_rels" / "workbook.xml.rels"
        if rels_xml.exists():
            rels_tree = _parse_xml(rels_xml)
            rels_root = rels_tree.getroot()
            remove_rels = []
            for rel in list(rels_root):
                rel_type = rel.attrib.get("Type", "")
                if rel_type.endswith("/externalLink"):
                    remove_rels.append(rel)
            for rel in remove_rels:
                rels_root.remove(rel)
            stats["workbook_rel_external_removed"] = len(remove_rels)
            _write_xml(rels_tree, rels_xml)

        # remove externalLink parts
        ext_dir = td_path / "xl" / "externalLinks"
        if ext_dir.exists():
            removed = 0
            for f in ext_dir.rglob("*"):
                if f.is_file():
                    f.unlink()
                    removed += 1
            for d in sorted([p for p in ext_dir.rglob("*") if p.is_dir()], reverse=True):
                d.rmdir()
            ext_dir.rmdir()
            stats["external_links_removed"] = removed

        # remove externalLink content-types entries
        ct_xml = td_path / "[Content_Types].xml"
        if ct_xml.exists():
            ct_tree = _parse_xml(ct_xml)
            ct_root = ct_tree.getroot()
            remove_nodes = []
            for node in list(ct_root):
                part_name = node.attrib.get("PartName", "")
                content_type = node.attrib.get("ContentType", "")
                if "/xl/externalLinks/" in part_name or "externalLink" in content_type:
                    remove_nodes.append(node)
            for node in remove_nodes:
                ct_root.remove(node)
            stats["content_types_external_removed"] = len(remove_nodes)
            _write_xml(ct_tree, ct_xml)

        with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path in td_path.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, file_path.relative_to(td_path).as_posix())

    stats["sku_key_array_refs_normalized"] = normalize_sales_sheet_sku_key_array_formula_refs(out_path)
    stats["stale_calcchain_refs_removed"] = prune_stale_calcchain_refs(out_path)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair CRM workbook package metadata safely")
    parser.add_argument("--workbook", type=Path, default=Path("excel_ui/SALES_KSP_CRM_V3.xlsx"))
    parser.add_argument("--output", type=Path, default=None, help="Optional output workbook path")
    parser.add_argument("--backup-dir", type=Path, default=Path("excel_ui/backups"))
    parser.add_argument("--apply", action="store_true", help="Write repaired file to source workbook path")
    args = parser.parse_args()

    src = args.workbook
    if not src.exists():
        raise FileNotFoundError(f"Workbook not found: {src}")

    if args.apply:
        backup = _backup_file(src, args.backup_dir)
        out = src
        # write to temporary path first
        tmp = src.with_name(f"{src.stem}.repaired.tmp.xlsx")
        stats = repair_workbook_package(src, tmp)
        shutil.move(str(tmp), str(src))
        print("Workbook repair APPLY")
        print(f"  workbook: {src}")
        print(f"  backup: {backup}")
    else:
        out = args.output or src.with_name(f"{src.stem}_REPAIRED.xlsx")
        stats = repair_workbook_package(src, out)
        print("Workbook repair DRY RUN")
        print(f"  input: {src}")
        print(f"  output: {out}")

    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
