import hashlib
import json
from argparse import Namespace
from pathlib import Path

import scripts.run_kaspi_customer_chat_resident_no_send_controller as resident
from scripts.enqueue_kaspi_customer_chat_resident_no_send_command import build_command
from scripts.run_kaspi_customer_chat_resident_no_send_controller import (
    COMMAND_ACTION_LOGIN_SMS_OTP,
    COMMAND_ACTION_UI_LIVE_SEND_CANARY,
    COMMAND_ACTION_UI_OPEN_CHAT_NO_TYPE_CANARY,
    COMMAND_ACTION_METADATA_CAPTURE,
    COMMAND_ACTION_UI_CHAT_BUTTON,
    COMMAND_ACTION_UI_SEARCH,
    COMMAND_ACTION_UI_OPEN_CHAT_SELECTOR_DOM_DIAGNOSTIC,
    GREEN_GATE,
    LIVE_SEND_DISABLED_GATE,
    LIVE_SEND_PREFLIGHT_READY_GATE,
    LIVE_SEND_TRANSPORT_PLAN_BLOCKED_GATE,
    LIVE_SEND_TRANSPORT_PLAN_READY_GATE,
    LIVE_SEND_UNSAFE_GATE,
    LOGIN_OTP_BLOCKED_GATE,
    LOGIN_OTP_FILLED_GATE,
    OPEN_CHAT_DISABLED_GATE,
    OPEN_CHAT_PREFLIGHT_READY_GATE,
    OPEN_CHAT_RESULT_GREEN_GATE,
    OPEN_CHAT_TRANSPORT_PLAN_BLOCKED_GATE,
    OPEN_CHAT_TRANSPORT_PLAN_READY_GATE,
    OPEN_CHAT_UNSAFE_GATE,
    SELECTOR_DOM_DIAGNOSTIC_GREEN_GATE,
    SELECTOR_DOM_DIAGNOSTIC_RED_GATE,
    SELECTOR_DOM_DIAGNOSTIC_YELLOW_GATE,
    SESSION_CLOSE_GUARD_BLOCKER,
    YELLOW_GATE,
    _build_open_chat_no_type_preflight_result,
    _build_live_send_preflight_result,
    _build_live_send_transport_plan,
    _heartbeat_payload,
    _route_flags_from_events,
    _run_open_chat_selector_dom_diagnostic_command,
    _run_open_chat_no_type_command,
    _run_login_sms_otp_command,
    build_parser,
    normalize_command,
)


def _write_open_chat_packet(tmp_path: Path) -> tuple[Path, Path]:
    packet_dir = tmp_path / "open_chat_packet"
    packet_dir.mkdir()
    lock_path = packet_dir / "open_chat_no_type_packet_lock.json"
    lock_payload = {
        "gate": "GREEN_OPEN_CHAT_NO_TYPE_CANARY_PACKET_READY_NO_SEND",
        "customer_send_allowed_now": False,
        "kaspi_chat_write_allowed_now": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
    }
    lock_path.write_text(json.dumps(lock_payload, ensure_ascii=False) + "\n", encoding="utf-8")
    phrase_path = packet_dir / "REQUIRED_EXACT_OPEN_CHAT_NO_TYPE_APPROVAL_PHRASE.txt"
    phrase_path.write_text("I approve exact open chat no type canary\n", encoding="utf-8")
    manifest_payload = {
        **lock_payload,
        "selected_order_ref": "sha256:3a507903190c4097e2d211ee",
        "selected_db_row_id": 36170,
        "selected_store_code": "ACMEWEAR",
        "selected_status_filter": "NEW",
        "expected_merchant_account_id": "30137883",
        "packet_manifest_path": str(lock_path),
        "packet_manifest_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
        "approval_phrase_generated": True,
    }
    (packet_dir / "manifest.json").write_text(
        json.dumps(manifest_payload, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return packet_dir, phrase_path


def test_normalize_command_defaults_to_no_send_ui_search(tmp_path):
    command = normalize_command(
        {},
        run_dir=tmp_path,
        profile_store_code="ACMEWEAR",
    )

    assert command["action"] == COMMAND_ACTION_UI_SEARCH
    assert command["profile_store_code"] == "ACMEWEAR"
    assert command["stores"] == "ACMEWEAR"
    assert command["max_candidates"] == 6
    assert str(tmp_path) in command["output_dir"]


def test_normalize_command_preserves_adjacent_status_sweep_without_raw_ids(tmp_path):
    command = normalize_command(
        {
            "command_id": "status_sweep",
            "target_date": "2026-06-17",
            "lookback_days": 4,
            "stores": "ACMEWEAR",
            "extra_status_filters": "NEW,KASPI_DELIVERY_WAIT_FOR_COURIER",
            "max_candidates": 12,
            "candidate_pool_limit": 8,
        },
        run_dir=tmp_path,
        profile_store_code="ACMEWEAR",
    )

    assert command["command_id"] == "status_sweep"
    assert command["target_date"] == "2026-06-17"
    assert command["extra_status_filters"] == "NEW,KASPI_DELIVERY_WAIT_FOR_COURIER"
    assert "raw_order" not in str(command)


def test_normalize_command_preserves_chat_button_no_open_action(tmp_path):
    command = normalize_command(
        {
            "command_id": "button_probe",
            "action": COMMAND_ACTION_UI_CHAT_BUTTON,
            "target_date": "2026-06-17",
            "stores": "ACMEWEAR",
            "max_candidates": 1,
        },
        run_dir=tmp_path,
        profile_store_code="ACMEWEAR",
    )

    assert command["action"] == COMMAND_ACTION_UI_CHAT_BUTTON
    assert command["max_candidates"] == 1
    assert command["profile_store_code"] == "ACMEWEAR"
    assert "raw_order" not in str(command)


def test_normalize_command_preserves_redacted_target_filters(tmp_path):
    command = normalize_command(
        {
            "command_id": "priority_target_button_probe",
            "action": COMMAND_ACTION_UI_CHAT_BUTTON,
            "target_date": "2026-06-18",
            "stores": "ACMEWEAR",
            "max_candidates": 1,
            "target_db_row_ids": "36170",
            "target_order_refs": "sha256:3a507903190c4097e2d211ee",
        },
        run_dir=tmp_path,
        profile_store_code="ACMEWEAR",
    )

    assert command["action"] == COMMAND_ACTION_UI_CHAT_BUTTON
    assert command["target_db_row_ids"] == "36170"
    assert command["target_order_refs"] == "sha256:3a507903190c4097e2d211ee"
    assert "raw_order" not in str(command)


def test_normalize_command_preserves_metadata_capture_action(tmp_path):
    command = normalize_command(
        {
            "command_id": "metadata_probe",
            "action": COMMAND_ACTION_METADATA_CAPTURE,
            "target_date": "2026-06-17",
            "stores": "ACMEWEAR",
            "max_candidates": 1,
        },
        run_dir=tmp_path,
        profile_store_code="ACMEWEAR",
    )

    assert command["action"] == COMMAND_ACTION_METADATA_CAPTURE
    assert command["max_candidates"] == 1
    assert command["profile_store_code"] == "ACMEWEAR"
    assert "raw_order" not in str(command)


def test_normalize_command_preserves_live_send_canary_gate_fields(tmp_path):
    command = normalize_command(
        {
            "command_id": "live_send_candidate",
            "action": COMMAND_ACTION_UI_LIVE_SEND_CANARY,
            "target_date": "2026-06-18",
            "stores": "ACMEWEAR",
            "max_candidates": 1,
            "target_db_row_ids": "36170",
            "target_order_refs": "sha256:3a507903190c4097e2d211ee",
            "approval_dir": "/tmp/approval",
            "live_send_execution_preflight_manifest": "/tmp/preflight.json",
            "expected_merchant_account_id": "30137883",
            "template_hash": "abc123",
            "template_text": "Добрый день",
            "allow_customer_send": True,
            "kaspi_chat_write_allowed": True,
            "chat_open_allowed": True,
            "message_text_typed": True,
            "message_sent": True,
        },
        run_dir=tmp_path,
        profile_store_code="ACMEWEAR",
    )

    assert command["action"] == COMMAND_ACTION_UI_LIVE_SEND_CANARY
    assert command["target_db_row_ids"] == "36170"
    assert command["expected_merchant_account_id"] == "30137883"
    assert command["allow_customer_send"] is True
    assert command["kaspi_chat_write_allowed"] is True
    assert command["chat_open_allowed"] is True
    assert command["message_text_typed"] is True
    assert command["message_sent"] is True
    assert "raw_order" not in str(command)


def test_normalize_command_preserves_login_sms_otp_no_secret_fields(tmp_path):
    command = normalize_command(
        {
            "command_id": "login_otp",
            "action": COMMAND_ACTION_LOGIN_SMS_OTP,
            "messages_db": str(tmp_path / "chat.db"),
            "otp_audit_json": str(tmp_path / "otp_audit.json"),
            "otp_window_minutes": 7,
            "otp_max_scan_rows": 11,
            "otp_submit_allowed": True,
        },
        run_dir=tmp_path,
        profile_store_code="ACMEWEAR",
    )

    assert command["action"] == COMMAND_ACTION_LOGIN_SMS_OTP
    assert command["messages_db"] == str(tmp_path / "chat.db")
    assert command["otp_audit_json"] == str(tmp_path / "otp_audit.json")
    assert command["otp_window_minutes"] == 7
    assert command["otp_max_scan_rows"] == 11
    assert command["otp_submit_allowed"] is True
    assert command["allow_customer_send"] is False
    assert command["kaspi_chat_write_allowed"] is False
    assert command["chat_open_allowed"] is False
    assert command["message_text_typed"] is False
    assert command["message_sent"] is False
    assert "raw_order" not in str(command)


def test_normalize_command_preserves_open_chat_no_type_fields_without_send(tmp_path):
    command = normalize_command(
        {
            "command_id": "open_chat_no_type",
            "action": COMMAND_ACTION_UI_OPEN_CHAT_NO_TYPE_CANARY,
            "stores": "ACMEWEAR",
            "max_candidates": 1,
            "target_db_row_ids": "36170",
            "target_order_refs": "sha256:3a507903190c4097e2d211ee",
            "expected_merchant_account_id": "30137883",
            "open_chat_packet_dir": str(tmp_path / "packet"),
            "open_chat_approval_text_file": str(tmp_path / "approval.txt"),
            "chat_open_allowed": True,
        },
        run_dir=tmp_path,
        profile_store_code="ACMEWEAR",
    )

    assert command["action"] == COMMAND_ACTION_UI_OPEN_CHAT_NO_TYPE_CANARY
    assert command["target_db_row_ids"] == "36170"
    assert command["expected_merchant_account_id"] == "30137883"
    assert command["open_chat_packet_dir"] == str(tmp_path / "packet")
    assert command["open_chat_approval_text_file"] == str(tmp_path / "approval.txt")
    assert command["chat_open_allowed"] is True
    assert command["allow_customer_send"] is False
    assert command["kaspi_chat_write_allowed"] is False
    assert command["message_text_typed"] is False
    assert command["message_sent"] is False
    assert "raw_order" not in str(command)


def test_heartbeat_payload_is_no_send_and_keeps_browser_open(tmp_path):
    payload = _heartbeat_payload(
        gate=GREEN_GATE,
        run_dir=tmp_path,
        persistent_profile_dir=tmp_path / "profile",
        profile_store_code="ACMEWEAR",
        commands_dir=tmp_path / "command_queue",
    )

    assert payload["browser_should_remain_open"] is True
    assert payload["session_close_requires_explicit_allow_session_close"] is True
    assert payload["customer_send_allowed"] is False
    assert payload["kaspi_chat_write_allowed"] is False
    assert payload["chat_opened"] is False
    assert payload["message_sent"] is False
    assert payload["raw_session_material_exported"] is False


def test_resident_controller_once_requires_explicit_session_close_flag():
    parser = build_parser()

    guarded = parser.parse_args(["--once"])
    allowed = parser.parse_args(["--once", "--allow-session-close"])

    assert guarded.once is True
    assert guarded.allow_session_close is False
    assert allowed.once is True
    assert allowed.allow_session_close is True
    assert SESSION_CLOSE_GUARD_BLOCKER == "session_close_requires_explicit_allow_session_close"
    assert guarded.enable_live_send_canary is False
    assert guarded.idle_heartbeat_seconds == 60.0


def test_live_send_canary_command_is_disabled_by_default(tmp_path):
    command = normalize_command(
        {
            "command_id": "live_send_candidate",
            "action": COMMAND_ACTION_UI_LIVE_SEND_CANARY,
            "stores": "ACMEWEAR",
            "max_candidates": 1,
            "target_db_row_ids": "36170",
            "target_order_refs": "sha256:3a507903190c4097e2d211ee",
            "approval_dir": str(tmp_path / "approval"),
            "live_send_execution_preflight_manifest": str(tmp_path / "preflight.json"),
            "expected_merchant_account_id": "30137883",
            "template_hash": "abc123",
            "template_text": "Добрый день",
            "allow_customer_send": True,
            "kaspi_chat_write_allowed": True,
            "chat_open_allowed": True,
            "message_text_typed": True,
            "message_sent": True,
        },
        run_dir=tmp_path,
        profile_store_code="ACMEWEAR",
    )

    result = _build_live_send_preflight_result(
        command=command,
        enable_live_send_canary=False,
    )

    assert result["gate"] == LIVE_SEND_DISABLED_GATE
    assert "controller_live_send_canary_not_enabled" in result["blockers"]
    assert result["customer_send_performed"] is False
    assert result["message_sent"] is False


def test_live_send_canary_command_rejects_missing_exact_write_flags(tmp_path):
    command = normalize_command(
        {
            "command_id": "live_send_candidate",
            "action": COMMAND_ACTION_UI_LIVE_SEND_CANARY,
            "stores": "ACMEWEAR",
            "target_db_row_ids": "36170",
            "target_order_refs": "sha256:3a507903190c4097e2d211ee",
            "approval_dir": str(tmp_path / "approval"),
            "live_send_execution_preflight_manifest": str(tmp_path / "preflight.json"),
            "expected_merchant_account_id": "30137883",
            "template_hash": "abc123",
            "template_text": "Добрый день",
            "allow_customer_send": False,
        },
        run_dir=tmp_path,
        profile_store_code="ACMEWEAR",
    )

    result = _build_live_send_preflight_result(
        command=command,
        enable_live_send_canary=True,
    )

    assert result["gate"] == LIVE_SEND_UNSAFE_GATE
    assert "command_allow_customer_send_not_true" in result["unsafe_blockers"]
    assert "command_kaspi_chat_write_allowed_not_true" in result["unsafe_blockers"]
    assert result["customer_send_performed"] is False


def test_live_send_canary_command_green_preflight_when_everything_matches(tmp_path):
    approval_dir = tmp_path / "approval"
    approval_dir.mkdir()
    preflight_path = tmp_path / "preflight.json"
    approval_manifest = {
        "gate": "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND",
        "selected_order_ref": "sha256:3a507903190c4097e2d211ee",
        "selected_db_row_id": 36170,
        "selected_store_code": "ACMEWEAR",
        "expected_merchant_account_id": "30137883",
        "template_hash": "abc123",
    }
    (approval_dir / "manifest.json").write_text(
        __import__("json").dumps(approval_manifest, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    preflight_path.write_text(
        __import__("json").dumps(
            {
                **approval_manifest,
                "gate": "GREEN_LIVE_SEND_CANARY_EXECUTION_PREFLIGHT_READY_NO_SEND",
                "owner_approval_text_match": True,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    command = normalize_command(
        {
            "command_id": "live_send_candidate",
            "action": COMMAND_ACTION_UI_LIVE_SEND_CANARY,
            "stores": "ACMEWEAR",
            "profile_store_code": "ACMEWEAR",
            "max_candidates": 1,
            "target_db_row_ids": "36170",
            "target_order_refs": "sha256:3a507903190c4097e2d211ee",
            "approval_dir": str(approval_dir),
            "live_send_execution_preflight_manifest": str(preflight_path),
            "expected_merchant_account_id": "30137883",
            "template_hash": "abc123",
            "template_text": "Добрый день",
            "allow_customer_send": True,
            "kaspi_chat_write_allowed": True,
            "chat_open_allowed": True,
            "message_text_typed": True,
            "message_sent": True,
        },
        run_dir=tmp_path,
        profile_store_code="ACMEWEAR",
    )

    result = _build_live_send_preflight_result(
        command=command,
        enable_live_send_canary=True,
    )

    assert result["gate"] == LIVE_SEND_PREFLIGHT_READY_GATE
    assert result["blockers"] == []
    assert result["unsafe_blockers"] == []
    assert result["customer_send_performed"] is False
    assert result["message_sent"] is False
    assert result["transport_plan"]["gate"] == LIVE_SEND_TRANSPORT_PLAN_READY_GATE
    assert result["transport_plan"]["expected_merchant_selector_text"] == "ID - 30137883"
    assert result["transport_plan"]["message_sent"] is False
    assert "raw_order_id" in result["transport_plan"]["runtime_only_values"]
    assert "Добрый" not in str(result["transport_plan"])


def test_live_send_transport_plan_blocks_if_preflight_not_green(tmp_path):
    command = normalize_command(
        {
            "command_id": "live_send_candidate",
            "action": COMMAND_ACTION_UI_LIVE_SEND_CANARY,
            "stores": "ACMEWEAR",
            "max_candidates": 1,
            "target_db_row_ids": "36170",
            "target_order_refs": "sha256:3a507903190c4097e2d211ee",
            "expected_merchant_account_id": "30137883",
            "template_hash": "abc123",
        },
        run_dir=tmp_path,
        profile_store_code="ACMEWEAR",
    )

    plan = _build_live_send_transport_plan(
        command=command,
        preflight_result={
            "gate": LIVE_SEND_DISABLED_GATE,
            "selected_order_ref": "sha256:3a507903190c4097e2d211ee",
            "selected_db_row_id": "36170",
            "selected_store_code": "ACMEWEAR",
        },
    )

    assert plan["gate"] == LIVE_SEND_TRANSPORT_PLAN_BLOCKED_GATE
    assert plan["blockers"] == ["live_send_preflight_not_green"]
    assert plan["message_sent"] is False


def test_live_send_transport_plan_is_selector_scoped_and_redacted(tmp_path):
    command = normalize_command(
        {
            "command_id": "live_send_candidate",
            "action": COMMAND_ACTION_UI_LIVE_SEND_CANARY,
            "stores": "ACMEWEAR",
            "extra_status_filters": "NEW,KASPI_DELIVERY_WAIT_FOR_COURIER",
            "max_candidates": 1,
            "target_db_row_ids": "36170",
            "target_order_refs": "sha256:3a507903190c4097e2d211ee",
            "expected_merchant_account_id": "30137883",
            "template_hash": "abc123",
            "template_text": "Добрый день",
        },
        run_dir=tmp_path,
        profile_store_code="ACMEWEAR",
    )

    plan = _build_live_send_transport_plan(
        command=command,
        preflight_result={
            "gate": LIVE_SEND_PREFLIGHT_READY_GATE,
            "selected_order_ref": "sha256:3a507903190c4097e2d211ee",
            "selected_db_row_id": "36170",
            "selected_store_code": "ACMEWEAR",
            "selected_status_filter": "NEW",
        },
    )

    assert plan["gate"] == LIVE_SEND_TRANSPORT_PLAN_READY_GATE
    assert plan["expected_merchant_selector_text"] == "ID - 30137883"
    assert plan["order_search_input_selector"] == "input[placeholder='Номер заказа']"
    assert plan["chat_button_selector"] == "button.init-chat-button.chat-section[type='CLIENT_SELLER_BY_ORDER']"
    assert "NEW" in plan["status_filter_candidates"]
    assert "KASPI_DELIVERY_WAIT_FOR_COURIER" in plan["status_filter_candidates"]
    assert "resolve_raw_order_id_runtime_only_from_db_row_or_order_ref" in plan["steps"]
    assert "send_once" in plan["steps"]
    assert "visible_merchant_selector_not_exact_expected_id" in plan["stoplines"]
    assert plan["redaction_policy"]["raw_order_id_exported"] is False
    assert plan["message_text_typed"] is False
    assert plan["message_sent"] is False
    assert "938710785" not in str(plan)
    assert "Добрый день" not in str(plan)


def test_open_chat_no_type_command_is_disabled_by_default(tmp_path):
    packet_dir, phrase_path = _write_open_chat_packet(tmp_path)
    command = normalize_command(
        {
            "command_id": "open_chat_no_type",
            "action": COMMAND_ACTION_UI_OPEN_CHAT_NO_TYPE_CANARY,
            "stores": "ACMEWEAR",
            "profile_store_code": "ACMEWEAR",
            "max_candidates": 1,
            "target_db_row_ids": "36170",
            "target_order_refs": "sha256:3a507903190c4097e2d211ee",
            "expected_merchant_account_id": "30137883",
            "open_chat_packet_dir": str(packet_dir),
            "open_chat_approval_text_file": str(phrase_path),
            "chat_open_allowed": True,
        },
        run_dir=tmp_path,
        profile_store_code="ACMEWEAR",
    )

    result = _build_open_chat_no_type_preflight_result(
        command=command,
        enable_open_chat_no_type_canary=False,
    )

    assert result["gate"] == OPEN_CHAT_DISABLED_GATE
    assert "controller_open_chat_no_type_canary_not_enabled" in result["blockers"]
    assert result["customer_send_performed"] is False
    assert result["chat_opened"] is False
    assert result["message_text_typed"] is False
    assert result["message_sent"] is False


def test_open_chat_no_type_command_rejects_send_or_write_flags(tmp_path):
    packet_dir, phrase_path = _write_open_chat_packet(tmp_path)
    command = normalize_command(
        {
            "command_id": "open_chat_no_type",
            "action": COMMAND_ACTION_UI_OPEN_CHAT_NO_TYPE_CANARY,
            "stores": "ACMEWEAR",
            "max_candidates": 1,
            "target_db_row_ids": "36170",
            "target_order_refs": "sha256:3a507903190c4097e2d211ee",
            "expected_merchant_account_id": "30137883",
            "open_chat_packet_dir": str(packet_dir),
            "open_chat_approval_text_file": str(phrase_path),
            "chat_open_allowed": True,
            "kaspi_chat_write_allowed": True,
        },
        run_dir=tmp_path,
        profile_store_code="ACMEWEAR",
    )

    result = _build_open_chat_no_type_preflight_result(
        command=command,
        enable_open_chat_no_type_canary=True,
    )

    assert result["gate"] == OPEN_CHAT_UNSAFE_GATE
    assert "command_kaspi_chat_write_allowed_must_remain_false" in result["unsafe_blockers"]
    assert result["customer_send_performed"] is False
    assert result["message_sent"] is False


def test_open_chat_no_type_command_green_preflight_builds_no_send_transport_plan(tmp_path):
    packet_dir, phrase_path = _write_open_chat_packet(tmp_path)
    command = normalize_command(
        {
            "command_id": "open_chat_no_type",
            "action": COMMAND_ACTION_UI_OPEN_CHAT_NO_TYPE_CANARY,
            "stores": "ACMEWEAR",
            "profile_store_code": "ACMEWEAR",
            "extra_status_filters": "NEW,KASPI_DELIVERY_WAIT_FOR_COURIER",
            "max_candidates": 1,
            "target_db_row_ids": "36170",
            "target_order_refs": "sha256:3a507903190c4097e2d211ee",
            "expected_merchant_account_id": "30137883",
            "open_chat_packet_dir": str(packet_dir),
            "open_chat_approval_text_file": str(phrase_path),
            "chat_open_allowed": True,
        },
        run_dir=tmp_path,
        profile_store_code="ACMEWEAR",
    )

    result = _build_open_chat_no_type_preflight_result(
        command=command,
        enable_open_chat_no_type_canary=True,
    )

    assert result["gate"] == OPEN_CHAT_PREFLIGHT_READY_GATE
    assert result["blockers"] == []
    assert result["unsafe_blockers"] == []
    assert result["customer_send_performed"] is False
    assert result["kaspi_chat_write_performed"] is False
    assert result["chat_opened"] is False
    assert result["message_text_typed"] is False
    assert result["message_sent"] is False
    assert result["transport_plan"]["gate"] == OPEN_CHAT_TRANSPORT_PLAN_READY_GATE
    assert result["transport_plan"]["expected_merchant_selector_text"] == "ID - 30137883"
    assert "open_customer_message_ui_for_selected_order_only" in result["transport_plan"]["steps"]
    assert "type_nothing" in result["transport_plan"]["steps"]
    assert "send_nothing" in result["transport_plan"]["steps"]
    assert "send_once" not in result["transport_plan"]["steps"]
    assert "raw_order_id" in result["transport_plan"]["runtime_only_values"]
    assert "938710785" not in str(result["transport_plan"])


class _FakeRequest:
    def __init__(self, url: str):
        self.method = "GET"
        self.url = url
        self.resource_type = "xhr"


class _OpenChatButtonLocator:
    def __init__(self, page, *, route_url: str | None = None):
        self.page = page
        self.route_url = route_url
        self.clicked = False

    @property
    def first(self):
        return self

    def count(self):
        return 1

    def is_visible(self, timeout=0):
        return True

    def click(self, timeout=0):
        self.clicked = True
        if self.route_url:
            self.page.emit_request(self.route_url)


class _OpenChatFakePage:
    def __init__(
        self,
        *,
        route_url: str | None = None,
        message_input_has_text: bool = False,
        message_input_present: bool = True,
        visible_chat_selectors: list[str] | None = None,
        visible_send_button: bool = False,
    ):
        self.handlers: dict[str, list] = {"request": []}
        if visible_chat_selectors is None:
            visible_chat_selectors = [resident.CHAT_BUTTON_SELECTOR]
        self.chat_buttons = {
            selector: _OpenChatButtonLocator(self, route_url=route_url)
            for selector in visible_chat_selectors
        }
        self.send_button = _OpenChatButtonLocator(self, route_url=route_url)
        self.visible_send_button = visible_send_button
        self.message_input_present = message_input_present
        self.message_input_has_text = message_input_has_text

    def locator(self, selector):
        if selector in self.chat_buttons:
            return self.chat_buttons[selector]
        if selector == "button:has-text('Отправить')" and self.visible_send_button:
            return self.send_button
        return _FakeLocator(visible=False)

    def on(self, event_name, handler):
        self.handlers.setdefault(event_name, []).append(handler)

    def remove_listener(self, event_name, handler):
        if handler in self.handlers.get(event_name, []):
            self.handlers[event_name].remove(handler)

    def emit_request(self, url: str):
        request = _FakeRequest(url)
        for handler in list(self.handlers.get("request", [])):
            handler(request)

    def evaluate(self, script, arg=None):
        return {
            "message_input_present": self.message_input_present,
            "message_input_has_text": self.message_input_has_text,
            "visible_message_input_count": 1 if self.message_input_present else 0,
        }

    def wait_for_timeout(self, timeout):
        return None


def _open_chat_command(tmp_path: Path, packet_dir: Path, phrase_path: Path) -> dict:
    return normalize_command(
        {
            "command_id": "open_chat_no_type",
            "action": COMMAND_ACTION_UI_OPEN_CHAT_NO_TYPE_CANARY,
            "stores": "ACMEWEAR",
            "profile_store_code": "ACMEWEAR",
            "extra_status_filters": "NEW,KASPI_DELIVERY_WAIT_FOR_COURIER",
            "max_candidates": 1,
            "target_db_row_ids": "36170",
            "target_order_refs": "sha256:3a507903190c4097e2d211ee",
            "expected_merchant_account_id": "30137883",
            "open_chat_packet_dir": str(packet_dir),
            "open_chat_approval_text_file": str(phrase_path),
            "chat_open_allowed": True,
            "output_dir": str(tmp_path / "open_chat_out"),
        },
        run_dir=tmp_path,
        profile_store_code="ACMEWEAR",
    )


def _patch_open_chat_runtime(monkeypatch, *, chat_button_present: bool = True):
    class _Candidate:
        db_row_id = 36170
        order_ref = "sha256:3a507903190c4097e2d211ee"

    monkeypatch.setattr(resident, "load_missing_size_candidates", lambda *args, **kwargs: [_Candidate()])
    monkeypatch.setattr(resident, "plan_probes", lambda *args, **kwargs: ["plan"])
    monkeypatch.setattr(
        resident,
        "_probe_one",
        lambda *args, **kwargs: {
            "result_or_detail_reached": True,
            "chat_button_present": chat_button_present,
            "merchant_account_match_proven": True,
            "observed_merchant_account_ids_after": ["30137883"],
        },
    )


class _SelectorDiagnosticFakePage:
    def __init__(self, diagnostic_payload: dict, *, append_event: tuple[list[dict], dict] | None = None):
        self.diagnostic_payload = diagnostic_payload
        self.append_event = append_event

    def evaluate(self, script, arg=None):
        if self.append_event is not None:
            target, event = self.append_event
            target.append(event)
        return self.diagnostic_payload


def _selector_diagnostic_command(tmp_path: Path) -> dict:
    return normalize_command(
        {
            "command_id": "selector_diag",
            "action": COMMAND_ACTION_UI_OPEN_CHAT_SELECTOR_DOM_DIAGNOSTIC,
            "stores": "ACMEWEAR",
            "profile_store_code": "ACMEWEAR",
            "extra_status_filters": "NEW,KASPI_DELIVERY_WAIT_FOR_COURIER",
            "max_candidates": 1,
            "target_db_row_ids": "36170",
            "target_order_refs": "sha256:3a507903190c4097e2d211ee",
            "expected_merchant_account_id": "30137883",
            "output_dir": str(tmp_path / "selector_diag_out"),
        },
        run_dir=tmp_path,
        profile_store_code="ACMEWEAR",
    )


def test_open_chat_selector_dom_diagnostic_green_without_click_or_send(tmp_path, monkeypatch):
    command = _selector_diagnostic_command(tmp_path)
    page = _SelectorDiagnosticFakePage(
        {
            "selector_code_sha256": "sha",
            "candidate_count": 16,
            "visible_enabled_candidate_count": 16,
            "click_target_count": 1,
            "visible_enabled_click_target_count": 1,
            "recommended_click_selector": "init-chat-button[type='CLIENT_SELLER_BY_ORDER']",
            "recommended_selector_family": "init-chat-button",
            "click_targets": [
                {
                    "source_buckets": [
                        "css:[type='CLIENT_SELLER_BY_ORDER']",
                        "text_marker:0",
                        "text_marker:0",
                    ],
                    "raw_anchor_count": 3,
                    "recommended_click_selector": "init-chat-button[type='CLIENT_SELLER_BY_ORDER']",
                    "selected_order_containment_bucket": "near_order_like_container",
                    "eligible_click_target": True,
                    "visible_enabled": True,
                }
            ],
            "candidates": [
                {
                    "source_bucket": "css:[type='CLIENT_SELLER_BY_ORDER']",
                    "visible_enabled": True,
                    "eligible_click_target": True,
                    "selected_order_containment_bucket": "near_order_like_container",
                }
            ],
            "raw_html_exported": False,
            "raw_text_exported": False,
            "raw_href_exported": False,
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
            "raw_phone_exported": False,
            "raw_session_material_exported": False,
        }
    )
    unsafe_events: list[dict] = []
    _patch_open_chat_runtime(monkeypatch)

    result = _run_open_chat_selector_dom_diagnostic_command(
        command=command,
        page=page,
        persistent_profile_dir=tmp_path / "profile",
        unsafe_events=unsafe_events,
        db_path=tmp_path / "app.db",
    )
    saved = json.loads((tmp_path / "selector_diag_out" / "open_chat_selector_dom_diagnostic_result.json").read_text())

    assert result["gate"] == SELECTOR_DOM_DIAGNOSTIC_GREEN_GATE
    assert saved["selector_dom_diagnostic"]["visible_enabled_candidate_count"] == 16
    assert saved["selector_dom_diagnostic"]["visible_enabled_click_target_count"] == 1
    assert saved["selector_dom_diagnostic"]["recommended_click_selector"] == (
        "init-chat-button[type='CLIENT_SELLER_BY_ORDER']"
    )
    assert result["chat_opened"] is False
    assert result["message_text_typed"] is False
    assert result["message_sent"] is False
    assert result["customer_send_performed"] is False
    assert "938710" not in json.dumps(result, ensure_ascii=False)


def test_open_chat_selector_dom_diagnostic_blocks_ambiguous_click_targets(tmp_path, monkeypatch):
    command = _selector_diagnostic_command(tmp_path)
    page = _SelectorDiagnosticFakePage(
        {
            "selector_code_sha256": "sha",
            "candidate_count": 2,
            "visible_enabled_candidate_count": 2,
            "click_target_count": 2,
            "visible_enabled_click_target_count": 2,
            "recommended_click_selector": "",
            "click_targets": [
                {"eligible_click_target": True, "visible_enabled": True},
                {"eligible_click_target": True, "visible_enabled": True},
            ],
            "candidates": [{"visible_enabled": True}, {"visible_enabled": True}],
            "raw_html_exported": False,
            "raw_text_exported": False,
            "raw_href_exported": False,
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
            "raw_phone_exported": False,
            "raw_session_material_exported": False,
        }
    )
    unsafe_events: list[dict] = []
    _patch_open_chat_runtime(monkeypatch)

    result = _run_open_chat_selector_dom_diagnostic_command(
        command=command,
        page=page,
        persistent_profile_dir=tmp_path / "profile",
        unsafe_events=unsafe_events,
        db_path=tmp_path / "app.db",
    )

    assert result["gate"] == SELECTOR_DOM_DIAGNOSTIC_YELLOW_GATE
    assert "visible_enabled_click_target_count_not_one:2" in result["blockers"]
    assert result["chat_opened"] is False
    assert result["message_sent"] is False


def test_open_chat_selector_dom_diagnostic_ignores_generic_text_marker_containers(tmp_path, monkeypatch):
    command = _selector_diagnostic_command(tmp_path)
    page = _SelectorDiagnosticFakePage(
        {
            "selector_code_sha256": "sha",
            "candidate_count": 8,
            "visible_enabled_candidate_count": 8,
            "click_target_count": 0,
            "visible_enabled_click_target_count": 0,
            "recommended_click_selector": "",
            "click_targets": [],
            "candidates": [
                {
                    "source_bucket": "text_marker:0",
                    "visible_enabled": True,
                    "eligible_click_target": False,
                    "selected_order_containment_bucket": "near_order_like_container",
                }
            ],
            "raw_html_exported": False,
            "raw_text_exported": False,
            "raw_href_exported": False,
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
            "raw_phone_exported": False,
            "raw_session_material_exported": False,
        }
    )
    unsafe_events: list[dict] = []
    _patch_open_chat_runtime(monkeypatch)

    result = _run_open_chat_selector_dom_diagnostic_command(
        command=command,
        page=page,
        persistent_profile_dir=tmp_path / "profile",
        unsafe_events=unsafe_events,
        db_path=tmp_path / "app.db",
    )

    assert result["gate"] == SELECTOR_DOM_DIAGNOSTIC_YELLOW_GATE
    assert "visible_enabled_click_target_count_not_one:0" in result["blockers"]
    assert result["selector_dom_diagnostic"]["recommended_click_selector"] == ""
    assert result["chat_opened"] is False
    assert result["message_sent"] is False


def test_open_chat_selector_dom_diagnostic_requires_sanitized_recommended_selector(tmp_path, monkeypatch):
    command = _selector_diagnostic_command(tmp_path)
    page = _SelectorDiagnosticFakePage(
        {
            "selector_code_sha256": "sha",
            "candidate_count": 1,
            "visible_enabled_candidate_count": 1,
            "click_target_count": 1,
            "visible_enabled_click_target_count": 1,
            "recommended_click_selector": "",
            "click_targets": [
                {
                    "eligible_click_target": True,
                    "visible_enabled": True,
                    "selected_order_containment_bucket": "near_order_like_container",
                }
            ],
            "candidates": [{"visible_enabled": True, "eligible_click_target": True}],
            "raw_html_exported": False,
            "raw_text_exported": False,
            "raw_href_exported": False,
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
            "raw_phone_exported": False,
            "raw_session_material_exported": False,
        }
    )
    unsafe_events: list[dict] = []
    _patch_open_chat_runtime(monkeypatch)

    result = _run_open_chat_selector_dom_diagnostic_command(
        command=command,
        page=page,
        persistent_profile_dir=tmp_path / "profile",
        unsafe_events=unsafe_events,
        db_path=tmp_path / "app.db",
    )

    assert result["gate"] == SELECTOR_DOM_DIAGNOSTIC_YELLOW_GATE
    assert "recommended_click_selector_missing" in result["blockers"]
    assert result["chat_opened"] is False
    assert result["message_sent"] is False


def test_open_chat_selector_dom_diagnostic_rejects_unsafe_route_observation(tmp_path, monkeypatch):
    command = _selector_diagnostic_command(tmp_path)
    unsafe_events: list[dict] = []
    page = _SelectorDiagnosticFakePage(
        {
            "selector_code_sha256": "sha",
            "candidate_count": 1,
            "visible_enabled_candidate_count": 1,
            "click_target_count": 1,
            "visible_enabled_click_target_count": 1,
            "recommended_click_selector": "init-chat-button[type='CLIENT_SELLER_BY_ORDER']",
            "click_targets": [{"eligible_click_target": True, "visible_enabled": True}],
            "candidates": [{"visible_enabled": True}],
            "raw_html_exported": False,
            "raw_text_exported": False,
            "raw_href_exported": False,
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
            "raw_phone_exported": False,
            "raw_session_material_exported": False,
        },
        append_event=(
            unsafe_events,
            {
                "host": "mc.shop.kaspi.kz",
                "path_template": "/chats/api/mobile/messages/sendMessage",
                "reason": "send_message_route_blocked_no_send",
            },
        ),
    )
    _patch_open_chat_runtime(monkeypatch)

    result = _run_open_chat_selector_dom_diagnostic_command(
        command=command,
        page=page,
        persistent_profile_dir=tmp_path / "profile",
        unsafe_events=unsafe_events,
        db_path=tmp_path / "app.db",
    )

    assert result["gate"] == SELECTOR_DOM_DIAGNOSTIC_RED_GATE
    assert "unexpected_route_observed_during_no_click_diagnostic" in result["unsafe_blockers"]
    assert result["message_text_typed"] is False
    assert result["message_sent"] is False


def test_route_flags_classify_open_chat_read_side_effect_without_send():
    flags = _route_flags_from_events(
        [
            {
                "host": "mc.shop.kaspi.kz",
                "path_template": "/chats/api/mobile/messageStatus/changeStatus",
                "reason": "message_status_change_route_blocked_read_side_effect_unknown",
            },
            {
                "host": "mc.shop.kaspi.kz",
                "path_template": "/chats/api/mobile/history/loadMoreMessages",
            },
        ]
    )

    assert flags["message_status_change_route_observed"] is True
    assert flags["load_more_messages_route_observed"] is True
    assert flags["send_message_route_observed"] is False
    assert flags["typing_send_text_route_observed"] is False
    assert flags["start_chat_route_observed"] is False


def test_open_chat_no_type_resident_command_records_green_without_send(tmp_path, monkeypatch):
    packet_dir, phrase_path = _write_open_chat_packet(tmp_path)
    command = _open_chat_command(tmp_path, packet_dir, phrase_path)
    page = _OpenChatFakePage(
        route_url="https://mc.shop.kaspi.kz/chats/api/mobile/history/loadMoreMessages"
    )
    unsafe_events: list[dict] = []
    _patch_open_chat_runtime(monkeypatch)

    result = _run_open_chat_no_type_command(
        command=command,
        page=page,
        persistent_profile_dir=tmp_path / "profile",
        unsafe_events=unsafe_events,
        db_path=tmp_path / "app.db",
        enable_open_chat_no_type_canary=True,
    )
    packet_result = json.loads((packet_dir / "open_chat_no_type_result_redacted.json").read_text())

    assert result["gate"] == OPEN_CHAT_RESULT_GREEN_GATE
    assert result["chat_opened"] is True
    assert result["message_text_typed"] is False
    assert result["message_sent"] is False
    assert packet_result["gate"] == OPEN_CHAT_RESULT_GREEN_GATE
    assert packet_result["chat_opened"] is True
    assert packet_result["message_text_typed"] is False
    assert packet_result["message_sent"] is False
    assert packet_result["visible_merchant_selector_id"] == "30137883"
    assert packet_result["load_more_messages_route_observed"] is True
    assert result["chat_button_click_selector"] == resident.CHAT_BUTTON_SELECTOR
    assert "938710" not in json.dumps(result, ensure_ascii=False)


def test_open_chat_no_type_resident_command_uses_safe_alternate_chat_button_selector(
    tmp_path, monkeypatch
):
    packet_dir, phrase_path = _write_open_chat_packet(tmp_path)
    command = _open_chat_command(tmp_path, packet_dir, phrase_path)
    alternate_selector = "button:has-text('Написать покупателю')"
    page = _OpenChatFakePage(
        route_url="https://mc.shop.kaspi.kz/chats/api/mobile/history/loadMoreMessages",
        visible_chat_selectors=[alternate_selector],
    )
    unsafe_events: list[dict] = []
    _patch_open_chat_runtime(monkeypatch)

    result = _run_open_chat_no_type_command(
        command=command,
        page=page,
        persistent_profile_dir=tmp_path / "profile",
        unsafe_events=unsafe_events,
        db_path=tmp_path / "app.db",
        enable_open_chat_no_type_canary=True,
    )

    assert result["gate"] == OPEN_CHAT_RESULT_GREEN_GATE
    assert result["chat_button_clicked"] is True
    assert result["chat_button_click_selector"] == alternate_selector
    assert result["message_text_typed"] is False
    assert result["message_sent"] is False


def test_open_chat_no_type_resident_command_never_uses_send_button_as_fallback(
    tmp_path, monkeypatch
):
    packet_dir, phrase_path = _write_open_chat_packet(tmp_path)
    command = _open_chat_command(tmp_path, packet_dir, phrase_path)
    page = _OpenChatFakePage(
        visible_chat_selectors=[],
        visible_send_button=True,
    )
    unsafe_events: list[dict] = []
    _patch_open_chat_runtime(monkeypatch)

    result = _run_open_chat_no_type_command(
        command=command,
        page=page,
        persistent_profile_dir=tmp_path / "profile",
        unsafe_events=unsafe_events,
        db_path=tmp_path / "app.db",
        enable_open_chat_no_type_canary=True,
    )

    assert result["gate"] == OPEN_CHAT_TRANSPORT_PLAN_BLOCKED_GATE
    assert "chat_button_locator_missing_at_click_time" in result["blockers"]
    assert result["chat_button_clicked"] is False
    assert page.send_button.clicked is False
    assert result["message_text_typed"] is False
    assert result["message_sent"] is False
    assert not (packet_dir / "open_chat_no_type_result_redacted.json").exists()


def test_open_chat_no_type_resident_command_blocks_click_without_visible_message_input(
    tmp_path, monkeypatch
):
    packet_dir, phrase_path = _write_open_chat_packet(tmp_path)
    command = _open_chat_command(tmp_path, packet_dir, phrase_path)
    exact_text_selector = "xpath=//*[normalize-space()='Написать покупателю']"
    page = _OpenChatFakePage(
        visible_chat_selectors=[exact_text_selector],
        message_input_present=False,
    )
    unsafe_events: list[dict] = []
    _patch_open_chat_runtime(monkeypatch)

    result = _run_open_chat_no_type_command(
        command=command,
        page=page,
        persistent_profile_dir=tmp_path / "profile",
        unsafe_events=unsafe_events,
        db_path=tmp_path / "app.db",
        enable_open_chat_no_type_canary=True,
    )

    assert result["gate"] == OPEN_CHAT_TRANSPORT_PLAN_BLOCKED_GATE
    assert result["chat_button_clicked"] is True
    assert result["chat_button_click_selector"] == exact_text_selector
    assert "message_input_not_visible_after_open_click" in result["blockers"]
    assert result["message_text_typed"] is False
    assert result["message_sent"] is False
    assert not (packet_dir / "open_chat_no_type_result_redacted.json").exists()


def test_open_chat_no_type_resident_command_rejects_send_route(tmp_path, monkeypatch):
    packet_dir, phrase_path = _write_open_chat_packet(tmp_path)
    command = _open_chat_command(tmp_path, packet_dir, phrase_path)
    page = _OpenChatFakePage(
        route_url="https://mc.shop.kaspi.kz/chats/api/mobile/messages/sendMessage"
    )
    unsafe_events: list[dict] = []
    _patch_open_chat_runtime(monkeypatch)

    result = _run_open_chat_no_type_command(
        command=command,
        page=page,
        persistent_profile_dir=tmp_path / "profile",
        unsafe_events=unsafe_events,
        db_path=tmp_path / "app.db",
        enable_open_chat_no_type_canary=True,
    )

    assert result["gate"] == OPEN_CHAT_UNSAFE_GATE
    assert "send_typing_or_start_chat_route_observed" in result["unsafe_blockers"]
    assert result["message_text_typed"] is False
    assert result["message_sent"] is False
    assert not (packet_dir / "open_chat_no_type_result_redacted.json").exists()


def test_heartbeat_payload_waiting_for_login_gate_is_explicit(tmp_path):
    payload = _heartbeat_payload(
        gate=YELLOW_GATE,
        run_dir=tmp_path,
        persistent_profile_dir=tmp_path / "profile",
        profile_store_code="ACMEWEAR",
        commands_dir=tmp_path / "command_queue",
        blockers=["orders_search_input_not_visible_yet_owner_login_may_be_required"],
    )

    assert payload["gate"] == YELLOW_GATE
    assert payload["blockers"] == ["orders_search_input_not_visible_yet_owner_login_may_be_required"]


class _FakeLocator:
    def __init__(self, *, visible: bool = False, text: str = ""):
        self.visible = visible
        self.text = text
        self.filled = ""
        self.clicked = False

    @property
    def first(self):
        return self

    def count(self):
        return 1 if self.visible else 0

    def is_visible(self, timeout=0):
        return self.visible

    def inner_text(self, timeout=0):
        return self.text

    def fill(self, value, timeout=0):
        self.filled = value

    def click(self, timeout=0):
        self.clicked = True


class _FakePage:
    def __init__(self):
        self.url = "https://idmc.shop.kaspi.kz/login"
        self.body = _FakeLocator(visible=True, text="Введите код из SMS")
        self.otp_input = _FakeLocator(visible=True)
        self.submit = _FakeLocator(visible=True)
        self.orders_input = _FakeLocator(visible=False)

    def locator(self, selector):
        if selector == "body":
            return self.body
        if selector == "input[placeholder='Номер заказа']":
            return self.orders_input
        if selector == "input[autocomplete='one-time-code']":
            return self.otp_input
        if selector == "button:has-text('Продолжить')":
            return self.submit
        return _FakeLocator(visible=False)

    def wait_for_timeout(self, timeout):
        return None


def test_login_sms_otp_command_fills_runtime_code_without_exporting_it(tmp_path, monkeypatch):
    page = _FakePage()
    command = normalize_command(
        {
            "command_id": "login_otp",
            "action": COMMAND_ACTION_LOGIN_SMS_OTP,
            "output_dir": str(tmp_path / "out"),
            "messages_db": str(tmp_path / "chat.db"),
            "otp_audit_json": str(tmp_path / "otp_audit.json"),
            "otp_submit_allowed": True,
        },
        run_dir=tmp_path,
        profile_store_code="ACMEWEAR",
    )

    def _fake_resolver(**kwargs):
        return (
            0,
            {
                "gate": resident.OTP_RESOLVED_GATE,
                "otp_exported_to_audit": False,
                "raw_sms_text_exported": False,
                "raw_sender_exported": False,
            },
            "777777",
        )

    monkeypatch.setattr(resident, "resolve_runtime_otp", _fake_resolver)

    result = _run_login_sms_otp_command(command=command, page=page)
    result_text = (tmp_path / "out" / "login_sms_otp_result_redacted.json").read_text(
        encoding="utf-8"
    )
    audit_text = (tmp_path / "otp_audit.json").read_text(encoding="utf-8")

    assert result["gate"] == LOGIN_OTP_FILLED_GATE
    assert page.otp_input.filled == "777777"
    assert page.submit.clicked is True
    assert result["otp_runtime_secret_used"] is True
    assert result["otp_filled"] is True
    assert result["login_submit_attempted"] is True
    assert result["customer_send_performed"] is False
    assert result["kaspi_chat_write_performed"] is False
    assert result["chat_opened"] is False
    assert result["message_text_typed"] is False
    assert result["message_sent"] is False
    assert result["raw_otp_exported"] is False
    assert "777777" not in result_text
    assert "777777" not in audit_text


def test_login_sms_otp_command_blocks_when_resolver_not_green(tmp_path, monkeypatch):
    page = _FakePage()
    command = normalize_command(
        {
            "command_id": "login_otp",
            "action": COMMAND_ACTION_LOGIN_SMS_OTP,
            "output_dir": str(tmp_path / "out"),
            "messages_db": str(tmp_path / "chat.db"),
            "otp_audit_json": str(tmp_path / "otp_audit.json"),
        },
        run_dir=tmp_path,
        profile_store_code="ACMEWEAR",
    )

    def _fake_resolver(**kwargs):
        return (
            3,
            {
                "gate": "YELLOW_KASPI_LOGIN_SMS_OTP_AMBIGUOUS_NO_SECRET",
                "otp_exported_to_audit": False,
                "raw_sms_text_exported": False,
                "raw_sender_exported": False,
            },
            None,
        )

    monkeypatch.setattr(resident, "resolve_runtime_otp", _fake_resolver)

    result = _run_login_sms_otp_command(command=command, page=page)

    assert result["gate"] == LOGIN_OTP_BLOCKED_GATE
    assert "otp_runtime_resolver_not_green" in result["blockers"]
    assert page.otp_input.filled == ""
    assert result["otp_runtime_secret_used"] is False
    assert result["otp_filled"] is False
    assert result["message_sent"] is False


def test_enqueue_build_command_is_no_send_and_has_no_raw_identity(tmp_path):
    command = build_command(
        Namespace(
            command_id="cmd1",
            action=COMMAND_ACTION_UI_SEARCH,
            target_date="2026-06-17",
            lookback_days=5,
            stores="ACMEWEAR",
            profile_store_code="ACMEWEAR",
            max_candidates=6,
            candidate_pool_limit=30,
            extra_status_filters="NEW",
            target_db_row_ids="",
            target_order_refs="",
            expected_merchant_account_id="",
            timeout_ms=30000,
            output_dir=tmp_path / "out",
        )
    )

    assert command["command_id"] == "cmd1"
    assert command["customer_send_allowed"] is False
    assert command["kaspi_chat_write_allowed"] is False
    assert command["message_sent"] is False
    assert command["raw_order_id_exported"] is False
    assert "938710785" not in str(command)


def test_enqueue_build_command_supports_chat_button_action_without_send(tmp_path):
    command = build_command(
        Namespace(
            command_id="button_cmd",
            action=COMMAND_ACTION_UI_CHAT_BUTTON,
            target_date="2026-06-17",
            lookback_days=5,
            stores="ACMEWEAR",
            profile_store_code="ACMEWEAR",
            max_candidates=1,
            candidate_pool_limit=30,
            extra_status_filters="",
            target_db_row_ids="36170",
            target_order_refs="sha256:3a507903190c4097e2d211ee",
            expected_merchant_account_id="30137883",
            timeout_ms=30000,
            output_dir=tmp_path / "out",
        )
    )

    assert command["action"] == COMMAND_ACTION_UI_CHAT_BUTTON
    assert command["target_db_row_ids"] == "36170"
    assert command["target_order_refs"] == "sha256:3a507903190c4097e2d211ee"
    assert command["chat_open_allowed"] is False
    assert command["message_text_typed"] is False
    assert command["message_sent"] is False


def test_enqueue_build_command_supports_metadata_capture_without_send(tmp_path):
    command = build_command(
        Namespace(
            command_id="metadata_cmd",
            action=COMMAND_ACTION_METADATA_CAPTURE,
            target_date="2026-06-17",
            lookback_days=5,
            stores="ACMEWEAR",
            profile_store_code="ACMEWEAR",
            max_candidates=1,
            candidate_pool_limit=30,
            extra_status_filters="",
            target_db_row_ids="",
            target_order_refs="",
            expected_merchant_account_id="",
            timeout_ms=30000,
            output_dir=tmp_path / "out",
        )
    )

    assert command["action"] == COMMAND_ACTION_METADATA_CAPTURE
    assert command["customer_send_allowed"] is False
    assert command["chat_open_allowed"] is False
    assert command["message_text_typed"] is False
    assert command["message_sent"] is False


def test_enqueue_build_command_supports_login_sms_otp_without_customer_send(tmp_path):
    command = build_command(
        Namespace(
            command_id="login_otp",
            action=COMMAND_ACTION_LOGIN_SMS_OTP,
            target_date="2026-06-17",
            lookback_days=5,
            stores="ACMEWEAR",
            profile_store_code="ACMEWEAR",
            max_candidates=1,
            candidate_pool_limit=30,
            extra_status_filters="",
            target_db_row_ids="",
            target_order_refs="",
            expected_merchant_account_id="",
            timeout_ms=30000,
            output_dir=tmp_path / "out",
            messages_db=tmp_path / "chat.db",
            otp_audit_json=tmp_path / "otp_audit.json",
            otp_window_minutes=9,
            otp_max_scan_rows=22,
            otp_submit_allowed=True,
        )
    )

    assert command["action"] == COMMAND_ACTION_LOGIN_SMS_OTP
    assert command["messages_db"] == str(tmp_path / "chat.db")
    assert command["otp_audit_json"] == str(tmp_path / "otp_audit.json")
    assert command["otp_window_minutes"] == 9
    assert command["otp_max_scan_rows"] == 22
    assert command["otp_submit_allowed"] is True
    assert command["customer_send_allowed"] is False
    assert command["kaspi_chat_write_allowed"] is False
    assert command["chat_open_allowed"] is False
    assert command["message_text_typed"] is False
    assert command["message_sent"] is False


def test_enqueue_build_command_supports_open_chat_no_type_without_send(tmp_path):
    command = build_command(
        Namespace(
            command_id="open_chat_no_type",
            action=COMMAND_ACTION_UI_OPEN_CHAT_NO_TYPE_CANARY,
            target_date="2026-06-18",
            lookback_days=5,
            stores="ACMEWEAR",
            profile_store_code="ACMEWEAR",
            max_candidates=1,
            candidate_pool_limit=30,
            extra_status_filters="NEW",
            target_db_row_ids="36170",
            target_order_refs="sha256:3a507903190c4097e2d211ee",
            expected_merchant_account_id="30137883",
            timeout_ms=30000,
            output_dir=tmp_path / "out",
            messages_db=None,
            otp_audit_json=None,
            otp_window_minutes=10,
            otp_max_scan_rows=50,
            otp_submit_allowed=False,
            open_chat_packet_dir=tmp_path / "packet",
            open_chat_approval_text_file=tmp_path / "approval.txt",
            chat_open_allowed=True,
        )
    )

    assert command["action"] == COMMAND_ACTION_UI_OPEN_CHAT_NO_TYPE_CANARY
    assert command["open_chat_packet_dir"] == str(tmp_path / "packet")
    assert command["open_chat_approval_text_file"] == str(tmp_path / "approval.txt")
    assert command["expected_merchant_account_id"] == "30137883"
    assert command["chat_open_allowed"] is True
    assert command["customer_send_allowed"] is False
    assert command["kaspi_chat_write_allowed"] is False
    assert command["message_text_typed"] is False
    assert command["message_sent"] is False
    assert command["raw_order_id_exported"] is False


def test_enqueue_build_command_supports_selector_dom_diagnostic_without_send(tmp_path):
    command = build_command(
        Namespace(
            command_id="selector_dom_diag",
            action=COMMAND_ACTION_UI_OPEN_CHAT_SELECTOR_DOM_DIAGNOSTIC,
            target_date="2026-06-18",
            lookback_days=5,
            stores="ACMEWEAR",
            profile_store_code="ACMEWEAR",
            max_candidates=1,
            candidate_pool_limit=30,
            extra_status_filters="NEW",
            target_db_row_ids="36170",
            target_order_refs="sha256:3a507903190c4097e2d211ee",
            expected_merchant_account_id="30137883",
            timeout_ms=30000,
            output_dir=tmp_path / "out",
            messages_db=None,
            otp_audit_json=None,
            otp_window_minutes=10,
            otp_max_scan_rows=50,
            otp_submit_allowed=False,
            open_chat_packet_dir=None,
            open_chat_approval_text_file=None,
            chat_open_allowed=False,
        )
    )

    assert command["action"] == COMMAND_ACTION_UI_OPEN_CHAT_SELECTOR_DOM_DIAGNOSTIC
    assert command["expected_merchant_account_id"] == "30137883"
    assert command["chat_open_allowed"] is False
    assert command["customer_send_allowed"] is False
    assert command["kaspi_chat_write_allowed"] is False
    assert command["message_text_typed"] is False
    assert command["message_sent"] is False
    assert command["raw_order_id_exported"] is False
