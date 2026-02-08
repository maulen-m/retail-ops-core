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
import posixpath
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple
import xml.etree.ElementTree as ET


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
A1_RANGE_RE = re.compile(r"^([A-Z]+)(\d+):([A-Z]+)(\d+)$")


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


def validate_workbook_integrity(workbook_path: Path) -> IntegrityResult:
    errors: List[str] = []
    warnings: List[str] = []

    with zipfile.ZipFile(workbook_path, "r") as zf:
        names = set(zf.namelist())

        wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
        wb_rel_map = _load_rels_map(zf, "xl/_rels/workbook.xml.rels")

        ext_refs = wb_root.find(f"{{{MAIN_NS}}}externalReferences")
        if ext_refs is not None:
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

        dns = wb_root.find(f"{{{MAIN_NS}}}definedNames")
        if dns is not None:
            for dn in dns.findall(f"{{{MAIN_NS}}}definedName"):
                if "#REF!" in (dn.text or ""):
                    name = dn.attrib.get("name", "<unnamed>")
                    errors.append(f"named range contains #REF!: {name}")

        table_files = [n for n in names if n.startswith("xl/tables/table") and n.endswith(".xml")]
        for table_file in sorted(table_files):
            root = ET.fromstring(zf.read(table_file))
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
            count_nodes = len(cols.findall(f"{{{MAIN_NS}}}tableColumn"))
            if not (width == count_attr == count_nodes):
                errors.append(
                    "table column mismatch: "
                    f"{table_file} width={width} count_attr={count_attr} count_nodes={count_nodes}"
                )

        ws_files = [n for n in names if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
        for ws_file in ws_files:
            rels_file = ws_file.replace("xl/worksheets/", "xl/worksheets/_rels/") + ".rels"
            rel_map: Dict[str, str] = {}
            if rels_file in names:
                rel_map = _load_rels_map(zf, rels_file)

            ws_root = ET.fromstring(zf.read(ws_file))
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate CRM workbook package integrity")
    parser.add_argument(
        "--workbook",
        type=Path,
        default=Path("excel_ui/SALES_KSP_CRM_V3.xlsx"),
        help="Workbook path",
    )
    args = parser.parse_args()

    result = validate_workbook_integrity(args.workbook)
    print(f"Workbook: {args.workbook}")
    print(f"Errors: {len(result.errors)}")
    print(f"Warnings: {len(result.warnings)}")
    for msg in result.errors:
        print(f"ERROR: {msg}")
    for msg in result.warnings:
        print(f"WARN: {msg}")

    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
