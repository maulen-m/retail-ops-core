from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from core.integrations.google_ops_board import load_ops_board_contract
from core.ops.waybill_prepacked_exclusions import (
    DEFAULT_PREPACKED_EXCLUSION_PATH,
    apply_prepacked_exclusion,
    load_validated_prepacked_exclusion,
)
from core.ops.waybill_shipping_obligations import reconcile_shipping_obligations
from scripts import google_ops_board_automation_common as automation_common
from scripts import run_google_ops_board_closeout as closeout_mod
from scripts import send_waybills_telegram as telegram_mod
from scripts import validate_google_closeout_expected_orders as expected_orders_mod
from scripts.send_waybills_whatsapp import SOURCE_MERGED
from tests import test_google_ops_board_closeout as base_closeout_tests
from tests import test_send_waybills_telegram as base_telegram_tests


TARGET_DATE = date(2026, 7, 18)
READY_SET_AT = "2026-07-18T18:57:05+05:00"
RESIDUAL_ORDER_ID = "NEW-0718-001"


@pytest.fixture(autouse=True)
def _isolate_adversarial_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(closeout_mod, "DEFAULT_RUN_ROOT", tmp_path / "workflow_runs")
    monkeypatch.setattr(
        closeout_mod,
        "DEFAULT_SHIPPING_OBLIGATION_LEDGER_PATH",
        tmp_path / "runtime" / "state" / "waybill_shipping_obligations.json",
    )
    monkeypatch.setattr(
        expected_orders_mod,
        "load_order_name_core_overrides",
        lambda: {
            "1001": "Offer",
            RESIDUAL_ORDER_ID: "Offer",
        },
    )
    monkeypatch.setattr(
        closeout_mod,
        "evaluate_closeout_halt_barrier",
        lambda **_kwargs: {
            "blocked": False,
            "reason": "NO_HALT_BARRIER",
            "request_halted": False,
            "barrier": {},
        },
    )
    monkeypatch.setattr(
        telegram_mod,
        "CLOSEOUT_HALT_BARRIER_PATH",
        tmp_path / "telegram_closeout_halt_barrier.json",
    )
    monkeypatch.setattr(
        telegram_mod,
        "arm_passive_handover_watch",
        lambda **_kwargs: {"armed": False},
        raising=False,
    )


def _serialized_ids(values: dict[str, set[str]]) -> dict[str, list[str]]:
    return {store: sorted(order_ids) for store, order_ids in sorted(values.items())}


def _real_decision() -> dict[str, object]:
    decision = load_validated_prepacked_exclusion(target_date=TARGET_DATE)
    assert decision is not None
    return decision


def _armed_ids(decision: dict[str, object] | None = None) -> list[str]:
    payload = decision or _real_decision()
    return sorted(payload["excluded_order_ids_by_store"]["UNIVERSAL"])


def _prior_obligation_ledger(order_ids: list[str]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "updated_at": "2026-07-17T22:00:00+05:00",
        "request_identity": {
            "target_date": "2026-07-17",
            "ready_set_at": "2026-07-17T18:57:05+05:00",
        },
        "entries": {
            f"UNIVERSAL:{order_id}": {
                "store_code": "UNIVERSAL",
                "order_id": order_id,
                "status": "unresolved",
                "first_seen_target_date": "2026-07-17",
                "last_seen_target_date": "2026-07-17",
                "last_stage": "ASSEMBLED_PENDING_HANDOVER",
            }
            for order_id in order_ids
        },
    }


def _in_delivery_detail(order_id: str) -> dict[str, object]:
    return {
        "order": {
            "attributes": {
                "code": order_id,
                "state": "KASPI_DELIVERY",
                "status": "TRANSMITTED_TO_COURIER",
                "courierTransmissionDate": 1784304000000,
            }
        }
    }


def _exercise_rehearsal_scenario(
    *,
    scenario: str,
    active_carried_ids: set[str],
    handed_over_ids: set[str],
    residual_ids: set[str],
) -> dict[str, object]:
    decision = _real_decision()
    all_carried = set(_armed_ids(decision))
    assert active_carried_ids | handed_over_ids == all_carried
    assert not active_carried_ids & handed_over_ids

    prior = _prior_obligation_ledger(sorted(all_carried))
    selector = {"UNIVERSAL": set(active_carried_ids) | set(residual_ids)}
    reconciliation_current = closeout_mod._existing_open_orders_present_in_current(
        prior,
        selector,
    )
    detail_results = {
        f"UNIVERSAL:{order_id}": _in_delivery_detail(order_id)
        for order_id in handed_over_ids
    }
    obligation_result = reconcile_shipping_obligations(
        prior_ledger=prior,
        current_active_order_ids_by_store=reconciliation_current,
        detail_results=detail_results,
        target_date=TARGET_DATE,
        ready_set_at=READY_SET_AT,
        now=datetime(2026, 7, 18, 18, 58, tzinfo=ZoneInfo("Asia/Almaty")),
    )
    required_before = closeout_mod._union_order_ids_by_store(
        selector,
        {
            store: set(order_ids)
            for store, order_ids in obligation_result[
                "active_order_ids_by_store"
            ].items()
        },
    )
    exclusion = apply_prepacked_exclusion(required_before, decision)
    required_after = {
        store: set(order_ids)
        for store, order_ids in exclusion["required_ids_by_store"].items()
    }
    statuses = {
        order_id: obligation_result["ledger"]["entries"][
            f"UNIVERSAL:{order_id}"
        ]["status"]
        for order_id in sorted(all_carried)
    }
    discharge_reasons = {
        order_id: obligation_result["ledger"]["entries"][
            f"UNIVERSAL:{order_id}"
        ].get("discharge_reason", "")
        for order_id in sorted(all_carried)
    }
    return {
        "scenario": scenario,
        "selector_active_ids_by_store": _serialized_ids(selector),
        "reconciliation_active_ids_by_store": _serialized_ids(
            reconciliation_current
        ),
        "obligation_reconciliation_ok": obligation_result["ok"],
        "obligation_issues": obligation_result["issues"],
        "obligation_statuses": statuses,
        "obligation_discharge_reasons": discharge_reasons,
        "required_ids_before_exclusion": _serialized_ids(required_before),
        "required_ids_after_exclusion": _serialized_ids(required_after),
        "download_scope": _serialized_ids(required_after),
        "build_scope": _serialized_ids(required_after),
        "send_scope": _serialized_ids(required_after),
        "excluded_active_ids_by_store": _serialized_ids(
            exclusion["excluded_active_ids_by_store"]
        ),
        "inactive_declared_ids_by_store": _serialized_ids(
            exclusion["inactive_declared_ids_by_store"]
        ),
        "excluded_active_count": exclusion["excluded_active_count"],
        "declared_exclusion_count": exclusion["declared_exclusion_count"],
        "count_assertion": exclusion["count_assertion"],
        "zero_order_noop": sum(len(ids) for ids in required_after.values()) == 0,
    }


def build_rehearsal_evidence() -> dict[str, object]:
    decision = _real_decision()
    carried = set(_armed_ids(decision))
    active_mixed = set(sorted(carried)[:3])
    source_manifest = Path(str(decision["source_manifest_path"]))
    source_ledger = Path(str(decision["source_telegram_ledger_path"]))
    scenarios = {
        "assembled_all_day": _exercise_rehearsal_scenario(
            scenario="ASSEMBLED-ALL-DAY",
            active_carried_ids=carried,
            handed_over_ids=set(),
            residual_ids={RESIDUAL_ORDER_ID},
        ),
        "handed_over": _exercise_rehearsal_scenario(
            scenario="HANDED-OVER",
            active_carried_ids=set(),
            handed_over_ids=carried,
            residual_ids={RESIDUAL_ORDER_ID},
        ),
        "mixed": _exercise_rehearsal_scenario(
            scenario="MIXED-3-ASSEMBLED-6-HANDED-OVER",
            active_carried_ids=active_mixed,
            handed_over_ids=carried - active_mixed,
            residual_ids={RESIDUAL_ORDER_ID},
        ),
        "zero_new_orders": _exercise_rehearsal_scenario(
            scenario="ZERO-NEW-ORDERS",
            active_carried_ids=carried,
            handed_over_ids=set(),
            residual_ids=set(),
        ),
    }
    return {
        "schema_version": 1,
        "target_date": TARGET_DATE.isoformat(),
        "execution_mode": "offline_unit_harness_read_only_runtime_state",
        "external_writes_performed": False,
        "runtime_state_mutated": False,
        "harness": "tests/test_closeout_adversarial_matrix.py",
        "decision": {
            "path": str(DEFAULT_PREPACKED_EXCLUSION_PATH.resolve()),
            "sha256": hashlib.sha256(
                DEFAULT_PREPACKED_EXCLUSION_PATH.read_bytes()
            ).hexdigest(),
            "decision_id": decision["decision_id"],
            "authority": decision["authority"],
            "target_date": decision["target_date"],
            "preserve_physical_handover_obligation": decision[
                "preserve_physical_handover_obligation"
            ],
            "declared_order_count": decision["excluded_order_count"],
            "declared_ids_by_store": _serialized_ids(
                decision["excluded_order_ids_by_store"]
            ),
            "expected_count_keys_present": any(
                key in decision
                for key in (
                    "expected_required_counts_by_store",
                    "expected_required_order_count",
                )
            ),
            "source_manifest_path": str(source_manifest),
            "source_manifest_sha256_verified": hashlib.sha256(
                source_manifest.read_bytes()
            ).hexdigest()
            == decision["source_manifest_sha256"],
            "source_telegram_ledger_path": str(source_ledger),
            "source_telegram_ledger_sha256_verified": hashlib.sha256(
                source_ledger.read_bytes()
            ).hexdigest()
            == decision["source_telegram_ledger_sha256"],
        },
        "scenarios": scenarios,
        "guarantees": {
            "assembled_carried_orders_excluded_from_downstream_scope": (
                scenarios["assembled_all_day"]["required_ids_after_exclusion"]
                == {"UNIVERSAL": [RESIDUAL_ORDER_ID]}
            ),
            "assembled_carried_obligations_remain_open": all(
                status == "unresolved"
                for status in scenarios["assembled_all_day"][
                    "obligation_statuses"
                ].values()
            ),
            "handed_over_obligations_discharge": all(
                status == "discharged"
                for status in scenarios["handed_over"]["obligation_statuses"].values()
            ),
            "handed_over_exclusion_is_inactive_declared": (
                len(
                    scenarios["handed_over"]["inactive_declared_ids_by_store"]
                    .get("UNIVERSAL", [])
                )
                == 9
            ),
            "mixed_six_discharged_three_excluded": (
                sum(
                    status == "discharged"
                    for status in scenarios["mixed"]["obligation_statuses"].values()
                )
                == 6
                and scenarios["mixed"]["excluded_active_count"] == 3
            ),
            "loader_count_assertion_is_skipped_absent_expected_counts": all(
                scenario["count_assertion"]
                == "skipped_absent_expected_counts"
                for scenario in scenarios.values()
            ),
            "zero_new_orders_uses_noop_scope": (
                scenarios["zero_new_orders"]["zero_order_noop"] is True
                and scenarios["zero_new_orders"]["send_scope"]
                == {"UNIVERSAL": []}
            ),
        },
    }


def _salesraw_row(target_date: str, order_id: str) -> list[str]:
    return [
        "TODAY",
        target_date,
        "Universal",
        "",
        "",
        "1",
        "Nike",
        order_id,
        "L",
        "L",
        "Offer",
        "SKU-1",
        "1",
        f"{order_id}|{target_date}|SKU-1|Offer|1",
        "DEFAULT",
        "LOW",
    ]


def _board_client(
    *, target_date: str, salesraw_rows: list[list[str]]
) -> base_closeout_tests._FakeClient:
    contract = load_ops_board_contract()
    return base_closeout_tests._FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                [target_date, "READY", "adil", READY_SET_AT, "", "", "", ""],
            ],
            "SalesRaw_Today": [
                contract.tabs["SalesRaw_Today"].headers,
                *salesraw_rows,
            ],
        }
    )


def _patch_local_closeout_inputs(
    monkeypatch: pytest.MonkeyPatch,
    *,
    client: base_closeout_tests._FakeClient,
    active_ids_by_store: dict[str, set[str]],
    store_context: dict[str, object] | None = None,
) -> None:
    monkeypatch.setattr(
        closeout_mod.GoogleOpsBoardClient,
        "from_service_account_file",
        lambda *_args, **_kwargs: client,
    )
    monkeypatch.setattr(
        closeout_mod,
        "fetch_api_active_order_ids_by_store",
        lambda **_kwargs: copy.deepcopy(active_ids_by_store),
    )
    monkeypatch.setattr(
        closeout_mod,
        "build_store_context_report",
        lambda **_kwargs: store_context
        or {
            "ok": True,
            "active_store_codes": sorted(active_ids_by_store) or ["UNIVERSAL"],
            "stores": [],
            "failure_count": 0,
        },
    )


def _main_args(
    *,
    db_path: Path,
    creds: Path,
    run_root: Path,
    report_path: Path,
    target_date: str,
    obligation_ledger_path: Path | None = None,
) -> list[str]:
    args = [
        "--db-path",
        str(db_path),
        "--service-account-json",
        str(creds),
        "--spreadsheet-id",
        "sheet-id",
        "--target-date",
        target_date,
        "--run-root",
        str(run_root),
        "--json-out",
        str(report_path),
    ]
    if obligation_ledger_path is not None:
        args.extend(["--obligation-ledger-path", str(obligation_ledger_path)])
    return args


def test_real_armed_decision_loads_and_uses_optional_count_semantics() -> None:
    evidence = build_rehearsal_evidence()
    decision = evidence["decision"]

    assert decision["target_date"] == "2026-07-18"
    assert decision["declared_order_count"] == 9
    assert decision["expected_count_keys_present"] is False
    assert decision["source_manifest_sha256_verified"] is True
    assert decision["source_telegram_ledger_sha256_verified"] is True
    assert evidence["guarantees"][
        "loader_count_assertion_is_skipped_absent_expected_counts"
    ] is True


def test_rehearsal_assembled_handed_over_and_mixed_scopes() -> None:
    evidence = build_rehearsal_evidence()
    guarantees = evidence["guarantees"]

    assert guarantees["assembled_carried_orders_excluded_from_downstream_scope"]
    assert guarantees["assembled_carried_obligations_remain_open"]
    assert guarantees["handed_over_obligations_discharge"]
    assert guarantees["handed_over_exclusion_is_inactive_declared"]
    assert guarantees["mixed_six_discharged_three_excluded"]
    assert evidence["scenarios"]["mixed"]["obligation_reconciliation_ok"] is True


def test_rehearsal_zero_new_orders_takes_local_noop_with_real_decision(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    decision = _real_decision()
    carried = set(_armed_ids(decision))
    db_path = tmp_path / "app.db"
    base_closeout_tests._make_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM fact_orders_kaspi")
    creds = tmp_path / "svc.json"
    creds.write_text("{}", encoding="utf-8")
    client = _board_client(target_date="2026-07-18", salesraw_rows=[])
    ledger_path = tmp_path / "waybill_shipping_obligations.json"
    ledger_path.write_text(
        json.dumps(_prior_obligation_ledger(sorted(carried))), encoding="utf-8"
    )
    calls: list[str] = []

    def _fake_run_command(*, name, command, env, report_path):
        calls.append(name)
        if "--output-json" in command:
            Path(command[command.index("--output-json") + 1]).write_text(
                json.dumps(
                    {"db_backup_path": None, "updates_applied": 0, "updates_count": 0}
                ),
                encoding="utf-8",
            )
        step = {
            "name": name,
            "command": command,
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "ok": True,
        }
        report_path.write_text(json.dumps(step), encoding="utf-8")
        return step

    _patch_local_closeout_inputs(
        monkeypatch,
        client=client,
        active_ids_by_store={"UNIVERSAL": carried},
    )
    monkeypatch.setattr(closeout_mod, "_run_command", _fake_run_command)
    report_path = tmp_path / "closeout_report.json"
    rc = closeout_mod.main(
        _main_args(
            db_path=db_path,
            creds=creds,
            run_root=tmp_path / "runs",
            report_path=report_path,
            target_date="2026-07-18",
            obligation_ledger_path=ledger_path,
        )
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert rc == 0
    assert report["ok"] is True
    assert report["zero_order_noop"] is True
    assert report["expected_closeout_order_count"] == 0
    assert calls == ["size_writeback"]
    assert report["steps"][-1]["name"] == "zero_order_noop"
    assert not any(
        step["name"] in {"shipping", "download_waybills", "build_waybills", "delivery_send"}
        for step in report["steps"]
    )
    prepacked_report = json.loads(
        Path(report["prepacked_exclusion_report_path"]).read_text(encoding="utf-8")
    )
    assert prepacked_report["excluded_active_count"] == 9


@pytest.mark.parametrize("failed_stage", closeout_mod.STAGE_ORDER)
def test_stage_boundary_timeout_resume_skips_completed_without_double_effects(
    failed_stage: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / f"run_{failed_stage}"
    run_dir.mkdir()
    run_control = {
        "target_date": "2026-07-18",
        "ready_for_closeout": "READY",
        "ready_set_at": READY_SET_AT,
    }
    checkpoint = {
        "execution_mode": "apply",
        "target_date": "2026-07-18",
        "salesraw_writeback_fingerprint": closeout_mod.salesraw_writeback_fingerprint([]),
        "run_control_resume_fingerprint": closeout_mod.run_control_resume_fingerprint(
            run_control
        ),
        "stages": {},
    }
    boundary_index = closeout_mod.STAGE_ORDER.index(failed_stage)
    for stage in closeout_mod.STAGE_ORDER[:boundary_index]:
        step_path = run_dir / f"step_{stage}.json"
        step = {
            "name": stage,
            "returncode": 0,
            "stdout": f"{stage} completed once",
            "stderr": "",
            "ok": True,
        }
        step_path.write_text(json.dumps(step), encoding="utf-8")
        closeout_mod._checkpoint_stage_report(
            checkpoint=checkpoint,
            stage=stage,
            step_report=step,
            run_id="run-before-kill",
            run_dir=run_dir,
        )

    def _timeout(command, **kwargs):
        raise closeout_mod.subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(closeout_mod.subprocess, "run", _timeout)
    failed_report = closeout_mod._run_command(
        name=failed_stage,
        command=["simulated-worker", failed_stage],
        env={},
        report_path=run_dir / f"step_{failed_stage}.json",
    )
    closeout_mod._checkpoint_stage_report(
        checkpoint=checkpoint,
        stage=failed_stage,
        step_report=failed_report,
        run_id="run-before-kill",
        run_dir=run_dir,
    )
    checkpoint_path = run_dir / "closeout_checkpoint.json"
    closeout_mod._write_checkpoint(checkpoint_path, checkpoint)

    monkeypatch.setattr(
        closeout_mod,
        "_required_orders_checkpoint_valid",
        lambda *_args, **_kwargs: (True, ""),
    )
    monkeypatch.setattr(
        closeout_mod,
        "_validate_pinned_manifest",
        lambda *_args, **_kwargs: (True, ""),
    )
    monkeypatch.setattr(
        closeout_mod,
        "delivery_completion_state",
        lambda **_kwargs: {"completed": True, "status": "TELEGRAM_CONFIRMED"},
    )
    reloaded = closeout_mod._load_checkpoint(checkpoint_path)
    resumed = closeout_mod._contiguous_successful_stages(
        reloaded,
        salesraw_rows=[],
        run_control_row=run_control,
        today_folder=tmp_path / "Today",
        target_date=TARGET_DATE,
        run_root=tmp_path / "runs",
        execution_mode="apply",
    )
    resume_execution = [
        stage for stage in closeout_mod.STAGE_ORDER if stage not in resumed
    ]

    assert resumed == closeout_mod.STAGE_ORDER[:boundary_index]
    assert not set(resumed) & set(resume_execution)
    assert resume_execution[0] == failed_stage
    assert failed_report["returncode"] == 124
    assert failed_report["timed_out"] is True
    assert (run_dir / f"step_{failed_stage}.json").is_file()
    assert reloaded["stages"][failed_stage]["status"] == "failed"


def test_repeated_ready_identity_reuses_checkpoint_and_changed_identity_is_new_request(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    creds = tmp_path / "svc.json"
    db_path.write_bytes(b"db")
    creds.write_text("{}", encoding="utf-8")
    old_row = {
        "target_date": "2026-07-18",
        "ready_for_closeout": "READY",
        "ready_set_at": READY_SET_AT,
    }
    new_row = {**old_row, "ready_set_at": "2026-07-18T18:58:00+05:00"}
    checkpoint = closeout_mod._build_checkpoint_base(
        target_date=TARGET_DATE,
        db_path=db_path,
        spreadsheet_id="sheet-id",
        service_account_json=creds,
        run_control_row=old_row,
        salesraw_rows=[],
        execution_mode="apply",
    )
    checkpoint["stages"]["size_writeback"] = {"status": "ok"}

    same, same_reason, same_block = closeout_mod._rebase_checkpoint_for_ready_request(
        checkpoint=checkpoint,
        fresh_checkpoint=copy.deepcopy(checkpoint),
        run_control_row=old_row,
    )
    fresh = closeout_mod._build_checkpoint_base(
        target_date=TARGET_DATE,
        db_path=db_path,
        spreadsheet_id="sheet-id",
        service_account_json=creds,
        run_control_row=new_row,
        salesraw_rows=[],
        execution_mode="apply",
    )
    changed, changed_reason, changed_block = (
        closeout_mod._rebase_checkpoint_for_ready_request(
            checkpoint=checkpoint,
            fresh_checkpoint=fresh,
            run_control_row=new_row,
        )
    )
    attempted = copy.deepcopy(checkpoint)
    attempted["delivery_attempt"] = {"status": "started"}
    _unchanged, _reason, attempted_block = (
        closeout_mod._rebase_checkpoint_for_ready_request(
            checkpoint=attempted,
            fresh_checkpoint=fresh,
            run_control_row=new_row,
        )
    )
    visibility_path = tmp_path / "ready_identity_matrix.json"
    visibility_path.write_text(
        json.dumps(
            {
                "same_reason": same_reason,
                "changed_reason": changed_reason,
                "attempted_block": attempted_block,
            }
        ),
        encoding="utf-8",
    )

    assert same is checkpoint
    assert same_reason == "" and same_block == ""
    assert "size_writeback" in same["stages"]
    assert changed == fresh
    assert changed["stages"] == {}
    assert changed_reason == "new_ready_request_identity"
    assert changed_block == ""
    assert attempted_block.startswith(
        "checkpoint_previous_request_delivery_attempt_present:"
    )
    assert visibility_path.is_file()


def test_stale_board_cannot_hide_fresh_selector_scope_and_failure_is_visible(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    base_closeout_tests._make_db(db_path)
    base_closeout_tests._set_db_size(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                id, order_id, store_code, kaspi_article, assigned_size, sku_key,
                sku_id, kaspi_offer_name, quantity, planned_shipment_date
            ) VALUES (
                2, '2001', 'UNIVERSAL', 'ARTICLE-1', 'L', 'SKU-1',
                'SKU-1_L', 'Offer', 1, '2026-04-15'
            )
            """
        )
    creds = tmp_path / "svc.json"
    creds.write_text("{}", encoding="utf-8")
    client = _board_client(
        target_date="2026-04-15",
        salesraw_rows=[_salesraw_row("2026-04-15", "1001")],
    )
    _patch_local_closeout_inputs(
        monkeypatch,
        client=client,
        active_ids_by_store={"UNIVERSAL": {"2001"}},
    )
    monkeypatch.setattr(
        closeout_mod,
        "_run_command",
        lambda **_kwargs: pytest.fail("stale Board must fail before stage execution"),
    )
    report_path = tmp_path / "stale_board_report.json"
    rc = closeout_mod.main(
        _main_args(
            db_path=db_path,
            creds=creds,
            run_root=tmp_path / "runs",
            report_path=report_path,
            target_date="2026-04-15",
        )
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert rc == 1
    assert report["ok"] is False
    assert report["failure_stage"] == "size_writeback"
    assert "incomplete pinned SalesRaw rows" in report["failure_reason"]
    api_scope = json.loads(
        Path(report["api_active_order_ids_by_store_path"]).read_text(encoding="utf-8")
    )
    assert api_scope["stores"] == {"UNIVERSAL": ["2001"]}
    assert report_path.is_file()


def test_telegram_api_started_is_fail_closed_with_stopline_and_no_resend(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    batch_root = base_telegram_tests._write_manifest(
        tmp_path,
        [
            {
                "pdf_key": "pdf-a",
                "filename": "ambiguous.pdf",
                "order_id": "1001",
                "send_sequence": 1,
            }
        ],
    )
    manifest_path = batch_root / "send_batch_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    ledger_path = batch_root / telegram_mod.TELEGRAM_SEND_LEDGER_FILE
    ledger = telegram_mod.load_telegram_ledger(
        ledger_path, manifest, chat_id="-1001"
    )
    telegram_mod._set_entry_state(
        ledger,
        "pdf-a",
        "api_started",
        note="simulated process death after API launch",
    )
    telegram_mod.save_telegram_ledger(ledger_path, ledger)
    monkeypatch.setattr(
        telegram_mod,
        "send_document",
        lambda **_kwargs: pytest.fail("ambiguous entry must never be resent"),
    )

    report = telegram_mod.run_sender(
        today_folder=tmp_path,
        bundle_source=SOURCE_MERGED,
        expected_target_date=date(2026, 4, 21),
        token="token-1",
        chat_id="-1001",
        status_messages=False,
        send_delay=0,
        resume=True,
        manifest_path=manifest_path,
        expected_manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    )
    stopline = tmp_path / telegram_mod.TELEGRAM_SEND_STOPLINE_FILE

    assert report["ok"] is False
    assert report["halted"] is True
    assert report["halt_reason"] == "TELEGRAM_UNRESOLVED_LEDGER"
    assert report["blocked_filenames"] == ["ambiguous.pdf"]
    assert stopline.is_file()
    assert json.loads(stopline.read_text(encoding="utf-8"))["halt_reason"] == (
        "TELEGRAM_UNRESOLVED_LEDGER"
    )


def test_already_sent_new_day_scope_uses_exclusion_and_per_batch_ledger() -> None:
    decision = _real_decision()
    carried = set(_armed_ids(decision))
    result = apply_prepacked_exclusion(
        {"UNIVERSAL": carried | {RESIDUAL_ORDER_ID}}, decision
    )
    carried_id = sorted(carried)[0]
    entries = [
        {"pdf_key": "carried", "filename": "carried.pdf"},
        {"pdf_key": "new", "filename": "new.pdf"},
    ]
    ledger = {
        "entries": {
            "carried": {"state": "confirmed", "history": [{"state": "confirmed"}]},
            "new": {"state": "pending", "history": []},
        }
    }
    selected, blocked = telegram_mod._select_entries_for_telegram_send(
        entries, ledger, resume=True
    )
    visibility = {
        "excluded": _serialized_ids(result["excluded_active_ids_by_store"]),
        "selected_pdf_keys": [entry["pdf_key"] for entry in selected],
        "blocked_pdf_keys": [entry["pdf_key"] for entry in blocked],
    }

    assert result["required_ids_by_store"] == {
        "UNIVERSAL": {RESIDUAL_ORDER_ID}
    }
    assert carried_id not in result["required_ids_by_store"]["UNIVERSAL"]
    assert visibility["selected_pdf_keys"] == ["new"]
    assert visibility["blocked_pdf_keys"] == []
    assert len(visibility["excluded"]["UNIVERSAL"]) == 9


def test_exclusion_postponement_is_store_specific_and_visible() -> None:
    decision = _real_decision()
    carried = set(_armed_ids(decision))
    shared_id = sorted(carried)[0]
    result = apply_prepacked_exclusion(
        {
            "UNIVERSAL": carried | {RESIDUAL_ORDER_ID},
            "ACMEWEAR": {shared_id, "ACMEWEAR-NEW"},
        },
        decision,
    )

    assert result["required_ids_by_store"]["UNIVERSAL"] == {RESIDUAL_ORDER_ID}
    assert result["required_ids_by_store"]["ACMEWEAR"] == {
        shared_id,
        "ACMEWEAR-NEW",
    }
    assert set(result["excluded_active_ids_by_store"]) == {"UNIVERSAL"}
    assert result["counts_before"] == {"ACMEWEAR": 2, "UNIVERSAL": 10}
    assert result["counts_after"] == {"ACMEWEAR": 2, "UNIVERSAL": 1}


def test_process_restart_mid_send_sends_only_pending_entries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    batch_root = base_telegram_tests._write_manifest(
        tmp_path,
        [
            {
                "pdf_key": "pdf-a",
                "filename": "already-confirmed.pdf",
                "order_id": "1001",
                "send_sequence": 1,
            },
            {
                "pdf_key": "pdf-b",
                "filename": "still-pending.pdf",
                "order_id": "1002",
                "send_sequence": 2,
            },
        ],
    )
    manifest_path = batch_root / "send_batch_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    ledger_path = batch_root / telegram_mod.TELEGRAM_SEND_LEDGER_FILE
    ledger = telegram_mod.load_telegram_ledger(
        ledger_path, manifest, chat_id="-1001"
    )
    telegram_mod._set_entry_state(
        ledger,
        "pdf-a",
        "confirmed",
        note="confirmed before process restart",
        extra={"telegram_chat_id": "-1001", "message_id": "msg-old"},
    )
    telegram_mod.save_telegram_ledger(ledger_path, ledger)
    sent: list[str] = []

    def _send_document(**kwargs):
        sent.append(Path(kwargs["document_path"]).name)
        return {"success": True, "message_id": "msg-new", "chat_id": "-1001"}

    monkeypatch.setattr(telegram_mod, "send_document", _send_document)
    report = telegram_mod.run_sender(
        today_folder=tmp_path,
        bundle_source=SOURCE_MERGED,
        expected_target_date=date(2026, 4, 21),
        token="token-1",
        chat_id="-1001",
        status_messages=False,
        send_delay=0,
        resume=True,
        manifest_path=manifest_path,
        expected_manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    )
    final_ledger = json.loads(ledger_path.read_text(encoding="utf-8"))

    assert report["ok"] is True
    assert report["sent"] == 1
    assert report["confirmed_total"] == 2
    assert sent == ["still-pending.pdf"]
    assert final_ledger["entries"]["pdf-a"]["message_id"] == "msg-old"
    assert final_ledger["entries"]["pdf-b"]["state"] == "confirmed"


def test_midnight_rollover_keeps_july17_request_halted_and_allows_fresh_july18_ready(
    tmp_path: Path,
) -> None:
    tz = ZoneInfo("Asia/Almaty")
    barrier_path = tmp_path / "halt_barrier.json"
    automation_common.persist_closeout_halt_barrier(
        target_date=date(2026, 7, 17),
        requested_at=datetime(2026, 7, 17, 18, 0, tzinfo=tz),
        source="adversarial:/halt",
        request_key="telegram_update:17",
        path=barrier_path,
    )
    hold = automation_common.evaluate_closeout_halt_barrier(
        target_date=date(2026, 7, 17),
        run_control_row={
            "target_date": "2026-07-17",
            "ready_for_closeout": "HOLD",
            "ready_set_at": "",
        },
        now=datetime(2026, 7, 17, 18, 1, tzinfo=tz),
        path=barrier_path,
    )
    blank_new_day = automation_common.evaluate_closeout_halt_barrier(
        target_date=date(2026, 7, 18),
        run_control_row={
            "target_date": "2026-07-18",
            "ready_for_closeout": "READY",
            "ready_set_at": "",
        },
        path=barrier_path,
    )
    stamped_new_day = automation_common.evaluate_closeout_halt_barrier(
        target_date=date(2026, 7, 18),
        run_control_row={
            "target_date": "2026-07-18",
            "ready_for_closeout": "READY",
            "ready_set_at": READY_SET_AT,
        },
        request_ready_set_at=READY_SET_AT,
        path=barrier_path,
    )
    old_request = automation_common.evaluate_closeout_halt_barrier(
        target_date=date(2026, 7, 17),
        run_control_row={
            "target_date": "2026-07-17",
            "ready_for_closeout": "READY",
            "ready_set_at": "2026-07-17T17:59:00+05:00",
        },
        request_ready_set_at="2026-07-17T17:59:00+05:00",
        path=barrier_path,
    )

    assert hold["blocked"] is True
    assert hold["barrier"]["state"] == "HOLD_CONFIRMED"
    assert blank_new_day["blocked"] is True
    assert blank_new_day["allow_fresh_blank_ready"] is True
    assert stamped_new_day["blocked"] is False
    assert stamped_new_day["reason"] == "FRESH_READY_SUPERSEDES_HALT"
    assert old_request["blocked"] is True
    assert old_request["request_halted"] is True
    assert barrier_path.is_file()


def test_kaspi_detail_error_is_non_sticky_blocking_and_visible(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    base_closeout_tests._make_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM fact_orders_kaspi")
    creds = tmp_path / "svc.json"
    creds.write_text("{}", encoding="utf-8")
    client = _board_client(target_date="2026-04-15", salesraw_rows=[])
    ledger_path = tmp_path / "obligations.json"
    ledger_path.write_text(
        json.dumps(_prior_obligation_ledger(["1001"])), encoding="utf-8"
    )
    ledger_before = ledger_path.read_bytes()

    class _FailingKaspiClient:
        def __init__(self, store_code: str):
            assert store_code == "UNIVERSAL"

        def get_order(self, order_id: str):
            assert order_id == "1001"
            return SimpleNamespace(success=False, error="503 dependency unavailable", data=None)

    _patch_local_closeout_inputs(
        monkeypatch,
        client=client,
        active_ids_by_store={"UNIVERSAL": set()},
    )
    monkeypatch.setattr(closeout_mod, "KaspiAPIClient", _FailingKaspiClient)
    report_path = tmp_path / "dependency_failure_report.json"
    rc = closeout_mod.main(
        _main_args(
            db_path=db_path,
            creds=creds,
            run_root=tmp_path / "runs",
            report_path=report_path,
            target_date="2026-04-15",
            obligation_ledger_path=ledger_path,
        )
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    reconciliation_path = Path(report["shipping_obligation_reconciliation_path"])
    reconciliation = json.loads(reconciliation_path.read_text(encoding="utf-8"))

    assert rc == 1
    assert report["ok"] is False
    assert report["failure_stage"] == "shipping_obligations"
    assert report["shipping_obligation_ledger_write_suppressed"] is True
    assert ledger_path.read_bytes() == ledger_before
    assert reconciliation["ok"] is False
    assert reconciliation["issues"][0]["code"] == "obligation_api_uncertain"
    assert "503 dependency unavailable" in reconciliation["issues"][0]["detail"]
    assert reconciliation_path.is_file()
    assert report_path.is_file()


def test_partial_store_processing_never_reports_green_and_stops_downstream(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    base_closeout_tests._make_db(db_path)
    base_closeout_tests._set_db_size(db_path)
    creds = tmp_path / "svc.json"
    creds.write_text("{}", encoding="utf-8")
    client = _board_client(
        target_date="2026-04-15",
        salesraw_rows=[_salesraw_row("2026-04-15", "1001")],
    )
    calls: list[str] = []

    def _fake_run_command(*, name, command, env, report_path):
        calls.append(name)
        if name == "size_writeback":
            output_path = Path(command[command.index("--output-json") + 1])
            output_path.write_text(
                json.dumps(
                    {"db_backup_path": None, "updates_applied": 0, "updates_count": 0}
                ),
                encoding="utf-8",
            )
            returncode = 0
            stdout = json.dumps({"stores": {"UNIVERSAL": "ok"}})
        elif name == "shipping":
            returncode = 1
            stdout = json.dumps(
                {
                    "stores": {
                        "UNIVERSAL": {"ok": True, "processed": 1},
                        "STOREB": {"ok": False, "error": "dependency timeout"},
                    }
                }
            )
        else:
            pytest.fail(f"unexpected downstream stage after partial failure: {name}")
        step = {
            "name": name,
            "command": command,
            "returncode": returncode,
            "stdout": stdout,
            "stderr": "",
            "ok": returncode == 0,
        }
        report_path.write_text(json.dumps(step), encoding="utf-8")
        return step

    _patch_local_closeout_inputs(
        monkeypatch,
        client=client,
        active_ids_by_store={"UNIVERSAL": {"1001"}},
        store_context={
            "ok": True,
            "active_store_codes": ["UNIVERSAL", "STOREB"],
            "stores": [],
            "failure_count": 0,
        },
    )
    monkeypatch.setattr(closeout_mod, "_run_command", _fake_run_command)
    report_path = tmp_path / "partial_report.json"
    rc = closeout_mod.main(
        _main_args(
            db_path=db_path,
            creds=creds,
            run_root=tmp_path / "runs",
            report_path=report_path,
            target_date="2026-04-15",
        )
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    shipping_step = next(step for step in report["steps"] if step["name"] == "shipping")
    store_results = json.loads(shipping_step["stdout"])["stores"]

    assert rc == 1
    assert report["ok"] is False
    assert report["failure_stage"] == "shipping"
    assert calls == ["size_writeback", "shipping"]
    assert store_results["UNIVERSAL"]["ok"] is True
    assert store_results["STOREB"]["ok"] is False
    assert Path(shipping_step["command"][shipping_step["command"].index("--json-out") + 1]).parent.exists()
    assert (Path(report["run_dir"]) / "step_shipping.json").is_file()
    assert report_path.is_file()
