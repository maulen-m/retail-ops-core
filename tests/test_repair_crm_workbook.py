from __future__ import annotations

import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
import xml.etree.ElementTree as ET

from openpyxl import Workbook, load_workbook

from scripts.repair_crm_workbook import repair_workbook_package


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"


def _inject_bad_metadata(xlsx_path: Path) -> None:
    with TemporaryDirectory() as td:
        td_path = Path(td)
        with zipfile.ZipFile(xlsx_path, "r") as zf:
            zf.extractall(td_path)

        wb_xml = td_path / "xl" / "workbook.xml"
        wb_root = ET.fromstring(wb_xml.read_bytes())

        ext_refs = ET.SubElement(wb_root, f"{{{MAIN_NS}}}externalReferences")
        ext_ref = ET.SubElement(ext_refs, f"{{{MAIN_NS}}}externalReference")
        ext_ref.set(f"{{{REL_NS}}}id", "rIdExt1")

        dns = wb_root.find(f"{{{MAIN_NS}}}definedNames")
        if dns is None:
            dns = ET.SubElement(wb_root, f"{{{MAIN_NS}}}definedNames")
        dn = ET.SubElement(dns, f"{{{MAIN_NS}}}definedName", {"name": "BROKEN_NAME"})
        dn.text = "[1]ExternalBook.xlsx!#REF!"
        wb_xml.write_bytes(ET.tostring(wb_root, encoding="utf-8", xml_declaration=True))

        rels_xml = td_path / "xl" / "_rels" / "workbook.xml.rels"
        rels_root = ET.fromstring(rels_xml.read_bytes())
        ET.SubElement(
            rels_root,
            f"{{{PKG_REL_NS}}}Relationship",
            {
                "Id": "rIdExt1",
                "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/externalLink",
                "Target": "/xl/externalLinks/externalLink1.xml",
            },
        )
        rels_xml.write_bytes(ET.tostring(rels_root, encoding="utf-8", xml_declaration=True))

        ext_dir = td_path / "xl" / "externalLinks"
        ext_rels_dir = ext_dir / "_rels"
        ext_dir.mkdir(parents=True, exist_ok=True)
        ext_rels_dir.mkdir(parents=True, exist_ok=True)
        (ext_dir / "externalLink1.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<externalLink xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>',
            encoding="utf-8",
        )
        (ext_rels_dir / "externalLink1.xml.rels").write_text(
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>',
            encoding="utf-8",
        )

        ct_xml = td_path / "[Content_Types].xml"
        ct_root = ET.fromstring(ct_xml.read_bytes())
        ET.SubElement(
            ct_root,
            f"{{{CT_NS}}}Override",
            {
                "PartName": "/xl/externalLinks/externalLink1.xml",
                "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.externalLink+xml",
            },
        )
        ct_xml.write_bytes(ET.tostring(ct_root, encoding="utf-8", xml_declaration=True))

        with zipfile.ZipFile(xlsx_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path in td_path.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, file_path.relative_to(td_path).as_posix())


def test_repair_workbook_package_removes_external_links_and_broken_names():
    with TemporaryDirectory() as td:
        td_path = Path(td)
        src = td_path / "sample.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        ws["A1"] = "ok"
        wb.save(src)
        wb.close()

        _inject_bad_metadata(src)
        out = td_path / "sample_repaired.xlsx"
        stats = repair_workbook_package(src, out)
        assert stats["external_links_removed"] >= 1
        assert stats["broken_defined_names_removed"] >= 1

        with zipfile.ZipFile(out, "r") as zf:
            names = set(zf.namelist())
            assert "xl/externalLinks/externalLink1.xml" not in names
            wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
            assert wb_root.find(f".//{{{MAIN_NS}}}externalReferences") is None
            for dn in wb_root.findall(f".//{{{MAIN_NS}}}definedName"):
                assert "#REF!" not in (dn.text or "")

        wb2 = load_workbook(out, read_only=True)
        assert "Sheet1" in wb2.sheetnames
        wb2.close()
