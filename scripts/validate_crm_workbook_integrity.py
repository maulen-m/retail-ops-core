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
A1_RANGE_RE = re.compile(r"^([A-Z]+)(\d+):([A-Z]+)(\d+)$")
EMPTY_SHARED_STRINGS_XML = (
    "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
    "<sst xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" "
    "count=\"0\" uniqueCount=\"0\"/>"
).encode("utf-8")


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

    with zipfile.ZipFile(workbook_path, "r") as zf:
        names = set(zf.namelist())

        wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
        wb_rel_map = _load_rels_map(zf, "xl/_rels/workbook.xml.rels")

        for rid, target in _shared_strings_targets(zf):
            if target not in names:
                errors.append(f"workbook sharedStrings target missing: rid={rid} target={target}")

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
