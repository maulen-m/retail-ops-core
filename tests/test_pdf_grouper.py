"""
Unit tests for pdf_grouper.py (Phase 9.5)

TASK-118: Tests for waybill PDF grouping.
"""
import pytest
import sys
import tempfile
import types
import zipfile
from pathlib import Path

from core.waybill.pdf_grouper import (
    WaybillGroup,
    sanitize_filename,
    extract_waybills_from_zip,
    extract_waybills_from_dir,
    group_orders_for_shipment,
    _extract_name_core,
)


class TestSanitizeFilename:
    """Tests for filename sanitization."""

    def test_basic_sanitization(self):
        """Test basic character replacement."""
        assert sanitize_filename("hello/world") == "hello_world"
        assert sanitize_filename("file:name") == "file_name"
        # Trailing underscores are stripped
        assert sanitize_filename("file*name?") == "file_name"

    def test_spaces(self):
        """Test space replacement."""
        assert sanitize_filename("hello world") == "hello_world"
        assert sanitize_filename("  multiple   spaces  ") == "multiple_spaces"

    def test_multiple_underscores(self):
        """Test multiple underscore consolidation."""
        assert sanitize_filename("a___b") == "a_b"
        assert sanitize_filename("a / b : c") == "a_b_c"

    def test_empty_string(self):
        """Test empty string handling."""
        assert sanitize_filename("") == "UNKNOWN"
        assert sanitize_filename(None) == "UNKNOWN"

    def test_long_filename(self):
        """Test truncation of long names."""
        long_name = "a" * 200
        result = sanitize_filename(long_name)
        assert len(result) <= 100

    def test_cyrillic(self):
        """Test Cyrillic characters (should be preserved)."""
        # Note: Cyrillic chars are kept, only problematic chars removed
        result = sanitize_filename("Комплект Line52")
        assert "Line52" in result


class TestExtractNameCore:
    """Tests for product name core extraction."""

    def test_line52_extraction(self):
        """Test LINE52 model extraction."""
        result = _extract_name_core("Комплект Line52 черный XL")
        assert "LINE52" in result or "PRINT" in result

    def test_color_extraction(self):
        """Test color extraction."""
        result = _extract_name_core("Комплект Line52 черный XL")
        assert "BLACK" in result

    def test_line51_extraction(self):
        """Test LINE51 model extraction."""
        result = _extract_name_core("Рашгард Line51 белый M")
        assert "LINE" in result or "WHITE" in result

    def test_unknown_product(self):
        """Test unknown product name handling."""
        result = _extract_name_core("Unknown Product Name")
        assert result is not None
        assert len(result) > 0


class TestWaybillGroup:
    """Tests for WaybillGroup dataclass."""

    def test_normal_filename_generation(self):
        """Test filename generation for NORMAL type."""
        group = WaybillGroup(
            group_type="NORMAL",
            store_code="PP1",
            kaspi_name_core="LINE52_BLACK",
            my_size="XL",
            total_quantity=1,
            order_ids=["123456"],
            pdf_paths=[],
        )
        assert "PP1" in group.output_filename
        assert "XL" in group.output_filename
        assert "LINE52" in group.output_filename
        assert group.output_filename.endswith(".pdf")

    def test_multi_qty_filename_generation(self):
        """Test filename generation for MULTI_QTY type."""
        group = WaybillGroup(
            group_type="MULTI_QTY",
            store_code="PP1",
            kaspi_name_core="LINE52_BLACK",
            my_size="",
            total_quantity=5,
            order_ids=["123", "456", "789"],
            pdf_paths=[],
        )
        assert "qnt5" in group.output_filename
        assert group.output_filename.endswith(".pdf")

    def test_multi_line_filename_generation(self):
        """Test filename generation for MULTI_LINE type."""
        group = WaybillGroup(
            group_type="MULTI_LINE",
            store_code="PP1",
            kaspi_name_core="LINE52_BLACK",
            my_size="MULTI",
            total_quantity=2,
            order_ids=["123456"],
            pdf_paths=[],
        )
        assert "ORDER123456" in group.output_filename
        assert "items" in group.output_filename
        assert group.output_filename.endswith(".pdf")


class TestExtractWaybillsFromZip:
    """Tests for ZIP extraction."""

    @pytest.fixture
    def sample_zip(self, tmp_path):
        """Create a sample ZIP file with waybill PDFs."""
        zip_path = tmp_path / "waybills.zip"

        with zipfile.ZipFile(zip_path, 'w') as zf:
            # Create dummy PDF content (just text for testing)
            zf.writestr("KASPI_SHOP-123456789.pdf", b"%PDF-1.4\nDummy PDF content")
            zf.writestr("KASPI_SHOP-987654321.pdf", b"%PDF-1.4\nDummy PDF content")
            zf.writestr("other_file.txt", b"Not a waybill")

        return zip_path

    def test_extract_waybills(self, sample_zip, tmp_path):
        """Test waybill extraction from ZIP."""
        extract_dir = tmp_path / "extracted"
        waybill_map = extract_waybills_from_zip(sample_zip, extract_dir)

        assert len(waybill_map) == 2
        assert "123456789" in waybill_map
        assert "987654321" in waybill_map

    def test_extract_paths_exist(self, sample_zip, tmp_path):
        """Test that extracted files actually exist."""
        extract_dir = tmp_path / "extracted"
        waybill_map = extract_waybills_from_zip(sample_zip, extract_dir)

        for order_id, path in waybill_map.items():
            assert path.exists()
            assert path.suffix == ".pdf"

    def test_missing_zip(self, tmp_path):
        """Test error on missing ZIP file."""
        with pytest.raises(FileNotFoundError):
            extract_waybills_from_zip(
                tmp_path / "nonexistent.zip",
                tmp_path / "extract"
            )

    def test_empty_zip(self, tmp_path):
        """Test handling of ZIP with no waybills."""
        zip_path = tmp_path / "empty.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("readme.txt", b"No waybills here")

        extract_dir = tmp_path / "extracted"
        waybill_map = extract_waybills_from_zip(zip_path, extract_dir)

        assert len(waybill_map) == 0


class TestExtractWaybillsFromDir:
    """Tests for directory extraction."""

    @pytest.fixture
    def sample_dir(self, tmp_path):
        """Create a sample directory with waybill PDFs."""
        waybills_dir = tmp_path / "waybills"
        waybills_dir.mkdir()

        (waybills_dir / "KASPI_SHOP-111111111.pdf").write_bytes(b"%PDF-1.4\nTest")
        (waybills_dir / "KASPI_SHOP-222222222.pdf").write_bytes(b"%PDF-1.4\nTest")
        (waybills_dir / "other.pdf").write_bytes(b"%PDF-1.4\nNot a waybill")

        return waybills_dir

    def test_extract_from_dir(self, sample_dir):
        """Test waybill loading from directory."""
        waybill_map = extract_waybills_from_dir(sample_dir)

        assert len(waybill_map) == 2
        assert "111111111" in waybill_map
        assert "222222222" in waybill_map

    def test_missing_dir(self, tmp_path):
        """Test error on missing directory."""
        with pytest.raises(FileNotFoundError):
            extract_waybills_from_dir(tmp_path / "nonexistent")


class TestGroupOrdersForShipment:
    """Tests for order grouping logic."""

    @pytest.fixture
    def sample_waybill_map(self, tmp_path):
        """Create sample waybill paths."""
        waybills = {}
        for oid in ["111", "222", "333", "444", "555"]:
            path = tmp_path / f"KASPI_SHOP-{oid}.pdf"
            path.write_bytes(b"%PDF-1.4\nTest")
            waybills[oid] = path
        return waybills

    def test_normal_grouping(self, sample_waybill_map):
        """Test NORMAL grouping (single item, qty=1)."""
        orders = [
            {
                "order_id": "111",
                "store_code": "PP1",
                "kaspi_offer_name": "Line52 черный XL",
                "my_size": "XL",
                "quantity": 1,
            }
        ]

        groups, missing = group_orders_for_shipment(orders, sample_waybill_map)

        assert len(groups) == 1
        assert groups[0].group_type == "NORMAL"
        assert len(missing) == 0

    def test_multi_qty_grouping(self, sample_waybill_map):
        """Test MULTI_QTY grouping (quantity > 1)."""
        orders = [
            {
                "order_id": "111",
                "store_code": "PP1",
                "kaspi_offer_name": "Line52 черный XL",
                "my_size": "XL",
                "quantity": 3,
            }
        ]

        groups, missing = group_orders_for_shipment(orders, sample_waybill_map)

        assert len(groups) == 1
        assert groups[0].group_type == "MULTI_QTY"
        assert groups[0].total_quantity == 3

    def test_multi_line_grouping(self, sample_waybill_map):
        """Test MULTI_LINE grouping (same order_id, different SKUs)."""
        orders = [
            {
                "order_id": "111",  # Same order
                "store_code": "PP1",
                "kaspi_offer_name": "Line52 черный XL",
                "my_size": "XL",
                "quantity": 1,
            },
            {
                "order_id": "111",  # Same order
                "store_code": "PP1",
                "kaspi_offer_name": "Line51 белый M",
                "my_size": "M",
                "quantity": 1,
            }
        ]

        groups, missing = group_orders_for_shipment(orders, sample_waybill_map)

        # Should have one MULTI_LINE group
        multi_line = [g for g in groups if g.group_type == "MULTI_LINE"]
        assert len(multi_line) == 1
        assert multi_line[0].total_quantity == 2

    def test_missing_waybills(self, sample_waybill_map):
        """Test handling of missing waybills."""
        orders = [
            {
                "order_id": "999",  # Not in waybill_map
                "store_code": "PP1",
                "kaspi_offer_name": "Line52 черный XL",
                "my_size": "XL",
                "quantity": 1,
            }
        ]

        groups, missing = group_orders_for_shipment(orders, sample_waybill_map)

        assert len(missing) == 1
        assert "999" in missing

    def test_mixed_grouping(self, sample_waybill_map):
        """Test mixed grouping types."""
        orders = [
            # NORMAL
            {
                "order_id": "111",
                "store_code": "PP1",
                "kaspi_offer_name": "Line52 черный XL",
                "my_size": "XL",
                "quantity": 1,
            },
            # MULTI_QTY
            {
                "order_id": "222",
                "store_code": "PP1",
                "kaspi_offer_name": "Line51 белый M",
                "my_size": "M",
                "quantity": 2,
            },
            # MULTI_LINE (part 1)
            {
                "order_id": "333",
                "store_code": "PP2",
                "kaspi_offer_name": "Line52 черный L",
                "my_size": "L",
                "quantity": 1,
            },
            # MULTI_LINE (part 2)
            {
                "order_id": "333",
                "store_code": "PP2",
                "kaspi_offer_name": "Line51 белый S",
                "my_size": "S",
                "quantity": 1,
            },
        ]

        groups, missing = group_orders_for_shipment(orders, sample_waybill_map)

        types = {g.group_type for g in groups}
        assert "NORMAL" in types
        assert "MULTI_QTY" in types
        assert "MULTI_LINE" in types


class TestMergePdfs:
    """Tests for PDF merging functionality."""

    @pytest.fixture
    def sample_pdfs(self, tmp_path):
        """Create sample PDF files for merging."""
        # Create minimal valid PDFs
        pdfs = []
        for i in range(3):
            path = tmp_path / f"test_{i}.pdf"
            # Minimal PDF structure
            content = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [] /Count 0 >> endobj
xref
0 3
0000000000 65535 f
0000000009 00000 n
0000000052 00000 n
trailer << /Size 3 /Root 1 0 R >>
startxref
106
%%EOF"""
            path.write_bytes(content)
            pdfs.append(path)
        return pdfs

    def test_single_pdf_copy(self, sample_pdfs, tmp_path):
        """Test that single PDF is just copied."""
        pytest.importorskip("PyPDF2")
        from core.waybill.pdf_grouper import merge_pdfs

        output = tmp_path / "output.pdf"
        result = merge_pdfs([sample_pdfs[0]], output)

        assert result == output
        assert output.exists()

    def test_single_pdf_copy_creates_nested_output_dir(self, sample_pdfs, tmp_path):
        """Test that single PDF copy recreates nested output dirs safely."""
        pytest.importorskip("PyPDF2")
        from core.waybill.pdf_grouper import merge_pdfs

        output = tmp_path / "nested" / "NORMAL_singles" / "output.pdf"
        result = merge_pdfs([sample_pdfs[0]], output)

        assert result == output
        assert output.exists()

    def test_multiple_pdf_merge(self, sample_pdfs, tmp_path):
        """Test merging multiple PDFs."""
        pytest.importorskip("PyPDF2")
        from core.waybill.pdf_grouper import merge_pdfs

        output = tmp_path / "merged.pdf"
        result = merge_pdfs(sample_pdfs, output)

        assert result == output
        assert output.exists()
        # Merged file should be larger than individual files
        assert output.stat().st_size > 0

    def test_multiple_pdf_merge_writes_to_open_file_handle(self, sample_pdfs, tmp_path, monkeypatch):
        """Test merge writes through an open file handle, not a raw path string."""
        from core.waybill.pdf_grouper import merge_pdfs

        class FakePdfMerger:
            def __init__(self):
                self.appended = []
                self.closed = False

            def append(self, pdf_path):
                self.appended.append(pdf_path)

            def write(self, fileobj):
                assert hasattr(fileobj, "write")
                assert not isinstance(fileobj, (str, Path))
                fileobj.write(b"%PDF-1.4\nfake-merge\n")

            def close(self):
                self.closed = True

        fake_module = types.SimpleNamespace(PdfMerger=FakePdfMerger)
        monkeypatch.setitem(sys.modules, "pypdf", fake_module)

        output = tmp_path / "merged.pdf"
        result = merge_pdfs(sample_pdfs, output)

        assert result == output
        assert output.exists()
        assert output.read_bytes().startswith(b"%PDF-1.4")

    def test_empty_list_error(self, tmp_path):
        """Test error on empty PDF list."""
        pytest.importorskip("PyPDF2")
        from core.waybill.pdf_grouper import merge_pdfs

        output = tmp_path / "output.pdf"
        with pytest.raises(ValueError):
            merge_pdfs([], output)

    def test_missing_pdf_warning(self, sample_pdfs, tmp_path):
        """Test warning on missing PDF (but continues with available)."""
        pytest.importorskip("PyPDF2")
        from core.waybill.pdf_grouper import merge_pdfs

        paths = sample_pdfs + [tmp_path / "nonexistent.pdf"]
        output = tmp_path / "output.pdf"

        # Should not raise, just warn
        result = merge_pdfs(paths, output)
        assert result == output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
