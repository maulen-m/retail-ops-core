#!/usr/bin/env python3
"""Offline weekly replay of the latest completed Google Board closeout."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import sys
import tempfile
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.alerts.ops_alert_outbox import enqueue_alert  # noqa: E402
from core.integrations.google_ops_board import (  # noqa: E402
    extract_rows_from_matrix,
    load_ops_board_contract,
)
from core.ops.waybill_prepacked_exclusions import apply_prepacked_exclusion  # noqa: E402
from core.ops.waybill_shipping_obligations import (  # noqa: E402
    load_shipping_obligation_ledger,
    normalize_store_code,
    obligation_key,
    reconcile_shipping_obligations,
    required_line_scope_hash,
)
from scripts.run_google_ops_board_closeout import (  # noqa: E402
    ALMATY_TZ,
    _apply_store_day_state_scope,
    _existing_open_orders_present_in_current,
    _load_preserved_board_client,
    _select_run_control_row,
    _union_order_ids_by_store,
)


DEFAULT_WORKFLOW_ROOT = PROJECT_ROOT / "exports/google_ops_board/workflow_runs"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports/google_ops_board/shadow_days"
LIVE_RUNTIME_STATE_ROOT = PROJECT_ROOT / "runtime/state"
SIMULATE_OBLIGATION_DETAIL_ERROR_ENV = "AB_SHADOW_SIMULATE_OBLIGATION_DETAIL_ERROR"
SIMULATE_EXCLUSION_DECISION_MISSING_ENV = (
    "AB_SHADOW_SIMULATE_EXCLUSION_DECISION_MISSING"
)
RUN_FILES = (
    "closeout_report.json",
    "run_control_snapshot.json",
    "salesraw_snapshot.json",
    "api_active_order_ids_by_store.json",
    "shipping_obligation_reconciliation.json",
    "prepacked_exclusion_report.json",
    "store_day_state_report.json",
    "expected_closeout_orders.json",
)


class ShadowDayError(RuntimeError):
    pass


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    return text[:-2] if text.endswith(".0") and text[:-2].isdigit() else text


def _truthy(value: Any) -> bool:
    return value is True or _clean(value).casefold() in {"1", "true", "yes", "on"}


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ShadowDayError(f"{label} is missing or invalid: {path}") from exc
    if not isinstance(payload, dict):
        raise ShadowDayError(f"{label} must be an object: {path}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ids(values: Mapping[str, Iterable[Any]] | None) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for raw_store, raw_ids in dict(values or {}).items():
        store = normalize_store_code(raw_store)
        if store:
            result.setdefault(store, set()).update(
                order_id
                for order_id in (_clean(value) for value in raw_ids or [])
                if order_id
            )
    return {store: set(order_ids) for store, order_ids in sorted(result.items())}


def _serial(values: Mapping[str, Iterable[Any]]) -> dict[str, list[str]]:
    return {store: sorted(order_ids) for store, order_ids in _ids(values).items()}


def _counts(values: Mapping[str, Iterable[Any]]) -> dict[str, int]:
    return {store: len(order_ids) for store, order_ids in _ids(values).items()}


def _completed_report(path: Path) -> dict[str, Any] | None:
    try:
        report = _read_json(path, "closeout report")
    except ShadowDayError:
        return None
    if (
        report.get("ok") is True
        and _clean(report.get("mode")) == "apply"
        and _clean(report.get("target_date"))
        and _clean(report.get("completed_at"))
    ):
        return report
    return None


def _select_run(
    workflow_root: Path,
    *,
    target_date: date | None,
    source_run_dir: Path | None,
) -> tuple[Path, dict[str, Any]]:
    if source_run_dir is not None:
        run_dir = Path(source_run_dir).expanduser().resolve()
        report = _completed_report(run_dir / "closeout_report.json")
        if report is None:
            raise ShadowDayError("source run is not a completed successful apply closeout")
        if target_date and _clean(report["target_date"]) != target_date.isoformat():
            raise ShadowDayError("source run does not match target date")
        return run_dir, report

    candidates: list[tuple[str, str, str, Path, dict[str, Any]]] = []
    for report_path in Path(workflow_root).expanduser().glob(
        "*/*/closeout_report.json"
    ):
        report = _completed_report(report_path)
        if report is None:
            continue
        target = _clean(report["target_date"])
        if target_date and target != target_date.isoformat():
            continue
        candidates.append(
            (
                target,
                _clean(report["completed_at"]),
                _clean(report.get("run_id")),
                report_path.parent,
                report,
            )
        )
    if not candidates:
        raise ShadowDayError("no completed apply closeout is available for replay")
    _target, _completed, _run_id, run_dir, report = max(candidates)
    return run_dir, report


def _source_checkpoint(run_dir: Path, report: Mapping[str, Any]) -> Path:
    target = date.fromisoformat(_clean(report["target_date"]))
    for filename in RUN_FILES:
        if not (run_dir / filename).is_file():
            raise ShadowDayError(f"completed run lacks {filename}")
    raw_path = _clean(report.get("checkpoint_path"))
    path = Path(raw_path).expanduser() if raw_path else run_dir.parent / "closeout_checkpoint.json"
    checkpoint = _read_json(path, "closeout checkpoint")
    recorded_date = _clean(checkpoint.get("target_date"))
    if recorded_date and recorded_date != target.isoformat():
        raise ShadowDayError("checkpoint target date differs from completed run")
    return path


def _copy_inputs(
    run_dir: Path,
    checkpoint_path: Path,
    temp_root: Path,
) -> tuple[Path, Path, list[dict[str, str]]]:
    copied_run = temp_root / "preserved_run"
    copied_run.mkdir(parents=True)
    evidence: list[dict[str, str]] = []
    for filename in RUN_FILES:
        source = run_dir / filename
        target = copied_run / filename
        shutil.copy2(source, target)
        evidence.append(
            {
                "name": filename,
                "source_path": str(source.resolve()),
                "sha256": _sha256(target),
            }
        )
    copied_checkpoint = temp_root / "state/closeout_checkpoint.json"
    copied_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(checkpoint_path, copied_checkpoint)
    evidence.append(
        {
            "name": "closeout_checkpoint.json",
            "source_path": str(checkpoint_path.resolve()),
            "sha256": _sha256(copied_checkpoint),
        }
    )
    return copied_run, copied_checkpoint, evidence


def _obligation_ledger(reconciliation: Mapping[str, Any], target: date) -> dict[str, Any]:
    entries: dict[str, Any] = {}
    for store, order_ids in _ids(reconciliation.get("active_order_ids_by_store")).items():
        for order_id in order_ids:
            entries[obligation_key(store, order_id)] = {
                "store_code": store,
                "order_id": order_id,
                "status": "unresolved",
                "first_seen_target_date": target.isoformat(),
                "last_seen_target_date": target.isoformat(),
                "last_stage": "RECORDED_RECONCILIATION_ACTIVE",
            }
    return {
        "schema_version": 1,
        "updated_at": None,
        "request_identity": dict(reconciliation.get("request_identity") or {}),
        "entries": dict(sorted(entries.items())),
    }


def _replay_obligations(
    *,
    reconciliation: Mapping[str, Any],
    active: dict[str, set[str]],
    target: date,
    state_path: Path,
    inject_error: bool,
) -> dict[str, Any]:
    _write_json(state_path, _obligation_ledger(reconciliation, target))
    ledger = load_shipping_obligation_ledger(state_path)
    current = _existing_open_orders_present_in_current(ledger, active)
    issues = {
        _clean(item.get("key")): dict(item)
        for item in reconciliation.get("issues") or []
        if isinstance(item, Mapping) and _clean(item.get("key"))
    }
    details: dict[str, dict[str, Any]] = {}
    for key, raw_entry in dict(ledger.get("entries") or {}).items():
        entry = dict(raw_entry or {})
        store = normalize_store_code(entry.get("store_code"))
        order_id = _clean(entry.get("order_id"))
        if order_id in current.get(store, set()):
            continue
        issue = issues.get(str(key))
        details[str(key)] = (
            {"error": _clean(issue.get("detail")) or "recorded uncertainty"}
            if issue
            else {
                "order": {
                    "attributes": {
                        "code": order_id,
                        "state": "KASPI_DELIVERY",
                        "status": "ACCEPTED_BY_MERCHANT",
                    }
                }
            }
        )
    if inject_error:
        store = sorted(active)[0] if active else "UNIVERSAL"
        order_id = "SHADOW_FAULT_OBLIGATION"
        key = obligation_key(store, order_id)
        ledger["entries"][key] = {
            "store_code": store,
            "order_id": order_id,
            "status": "unresolved",
            "first_seen_target_date": target.isoformat(),
            "last_seen_target_date": target.isoformat(),
            "last_stage": "SHADOW_FAULT_INJECTION",
        }
        details[key] = {"error": "simulated obligation-detail dependency error"}
    return reconcile_shipping_obligations(
        prior_ledger=ledger,
        current_active_order_ids_by_store=current,
        detail_results=details,
        target_date=target,
        ready_set_at=_clean(
            (reconciliation.get("request_identity") or {}).get("ready_set_at")
        ),
        now=datetime.now(ALMATY_TZ),
        uncertainty_waiver_ids_by_store=(
            reconciliation.get("uncertainty_waiver_ids_by_store") or {}
        ),
        enqueue_uncertainty_warnings=False,
    )


def _recorded_decision(report: Mapping[str, Any]) -> dict[str, Any] | None:
    if report.get("applied") is not True:
        return None
    declared = _union_order_ids_by_store(
        _ids(report.get("excluded_active_ids_by_store")),
        _ids(report.get("inactive_declared_ids_by_store")),
    )
    return {
        "decision_id": _clean(report.get("decision_id")),
        "target_date": _clean(report.get("target_date")),
        "preserve_physical_handover_obligation": True,
        "excluded_order_ids_by_store": declared,
    }


def _rewind_day_state(checkpoint_path: Path, report: Mapping[str, Any]) -> dict[str, Any]:
    checkpoint = _read_json(checkpoint_path, "copied checkpoint")
    explicit = {
        normalize_store_code(store): copy.deepcopy(dict(record))
        for store, record in dict(report.get("effective_store_states") or {}).items()
        if isinstance(record, Mapping)
        and _clean(record.get("state")).upper() != "PENDING"
    }
    if explicit:
        checkpoint["store_day_states"] = {
            "schema_version": 1,
            "stores": dict(sorted(explicit.items())),
        }
    else:
        checkpoint.pop("store_day_states", None)
    _write_json(checkpoint_path, checkpoint)
    return {"rewound_to_scope_time": True, "explicit_store_states": explicit}


def _expected_scope(expected: Mapping[str, Any]) -> dict[str, set[str]]:
    scope: dict[str, set[str]] = {}
    for order in expected.get("orders") or []:
        if not isinstance(order, Mapping):
            continue
        store = normalize_store_code(order.get("store_code"))
        order_id = _clean(order.get("order_id"))
        if store and order_id:
            scope.setdefault(store, set()).add(order_id)
    return scope


def _rebuild_expected(
    recorded: Mapping[str, Any],
    required: Mapping[str, Iterable[Any]],
) -> dict[str, Any]:
    required_pairs = {
        (store, order_id)
        for store, order_ids in _ids(required).items()
        for order_id in order_ids
    }
    recorded_pairs = {
        (normalize_store_code(order.get("store_code")), _clean(order.get("order_id"))): copy.deepcopy(dict(order))
        for order in recorded.get("orders") or []
        if isinstance(order, Mapping)
        and normalize_store_code(order.get("store_code"))
        and _clean(order.get("order_id"))
    }
    orders = [recorded_pairs[pair] for pair in sorted(required_pairs & set(recorded_pairs))]
    orders.sort(
        key=lambda item: (
            _clean(item.get("planned_shipment_date")),
            normalize_store_code(item.get("store_code")),
            _clean(item.get("order_id")),
        )
    )
    lines = [
        line
        for order in orders
        for line in order.get("lines") or []
        if isinstance(line, Mapping)
    ]
    expected_ids = sorted({_clean(order.get("order_id")) for order in orders})
    overdue_ids = sorted(
        {_clean(order.get("order_id")) for order in orders if order.get("overdue") is True}
    )
    return {
        "schema_version": 3,
        "source": "recorded_expected_orders_offline_reconstruction",
        "target_date": _clean(recorded.get("target_date")),
        "request_identity": dict(recorded.get("request_identity") or {}),
        "expected_order_ids": expected_ids,
        "overdue_order_ids": overdue_ids,
        "orders": orders,
        "line_scope_hash": required_line_scope_hash(lines),
        "counts": {
            "orders": len(expected_ids),
            "order_lines": len(lines),
            "overdue_orders": len(overdue_ids),
        },
        "counts_by_store": dict(
            sorted(Counter(normalize_store_code(order.get("store_code")) for order in orders).items())
        ),
        "counts_by_stage": dict(
            sorted(Counter(_clean(order.get("stage")) for order in orders).items())
        ),
        "missing_required_pairs": [
            {"store_code": store, "order_id": order_id}
            for store, order_id in sorted(required_pairs - set(recorded_pairs))
        ],
    }


def _compare(findings: list[dict[str, Any]], code: str, expected: Any, observed: Any) -> None:
    if expected != observed:
        findings.append({"code": code, "expected": expected, "observed": observed})


def _replay(copied_run: Path, checkpoint: Path, temp_root: Path, faults: dict[str, bool]) -> dict[str, Any]:
    closeout = _read_json(copied_run / "closeout_report.json", "copied closeout report")
    target = date.fromisoformat(_clean(closeout["target_date"]))
    contract = load_ops_board_contract()
    client, board_source = _load_preserved_board_client(copied_run, target_date=target)
    run_control = client.get_tab_values("Run_Control")
    salesraw = client.get_tab_values("SalesRaw_Today")
    run_control_row = _select_run_control_row(
        extract_rows_from_matrix(contract.tabs["Run_Control"].headers, run_control),
        target,
    ) or {}

    active_artifact = _read_json(
        copied_run / "api_active_order_ids_by_store.json", "active-order artifact"
    )
    active = _ids(active_artifact.get("stores"))
    recorded_reconciliation = _read_json(
        copied_run / "shipping_obligation_reconciliation.json",
        "obligation reconciliation",
    )
    obligation_path = temp_root / "state/waybill_shipping_obligations.json"
    reconciliation = _replay_obligations(
        reconciliation=recorded_reconciliation,
        active=active,
        target=target,
        state_path=obligation_path,
        inject_error=faults["obligation_detail_error"],
    )
    before_exclusion = _union_order_ids_by_store(
        active, _ids(reconciliation.get("active_order_ids_by_store"))
    )
    recorded_exclusion = _read_json(
        copied_run / "prepacked_exclusion_report.json", "exclusion report"
    )
    decision = None if faults["exclusion_decision_missing"] else _recorded_decision(recorded_exclusion)
    exclusion = apply_prepacked_exclusion(before_exclusion, decision)
    after_exclusion = _ids(exclusion.get("required_ids_by_store"))

    recorded_day_state = _read_json(
        copied_run / "store_day_state_report.json", "day-state report"
    )
    rewind = _rewind_day_state(checkpoint, recorded_day_state)
    after_day_state, day_state = _apply_store_day_state_scope(
        after_exclusion,
        target_date=target,
        checkpoint_path=checkpoint,
        report_path=temp_root / "reports/store_day_state_report.json",
    )
    recorded_expected = _read_json(
        copied_run / "expected_closeout_orders.json", "expected orders"
    )
    rebuilt_expected = _rebuild_expected(recorded_expected, after_day_state)

    findings: list[dict[str, Any]] = []
    if reconciliation.get("ok") is not True:
        findings.append(
            {
                "code": "obligation_reconciliation_not_green",
                "expected": True,
                "observed": False,
                "issues": reconciliation.get("issues") or [],
            }
        )
    _compare(findings, "scope_before_exclusion_diverged", recorded_exclusion.get("counts_before") or {}, _counts(before_exclusion))
    _compare(findings, "exclusion_application_diverged", bool(recorded_exclusion.get("applied")), bool(exclusion.get("applied")))
    _compare(findings, "excluded_active_scope_diverged", _serial(_ids(recorded_exclusion.get("excluded_active_ids_by_store"))), _serial(_ids(exclusion.get("excluded_active_ids_by_store"))))
    _compare(findings, "scope_after_exclusion_diverged", recorded_exclusion.get("counts_after") or {}, _counts(after_exclusion))
    _compare(findings, "scope_after_day_state_diverged", recorded_day_state.get("counts_after") or {}, _counts(after_day_state))
    _compare(findings, "day_state_effective_states_diverged", recorded_day_state.get("effective_store_states") or {}, day_state.get("effective_store_states") or {})
    _compare(findings, "expected_order_scope_diverged", _serial(_expected_scope(recorded_expected)), _serial(after_day_state))
    _compare(findings, "expected_order_ids_diverged", sorted(recorded_expected.get("expected_order_ids") or []), rebuilt_expected["expected_order_ids"])
    _compare(findings, "expected_line_scope_hash_diverged", _clean(recorded_expected.get("line_scope_hash")), rebuilt_expected["line_scope_hash"])
    _compare(findings, "expected_counts_by_store_diverged", recorded_expected.get("counts_by_store") or {}, rebuilt_expected["counts_by_store"])
    if rebuilt_expected["missing_required_pairs"]:
        findings.append(
            {
                "code": "expected_reconstruction_missing_recorded_rows",
                "expected": [],
                "observed": rebuilt_expected["missing_required_pairs"],
            }
        )
    if _clean(run_control_row.get("target_date")) != target.isoformat():
        findings.append(
            {
                "code": "preserved_run_control_target_missing",
                "expected": target.isoformat(),
                "observed": _clean(run_control_row.get("target_date")),
            }
        )
    day_state["checkpoint_rewind"] = rewind
    return {
        "findings": findings,
        "board_source": board_source,
        "preserved_board": {
            "run_control_row": run_control_row,
            "salesraw_row_count": len(
                extract_rows_from_matrix(contract.tabs["SalesRaw_Today"].headers, salesraw)
            ),
        },
        "obligations": {
            "state_copy_path": str(obligation_path),
            "state_copy_is_under_temp_root": obligation_path.is_relative_to(temp_root),
            "ok": bool(reconciliation.get("ok")),
            "issues": reconciliation.get("issues") or [],
            "active_ids_by_store": _serial(_ids(reconciliation.get("active_order_ids_by_store"))),
        },
        "scope": {
            "recorded_active_ids_by_store": _serial(active),
            "before_exclusion": _serial(before_exclusion),
            "after_exclusion": _serial(after_exclusion),
            "after_day_state": _serial(after_day_state),
        },
        "exclusion": {
            "recorded_applied": bool(recorded_exclusion.get("applied")),
            "observed_applied": bool(exclusion.get("applied")),
            "excluded_active_ids_by_store": _serial(_ids(exclusion.get("excluded_active_ids_by_store"))),
        },
        "day_state": day_state,
        "expected_orders": rebuilt_expected,
    }


def run_shadow_day(
    *,
    workflow_root: Path = DEFAULT_WORKFLOW_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    target_date: date | None = None,
    source_run_dir: Path | None = None,
    json_out: Path | None = None,
    simulate_obligation_detail_error: bool | None = None,
    simulate_exclusion_decision_missing: bool | None = None,
) -> dict[str, Any]:
    run_dir, closeout = _select_run(
        workflow_root,
        target_date=target_date,
        source_run_dir=source_run_dir,
    )
    checkpoint = _source_checkpoint(run_dir, closeout)
    target = date.fromisoformat(_clean(closeout["target_date"]))
    output_path = Path(json_out).expanduser() if json_out else Path(output_root).expanduser() / target.isoformat() / "shadow_report.json"
    faults = {
        "obligation_detail_error": (
            _truthy(os.environ.get(SIMULATE_OBLIGATION_DETAIL_ERROR_ENV))
            if simulate_obligation_detail_error is None
            else bool(simulate_obligation_detail_error)
        ),
        "exclusion_decision_missing": (
            _truthy(os.environ.get(SIMULATE_EXCLUSION_DECISION_MISSING_ENV))
            if simulate_exclusion_decision_missing is None
            else bool(simulate_exclusion_decision_missing)
        ),
    }
    started_at = datetime.now(ALMATY_TZ).isoformat()
    with tempfile.TemporaryDirectory(prefix="ab_closeout_shadow_day_") as raw_temp:
        temp_root = Path(raw_temp).resolve()
        copied_run, copied_checkpoint, copied_inputs = _copy_inputs(
            run_dir, checkpoint, temp_root
        )
        replay = _replay(copied_run, copied_checkpoint, temp_root, faults)
        findings = replay.pop("findings")
        report: dict[str, Any] = {
            "schema_version": 1,
            "kind": "weekly_closeout_shadow_day",
            "target_date": target.isoformat(),
            "source_run_id": _clean(closeout.get("run_id")),
            "source_run_dir": str(run_dir.resolve()),
            "source_completed_at": _clean(closeout.get("completed_at")),
            "started_at": started_at,
            "completed_at": datetime.now(ALMATY_TZ).isoformat(),
            "execution_mode": "offline_report_only",
            "status": "GREEN" if not findings else "WARN",
            "ok": not findings,
            "divergence": bool(findings),
            "findings": findings,
            "fault_injections": faults,
            "safety": {
                "external_writes_performed": False,
                "live_api_gets_performed": False,
                "live_google_board_read": False,
                "live_db_read": False,
                "live_runtime_state_input_read": False,
                "live_runtime_state_root_forbidden": str(LIVE_RUNTIME_STATE_ROOT.resolve()),
                "all_mutable_inputs_copied_under_temp_root": True,
                "temp_root_removed_after_run": True,
                "telegram_send_performed": False,
                "outbox_warning_mode": "local_only_not_deliverable",
            },
            "copied_inputs": copied_inputs,
            **replay,
        }

    report["warning"] = {
        "required": report["divergence"],
        "enqueued": False,
        "local_only": report["divergence"],
        "held": False,
        "error": "",
    }
    if report["divergence"]:
        try:
            enqueue_alert(
                title="Weekly closeout shadow-day divergence",
                lines=[
                    f"Target date: {target.isoformat()}",
                    f"Source run: {report['source_run_id']}",
                    "Findings: " + ", ".join(item["code"] for item in findings),
                    f"Report: {output_path}",
                    "Local-only warning; it is ineligible for Telegram delivery.",
                ],
                severity="WARN",
                dedup_key=f"weekly_closeout_shadow_day:{target.isoformat()}:{report['source_run_id']}",
                local_only=True,
            )
            report["warning"]["enqueued"] = True
        except Exception as exc:  # pragma: no cover
            report["warning"]["error"] = f"{type(exc).__name__}: {exc}"
    report["report_path"] = str(output_path.resolve())
    _write_json(output_path, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay the latest completed closeout from recorded artifacts only."
    )
    parser.add_argument("--workflow-root", type=Path, default=DEFAULT_WORKFLOW_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--target-date", default="")
    parser.add_argument("--source-run-dir", type=Path)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args(argv)
    try:
        report = run_shadow_day(
            workflow_root=args.workflow_root,
            output_root=args.output_root,
            target_date=date.fromisoformat(args.target_date) if args.target_date else None,
            source_run_dir=args.source_run_dir,
            json_out=args.json_out,
        )
    except (ShadowDayError, ValueError) as exc:
        print(f"Shadow day failed closed: {exc}", file=sys.stderr)
        return 2
    print(f"Shadow day report: {report['report_path']}")
    print(f"Shadow day status: {report['status']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
