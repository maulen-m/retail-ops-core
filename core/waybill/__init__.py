"""
Waybill processing module for Kaspi order fulfillment.

Phase 9.5 - Kaspi Order Automation
"""
from .pdf_grouper import (
    WaybillGroup,
    extract_waybills_from_zip,
    group_orders_for_shipment,
    merge_pdfs,
    sanitize_filename,
)
from .waybill_downloader import (
    WaybillDownloader,
    DownloadResult,
    BatchDownloadResult,
)

__all__ = [
    "WaybillGroup",
    "extract_waybills_from_zip",
    "group_orders_for_shipment",
    "merge_pdfs",
    "sanitize_filename",
    "WaybillDownloader",
    "DownloadResult",
    "BatchDownloadResult",
]
