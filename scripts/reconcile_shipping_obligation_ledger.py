#!/usr/bin/env python3
"""Evidence-gated repair for the durable shipping-obligation ledger.

The script is dry-run by default.  It exact-reads every currently open ledger
entry from Kaspi, delegates stage/status mutation to
``core.ops.waybill_shipping_obligations``, and writes all decision evidence to a
run directory.  Applying a candidate additionally requires
``ENABLE_SHIPPING_OBLIGATION_LEDGER_REPAIR=1`` and creates a verified sibling
backup before the module's atomic save is called.

Premature-registration rule
----------------------------
An open entry is premature when its ``first_seen_target_date`` equals the
failed/aborted request's contamination date.  The hardened closeout registers
new current-target obligations only after a successful shipping (or terminal
zero-order) stage, so such an entry could not have been created by that path.
The invalid registration is removed before exact evidence is re-adjudicated for
the rollover date.  A source-proven handover/terminal result becomes a
discharged evidence record; a legitimate carryforward or manual-handover API
lag becomes a new rollover-dated open record; an otherwise unclaimed premature
entry is removed.  Entries outside the initial open adjudication set are never
changed.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.integrations.kaspi_api_client import KaspiAPIClient  # noqa: E402
from core.ops import waybill_shipping_obligations as obligations  # noqa: E402


ALMATY = ZoneInfo("Asia/Almaty")
APPLY_ENV = "ENABLE_SHIPPING_OBLIGATION_LEDGER_REPAIR"
DEFAULT_LEDGER_PATH = PROJECT_ROOT / "runtime/state/waybill_shipping_obligations.json"
DEFAULT_RUN_DIR = (
    PROJECT_ROOT
    / "runs/tmux_orchestration/20260717_fable5_system_mission/executorM2_ledger_reconcile"
)
CONTRADICTORY_MANUAL_STAGES = {
    "CANCELLING",
    "RETURN_REQUESTED",
    "CANCELLED",
    "RETURNED",
}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _attrs(order: Mapping[str, Any]) -> Mapping[str, Any]:
    value = order.get("attributes")
    return value if isinstance(value, Mapping) else order


def _safe_evidence_summary(detail: Mapping[str, Any], *, stage: str) -> dict[str, Any]:
    error = _clean(detail.get("error"))
    order = detail.get("order")
    if error or not isinstance(order, Mapping):
        return {
            "exact_get_ok": False,
            "error": error or "exact GET returned no order object",
            "stage": stage,
        }
    attrs = _attrs(order)
    delivery = attrs.get("kaspiDelivery")
    if not isinstance(delivery, Mapping):
        delivery = {}
    return {
        "exact_get_ok": True,
        "state": _clean(attrs.get("state")),
        "status": _clean(attrs.get("status")),
        "courier_transmission_date": (
            delivery.get("courierTransmissionDate")
            or attrs.get("courierTransmissionDate")
            or None
        ),
        "returned_to_warehouse": bool(
            attrs.get("returnedToWarehouse") or attrs.get("returned_to_warehouse")
        ),
        "stage": stage,
    }


def _module_reconcile_one(
    *,
    prior_entry: Mapping[str, Any] | None,
    store_code: str,
    order_id: str,
    detail: Mapping[str, Any],
    rollover_date: date,
    ready_set_at: str,
    now: datetime,
) -> dict[str, Any]:
    key = obligations.obligation_key(store_code, order_id)
    entries = {key: copy.deepcopy(dict(prior_entry))} if prior_entry is not None else {}
    result = obligations.reconcile_shipping_obligations(
        prior_ledger={
            "schema_version": obligations.SCHEMA_VERSION,
            "updated_at": None,
            "request_identity": {},
            "entries": entries,
        },
        current_active_order_ids_by_store={store_code: {order_id}},
        detail_results={key: dict(detail)},
        target_date=rollover_date,
        ready_set_at=ready_set_at,
        now=now,
    )
    entry = dict(result["ledger"]["entries"][key])
    return {"entry": entry, "issues": list(result.get("issues") or [])}


def reconcile_ledger(
    *,
    prior_ledger: Mapping[str, Any],
    detail_results: Mapping[str, Mapping[str, Any]],
    contamination_date: date,
    rollover_date: date,
    manual_handover_stores: set[str],
    carryforward_stores: set[str],
    now: datetime,
    ready_set_at: str,
) -> dict[str, Any]:
    """Return a scope-locked candidate ledger and per-entry decisions."""
    prior = copy.deepcopy(dict(prior_ledger))
    prior_entries = prior.get("entries")
    if int(prior.get("schema_version") or 0) != obligations.SCHEMA_VERSION:
        raise ValueError("unsupported shipping obligation ledger schema")
    if not isinstance(prior_entries, dict):
        raise ValueError("shipping obligation ledger entries must be an object")

    manual_stores = {
        obligations.normalize_store_code(value) for value in manual_handover_stores
    }
    carry_stores = {
        obligations.normalize_store_code(value) for value in carryforward_stores
    }
    contamination_iso = contamination_date.isoformat()
    rollover_iso = rollover_date.isoformat()
    adjudicated_keys = {
        str(key)
        for key, entry in prior_entries.items()
        if isinstance(entry, Mapping)
        and _clean(entry.get("status")) in obligations.OPEN_STATUSES
    }
    if set(detail_results) != adjudicated_keys:
        missing = sorted(adjudicated_keys - set(detail_results))
        extra = sorted(set(detail_results) - adjudicated_keys)
        raise ValueError(
            "fresh exact evidence scope mismatch: "
            f"missing={missing or []} extra={extra or []}"
        )

    candidate_entries = {
        str(key): copy.deepcopy(value)
        for key, value in prior_entries.items()
        if str(key) not in adjudicated_keys
    }
    untouched_entries = copy.deepcopy(candidate_entries)
    decisions: list[dict[str, Any]] = []
    contradiction_count = 0
    api_uncertainty_count = 0
    module_issue_count = 0
    premature_count = 0

    for key in sorted(adjudicated_keys):
        prior_entry = dict(prior_entries[key])
        store_code = obligations.normalize_store_code(prior_entry.get("store_code"))
        order_id = _clean(prior_entry.get("order_id"))
        canonical_key = obligations.obligation_key(store_code, order_id)
        if canonical_key != key:
            raise ValueError(f"ledger identity changed during adjudication: {key}")
        premature = (
            _clean(prior_entry.get("status")) in obligations.OPEN_STATUSES
            and _clean(prior_entry.get("first_seen_target_date")) == contamination_iso
        )
        if premature:
            premature_count += 1

        detail = dict(detail_results[key])
        module_prior = None if premature else prior_entry
        first_pass = _module_reconcile_one(
            prior_entry=module_prior,
            store_code=store_code,
            order_id=order_id,
            detail=detail,
            rollover_date=rollover_date,
            ready_set_at=ready_set_at,
            now=now,
        )
        candidate_entry = dict(first_pass["entry"])
        stage = _clean(candidate_entry.get("last_stage")) or "UNKNOWN"
        evidence = _safe_evidence_summary(detail, stage=stage)
        manual_scope = premature and store_code in manual_stores
        carry_scope = store_code in carry_stores

        contradiction = ""
        if manual_scope and stage in CONTRADICTORY_MANUAL_STAGES:
            contradiction = (
                f"manual-handover day truth contradicted by fresh stage {stage}"
            )
        elif carry_scope and _clean(candidate_entry.get("status")) not in obligations.OPEN_STATUSES:
            contradiction = (
                f"required carryforward day truth contradicted by fresh stage {stage}"
            )

        if contradiction:
            contradiction_count += 1
            held = _module_reconcile_one(
                prior_entry=module_prior,
                store_code=store_code,
                order_id=order_id,
                detail={"error": contradiction},
                rollover_date=rollover_date,
                ready_set_at=ready_set_at,
                now=now,
            )
            candidate_entry = dict(held["entry"])
            module_issues = list(held["issues"])
            action = "keep-open"
            reason = f"fresh evidence contradicts day truth; retained open: {contradiction}"
        else:
            module_issues = list(first_pass["issues"])
            final_status = _clean(candidate_entry.get("status"))
            if final_status == obligations.STATUS_DISCHARGED:
                action = "discharge-with-evidence"
                reason = (
                    "fresh exact GET proves module discharge stage "
                    f"{_clean(candidate_entry.get('discharge_reason')) or stage}"
                )
            elif manual_scope:
                action = "keep-open"
                reason = "manual handover not yet in API"
                if not evidence["exact_get_ok"]:
                    reason += f"; exact GET uncertain: {evidence['error']}"
            elif carry_scope:
                action = "keep-open"
                reason = f"legitimate carryforward for {rollover_iso}"
            elif premature:
                action = "remove-premature-registration"
                reason = (
                    "failed/aborted current-target registration is forbidden by the "
                    "hardened successful-path rule"
                )
            else:
                action = "keep-open"
                reason = f"fresh exact GET retains module stage {stage}"

        module_issue_count += len(module_issues)
        if not evidence["exact_get_ok"]:
            api_uncertainty_count += 1

        if action != "remove-premature-registration":
            candidate_entries[key] = candidate_entry

        decisions.append(
            {
                "key": key,
                "store_code": store_code,
                "order_id": order_id,
                "prior_status": _clean(prior_entry.get("status")),
                "prior_first_seen_target_date": _clean(
                    prior_entry.get("first_seen_target_date")
                ),
                "premature_registration_removed": premature,
                "fresh_evidence": evidence,
                "action": action,
                "reason": reason,
                "final_status": (
                    _clean(candidate_entry.get("status"))
                    if action != "remove-premature-registration"
                    else "removed"
                ),
                "final_first_seen_target_date": (
                    _clean(candidate_entry.get("first_seen_target_date"))
                    if action != "remove-premature-registration"
                    else ""
                ),
                "module_issues": module_issues,
                "contradiction": contradiction,
            }
        )

    metadata_shell = obligations.reconcile_shipping_obligations(
        prior_ledger=obligations.empty_shipping_obligation_ledger(),
        current_active_order_ids_by_store={},
        detail_results={},
        target_date=rollover_date,
        ready_set_at=ready_set_at,
        now=now,
    )["ledger"]
    candidate = copy.deepcopy(metadata_shell)
    candidate["entries"] = dict(sorted(candidate_entries.items()))

    for key, value in untouched_entries.items():
        if candidate["entries"].get(key) != value:
            raise RuntimeError(f"out-of-scope entry changed: {key}")
    if set(candidate["entries"]) - (set(prior_entries) | adjudicated_keys):
        raise RuntimeError("candidate contains an entry outside the adjudicated scope")

    remaining_contamination = sorted(
        key
        for key, entry in candidate["entries"].items()
        if _clean(entry.get("first_seen_target_date")) == contamination_iso
    )
    open_counts = Counter(
        obligations.normalize_store_code(entry.get("store_code"))
        for entry in candidate["entries"].values()
        if _clean(entry.get("status")) in obligations.OPEN_STATUSES
    )
    action_counts = Counter(item["action"] for item in decisions)
    return {
        "candidate_ledger": candidate,
        "decisions": decisions,
        "summary": {
            "adjudicated_count": len(adjudicated_keys),
            "premature_registration_count": premature_count,
            "action_counts": dict(sorted(action_counts.items())),
            "open_counts_by_store": dict(sorted(open_counts.items())),
            "remaining_contamination_keys": remaining_contamination,
            "api_uncertainty_count": api_uncertainty_count,
            "module_issue_count": module_issue_count,
            "contradiction_count": contradiction_count,
            "untouched_entry_count": len(untouched_entries),
        },
    }


def fetch_exact_details(ledger: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Perform one fresh exact Kaspi GET for every currently open entry."""
    clients: dict[str, KaspiAPIClient] = {}
    results: dict[str, dict[str, Any]] = {}
    entries = dict(ledger.get("entries") or {})
    for key, raw_entry in sorted(entries.items()):
        entry = dict(raw_entry or {})
        if _clean(entry.get("status")) not in obligations.OPEN_STATUSES:
            continue
        store_code = obligations.normalize_store_code(entry.get("store_code"))
        order_id = _clean(entry.get("order_id"))
        canonical_key = obligations.obligation_key(store_code, order_id)
        if canonical_key != str(key):
            raise ValueError(f"ledger entry identity mismatch before exact GET: {key}")
        try:
            client = clients.get(store_code)
            if client is None:
                client = KaspiAPIClient(store_code=store_code, enable_writes=False)
                clients[store_code] = client
            response = client.get_order(order_id)
            if not response.success:
                results[canonical_key] = {
                    "error": _clean(response.error) or "fresh exact GET failed"
                }
            elif not isinstance(response.data, dict):
                results[canonical_key] = {
                    "error": "fresh exact GET returned a malformed payload"
                }
            else:
                results[canonical_key] = {"order": response.data}
        except Exception as exc:
            results[canonical_key] = {
                "error": f"{type(exc).__name__}: {exc}"
            }
    return results


def _parse_store_count(value: str) -> tuple[str, int]:
    store, separator, raw_count = value.partition("=")
    if not separator:
        raise argparse.ArgumentTypeError("expected STORE=COUNT")
    normalized = obligations.normalize_store_code(store)
    try:
        count = int(raw_count)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("COUNT must be an integer") from exc
    if not normalized or count < 0:
        raise argparse.ArgumentTypeError("STORE must be nonblank and COUNT nonnegative")
    return normalized, count


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_summary(path: Path, report: Mapping[str, Any]) -> None:
    summary = dict(report["summary"])
    mode = _clean(report.get("mode")).upper()
    warnings = (
        int(summary.get("api_uncertainty_count") or 0)
        + int(summary.get("module_issue_count") or 0)
        + int(summary.get("contradiction_count") or 0)
    )
    gate = "GREEN" if warnings == 0 else "YELLOW"
    lines = [
        f"# Shipping obligation ledger reconciliation — {mode}",
        "",
        f"Gate: {gate}",
        "",
        f"- Ledger: `{report['ledger_path']}`",
        f"- Source SHA-256: `{report['source_sha256']}`",
        f"- Contamination date: `{report['contamination_date']}`",
        f"- Rollover date: `{report['rollover_date']}`",
        f"- Exact GET attempts / adjudicated entries: `{summary['adjudicated_count']}`",
        f"- Premature registrations removed before re-adjudication: `{summary['premature_registration_count']}`",
        f"- Actions: `{json.dumps(summary['action_counts'], sort_keys=True)}`",
        f"- Final open counts: `{json.dumps(summary['open_counts_by_store'], sort_keys=True)}`",
        f"- Remaining `{report['contamination_date']}` first-seen rows: `{len(summary['remaining_contamination_keys'])}`",
        f"- API uncertainties: `{summary['api_uncertainty_count']}`",
        f"- Day-truth contradictions retained open: `{summary['contradiction_count']}`",
        f"- Candidate SHA-256: `{report['candidate_sha256']}`",
    ]
    if report.get("backup_path"):
        lines.extend(
            [
                f"- Verified backup: `{report['backup_path']}`",
                f"- Persisted SHA-256: `{report.get('persisted_sha256')}`",
            ]
        )
    lines.extend(
        [
            "",
            "The JSON decision log records prior status, fresh source evidence, action,",
            "reason, and final status for every adjudicated entry. No full Kaspi payload",
            "or customer data is retained.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _verified_backup(ledger_path: Path, *, expected_sha256: str, now: datetime) -> Path:
    if _sha256(ledger_path) != expected_sha256:
        raise RuntimeError("ledger changed after evidence collection; refusing apply")
    stamp = now.strftime("%Y%m%d_%H%M%S")
    backup_path = ledger_path.with_name(
        f"{ledger_path.stem}.pre_reconcile_{stamp}{ledger_path.suffix}.bak"
    )
    if backup_path.exists():
        raise RuntimeError(f"refusing to overwrite existing backup: {backup_path}")
    shutil.copy2(ledger_path, backup_path)
    if _sha256(backup_path) != expected_sha256:
        raise RuntimeError(f"backup verification failed: {backup_path}")
    obligations.load_shipping_obligation_ledger(backup_path)
    return backup_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger-path", type=Path, default=DEFAULT_LEDGER_PATH)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    parser.add_argument("--dotenv-path", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--contamination-date", type=date.fromisoformat, required=True)
    parser.add_argument("--rollover-date", type=date.fromisoformat)
    parser.add_argument("--manual-handover-store", action="append", default=[])
    parser.add_argument("--carryforward-store", action="append", default=[])
    parser.add_argument("--expected-open", type=_parse_store_count, action="append", default=[])
    parser.add_argument("--expected-premature-count", type=int)
    parser.add_argument("--apply", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.apply and _clean(os.environ.get(APPLY_ENV)) != "1":
        raise RuntimeError(f"{APPLY_ENV}=1 is required with --apply")
    rollover_date = args.rollover_date or (args.contamination_date + timedelta(days=1))
    if rollover_date <= args.contamination_date:
        raise ValueError("rollover date must be after the contamination date")

    ledger_path = args.ledger_path.expanduser().resolve()
    run_dir = args.run_dir.expanduser().resolve()
    dotenv_path = args.dotenv_path.expanduser().resolve()
    if not ledger_path.is_file():
        raise FileNotFoundError(ledger_path)
    run_dir.mkdir(parents=True, exist_ok=True)
    load_dotenv(dotenv_path, override=False)
    os.environ["ENABLE_KASPI_WRITE"] = "0"
    os.environ["KASPI_API_CALL_LEDGER"] = "0"
    os.environ.pop("KASPI_API_CALL_LEDGER_PATH", None)

    source_sha256 = _sha256(ledger_path)
    prior = obligations.load_shipping_obligation_ledger(ledger_path)
    now = datetime.now(ALMATY)
    ready_set_at = f"ledger-reconcile:{now.isoformat()}"
    details = fetch_exact_details(prior)
    result = reconcile_ledger(
        prior_ledger=prior,
        detail_results=details,
        contamination_date=args.contamination_date,
        rollover_date=rollover_date,
        manual_handover_stores=set(args.manual_handover_store),
        carryforward_stores=set(args.carryforward_store),
        now=now,
        ready_set_at=ready_set_at,
    )
    summary = dict(result["summary"])

    if args.expected_premature_count is not None and (
        int(summary["premature_registration_count"]) != args.expected_premature_count
    ):
        raise RuntimeError(
            "premature-registration count mismatch: "
            f"expected={args.expected_premature_count} "
            f"observed={summary['premature_registration_count']}"
        )
    expected_open = dict(args.expected_open)
    for store_code, expected_count in expected_open.items():
        observed = int(summary["open_counts_by_store"].get(store_code, 0))
        if observed != expected_count:
            raise RuntimeError(
                f"final open count mismatch for {store_code}: "
                f"expected={expected_count} observed={observed}"
            )
    if summary["remaining_contamination_keys"]:
        raise RuntimeError(
            "candidate retains contamination-date rows: "
            + ", ".join(summary["remaining_contamination_keys"])
        )

    mode = "apply" if args.apply else "dry_run"
    candidate_path = run_dir / f"candidate_ledger_{mode}.json"
    obligations.save_shipping_obligation_ledger(candidate_path, result["candidate_ledger"])
    reloaded_candidate = obligations.load_shipping_obligation_ledger(candidate_path)
    if reloaded_candidate != result["candidate_ledger"]:
        raise RuntimeError("candidate ledger failed module round-trip validation")
    candidate_sha256 = _sha256(candidate_path)

    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": now.isoformat(),
        "mode": mode,
        "ledger_path": str(ledger_path),
        "run_dir": str(run_dir),
        "source_sha256": source_sha256,
        "candidate_path": str(candidate_path),
        "candidate_sha256": candidate_sha256,
        "contamination_date": args.contamination_date.isoformat(),
        "rollover_date": rollover_date.isoformat(),
        "manual_handover_stores": sorted(
            obligations.normalize_store_code(value)
            for value in args.manual_handover_store
        ),
        "carryforward_stores": sorted(
            obligations.normalize_store_code(value) for value in args.carryforward_store
        ),
        "expected_open_counts": expected_open,
        "summary": summary,
        "backup_path": None,
        "backup_sha256": None,
        "persisted_sha256": None,
    }

    if args.apply:
        backup_path = _verified_backup(
            ledger_path,
            expected_sha256=source_sha256,
            now=now,
        )
        report["backup_path"] = str(backup_path)
        report["backup_sha256"] = _sha256(backup_path)
        obligations.save_shipping_obligation_ledger(
            ledger_path,
            result["candidate_ledger"],
        )
        persisted = obligations.load_shipping_obligation_ledger(ledger_path)
        if persisted != result["candidate_ledger"]:
            raise RuntimeError("persisted ledger failed module readback verification")
        report["persisted_sha256"] = _sha256(ledger_path)
        if report["persisted_sha256"] != candidate_sha256:
            raise RuntimeError("persisted ledger hash differs from reviewed candidate")

    _write_json(run_dir / f"{mode}_decisions.json", {"decisions": result["decisions"]})
    _write_json(run_dir / f"{mode}_report.json", report)
    _write_summary(run_dir / f"{mode.upper()}_SUMMARY.md", report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
