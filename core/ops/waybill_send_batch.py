from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional


SEND_BATCH_MANIFEST_FILE = "send_batch_manifest.json"
SEND_LEDGER_FILE = "send_ledger.json"
SEND_STOPLINE_FILE = "whatsapp_send_stopline.json"
LEDGER_STATES = {"pending", "opened", "clicked", "confirmed", "unsure", "failed"}
AUTONOMOUS_MANIFEST_SCHEMA_VERSION = 4


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _split_order_ids(raw_value: Any) -> List[str]:
    return [token.strip() for token in str(raw_value or "").split(";") if token.strip()]


def _normalize_items_detail(raw_value: Any) -> List[str]:
    return [token.strip() for token in str(raw_value or "").split(";") if token.strip()]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _looks_like_sha256(value: Any) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{64}", str(value or "").strip()))


def _batch_hash(entries: Iterable[dict[str, Any]]) -> str:
    normalized = [
        {
            "pdf_key": entry["pdf_key"],
            "order_ids": list(entry.get("order_ids") or []),
            "logical_group_type": entry.get("logical_group_type"),
            "sha256": entry.get("sha256"),
            "file_size": int(entry.get("file_size") or 0),
            "size_token": entry.get("size_token"),
            "size_rank": int(entry.get("size_rank") or 0),
            "product_family_key": entry.get("product_family_key"),
            "color_key": entry.get("color_key"),
            "product_color_key": entry.get("product_color_key"),
            "send_sequence": int(entry.get("send_sequence") or 0),
        }
        for entry in entries
    ]
    normalized.sort(key=lambda row: row["pdf_key"])
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _stable_manifest_entries(entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    stable_entries: list[dict[str, Any]] = []
    for entry in sorted(entries, key=lambda item: str(item.get("pdf_key") or "")):
        stable_entry = {
            "pdf_key": str(entry.get("pdf_key") or ""),
            "relative_output_path": str(entry.get("relative_output_path") or ""),
            "relative_to_today": str(entry.get("relative_to_today") or ""),
            "filename": str(entry.get("filename") or ""),
            "category": str(entry.get("category") or ""),
            "sha256": str(entry.get("sha256") or ""),
            "file_size": int(entry.get("file_size") or 0),
            "mtime": str(entry.get("mtime") or ""),
            "logical_group_type": str(entry.get("logical_group_type") or ""),
            "order_ids": [str(value) for value in entry.get("order_ids") or []],
            "order_counts_by_store": {
                str(store): int(count or 0)
                for store, count in sorted(
                    dict(entry.get("order_counts_by_store") or {}).items()
                )
            },
            "source_row_ids": [str(value) for value in entry.get("source_row_ids") or []],
            "source_lines": list(entry.get("source_lines") or []),
            "items_detail": [str(value) for value in entry.get("items_detail") or []],
            "product_family_key": str(entry.get("product_family_key") or ""),
            "color_key": str(entry.get("color_key") or ""),
            "product_color_key": str(entry.get("product_color_key") or ""),
            "size_token": str(entry.get("size_token") or ""),
            "size_rank": int(entry.get("size_rank") or 0),
            "send_sequence": int(entry.get("send_sequence") or 0),
            "core_resolution_sources": sorted(
                str(value) for value in entry.get("core_resolution_sources") or []
            ),
            "unsafe_core_resolution_sources": sorted(
                str(value) for value in entry.get("unsafe_core_resolution_sources") or []
            ),
            "requires_core_review": bool(entry.get("requires_core_review")),
        }
        stable_entries.append(stable_entry)
    return stable_entries


def manifest_batch_hash_payload(manifest: Mapping[str, Any]) -> Any:
    """Return the immutable send-authorizing payload for schema-v4 manifests."""
    entries = _stable_manifest_entries(manifest.get("entries") or [])
    schema_version = int(manifest.get("schema_version") or 0)
    if schema_version < AUTONOMOUS_MANIFEST_SCHEMA_VERSION:
        # Diagnostic compatibility only. Live autonomous preflight separately
        # rejects request-pinned manifests below schema v4.
        legacy_entries = []
        for entry in entries:
            legacy = {
                key: entry[key]
                for key in (
                    "pdf_key",
                    "relative_output_path",
                    "sha256",
                    "file_size",
                    "mtime",
                    "logical_group_type",
                    "order_ids",
                    "source_row_ids",
                    "product_family_key",
                    "color_key",
                    "product_color_key",
                    "size_token",
                    "size_rank",
                    "send_sequence",
                )
            }
            if entry["source_lines"]:
                legacy["source_lines"] = entry["source_lines"]
            legacy_entries.append(legacy)
        if any(
            key in manifest
            for key in ("request_identity", "expected_orders_sha256", "obligation_scope_hash")
        ):
            return {
                "entries": legacy_entries,
                "request_identity": dict(manifest.get("request_identity") or {}),
                "expected_orders_sha256": str(manifest.get("expected_orders_sha256") or ""),
                "obligation_scope_hash": str(manifest.get("obligation_scope_hash") or ""),
            }
        return legacy_entries

    raw_counts = dict(manifest.get("counts") or {})
    counts = {
        str(key): int(value or 0)
        for key, value in sorted(raw_counts.items())
    }
    return {
        "schema_version": schema_version,
        "entries": entries,
        "target_date": str(manifest.get("target_date") or ""),
        "ready_set_at": str(manifest.get("ready_set_at") or ""),
        "request_identity": dict(manifest.get("request_identity") or {}),
        "expected_orders_sha256": str(manifest.get("expected_orders_sha256") or ""),
        "obligation_scope_hash": str(manifest.get("obligation_scope_hash") or ""),
        "line_scope_hash": str(manifest.get("line_scope_hash") or ""),
        "terminal_orders_excluded": bool(manifest.get("terminal_orders_excluded")),
        "send_order_ids": sorted(str(value) for value in manifest.get("send_order_ids") or []),
        "overdue_order_ids": sorted(
            str(value) for value in manifest.get("overdue_order_ids") or []
        ),
        "missing_overdue_order_ids": sorted(
            str(value) for value in manifest.get("missing_overdue_order_ids") or []
        ),
        "counts": counts,
    }


def compute_manifest_batch_hash(manifest: Mapping[str, Any]) -> str:
    payload = manifest_batch_hash_payload(manifest)
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def build_pdf_key(*, sha256: str, order_ids: Iterable[str], logical_group_type: str) -> str:
    order_part = ",".join(sorted(str(order_id) for order_id in order_ids if str(order_id).strip()))
    raw = f"{logical_group_type}|{order_part}|{sha256}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _group_source_row_ids(groups: Optional[Iterable[Any]]) -> Dict[str, List[str]]:
    mapping: Dict[str, List[str]] = {}
    if not groups:
        return mapping

    for group in groups:
        output = str(getattr(group, "output_filename", "") or "").strip()
        if not output:
            continue
        row_ids: List[str] = []
        for item in list(getattr(group, "items", []) or []):
            source_row_id = str(getattr(item, "source_row_id", "") or "").strip()
            if source_row_id:
                row_ids.append(source_row_id)
        if row_ids:
            mapping[output] = row_ids
    return mapping


def _collect_overdue_ids_frostore_bs(
    groups: Optional[Iterable[Any]],
    target_date: Optional[date],
) -> List[str]:
    if not groups or target_date is None:
        return []
    overdue: set[str] = set()
    for group in groups:
        for item in list(getattr(group, "items", []) or []):
            order_id = str(getattr(item, "order_id", "") or "").strip()
            planned_date = getattr(item, "planned_date", None)
            if order_id and isinstance(planned_date, date) and planned_date < target_date:
                overdue.add(order_id)
    return sorted(overdue)


def _collect_overdue_ids_from_root(today_root: Path) -> List[str]:
    overdue_root = today_root / "MERGED" / "OVERDUE"
    overdue_ids: set[str] = set()
    for manifest_path in sorted(overdue_root.rglob("manifest_*.csv")):
        with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                overdue_ids.update(_split_order_ids(row.get("order_id")))
    return sorted(overdue_ids)


def build_send_batch_manifest_payload(
    *,
    batch_root: Path,
    today_root: Path,
    groups: Optional[Iterable[Any]] = None,
    target_date: Optional[date] = None,
) -> Dict[str, Any]:
    if not batch_root.exists():
        raise FileNotFoundError(f"Batch root not found: {batch_root}")

    source_row_ids_by_output = _group_source_row_ids(groups)
    overdue_order_ids = (
        _collect_overdue_ids_frostore_bs(groups, target_date)
        if groups is not None and target_date is not None
        else _collect_overdue_ids_from_root(today_root)
    )

    entries: List[Dict[str, Any]] = []
    order_ids_all: set[str] = set()
    send_order_ids: set[str] = set()

    for manifest_path in sorted(batch_root.glob("manifest_*.csv")):
        with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                continue
            for row_index, row in enumerate(reader, start=2):
                relative_output_path = str(row.get("output") or "").replace("\\", "/").lstrip("./")
                if not relative_output_path:
                    continue
                pdf_path = batch_root / relative_output_path
                if not pdf_path.exists():
                    raise FileNotFoundError(
                        f"Manifest output missing on disk: {manifest_path.name}:{row_index} -> {relative_output_path}"
                    )
                order_ids = _split_order_ids(row.get("order_id"))
                order_ids_all.update(order_ids)
                send_order_ids.update(order_ids)
                logical_group_type = str(row.get("type") or "").strip() or pdf_path.parent.name
                sha256 = _sha256_file(pdf_path)
                stat = pdf_path.stat()
                entry = {
                    "pdf_key": build_pdf_key(
                        sha256=sha256,
                        order_ids=order_ids,
                        logical_group_type=logical_group_type,
                    ),
                    "relative_output_path": relative_output_path,
                    "filename": pdf_path.name,
                    "category": pdf_path.parent.name,
                    "logical_group_type": logical_group_type,
                    "sha256": sha256,
                    "file_size": stat.st_size,
                    "mtime": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
                    "order_ids": order_ids,
                    "order_counts_by_store": {},
                    "source_manifest": manifest_path.name,
                    "source_row_index": row_index,
                    "source_row_ids": source_row_ids_by_output.get(relative_output_path, []),
                    "items_detail": _normalize_items_detail(row.get("items_detail")),
                }
                entries.append(entry)

    entries.sort(key=lambda entry: (entry["category"], entry["filename"].lower(), entry["pdf_key"]))
    missing_overdue = sorted(set(overdue_order_ids) - send_order_ids)
    payload = {
        "schema_version": 1,
        "created_at": _now_iso(),
        "target_date": target_date.isoformat() if isinstance(target_date, date) else None,
        "source_root": str(batch_root),
        "batch_label": batch_root.name,
        "counts": {
            "pdfs": len(entries),
            "orders": len(order_ids_all),
            "overdue_orders": len(overdue_order_ids),
        },
        "overdue_order_ids": overdue_order_ids,
        "missing_overdue_order_ids": missing_overdue,
        "terminal_orders_excluded": True,
        "entries": entries,
    }
    payload["batch_hash"] = _batch_hash(entries)
    return payload


def write_send_batch_manifest(
    *,
    batch_root: Path,
    today_root: Path,
    groups: Optional[Iterable[Any]] = None,
    target_date: Optional[date] = None,
) -> Path:
    payload = build_send_batch_manifest_payload(
        batch_root=batch_root,
        today_root=today_root,
        groups=groups,
        target_date=target_date,
    )
    manifest_path = batch_root / SEND_BATCH_MANIFEST_FILE
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def _default_ledger_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "state": "pending",
        "last_updated": None,
        "history": [],
        "filename": entry.get("filename"),
        "relative_output_path": entry.get("relative_output_path"),
        "order_ids": list(entry.get("order_ids") or []),
    }


def initialize_send_ledger(
    ledger_path: Path,
    manifest_payload: Dict[str, Any],
) -> Dict[str, Any]:
    manifest_schema_version = int(manifest_payload.get("schema_version") or 2)
    ledger = {
        "schema_version": manifest_schema_version,
        "batch_hash": manifest_payload.get("batch_hash"),
        "batch_label": manifest_payload.get("batch_label"),
        "manifest_path": str((ledger_path.parent / SEND_BATCH_MANIFEST_FILE).resolve()),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "entries": {
            entry["pdf_key"]: _default_ledger_entry(entry)
            for entry in manifest_payload.get("entries", [])
        },
    }
    save_send_ledger(ledger_path, ledger)
    return ledger


def load_send_ledger(
    ledger_path: Path,
    manifest_payload: Dict[str, Any],
) -> Dict[str, Any]:
    manifest_schema_version = int(manifest_payload.get("schema_version") or 2)
    if ledger_path.exists():
        payload = json.loads(ledger_path.read_text(encoding="utf-8"))
        if str(payload.get("batch_hash") or "") not in {
            "",
            str(manifest_payload.get("batch_hash") or ""),
        }:
            raise RuntimeError(
                "Existing send ledger batch hash does not match current send batch manifest"
            )
    else:
        payload = {
            "schema_version": manifest_schema_version,
            "batch_hash": manifest_payload.get("batch_hash"),
            "batch_label": manifest_payload.get("batch_label"),
            "manifest_path": str((ledger_path.parent / SEND_BATCH_MANIFEST_FILE).resolve()),
            "created_at": None,
            "updated_at": None,
            "entries": {},
        }

    payload.setdefault("schema_version", manifest_schema_version)
    payload.setdefault("batch_hash", manifest_payload.get("batch_hash"))
    payload.setdefault("batch_label", manifest_payload.get("batch_label"))
    payload.setdefault("manifest_path", str((ledger_path.parent / SEND_BATCH_MANIFEST_FILE).resolve()))
    payload.setdefault("created_at", None)
    payload.setdefault("updated_at", None)
    payload.setdefault("entries", {})
    for entry in manifest_payload.get("entries", []):
        payload["entries"].setdefault(entry["pdf_key"], _default_ledger_entry(entry))
    return payload


def save_send_ledger(ledger_path: Path, ledger: Dict[str, Any]) -> None:
    ledger["updated_at"] = _now_iso()
    temp_path = ledger_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(ledger_path)


ALLOWED_LEDGER_TRANSITIONS = {
    "pending": {"opened", "unsure", "failed"},
    "opened": {"clicked", "failed"},
    "clicked": {"confirmed", "unsure", "failed"},
    "unsure": set(),
    "failed": set(),
    "confirmed": set(),
}


def _failed_entry_retryable(entry: Dict[str, Any]) -> bool:
    history = list(entry.get("history") or [])
    seen_states = {
        str(item.get("state") or "").strip()
        for item in history
        if str(item.get("state") or "").strip()
    }
    return not any(state in seen_states for state in {"clicked", "confirmed", "unsure"})


def transition_send_ledger_entry(
    ledger: Dict[str, Any],
    pdf_key: str,
    new_state: str,
    *,
    allow_unsure_resume: bool = False,
    note: str = "",
) -> Dict[str, Any]:
    if new_state not in LEDGER_STATES:
        raise ValueError(f"Unsupported ledger state: {new_state}")
    entry = ledger.setdefault("entries", {}).get(pdf_key)
    if entry is None:
        raise KeyError(f"Unknown pdf_key in ledger: {pdf_key}")
    current_state = str(entry.get("state") or "pending")
    if new_state == current_state:
        raise RuntimeError(f"Ledger entry {pdf_key} already in state {current_state}")
    allowed = ALLOWED_LEDGER_TRANSITIONS.get(current_state, set())
    if current_state == "failed" and _failed_entry_retryable(entry):
        allowed = {"opened"}
    if current_state == "unsure" and allow_unsure_resume:
        allowed = {"opened"}
    if new_state not in allowed:
        raise RuntimeError(
            f"Invalid ledger transition for {pdf_key}: {current_state} -> {new_state}"
        )
    entry["state"] = new_state
    entry["last_updated"] = _now_iso()
    entry.setdefault("history", []).append(
        {
            "state": new_state,
            "at": _now_iso(),
            "note": note,
        }
    )
    return entry


def resolve_unsure_ledger_entry(
    manifest_payload: Dict[str, Any],
    ledger: Dict[str, Any],
    *,
    filename: str,
    resolution: str,
    note: str = "",
) -> str:
    normalized_filename = str(filename or "").strip()
    if not normalized_filename:
        raise ValueError("Filename is required to resolve an UNSURE ledger entry")

    normalized_resolution = str(resolution or "").strip().lower()
    if normalized_resolution not in {"confirmed", "pending"}:
        raise ValueError(f"Unsupported UNSURE resolution: {resolution}")

    matches = [
        entry
        for entry in manifest_payload.get("entries", [])
        if str(entry.get("filename") or "").strip() == normalized_filename
    ]
    if not matches:
        raise KeyError(f"Manifest entry not found for filename: {normalized_filename}")
    if len(matches) > 1:
        raise RuntimeError(f"Multiple manifest entries matched filename: {normalized_filename}")

    manifest_entry = matches[0]
    pdf_key = str(manifest_entry.get("pdf_key") or "").strip()
    if not pdf_key:
        raise RuntimeError(f"Manifest entry missing pdf_key for filename: {normalized_filename}")

    ledger_entry = ledger.setdefault("entries", {}).get(pdf_key)
    if ledger_entry is None:
        raise KeyError(f"Ledger entry not found for filename: {normalized_filename}")

    current_state = str(ledger_entry.get("state") or "pending")
    if current_state != "unsure":
        raise RuntimeError(
            f"Can only resolve UNSURE ledger entries: {normalized_filename} is {current_state}"
        )

    note_text = note.strip() or f"manual_resolve:{normalized_resolution}"
    ledger_entry["state"] = normalized_resolution
    ledger_entry["last_updated"] = _now_iso()
    ledger_entry.setdefault("history", []).append(
        {
            "state": normalized_resolution,
            "at": _now_iso(),
            "note": note_text,
        }
    )
    return pdf_key


def select_manifest_entries_for_send(
    manifest_payload: Dict[str, Any],
    ledger: Dict[str, Any],
    *,
    allow_unsure_resume: bool = False,
) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    seen_pdf_keys: set[str] = set()
    for entry in manifest_payload.get("entries", []):
        pdf_key = str(entry.get("pdf_key") or "").strip()
        if not pdf_key:
            raise RuntimeError("Manifest entry missing pdf_key")
        if pdf_key in seen_pdf_keys:
            raise RuntimeError(f"Duplicate pdf_key in manifest: {pdf_key}")
        seen_pdf_keys.add(pdf_key)
        ledger_state = str(
            ledger.get("entries", {}).get(pdf_key, {}).get("state") or "pending"
        )
        if ledger_state == "confirmed":
            continue
        if ledger_state == "unsure" and not allow_unsure_resume:
            continue
        if ledger_state == "failed" and not _failed_entry_retryable(
            ledger.get("entries", {}).get(pdf_key, {})
        ):
            continue
        if ledger_state not in {"pending", "unsure", "failed"}:
            continue
        selected.append(entry)
    return selected


def resolve_manifest_entry_path(batch_root: Path, entry: Dict[str, Any]) -> Path:
    relative_output_path = str(entry.get("relative_output_path") or "").replace("\\", "/").lstrip("./")
    expected_sha_raw = str(entry.get("sha256") or "").strip()
    expected_sha256 = expected_sha_raw if _looks_like_sha256(expected_sha_raw) else ""
    expected_size = int(entry.get("file_size") or 0)
    resolved_batch_root = Path(batch_root).resolve()
    exact_path = (resolved_batch_root / relative_output_path).resolve()
    try:
        exact_path.relative_to(resolved_batch_root)
    except ValueError as exc:
        raise RuntimeError(
            f"Manifest entry path escapes immutable batch root: {relative_output_path}"
        ) from exc
    if exact_path.exists():
        if expected_sha256:
            if _sha256_file(exact_path) == expected_sha256 and (
                expected_size <= 0 or exact_path.stat().st_size == expected_size
            ):
                return exact_path
        else:
            return exact_path

    matches: List[Path] = []
    for candidate in sorted(resolved_batch_root.rglob("*.pdf")):
        stat = candidate.stat()
        if expected_size and stat.st_size != expected_size:
            continue
        if expected_sha256:
            if _sha256_file(candidate) == expected_sha256:
                matches.append(candidate)
        elif candidate.name == Path(relative_output_path).name:
            matches.append(candidate)
        elif expected_size:
            matches.append(candidate)

    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise FileNotFoundError(
            f"Unable to resolve manifest entry path for {entry.get('filename') or relative_output_path}"
        )
    raise RuntimeError(
        f"Multiple PDF candidates matched immutable manifest identity for {entry.get('filename') or relative_output_path}"
    )
