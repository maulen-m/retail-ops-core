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


STAGE_ORDER = (
    "size_writeback",
    "shipping",
    "download_waybills",
    "build_waybills",
    "delivery_send",
    "shipped_truth_sync",
)


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


def _resolve_delivery_pin(
    *,
    closeout: dict[str, Any],
    checkpoint: dict[str, Any] | None,
) -> dict[str, Any]:
    report_pin = closeout.get("pinned_delivery_artifacts")
    checkpoint_pin = checkpoint.get("delivery_artifacts") if isinstance(checkpoint, dict) else None
    if isinstance(checkpoint, dict):
        if not isinstance(checkpoint_pin, dict) or not checkpoint_pin:
            raise CloseoutEvidenceError("checkpoint delivery artifacts are missing")
        if isinstance(report_pin, dict):
            _require_equal(
                report_pin,
                checkpoint_pin,
                label="report/checkpoint pinned delivery artifacts",
            )
        elif report_pin is not None:
            raise CloseoutEvidenceError("report pinned delivery artifacts must be an object")
        return dict(checkpoint_pin)
    if not isinstance(report_pin, dict) or not report_pin:
        raise CloseoutEvidenceError("pinned delivery artifacts are missing")
    return dict(report_pin)


def _verify_resumed_checkpoint_evidence(
    *,
    closeout: dict[str, Any],
    checkpoint: dict[str, Any],
    checkpoint_path: Path,
    run_dir: Path,
    resumed: tuple[str, ...],
    steps: dict[str, dict[str, Any]],
) -> None:
    evidence_path_text = _clean(closeout.get("resumed_checkpoint_evidence_path"))
    evidence_sha = _clean(closeout.get("resumed_checkpoint_evidence_sha256")).lower()
    future_provenance = any(
        isinstance(steps.get(stage), dict)
        and isinstance(steps[stage].get("checkpoint_source"), dict)
        for stage in resumed
    )
    if not evidence_path_text and not evidence_sha:
        if future_provenance:
            raise CloseoutEvidenceError("resumed checkpoint evidence is missing")
        return
    if not evidence_path_text or len(evidence_sha) != 64:
        raise CloseoutEvidenceError("resumed checkpoint evidence pin is incomplete")
    evidence_path = _regular_file(
        Path(evidence_path_text),
        label="resumed checkpoint evidence",
    )
    _require_equal(
        evidence_path,
        (run_dir / "resumed_checkpoint_evidence.json").resolve(),
        label="resumed checkpoint evidence path",
    )
    if _sha256(evidence_path) != evidence_sha:
        raise CloseoutEvidenceError("resumed checkpoint evidence SHA-256 mismatch")
    evidence = _load_object(evidence_path, label="resumed checkpoint evidence")
    _require_equal(evidence.get("schema_version"), 1, label="resumed evidence schema")
    _require_equal(
        _clean(evidence.get("target_date")),
        _clean(checkpoint.get("target_date")),
        label="resumed evidence target date",
    )
    _require_equal(
        _clean(evidence.get("execution_mode")),
        "apply",
        label="resumed evidence execution mode",
    )
    _require_equal(
        Path(_clean(evidence.get("checkpoint_path"))).expanduser().resolve(),
        checkpoint_path,
        label="resumed evidence checkpoint path",
    )
    checkpoint_sha = _clean(evidence.get("checkpoint_sha256")).lower()
    if len(checkpoint_sha) != 64:
        raise CloseoutEvidenceError("resumed evidence checkpoint SHA-256 is invalid")
    _require_equal(
        evidence.get("resumed_stages"),
        list(resumed),
        label="resumed evidence stage prefix",
    )
    checkpoint_stages = checkpoint.get("stages") or {}
    expected_stage_sources = {
        stage: dict(checkpoint_stages.get(stage) or {}) for stage in resumed
    }
    _require_equal(
        evidence.get("stage_sources"),
        expected_stage_sources,
        label="resumed evidence stage sources",
    )
    _require_equal(
        evidence.get("required_orders"),
        dict(checkpoint.get("required_orders") or {}),
        label="resumed evidence required-orders pin",
    )
    _require_equal(
        evidence.get("delivery_artifacts"),
        dict(checkpoint.get("delivery_artifacts") or {}),
        label="resumed evidence delivery pin",
    )
    _require_equal(
        _clean(evidence.get("run_control_resume_fingerprint")),
        _clean(checkpoint.get("run_control_resume_fingerprint")),
        label="resumed evidence Run_Control fingerprint",
    )


def _resolve_stage_evidence(
    *,
    closeout: dict[str, Any],
    run_dir: Path,
    workflow_root: Path,
    target: str,
) -> tuple[dict[str, Any] | None, dict[str, Path], dict[str, str]]:
    """Resolve each stage to its exact current or checkpoint source run.

    Resumed stages must be one contiguous prefix and must be backed by the
    canonical day checkpoint.  No latest/glob discovery is allowed.
    """

    raw_resumed = closeout.get("resumed_stages") or []
    if not isinstance(raw_resumed, list) or any(not isinstance(item, str) for item in raw_resumed):
        raise CloseoutEvidenceError("resumed stages must be a string list")
    resumed = tuple(_clean(item) for item in raw_resumed)
    if resumed != STAGE_ORDER[: len(resumed)]:
        raise CloseoutEvidenceError("resumed stages are not a contiguous stage prefix")
    if bool(closeout.get("resumed_from_checkpoint")) != bool(resumed):
        raise CloseoutEvidenceError("resumed checkpoint marker disagrees with resumed stages")

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

    checkpoint: dict[str, Any] | None = None
    checkpoint_stages: dict[str, Any] = {}
    if resumed:
        expected_checkpoint_path = (workflow_root / target / "closeout_checkpoint.json").resolve()
        checkpoint_path = _regular_file(
            Path(_clean(closeout.get("checkpoint_path"))),
            label="canonical closeout checkpoint",
        )
        _require_equal(
            checkpoint_path,
            expected_checkpoint_path,
            label="canonical closeout checkpoint path",
        )
        checkpoint = _load_object(checkpoint_path, label="canonical closeout checkpoint")
        _require_equal(_clean(checkpoint.get("target_date")), target, label="checkpoint target date")
        _require_equal(_clean(checkpoint.get("execution_mode")), "apply", label="checkpoint execution mode")
        checkpoint_stages = checkpoint.get("stages") or {}
        if not isinstance(checkpoint_stages, dict):
            raise CloseoutEvidenceError("checkpoint stages are missing")
        _verify_resumed_checkpoint_evidence(
            closeout=closeout,
            checkpoint=checkpoint,
            checkpoint_path=checkpoint_path,
            run_dir=run_dir,
            resumed=resumed,
            steps=steps,
        )

    stage_paths: dict[str, Path] = {}
    step_hashes: dict[str, str] = {}
    for name in STAGE_ORDER:
        item = steps.get(name)
        if (
            not isinstance(item, dict)
            or item.get("ok") is not True
            or _integer(item.get("returncode"), label=f"{name} return code") != 0
        ):
            raise CloseoutEvidenceError(
                f"required closeout stage is missing or non-green: {name}"
            )
        inherited = name in resumed
        if bool(item.get("from_checkpoint")) != inherited:
            raise CloseoutEvidenceError(
                f"stage checkpoint provenance disagrees with resumed prefix: {name}"
            )
        if inherited:
            state = checkpoint_stages.get(name) if isinstance(checkpoint_stages, dict) else None
            if not isinstance(state, dict):
                raise CloseoutEvidenceError(f"checkpoint stage evidence is missing: {name}")
            if _clean(state.get("status")) != "ok" or _clean(
                state.get("execution_mode")
            ) != "apply":
                raise CloseoutEvidenceError(f"checkpoint stage is non-green: {name}")
            source_run_id = _clean(state.get("run_id"))
            if not source_run_id:
                raise CloseoutEvidenceError(f"checkpoint stage run_id is missing: {name}")
            expected_source_dir = (workflow_root / target / source_run_id).resolve()
            source_dir = Path(_clean(state.get("run_dir"))).expanduser().resolve()
            _require_equal(source_dir, expected_source_dir, label=f"{name} source run directory")
            step_path = _regular_file(
                Path(_clean(state.get("step_report_path"))),
                label=f"{name} checkpoint step report",
            )
            _require_equal(
                step_path,
                (source_dir / f"step_{name}.json").resolve(),
                label=f"{name} checkpoint step path",
            )
        else:
            source_dir = run_dir.resolve()
            step_path = _regular_file(
                source_dir / f"step_{name}.json",
                label=f"{name} step report",
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
        stage_paths[name] = source_dir
        step_hashes[name] = _sha256(step_path)
    return checkpoint, stage_paths, step_hashes


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
    workflow_root: Path,
    target: str,
    expected_order_count: int,
) -> dict[str, Any]:
    if closeout.get("ready") is not True:
        raise CloseoutEvidenceError("closeout was not finalized from READY state")
    halt_gate = closeout.get("halt_barrier_gate")
    if not isinstance(halt_gate, dict) or halt_gate.get("blocked") is not False:
        raise CloseoutEvidenceError("closeout halt barrier was not clear")

    checkpoint, stage_dirs, step_hashes = _resolve_stage_evidence(
        closeout=closeout,
        run_dir=run_dir,
        workflow_root=workflow_root,
        target=target,
    )

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
        stage_dirs["shipping"] / "shipping_report.json", label="shipping report"
    )
    shipping = _load_object(shipping_path, label="shipping report")
    required_count = _integer(
        shipping.get("required_count"), label="shipping required count"
    )
    shipped_count = _integer(shipping.get("shipped"), label="shipping shipped count")
    satisfied_before = _integer(
        shipping.get("required_satisfied_before")
        if shipping.get("required_satisfied_before") is not None
        else shipping.get("satisfied_count"),
        label="shipping previously satisfied count",
    )
    remaining_pending = _integer(
        shipping.get("remaining_pending")
        if shipping.get("remaining_pending") is not None
        else shipping.get("pending_count"),
        label="shipping remaining pending",
    )
    selection_status = _clean(shipping.get("selection_status"))
    observed_stages = shipping.get("observed_stages") or {}
    legacy_already_assembled = (
        selection_status == "PINNED_REQUIRED_ORDERS_ALREADY_ASSEMBLED"
        and isinstance(observed_stages, dict)
        and len(observed_stages) == required_count
        and all(_clean(value) == "ASSEMBLED_PENDING_HANDOVER" for value in observed_stages.values())
    )
    remaining_overdue_pending = (
        _integer(
            shipping.get("remaining_overdue_pending"),
            label="shipping remaining overdue pending",
        )
        if shipping.get("remaining_overdue_pending") is not None
        else (0 if legacy_already_assembled else -1)
    )
    if (
        _clean(shipping.get("target_date")) != target
        or required_count != expected_order_count
        or shipped_count + satisfied_before != required_count
        or remaining_pending != 0
        or remaining_overdue_pending != 0
        or list(shipping.get("errors") or [])
        or _clean(shipping.get("health_code")).lower() != "ok"
        or _integer(
            shipping.get("health_exit_code"), label="shipping health exit code"
        )
        != 0
        or selection_status
        not in {"PINNED_REQUIRED_ORDERS", "PINNED_REQUIRED_ORDERS_ALREADY_ASSEMBLED"}
    ):
        raise CloseoutEvidenceError(
            "shipping report does not prove all required orders with zero pending"
        )

    truth_path = _regular_file(
        stage_dirs["shipped_truth_sync"] / "shipped_truth_sync_report.json",
        label="shipped-truth sync report",
    )
    truth = _load_object(truth_path, label="shipped-truth sync report")
    if truth.get("ok") is not True or _clean(truth.get("target_date")) != target:
        raise CloseoutEvidenceError("shipped-truth sync report is not green")
    return {
        "required_stage_count": len(STAGE_ORDER),
        "required_stage_report_sha256": step_hashes,
        "resumed_stage_count": len(closeout.get("resumed_stages") or []),
        "checkpoint_path": _clean(closeout.get("checkpoint_path")) if checkpoint else "",
        "stage_source_run_dirs": {name: str(path) for name, path in stage_dirs.items()},
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
    checkpoint: dict[str, Any] | None = None
    if closeout.get("resumed_stages"):
        checkpoint_path = _regular_file(
            Path(_clean(closeout.get("checkpoint_path"))),
            label="canonical closeout checkpoint",
        )
        expected_checkpoint_path = (workflow_root / target_date.isoformat() / "closeout_checkpoint.json").resolve()
        _require_equal(checkpoint_path, expected_checkpoint_path, label="canonical closeout checkpoint path")
        checkpoint = _load_object(checkpoint_path, label="canonical closeout checkpoint")
    pinned = _resolve_delivery_pin(closeout=closeout, checkpoint=checkpoint)

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
        workflow_root=workflow_root,
        target=target_date.isoformat(),
        expected_order_count=expected_order_count,
    )
    expected_orders_path = _regular_file(
        Path(_clean(closeout.get("expected_closeout_orders_path"))),
        label="closeout expected-orders artifact",
    )
    _require_equal(
        Path(_clean(pinned.get("expected_orders_path"))).expanduser().resolve(),
        expected_orders_path,
        label="pinned expected-orders path",
    )
    expected_orders_sha = _clean(pinned.get("expected_orders_sha256")).lower()
    if len(expected_orders_sha) != 64 or _sha256(expected_orders_path) != expected_orders_sha:
        raise CloseoutEvidenceError("pinned expected-orders SHA-256 mismatch")
    if isinstance(checkpoint, dict):
        required_orders = checkpoint.get("required_orders") or {}
        if not isinstance(required_orders, dict):
            raise CloseoutEvidenceError("checkpoint required-orders pin is missing")
        _require_equal(
            Path(_clean(required_orders.get("path"))).expanduser().resolve(),
            expected_orders_path,
            label="checkpoint expected-orders path",
        )
        _require_equal(
            _clean(required_orders.get("sha256")).lower(),
            expected_orders_sha,
            label="checkpoint expected-orders SHA-256",
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

    delivery_source_dir = Path(
        stage_evidence["stage_source_run_dirs"]["delivery_send"]
    )
    delivery_report_path = _regular_file(
        delivery_source_dir / "delivery_send_report.json", label="delivery send report"
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
