#!/usr/bin/env python3
"""
Validate CRM workbook package integrity without modifying workbook content.

Checks:
- Workbook externalReference r:id targets exist.
- Worksheet tableParts r:id targets exist.
- Table refs and tableColumns counts are structurally consistent.
- Named ranges containing #REF! are treated as integrity errors.
"""
from __future__ import annotations

import argparse
import shutil
import posixpath
import re
import sys
import zipfile
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
import xml.etree.ElementTree as ET


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
SHARED_STRINGS_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings"
SHARED_STRINGS_CT = "application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"
KASPI_NAME_CORE_CF_SENTINEL = '$M2="CL_OC_MEN_LINE52_BLACK"'
CRM_SALES_TABLE_NAME = "tb_SalesRaw"
A1_RANGE_RE = re.compile(r"^([A-Z]+)(\d+):([A-Z]+)(\d+)$")
CELL_REF_RE = re.compile(r"^([A-Z]+)(\d+)$")
EMPTY_SHARED_STRINGS_XML = (
    "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
    "<sst xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" "
    "count=\"0\" uniqueCount=\"0\"/>"
).encode("utf-8")
IGNORABLE_ATTR_RE = re.compile(r'\b(?:[A-Za-z0-9_]+:)?Ignorable="([^"]+)"')
XMLNS_PREFIX_RE = re.compile(r'\bxmlns:([A-Za-z0-9_]+)=')


@dataclass
class IntegrityResult:
    errors: List[str]
    warnings: List[str]


def _col_to_num(col: str) -> int:
    out = 0
    for ch in col:
        out = out * 26 + (ord(ch) - 64)
    return out


def _load_rels_map(zf: zipfile.ZipFile, rels_path: str) -> Dict[str, str]:
    rels_xml = zf.read(rels_path)
    root = ET.fromstring(rels_xml)
    rels = root.findall(f"{{{PKG_REL_NS}}}Relationship")
    return {r.attrib.get("Id", ""): r.attrib.get("Target", "") for r in rels}


def _norm_target(base_path: str, target: str) -> str:
    base = posixpath.dirname(base_path)
    normalized = posixpath.normpath(posixpath.join(base, target))
    return normalized.lstrip("/")


def _normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _external_link_missing_relationship_ids(
    zf: zipfile.ZipFile,
    names: set[str],
    safe_read,
    external_link_path: str,
) -> List[str]:
    xml_bytes = safe_read(zf, external_link_path)
    if xml_bytes is None:
        return []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        return [f"xml parse error: {external_link_path} ({exc})"]

    rels_path = external_link_path.replace("xl/externalLinks/", "xl/externalLinks/_rels/") + ".rels"
    if rels_path not in names:
        return [f"externalLink relationships part missing: {external_link_path}"]

    rels_xml = safe_read(zf, rels_path)
    if rels_xml is None:
        return [f"externalLink relationships part missing: {external_link_path}"]
    try:
        rels_root = ET.fromstring(rels_xml)
    except ET.ParseError as exc:
        return [f"xml parse error: {rels_path} ({exc})"]

    rel_ids = {
        rel.attrib.get("Id", "")
        for rel in rels_root.findall(f"{{{PKG_REL_NS}}}Relationship")
        if rel.attrib.get("Id")
    }
    referenced_ids = {
        attr_value
        for node in root.iter()
        for attr_name, attr_value in node.attrib.items()
        if attr_name == f"{{{REL_NS}}}id" and attr_value
    }
    missing_ids = sorted(referenced_ids - rel_ids)
    if not missing_ids:
        return []
    return [
        f"externalLink relationship ids missing: {external_link_path} missing={','.join(missing_ids)}"
    ]


def _find_undeclared_ignorable_prefixes(xml_bytes: bytes) -> list[str]:
    try:
        head = xml_bytes.decode("utf-8", "ignore")
    except Exception:
        return []
    root_start = head.find("<")
    if root_start == -1:
        return []
    root_end = head.find(">", root_start)
    if root_end == -1:
        return []
    root_tag = head[root_start : root_end + 1]
    match = IGNORABLE_ATTR_RE.search(root_tag)
    if not match:
        return []
    ignorable = [token for token in match.group(1).split() if token]
    declared = set(XMLNS_PREFIX_RE.findall(root_tag))
    return [token for token in ignorable if token not in declared]


def _sheet_formula_cells_by_sheet_id(
    zf: zipfile.ZipFile,
    names: set[str],
    safe_read,
    wb_root: ET.Element,
    wb_rel_map: Dict[str, str],
) -> Dict[str, set[str]]:
    formula_cells: Dict[str, set[str]] = {}
    for sheet in wb_root.findall(f".//{{{MAIN_NS}}}sheet"):
        sheet_id = str(sheet.attrib.get("sheetId", "") or "").strip()
        if not sheet_id:
            continue
        rid = sheet.attrib.get(f"{{{REL_NS}}}id", "")
        target = wb_rel_map.get(rid)
        if not target:
            continue
        package_target = _norm_target("xl/workbook.xml", target)
        if package_target not in names:
            continue
        ws_xml = safe_read(zf, package_target)
        if ws_xml is None:
            continue
        try:
            ws_root = ET.fromstring(ws_xml)
        except ET.ParseError:
            continue
        formula_cells[sheet_id] = {
            cell.attrib.get("r", "")
            for cell in ws_root.findall(f".//{{{MAIN_NS}}}c")
            if cell.find(f"{{{MAIN_NS}}}f") is not None
        }
    return formula_cells


def _table_to_worksheet_map(
    zf: zipfile.ZipFile,
    names: set[str],
    safe_read,
) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    ws_files = [n for n in names if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
    for ws_file in ws_files:
        rels_file = ws_file.replace("xl/worksheets/", "xl/worksheets/_rels/") + ".rels"
        rel_map: Dict[str, str] = {}
        if rels_file in names:
            rels_xml = safe_read(zf, rels_file)
            if rels_xml is not None:
                try:
                    rels_root = ET.fromstring(rels_xml)
                    rel_map = {
                        r.attrib.get("Id", ""): r.attrib.get("Target", "")
                        for r in rels_root.findall(f"{{{PKG_REL_NS}}}Relationship")
                    }
                except ET.ParseError:
                    rel_map = {}

        ws_xml = safe_read(zf, ws_file)
        if ws_xml is None:
            continue
        try:
            ws_root = ET.fromstring(ws_xml)
        except ET.ParseError:
            continue
        table_parts = ws_root.find(f"{{{MAIN_NS}}}tableParts")
        if table_parts is None:
            continue
        for part in table_parts.findall(f"{{{MAIN_NS}}}tablePart"):
            rid = part.attrib.get(f"{{{REL_NS}}}id", "")
            target = rel_map.get(rid)
            if not target:
                continue
            mapping[_norm_target(ws_file, target)] = ws_file
    return mapping


def _count_array_formula_cells_in_column(
    worksheet_xml: bytes,
    *,
    column_letters: str,
    data_start_row: int,
    data_end_row: int,
) -> int:
    try:
        root = ET.fromstring(worksheet_xml)
    except ET.ParseError:
        return 0

    target_col = column_letters.upper()
    count = 0
    for cell in root.findall(f".//{{{MAIN_NS}}}c"):
        cell_ref = cell.attrib.get("r", "")
        match = CELL_REF_RE.match(cell_ref)
        if not match:
            continue
        col_letters, row_num = match.group(1), int(match.group(2))
        if col_letters != target_col or row_num < data_start_row or row_num > data_end_row:
            continue
        formula = cell.find(f"{{{MAIN_NS}}}f")
        if formula is not None and formula.attrib.get("t") == "array":
            count += 1
    return count


def _array_formula_ref_mismatches_in_column(
    worksheet_xml: bytes,
    *,
    column_letters: str,
    data_start_row: int,
    data_end_row: int,
) -> List[Tuple[str, str]]:
    try:
        root = ET.fromstring(worksheet_xml)
    except ET.ParseError:
        return []

    target_col = column_letters.upper()
    mismatches: List[Tuple[str, str]] = []
    for cell in root.findall(f".//{{{MAIN_NS}}}c"):
        cell_ref = cell.attrib.get("r", "")
        match = CELL_REF_RE.match(cell_ref)
        if not match:
            continue
        col_letters, row_num = match.group(1), int(match.group(2))
        if col_letters != target_col or row_num < data_start_row or row_num > data_end_row:
            continue
        formula = cell.find(f"{{{MAIN_NS}}}f")
        if formula is None or formula.attrib.get("t") != "array":
            continue
        formula_ref = str(formula.attrib.get("ref", "") or "").strip()
        if formula_ref != cell_ref:
            mismatches.append((cell_ref, formula_ref))
    return mismatches


def _self_externalized_formulas_in_table_window(
    worksheet_xml: bytes,
    *,
    start_col_num: int,
    end_col_num: int,
    data_start_row: int,
    data_end_row: int,
) -> List[Tuple[str, str]]:
    try:
        root = ET.fromstring(worksheet_xml)
    except ET.ParseError:
        return []

    pattern = re.compile(r"\[[0-9]+\]!")
    hits: List[Tuple[str, str]] = []
    for cell in root.findall(f".//{{{MAIN_NS}}}c"):
        cell_ref = cell.attrib.get("r", "")
        match = CELL_REF_RE.match(cell_ref)
        if not match:
            continue
        col_num = _col_to_num(match.group(1))
        row_num = int(match.group(2))
        if col_num < start_col_num or col_num > end_col_num:
            continue
        if row_num < data_start_row or row_num > data_end_row:
            continue
        formula = cell.find(f"{{{MAIN_NS}}}f")
        if formula is None:
            continue
        formula_text = (formula.text or "").strip()
        if pattern.search(formula_text):
            hits.append((cell_ref, formula_text))
    return hits


def _shared_strings_targets(zf: zipfile.ZipFile) -> List[Tuple[str, str]]:
    rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    targets: List[Tuple[str, str]] = []
    for rel in rels_root.findall(f"{{{PKG_REL_NS}}}Relationship"):
        rel_type = rel.attrib.get("Type", "")
        if rel_type != SHARED_STRINGS_REL_TYPE:
            continue
        rid = rel.attrib.get("Id", "")
        target = rel.attrib.get("Target", "")
        if not target:
            continue
        targets.append((rid, _norm_target("xl/workbook.xml", target)))
    return targets


def repair_missing_shared_strings_part(
    workbook_path: Path,
    backup_dir: Path | None = None,
) -> Tuple[bool, Path | None]:
    """Add empty xl/sharedStrings.xml when workbook rels reference it but part is missing."""
    workbook_path = Path(workbook_path)
    with zipfile.ZipFile(workbook_path, "r") as zin:
        names = set(zin.namelist())
        targets = _shared_strings_targets(zin)
        if not targets:
            return False, None

        missing_targets = [target for _, target in targets if target not in names]
        if not missing_targets:
            return False, None

        shared_cells = 0
        for name in names:
            if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"):
                shared_cells += zin.read(name).count(b't="s"')
        if shared_cells > 0:
            raise RuntimeError(
                "Workbook references sharedStrings.xml but it is missing and worksheet cells still "
                "use shared-string indexes (t=\"s\"). Automatic repair is unsafe."
            )

        backup_path: Path | None = None
        if backup_dir is not None:
            backup_dir = Path(backup_dir)
            backup_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"{workbook_path.stem}_pre_sharedstrings_fix_{ts}{workbook_path.suffix}"
            shutil.copy2(workbook_path, backup_path)

        tmp_path = workbook_path.with_suffix(f"{workbook_path.suffix}.sharedstrings_fix")

        ct_root = ET.fromstring(zin.read("[Content_Types].xml"))
        existing_overrides = {
            node.attrib.get("PartName", "")
            for node in ct_root.findall(f"{{{CT_NS}}}Override")
        }
        for target in missing_targets:
            part_name = "/" + target
            if part_name not in existing_overrides:
                ET.SubElement(
                    ct_root,
                    f"{{{CT_NS}}}Override",
                    {
                        "PartName": part_name,
                        "ContentType": SHARED_STRINGS_CT,
                    },
                )
        ct_bytes = ET.tostring(ct_root, encoding="utf-8", xml_declaration=True)

        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename == "[Content_Types].xml":
                    zout.writestr(item, ct_bytes)
                else:
                    zout.writestr(item, zin.read(item.filename))
            for target in missing_targets:
                zout.writestr(target, EMPTY_SHARED_STRINGS_XML)

    shutil.move(str(tmp_path), str(workbook_path))
    return True, backup_path


def validate_workbook_integrity(workbook_path: Path) -> IntegrityResult:
    errors: List[str] = []
    warnings: List[str] = []
    part_cache: Dict[str, bytes | None] = {}

    def _safe_read(zf: zipfile.ZipFile, part_name: str) -> bytes | None:
        if part_name in part_cache:
            return part_cache[part_name]
        try:
            data = zf.read(part_name)
            part_cache[part_name] = data
            return data
        except KeyError:
            errors.append(f"package part missing: {part_name}")
        except Exception as exc:  # pragma: no cover - exercised via integration/corrupt files
            errors.append(f"zip entry unreadable: {part_name} ({exc})")
        part_cache[part_name] = None
        return None

    with zipfile.ZipFile(workbook_path, "r") as zf:
        names = set(zf.namelist())
        for part_name in sorted(name for name in names if name.startswith("xl/")):
            _safe_read(zf, part_name)
        table_to_sheet = _table_to_worksheet_map(zf, names, _safe_read)

        wb_xml = _safe_read(zf, "xl/workbook.xml")
        wb_rels_xml = _safe_read(zf, "xl/_rels/workbook.xml.rels")
        if wb_xml is None or wb_rels_xml is None:
            return IntegrityResult(errors=errors, warnings=warnings)

        missing_ignorable_prefixes = _find_undeclared_ignorable_prefixes(wb_xml)
        if missing_ignorable_prefixes:
            errors.append(
                "workbook mc:Ignorable references undeclared prefixes: "
                + ", ".join(missing_ignorable_prefixes)
            )

        try:
            wb_root = ET.fromstring(wb_xml)
        except ET.ParseError as exc:
            errors.append(f"xml parse error: xl/workbook.xml ({exc})")
            return IntegrityResult(errors=errors, warnings=warnings)

        try:
            rels_root = ET.fromstring(wb_rels_xml)
            wb_rel_rows = [
                (
                    r.attrib.get("Id", ""),
                    r.attrib.get("Target", ""),
                    r.attrib.get("Type", ""),
                    r.attrib.get("TargetMode", ""),
                )
                for r in rels_root.findall(f"{{{PKG_REL_NS}}}Relationship")
            ]
            wb_rel_map = {rid: target for rid, target, _rel_type, _target_mode in wb_rel_rows}
        except ET.ParseError as exc:
            errors.append(f"xml parse error: xl/_rels/workbook.xml.rels ({exc})")
            return IntegrityResult(errors=errors, warnings=warnings)

        formula_cells_by_sheet_id = _sheet_formula_cells_by_sheet_id(
            zf,
            names,
            _safe_read,
            wb_root,
            wb_rel_map,
        )

        for rid, target, rel_type, target_mode in wb_rel_rows:
            if not target or str(target_mode).lower() == "external":
                continue
            package_target = _norm_target("xl/workbook.xml", target)
            if package_target not in names:
                errors.append(
                    "workbook relationship target missing: "
                    f"rid={rid} target={package_target} type={rel_type}"
                )

        try:
            shared_targets = _shared_strings_targets(zf)
        except Exception as exc:
            errors.append(f"zip entry unreadable: xl/_rels/workbook.xml.rels ({exc})")
            shared_targets = []
        for rid, target in shared_targets:
            if target not in names:
                errors.append(f"workbook sharedStrings target missing: rid={rid} target={target}")

        ext_refs = wb_root.find(f"{{{MAIN_NS}}}externalReferences")
        if ext_refs is not None:
            checked_external_links: set[str] = set()
            for node in ext_refs.findall(f"{{{MAIN_NS}}}externalReference"):
                rid = node.attrib.get(f"{{{REL_NS}}}id", "")
                target = wb_rel_map.get(rid)
                if not target:
                    errors.append(f"workbook externalReference missing relationship: {rid}")
                    continue
                package_target = _norm_target("xl/workbook.xml", target)
                if package_target not in names:
                    errors.append(
                        f"workbook externalReference target missing: rid={rid} target={package_target}"
                    )
                    continue
                if package_target not in checked_external_links:
                    errors.extend(
                        _external_link_missing_relationship_ids(
                            zf,
                            names,
                            _safe_read,
                            package_target,
                        )
                    )
                    checked_external_links.add(package_target)

        if "xl/calcChain.xml" in names:
            calc_chain_xml = _safe_read(zf, "xl/calcChain.xml")
            if calc_chain_xml is not None:
                try:
                    calc_chain_root = ET.fromstring(calc_chain_xml)
                except ET.ParseError as exc:
                    errors.append(f"xml parse error: xl/calcChain.xml ({exc})")
                else:
                    current_sheet_id: str | None = None
                    stale_refs: List[str] = []
                    for node in calc_chain_root.findall(f".//{{{MAIN_NS}}}c"):
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
                            stale_refs.append(f"sheetId={current_sheet_id}:{ref}")
                    if stale_refs:
                        sample = ", ".join(stale_refs[:8])
                        errors.append(
                            "calcChain contains refs to non-formula cells: "
                            f"count={len(stale_refs)} sample={sample}"
                        )

        dns = wb_root.find(f"{{{MAIN_NS}}}definedNames")
        if dns is not None:
            for dn in dns.findall(f"{{{MAIN_NS}}}definedName"):
                if "#REF!" in (dn.text or ""):
                    name = dn.attrib.get("name", "<unnamed>")
                    errors.append(f"named range contains #REF!: {name}")

        table_files = [n for n in names if n.startswith("xl/tables/table") and n.endswith(".xml")]
        for table_file in sorted(table_files):
            table_xml = _safe_read(zf, table_file)
            if table_xml is None:
                continue
            try:
                root = ET.fromstring(table_xml)
            except ET.ParseError as exc:
                errors.append(f"xml parse error: {table_file} ({exc})")
                continue
            table_ref = root.attrib.get("ref", "")
            m = A1_RANGE_RE.match(table_ref)
            if not m:
                errors.append(f"table invalid ref: {table_file} ref={table_ref}")
                continue
            width = _col_to_num(m.group(3)) - _col_to_num(m.group(1)) + 1
            cols = root.find(f"{{{MAIN_NS}}}tableColumns")
            if cols is None:
                errors.append(f"table missing tableColumns: {table_file}")
                continue
            count_attr = int(cols.attrib.get("count", "0"))
            table_columns = cols.findall(f"{{{MAIN_NS}}}tableColumn")
            count_nodes = len(table_columns)
            if not (width == count_attr == count_nodes):
                errors.append(
                    "table column mismatch: "
                    f"{table_file} width={width} count_attr={count_attr} count_nodes={count_nodes}"
                )

            table_name = root.attrib.get("name") or root.attrib.get("displayName") or ""
            if _normalize_header(table_name) != _normalize_header(CRM_SALES_TABLE_NAME):
                continue

            sku_col_index = None
            has_kaspi_name_core_col = False
            for idx, column in enumerate(table_columns, start=1):
                if _normalize_header(column.attrib.get("name", "")) == "kaspinamecore":
                    has_kaspi_name_core_col = True
                if _normalize_header(column.attrib.get("name", "")) == "skukey":
                    sku_col_index = idx
                    calc_formula = column.find(f"{{{MAIN_NS}}}calculatedColumnFormula")
                    if calc_formula is None or calc_formula.attrib.get("array") not in {"1", "true", "True"}:
                        errors.append(
                            f"SKU_key calculatedColumnFormula must use array=1: {table_file}"
                        )
                    break

            if sku_col_index is not None:
                start_col_num = _col_to_num(m.group(1))
                sku_col_letters = ""
                col_num = start_col_num + sku_col_index - 1
                while col_num > 0:
                    col_num, rem = divmod(col_num - 1, 26)
                    sku_col_letters = chr(65 + rem) + sku_col_letters
                data_start_row = int(m.group(2)) + 1
                data_end_row = int(m.group(4))
                ws_file = table_to_sheet.get(table_file)
                if ws_file:
                    ws_xml = _safe_read(zf, ws_file)
                    if ws_xml is not None:
                        array_cells = _count_array_formula_cells_in_column(
                            ws_xml,
                            column_letters=sku_col_letters,
                            data_start_row=data_start_row,
                            data_end_row=data_end_row,
                        )
                        if array_cells <= 0 and data_end_row >= data_start_row:
                            errors.append(
                                f"SKU_key must preserve per-row array formulas: {table_file} count={array_cells}"
                            )
                        mismatches = _array_formula_ref_mismatches_in_column(
                            ws_xml,
                            column_letters=sku_col_letters,
                            data_start_row=data_start_row,
                            data_end_row=data_end_row,
                        )
                        if mismatches:
                            sample = ", ".join(f"{cell}->{ref or '<blank>'}" for cell, ref in mismatches[:5])
                            errors.append(
                                f"SKU_key array formula refs must match owning cell: {table_file} sample={sample}"
                            )
                        if has_kaspi_name_core_col and KASPI_NAME_CORE_CF_SENTINEL not in ws_xml.decode("utf-8", "ignore"):
                            errors.append(
                                f"Kaspi_name_core conditional-formatting sentinel missing: {table_file}"
                            )
                        self_externalized = _self_externalized_formulas_in_table_window(
                            ws_xml,
                            start_col_num=start_col_num,
                            end_col_num=_col_to_num(m.group(3)),
                            data_start_row=data_start_row,
                            data_end_row=data_end_row,
                        )
                        if self_externalized:
                            sample = ", ".join(
                                f"{cell}={formula[:80]}"
                                for cell, formula in self_externalized[:5]
                            )
                            errors.append(
                                "CRM sales sheet contains self-externalized formulas: "
                                f"{table_file} sample={sample}"
                            )

        ws_files = [n for n in names if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
        for ws_file in ws_files:
            rels_file = ws_file.replace("xl/worksheets/", "xl/worksheets/_rels/") + ".rels"
            rel_map: Dict[str, str] = {}
            if rels_file in names:
                rels_xml = _safe_read(zf, rels_file)
                if rels_xml is not None:
                    try:
                        rels_root = ET.fromstring(rels_xml)
                        rel_map = {
                            r.attrib.get("Id", ""): r.attrib.get("Target", "")
                            for r in rels_root.findall(f"{{{PKG_REL_NS}}}Relationship")
                        }
                    except ET.ParseError as exc:
                        errors.append(f"xml parse error: {rels_file} ({exc})")
                        rel_map = {}

            ws_xml = _safe_read(zf, ws_file)
            if ws_xml is None:
                continue
            try:
                ws_root = ET.fromstring(ws_xml)
            except ET.ParseError as exc:
                errors.append(f"xml parse error: {ws_file} ({exc})")
                continue
            table_parts = ws_root.find(f"{{{MAIN_NS}}}tableParts")
            if table_parts is None:
                continue
            for part in table_parts.findall(f"{{{MAIN_NS}}}tablePart"):
                rid = part.attrib.get(f"{{{REL_NS}}}id", "")
                target = rel_map.get(rid)
                if not target:
                    errors.append(f"{ws_file} tablePart missing relationship: {rid}")
                    continue
                package_target = _norm_target(ws_file, target)
                if package_target not in names:
                    errors.append(
                        f"{ws_file} tablePart target missing: rid={rid} target={package_target}"
                    )

    return IntegrityResult(errors=errors, warnings=warnings)


def filter_integrity_errors(
    errors: Iterable[str],
    allow_exact: Iterable[str] | None = None,
    allow_prefix: Iterable[str] | None = None,
) -> Tuple[List[str], List[str]]:
    allow_exact_set = {e for e in (allow_exact or []) if e}
    allow_prefix_list = [p for p in (allow_prefix or []) if p]
    blocking: List[str] = []
    allowed: List[str] = []
    for err in errors:
        if err in allow_exact_set or any(err.startswith(prefix) for prefix in allow_prefix_list):
            allowed.append(err)
        else:
            blocking.append(err)
    return blocking, allowed


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate CRM workbook package integrity")
    parser.add_argument(
        "--workbook",
        type=Path,
        default=Path("excel_ui/SALES_KSP_CRM_V3.xlsx"),
        help="Workbook path",
    )
    parser.add_argument(
        "--allow-error-exact",
        action="append",
        default=[],
        help="Treat matching integrity error text as allowed (does not fail exit code). Repeatable.",
    )
    parser.add_argument(
        "--allow-error-prefix",
        action="append",
        default=[],
        help="Treat integrity errors with this prefix as allowed. Repeatable.",
    )
    parser.add_argument(
        "--repair-missing-shared-strings",
        action="store_true",
        help="Safely add empty xl/sharedStrings.xml if workbook rels reference it but part is missing.",
    )
    parser.add_argument(
        "--repair-backup-dir",
        type=Path,
        default=Path("excel_ui/backups"),
        help="Backup directory used when --repair-missing-shared-strings is enabled.",
    )
    args = parser.parse_args()

    if args.repair_missing_shared_strings:
        repaired, backup_path = repair_missing_shared_strings_part(
            args.workbook,
            backup_dir=args.repair_backup_dir,
        )
        if repaired:
            print("REPAIR: added missing sharedStrings part")
            if backup_path:
                print(f"REPAIR_BACKUP: {backup_path}")

    result = validate_workbook_integrity(args.workbook)
    blocking_errors, allowed_errors = filter_integrity_errors(
        result.errors,
        allow_exact=args.allow_error_exact,
        allow_prefix=args.allow_error_prefix,
    )
    print(f"Workbook: {args.workbook}")
    print(f"Errors: {len(blocking_errors)}")
    print(f"Allowed errors: {len(allowed_errors)}")
    print(f"Warnings: {len(result.warnings)}")
    for msg in allowed_errors:
        print(f"ALLOW: {msg}")
    for msg in blocking_errors:
        print(f"ERROR: {msg}")
    for msg in result.warnings:
        print(f"WARN: {msg}")

    return 1 if blocking_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
