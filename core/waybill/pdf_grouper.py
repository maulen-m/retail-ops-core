"""
Waybill PDF grouper for Kaspi order fulfillment.

Phase 9.5 TASK-115: Group waybill PDFs by store/product/size for efficient shipping.

Groups orders into three categories:
- NORMAL: Single item, single quantity
- MULTI_LINE: Same order has multiple SKUs
- MULTI_QTY: Same product ordered multiple times (merge across orders)

Usage:
    from core.waybill.pdf_grouper import extract_waybills_from_zip, group_orders_for_shipment

    waybill_map = extract_waybills_from_zip(Path("waybills.zip"), temp_dir)
    groups, missing = group_orders_for_shipment(orders, waybill_map)
"""

import logging
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _replace_file_atomically(source_path: Path, output_path: Path) -> Path:
    """Move a prepared temp file into place after recreating the parent path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.replace(output_path)
    return output_path


@dataclass
class WaybillGroup:
    """Represents a group of waybills to be merged/processed together."""
    group_type: str  # NORMAL, MULTI_LINE, MULTI_QTY
    store_code: str
    kaspi_name_core: str  # Core product name (without size)
    my_size: str
    total_quantity: int
    order_ids: list[str] = field(default_factory=list)
    pdf_paths: list[Path] = field(default_factory=list)
    output_filename: str = ""

    def __post_init__(self):
        """Generate output filename if not set."""
        if not self.output_filename:
            self.output_filename = self._generate_filename()

    def _generate_filename(self) -> str:
        """Generate output filename based on group type."""
        store = sanitize_filename(self.store_code)
        name = sanitize_filename(self.kaspi_name_core)
        size = sanitize_filename(self.my_size) if self.my_size else "NOSIZE"

        if self.group_type == "MULTI_QTY":
            return f"{name}___qnt{self.total_quantity}.pdf"
        elif self.group_type == "MULTI_LINE":
            order_id = self.order_ids[0] if self.order_ids else "UNKNOWN"
            n_items = len(self.order_ids)
            return f"{store}___ORDER{order_id}_{n_items}items.pdf"
        else:  # NORMAL
            return f"{store}___{size}___{name}.pdf"


def sanitize_filename(name: str) -> str:
    r"""
    Remove/replace characters that break file systems.

    Replaces: / \\ : * ? " < > |
    Also handles Cyrillic and other Unicode by replacing with underscores.
    """
    if not name:
        return "UNKNOWN"

    # Replace problematic characters
    invalid_chars = r'[/\\:*?"<>|\s]'
    result = re.sub(invalid_chars, '_', str(name))

    # Remove multiple consecutive underscores
    result = re.sub(r'_+', '_', result)

    # Remove leading/trailing underscores
    result = result.strip('_')

    # Truncate very long names
    if len(result) > 100:
        result = result[:100]

    return result if result else "UNKNOWN"


def extract_waybills_from_zip(
    zip_path: Path,
    temp_dir: Path,
    pattern: str = r'KASPI_SHOP-(\d+)\.pdf'
) -> dict[str, Path]:
    """
    Extract waybill PDFs from Kaspi ZIP.

    Args:
        zip_path: Path to ZIP file containing waybills
        temp_dir: Directory to extract files to
        pattern: Regex pattern to extract order_id from filename

    Returns:
        Dict mapping order_id -> PDF path
    """
    if not zip_path.exists():
        raise FileNotFoundError(f"ZIP file not found: {zip_path}")

    waybill_map = {}
    temp_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, 'r') as zf:
        for filename in zf.namelist():
            # Skip directories and non-PDF files
            if filename.endswith('/') or not filename.lower().endswith('.pdf'):
                continue

            # Extract order_id from filename
            basename = Path(filename).name
            match = re.search(pattern, basename)

            if match:
                order_id = match.group(1)
                # Extract the file
                extracted_path = temp_dir / basename
                with zf.open(filename) as src, open(extracted_path, 'wb') as dst:
                    dst.write(src.read())
                waybill_map[order_id] = extracted_path
                logger.debug(f"Extracted waybill: {order_id} -> {extracted_path}")
            else:
                logger.warning(f"Could not extract order_id from: {filename}")

    logger.info(f"Extracted {len(waybill_map)} waybills from {zip_path.name}")
    return waybill_map


def extract_waybills_from_dir(
    dir_path: Path,
    pattern: str = r'KASPI_SHOP-(\d+)\.pdf'
) -> dict[str, Path]:
    """
    Build waybill map from directory of PDF files.

    Args:
        dir_path: Directory containing waybill PDFs
        pattern: Regex pattern to extract order_id from filename

    Returns:
        Dict mapping order_id -> PDF path
    """
    if not dir_path.exists():
        raise FileNotFoundError(f"Directory not found: {dir_path}")

    waybill_map = {}

    for pdf_file in dir_path.glob('*.pdf'):
        match = re.search(pattern, pdf_file.name)
        if match:
            order_id = match.group(1)
            waybill_map[order_id] = pdf_file

    logger.info(f"Found {len(waybill_map)} waybills in {dir_path}")
    return waybill_map


def group_orders_for_shipment(
    orders: list[dict],
    waybill_map: dict[str, Path]
) -> tuple[list[WaybillGroup], list[str]]:
    """
    Group orders into waybill bundles.

    Logic:
        - MULTI_QTY: Same kaspi_name_core, quantity > 1 (merge across orders)
        - MULTI_LINE: Same order_id appears on multiple lines (multi-SKU order)
        - NORMAL: Single item, single quantity

    Args:
        orders: List of order dicts (from kaspi_export_parser)
        waybill_map: Dict mapping order_id -> PDF path

    Returns:
        Tuple of (groups, missing_order_ids)
    """
    groups = []
    missing_order_ids = []

    # Index orders by order_id to detect multi-line
    orders_by_id = {}
    for order in orders:
        oid = order.get('order_id')
        if oid:
            orders_by_id.setdefault(oid, []).append(order)

    # Detect multi-line order IDs (same order_id, multiple SKUs)
    multi_line_ids = {
        oid for oid, items in orders_by_id.items()
        if len(items) > 1
    }

    # Track which orders have been grouped
    grouped_orders = set()

    # First pass: Handle MULTI_QTY (quantity > 1)
    # Group by (kaspi_name_core) across all orders
    qty_groups = {}
    for order in orders:
        qty = order.get('quantity', 1)
        if qty > 1:
            name_core = _extract_name_core(order.get('kaspi_offer_name', ''))
            key = (name_core, order.get('store_code', ''))
            qty_groups.setdefault(key, []).append(order)

    for (name_core, store_code), group_orders in qty_groups.items():
        total_qty = sum(o.get('quantity', 1) for o in group_orders)
        order_ids = [o.get('order_id') for o in group_orders]

        # Get waybill PDFs
        pdf_paths = []
        for oid in order_ids:
            if oid in waybill_map:
                pdf_paths.append(waybill_map[oid])
            else:
                missing_order_ids.append(oid)

        if pdf_paths:
            group = WaybillGroup(
                group_type="MULTI_QTY",
                store_code=store_code,
                kaspi_name_core=name_core,
                my_size="",  # Size varies in MULTI_QTY
                total_quantity=total_qty,
                order_ids=order_ids,
                pdf_paths=pdf_paths,
            )
            groups.append(group)
            grouped_orders.update(order_ids)

    # Second pass: Handle MULTI_LINE (same order_id, multiple SKUs)
    for oid in multi_line_ids:
        if oid in grouped_orders:
            continue

        items = orders_by_id[oid]
        if not items:
            continue

        # Get store from first item
        store_code = items[0].get('store_code', '')

        # Get waybill PDF (one per order, regardless of line count)
        pdf_paths = []
        if oid in waybill_map:
            pdf_paths.append(waybill_map[oid])
        else:
            missing_order_ids.append(oid)

        if pdf_paths:
            # Extract first item's name for reference
            name_core = _extract_name_core(items[0].get('kaspi_offer_name', ''))

            group = WaybillGroup(
                group_type="MULTI_LINE",
                store_code=store_code,
                kaspi_name_core=name_core,
                my_size="MULTI",
                total_quantity=len(items),
                order_ids=[oid],
                pdf_paths=pdf_paths,
            )
            groups.append(group)
            grouped_orders.add(oid)

    # Third pass: Handle NORMAL (single item, quantity=1)
    for order in orders:
        oid = order.get('order_id')
        if not oid or oid in grouped_orders:
            continue

        qty = order.get('quantity', 1)
        if qty != 1:
            continue  # Should have been handled in MULTI_QTY

        store_code = order.get('store_code', '')
        name_core = _extract_name_core(order.get('kaspi_offer_name', ''))
        my_size = order.get('my_size', '')

        # Get waybill PDF
        pdf_paths = []
        if oid in waybill_map:
            pdf_paths.append(waybill_map[oid])
        else:
            missing_order_ids.append(oid)

        if pdf_paths:
            group = WaybillGroup(
                group_type="NORMAL",
                store_code=store_code,
                kaspi_name_core=name_core,
                my_size=my_size,
                total_quantity=1,
                order_ids=[oid],
                pdf_paths=pdf_paths,
            )
            groups.append(group)
            grouped_orders.add(oid)

    # Deduplicate missing order IDs
    missing_order_ids = list(set(missing_order_ids))

    logger.info(
        f"Grouped {len(grouped_orders)} orders into {len(groups)} bundles "
        f"({len(missing_order_ids)} missing waybills)"
    )

    return groups, missing_order_ids


def _extract_name_core(kaspi_name: str) -> str:
    """
    Extract core product name (without size).

    Examples:
        "Комплект мужской Line52 черный XL" -> "Line52_BLACK"
        "Рашгард Print5в1 черный 2XL" -> "Print5v1_BLACK"
    """
    if not kaspi_name:
        return "UNKNOWN"

    name = str(kaspi_name).upper()

    # Extract model name
    model_patterns = [
        r'\bPRINT\s*5[ВB]?1\b',  # LINE52, Print5в1
        r'\bLINE\s*\d+\b',
        r'\bCOMBO\s*\d+\b',
        r'\bBASIC\s*\d+\b',
        r'\bELITE\s*\d+\b',
    ]

    model = None
    for pattern in model_patterns:
        match = re.search(pattern, name, re.IGNORECASE)
        if match:
            model = re.sub(r'\s+', '', match.group(0))
            break

    if not model:
        # Fallback: use first 20 chars
        model = sanitize_filename(kaspi_name[:20])

    # Extract color
    colors = {
        'ЧЕРНЫЙ': 'BLACK', 'ЧЁРНЫЙ': 'BLACK',
        'БЕЛЫЙ': 'WHITE',
        'СЕРЫЙ': 'GREY',
        'ХАКИ': 'KHAKI',
        'NAVY': 'NAVY',
        'BLACK': 'BLACK',
        'WHITE': 'WHITE',
    }

    color = None
    for rus, eng in colors.items():
        if rus in name:
            color = eng
            break

    if color:
        return f"{model}_{color}"
    return model


def merge_pdfs(pdf_paths: list[Path], output_path: Path) -> Path:
    """
    Merge multiple PDFs into a single file.

    Uses PyPDF2 for merging.

    Args:
        pdf_paths: List of PDF paths to merge
        output_path: Output PDF path

    Returns:
        Path to merged PDF
    """
    try:
        from pypdf import PdfMerger
    except ImportError:
        try:
            from PyPDF2 import PdfMerger
        except ImportError:
            raise ImportError(
                "pypdf (preferred) or PyPDF2 is required for PDF merging. "
                "Install with: python3 -m pip install pypdf"
            )

    if not pdf_paths:
        raise ValueError("No PDF paths provided for merging")

    if len(pdf_paths) == 1:
        # Just copy the single file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_output_path: Path | None = None
        with tempfile.NamedTemporaryFile(
            dir=output_path.parent,
            prefix=".waybill-copy-",
            suffix=output_path.suffix,
            delete=False,
        ) as tmp_file:
            temp_output_path = Path(tmp_file.name)
        try:
            shutil.copy2(pdf_paths[0], temp_output_path)
            return _replace_file_atomically(temp_output_path, output_path)
        finally:
            if temp_output_path is not None:
                temp_output_path.unlink(missing_ok=True)

    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    merger = PdfMerger()

    for pdf_path in pdf_paths:
        if pdf_path.exists():
            merger.append(str(pdf_path))
        else:
            logger.warning(f"PDF not found, skipping: {pdf_path}")

    temp_output_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output_path.parent,
            prefix=".waybill-merge-",
            suffix=output_path.suffix,
            delete=False,
        ) as tmp_file:
            temp_output_path = Path(tmp_file.name)
            merger.write(tmp_file)

        _replace_file_atomically(temp_output_path, output_path)
    finally:
        merger.close()
        if temp_output_path is not None:
            temp_output_path.unlink(missing_ok=True)

    logger.debug(f"Merged {len(pdf_paths)} PDFs -> {output_path}")
    return output_path


def build_grouped_output(
    groups: list[WaybillGroup],
    output_dir: Path,
    merge_multi: bool = True
) -> dict:
    """
    Build grouped output directory structure.

    Args:
        groups: List of WaybillGroup objects
        output_dir: Base output directory
        merge_multi: If True, merge multi-qty/multi-line PDFs

    Returns:
        Dict with stats: normal, multi_line, multi_qty, errors
    """
    stats = {'normal': 0, 'multi_line': 0, 'multi_qty': 0, 'errors': 0}

    # Create subdirectories
    normal_dir = output_dir / "NORMAL_singles"
    multi_line_dir = output_dir / "SPECIAL_multi_line"
    multi_qty_dir = output_dir / "SPECIAL_multi_qty"

    normal_dir.mkdir(parents=True, exist_ok=True)
    multi_line_dir.mkdir(parents=True, exist_ok=True)
    multi_qty_dir.mkdir(parents=True, exist_ok=True)

    # Track used filenames to handle collisions
    used_filenames = set()

    for group in groups:
        try:
            # Determine output directory
            if group.group_type == "MULTI_QTY":
                out_dir = multi_qty_dir
                stat_key = 'multi_qty'
            elif group.group_type == "MULTI_LINE":
                out_dir = multi_line_dir
                stat_key = 'multi_line'
            else:
                out_dir = normal_dir
                stat_key = 'normal'

            # Handle filename collisions
            filename = group.output_filename
            if filename in used_filenames:
                # Add order_id to make unique
                base, ext = filename.rsplit('.', 1)
                oid = group.order_ids[0] if group.order_ids else 'dup'
                filename = f"{base}_{oid}.{ext}"

            used_filenames.add(filename)
            output_path = out_dir / filename

            # Copy or merge PDFs
            if len(group.pdf_paths) > 1 and merge_multi:
                merge_pdfs(group.pdf_paths, output_path)
            elif group.pdf_paths:
                shutil.copy2(group.pdf_paths[0], output_path)

            stats[stat_key] += 1

        except Exception as e:
            logger.error(f"Error processing group {group.order_ids}: {e}")
            stats['errors'] += 1

    return stats


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python pdf_grouper.py <zip_file>")
        print("\nTests waybill extraction from ZIP.")
        sys.exit(0)

    zip_path = Path(sys.argv[1])

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        print(f"Extracting from: {zip_path}")
        waybill_map = extract_waybills_from_zip(zip_path, temp_path)

        print(f"\nExtracted {len(waybill_map)} waybills:")
        for oid, path in list(waybill_map.items())[:5]:
            print(f"  {oid}: {path.name}")

        if len(waybill_map) > 5:
            print(f"  ... and {len(waybill_map) - 5} more")
