from __future__ import annotations

import json
import plistlib
from pathlib import Path

import pytest

from core.integrations.google_ops_board import load_ops_board_contract
from core.ops.google_board_day_state import effective_store_states
from core.ops.waybill_shipping_obligations import required_line_scope_hash
from scripts import run_closeout_shadow_day as shadow_mod


TARGET_DATE = "2026-07-18"
RUN_ID = "20260718_190000_2026-07-18_closeout"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _matrix(headers: list[str], row: dict[str, object]) -> list[list[object]]:
    return [headers, [row.get(header, "") for header in headers]]


def _blank_effective_states() -> dict[str, dict[str, str]]:
    return {
        store: {
            "state": "PENDING",
            "postponed_to": "",
            "set_by": "",
            "set_at": "",
            "reason": "",
        }
        for store in ["11KZ", "MELVIS", "STOREB", "ACMEWEAR", "UNIVERSAL"]
    }


def _expected_order(order_id: str = "1002") -> dict[str, object]:
    line = {
        "db_row_id": "row-1002",
        "store_code": "UNIVERSAL",
        "order_id": order_id,
        "sku_key": "SKU-KEY-1",
        "sku_id": "SKU-ID-1",
        "kaspi_offer_name": "Synthetic offer",
        "kaspi_name_core": "Synthetic_core",
        "quantity": 1,
        "assigned_size": "L",
        "my_size": "",
        "final_size": "L",
    }
    return {
        "order_id": order_id,
        "store_code": "UNIVERSAL",
        "planned_shipment_date": TARGET_DATE,
        "assigned_size": "L",
        "my_size": "",
        "final_size": "L",
        "lines": [line],
        "package_count": 1,
        "stage": "ACCEPTED_PENDING_ASSEMBLY",
        "overdue": False,
    }


def _build_completed_day(tmp_path: Path) -> tuple[Path, Path, Path]:
    workflow_root = tmp_path / "workflow_runs"
    run_dir = workflow_root / TARGET_DATE / RUN_ID
    checkpoint_path = workflow_root / TARGET_DATE / "closeout_checkpoint.json"
    output_root = tmp_path / "shadow_days"
    contract = load_ops_board_contract()
    run_control_headers = contract.tabs["Run_Control"].headers
    salesraw_headers = contract.tabs["SalesRaw_Today"].headers
    ready_set_at = "2026-07-18T18:57:05+05:00"
    run_control_row = {
        "target_date": TARGET_DATE,
        "ready_for_closeout": "READY",
        "ready_set_at": ready_set_at,
    }
    salesraw_row = {
        "Status": "TODAY",
        "Date": TARGET_DATE,
        "STORE_NAME": "Universal",
        "OrderID": "1002",
        "MY_SIZE": "L",
        "_db_row_id": "row-1002",
    }
    _write_json(
        checkpoint_path,
        {
            "target_date": TARGET_DATE,
            "store_day_states": {
                "schema_version": 1,
                "stores": {
                    "UNIVERSAL": {
                        "state": "AUTO_SENT",
                        "postponed_to": "",
                        "set_by": "run_google_ops_board_closeout",
                        "set_at": "2026-07-18T19:09:00+05:00",
                        "reason": "delivery_send stage confirmed",
                    }
                },
            },
        },
    )
    _write_json(
        run_dir / "closeout_report.json",
        {
            "ok": True,
            "mode": "apply",
            "target_date": TARGET_DATE,
            "run_id": RUN_ID,
            "completed_at": "2026-07-18T19:10:00+05:00",
            "checkpoint_path": str(checkpoint_path),
            "expected_closeout_order_count": 1,
        },
    )
    _write_json(
        run_dir / "run_control_snapshot.json",
        {
            "target_date": TARGET_DATE,
            "headers": run_control_headers,
            "matrix": _matrix(run_control_headers, run_control_row),
            "rows": [run_control_row],
        },
    )
    _write_json(
        run_dir / "salesraw_snapshot.json",
        {
            "target_date": TARGET_DATE,
            "headers": salesraw_headers,
            "matrix": _matrix(salesraw_headers, salesraw_row),
            "rows": [salesraw_row],
        },
    )
    _write_json(
        run_dir / "api_active_order_ids_by_store.json",
        {
            "target_date": TARGET_DATE,
            "lookback_days": 5,
            "api_since_days": 14,
            "counts_by_store": {"UNIVERSAL": 2},
            "stores": {"UNIVERSAL": ["1001", "1002"]},
        },
    )
    _write_json(
        run_dir / "shipping_obligation_reconciliation.json",
        {
            "ok": True,
            "target_date": TARGET_DATE,
            "request_identity": {
                "target_date": TARGET_DATE,
                "ready_set_at": ready_set_at,
            },
            "issues": [],
            "active_order_ids_by_store": {"UNIVERSAL": ["1001"]},
            "uncertainty_waiver_ids_by_store": {"UNIVERSAL": ["1001"]},
        },
    )
    _write_json(
        run_dir / "prepacked_exclusion_report.json",
        {
            "target_date": TARGET_DATE,
            "applied": True,
            "decision_id": "SYNTHETIC-EXCLUSION",
            "preserve_physical_handover_obligation": True,
            "counts_before": {"UNIVERSAL": 2},
            "counts_after": {"UNIVERSAL": 1},
            "declared_exclusion_count": 1,
            "excluded_active_count": 1,
            "excluded_active_ids_by_store": {"UNIVERSAL": ["1001"]},
            "inactive_declared_ids_by_store": {},
        },
    )
    _write_json(
        run_dir / "store_day_state_report.json",
        {
            "schema_version": 1,
            "target_date": TARGET_DATE,
            "section_present": False,
            "applied": False,
            "effective_store_states": _blank_effective_states(),
            "excluded_ids_by_store": {},
            "counts_before": {"UNIVERSAL": 1},
            "counts_after": {"UNIVERSAL": 1},
        },
    )
    order = _expected_order()
    line_scope_hash = required_line_scope_hash(order["lines"])
    _write_json(
        run_dir / "expected_closeout_orders.json",
        {
            "schema_version": 3,
            "ok": True,
            "target_date": TARGET_DATE,
            "request_identity": {
                "target_date": TARGET_DATE,
                "ready_set_at": ready_set_at,
            },
            "source": "synthetic completed day",
            "expected_order_ids": ["1002"],
            "overdue_order_ids": [],
            "orders": [order],
            "line_scope_hash": line_scope_hash,
            "counts": {
                "orders": 1,
                "order_lines": 1,
                "overdue_orders": 0,
            },
            "counts_by_store": {"UNIVERSAL": 1},
            "counts_by_stage": {"ACCEPTED_PENDING_ASSEMBLY": 1},
        },
    )
    assert effective_store_states(TARGET_DATE, checkpoint_path=checkpoint_path)[
        "UNIVERSAL"
    ]["state"] == "AUTO_SENT"
    return workflow_root, run_dir, output_root


def test_green_replay_of_synthetic_completed_day_is_silent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workflow_root, run_dir, output_root = _build_completed_day(tmp_path)
    alerts: list[dict] = []
    monkeypatch.setattr(
        shadow_mod,
        "enqueue_alert",
        lambda **kwargs: alerts.append(kwargs) or False,
    )

    report = shadow_mod.run_shadow_day(
        workflow_root=workflow_root,
        output_root=output_root,
    )

    assert report["ok"] is True
    assert report["status"] == "GREEN"
    assert report["divergence"] is False
    assert report["source_run_dir"] == str(run_dir.resolve())
    assert report["scope"]["after_day_state"] == {"UNIVERSAL": ["1002"]}
    assert report["day_state"]["checkpoint_rewind"] == {
        "rewound_to_scope_time": True,
        "explicit_store_states": {},
    }
    assert report["expected_orders"]["expected_order_ids"] == ["1002"]
    assert report["safety"]["live_api_gets_performed"] is False
    assert report["warning"]["required"] is False
    assert alerts == []
    persisted = json.loads(
        (output_root / TARGET_DATE / "shadow_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert persisted["status"] == "GREEN"


def test_divergence_detection_enqueues_one_held_warn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workflow_root, run_dir, output_root = _build_completed_day(tmp_path)
    expected_path = run_dir / "expected_closeout_orders.json"
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    expected["line_scope_hash"] = "0" * 64
    _write_json(expected_path, expected)
    alerts: list[dict] = []
    monkeypatch.setattr(
        shadow_mod,
        "enqueue_alert",
        lambda **kwargs: alerts.append(kwargs) or False,
    )

    report = shadow_mod.run_shadow_day(
        workflow_root=workflow_root,
        output_root=output_root,
    )

    assert report["ok"] is False
    assert report["status"] == "WARN"
    assert {item["code"] for item in report["findings"]} == {
        "expected_line_scope_hash_diverged"
    }
    assert len(alerts) == 1
    assert alerts[0]["severity"] == "WARN"
    assert alerts[0]["local_only"] is True
    assert report["warning"] == {
        "required": True,
        "enqueued": True,
        "local_only": True,
        "held": False,
        "error": "",
    }


@pytest.mark.parametrize(
    ("env_name", "finding_code"),
    [
        (
            shadow_mod.SIMULATE_OBLIGATION_DETAIL_ERROR_ENV,
            "obligation_reconciliation_not_green",
        ),
        (
            shadow_mod.SIMULATE_EXCLUSION_DECISION_MISSING_ENV,
            "exclusion_application_diverged",
        ),
    ],
)
def test_fault_injection_paths_fail_visible_and_report_only(
    env_name: str,
    finding_code: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workflow_root, _run_dir, output_root = _build_completed_day(tmp_path)
    monkeypatch.setenv(env_name, "1")
    alerts: list[dict] = []
    monkeypatch.setattr(
        shadow_mod,
        "enqueue_alert",
        lambda **kwargs: alerts.append(kwargs) or False,
    )

    report = shadow_mod.run_shadow_day(
        workflow_root=workflow_root,
        output_root=output_root,
    )

    assert report["ok"] is False
    assert report["fault_injections"][
        "obligation_detail_error"
        if env_name == shadow_mod.SIMULATE_OBLIGATION_DETAIL_ERROR_ENV
        else "exclusion_decision_missing"
    ] is True
    assert finding_code in {item["code"] for item in report["findings"]}
    assert len(alerts) == 1
    assert alerts[0]["local_only"] is True
    assert report["safety"]["telegram_send_performed"] is False


def test_no_live_state_or_source_artifact_is_touched(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workflow_root, run_dir, output_root = _build_completed_day(tmp_path)
    live_root = tmp_path / "runtime" / "state"
    live_sentinel = live_root / "waybill_shipping_obligations.json"
    live_sentinel.parent.mkdir(parents=True)
    live_sentinel.write_bytes(b"live-state-must-not-be-read-or-written\n")
    live_before = live_sentinel.read_bytes()
    source_before = {
        path: path.read_bytes()
        for path in sorted(run_dir.glob("*.json"))
    }
    original_read_text = Path.read_text

    def _guarded_read_text(path: Path, *args, **kwargs):
        if path.resolve().is_relative_to(live_root.resolve()):
            raise AssertionError(f"live runtime state read attempted: {path}")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(shadow_mod, "LIVE_RUNTIME_STATE_ROOT", live_root)
    monkeypatch.setattr(Path, "read_text", _guarded_read_text)
    monkeypatch.setattr(
        shadow_mod,
        "enqueue_alert",
        lambda **_kwargs: pytest.fail("silent-green replay must not use outbox"),
    )

    report = shadow_mod.run_shadow_day(
        workflow_root=workflow_root,
        output_root=output_root,
    )

    assert report["ok"] is True
    assert report["safety"]["live_runtime_state_input_read"] is False
    assert report["obligations"]["state_copy_is_under_temp_root"] is True
    assert live_sentinel.read_bytes() == live_before
    assert {
        path: path.read_bytes()
        for path in sorted(run_dir.glob("*.json"))
    } == source_before
    assert sorted(output_root.rglob("*")) == [
        output_root / TARGET_DATE,
        output_root / TARGET_DATE / "shadow_report.json",
    ]


def test_candidate_plist_is_sunday_0500_and_not_activated() -> None:
    project_root = Path(__file__).resolve().parents[1]
    plist_path = project_root / "config" / "com.example.closeout-shadow-day.plist"
    payload = plistlib.loads(plist_path.read_bytes())
    runtime = json.loads(
        (project_root / "config" / "daily_shipping_runtime.json").read_text(
            encoding="utf-8"
        )
    )
    registration = runtime["observability"]["closeout_shadow_day"]

    assert payload["Label"] == "com.example.closeout-shadow-day"
    assert payload["StartCalendarInterval"] == {
        "Weekday": 1,
        "Hour": 5,
        "Minute": 0,
    }
    assert payload["RunAtLoad"] is False
    assert payload["KeepAlive"] is False
    assert payload["ProgramArguments"] == [
        str(project_root / ".venv" / "bin" / "python"),
        str(project_root / "scripts" / "run_closeout_shadow_day.py"),
    ]
    assert registration["candidate_plist"] == str(plist_path.relative_to(project_root))
    assert registration["activation_state"] == "candidate_not_installed"
