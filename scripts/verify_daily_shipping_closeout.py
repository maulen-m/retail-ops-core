#!/usr/bin/env python3
"""Verify a daily-shipping closeout from its pinned local artifacts.

The verifier is read-only and emits aggregates, paths, and hashes only. A
non-zero-order closeout is GREEN only when the pinned send manifest still
matches its SHA-256 and batch hash and the existing Telegram ledger recomputes
to fully confirmed. A zero-order closeout needs its own hashed apply marker and
empty expected-orders artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import sys
from datetime import date
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.waybill_delivery_completion import delivery_completion_state  # noqa: E402


class CloseoutEvidenceError(RuntimeError):
    """The supplied closeout does not prove terminal daily shipping."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _regular_file(path: Path, *, label: str) -> Path:
    expanded = path.expanduser()
    try:
        metadata = expanded.lstat()
    except FileNotFoundError as exc:
        raise CloseoutEvidenceError(f"{label} does not exist: {expanded}") from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise CloseoutEvidenceError(f"{label} must not be a symlink: {expanded}")
    if not stat.S_ISREG(metadata.st_mode):
        raise CloseoutEvidenceError(f"{label} must be a regular file: {expanded}")
    return expanded.resolve()


def _load_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CloseoutEvidenceError(f"{label} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise CloseoutEvidenceError(f"{label} must be a JSON object")
    return payload


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _integer(value: Any, *, label: str) -> int:
    if isinstance(value, bool):
        raise CloseoutEvidenceError(f"{label} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise CloseoutEvidenceError(f"{label} must be an integer") from exc
    if parsed < 0:
        raise CloseoutEvidenceError(f"{label} must not be negative")
    return parsed


def _require_equal(actual: Any, expected: Any, *, label: str) -> None:
    if actual != expected:
        raise CloseoutEvidenceError(
            f"{label} mismatch: expected {expected!r}, observed {actual!r}"
        )


def _verify_zero_order(
    *,
    closeout: dict[str, Any],
    run_dir: Path,
    target: str,
    run_id: str,
) -> dict[str, Any]:
    if _integer(
        closeout.get("expected_closeout_order_count"),
        label="expected closeout order count",
    ) != 0:
        raise CloseoutEvidenceError(
            "zero-order closeout must have expected closeout order count 0"
        )
    marker_path = _regular_file(
        Path(_clean(closeout.get("zero_order_completion_path"))),
        label="zero-order completion marker",
    )
    expected_marker = (run_dir / "zero_order_completion.json").resolve()
    _require_equal(marker_path, expected_marker, label="zero-order marker path")
    marker = _load_object(marker_path, label="zero-order completion marker")
    if (
        marker.get("completed") is not True
        or _clean(marker.get("mode")) != "apply"
    ):
        raise CloseoutEvidenceError("zero-order marker is not a completed apply marker")
    _require_equal(_clean(marker.get("target_date")), target, label="zero-order target date")
    _require_equal(_clean(marker.get("run_id")), run_id, label="zero-order run_id")
    if _integer(marker.get("required_order_count"), label="required order count") != 0:
        raise CloseoutEvidenceError("zero-order marker required order count must be 0")

    expected_path = _regular_file(
        Path(_clean(marker.get("required_orders_path"))),
        label="zero-order expected-orders artifact",
    )
    report_expected_path = _clean(closeout.get("expected_closeout_orders_path"))
    if report_expected_path:
        _require_equal(
            expected_path,
            Path(report_expected_path).expanduser().resolve(),
            label="zero-order expected-orders path",
        )
    if not _is_relative_to(expected_path, run_dir):
        raise CloseoutEvidenceError(
            "zero-order expected-orders artifact must remain inside the closeout run"
        )
    expected_sha = _clean(marker.get("required_orders_sha256")).lower()
    if len(expected_sha) != 64 or _sha256(expected_path) != expected_sha:
        raise CloseoutEvidenceError("zero-order required orders SHA-256 mismatch")
    expected = _load_object(expected_path, label="zero-order expected-orders artifact")
    _require_equal(_clean(expected.get("target_date")), target, label="expected-orders target date")
    counts = expected.get("counts") if isinstance(expected.get("counts"), dict) else {}
    if (
        _integer(counts.get("orders"), label="expected-orders count") != 0
        or list(expected.get("expected_order_ids") or [])
        or list(expected.get("orders") or [])
    ):
        raise CloseoutEvidenceError("zero-order expected-orders artifact is not empty")
    marker_identity = marker.get("request_identity") or {}
    if not isinstance(marker_identity, dict) or _clean(
        marker_identity.get("target_date")
    ) != target:
        raise CloseoutEvidenceError("zero-order request identity is not bound to target date")
    return {
        "completion_kind": "zero_order_noop",
        "manifest_count": 0,
        "confirmed_count": 0,
        "pending_count": 0,
        "zero_order_marker_path": str(marker_path),
        "zero_order_marker_sha256": _sha256(marker_path),
        "expected_orders_path": str(expected_path),
        "expected_orders_sha256": expected_sha,
    }


def _verify_nonzero_stage_artifacts(
    *,
    closeout: dict[str, Any],
    run_dir: Path,
    target: str,
    expected_order_count: int,
) -> dict[str, Any]:
    if closeout.get("ready") is not True:
        raise CloseoutEvidenceError("closeout was not finalized from READY state")
    halt_gate = closeout.get("halt_barrier_gate")
    if not isinstance(halt_gate, dict) or halt_gate.get("blocked") is not False:
        raise CloseoutEvidenceError("closeout halt barrier was not clear")

    required_stages = (
        "size_writeback",
        "shipping",
        "download_waybills",
        "build_waybills",
        "delivery_send",
        "shipped_truth_sync",
    )
    raw_steps = closeout.get("steps")
    if not isinstance(raw_steps, list):
        raise CloseoutEvidenceError("closeout stage evidence is missing")
    steps: dict[str, dict[str, Any]] = {}
    for item in raw_steps:
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("name"))
        if name in steps:
            raise CloseoutEvidenceError(f"duplicate closeout stage evidence: {name}")
        if name:
            steps[name] = item
    step_hashes: dict[str, str] = {}
    for name in required_stages:
        item = steps.get(name)
        if (
            not isinstance(item, dict)
            or item.get("ok") is not True
            or _integer(item.get("returncode"), label=f"{name} return code") != 0
        ):
            raise CloseoutEvidenceError(
                f"required closeout stage is missing or non-green: {name}"
            )
        step_path = _regular_file(
            run_dir / f"step_{name}.json", label=f"{name} step report"
        )
        persisted = _load_object(step_path, label=f"{name} step report")
        if (
            _clean(persisted.get("name")) != name
            or persisted.get("ok") is not True
            or _integer(
                persisted.get("returncode"), label=f"persisted {name} return code"
            )
            != 0
        ):
            raise CloseoutEvidenceError(f"persisted closeout stage is non-green: {name}")
        step_hashes[name] = _sha256(step_path)

    expected_gate_path = _regular_file(
        Path(_clean(closeout.get("expected_order_manifest_gate_path"))),
        label="expected-order manifest gate",
    )
    _require_equal(
        expected_gate_path,
        (run_dir / "expected_order_manifest_gate.json").resolve(),
        label="expected-order manifest gate path",
    )
    expected_gate = _load_object(
        expected_gate_path, label="expected-order manifest gate"
    )
    if (
        closeout.get("expected_order_manifest_gate_ok") is not True
        or expected_gate.get("ok") is not True
        or _clean(expected_gate.get("target_date")) != target
        or _integer(
            expected_gate.get("manifest_count"),
            label="expected-order manifest count",
        )
        != expected_order_count
    ):
        raise CloseoutEvidenceError("expected-order manifest gate is not green")

    shipping_path = _regular_file(
        run_dir / "shipping_report.json", label="shipping report"
    )
    shipping = _load_object(shipping_path, label="shipping report")
    required_count = _integer(
        shipping.get("required_count"), label="shipping required count"
    )
    shipped_count = _integer(shipping.get("shipped"), label="shipping shipped count")
    satisfied_before = _integer(
        shipping.get("required_satisfied_before"),
        label="shipping previously satisfied count",
    )
    if (
        _clean(shipping.get("target_date")) != target
        or required_count != expected_order_count
        or shipped_count + satisfied_before != required_count
        or _integer(
            shipping.get("remaining_pending"), label="shipping remaining pending"
        )
        != 0
        or _integer(
            shipping.get("remaining_overdue_pending"),
            label="shipping remaining overdue pending",
        )
        != 0
        or list(shipping.get("errors") or [])
        or _clean(shipping.get("health_code")).lower() != "ok"
        or _integer(
            shipping.get("health_exit_code"), label="shipping health exit code"
        )
        != 0
        or _clean(shipping.get("selection_status")) != "PINNED_REQUIRED_ORDERS"
    ):
        raise CloseoutEvidenceError(
            "shipping report does not prove all required orders with zero pending"
        )

    truth_path = _regular_file(
        run_dir / "shipped_truth_sync_report.json",
        label="shipped-truth sync report",
    )
    truth = _load_object(truth_path, label="shipped-truth sync report")
    if truth.get("ok") is not True or _clean(truth.get("target_date")) != target:
        raise CloseoutEvidenceError("shipped-truth sync report is not green")
    return {
        "required_stage_count": len(required_stages),
        "required_stage_report_sha256": step_hashes,
        "expected_order_count": expected_order_count,
        "shipping_newly_shipped_count": shipped_count,
        "shipping_previously_satisfied_count": satisfied_before,
        "shipping_report_path": str(shipping_path),
        "shipping_report_sha256": _sha256(shipping_path),
        "expected_order_gate_path": str(expected_gate_path),
        "expected_order_gate_sha256": _sha256(expected_gate_path),
        "shipped_truth_sync_report_path": str(truth_path),
        "shipped_truth_sync_report_sha256": _sha256(truth_path),
    }


def _verify_telegram_delivery(
    *,
    closeout: dict[str, Any],
    project_root: Path,
    run_dir: Path,
    workflow_root: Path,
    target_date: date,
    run_id: str,
) -> dict[str, Any]:
    closeout_verification = closeout.get("delivery_completion_verification")
    if not isinstance(closeout_verification, dict):
        raise CloseoutEvidenceError("closeout delivery verification is missing")
    pinned = closeout.get("pinned_delivery_artifacts")
    if not isinstance(pinned, dict):
        raise CloseoutEvidenceError("pinned delivery artifacts are missing")

    today_root = (
        project_root / "excel_ui" / "Kaspi_orders" / "Today"
    ).resolve()
    manifest_path = _regular_file(
        Path(_clean(pinned.get("manifest_path"))), label="pinned send manifest"
    )
    if (
        manifest_path.name != "send_batch_manifest.json"
        or not _is_relative_to(manifest_path, today_root / "MERGED" / "SEND")
    ):
        raise CloseoutEvidenceError(
            "pinned send manifest is outside the live Today/MERGED/SEND root"
        )
    expected_manifest_sha = _clean(pinned.get("manifest_sha256")).lower()
    if len(expected_manifest_sha) != 64 or _sha256(manifest_path) != expected_manifest_sha:
        raise CloseoutEvidenceError("pinned manifest SHA-256 mismatch")

    pinned_ledger_path = _regular_file(
        Path(_clean(pinned.get("ledger_path"))), label="pinned delivery ledger"
    )
    allowed_pinned_ledgers = {
        (manifest_path.parent / "send_ledger.json").resolve(),
        (manifest_path.parent / "telegram_send_ledger.json").resolve(),
    }
    if pinned_ledger_path not in allowed_pinned_ledgers:
        raise CloseoutEvidenceError(
            "pinned delivery ledger path is outside the manifest batch root"
        )
    telegram_ledger_path = _regular_file(
        manifest_path.parent / "telegram_send_ledger.json",
        label="authoritative Telegram ledger",
    )

    manifest = _load_object(manifest_path, label="pinned send manifest")
    _require_equal(
        _clean(manifest.get("target_date")),
        target_date.isoformat(),
        label="manifest target date",
    )
    _require_equal(
        _clean(manifest.get("batch_hash")),
        _clean(pinned.get("batch_hash")),
        label="pinned batch hash",
    )
    expected_order_count = _integer(
        closeout.get("expected_closeout_order_count"),
        label="expected closeout order count",
    )
    if expected_order_count < 1:
        raise CloseoutEvidenceError(
            "non-zero-order closeout must have at least one expected order"
        )
    stage_evidence = _verify_nonzero_stage_artifacts(
        closeout=closeout,
        run_dir=run_dir,
        target=target_date.isoformat(),
        expected_order_count=expected_order_count,
    )
    manifest_counts = manifest.get("counts") if isinstance(manifest.get("counts"), dict) else {}
    _require_equal(
        _integer(manifest_counts.get("orders"), label="manifest order count"),
        expected_order_count,
        label="manifest order count",
    )
    request_identity = manifest.get("request_identity") or {}
    pinned_identity = pinned.get("request_identity") or {}
    if not isinstance(request_identity, dict) or not isinstance(pinned_identity, dict):
        raise CloseoutEvidenceError("delivery request identity is missing")
    _require_equal(request_identity, pinned_identity, label="pinned request identity")
    if _clean(request_identity.get("target_date")) != target_date.isoformat() or not _clean(
        request_identity.get("ready_set_at")
    ):
        raise CloseoutEvidenceError("delivery request identity is not target-date bound")

    state = delivery_completion_state(
        today_folder=today_root,
        target_date=target_date,
        run_root=workflow_root,
        run_id=run_id,
        manifest_path=manifest_path,
        expected_manifest_sha256=expected_manifest_sha,
    )
    if (
        state.get("completed") is not True
        or _clean(state.get("channel")) != "telegram"
        or _clean(state.get("status")) != "TELEGRAM_CONFIRMED"
    ):
        raise CloseoutEvidenceError(
            "Telegram ledger is not complete: "
            f"{_clean(state.get('status')) or 'UNKNOWN'}"
        )
    manifest_count = _integer(state.get("manifest_count"), label="ledger manifest count")
    confirmed_count = _integer(state.get("confirmed_count"), label="ledger confirmed count")
    pending_count = _integer(state.get("pending_count"), label="ledger pending count")
    if manifest_count < 1 or confirmed_count != manifest_count or pending_count != 0:
        raise CloseoutEvidenceError("Telegram ledger counts are not fully confirmed")
    _require_equal(
        Path(_clean(state.get("manifest_path"))).resolve(),
        manifest_path,
        label="recomputed manifest path",
    )
    _require_equal(
        Path(_clean(state.get("ledger_path"))).resolve(),
        telegram_ledger_path,
        label="recomputed ledger path",
    )

    if (
        closeout_verification.get("completed") is not True
        or _clean(closeout_verification.get("status")) != "TELEGRAM_CONFIRMED"
        or _integer(
            closeout_verification.get("manifest_count"),
            label="closeout manifest count",
        )
        != manifest_count
        or _integer(
            closeout_verification.get("confirmed_count"),
            label="closeout confirmed count",
        )
        != confirmed_count
    ):
        raise CloseoutEvidenceError(
            "closeout delivery verification disagrees with the recomputed ledger"
        )

    delivery_report_path = _regular_file(
        run_dir / "delivery_send_report.json", label="delivery send report"
    )
    delivery_report = _load_object(delivery_report_path, label="delivery send report")
    delivery = delivery_report.get("delivery_completion")
    if (
        delivery_report.get("ok") is not True
        or _clean(delivery_report.get("expected_target_date")) != target_date.isoformat()
        or _clean(delivery_report.get("delivery_channel")) != "telegram"
        or not isinstance(delivery, dict)
        or delivery.get("completed") is not True
        or _clean(delivery.get("status")) != "TELEGRAM_CONFIRMED"
        or _integer(delivery.get("manifest_count"), label="delivery report manifest count")
        != manifest_count
        or _integer(delivery.get("confirmed_count"), label="delivery report confirmed count")
        != confirmed_count
        or _integer(delivery.get("pending_count"), label="delivery report pending count")
        != 0
    ):
        raise CloseoutEvidenceError(
            "delivery send report disagrees with the recomputed Telegram ledger"
        )
    _require_equal(
        Path(_clean(delivery.get("manifest_path"))).resolve(),
        manifest_path,
        label="delivery report manifest path",
    )
    _require_equal(
        Path(_clean(delivery.get("ledger_path"))).resolve(),
        telegram_ledger_path,
        label="delivery report ledger path",
    )
    return {
        "completion_kind": "telegram_ledger",
        **stage_evidence,
        "manifest_count": manifest_count,
        "confirmed_count": confirmed_count,
        "pending_count": pending_count,
        "manifest_path": str(manifest_path),
        "manifest_sha256": expected_manifest_sha,
        "pinned_delivery_ledger_path": str(pinned_ledger_path),
        "pinned_delivery_ledger_sha256": _sha256(pinned_ledger_path),
        "ledger_path": str(telegram_ledger_path),
        "ledger_sha256": _sha256(telegram_ledger_path),
        "delivery_report_path": str(delivery_report_path),
        "delivery_report_sha256": _sha256(delivery_report_path),
    }


def verify_closeout_evidence(
    *,
    closeout_report_path: Path,
    expected_date: date,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    """Return a secret/PII-free GREEN report or raise on incomplete evidence."""

    root = Path(project_root).expanduser().resolve()
    workflow_root = (
        root / "exports" / "google_ops_board" / "workflow_runs"
    ).resolve()
    closeout_path = _regular_file(
        Path(closeout_report_path), label="closeout report"
    )
    closeout = _load_object(closeout_path, label="closeout report")
    target = expected_date.isoformat()
    run_id = _clean(closeout.get("run_id"))
    if not run_id or run_id != closeout_path.parent.name:
        raise CloseoutEvidenceError("closeout run_id does not match its run directory")
    expected_path = workflow_root / target / run_id / "closeout_report.json"
    if closeout_path != expected_path.resolve():
        raise CloseoutEvidenceError(
            "closeout report is not at the expected workflow path for target date"
        )
    if (
        closeout.get("ok") is not True
        or _clean(closeout.get("mode")) != "apply"
    ):
        raise CloseoutEvidenceError("closeout is not a successful apply report")
    _require_equal(_clean(closeout.get("target_date")), target, label="closeout target date")

    if closeout.get("zero_order_noop") is True:
        completion = _verify_zero_order(
            closeout=closeout,
            run_dir=closeout_path.parent,
            target=target,
            run_id=run_id,
        )
    else:
        completion = _verify_telegram_delivery(
            closeout=closeout,
            project_root=root,
            run_dir=closeout_path.parent,
            workflow_root=workflow_root,
            target_date=expected_date,
            run_id=run_id,
        )
    return {
        "schema_version": 1,
        "ok": True,
        "gate": "GREEN",
        "target_date": target,
        "run_id": run_id,
        "closeout_report_path": str(closeout_path),
        "closeout_report_sha256": _sha256(closeout_path),
        **completion,
        "credential_values_read": False,
        "credential_values_exposed": False,
        "customer_data_exposed": False,
        "external_writes_performed": 0,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify a daily-shipping closeout from pinned local evidence."
    )
    parser.add_argument("--closeout-report", type=Path, required=True)
    parser.add_argument("--expected-date", type=date.fromisoformat, required=True)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = verify_closeout_evidence(
            closeout_report_path=args.closeout_report,
            expected_date=args.expected_date,
            project_root=args.project_root,
        )
    except CloseoutEvidenceError as exc:
        report = {
            "schema_version": 1,
            "ok": False,
            "gate": "RED",
            "error": str(exc),
            "credential_values_read": False,
            "credential_values_exposed": False,
            "customer_data_exposed": False,
            "external_writes_performed": 0,
        }
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        stream = sys.stderr
        print(f"Gate: {report['gate']}", file=stream)
        if not report.get("ok"):
            print(f"ERROR: {report['error']}", file=stream)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
