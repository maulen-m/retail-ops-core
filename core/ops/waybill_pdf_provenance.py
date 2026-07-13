"""Fail-closed provenance for Kaspi waybill PDFs used by pinned closeouts."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from core.ops.waybill_shipping_obligations import normalize_store_code


SCHEMA_VERSION = 1
SOURCE = "kaspi_api_exact_order_detail"
PROVENANCE_SUFFIX = ".provenance.json"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def waybill_url_sha256(url: str) -> str:
    """Hash the current URL without persisting its potentially sensitive value."""
    return _sha256_bytes(_clean(url).encode("utf-8"))


def provenance_path(pdf_path: Path) -> Path:
    pdf_path = Path(pdf_path)
    return pdf_path.with_name(pdf_path.name + PROVENANCE_SUFFIX)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(dict(payload), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temp_path.replace(path)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def write_waybill_pdf_provenance(
    *,
    pdf_path: Path,
    store_code: str,
    order_id: str,
    waybill_url: str,
    api_resource_id: str = "",
    required_orders_sha256: str,
    request_identity: Mapping[str, Any],
) -> Path:
    """Bind current PDF bytes to an exact Kaspi order and READY request."""
    pdf_path = Path(pdf_path)
    normalized_store = normalize_store_code(store_code)
    normalized_order = _clean(order_id)
    required_hash = _clean(required_orders_sha256).lower()
    request = dict(request_identity or {})
    if not normalized_store or not normalized_order:
        raise ValueError("waybill provenance requires store_code and order_id")
    if pdf_path.name != f"{normalized_order}.pdf":
        raise ValueError("pinned waybill provenance requires exact numeric order filename")
    if len(required_hash) != 64 or any(ch not in "0123456789abcdef" for ch in required_hash):
        raise ValueError("waybill provenance requires a valid required-orders SHA-256")
    if _clean(request.get("target_date")) == "" or _clean(request.get("ready_set_at")) == "":
        raise ValueError("waybill provenance requires target_date and ready_set_at")
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)
    stat = pdf_path.stat()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "source": SOURCE,
        "store_code": normalized_store,
        "order_id": normalized_order,
        "api_resource_id": _clean(api_resource_id),
        "pdf_filename": pdf_path.name,
        "file_size": int(stat.st_size),
        "pdf_sha256": file_sha256(pdf_path),
        "waybill_url_sha256": waybill_url_sha256(waybill_url),
        "required_orders_sha256": required_hash,
        "request_identity": request,
        "verified_at": datetime.now().astimezone().isoformat(),
    }
    output_path = provenance_path(pdf_path)
    _atomic_write_json(output_path, payload)
    return output_path


def validate_waybill_pdf_provenance(
    *,
    pdf_path: Path,
    expected_store_code: str,
    expected_order_id: str,
    expected_required_orders_sha256: str,
    expected_request_identity: Mapping[str, Any],
    expected_waybill_url: str | None = None,
    require_request_binding: bool = True,
) -> tuple[bool, str, dict[str, Any]]:
    """Validate the exact PDF, order, store, URL (when known), and request binding."""
    pdf_path = Path(pdf_path)
    sidecar_path = provenance_path(pdf_path)
    if not pdf_path.is_file():
        return False, "pdf_missing", {}
    if pdf_path.name != f"{_clean(expected_order_id)}.pdf":
        return False, "pdf_filename_mismatch", {}
    if not sidecar_path.is_file():
        return False, "provenance_missing", {}
    try:
        payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, f"provenance_unreadable:{exc}", {}
    if not isinstance(payload, dict):
        return False, "provenance_not_object", {}
    checks = {
        "schema_version": int(payload.get("schema_version") or 0) == SCHEMA_VERSION,
        "source": _clean(payload.get("source")) == SOURCE,
        "store_code": normalize_store_code(payload.get("store_code"))
        == normalize_store_code(expected_store_code),
        "order_id": _clean(payload.get("order_id")) == _clean(expected_order_id),
        "pdf_filename": _clean(payload.get("pdf_filename")) == pdf_path.name,
    }
    if require_request_binding:
        checks["required_orders_sha256"] = (
            _clean(payload.get("required_orders_sha256")).lower()
            == _clean(expected_required_orders_sha256).lower()
        )
        checks["request_identity"] = (
            dict(payload.get("request_identity") or {})
            == dict(expected_request_identity or {})
        )
    for field, ok in checks.items():
        if not ok:
            return False, f"provenance_{field}_mismatch", payload
    try:
        with pdf_path.open("rb") as handle:
            head = handle.read(16)
            handle.seek(max(0, pdf_path.stat().st_size - 2048))
            tail = handle.read()
        if not head.lstrip().startswith(b"%PDF") or b"%%EOF" not in tail:
            return False, "provenance_pdf_incomplete", payload
        stat = pdf_path.stat()
        if int(payload.get("file_size") or -1) != int(stat.st_size):
            return False, "provenance_file_size_mismatch", payload
        if _clean(payload.get("pdf_sha256")).lower() != file_sha256(pdf_path):
            return False, "provenance_pdf_sha256_mismatch", payload
    except OSError as exc:
        return False, f"provenance_pdf_read_failed:{exc}", payload
    if expected_waybill_url is not None:
        if _clean(payload.get("waybill_url_sha256")).lower() != waybill_url_sha256(
            expected_waybill_url
        ):
            return False, "provenance_waybill_url_sha256_mismatch", payload
    return True, "", payload
