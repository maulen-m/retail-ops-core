from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from scripts import run_google_ops_board_closeout as closeout_mod
from core.integrations.google_ops_board import load_ops_board_contract


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
        INSERT INTO fact_orders_kaspi (id, order_id, store_code, assigned_size, sku_key, planned_shipment_date)
        VALUES (1, '1001', 'UNIVERSAL', '', 'SKU-1', '2026-04-15')
        """
    )
    conn.commit()
    conn.close()


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

    seen_health: dict[str, object] = {}

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

    def _fake_run_command(*, name, command, env, report_path):
        calls.append(name)
        if "--output-json" in command:
            json_path = Path(command[command.index("--output-json") + 1])
            if name == "size_writeback":
                json_path.write_text(
                    json.dumps(
                        {
                            "db_backup_path": None,
                            "updates_applied": 0,
                            "updates_count": 1,
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
    assert report["steps"][-1]["name"] == "delivery_preflight"
    assert report["steps"][-1]["skipped"] is True


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
            "--run-root",
            str(tmp_path / "workflow_runs"),
            "--json-out",
            str(tmp_path / "closeout_report.json"),
        ]
    )

    report = json.loads((tmp_path / "closeout_report.json").read_text(encoding="utf-8"))
    assert rc == 1
    assert report["failure_stage"] == "store_context"
    assert calls == ["size_writeback"]
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
            batch_root = today_folder / "MERGED" / "SEND" / "test_batch"
            batch_root.mkdir(parents=True, exist_ok=True)
            (batch_root / "send_batch_manifest.json").write_text(
                json.dumps(
                    {
                        "target_date": "2026-04-15",
                        "counts": {"pdfs": 1, "orders": 1, "overdue_orders": 0},
                        "send_order_ids": ["TODAY100"],
                        "overdue_order_ids": [],
                        "missing_overdue_order_ids": [],
                        "terminal_orders_excluded": True,
                        "entries": [
                            {
                                "pdf_key": "pdf-1",
                                "filename": "today.pdf",
                                "send_sequence": 1,
                                "order_ids": ["TODAY100"],
                                "order_counts_by_store": {"UNIVERSAL": 1},
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
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
    assert report["failure_stage"] == "expected_order_gate"
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
            batch_root = today_folder / "MERGED" / "SEND" / "test_batch"
            batch_root.mkdir(parents=True, exist_ok=True)
            (batch_root / "send_batch_manifest.json").write_text(
                json.dumps(
                    {
                        "target_date": "2026-04-15",
                        "counts": {"pdfs": 1, "orders": 1, "overdue_orders": 0},
                        "send_order_ids": ["TODAY100"],
                        "overdue_order_ids": [],
                        "missing_overdue_order_ids": [],
                        "terminal_orders_excluded": True,
                        "entries": [{"pdf_key": "pdf-1", "filename": "today.pdf", "order_ids": ["TODAY100"]}],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
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
    assert report["resumed_from_checkpoint"] is True
    assert report["resumed_stages"] == ["size_writeback", "shipping"]
    assert [step["name"] for step in report["steps"][:2]] == ["size_writeback", "shipping"]
    assert report["steps"][0]["from_checkpoint"] is True
    assert calls == ["download_waybills", "build_waybills"]


def test_closeout_resume_does_not_reuse_delivery_send_checkpoint_without_ledger_completion(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)
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
    batch_root = today_folder / "MERGED" / "SEND" / "test_batch"
    batch_root.mkdir(parents=True, exist_ok=True)
    (batch_root / "send_batch_manifest.json").write_text(
        json.dumps(
            {
                "target_date": "2026-04-15",
                "counts": {"orders": 1, "pdfs": 1},
                "send_order_ids": ["1001"],
                "entries": [{"pdf_key": "pdf-1", "filename": "bundle.pdf", "order_ids": ["1001"]}],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    checkpoint_path = tmp_path / "workflow_runs" / "2026-04-15" / "closeout_checkpoint.json"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(
        json.dumps(
            {
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
        lambda **_kwargs: {
            "expected_order_ids": ["1001"],
            "overdue_order_ids": [],
            "orders": [],
            "counts": {"orders": 1, "order_lines": 1, "overdue_orders": 0, "excluded_rows": 0},
            "counts_by_store": {"UNIVERSAL": 1},
            "counts_by_stage": {},
            "excluded_counts": {},
        },
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
    assert report["resumed_stages"] == ["size_writeback", "shipping", "download_waybills", "build_waybills"]
    assert calls == ["delivery_send", "shipped_truth_sync"]


def test_closeout_resume_reuses_completed_shipped_truth_sync_checkpoint(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    _make_db(db_path)
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

    checkpoint_path = tmp_path / "workflow_runs" / "2026-04-15" / "closeout_checkpoint.json"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(
        json.dumps(
            {
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
        lambda **_kwargs: {
            "expected_order_ids": ["1001"],
            "overdue_order_ids": [],
            "orders": [],
            "counts": {"orders": 1, "order_lines": 1, "overdue_orders": 0, "excluded_rows": 0},
            "counts_by_store": {"UNIVERSAL": 1},
            "counts_by_stage": {},
            "excluded_counts": {},
        },
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
    contract = load_ops_board_contract()
    creds = tmp_path / "svc.json"
    creds.write_text("{}", encoding="utf-8")

    salesraw_row = ["TODAY", "2026-04-15", "Universal", "", "", "1", "Nike", "1001", "L", "L", "Offer", "SKU-1", "1", "line", "DEFAULT", "LOW"]
    checkpoint_run_control = ["2026-04-15", "READY", "adil", "", "", "", "", ""]
    current_run_control = [
        "2026-04-15",
        "READY",
        "adil",
        "",
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
    assert report["resumed_stages"] == ["size_writeback", "shipping"]
    assert "shipping" not in calls
    assert calls == ["download_waybills", "build_waybills"]


def test_closeout_resume_fails_closed_on_checkpoint_mismatch(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "app.db"
    _make_db(db_path)
    contract = load_ops_board_contract()
    creds = tmp_path / "svc.json"
    creds.write_text("{}", encoding="utf-8")
    client = _FakeClient(
        {
            "Run_Control": [contract.tabs["Run_Control"].headers, ["2026-04-15", "READY", "adil", "", "", "", "", ""]],
            "SalesRaw_Today": [contract.tabs["SalesRaw_Today"].headers, ["TODAY", "2026-04-15", "Universal", "", "", "1", "Nike", "1001", "L", "L", "Offer", "SKU-1", "1", "line", "DEFAULT", "LOW"]],
        }
    )

    checkpoint_path = tmp_path / "workflow_runs" / "2026-04-15" / "closeout_checkpoint.json"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(
        json.dumps(
            {
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
