import json
import sqlite3

from core.ops.customer_size_request import DEFAULT_REQUEST_TEMPLATE, request_template_hash
from scripts.run_kaspi_customer_chat_gateway_fixture import (
    APPROVAL_TOKEN,
    GREEN_CASES_GATE,
    GREEN_NO_SEND_GATE,
    GREEN_SEND_GATE,
    RED_UNSAFE_GATE,
    YELLOW_METADATA_GATE,
    YELLOW_BLOCKED_GATE,
    YELLOW_UNKNOWN_GATE,
    main as gateway_fixture_main,
    _default_fixture_shapes,
)


def _read_result(out_dir):
    return json.loads((out_dir / "gateway_fixture_result_redacted.json").read_text(encoding="utf-8"))


def _ledger_status(ledger_db, order_ref="sha256:fixture-order-ref"):
    with sqlite3.connect(ledger_db) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT *
            FROM kaspi_customer_chat_gateway_fixture_ledger
            WHERE order_ref = ?
            """,
            (order_ref,),
        ).fetchone()
    return dict(row)


def _safe_fixture_case(**overrides):
    case = {
        "case_id": "safe_command_build",
        "stage": "command_build",
        "target": {
            "order_ref": "sha256:aaaaaaaaaaaaaaaaaaaaaaaa",
            "db_row_id": 36170,
            "store_code": "ACMEWEAR",
            "expected_merchant_account_id": "30137883",
            "visible_merchant_account_id": "30137883",
            "template_hash": "b" * 64,
        },
        "command_flags": {
            "customer_send_allowed": False,
            "kaspi_chat_write_allowed": False,
            "chat_open_allowed": False,
            "message_text_typed": False,
            "message_sent": False,
        },
        "approval": {
            "env_gate_enabled": False,
            "exact_approval_marker_present": False,
            "approval_phrase_sha256": "",
        },
        "ledger_before": {
            "status": "NONE",
            "channel": "",
            "send_attempt_count": 0,
        },
        "transport_events": [],
        "expected": {
            "gate": "GREEN_RESIDENT_NO_SEND_COMMAND_PACKET_READY",
            "ledger_status_after": "SEND_PLANNED_NO_SEND",
            "sent_count": 0,
            "blockers": [],
            "redaction": {
                "raw_order_id_exported": False,
                "raw_customer_text_exported": False,
                "raw_phone_exported": False,
                "raw_session_material_exported": False,
                "cookie_token_session_exported": False,
            },
        },
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(case.get(key), dict):
            case[key] = {**case[key], **value}
        else:
            case[key] = value
    return case


def test_gateway_fixture_defaults_to_no_send_and_redacted_artifacts(tmp_path, capsys):
    ledger_db = tmp_path / "ledger.sqlite"
    out_dir = tmp_path / "out"

    rc = gateway_fixture_main(["--ledger-db", str(ledger_db), "--output-dir", str(out_dir)])
    capsys.readouterr()

    result = _read_result(out_dir)
    ledger = _ledger_status(ledger_db)
    combined = "\n".join(path.read_text(encoding="utf-8") for path in out_dir.glob("*"))
    assert rc == 0
    assert result["gate"] == GREEN_NO_SEND_GATE
    assert result["sent_count"] == 0
    assert result["external_network_performed"] is False
    assert ledger["status"] == "SEND_PLANNED_NO_SEND"
    assert DEFAULT_REQUEST_TEMPLATE not in combined


def test_gateway_fixture_default_shapes_use_live_confirmed_chat_api_base():
    shapes = _default_fixture_shapes()
    by_purpose = {shape["purpose"]: shape for shape in shapes}

    for purpose in ["startChat", "loadMoreMessages", "changeStatus", "sendMessage"]:
        shape = by_purpose[purpose]
        assert shape["host"] == "mc.shop.kaspi.kz"
        assert shape["path_template"].startswith("/chats/api/mobile/api/v1/")
        assert "/paychat/" not in shape["path_template"]
    assert by_purpose["websocket"]["host"] == "mc.shop.kaspi.kz"


def test_gateway_fixture_send_branch_requires_env_and_approval(tmp_path, capsys):
    ledger_db = tmp_path / "ledger.sqlite"
    out_dir = tmp_path / "out"

    rc = gateway_fixture_main(
        [
            "--ledger-db",
            str(ledger_db),
            "--output-dir",
            str(out_dir),
            "--mode",
            "send-simulated",
        ]
    )
    capsys.readouterr()

    result = _read_result(out_dir)
    assert rc == 0
    assert result["gate"] == YELLOW_BLOCKED_GATE
    assert "missing_env_gate:ENABLE_KASPI_CUSTOMER_CHAT_GATEWAY_FIXTURE_SEND" in result["blockers"]
    assert any(blocker.startswith("missing_approval_marker:") for blocker in result["blockers"])
    assert _ledger_status(ledger_db)["status"] == "SEND_PLANNED_NO_SEND"


def test_gateway_fixture_send_simulated_requires_both_gates_and_marks_request_sent(
    tmp_path, capsys, monkeypatch
):
    ledger_db = tmp_path / "ledger.sqlite"
    out_dir = tmp_path / "out"
    monkeypatch.setenv("ENABLE_KASPI_CUSTOMER_CHAT_GATEWAY_FIXTURE_SEND", "1")

    rc = gateway_fixture_main(
        [
            "--ledger-db",
            str(ledger_db),
            "--output-dir",
            str(out_dir),
            "--mode",
            "send-simulated",
            "--approval-phrase",
            f"I approve {APPROVAL_TOKEN}",
        ]
    )
    capsys.readouterr()

    result = _read_result(out_dir)
    ledger = _ledger_status(ledger_db)
    assert rc == 0
    assert result["gate"] == GREEN_SEND_GATE
    assert result["sent_count"] == 1
    assert result["customer_send_allowed"] is False
    assert result["kaspi_chat_write_allowed"] is False
    assert ledger["status"] == "REQUEST_SENT"
    assert ledger["send_attempt_count"] == 1


def test_gateway_fixture_blocks_duplicate_after_request_sent(tmp_path, capsys, monkeypatch):
    ledger_db = tmp_path / "ledger.sqlite"
    out_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    monkeypatch.setenv("ENABLE_KASPI_CUSTOMER_CHAT_GATEWAY_FIXTURE_SEND", "1")
    args = [
        "--ledger-db",
        str(ledger_db),
        "--mode",
        "send-simulated",
        "--approval-phrase",
        f"I approve {APPROVAL_TOKEN}",
    ]

    assert gateway_fixture_main([*args, "--output-dir", str(out_dir)]) == 0
    assert gateway_fixture_main([*args, "--output-dir", str(second_dir)]) == 0
    capsys.readouterr()

    result = _read_result(second_dir)
    assert result["gate"] == YELLOW_BLOCKED_GATE
    assert "prior_status_blocks_send:REQUEST_SENT" in result["blockers"]
    assert _ledger_status(ledger_db)["send_attempt_count"] == 1


def test_gateway_fixture_blocks_duplicate_from_different_channel(
    tmp_path, capsys, monkeypatch
):
    ledger_db = tmp_path / "ledger.sqlite"
    seed_dir = tmp_path / "seed"
    retry_dir = tmp_path / "retry"
    monkeypatch.setenv("ENABLE_KASPI_CUSTOMER_CHAT_GATEWAY_FIXTURE_SEND", "1")

    assert gateway_fixture_main(["--ledger-db", str(ledger_db), "--output-dir", str(seed_dir)]) == 0
    with sqlite3.connect(ledger_db) as conn:
        conn.execute(
            """
            UPDATE kaspi_customer_chat_gateway_fixture_ledger
            SET channel = 'KASPI_MERCHANT_CHAT_UI',
                status = 'REQUEST_SENT',
                send_attempt_count = 1
            """
        )
        conn.commit()

    rc = gateway_fixture_main(
        [
            "--ledger-db",
            str(ledger_db),
            "--output-dir",
            str(retry_dir),
            "--mode",
            "send-simulated",
            "--approval-phrase",
            f"I approve {APPROVAL_TOKEN}",
        ]
    )
    capsys.readouterr()

    result = _read_result(retry_dir)
    ledger = _ledger_status(ledger_db)
    assert rc == 0
    assert result["gate"] == YELLOW_BLOCKED_GATE
    assert "prior_status_blocks_send:REQUEST_SENT" in result["blockers"]
    assert ledger["channel"] == "KASPI_MERCHANT_CHAT_UI"
    assert ledger["send_attempt_count"] == 1


def test_gateway_fixture_timeout_records_unknown_and_blocks_retry(tmp_path, capsys, monkeypatch):
    ledger_db = tmp_path / "ledger.sqlite"
    out_dir = tmp_path / "timeout"
    retry_dir = tmp_path / "retry"
    monkeypatch.setenv("ENABLE_KASPI_CUSTOMER_CHAT_GATEWAY_FIXTURE_SEND", "1")
    args = [
        "--ledger-db",
        str(ledger_db),
        "--approval-phrase",
        f"I approve {APPROVAL_TOKEN}",
    ]

    rc = gateway_fixture_main([*args, "--output-dir", str(out_dir), "--mode", "timeout-simulated"])
    retry_rc = gateway_fixture_main([*args, "--output-dir", str(retry_dir), "--mode", "send-simulated"])
    capsys.readouterr()

    result = _read_result(out_dir)
    retry = _read_result(retry_dir)
    ledger = _ledger_status(ledger_db)
    assert rc == 0
    assert retry_rc == 0
    assert result["gate"] == YELLOW_UNKNOWN_GATE
    assert ledger["status"] == "UNKNOWN_SEND_OUTCOME"
    assert retry["gate"] == YELLOW_BLOCKED_GATE
    assert "prior_status_blocks_send:UNKNOWN_SEND_OUTCOME" in retry["blockers"]
    assert ledger["send_attempt_count"] == 1


def test_gateway_fixture_rejects_fixture_with_raw_values_or_secret_keys(tmp_path, capsys):
    ledger_db = tmp_path / "ledger.sqlite"
    out_dir = tmp_path / "out"
    fixture = tmp_path / "bad_fixture.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    "transport_shape_id": "bad",
                    "purpose": "sendMessage",
                    "method": "POST",
                    "host": "msg-web.kaspi.kz",
                    "path_template": "/paychat/api/v1/messages/sendMessage",
                    "field_names": ["order"],
                    "headers": {"authorization": "Bearer secret"},
                    "raw_order_id": "938710785",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rc = gateway_fixture_main(
        [
            "--ledger-db",
            str(ledger_db),
            "--output-dir",
            str(out_dir),
            "--fixture-json",
            str(fixture),
        ]
    )
    capsys.readouterr()

    result = _read_result(out_dir)
    assert rc == 2
    assert result["gate"] == RED_UNSAFE_GATE
    assert "shape_0_forbidden_key:headers" in result["blockers"]
    assert "shape_0_forbidden_key:raw_order_id" in result["blockers"]
    assert "raw_long_number_detected" in result["blockers"]


def test_gateway_fixture_template_hash_matches_core_helper(tmp_path, capsys):
    ledger_db = tmp_path / "ledger.sqlite"
    out_dir = tmp_path / "out"
    custom_template = "Добрый день"

    rc = gateway_fixture_main(
        [
            "--ledger-db",
            str(ledger_db),
            "--output-dir",
            str(out_dir),
            "--template-text",
            custom_template,
        ]
    )
    capsys.readouterr()

    result = _read_result(out_dir)
    assert rc == 0
    assert result["template_hash"] == request_template_hash(custom_template)
    assert custom_template not in (out_dir / "gateway_fixture_result_redacted.json").read_text(
        encoding="utf-8"
    )


def test_gateway_fixture_case_matrix_accepts_expected_green_yellow_and_red_cases(
    tmp_path, capsys
):
    ledger_db = tmp_path / "ledger.sqlite"
    out_dir = tmp_path / "out"
    cases_path = tmp_path / "cases.json"
    history_case = _safe_fixture_case(
        case_id="history_read_risk_yellow",
        stage="metadata_capture",
        transport_events=[
            {
                "kind": "request",
                "method": "POST",
                "host": "mc.shop.kaspi.kz",
                "path_template": "/chats/api/mobile/api/v1/history/loadMoreMessages",
                "route_family": "load_more_messages",
            }
        ],
        expected={
            "gate": YELLOW_METADATA_GATE,
            "ledger_status_after": "SEND_PLANNED_NO_SEND",
            "sent_count": 0,
            "blockers": [],
            "redaction": {
                "raw_order_id_exported": False,
                "raw_customer_text_exported": False,
                "raw_phone_exported": False,
                "raw_session_material_exported": False,
                "cookie_token_session_exported": False,
            },
        },
    )
    merchant_mismatch_case = _safe_fixture_case(
        case_id="merchant_mismatch_red",
        stage="no_click_selector",
        target={"visible_merchant_account_id": "30000001"},
        expected={
            "gate": RED_UNSAFE_GATE,
            "ledger_status_after": "SEND_PLANNED_NO_SEND",
            "sent_count": 0,
            "blockers": ["visible_merchant_selector_id_mismatch"],
            "redaction": {
                "raw_order_id_exported": False,
                "raw_customer_text_exported": False,
                "raw_phone_exported": False,
                "raw_session_material_exported": False,
                "cookie_token_session_exported": False,
            },
        },
    )
    cases_path.write_text(
        json.dumps(
            {"cases": [_safe_fixture_case(), history_case, merchant_mismatch_case]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rc = gateway_fixture_main(
        [
            "--ledger-db",
            str(ledger_db),
            "--output-dir",
            str(out_dir),
            "--fixture-cases-json",
            str(cases_path),
        ]
    )
    capsys.readouterr()

    result = _read_result(out_dir)
    by_case = {row["case_id"]: row for row in result["case_results"]}
    assert rc == 0
    assert result["gate"] == GREEN_CASES_GATE
    assert result["failed_cases"] == []
    assert by_case["safe_command_build"]["gate"] == "GREEN_RESIDENT_NO_SEND_COMMAND_PACKET_READY"
    assert by_case["history_read_risk_yellow"]["gate"] == YELLOW_METADATA_GATE
    assert by_case["merchant_mismatch_red"]["gate"] == RED_UNSAFE_GATE
    assert by_case["merchant_mismatch_red"]["blockers"] == [
        "visible_merchant_selector_id_mismatch"
    ]


def test_gateway_fixture_case_matrix_fails_on_unexpected_route_risk(tmp_path, capsys):
    ledger_db = tmp_path / "ledger.sqlite"
    out_dir = tmp_path / "out"
    cases_path = tmp_path / "cases.json"
    send_route_case = _safe_fixture_case(
        case_id="send_route_unexpected_green",
        stage="metadata_capture",
        transport_events=[
            {
                "kind": "request",
                "method": "POST",
                "host": "mc.shop.kaspi.kz",
                "path_template": "/chats/api/mobile/api/v1/messages/sendMessage",
                "route_family": "send_message_write_risk",
            }
        ],
        expected={
            "gate": "GREEN_CUSTOMER_CHAT_METADATA_CAPTURE_NO_SEND_NO_SECRET_EXPORT",
            "ledger_status_after": "SEND_PLANNED_NO_SEND",
            "sent_count": 0,
            "blockers": [],
            "redaction": {
                "raw_order_id_exported": False,
                "raw_customer_text_exported": False,
                "raw_phone_exported": False,
                "raw_session_material_exported": False,
                "cookie_token_session_exported": False,
            },
        },
    )
    cases_path.write_text(json.dumps({"cases": [send_route_case]}), encoding="utf-8")

    rc = gateway_fixture_main(
        [
            "--ledger-db",
            str(ledger_db),
            "--output-dir",
            str(out_dir),
            "--fixture-cases-json",
            str(cases_path),
        ]
    )
    capsys.readouterr()

    result = _read_result(out_dir)
    case_result = result["case_results"][0]
    assert rc == 2
    assert result["gate"] == "RED_KASPI_CUSTOMER_CHAT_GATEWAY_FIXTURE_CASES_FAILED"
    assert result["failed_cases"] == ["send_route_unexpected_green"]
    assert case_result["gate"] == "RED_CUSTOMER_CHAT_METADATA_CAPTURE_UNSAFE"
    assert "send_message_route_observed" in case_result["blockers"]
    assert case_result["expectation_mismatches"]


def test_gateway_fixture_case_matrix_blocks_prior_send_in_progress(tmp_path, capsys):
    ledger_db = tmp_path / "ledger.sqlite"
    out_dir = tmp_path / "out"
    cases_path = tmp_path / "cases.json"
    blocked_case = _safe_fixture_case(
        case_id="prior_send_in_progress_blocks_send",
        stage="send_simulated",
        approval={"env_gate_enabled": True, "exact_approval_marker_present": True},
        ledger_before={
            "status": "SEND_IN_PROGRESS",
            "channel": "KASPI_MERCHANT_CHAT_UI",
            "send_attempt_count": 1,
        },
        expected={
            "gate": YELLOW_BLOCKED_GATE,
            "ledger_status_after": "SEND_PLANNED_NO_SEND",
            "sent_count": 0,
            "blockers": ["prior_status_blocks_send:SEND_IN_PROGRESS"],
            "redaction": {
                "raw_order_id_exported": False,
                "raw_customer_text_exported": False,
                "raw_phone_exported": False,
                "raw_session_material_exported": False,
                "cookie_token_session_exported": False,
            },
        },
    )
    cases_path.write_text(json.dumps({"cases": [blocked_case]}), encoding="utf-8")

    rc = gateway_fixture_main(
        [
            "--ledger-db",
            str(ledger_db),
            "--output-dir",
            str(out_dir),
            "--fixture-cases-json",
            str(cases_path),
        ]
    )
    capsys.readouterr()

    result = _read_result(out_dir)
    assert rc == 0
    assert result["gate"] == GREEN_CASES_GATE
    assert result["case_results"][0]["gate"] == YELLOW_BLOCKED_GATE
    assert result["case_results"][0]["blockers"] == [
        "prior_status_blocks_send:SEND_IN_PROGRESS"
    ]
