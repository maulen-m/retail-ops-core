"""One-day, owner-approved exclusions for already-packed waybill batches.

This is deliberately separate from shipping-obligation truth.  A validated
exclusion suppresses duplicate PDF generation for one target date, but it never
discharges the order or marks physical handover.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping

from core.ops.waybill_shipping_obligations import normalize_store_code


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PREPACKED_EXCLUSION_PATH = (
    PROJECT_ROOT / "runtime" / "state" / "waybill_prepacked_exclusion.json"
)
DEFAULT_PREPACKED_EXCLUSION_EXPECTATION_PATH = (
    PROJECT_ROOT / "runtime" / "state" / "waybill_prepacked_exclusion_expected.json"
)
SCHEMA_VERSION = "autonomous_business.waybill_prepacked_exclusion.v1"
EXPECTATION_SCHEMA_VERSION = 1


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _normalized_ids_by_store(
    values: Mapping[str, Iterable[Any]] | None,
) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for raw_store, raw_ids in dict(values or {}).items():
        store = normalize_store_code(raw_store)
        for raw_id in raw_ids or []:
            order_id = _clean(raw_id)
            if store and order_id:
                out[store].add(order_id)
    return {store: set(ids) for store, ids in sorted(out.items())}


def load_prepacked_exclusion_expectation(
    *,
    target_date: date,
    path: Path = DEFAULT_PREPACKED_EXCLUSION_EXPECTATION_PATH,
) -> dict[str, Any] | None:
    """Load the optional effective-dated expectation for one closeout date."""
    path = Path(path)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise RuntimeError("Prepacked-exclusion expectation marker must be an object")
    if int(payload.get("schema_version") or 0) != EXPECTATION_SCHEMA_VERSION:
        raise RuntimeError("Unsupported prepacked-exclusion expectation schema")
    expectations = payload.get("expectations")
    if not isinstance(expectations, list):
        raise RuntimeError("Prepacked-exclusion expectations must be a list")
    matching = [
        dict(item)
        for item in expectations
        if isinstance(item, Mapping)
        and _clean(item.get("target_date")) == target_date.isoformat()
    ]
    if not matching:
        return None
    if len(matching) != 1:
        raise RuntimeError("Prepacked-exclusion expectation date is duplicated")
    expectation = matching[0]
    decision_id = _clean(expectation.get("decision_id"))
    decision_sha256 = _clean(expectation.get("decision_sha256")).lower()
    if not decision_id:
        raise RuntimeError("Prepacked-exclusion expectation lacks decision_id")
    if len(decision_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in decision_sha256
    ):
        raise RuntimeError("Prepacked-exclusion expectation has invalid decision_sha256")
    return {
        **expectation,
        "target_date": target_date.isoformat(),
        "decision_id": decision_id,
        "decision_sha256": decision_sha256,
        "path": str(path.resolve()),
    }


def load_validated_prepacked_exclusion(
    *,
    target_date: date,
    path: Path = DEFAULT_PREPACKED_EXCLUSION_PATH,
) -> dict[str, Any] | None:
    """Return a validated date-matched decision, or ``None`` when not applicable."""
    path = Path(path)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError("Unsupported prepacked-exclusion schema")
    if _clean(payload.get("target_date")) != target_date.isoformat():
        return None
    if _clean(payload.get("authority")) != "human_owner":
        raise RuntimeError("Prepacked exclusion lacks human-owner authority")
    if payload.get("preserve_physical_handover_obligation") is not True:
        raise RuntimeError("Prepacked exclusion must preserve physical-handover obligations")

    manifest_path = Path(_clean(payload.get("source_manifest_path"))).expanduser().resolve()
    ledger_path = Path(_clean(payload.get("source_telegram_ledger_path"))).expanduser().resolve()
    if not manifest_path.is_file() or not ledger_path.is_file():
        raise RuntimeError("Prepacked exclusion source manifest or Telegram ledger is missing")
    if _sha256(manifest_path) != _clean(payload.get("source_manifest_sha256")):
        raise RuntimeError("Prepacked exclusion source manifest SHA-256 mismatch")
    if _sha256(ledger_path) != _clean(payload.get("source_telegram_ledger_sha256")):
        raise RuntimeError("Prepacked exclusion Telegram ledger SHA-256 mismatch")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if int(manifest.get("schema_version") or 0) != 4:
        raise RuntimeError("Prepacked exclusion requires a schema-v4 source manifest")
    if _clean(manifest.get("target_date")) != _clean(payload.get("source_target_date")):
        raise RuntimeError("Prepacked exclusion source target-date mismatch")
    if _clean(manifest.get("batch_hash")) != _clean(payload.get("source_batch_hash")):
        raise RuntimeError("Prepacked exclusion source batch-hash mismatch")
    if _clean(ledger.get("batch_hash")) != _clean(manifest.get("batch_hash")):
        raise RuntimeError("Prepacked exclusion Telegram ledger batch-hash mismatch")

    manifest_entries = manifest.get("entries")
    ledger_entries = ledger.get("entries")
    if not isinstance(manifest_entries, list) or not isinstance(ledger_entries, dict):
        raise RuntimeError("Prepacked exclusion source entries are malformed")
    manifest_pdf_keys = {_clean(entry.get("pdf_key")) for entry in manifest_entries}
    if not manifest_pdf_keys or manifest_pdf_keys != set(ledger_entries):
        raise RuntimeError("Prepacked exclusion manifest/Telegram PDF scope mismatch")
    if any(
        not isinstance(entry, Mapping) or _clean(entry.get("state")) != "confirmed"
        for entry in ledger_entries.values()
    ):
        raise RuntimeError("Prepacked exclusion source Telegram ledger is not fully confirmed")

    observed: dict[str, set[str]] = defaultdict(set)
    for entry in manifest_entries:
        for line in entry.get("source_lines") or []:
            store = normalize_store_code(line.get("store_code"))
            order_id = _clean(line.get("order_id"))
            if store and order_id:
                observed[store].add(order_id)
    observed = {store: set(ids) for store, ids in sorted(observed.items())}
    declared = _normalized_ids_by_store(payload.get("excluded_order_ids_by_store"))
    if observed != declared:
        raise RuntimeError("Prepacked exclusion declared order scope differs from source manifest")
    declared_counts = {
        normalize_store_code(store): int(count)
        for store, count in dict(payload.get("excluded_counts_by_store") or {}).items()
    }
    if {store: len(ids) for store, ids in declared.items()} != declared_counts:
        raise RuntimeError("Prepacked exclusion declared store counts mismatch")
    if sum(declared_counts.values()) != int(payload.get("excluded_order_count") or -1):
        raise RuntimeError("Prepacked exclusion total count mismatch")
    if set(manifest.get("send_order_ids") or []) != {
        order_id for ids in observed.values() for order_id in ids
    }:
        raise RuntimeError("Prepacked exclusion source send-order scope mismatch")

    return {
        **payload,
        "path": str(path.resolve()),
        "decision_sha256": _sha256(path),
        "excluded_order_ids_by_store": declared,
        "source_manifest_path": str(manifest_path),
        "source_telegram_ledger_path": str(ledger_path),
    }


def apply_prepacked_exclusion(
    required_ids_by_store: Mapping[str, Iterable[Any]],
    decision: Mapping[str, Any] | None,
) -> dict[str, Any]:
    before = _normalized_ids_by_store(required_ids_by_store)
    if decision is None:
        return {
            "applied": False,
            "required_ids_by_store": before,
            "excluded_active_ids_by_store": {},
            "inactive_declared_ids_by_store": {},
        }

    declared = _normalized_ids_by_store(decision.get("excluded_order_ids_by_store"))
    excluded_active = {
        store: before.get(store, set()) & ids for store, ids in declared.items()
    }
    inactive_declared = {
        store: ids - before.get(store, set()) for store, ids in declared.items()
    }
    after = {
        store: set(ids) - declared.get(store, set()) for store, ids in before.items()
    }
    if (
        "expected_required_counts_by_store" in decision
        or "expected_required_order_count" in decision
    ):
        expected_counts = {
            normalize_store_code(store): int(count)
            for store, count in dict(
                decision.get("expected_required_counts_by_store") or {}
            ).items()
        }
        actual_counts = {store: len(after.get(store, set())) for store in expected_counts}
        if actual_counts != expected_counts:
            raise RuntimeError(
                "Prepacked exclusion required-order counts mismatch: "
                f"expected={expected_counts} observed={actual_counts}"
            )
        if sum(actual_counts.values()) != int(
            decision.get("expected_required_order_count") or -1
        ):
            raise RuntimeError("Prepacked exclusion required-order total mismatch")
        count_assertion = "strict"
    else:
        count_assertion = "skipped_absent_expected_counts"
    return {
        "applied": True,
        "count_assertion": count_assertion,
        "required_ids_by_store": after,
        "excluded_active_ids_by_store": excluded_active,
        "inactive_declared_ids_by_store": inactive_declared,
        "counts_before": {store: len(ids) for store, ids in sorted(before.items())},
        "counts_after": {store: len(ids) for store, ids in sorted(after.items())},
        "excluded_active_count": sum(len(ids) for ids in excluded_active.values()),
        "declared_exclusion_count": sum(len(ids) for ids in declared.values()),
    }
