from __future__ import annotations

import json
import hashlib
import sqlite3
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_google_ops_board_closeout as closeout_mod
from core.integrations.google_ops_board import load_ops_board_contract
from core.ops.waybill_send_batch import compute_manifest_batch_hash
from core.ops.waybill_shipping_obligations import required_line_scope_hash


@pytest.fixture(autouse=True)
def _isolate_closeout_runtime_defaults(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(closeout_mod, "DEFAULT_RUN_ROOT", tmp_path / "workflow_runs")
    monkeypatch.setattr(
        closeout_mod,
        "DEFAULT_SHIPPING_OBLIGATION_LEDGER_PATH",
        tmp_path / "runtime" / "state" / "waybill_shipping_obligations.json",
    )


def _preserved_board_run(
    tmp_path: Path,
    *,
    target_date: str = "2026-07-13",
    report_ok: bool = True,
    report_mode: str = "apply",
) -> Path:
    contract = load_ops_board_contract()
    run_dir = tmp_path / "preserved_closeout"
    run_dir.mkdir()
    run_control_row = [
        target_date,
        "READY",
        "owner",
        f"{target_date}T17:00:00+05:00",
        "",
        "",
        "",
        "",
    ]
    salesraw_row = [
        "TODAY",
        target_date,
        "Universal",
        "",
        "",
        "1",
        "Nike",
        "1001",
        "L",
        "L",
        "Offer",
        "SKU-1",
        "1",
        "line",
        "DEFAULT",
        "LOW",
    ]
    (run_dir / "closeout_report.json").write_text(
        json.dumps(
            {
                "ok": report_ok,
                "mode": report_mode,
                "target_date": target_date,
                "run_id": "preserved-apply-run",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "run_control_snapshot.json").write_text(
        json.dumps(
            {
                "target_date": target_date,
                "matrix": [contract.tabs["Run_Control"].headers, run_control_row],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "salesraw_snapshot.json").write_text(
        json.dumps(
            {
                "target_date": target_date,
                "matrix": [contract.tabs["SalesRaw_Today"].headers, salesraw_row],
            }
        ),
        encoding="utf-8",
    )
    return run_dir


def test_preserved_board_client_loads_snapshots_without_online_constructor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = _preserved_board_run(tmp_path)
    monkeypatch.setattr(
        closeout_mod.GoogleOpsBoardClient,
        "from_service_account_file",
        lambda *_args, **_kwargs: pytest.fail("online board client must not be constructed"),
    )

    client, receipt = closeout_mod._load_preserved_board_client(
        run_dir, target_date=date(2026, 7, 13)
    )

    assert client.get_tab_values("Run_Control")[1][0] == "2026-07-13"
    assert client.get_tab_values("SalesRaw_Today")[1][7] == "1001"
    assert receipt["board_source_mode"] == "preserved_snapshot"
    assert receipt["source_apply_run_id"] == "preserved-apply-run"


def test_preserved_board_client_refuses_writes(tmp_path: Path) -> None:
    run_dir = _preserved_board_run(tmp_path)
    client, _receipt = closeout_mod._load_preserved_board_client(
        run_dir, target_date=date(2026, 7, 13)
    )

    with pytest.raises(RuntimeError, match="read-only"):
        client.update_tab_rows("Run_Control", [], [])


@pytest.mark.parametrize(
    ("report_ok", "report_mode", "target_date", "match"),
    [
        (False, "apply", "2026-07-13", "successful apply"),
        (True, "dry_run", "2026-07-13", "successful apply"),
        (True, "apply", "2026-07-12", "target date"),
    ],
)
def test_preserved_board_client_rejects_non_authoritative_closeout(
    tmp_path: Path,
    report_ok: bool,
    report_mode: str,
    target_date: str,
    match: str,
) -> None:
    run_dir = _preserved_board_run(
        tmp_path,
        target_date=target_date,
        report_ok=report_ok,
        report_mode=report_mode,
    )

    with pytest.raises(ValueError, match=match):
        closeout_mod._load_preserved_board_client(
            run_dir, target_date=date(2026, 7, 13)
        )


def test_preserved_board_mode_cannot_be_combined_with_apply(tmp_path: Path) -> None:
    run_dir = _preserved_board_run(tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        closeout_mod.main(
            [
                "--apply",
                "--shadow-board-run-dir",
                str(run_dir),
            ]
        )

    assert exc_info.value.code == 2


def test_shadow_mode_strips_write_gates_after_dotenv_load() -> None:
    environment = {
        "ENABLE_GOOGLE_OPS_BOARD_WRITE": "1",
        "ENABLE_KASPI_SHIP_WRITE": "1",
        closeout_mod.AUTOMATION_LOCK_HELD_ENV: "1",
        "KASPI_TOKEN_ACMEWEAR": "protected-runtime-value",
    }

    removed = closeout_mod._strip_shadow_write_gates(environment)

    assert removed == [
        closeout_mod.AUTOMATION_LOCK_HELD_ENV,
        "ENABLE_GOOGLE_OPS_BOARD_WRITE",
        "ENABLE_KASPI_SHIP_WRITE",
    ]
    assert "ENABLE_GOOGLE_OPS_BOARD_WRITE" not in environment
    assert "ENABLE_KASPI_SHIP_WRITE" not in environment
    assert closeout_mod.AUTOMATION_LOCK_HELD_ENV not in environment
    assert environment["KASPI_TOKEN_ACMEWEAR"] == "protected-runtime-value"


def test_stage_runner_enforces_named_timeout_and_persists_timeout_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_run(command, **kwargs):
        assert kwargs["timeout"] == closeout_mod.STAGE_TIMEOUT_SECONDS["telegram_delivery"]
        raise closeout_mod.subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(closeout_mod.subprocess, "run", fake_run)
    report_path = tmp_path / "step.json"

    report = closeout_mod._run_command(
        name="telegram_delivery",
        command=["sender"],
        env={},
        report_path=report_path,
    )

    assert report["returncode"] == 124
    assert report["timed_out"] is True
    assert report["timeout_seconds"] == closeout_mod.STAGE_TIMEOUT_SECONDS["telegram_delivery"]
    assert json.loads(report_path.read_text(encoding="utf-8"))["timed_out"] is True


def test_apply_custom_run_root_requires_explicit_canonical_obligation_ledger(
    tmp_path: Path,
) -> None:
    args = SimpleNamespace(
        apply=True,
        run_root=tmp_path / "other_runs",
        obligation_ledger_path=None,
    )

    with pytest.raises(ValueError, match="explicit canonical"):
        closeout_mod._resolve_shipping_obligation_ledger_path(args)


def _write_attempt_evidence(
    today_folder: Path,
    *,
    ready_set_at: str,
    state: str,
    label: str = "batch-1",
    manifest_mode: str = "valid",
) -> Path:
    batch_root = today_folder / "MERGED" / "SEND" / label
    batch_root.mkdir(parents=True, exist_ok=True)
    manifest_path = batch_root / "send_batch_manifest.json"
    if manifest_mode == "valid":
        manifest_path.write_text(
            json.dumps(
                {
                    "target_date": "2026-04-15",
                    "request_identity": {
                        "target_date": "2026-04-15",
                        "ready_set_at": ready_set_at,
                    },
                }
            ),
            encoding="utf-8",
        )
    elif manifest_mode == "corrupt":
        manifest_path.write_text("{", encoding="utf-8")
    (batch_root / "telegram_send_ledger.json").write_text(
        json.dumps(
            {
                "entries": {
                    "pdf-1": {
                        "state": state,
                        "history": [] if state == "pending" else [{"event": "api_started"}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (batch_root / "send_ledger.json").write_text(
        json.dumps(
            {
                "entries": {
                    "pdf-1": {
                        "state": "pending",
                        "history": [],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_exact_request_attempt_without_checkpoint_is_fail_closed(tmp_path: Path) -> None:
    today_folder = tmp_path / "Today"
    _write_attempt_evidence(
        today_folder,
        ready_set_at="2026-04-15T17:00:00+05:00",
        state="api_started",
    )

    ok, reason, attempts = closeout_mod._guard_request_delivery_attempt_binding(
        checkpoint={},
        completed_stages=[],
        today_folder=today_folder,
        request_identity={
            "target_date": "2026-04-15",
            "ready_set_at": "2026-04-15T17:00:00+05:00",
        },
    )

    assert ok is False
    assert reason == "delivery_pin_missing"
    assert len(attempts) == 1


def test_attempt_scan_ignores_pristine_but_keeps_same_date_different_ready_attempt(
    tmp_path: Path,
) -> None:
    today_folder = tmp_path / "Today"
    _write_attempt_evidence(
        today_folder,
        ready_set_at="2026-04-15T17:00:00+05:00",
        state="pending",
        label="pristine",
    )
    _write_attempt_evidence(
        today_folder,
        ready_set_at="2026-04-15T16:00:00+05:00",
        state="confirmed",
        label="old-request",
    )

    attempts = closeout_mod._request_delivery_attempt_evidence(
        today_folder=today_folder,
        request_identity={
            "target_date": "2026-04-15",
            "ready_set_at": "2026-04-15T17:00:00+05:00",
        },
    )

    assert len(attempts) == 1
    assert attempts[0]["ready_set_at"] == "2026-04-15T16:00:00+05:00"
    assert attempts[0]["request_identity_match"] == "false"


def test_same_date_prior_attempt_under_different_ready_blocks_new_request(
    tmp_path: Path,
) -> None:
    today_folder = tmp_path / "Today"
    _write_attempt_evidence(
        today_folder,
        ready_set_at="2026-04-15T16:00:00+05:00",
        state="confirmed",
        label="lost-checkpoint-old-ready",
    )

    ok, reason, attempts = closeout_mod._guard_request_delivery_attempt_binding(
        checkpoint={},
        completed_stages=[],
        today_folder=today_folder,
        request_identity={
            "target_date": "2026-04-15",
            "ready_set_at": "2026-04-15T17:00:00+05:00",
        },
    )

    assert ok is False
    assert reason == "same_date_prior_attempt_different_request"
    assert len(attempts) == 1


def test_orphan_attempt_ledger_blocks_when_manifest_is_corrupt(tmp_path: Path) -> None:
    today_folder = tmp_path / "Today"
    _write_attempt_evidence(
        today_folder,
        ready_set_at="2026-04-15T17:00:00+05:00",
        state="unsure",
        manifest_mode="corrupt",
    )

    attempts = closeout_mod._request_delivery_attempt_evidence(
        today_folder=today_folder,
        request_identity={
            "target_date": "2026-04-15",
            "ready_set_at": "2026-04-15T17:00:00+05:00",
        },
    )

    assert len(attempts) == 1
    assert attempts[0]["reason"].startswith("orphan_or_unreadable_manifest:")


def test_run_control_resume_fingerprint_includes_ready_set_at() -> None:
    first = closeout_mod.run_control_resume_fingerprint(
        {
            "target_date": "2026-07-11",
            "ready_for_closeout": "READY",
            "ready_set_at": "2026-07-11T17:00:00+05:00",
        }
    )
    second = closeout_mod.run_control_resume_fingerprint(
        {
            "target_date": "2026-07-11",
            "ready_for_closeout": "READY",
            "ready_set_at": "2026-07-11T17:01:00+05:00",
        }
    )

    assert first != second


def test_apply_cannot_resume_a_dry_run_checkpoint(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    service_account = tmp_path / "svc.json"
    checkpoint = {
        "execution_mode": "dry_run",
        "target_date": "2026-04-15",
        "db_path": str(db_path.resolve()),
        "spreadsheet_id": "sheet-id",
        "service_account_json": str(service_account.resolve()),
        "stages": {"shipping": {"status": "ok", "execution_mode": "dry_run"}},
    }

    ok, reason = closeout_mod._validate_checkpoint(
        checkpoint=checkpoint,
        target_date=date(2026, 4, 15),
        db_path=db_path,
        spreadsheet_id="sheet-id",
        service_account_json=service_account,
        execution_mode="apply",
    )

    assert ok is False
    assert reason == "checkpoint_execution_mode_mismatch"


def test_new_ready_request_rebases_checkpoint_without_stale_stages() -> None:
    old_row = {
        "target_date": "2026-04-15",
        "ready_for_closeout": "READY",
        "ready_set_at": "2026-04-15T17:00:00+05:00",
    }
    new_row = old_row | {"ready_set_at": "2026-04-15T18:00:00+05:00"}
    saved = {
        "execution_mode": "apply",
        "run_control_resume_fingerprint": closeout_mod.run_control_resume_fingerprint(old_row),
        "stages": {
            "size_writeback": {"status": "ok"},
            "shipping": {"status": "ok"},
            "download_waybills": {"status": "ok"},
            "build_waybills": {"status": "ok"},
        },
        "required_orders": {"path": "/old/request.json"},
    }
    fresh = {
        "execution_mode": "apply",
        "run_control_resume_fingerprint": closeout_mod.run_control_resume_fingerprint(new_row),
        "stages": {},
    }

    rebased, reason, blocker = closeout_mod._rebase_checkpoint_for_ready_request(
        checkpoint=saved,
        fresh_checkpoint=fresh,
        run_control_row=new_row,
    )

    assert blocker == ""
    assert reason == "new_ready_request_identity"
    assert rebased == fresh
    assert rebased is not fresh
    assert rebased["stages"] == {}
    assert "required_orders" not in rebased


def test_new_ready_preserves_attempt_marker_when_telegram_ledger_is_missing(
    tmp_path: Path,
) -> None:
    old_row = {
        "target_date": "2026-04-15",
        "ready_for_closeout": "READY",
        "ready_set_at": "2026-04-15T17:00:00+05:00",
    }
    new_row = old_row | {"ready_set_at": "2026-04-15T18:00:00+05:00"}
    manifest_path = tmp_path / "MERGED" / "SEND" / "batch" / "send_batch_manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps({"batch_hash": "batch-1", "entries": [{"pdf_key": "pdf-1"}]}),
        encoding="utf-8",
    )
    saved = {
        "run_control_resume_fingerprint": closeout_mod.run_control_resume_fingerprint(old_row),
        "delivery_attempt": {
            "status": "started",
            "manifest_path": str(manifest_path),
        },
        "delivery_artifacts": {"manifest_path": str(manifest_path)},
        "stages": {},
    }
    fresh = {
        "run_control_resume_fingerprint": closeout_mod.run_control_resume_fingerprint(new_row),
        "stages": {},
    }

    rebased, reason, blocker = closeout_mod._rebase_checkpoint_for_ready_request(
        checkpoint=saved,
        fresh_checkpoint=fresh,
        run_control_row=new_row,
    )

    assert rebased is saved
    assert reason == ""
    assert blocker.endswith("telegram_send_ledger_missing_after_attempt")
    assert rebased["delivery_attempt"]["status"] == "started"


def test_checkpoint_attempt_marker_with_missing_telegram_ledger_blocks_new_ready(
    tmp_path: Path,
) -> None:
    today_folder = tmp_path / "Today"
    manifest_path = _write_attempt_evidence(
        today_folder,
        ready_set_at="2026-04-15T16:00:00+05:00",
        state="pending",
        label="old-ready-marker",
    )
    (manifest_path.parent / "telegram_send_ledger.json").unlink()
    checkpoint = {
        "delivery_attempt": {
            "status": "started",
            "manifest_path": str(manifest_path),
        },
        "delivery_artifacts": {"manifest_path": str(manifest_path)},
        "stages": {},
    }

    ok, reason, attempts = closeout_mod._guard_request_delivery_attempt_binding(
        checkpoint=checkpoint,
        completed_stages=[],
        today_folder=today_folder,
        request_identity={
            "target_date": "2026-04-15",
            "ready_set_at": "2026-04-15T17:00:00+05:00",
        },
    )

    assert ok is False
    assert reason == "same_date_prior_attempt_different_request"
    assert len(attempts) == 1
    assert attempts[0]["reason"] == "telegram_send_ledger_missing_after_attempt"


class _FakeClient:
    def __init__(self, tab_values: dict[str, list[list[str]]]) -> None:
        self._tab_values = tab_values
        self.updated_rows: list[tuple[str, list[str], list[dict[str, object]]]] = []

    def get_tab_values(self, tab_name: str):
        return self._tab_values.get(tab_name, [])

    def update_tab_rows(self, tab_name: str, headers: list[str], rows: list[dict[str, object]]) -> None:
        self.updated_rows.append((tab_name, headers, rows))
        matrix = self._tab_values.setdefault(tab_name, [headers])
        while len(matrix) <= rows[0]["sheet_row"] - 1:
            matrix.append([""] * len(headers))
        for update in rows:
            row_values = [str(update["row"].get(header, "")) for header in headers]
            matrix[update["sheet_row"] - 1] = row_values


def test_closeout_apply_stops_locally_before_any_write_when_halt_barrier_blocks(
    monkeypatch,
    tmp_path: Path,
) -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                [
                    "2026-04-15",
                    "READY",
                    "adil",
                    "2026-04-15T16:59:00+05:00",
                    "",
                    "",
                    "",
                    "",
                ],
            ],
            "SalesRaw_Today": [contract.tabs["SalesRaw_Today"].headers],
        }
    )
    creds = tmp_path / "svc.json"
    creds.write_text("{}", encoding="utf-8")
    report_path = tmp_path / "closeout_report.json"
    monkeypatch.setenv("ENABLE_GOOGLE_OPS_BOARD_CLOSEOUT", "1")
    monkeypatch.setenv(closeout_mod.AUTOMATION_LOCK_HELD_ENV, "1")
    monkeypatch.setattr(
        closeout_mod.GoogleOpsBoardClient,
        "from_service_account_file",
        lambda *_args, **_kwargs: client,
    )
    monkeypatch.setattr(
        closeout_mod,
        "evaluate_closeout_halt_barrier",
        lambda **_kwargs: {
            "blocked": True,
            "reason": "REQUEST_HALTED",
            "request_halted": True,
        },
    )

    rc = closeout_mod.main(
        [
            "--apply",
            "--db-path",
            str(tmp_path / "app.db"),
            "--service-account-json",
            str(creds),
            "--spreadsheet-id",
            "sheet-id",
            "--target-date",
            "2026-04-15",
            "--expected-ready-set-at",
            "2026-04-15T16:59:00+05:00",
            "--run-root",
            str(tmp_path / "workflow_runs"),
            "--json-out",
            str(report_path),
        ]
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert rc == 1
    assert report["failure_stage"] == "request_identity"
    assert report["failure_reason"] == "local_halt_barrier:REQUEST_HALTED"
    assert client.updated_rows == []


def test_closeout_run_control_helpers_never_fall_back_to_wrong_date() -> None:
    contract = load_ops_board_contract()
    headers = contract.tabs["Run_Control"].headers
    wrong_row = dict(
        zip(
            headers,
            ["2026-04-14", "READY", "adil", "", "", "", "old-run", "OK"],
        )
    )
    client = _FakeClient({"Run_Control": [headers, list(wrong_row.values())]})

    assert closeout_mod._select_run_control_row([wrong_row], date(2026, 4, 15)) is None

    closeout_mod._update_run_control_status(
        client=client,
        contract=contract,
        target_date=date(2026, 4, 15),
        run_id="new-run",
        status="BLOCKED",
        hold_on_failure=False,
    )

    assert client.updated_rows == []
    assert client.get_tab_values("Run_Control")[1][6] == "old-run"


def _make_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE fact_orders_kaspi (
            id INTEGER PRIMARY KEY,
            order_id TEXT,
            store_code TEXT,
            assigned_size TEXT,
            sku_key TEXT,
            kaspi_offer_name TEXT,
            planned_shipment_date TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            product_type TEXT
        )
        """
    )
    conn.execute("INSERT INTO dim_sku (sku_key, product_type) VALUES ('SKU-1', 'CL')")
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            id, order_id, store_code, assigned_size, sku_key, kaspi_offer_name,
            planned_shipment_date
        )
        VALUES (1, '1001', 'UNIVERSAL', '', 'SKU-1', 'Offer', '2026-04-15')
        """
    )
    conn.commit()
    conn.close()


def _set_db_size(db_path: Path, size: str = "L") -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE fact_orders_kaspi SET assigned_size = ? WHERE order_id = '1001'",
        (size,),
    )
    conn.commit()
    conn.close()


def _write_manifest_for_expected(
    *,
    expected_path: Path,
    today_folder: Path,
    send_order_ids: list[str] | None = None,
    batch_name: str = "test_batch",
    pin: bool = True,
    telegram_ledger_state: str | None = None,
) -> tuple[Path, dict[str, object]]:
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    expected_ids = list(expected.get("expected_order_ids") or [])
    send_ids = list(expected_ids if send_order_ids is None else send_order_ids)
    orders_by_store: dict[str, set[str]] = {}
    source_lines: list[dict[str, object]] = []
    for row in expected.get("orders") or []:
        orders_by_store.setdefault(str(row["store_code"]), set()).add(str(row["order_id"]))
        if str(row["order_id"]) in send_ids:
            source_lines.extend(list(row.get("lines") or []))
    batch_root = today_folder / "MERGED" / "SEND" / batch_name
    batch_root.mkdir(parents=True, exist_ok=True)
    manifest_path = batch_root / "send_batch_manifest.json"
    pdf_bytes = b"%PDF-1.4\ncloseout-test\n%%EOF\n"
    entries: list[dict[str, object]] = []
    if send_ids:
        (batch_root / "bundle.pdf").write_bytes(pdf_bytes)
        entries = [
            {
                "pdf_key": "pdf-1",
                "relative_output_path": "bundle.pdf",
                "filename": "bundle.pdf",
                "sha256": hashlib.sha256(pdf_bytes).hexdigest(),
                "file_size": len(pdf_bytes),
                "mtime": "2026-04-15T18:10:00+05:00",
                "logical_group_type": "NORMAL",
                "order_ids": send_ids,
                "source_row_ids": [
                    str(line["db_row_id"])
                    for line in source_lines
                ],
                "source_lines": source_lines,
            }
        ]
    payload = {
        "schema_version": 4,
        "target_date": expected["target_date"],
        "request_identity": expected["request_identity"],
        "ready_set_at": expected["request_identity"]["ready_set_at"],
        "expected_orders_path": str(expected_path.resolve()),
        "expected_orders_sha256": hashlib.sha256(expected_path.read_bytes()).hexdigest(),
        "obligation_scope_hash": closeout_mod._order_scope_hash(orders_by_store),
        "line_scope_hash": (
            required_line_scope_hash(source_lines)
            if int(expected.get("schema_version") or 1) >= 2
            else ""
        ),
        "batch_hash": "",
        "counts": {"pdfs": 1 if send_ids else 0, "orders": len(send_ids)},
        "send_order_ids": send_ids,
        "terminal_orders_excluded": True,
        "missing_overdue_order_ids": [],
        "overdue_order_ids": [
            order_id
            for order_id in expected.get("overdue_order_ids") or []
            if order_id in send_ids
        ],
        "entries": entries,
    }
    payload["batch_hash"] = compute_manifest_batch_hash(payload)
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (batch_root / "send_ledger.json").write_text("{}", encoding="utf-8")
    if telegram_ledger_state is not None:
        (batch_root / "telegram_send_ledger.json").write_text(
            json.dumps(
                {
                    "batch_hash": payload["batch_hash"],
                    "telegram_chat_id": "-100123",
                    "entries": {
                        "pdf-1": {
                            "state": telegram_ledger_state,
                            "telegram_chat_id": "-100123",
                            "history": (
                                [{"event": "confirmed"}]
                                if telegram_ledger_state == "confirmed"
                                else []
                            ),
                        }
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    delivery_pin = (
        closeout_mod._pin_send_manifest(
            manifest_path=manifest_path,
            today_folder=today_folder,
            expected_orders_path=expected_path,
        )
        if pin
        else {}
    )
    return manifest_path, delivery_pin


def _expected_payload_for_order_1001(
    *,
    ready_set_at: str = "2026-04-15T18:10:00+05:00",
) -> dict[str, object]:
    lines = [
        {
            "db_row_id": "1",
            "store_code": "UNIVERSAL",
            "order_id": "1001",
            "sku_key": "SKU-1",
            "sku_id": "",
            "kaspi_offer_name": "Offer",
            "kaspi_name_core": "Offer",
            "quantity": 1,
            "assigned_size": "L",
            "my_size": "",
            "final_size": "L",
        }
    ]
    return {
        "schema_version": 3,
        "ok": True,
        "generated_at": "2026-04-15T18:10:01+05:00",
        "target_date": "2026-04-15",
        "lookback_days": None,
        "min_planned_shipment_date": None,
        "request_identity": {
            "target_date": "2026-04-15",
            "ready_set_at": ready_set_at,
        },
        "source": "fact_orders_kaspi_after_final_size_writeback",
        "active_order_filter": True,
        "active_order_filter_counts_by_store": {"UNIVERSAL": 1},
        "expected_order_ids": ["1001"],
        "overdue_order_ids": [],
        "orders": [
            {
                "order_id": "1001",
                "store_code": "UNIVERSAL",
                "planned_shipment_date": "2026-04-15",
                "assigned_size": "L",
                "my_size": "",
                "final_size": "L",
                "lines": lines,
                "package_count": 1,
                "stage": "ACCEPTED_PENDING_ASSEMBLY",
                "overdue": False,
            }
        ],
        "counts": {
            "orders": 1,
            "order_lines": 1,
            "overdue_orders": 0,
            "excluded_rows": 0,
        },
        "counts_by_store": {"UNIVERSAL": 1},
        "counts_by_stage": {"ACCEPTED_PENDING_ASSEMBLY": 1},
        "line_scope_hash": required_line_scope_hash(lines),
        "excluded_counts": {},
        "missing_active_order_ids_by_store": {},
        "active_order_blockers": {},
    }


def test_build_readiness_report_blocks_when_hold_and_blank_size(tmp_path: Path):
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "HOLD", "", "", "", "", "", ""],
            ],
            "SalesRaw_Today": [
                contract.tabs["SalesRaw_Today"].headers,
                ["TODAY", "2026-04-15", "Universal", "", "", "1", "Nike", "1001", "", "L", "Offer", "SKU-1", "1", "line", "DEFAULT", "LOW"],
            ],
        }
    )

    report = closeout_mod.build_readiness_report(
        client=client,
        contract=contract,
        db_path=db_path,
        target_date=closeout_mod.date(2026, 4, 15),
        lookback_days=5,
    )

    assert report["ready"] is False
    assert report["run_control_ready_ok"] is False
    assert report["blank_size_count"] == 1


def test_build_readiness_report_accepts_ready_toggle_and_valid_sizes(tmp_path: Path):
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "READY", "adil", "2026-04-15T18:10:00+05:00", "", "", "", ""],
            ],
            "SalesRaw_Today": [
                contract.tabs["SalesRaw_Today"].headers,
                ["TODAY", "2026-04-15", "Universal", "", "", "1", "Nike", "1001", "L", "L", "Offer", "SKU-1", "1", "line", "DEFAULT", "LOW"],
            ],
        }
    )

    report = closeout_mod.build_readiness_report(
        client=client,
        contract=contract,
        db_path=db_path,
        target_date=closeout_mod.date(2026, 4, 15),
        lookback_days=5,
    )

    assert report["ready"] is True
    assert report["pending_db_writeback_count"] == 1
    assert report["invalid_size_count"] == 0


def test_build_readiness_report_fitpack_exclusion_ignores_storeb_blank_size(tmp_path: Path):
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-07-04", "READY", "adil", "2026-07-04T18:10:00+05:00", "", "", "", ""],
            ],
            "SalesRaw_Today": [
                contract.tabs["SalesRaw_Today"].headers,
                ["TODAY", "2026-07-04", "Universal", "", "", "1", "Nike", "1001", "L", "L", "Offer", "SKU-1", "1", "line", "DEFAULT", "LOW"],
                ["TODAY", "2026-07-04", "STORE-B", "", "", "2", "FitPack", "2001", "", "", "Offer", "SKU-1", "1", "line", "DEFAULT", "LOW"],
            ],
        }
    )

    report = closeout_mod.build_readiness_report(
        client=client,
        contract=contract,
        db_path=db_path,
        target_date=closeout_mod.date(2026, 7, 4),
        lookback_days=5,
        storeb_excluded=True,
    )

    assert report["ready"] is True
    assert report["blank_size_count"] == 0
    assert report["fitpack_storeb_excluded"] is True
    assert report["fitpack_storeb_skipped_rows"] == 1


def test_store_context_discovers_configured_store_absent_from_sheet(monkeypatch) -> None:
    initialized: list[str] = []

    class _Client:
        def __init__(self, store_code: str):
            initialized.append(store_code)
            self._merchant_uid = f"merchant-{store_code}"

    monkeypatch.setattr(
        closeout_mod,
        "load_sync_enabled_kaspi_store_codes",
        lambda: ["UNIVERSAL", "ACMEWEAR"],
    )
    monkeypatch.setattr(closeout_mod, "KaspiAPIClient", _Client)

    report = closeout_mod.build_store_context_report(
        salesraw_rows=[],
        storeb_excluded=False,
    )

    assert report["ok"] is True
    assert report["active_store_codes"] == ["UNIVERSAL", "ACMEWEAR"]
    assert initialized == ["UNIVERSAL", "ACMEWEAR"]


def test_fitpack_excluded_storeb_never_constructs_api_client(monkeypatch) -> None:
    initialized: list[str] = []

    class _Client:
        def __init__(self, store_code: str):
            initialized.append(store_code)
            self._merchant_uid = f"merchant-{store_code}"

    monkeypatch.setattr(
        closeout_mod,
        "load_sync_enabled_kaspi_store_codes",
        lambda: ["UNIVERSAL", "STOREB"],
    )
    monkeypatch.setattr(closeout_mod, "KaspiAPIClient", _Client)

    report = closeout_mod.build_store_context_report(
        salesraw_rows=[{"STORE_NAME": "STORE-B"}],
        storeb_excluded=True,
    )

    assert report["ok"] is True
    assert report["active_store_codes"] == ["UNIVERSAL"]
    assert initialized == ["UNIVERSAL"]


def test_unmapped_sync_enabled_store_fails_context_instead_of_disappearing(monkeypatch) -> None:
    initialized: list[str] = []

    class _Client:
        def __init__(self, store_code: str):
            initialized.append(store_code)
            self._merchant_uid = f"merchant-{store_code}"

    monkeypatch.setattr(
        closeout_mod,
        "load_sync_enabled_kaspi_store_codes",
        lambda: ["UNIVERSAL", "UNMAPPED_STORE"],
    )
    monkeypatch.setattr(closeout_mod, "KaspiAPIClient", _Client)

    report = closeout_mod.build_store_context_report(
        salesraw_rows=[],
        storeb_excluded=False,
    )

    assert report["ok"] is False
    assert report["active_store_codes"] == ["UNIVERSAL", "UNMAPPED_STORE"]
    assert initialized == ["UNIVERSAL"]
    assert report["failures"] == [
        {
            "store_code": "UNMAPPED_STORE",
            "token_env": "",
            "merchant_uid": "",
            "ok": False,
            "error": "configured sync-enabled store is missing from STORE_TOKEN_MAP",
        }
    ]


def test_unconfirmed_db_hint_api_error_is_quarantined_not_blocking(monkeypatch) -> None:
    monkeypatch.setattr(
        closeout_mod,
        "_fetch_prior_obligation_details",
        lambda **_kwargs: {"UNIVERSAL:LEGACY100": {"error": "timeout"}},
    )

    result = closeout_mod._resolve_db_bootstrap_hints(
        prior_ledger={"schema_version": 1, "entries": {}},
        candidates_by_store={"UNIVERSAL": {"LEGACY100"}},
        current_active_order_ids_by_store={"UNIVERSAL": set()},
        target_date=closeout_mod.date(2026, 7, 11),
        ready_set_at="2026-07-11T17:00:00+05:00",
    )

    assert result["ledger"]["entries"] == {}
    assert result["promoted_keys"] == []
    assert [row["key"] for row in result["quarantined"]] == ["UNIVERSAL:LEGACY100"]


def test_source_confirmed_prior_obligation_api_error_still_blocks() -> None:
    prior = {
        "schema_version": 1,
        "entries": {
            "UNIVERSAL:PRIOR100": {
                "store_code": "UNIVERSAL",
                "order_id": "PRIOR100",
                "status": "unresolved",
                "first_seen_target_date": "2026-07-10",
                "last_seen_target_date": "2026-07-10",
            }
        },
    }
    bootstrap = closeout_mod._resolve_db_bootstrap_hints(
        prior_ledger=prior,
        candidates_by_store={"UNIVERSAL": {"PRIOR100"}},
        current_active_order_ids_by_store={"UNIVERSAL": set()},
        target_date=closeout_mod.date(2026, 7, 11),
        ready_set_at="2026-07-11T17:00:00+05:00",
    )

    result = closeout_mod.reconcile_shipping_obligations(
        prior_ledger=bootstrap["ledger"],
        current_active_order_ids_by_store={"UNIVERSAL": set()},
        detail_results={"UNIVERSAL:PRIOR100": {"error": "timeout"}},
        target_date=closeout_mod.date(2026, 7, 11),
        ready_set_at="2026-07-11T17:00:00+05:00",
        now=closeout_mod.datetime.now(closeout_mod.ALMATY_TZ),
    )

    assert result["ok"] is False
    assert result["ledger"]["entries"]["UNIVERSAL:PRIOR100"]["status"] == "unresolved"
    assert result["issues"][0]["code"] == "obligation_api_uncertain"


def _obligation_ledger(store: str, count: int) -> dict[str, object]:
    return {
        "schema_version": 1,
        "entries": {
            f"{store}:ORDER-{idx:03d}": {
                "store_code": store,
                "order_id": f"ORDER-{idx:03d}",
                "status": "unresolved",
                "first_seen_target_date": "2026-07-10",
                "last_seen_target_date": "2026-07-13",
            }
            for idx in range(count)
        },
    }


def test_obligation_detail_resolver_uses_bulk_reads_before_exact_fallback(monkeypatch) -> None:
    exact_reads: list[str] = []
    bulk_reads: list[str] = []

    class _Client:
        def __init__(self, store_code: str):
            assert store_code == "UNIVERSAL"

        def list_all_orders(self, *, state, since, until, max_pages, raise_on_error):
            bulk_reads.append(state)
            if state != "KASPI_DELIVERY":
                return []
            return [
                {"id": f"ID-{idx}", "attributes": {"code": f"ORDER-{idx:03d}"}}
                for idx in range(20)
            ]

        def get_order(self, order_id: str):
            exact_reads.append(order_id)
            raise AssertionError("bulk resolution should cover this obligation")

    monkeypatch.setattr(closeout_mod, "KaspiAPIClient", _Client)
    stats: dict[str, object] = {}
    result = closeout_mod._fetch_prior_obligation_details(
        ledger=_obligation_ledger("UNIVERSAL", 20),
        current_active_order_ids_by_store={"UNIVERSAL": set()},
        target_date=closeout_mod.date(2026, 7, 14),
        stats_out=stats,
    )

    assert len(result) == 20
    assert all("order" in item for item in result.values())
    assert bulk_reads == ["KASPI_DELIVERY", "ARCHIVE"]
    assert exact_reads == []
    assert stats["exact_read_count"] == 0
    assert stats["resolved_count"] == 20


def test_obligation_detail_resolver_fails_closed_when_exact_budget_is_exhausted(monkeypatch) -> None:
    class _Response:
        success = True
        error = None

        def __init__(self, order_id: str):
            self.data = {"attributes": {"code": order_id}}

    class _Client:
        def __init__(self, store_code: str):
            self.store_code = store_code

        def list_all_orders(self, **_kwargs):
            return []

        def get_order(self, order_id: str):
            return _Response(order_id)

    monkeypatch.setattr(closeout_mod, "KaspiAPIClient", _Client)
    stats: dict[str, object] = {}
    result = closeout_mod._fetch_prior_obligation_details(
        ledger=_obligation_ledger("UNIVERSAL", 30),
        current_active_order_ids_by_store={"UNIVERSAL": set()},
        target_date=closeout_mod.date(2026, 7, 14),
        stats_out=stats,
    )

    errors = [item for item in result.values() if "error" in item]
    assert len(errors) == 5
    assert all("budget exhausted" in item["error"] for item in errors)
    assert stats["exact_read_count"] == 25
    assert stats["budget_exhausted"] is True


def test_success_status_resets_run_control_ready_toggle_to_hold() -> None:
    contract = load_ops_board_contract()
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "READY", "adil", "", "", "", "", ""],
            ]
        }
    )

    closeout_mod._update_run_control_status(
        client=client,
        contract=contract,
        target_date=closeout_mod.date(2026, 4, 15),
        run_id="run-1",
        status="OK",
        hold_on_failure=False,
    )

    row = client.updated_rows[-1][2][0]["row"]
    assert row["ready_for_closeout"] == "HOLD"
    assert row["last_orchestrator_run_id"] == "run-1"
    assert row["last_orchestrator_status"] == "OK"


def test_closeout_main_dry_run_executes_steps_in_order(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    _set_db_size(db_path)
    contract = load_ops_board_contract()
    creds = tmp_path / "svc.json"
    creds.write_text("{}", encoding="utf-8")

    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "READY", "adil", "2026-04-15T18:10:00+05:00", "", "", "", ""],
            ],
            "SalesRaw_Today": [
                contract.tabs["SalesRaw_Today"].headers,
                ["TODAY", "2026-04-15", "Universal", "", "", "1", "Nike", "1001", "L", "L", "Offer", "SKU-1", "1", "line", "DEFAULT", "LOW"],
            ],
        }
    )

    calls: list[str] = []
    commands: dict[str, list[str]] = {}

    def _fake_run_command(*, name, command, env, report_path):
        calls.append(name)
        commands[name] = list(command)
        if "--output-json" in command:
            json_path = Path(command[command.index("--output-json") + 1])
            if name == "size_writeback":
                json_path.write_text(
                    json.dumps(
                        {
                            "db_backup_path": None,
                            "updates_applied": 0,
                            "updates_count": 0,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            else:
                json_path.write_text("{}", encoding="utf-8")
        report = {
            "name": name,
            "command": command,
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "ok": True,
        }
        report_path.write_text(json.dumps(report), encoding="utf-8")
        return report

    monkeypatch.setattr(closeout_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(closeout_mod, "_run_command", _fake_run_command)
    monkeypatch.setattr(
        closeout_mod,
        "fetch_api_active_order_ids_by_store",
        lambda **_kwargs: {"UNIVERSAL": {"1001"}},
    )
    monkeypatch.setattr(
        closeout_mod,
        "build_store_context_report",
        lambda **_kwargs: {
            "ok": True,
            "active_store_codes": ["UNIVERSAL"],
            "stores": [{"store_code": "UNIVERSAL", "ok": True, "merchant_uid": "30000001", "token_env": "KASPI_TOKEN_UNIVERSAL", "error": ""}],
            "failure_count": 0,
        },
    )

    rc = closeout_mod.main(
        [
            "--db-path",
            str(db_path),
            "--service-account-json",
            str(creds),
            "--spreadsheet-id",
            "sheet-id",
            "--target-date",
            "2026-04-15",
            "--run-root",
            str(tmp_path / "workflow_runs"),
            "--json-out",
            str(tmp_path / "closeout_report.json"),
        ]
    )

    report = json.loads((tmp_path / "closeout_report.json").read_text(encoding="utf-8"))
    assert rc == 0
    assert calls == [
        "size_writeback",
        "shipping",
        "download_waybills",
        "build_waybills",
    ]
    assert report["ok"] is True
    assert report["shipping_obligation_ledger_written"] is False
    for stage in ("shipping", "download_waybills", "build_waybills"):
        assert "--dry-run" in commands[stage]
        assert "--required-orders-file" in commands[stage]
    assert report["steps"][-1]["name"] == "delivery_preflight"
    assert report["steps"][-1]["skipped"] is True


def test_pinned_delivery_attempt_evidence_blocks_rebuild_after_partial_send(tmp_path: Path) -> None:
    batch_root = tmp_path / "MERGED" / "SEND" / "batch"
    batch_root.mkdir(parents=True)
    manifest_path = batch_root / "send_batch_manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    ledger_path = batch_root / "send_ledger.json"
    ledger_path.write_text(
        json.dumps(
            {
                "entries": {
                    "pdf-1": {
                        "state": "confirmed",
                        "history": [{"event": "telegram_confirmed"}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    found, reason = closeout_mod._pinned_delivery_attempt_evidence(
        {"manifest_path": str(manifest_path), "ledger_path": str(ledger_path)}
    )

    assert found is True
    assert reason.startswith("delivery_attempt_evidence:")


def test_resume_invalid_pin_after_partial_send_stops_before_rebuild_or_delivery(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    _set_db_size(db_path)
    contract = load_ops_board_contract()
    creds = tmp_path / "svc.json"
    creds.write_text("{}", encoding="utf-8")
    salesraw_row = [
        "TODAY", "2026-04-15", "Universal", "", "", "1", "Nike", "1001",
        "L", "L", "Offer", "SKU-1", "1", "line", "DEFAULT", "LOW",
    ]
    run_control_row = [
        "2026-04-15", "READY", "adil", "2026-04-15T18:10:00+05:00",
        "", "", "", "",
    ]
    client = _FakeClient(
        {
            "Run_Control": [contract.tabs["Run_Control"].headers, run_control_row],
            "SalesRaw_Today": [contract.tabs["SalesRaw_Today"].headers, salesraw_row],
        }
    )
    prior_run_dir = tmp_path / "workflow_runs" / "2026-04-15" / "prior"
    prior_run_dir.mkdir(parents=True)
    expected_payload = _expected_payload_for_order_1001()
    expected_path = prior_run_dir / "expected_closeout_orders.json"
    expected_path.write_text(json.dumps(expected_payload), encoding="utf-8")
    today_folder = tmp_path / "Today"
    manifest_path, delivery_pin = _write_manifest_for_expected(
        expected_path=expected_path,
        today_folder=today_folder,
    )
    Path(delivery_pin["ledger_path"]).write_text(
        json.dumps(
            {
                "entries": {
                    "pdf-1": {
                        "state": "confirmed",
                        "history": [{"event": "telegram_confirmed"}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    checkpoint_path = tmp_path / "workflow_runs" / "2026-04-15" / "closeout_checkpoint.json"
    checkpoint_path.write_text(
        json.dumps(
            {
                "execution_mode": "dry_run",
                "target_date": "2026-04-15",
                "db_path": str(db_path.resolve()),
                "spreadsheet_id": "sheet-id",
                "service_account_json": str(creds.resolve()),
                "salesraw_writeback_fingerprint": closeout_mod.salesraw_writeback_fingerprint(
                    [dict(zip(contract.tabs["SalesRaw_Today"].headers, salesraw_row))]
                ),
                "run_control_resume_fingerprint": closeout_mod.run_control_resume_fingerprint(
                    dict(zip(contract.tabs["Run_Control"].headers, run_control_row))
                ),
                "delivery_artifacts": delivery_pin,
                "stages": {"build_waybills": {"status": "ok"}},
            }
        ),
        encoding="utf-8",
    )
    calls: list[str] = []

    monkeypatch.setattr(
        closeout_mod.GoogleOpsBoardClient,
        "from_service_account_file",
        lambda *_args, **_kwargs: client,
    )
    monkeypatch.setattr(
        closeout_mod,
        "_run_command",
        lambda **kwargs: calls.append(kwargs["name"]),
    )

    rc = closeout_mod.main(
        [
            "--db-path", str(db_path),
            "--service-account-json", str(creds),
            "--spreadsheet-id", "sheet-id",
            "--target-date", "2026-04-15",
            "--today-folder", str(today_folder),
            "--run-root", str(tmp_path / "workflow_runs"),
            "--checkpoint-path", str(checkpoint_path),
            "--resume",
            "--json-out", str(tmp_path / "closeout_report.json"),
        ]
    )

    report = json.loads((tmp_path / "closeout_report.json").read_text(encoding="utf-8"))
    assert rc == 1
    assert calls == []
    assert report["failure_stage"] == "checkpoint"
    assert report["failure_reason"].startswith(
        "checkpoint_delivery_pin_invalid_after_attempt:"
    )


def test_zero_order_closeout_is_local_noop_without_broad_consumers(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM fact_orders_kaspi")
    conn.commit()
    conn.close()
    contract = load_ops_board_contract()
    creds = tmp_path / "svc.json"
    creds.write_text("{}", encoding="utf-8")
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "READY", "adil", "2026-04-15T18:10:00+05:00", "", "", "", ""],
            ],
            "SalesRaw_Today": [contract.tabs["SalesRaw_Today"].headers],
        }
    )
    calls: list[str] = []

    def _fake_run_command(*, name, command, env, report_path):
        calls.append(name)
        if "--output-json" in command:
            Path(command[command.index("--output-json") + 1]).write_text(
                json.dumps(
                    {
                        "db_backup_path": None,
                        "updates_applied": 0,
                        "updates_count": 0,
                    }
                ),
                encoding="utf-8",
            )
        report = {
            "name": name,
            "command": command,
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "ok": True,
        }
        report_path.write_text(json.dumps(report), encoding="utf-8")
        return report

    monkeypatch.setattr(
        closeout_mod.GoogleOpsBoardClient,
        "from_service_account_file",
        lambda *_args, **_kwargs: client,
    )
    monkeypatch.setattr(closeout_mod, "_run_command", _fake_run_command)
    monkeypatch.setattr(
        closeout_mod,
        "fetch_api_active_order_ids_by_store",
        lambda **_kwargs: {"UNIVERSAL": set()},
    )
    monkeypatch.setattr(
        closeout_mod,
        "build_store_context_report",
        lambda **_kwargs: {
            "ok": True,
            "active_store_codes": ["UNIVERSAL"],
            "stores": [],
            "failure_count": 0,
        },
    )

    rc = closeout_mod.main(
        [
            "--db-path",
            str(db_path),
            "--service-account-json",
            str(creds),
            "--spreadsheet-id",
            "sheet-id",
            "--target-date",
            "2026-04-15",
            "--run-root",
            str(tmp_path / "workflow_runs"),
            "--json-out",
            str(tmp_path / "closeout_report.json"),
        ]
    )

    report = json.loads((tmp_path / "closeout_report.json").read_text(encoding="utf-8"))
    assert rc == 0
    assert calls == ["size_writeback"]
    assert report["zero_order_noop"] is True
    assert report["steps"][-1]["name"] == "zero_order_noop"


def test_closeout_apply_failure_disarms_ready_toggle(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    contract = load_ops_board_contract()
    creds = tmp_path / "svc.json"
    creds.write_text("{}", encoding="utf-8")

    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "READY", "adil", "2026-04-15T17:10:00+05:00", "", "", "", ""],
            ],
            "SalesRaw_Today": [
                contract.tabs["SalesRaw_Today"].headers,
                ["TODAY", "2026-04-15", "Universal", "", "", "1", "Nike", "1001", "L", "L", "Offer", "SKU-1", "1", "line", "DEFAULT", "LOW"],
            ],
        }
    )
    seen_health: dict[str, object] = {}

    def _fake_run_command(*, name, command, env, report_path):
        report = {
            "name": name,
            "command": command,
            "returncode": 1 if name == "shipping" else 0,
            "stdout": "",
            "stderr": "",
            "ok": name != "shipping",
        }
        report_path.write_text(json.dumps(report), encoding="utf-8")
        if "--output-json" in command:
            json_path = Path(command[command.index("--output-json") + 1])
            payload = {"db_backup_path": None, "updates_applied": 1, "updates_count": 1}
            json_path.write_text(json.dumps(payload), encoding="utf-8")
            conn = sqlite3.connect(db_path)
            conn.execute("UPDATE fact_orders_kaspi SET assigned_size = 'L' WHERE order_id = '1001'")
            conn.commit()
            conn.close()
        return report

    monkeypatch.setenv("ENABLE_GOOGLE_OPS_BOARD_CLOSEOUT", "1")
    monkeypatch.setattr(closeout_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(closeout_mod, "_run_command", _fake_run_command)
    monkeypatch.setattr(
        closeout_mod,
        "fetch_api_active_order_ids_by_store",
        lambda **_kwargs: {"UNIVERSAL": {"1001"}},
    )
    monkeypatch.setattr(
        closeout_mod,
        "ensure_prewindow_health",
        lambda **kwargs: seen_health.update(kwargs) or {"ok": True, "report_path": str(tmp_path / "closeout.json")},
    )
    monkeypatch.setattr(closeout_mod, "send_owner_ops_alert", lambda **_kwargs: True)
    monkeypatch.setattr(
        closeout_mod,
        "build_store_context_report",
        lambda **_kwargs: {
            "ok": True,
            "active_store_codes": ["UNIVERSAL"],
            "stores": [{"store_code": "UNIVERSAL", "ok": True, "merchant_uid": "30000001", "token_env": "KASPI_TOKEN_UNIVERSAL", "error": ""}],
            "failure_count": 0,
        },
    )

    rc = closeout_mod.main(
        [
            "--apply",
            "--db-path",
            str(db_path),
            "--service-account-json",
            str(creds),
            "--spreadsheet-id",
            "sheet-id",
            "--target-date",
            "2026-04-15",
            "--expected-ready-set-at",
            "2026-04-15T17:10:00+05:00",
            "--run-root",
            str(tmp_path / "workflow_runs"),
            "--json-out",
            str(tmp_path / "closeout_report.json"),
        ]
    )

    report = json.loads((tmp_path / "closeout_report.json").read_text(encoding="utf-8"))
    assert rc == 1
    assert seen_health["profile"] == "closeout"
    assert report["failure_stage"] == "shipping"
    assert client.get_tab_values("Run_Control")[1][1] == "READY"
    assert client.get_tab_values("Run_Control")[1][-1] == "FAILED_SHIPPING"


def test_closeout_apply_fails_before_external_steps_when_store_context_is_invalid(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    contract = load_ops_board_contract()
    creds = tmp_path / "svc.json"
    creds.write_text("{}", encoding="utf-8")

    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "READY", "adil", "2026-04-15T17:10:00+05:00", "", "", "", ""],
            ],
            "SalesRaw_Today": [
                contract.tabs["SalesRaw_Today"].headers,
                ["TODAY", "2026-04-15", "Universal", "", "", "1", "Nike", "1001", "L", "L", "Offer", "SKU-1", "1", "line", "DEFAULT", "LOW"],
            ],
        }
    )

    calls: list[str] = []

    def _fake_run_command(*, name, command, env, report_path):
        calls.append(name)
        report = {
            "name": name,
            "command": command,
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "ok": True,
        }
        report_path.write_text(json.dumps(report), encoding="utf-8")
        return report

    monkeypatch.setenv("ENABLE_GOOGLE_OPS_BOARD_CLOSEOUT", "1")
    monkeypatch.setattr(closeout_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(closeout_mod, "_run_command", _fake_run_command)
    monkeypatch.setattr(
        closeout_mod,
        "fetch_api_active_order_ids_by_store",
        lambda **_kwargs: {"UNIVERSAL": {"TODAY100"}, "ACMEWEAR": {"OVERDUE101"}},
    )
    monkeypatch.setattr(
        closeout_mod,
        "ensure_prewindow_health",
        lambda **_kwargs: {"ok": True, "report_path": str(tmp_path / "prewindow.json")},
    )
    monkeypatch.setattr(closeout_mod, "send_owner_ops_alert", lambda **_kwargs: True)
    monkeypatch.setattr(
        closeout_mod,
        "build_store_context_report",
        lambda **_kwargs: {
            "ok": False,
            "active_store_codes": ["UNIVERSAL"],
            "stores": [{"store_code": "UNIVERSAL", "ok": False, "error": "merchant UID missing"}],
            "failure_count": 1,
        },
    )

    rc = closeout_mod.main(
        [
            "--apply",
            "--db-path",
            str(db_path),
            "--service-account-json",
            str(creds),
            "--spreadsheet-id",
            "sheet-id",
            "--target-date",
            "2026-04-15",
            "--expected-ready-set-at",
            "2026-04-15T17:10:00+05:00",
            "--run-root",
            str(tmp_path / "workflow_runs"),
            "--json-out",
            str(tmp_path / "closeout_report.json"),
        ]
    )

    report = json.loads((tmp_path / "closeout_report.json").read_text(encoding="utf-8"))
    assert rc == 1
    assert report["failure_stage"] == "store_context"
    assert calls == []
    assert client.get_tab_values("Run_Control")[1][1] == "READY"
    assert client.get_tab_values("Run_Control")[1][-1] == "FAILED_STORE_CONTEXT"


def test_closeout_apply_blocks_delivery_when_send_manifest_missing_expected_order(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE fact_orders_kaspi (
            id INTEGER PRIMARY KEY,
            order_id TEXT,
            store_code TEXT,
            sku_key TEXT,
            assigned_size TEXT,
            my_size TEXT,
            planned_shipment_date TEXT,
            kaspi_status TEXT,
            kaspi_status_detail TEXT,
            signature_required INTEGER,
            courier_transmission_date TEXT,
            returned_to_warehouse INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE dim_sku (
            sku_key TEXT PRIMARY KEY,
            product_type TEXT
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO fact_orders_kaspi (
            id, order_id, store_code, sku_key, assigned_size, my_size, planned_shipment_date,
            kaspi_status, kaspi_status_detail, signature_required, courier_transmission_date,
            returned_to_warehouse
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (1, "TODAY100", "UNIVERSAL", "SKU-1", "L", "", "2026-04-15", "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", 0, "", 0),
            (2, "OVERDUE101", "ACMEWEAR", "SKU-2", "3XL", "", "2026-04-14", "KASPI_DELIVERY", "ACCEPTED_BY_MERCHANT", 0, "", 0),
        ],
    )
    conn.commit()
    conn.close()

    contract = load_ops_board_contract()
    creds = tmp_path / "svc.json"
    creds.write_text("{}", encoding="utf-8")
    today_folder = tmp_path / "Today"

    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "READY", "adil", "2026-04-15T17:10:00+05:00", "", "", "", ""],
            ],
            "SalesRaw_Today": [
                contract.tabs["SalesRaw_Today"].headers,
                ["TODAY", "2026-04-15", "Universal", "", "", "1", "Nike", "TODAY100", "L", "L", "Offer", "SKU-1", "1", "line1", "DEFAULT", "LOW"],
                ["OVERDUE", "2026-04-14", "AcmeWear", "", "", "1", "Line51", "OVERDUE101", "3XL", "3XL", "Offer", "SKU-2", "2", "line2", "DEFAULT", "LOW"],
            ],
        }
    )
    calls: list[str] = []

    def _fake_run_command(*, name, command, env, report_path):
        calls.append(name)
        if name == "build_waybills":
            required_path = Path(command[command.index("--required-orders-file") + 1])
            _write_manifest_for_expected(
                expected_path=required_path,
                today_folder=today_folder,
                send_order_ids=["TODAY100"],
                pin=False,
            )
        report = {
            "name": name,
            "command": command,
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "ok": True,
        }
        report_path.write_text(json.dumps(report), encoding="utf-8")
        if "--output-json" in command:
            json_path = Path(command[command.index("--output-json") + 1])
            json_path.write_text(
                json.dumps({"db_backup_path": None, "updates_applied": 0, "updates_count": 0}),
                encoding="utf-8",
            )
        return report

    monkeypatch.setenv("ENABLE_GOOGLE_OPS_BOARD_CLOSEOUT", "1")
    monkeypatch.setattr(closeout_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(closeout_mod, "_run_command", _fake_run_command)
    monkeypatch.setattr(
        closeout_mod,
        "fetch_api_active_order_ids_by_store",
        lambda **_kwargs: {"UNIVERSAL": {"TODAY100"}, "ACMEWEAR": {"OVERDUE101"}},
    )
    monkeypatch.setattr(
        closeout_mod,
        "ensure_prewindow_health",
        lambda **_kwargs: {"ok": True, "report_path": str(tmp_path / "prewindow.json")},
    )
    monkeypatch.setattr(closeout_mod, "send_owner_ops_alert", lambda **_kwargs: True)
    monkeypatch.setattr(
        closeout_mod,
        "build_store_context_report",
        lambda **_kwargs: {
            "ok": True,
            "active_store_codes": ["UNIVERSAL", "ACMEWEAR"],
            "stores": [],
            "failure_count": 0,
        },
    )

    rc = closeout_mod.main(
        [
            "--apply",
            "--db-path",
            str(db_path),
            "--service-account-json",
            str(creds),
            "--spreadsheet-id",
            "sheet-id",
            "--target-date",
            "2026-04-15",
            "--expected-ready-set-at",
            "2026-04-15T17:10:00+05:00",
            "--today-folder",
            str(today_folder),
            "--run-root",
            str(tmp_path / "workflow_runs"),
            "--json-out",
            str(tmp_path / "closeout_report.json"),
        ]
    )

    report = json.loads((tmp_path / "closeout_report.json").read_text(encoding="utf-8"))
    assert rc == 1
    assert report["failure_stage"] == "build_waybills"
    assert "OVERDUE101" in report["failure_reason"]
    assert "delivery_send" not in calls


def test_closeout_apply_runs_shipped_truth_sync_after_delivery(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE fact_orders_kaspi (
            id INTEGER PRIMARY KEY,
            order_id TEXT,
            store_code TEXT,
            sku_key TEXT,
            assigned_size TEXT,
            my_size TEXT,
            planned_shipment_date TEXT,
            kaspi_status TEXT,
            kaspi_status_detail TEXT,
            signature_required INTEGER,
            courier_transmission_date TEXT,
            returned_to_warehouse INTEGER
        )
        """
    )
    conn.execute("CREATE TABLE dim_sku (sku_key TEXT PRIMARY KEY, product_type TEXT)")
    conn.execute(
        """
        INSERT INTO fact_orders_kaspi (
            id, order_id, store_code, sku_key, assigned_size, my_size, planned_shipment_date,
            kaspi_status, kaspi_status_detail, signature_required, courier_transmission_date,
            returned_to_warehouse
        )
        VALUES (1, 'TODAY100', 'UNIVERSAL', 'SKU-1', 'L', '', '2026-04-15',
            'KASPI_DELIVERY', 'ACCEPTED_BY_MERCHANT', 0, '', 0)
        """
    )
    conn.commit()
    conn.close()

    contract = load_ops_board_contract()
    creds = tmp_path / "svc.json"
    creds.write_text("{}", encoding="utf-8")
    today_folder = tmp_path / "Today"
    client = _FakeClient(
        {
            "Run_Control": [
                contract.tabs["Run_Control"].headers,
                ["2026-04-15", "READY", "adil", "2026-04-15T17:10:00+05:00", "", "", "", ""],
            ],
            "SalesRaw_Today": [
                contract.tabs["SalesRaw_Today"].headers,
                ["TODAY", "2026-04-15", "Universal", "", "", "1", "Nike", "TODAY100", "L", "L", "Offer", "SKU-1", "1", "line1", "DEFAULT", "LOW"],
            ],
        }
    )
    calls: list[tuple[str, list[str], dict[str, str]]] = []

    def _fake_run_command(*, name, command, env, report_path):
        calls.append((name, list(command), dict(env)))
        if name == "build_waybills":
            _write_manifest_for_expected(
                expected_path=Path(command[command.index("--required-orders-file") + 1]),
                today_folder=today_folder,
            )
        report = {"name": name, "command": command, "returncode": 0, "stdout": "", "stderr": "", "ok": True}
        report_path.write_text(json.dumps(report), encoding="utf-8")
        if "--output-json" in command:
            json_path = Path(command[command.index("--output-json") + 1])
            json_path.write_text(json.dumps({"db_backup_path": None, "updates_applied": 0, "updates_count": 0}), encoding="utf-8")
        if "--json-out" in command:
            json_path = Path(command[command.index("--json-out") + 1])
            json_path.write_text(json.dumps({"ok": True, "returncode": 0}), encoding="utf-8")
        return report

    monkeypatch.setenv("ENABLE_GOOGLE_OPS_BOARD_CLOSEOUT", "1")
    monkeypatch.setattr(closeout_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(closeout_mod, "_run_command", _fake_run_command)
    monkeypatch.setattr(closeout_mod, "fetch_api_active_order_ids_by_store", lambda **_kwargs: {"UNIVERSAL": {"TODAY100"}})
    monkeypatch.setattr(closeout_mod, "ensure_prewindow_health", lambda **_kwargs: {"ok": True, "report_path": str(tmp_path / "prewindow.json")})
    monkeypatch.setattr(closeout_mod, "send_owner_ops_alert", lambda **_kwargs: True)
    monkeypatch.setattr(closeout_mod, "delivery_completion_state", lambda **_kwargs: {"completed": True, "status": "TELEGRAM_CONFIRMED"})
    monkeypatch.setattr(
        closeout_mod,
        "build_store_context_report",
        lambda **_kwargs: {"ok": True, "active_store_codes": ["UNIVERSAL"], "stores": [], "failure_count": 0},
    )

    rc = closeout_mod.main(
        [
            "--apply",
            "--db-path",
            str(db_path),
            "--service-account-json",
            str(creds),
            "--spreadsheet-id",
            "sheet-id",
            "--target-date",
            "2026-04-15",
            "--expected-ready-set-at",
            "2026-04-15T17:10:00+05:00",
            "--today-folder",
            str(today_folder),
            "--run-root",
            str(tmp_path / "workflow_runs"),
            "--json-out",
            str(tmp_path / "closeout_report.json"),
        ]
    )

    report = json.loads((tmp_path / "closeout_report.json").read_text(encoding="utf-8"))
    names = [name for name, _command, _env in calls]
    shipped_truth_call = calls[-1]
    assert rc == 0
    assert names == ["size_writeback", "shipping", "download_waybills", "build_waybills", "delivery_send", "shipped_truth_sync"]
    assert "run_kaspi_shipped_truth_sync_scheduler.py" in " ".join(shipped_truth_call[1])
    assert shipped_truth_call[2]["ENABLE_KASPI_SHIPPED_TRUTH_SYNC"] == "1"
    assert report["steps"][-1]["name"] == "shipped_truth_sync"


def test_closeout_resume_reuses_successful_checkpoint_stages(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    _set_db_size(db_path)
    contract = load_ops_board_contract()
    creds = tmp_path / "svc.json"
    creds.write_text("{}", encoding="utf-8")

    salesraw_row = ["TODAY", "2026-04-15", "Universal", "", "", "1", "Nike", "1001", "L", "L", "Offer", "SKU-1", "1", "line", "DEFAULT", "LOW"]
    run_control_row = ["2026-04-15", "READY", "adil", "2026-04-15T18:10:00+05:00", "", "", "", ""]
    client = _FakeClient(
        {
            "Run_Control": [contract.tabs["Run_Control"].headers, run_control_row],
            "SalesRaw_Today": [contract.tabs["SalesRaw_Today"].headers, salesraw_row],
        }
    )

    prior_run_dir = tmp_path / "workflow_runs" / "2026-04-15" / "20260415_170000_2026-04-15_closeout"
    prior_run_dir.mkdir(parents=True, exist_ok=True)
    for stage in ("size_writeback", "shipping"):
        step_report = {
            "name": stage,
            "command": [stage],
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "ok": True,
        }
        (prior_run_dir / f"step_{stage}.json").write_text(json.dumps(step_report), encoding="utf-8")

    checkpoint_path = tmp_path / "workflow_runs" / "2026-04-15" / "closeout_checkpoint.json"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(
        json.dumps(
            {
                "execution_mode": "dry_run",
                "target_date": "2026-04-15",
                "db_path": str(db_path.resolve()),
                "spreadsheet_id": "sheet-id",
                "service_account_json": str(creds.resolve()),
                "salesraw_writeback_fingerprint": closeout_mod.salesraw_writeback_fingerprint(
                    [dict(zip(contract.tabs["SalesRaw_Today"].headers, salesraw_row))]
                ),
                "run_control_row_hash": closeout_mod._hash_run_control_row(
                    dict(zip(contract.tabs["Run_Control"].headers, run_control_row))
                ),
                "stages": {
                    "size_writeback": {
                        "status": "ok",
                        "step_report_path": str(prior_run_dir / "step_size_writeback.json"),
                    },
                    "shipping": {
                        "status": "ok",
                        "step_report_path": str(prior_run_dir / "step_shipping.json"),
                    },
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    calls: list[str] = []

    def _fake_run_command(*, name, command, env, report_path):
        calls.append(name)
        report = {"name": name, "command": command, "returncode": 0, "stdout": "", "stderr": "", "ok": True}
        report_path.write_text(json.dumps(report), encoding="utf-8")
        return report

    monkeypatch.setattr(closeout_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(closeout_mod, "_run_command", _fake_run_command)
    monkeypatch.setattr(
        closeout_mod,
        "fetch_api_active_order_ids_by_store",
        lambda **_kwargs: {"UNIVERSAL": {"1001"}},
    )
    monkeypatch.setattr(closeout_mod, "send_owner_ops_alert", lambda **_kwargs: True)
    monkeypatch.setattr(
        closeout_mod,
        "build_store_context_report",
        lambda **_kwargs: {"ok": True, "active_store_codes": ["UNIVERSAL"], "stores": [], "failure_count": 0},
    )

    rc = closeout_mod.main(
        [
            "--db-path",
            str(db_path),
            "--service-account-json",
            str(creds),
            "--spreadsheet-id",
            "sheet-id",
            "--target-date",
            "2026-04-15",
            "--expected-ready-set-at",
            "2026-04-15T18:10:00+05:00",
            "--run-root",
            str(tmp_path / "workflow_runs"),
            "--checkpoint-path",
            str(checkpoint_path),
            "--resume",
            "--json-out",
            str(tmp_path / "closeout_report.json"),
        ]
    )

    report = json.loads((tmp_path / "closeout_report.json").read_text(encoding="utf-8"))
    assert rc == 0
    assert report["resumed_from_checkpoint"] is True
    assert report["resumed_stages"] == ["size_writeback"]
    assert [step["name"] for step in report["steps"][:1]] == ["size_writeback"]
    assert report["steps"][0]["from_checkpoint"] is True
    assert calls == ["shipping", "download_waybills", "build_waybills"]


def test_closeout_resume_blocks_when_telegram_ledger_is_missing_after_attempt(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    _set_db_size(db_path)
    contract = load_ops_board_contract()
    creds = tmp_path / "svc.json"
    creds.write_text("{}", encoding="utf-8")

    salesraw_row = ["TODAY", "2026-04-15", "Universal", "", "", "1", "Nike", "1001", "L", "L", "Offer", "SKU-1", "1", "line", "DEFAULT", "LOW"]
    run_control_row = ["2026-04-15", "READY", "adil", "2026-04-15T18:10:00+05:00", "", "", "", ""]
    client = _FakeClient(
        {
            "Run_Control": [contract.tabs["Run_Control"].headers, run_control_row],
            "SalesRaw_Today": [contract.tabs["SalesRaw_Today"].headers, salesraw_row],
        }
    )

    prior_run_dir = tmp_path / "workflow_runs" / "2026-04-15" / "20260415_170000_2026-04-15_closeout"
    prior_run_dir.mkdir(parents=True, exist_ok=True)
    for stage in ("size_writeback", "shipping", "download_waybills", "build_waybills", "delivery_send"):
        step_report = {"name": stage, "command": [stage], "returncode": 0, "stdout": "", "stderr": "", "ok": True}
        (prior_run_dir / f"step_{stage}.json").write_text(json.dumps(step_report), encoding="utf-8")

    today_folder = tmp_path / "today"
    expected_payload = _expected_payload_for_order_1001()
    expected_path = prior_run_dir / "expected_closeout_orders.json"
    expected_path.write_text(
        json.dumps(expected_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _manifest_path, delivery_pin = _write_manifest_for_expected(
        expected_path=expected_path,
        today_folder=today_folder,
    )
    expected_sha256 = hashlib.sha256(expected_path.read_bytes()).hexdigest()

    checkpoint_path = tmp_path / "workflow_runs" / "2026-04-15" / "closeout_checkpoint.json"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(
        json.dumps(
            {
                "execution_mode": "apply",
                "target_date": "2026-04-15",
                "db_path": str(db_path.resolve()),
                "spreadsheet_id": "sheet-id",
                "service_account_json": str(creds.resolve()),
                "salesraw_writeback_fingerprint": closeout_mod.salesraw_writeback_fingerprint(
                    [dict(zip(contract.tabs["SalesRaw_Today"].headers, salesraw_row))]
                ),
                "run_control_resume_fingerprint": closeout_mod.run_control_resume_fingerprint(
                    dict(zip(contract.tabs["Run_Control"].headers, run_control_row))
                ),
                "required_orders": {
                    "path": str(expected_path.resolve()),
                    "sha256": expected_sha256,
                    "request_identity": expected_payload["request_identity"],
                    "line_scope_hash": expected_payload["line_scope_hash"],
                },
                "delivery_artifacts": delivery_pin,
                "stages": {
                    stage: {
                        "status": "ok",
                        "run_id": "20260415_170000_2026-04-15_closeout",
                        "step_report_path": str(prior_run_dir / f"step_{stage}.json"),
                    }
                    for stage in ("size_writeback", "shipping", "download_waybills", "build_waybills", "delivery_send")
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    calls: list[str] = []

    def _fake_run_command(*, name, command, env, report_path):
        calls.append(name)
        report = {"name": name, "command": command, "returncode": 0, "stdout": "", "stderr": "", "ok": True}
        report_path.write_text(json.dumps(report), encoding="utf-8")
        return report

    monkeypatch.setattr(closeout_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(closeout_mod, "_run_command", _fake_run_command)
    monkeypatch.setattr(closeout_mod, "send_owner_ops_alert", lambda **_kwargs: True)
    monkeypatch.setenv("ENABLE_GOOGLE_OPS_BOARD_CLOSEOUT", "1")
    monkeypatch.setattr(closeout_mod, "delivery_completion_state", lambda **_kwargs: {"completed": False, "status": "TELEGRAM_LEDGER_INCOMPLETE"})
    monkeypatch.setattr(
        closeout_mod,
        "ensure_prewindow_health",
        lambda **_kwargs: {"ok": True, "report_path": str(tmp_path / "prewindow.json")},
    )
    monkeypatch.setattr(
        closeout_mod,
        "fetch_api_active_order_ids_by_store",
        lambda **_kwargs: {"UNIVERSAL": {"1001"}},
    )
    monkeypatch.setattr(
        closeout_mod,
        "build_expected_orders_from_db",
        lambda **_kwargs: expected_payload,
    )
    monkeypatch.setattr(
        closeout_mod,
        "build_store_context_report",
        lambda **_kwargs: {"ok": True, "active_store_codes": ["UNIVERSAL"], "stores": [], "failure_count": 0},
    )

    rc = closeout_mod.main(
        [
            "--apply",
            "--db-path",
            str(db_path),
            "--service-account-json",
            str(creds),
            "--spreadsheet-id",
            "sheet-id",
            "--target-date",
            "2026-04-15",
            "--expected-ready-set-at",
            "2026-04-15T18:10:00+05:00",
            "--today-folder",
            str(today_folder),
            "--run-root",
            str(tmp_path / "workflow_runs"),
            "--checkpoint-path",
            str(checkpoint_path),
            "--resume",
            "--json-out",
            str(tmp_path / "closeout_report.json"),
        ]
    )

    report = json.loads((tmp_path / "closeout_report.json").read_text(encoding="utf-8"))
    assert rc == 1
    assert report["failure_stage"] == "checkpoint"
    assert report["failure_reason"] == "telegram_send_ledger_missing_after_attempt"
    assert calls == []


def test_closeout_resume_reuses_completed_shipped_truth_sync_checkpoint(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    _set_db_size(db_path)
    contract = load_ops_board_contract()
    creds = tmp_path / "svc.json"
    creds.write_text("{}", encoding="utf-8")

    salesraw_row = ["TODAY", "2026-04-15", "Universal", "", "", "1", "Nike", "1001", "L", "L", "Offer", "SKU-1", "1", "line", "DEFAULT", "LOW"]
    run_control_row = ["2026-04-15", "READY", "adil", "2026-04-15T18:10:00+05:00", "", "", "", ""]
    client = _FakeClient(
        {
            "Run_Control": [contract.tabs["Run_Control"].headers, run_control_row],
            "SalesRaw_Today": [contract.tabs["SalesRaw_Today"].headers, salesraw_row],
        }
    )

    prior_run_dir = tmp_path / "workflow_runs" / "2026-04-15" / "20260415_170000_2026-04-15_closeout"
    prior_run_dir.mkdir(parents=True, exist_ok=True)
    checkpointed_stages = (
        "size_writeback",
        "shipping",
        "download_waybills",
        "build_waybills",
        "delivery_send",
        "shipped_truth_sync",
    )
    for stage in checkpointed_stages:
        step_report = {"name": stage, "command": [stage], "returncode": 0, "stdout": "", "stderr": "", "ok": True}
        (prior_run_dir / f"step_{stage}.json").write_text(json.dumps(step_report), encoding="utf-8")

    today_folder = tmp_path / "today"
    expected_payload = _expected_payload_for_order_1001()
    expected_path = prior_run_dir / "expected_closeout_orders.json"
    expected_path.write_text(
        json.dumps(expected_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _manifest_path, delivery_pin = _write_manifest_for_expected(
        expected_path=expected_path,
        today_folder=today_folder,
        telegram_ledger_state="confirmed",
    )
    expected_sha256 = hashlib.sha256(expected_path.read_bytes()).hexdigest()

    checkpoint_path = tmp_path / "workflow_runs" / "2026-04-15" / "closeout_checkpoint.json"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(
        json.dumps(
            {
                "execution_mode": "apply",
                "target_date": "2026-04-15",
                "db_path": str(db_path.resolve()),
                "spreadsheet_id": "sheet-id",
                "service_account_json": str(creds.resolve()),
                "salesraw_writeback_fingerprint": closeout_mod.salesraw_writeback_fingerprint(
                    [dict(zip(contract.tabs["SalesRaw_Today"].headers, salesraw_row))]
                ),
                "run_control_resume_fingerprint": closeout_mod.run_control_resume_fingerprint(
                    dict(zip(contract.tabs["Run_Control"].headers, run_control_row))
                ),
                "required_orders": {
                    "path": str(expected_path.resolve()),
                    "sha256": expected_sha256,
                    "request_identity": expected_payload["request_identity"],
                    "line_scope_hash": expected_payload["line_scope_hash"],
                },
                "delivery_artifacts": delivery_pin,
                "stages": {
                    stage: {
                        "status": "ok",
                        "run_id": "20260415_170000_2026-04-15_closeout",
                        "step_report_path": str(prior_run_dir / f"step_{stage}.json"),
                    }
                    for stage in checkpointed_stages
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    calls: list[str] = []

    def _fake_run_command(*, name, command, env, report_path):
        calls.append(name)
        report = {"name": name, "command": command, "returncode": 0, "stdout": "", "stderr": "", "ok": True}
        report_path.write_text(json.dumps(report), encoding="utf-8")
        return report

    monkeypatch.setenv("ENABLE_GOOGLE_OPS_BOARD_CLOSEOUT", "1")
    monkeypatch.setattr(closeout_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(closeout_mod, "_run_command", _fake_run_command)
    monkeypatch.setattr(closeout_mod, "send_owner_ops_alert", lambda **_kwargs: True)
    monkeypatch.setattr(closeout_mod, "delivery_completion_state", lambda **_kwargs: {"completed": True, "status": "TELEGRAM_CONFIRMED"})
    monkeypatch.setattr(
        closeout_mod,
        "ensure_prewindow_health",
        lambda **_kwargs: {"ok": True, "report_path": str(tmp_path / "prewindow.json")},
    )
    monkeypatch.setattr(
        closeout_mod,
        "fetch_api_active_order_ids_by_store",
        lambda **_kwargs: {"UNIVERSAL": {"1001"}},
    )
    monkeypatch.setattr(
        closeout_mod,
        "build_expected_orders_from_db",
        lambda **_kwargs: expected_payload,
    )
    monkeypatch.setattr(
        closeout_mod,
        "build_store_context_report",
        lambda **_kwargs: {"ok": True, "active_store_codes": ["UNIVERSAL"], "stores": [], "failure_count": 0},
    )

    rc = closeout_mod.main(
        [
            "--apply",
            "--db-path",
            str(db_path),
            "--service-account-json",
            str(creds),
            "--spreadsheet-id",
            "sheet-id",
            "--target-date",
            "2026-04-15",
            "--expected-ready-set-at",
            "2026-04-15T18:10:00+05:00",
            "--today-folder",
            str(today_folder),
            "--run-root",
            str(tmp_path / "workflow_runs"),
            "--checkpoint-path",
            str(checkpoint_path),
            "--resume",
            "--json-out",
            str(tmp_path / "closeout_report.json"),
        ]
    )

    report = json.loads((tmp_path / "closeout_report.json").read_text(encoding="utf-8"))
    assert rc == 0
    assert report["resumed_stages"] == list(checkpointed_stages)
    assert calls == []


def test_closeout_resume_keeps_external_checkpoint_when_only_run_control_status_drifted(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    _set_db_size(db_path)
    contract = load_ops_board_contract()
    creds = tmp_path / "svc.json"
    creds.write_text("{}", encoding="utf-8")

    salesraw_row = ["TODAY", "2026-04-15", "Universal", "", "", "1", "Nike", "1001", "L", "L", "Offer", "SKU-1", "1", "line", "DEFAULT", "LOW"]
    checkpoint_run_control = ["2026-04-15", "READY", "adil", "2026-04-15T17:00:00+05:00", "", "", "", ""]
    current_run_control = [
        "2026-04-15",
        "READY",
        "adil",
        "2026-04-15T17:00:00+05:00",
        "BLOCKED_MISSING_SIZES: fixed later",
        "2026-04-15T17:20:00+05:00",
        "old-run",
        "BLOCKED_MISSING_SIZES",
    ]
    client = _FakeClient(
        {
            "Run_Control": [contract.tabs["Run_Control"].headers, current_run_control],
            "SalesRaw_Today": [contract.tabs["SalesRaw_Today"].headers, salesraw_row],
        }
    )

    prior_run_dir = tmp_path / "workflow_runs" / "2026-04-15" / "20260415_170000_2026-04-15_closeout"
    prior_run_dir.mkdir(parents=True, exist_ok=True)
    for stage in ("size_writeback", "shipping"):
        step_report = {"name": stage, "command": [stage], "returncode": 0, "stdout": "", "stderr": "", "ok": True}
        (prior_run_dir / f"step_{stage}.json").write_text(json.dumps(step_report), encoding="utf-8")

    checkpoint_path = tmp_path / "workflow_runs" / "2026-04-15" / "closeout_checkpoint.json"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(
        json.dumps(
            {
                "execution_mode": "dry_run",
                "target_date": "2026-04-15",
                "db_path": str(db_path.resolve()),
                "spreadsheet_id": "sheet-id",
                "service_account_json": str(creds.resolve()),
                "salesraw_writeback_fingerprint": closeout_mod.salesraw_writeback_fingerprint(
                    [dict(zip(contract.tabs["SalesRaw_Today"].headers, salesraw_row))]
                ),
                "run_control_row_hash": closeout_mod._hash_run_control_row(
                    dict(zip(contract.tabs["Run_Control"].headers, checkpoint_run_control))
                ),
                "run_control_resume_fingerprint": closeout_mod.run_control_resume_fingerprint(
                    dict(zip(contract.tabs["Run_Control"].headers, checkpoint_run_control))
                ),
                "stages": {
                    "size_writeback": {
                        "status": "ok",
                        "step_report_path": str(prior_run_dir / "step_size_writeback.json"),
                    },
                    "shipping": {
                        "status": "ok",
                        "step_report_path": str(prior_run_dir / "step_shipping.json"),
                    },
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    calls: list[str] = []

    def _fake_run_command(*, name, command, env, report_path):
        calls.append(name)
        report = {"name": name, "command": command, "returncode": 0, "stdout": "", "stderr": "", "ok": True}
        report_path.write_text(json.dumps(report), encoding="utf-8")
        return report

    monkeypatch.setattr(closeout_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(closeout_mod, "_run_command", _fake_run_command)
    monkeypatch.setattr(
        closeout_mod,
        "fetch_api_active_order_ids_by_store",
        lambda **_kwargs: {"UNIVERSAL": {"1001"}},
    )
    monkeypatch.setattr(closeout_mod, "send_owner_ops_alert", lambda **_kwargs: True)
    monkeypatch.setattr(
        closeout_mod,
        "build_store_context_report",
        lambda **_kwargs: {"ok": True, "active_store_codes": ["UNIVERSAL"], "stores": [], "failure_count": 0},
    )

    rc = closeout_mod.main(
        [
            "--db-path",
            str(db_path),
            "--service-account-json",
            str(creds),
            "--spreadsheet-id",
            "sheet-id",
            "--target-date",
            "2026-04-15",
            "--run-root",
            str(tmp_path / "workflow_runs"),
            "--checkpoint-path",
            str(checkpoint_path),
            "--resume",
            "--json-out",
            str(tmp_path / "closeout_report.json"),
        ]
    )

    report = json.loads((tmp_path / "closeout_report.json").read_text(encoding="utf-8"))
    assert rc == 0
    assert report["resumed_stages"] == ["size_writeback"]
    assert calls == ["shipping", "download_waybills", "build_waybills"]


def test_closeout_resume_fails_closed_on_checkpoint_mismatch(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    contract = load_ops_board_contract()
    creds = tmp_path / "svc.json"
    creds.write_text("{}", encoding="utf-8")
    client = _FakeClient(
        {
            "Run_Control": [contract.tabs["Run_Control"].headers, ["2026-04-15", "READY", "adil", "2026-04-15T17:00:00+05:00", "", "", "", ""]],
            "SalesRaw_Today": [contract.tabs["SalesRaw_Today"].headers, ["TODAY", "2026-04-15", "Universal", "", "", "1", "Nike", "1001", "L", "L", "Offer", "SKU-1", "1", "line", "DEFAULT", "LOW"]],
        }
    )

    checkpoint_path = tmp_path / "workflow_runs" / "2026-04-15" / "closeout_checkpoint.json"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(
        json.dumps(
            {
                "execution_mode": "apply",
                "target_date": "2026-04-15",
                "db_path": str(db_path.resolve()),
                "spreadsheet_id": "wrong-sheet-id",
                "service_account_json": str(creds.resolve()),
                "salesraw_writeback_fingerprint": "abc",
                "run_control_row_hash": "xyz",
                "stages": {},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("ENABLE_GOOGLE_OPS_BOARD_CLOSEOUT", "1")
    monkeypatch.setattr(closeout_mod.GoogleOpsBoardClient, "from_service_account_file", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(closeout_mod, "ensure_prewindow_health", lambda **_kwargs: {"ok": True, "report_path": str(tmp_path / "prewindow.json")})
    monkeypatch.setattr(closeout_mod, "send_owner_ops_alert", lambda **_kwargs: True)

    rc = closeout_mod.main(
        [
            "--apply",
            "--db-path",
            str(db_path),
            "--service-account-json",
            str(creds),
            "--spreadsheet-id",
            "sheet-id",
            "--target-date",
            "2026-04-15",
            "--expected-ready-set-at",
            "2026-04-15T17:00:00+05:00",
            "--run-root",
            str(tmp_path / "workflow_runs"),
            "--checkpoint-path",
            str(checkpoint_path),
            "--resume",
            "--json-out",
            str(tmp_path / "closeout_report.json"),
        ]
    )

    report = json.loads((tmp_path / "closeout_report.json").read_text(encoding="utf-8"))
    assert rc == 1
    assert report["failure_stage"] == "checkpoint"
    assert report["failure_reason"] == "checkpoint_spreadsheet_id_mismatch"
    assert client.get_tab_values("Run_Control")[1][1] == "READY"
    assert client.get_tab_values("Run_Control")[1][-1] == "FAILED_CHECKPOINT"


def test_closeout_main_loads_repo_dotenv_before_run(monkeypatch):
    seen: dict[str, object] = {}

    monkeypatch.setattr(
        closeout_mod,
        "load_dotenv",
        lambda path, override=False: seen.update({"path": Path(path), "override": override}),
    )
    monkeypatch.setattr(closeout_mod, "_run_closeout", lambda _args: 0)

    rc = closeout_mod.main([])

    assert rc == 0
    assert seen["path"] == closeout_mod.DEFAULT_DOTENV_PATH
    assert seen["override"] is False


def test_closeout_main_apply_acquires_internal_lock_when_not_preheld(monkeypatch):
    seen: dict[str, object] = {"lock_entered": 0, "lock_exited": 0, "held_env": None}

    class _FakeLock:
        def __enter__(self):
            seen["lock_entered"] = int(seen["lock_entered"]) + 1
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            seen["lock_exited"] = int(seen["lock_exited"]) + 1
            return False

    monkeypatch.delenv(closeout_mod.AUTOMATION_LOCK_HELD_ENV, raising=False)
    monkeypatch.setattr(closeout_mod, "GoogleOpsBoardAutomationLock", _FakeLock)

    def _fake_run_closeout(_args):
        seen["held_env"] = closeout_mod.os.environ.get(closeout_mod.AUTOMATION_LOCK_HELD_ENV)
        return 0

    monkeypatch.setattr(closeout_mod, "_run_closeout", _fake_run_closeout)

    rc = closeout_mod.main(["--apply"])

    assert rc == 0
    assert seen["lock_entered"] == 1
    assert seen["lock_exited"] == 1
    assert seen["held_env"] == "1"


def test_closeout_main_apply_skips_internal_lock_when_preheld(monkeypatch):
    seen: dict[str, object] = {"lock_entered": 0, "held_env": None}

    class _FakeLock:
        def __enter__(self):
            seen["lock_entered"] = int(seen["lock_entered"]) + 1
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    monkeypatch.setenv(closeout_mod.AUTOMATION_LOCK_HELD_ENV, "1")
    monkeypatch.setattr(closeout_mod, "GoogleOpsBoardAutomationLock", _FakeLock)

    def _fake_run_closeout(_args):
        seen["held_env"] = closeout_mod.os.environ.get(closeout_mod.AUTOMATION_LOCK_HELD_ENV)
        return 0

    monkeypatch.setattr(closeout_mod, "_run_closeout", _fake_run_closeout)

    rc = closeout_mod.main(["--apply"])

    assert rc == 0
    assert seen["lock_entered"] == 0
    assert seen["held_env"] == "1"
