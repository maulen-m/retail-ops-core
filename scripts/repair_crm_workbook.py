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
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict
import xml.etree.ElementTree as ET


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"


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
    }

    with TemporaryDirectory() as td:
        td_path = Path(td)
        with zipfile.ZipFile(src_path, "r") as zf:
            zf.extractall(td_path)

        wb_xml = td_path / "xl" / "workbook.xml"
        wb_root = ET.fromstring(wb_xml.read_bytes())

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

        wb_xml.write_bytes(ET.tostring(wb_root, encoding="utf-8", xml_declaration=True))

        # remove externalLink relationships from workbook rels
        rels_xml = td_path / "xl" / "_rels" / "workbook.xml.rels"
        if rels_xml.exists():
            rels_root = ET.fromstring(rels_xml.read_bytes())
            remove_rels = []
            for rel in list(rels_root):
                rel_type = rel.attrib.get("Type", "")
                if rel_type.endswith("/externalLink"):
                    remove_rels.append(rel)
            for rel in remove_rels:
                rels_root.remove(rel)
            stats["workbook_rel_external_removed"] = len(remove_rels)
            rels_xml.write_bytes(ET.tostring(rels_root, encoding="utf-8", xml_declaration=True))

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
            ct_root = ET.fromstring(ct_xml.read_bytes())
            remove_nodes = []
            for node in list(ct_root):
                part_name = node.attrib.get("PartName", "")
                content_type = node.attrib.get("ContentType", "")
                if "/xl/externalLinks/" in part_name or "externalLink" in content_type:
                    remove_nodes.append(node)
            for node in remove_nodes:
                ct_root.remove(node)
            stats["content_types_external_removed"] = len(remove_nodes)
            ct_xml.write_bytes(ET.tostring(ct_root, encoding="utf-8", xml_declaration=True))

        with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path in td_path.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, file_path.relative_to(td_path).as_posix())

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
