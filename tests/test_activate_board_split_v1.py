from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from core.integrations.google_ops_board import (
    OWNERSHIP_MODE_LEGACY_V3,
    OWNERSHIP_MODE_PARTIAL,
    OWNERSHIP_MODE_SPLIT_V1,
    contract_for_ownership_mode,
    load_ops_board_contract,
)
from scripts import activate_board_split_v1 as activation
from scripts.google_ops_board_automation_common import GoogleOpsBoardAutomationLock


def _green_runtime() -> dict[str, Any]:
    return {
        "ok": True,
        "gate": "GREEN",
        "returncode": 0,
        "errors": [],
        "warnings": [],
    }


def _column_index(a1_cell: str) -> int:
    letters = "".join(character for character in a1_cell if character.isalpha())
    value = 0
    for character in letters:
        value = value * 26 + (ord(character.upper()) - ord("A") + 1)
    return value - 1


class FakeGoogleOpsBoardClient:
    def __init__(self, header_rows: dict[str, list[str]]) -> None:
        self.header_rows = deepcopy(header_rows)
        self.header_reads = 0
        self.update_calls: list[list[dict[str, Any]]] = []

    def get_header_rows(self, tab_names: list[str]) -> dict[str, list[str]]:
        self.header_reads += 1
        return {
            tab_name: list(self.header_rows.get(tab_name) or [])
            for tab_name in tab_names
        }

    def update_cells(self, updates: list[dict[str, Any]]) -> None:
        self.update_calls.append(deepcopy(updates))
        for update in updates:
            tab_name, a1_cell = str(update["range"]).split("!", 1)
            assert a1_cell.endswith("1")
            column_index = _column_index(a1_cell)
            headers = self.header_rows[tab_name]
            assert column_index == len(headers), "activation must append after the current trailing header"
            headers.append(str(update["value"]))


def _legacy_headers() -> dict[str, list[str]]:
    contract = load_ops_board_contract()
    legacy = contract_for_ownership_mode(contract, OWNERSHIP_MODE_LEGACY_V3)
    return {
        "SalesRaw_Today": legacy.tabs["SalesRaw_Today"].headers,
        "Run_Control": legacy.tabs["Run_Control"].headers,
    }


def test_fake_client_apply_appends_exact_five_trailing_headers_and_verifies_split(
    tmp_path: Path,
) -> None:
    contract = load_ops_board_contract()
    client = FakeGoogleOpsBoardClient(_legacy_headers())

    report = activation.execute_activation(
        client=client,
        contract=contract,
        apply=True,
        environ={activation.ACTIVATION_ENV_GATE: "1"},
        lock_path=tmp_path / "google_ops_board_closeout.lock",
        runtime_validator=_green_runtime,
    )

    assert report["ok"] is True
    assert report["write_applied"] is True
    assert report["ownership_layout_before"]["ownership_mode"] == OWNERSHIP_MODE_LEGACY_V3
    assert report["ownership_layout_after"]["ownership_mode"] == OWNERSHIP_MODE_SPLIT_V1
    assert report["header_readback_exact"] is True
    assert report["runtime_validation"]["gate"] == "GREEN"
    assert len(client.update_calls) == 1
    assert client.update_calls[0] == [
        {
            "range": "SalesRaw_Today!R1",
            "value": "AUTO_SIZE_SUGGESTION",
            "field": "AUTO_SIZE_SUGGESTION",
        },
        {
            "range": "Run_Control!I1",
            "value": "employee_ready_observed_at",
            "field": "employee_ready_observed_at",
        },
        {
            "range": "Run_Control!J1",
            "value": "auto_ready_for_closeout",
            "field": "auto_ready_for_closeout",
        },
        {
            "range": "Run_Control!K1",
            "value": "auto_ready_set_by",
            "field": "auto_ready_set_by",
        },
        {
            "range": "Run_Control!L1",
            "value": "auto_ready_set_at",
            "field": "auto_ready_set_at",
        },
    ]
    assert client.header_rows["SalesRaw_Today"] == contract.tabs["SalesRaw_Today"].headers
    assert client.header_rows["Run_Control"] == contract.tabs["Run_Control"].headers


def test_dry_run_default_plans_without_write_and_proves_rollback(tmp_path: Path) -> None:
    client = FakeGoogleOpsBoardClient(_legacy_headers())

    report = activation.execute_activation(
        client=client,
        contract=load_ops_board_contract(),
        apply=False,
        environ={},
        lock_path=tmp_path / "google_ops_board_closeout.lock",
        runtime_validator=_green_runtime,
    )

    assert report["ok"] is True
    assert report["mode"] == "dry_run"
    assert report["write_applied"] is False
    assert report["planned_ownership_layout_after"]["ownership_mode"] == OWNERSHIP_MODE_SPLIT_V1
    assert report["rollback"]["absence_semantics_proven"] is True
    assert report["rollback"]["resulting_ownership_mode"] == OWNERSHIP_MODE_LEGACY_V3
    assert client.update_calls == []
    assert client.header_reads == 1


def test_partial_layout_refuses_without_write_and_reports_existing_columns(
    tmp_path: Path,
) -> None:
    headers = _legacy_headers()
    headers["SalesRaw_Today"].append("AUTO_SIZE_SUGGESTION")
    client = FakeGoogleOpsBoardClient(headers)

    report = activation.execute_activation(
        client=client,
        contract=load_ops_board_contract(),
        apply=False,
        environ={},
        lock_path=tmp_path / "google_ops_board_closeout.lock",
        runtime_validator=_green_runtime,
    )

    assert report["ok"] is False
    assert report["failure_stage"] == "existing_v4_columns"
    assert report["ownership_layout_before"]["ownership_mode"] == OWNERSHIP_MODE_PARTIAL
    assert report["existing_v4_columns"] == {
        "SalesRaw_Today": ["AUTO_SIZE_SUGGESTION"],
        "Run_Control": [],
    }
    assert report["write_applied"] is False
    assert client.update_calls == []


def test_complete_split_layout_refuses_reactivation(tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    client = FakeGoogleOpsBoardClient(
        {
            "SalesRaw_Today": contract.tabs["SalesRaw_Today"].headers,
            "Run_Control": contract.tabs["Run_Control"].headers,
        }
    )

    report = activation.execute_activation(
        client=client,
        contract=contract,
        apply=True,
        environ={activation.ACTIVATION_ENV_GATE: "1"},
        lock_path=tmp_path / "google_ops_board_closeout.lock",
        runtime_validator=_green_runtime,
    )

    assert report["ok"] is False
    assert report["failure_stage"] == "existing_v4_columns"
    assert report["ownership_layout_before"]["ownership_mode"] == OWNERSHIP_MODE_SPLIT_V1
    assert report["write_applied"] is False
    assert client.update_calls == []


def test_shared_automation_lock_refuses_when_closeout_or_publish_running(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "google_ops_board_closeout.lock"
    client = FakeGoogleOpsBoardClient(_legacy_headers())

    with GoogleOpsBoardAutomationLock(lock_path):
        report = activation.execute_activation(
            client=client,
            contract=load_ops_board_contract(),
            apply=False,
            environ={},
            lock_path=lock_path,
            runtime_validator=_green_runtime,
        )

    assert report["ok"] is False
    assert report["failure_stage"] == "automation_lock"
    assert report["lock_path"] == str(lock_path)
    assert report["write_applied"] is False
    assert client.header_reads == 0
    assert client.update_calls == []


def test_apply_gate_refuses_before_lock_or_client_access(tmp_path: Path) -> None:
    client = FakeGoogleOpsBoardClient(_legacy_headers())

    report = activation.execute_activation(
        client=client,
        contract=load_ops_board_contract(),
        apply=True,
        environ={},
        lock_path=tmp_path / "google_ops_board_closeout.lock",
        runtime_validator=lambda: (_ for _ in ()).throw(
            AssertionError("runtime validator must not run before the apply gate")
        ),
    )

    assert report["ok"] is False
    assert report["failure_stage"] == "apply_gate"
    assert report["required_env_gate"] == activation.ACTIVATION_ENV_GATE
    assert report["write_applied"] is False
    assert client.header_reads == 0
    assert client.update_calls == []


def test_runtime_red_refuses_before_board_read_or_write(tmp_path: Path) -> None:
    client = FakeGoogleOpsBoardClient(_legacy_headers())

    report = activation.execute_activation(
        client=client,
        contract=load_ops_board_contract(),
        apply=True,
        environ={activation.ACTIVATION_ENV_GATE: "1"},
        lock_path=tmp_path / "google_ops_board_closeout.lock",
        runtime_validator=lambda: {
            "ok": False,
            "gate": "RED",
            "returncode": 1,
            "errors": ["runtime drift"],
        },
    )

    assert report["ok"] is False
    assert report["failure_stage"] == "daily_shipping_runtime"
    assert report["write_applied"] is False
    assert client.header_reads == 0
    assert client.update_calls == []
