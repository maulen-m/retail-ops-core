import json

from scripts.probe_kaspi_customer_chat_metadata_no_send import (
    GREEN_GATE,
    RED_GATE,
    SESSION_CLOSE_GUARD_BLOCKER,
    YELLOW_GATE,
    build_parser,
    build_request_event,
    main as metadata_probe_main,
    run,
    sanitize_url,
    validate_capture,
)


def _base_capture(events):
    return {
        "source": "fixture",
        "selected_order_ref": "sha256:selected-order",
        "store_code": "ACMEWEAR",
        "events": events,
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "chat_opened": False,
        "message_text_typed": False,
        "message_sent": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
    }


def test_live_browser_capture_requires_explicit_session_close_permission(tmp_path):
    packet_dir = tmp_path / "packet"
    packet_dir.mkdir(parents=True, exist_ok=True)
    (packet_dir / "manifest.json").write_text(
        json.dumps(
            {
                "selected_order_ref": "sha256:selected-order",
                "selected_db_row_id": 1,
                "selected_store_code": "ACMEWEAR",
                "selected_status_filter": "KASPI_DELIVERY_CARGO_ASSEMBLY",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    args = build_parser().parse_args(["--packet-dir", str(packet_dir), "--run-live-browser"])

    summary = run(args)
    capture = json.loads((packet_dir / "customer_chat_metadata_capture_redacted.json").read_text())

    assert summary["gate"] == YELLOW_GATE
    assert SESSION_CLOSE_GUARD_BLOCKER in capture["blockers"]
    assert capture["source"] == "playwright_metadata_no_send_blocked_session_preservation_guard"
    assert summary["customer_send_allowed"] is False


def test_metadata_url_sanitizer_keeps_query_keys_not_values():
    safe = sanitize_url(
        "https://msg-web.kaspi.kz/paychat/api/v1/group/startChat?order=938710785&foo=bar"
    )

    assert safe == {
        "scheme": "https",
        "host": "msg-web.kaspi.kz",
        "path_template": "/paychat/api/v1/group/startChat",
        "query_keys": ["foo", "order"],
    }
    assert "938710785" not in json.dumps(safe, ensure_ascii=False)
    assert "bar" not in json.dumps(safe, ensure_ascii=False)


def test_metadata_url_sanitizer_redacts_long_path_ids():
    safe = sanitize_url("https://mc.shop.kaspi.kz/mc/api/order/938710785/actions")

    assert safe["path_template"] == "/mc/api/order/[redacted]/actions"
    assert "938710785" not in json.dumps(safe, ensure_ascii=False)


def test_metadata_capture_accepts_safe_route_shapes():
    capture = _base_capture(
        [
            build_request_event(
                method="GET",
                url="https://msg-web.kaspi.kz/paychat",
                resource_type="xhr",
            )
        ]
    )

    validation = validate_capture(capture)

    assert validation["gate"] == GREEN_GATE
    assert validation["accepted"] is True
    assert validation["blockers"] == []
    assert validation["route_family_counts"] == {"paychat_frontend": 1}


def test_metadata_capture_allows_sha256_redacted_refs_with_digit_runs():
    capture = _base_capture(
        [
            build_request_event(
                method="GET",
                url="https://msg-web.kaspi.kz/paychat",
                resource_type="xhr",
            )
        ]
    )
    capture["selected_order_refs"] = ["sha256:3a507903190c4097e2d211ee"]

    validation = validate_capture(capture)

    assert validation["gate"] == GREEN_GATE
    assert validation["accepted"] is True
    assert "raw_long_number_detected" not in validation["blockers"]


def test_metadata_capture_still_rejects_raw_long_number_values():
    capture = _base_capture(
        [
            build_request_event(
                method="GET",
                url="https://msg-web.kaspi.kz/paychat",
                resource_type="xhr",
            )
        ]
    )
    capture["selected_order_refs"] = ["938710785"]

    validation = validate_capture(capture)

    assert validation["gate"] == RED_GATE
    assert validation["accepted"] is False
    assert "raw_long_number_detected" in validation["blockers"]


def test_metadata_capture_rejects_send_message_route_even_without_body():
    capture = _base_capture(
        [
            build_request_event(
                method="POST",
                url="https://msg-web.kaspi.kz/paychat/api/v1/messages/sendMessage",
                resource_type="xhr",
            )
        ]
    )

    validation = validate_capture(capture)

    assert validation["gate"] == RED_GATE
    assert validation["accepted"] is False
    assert "send_message_route_observed" in validation["blockers"]


def test_metadata_capture_rejects_typing_route_even_without_body():
    capture = _base_capture(
        [
            build_request_event(
                method="POST",
                url="https://mc.shop.kaspi.kz/chats/api/mobile/api/v1/typing/sendText",
                resource_type="xhr",
            )
        ]
    )

    validation = validate_capture(capture)

    assert validation["gate"] == RED_GATE
    assert validation["accepted"] is False
    assert "typing_send_text_route_observed" in validation["blockers"]
    assert "typing_send_text_write_risk" in validation["chat_route_families_observed"]


def test_metadata_capture_rejects_start_chat_route_even_without_body():
    capture = _base_capture(
        [
            build_request_event(
                method="POST",
                url="https://mc.shop.kaspi.kz/chats/api/mobile/api/v1/group/startChat",
                resource_type="xhr",
            )
        ]
    )

    validation = validate_capture(capture)

    assert validation["gate"] == RED_GATE
    assert validation["accepted"] is False
    assert "start_chat_route_observed" in validation["blockers"]
    assert "start_chat_write_risk" in validation["chat_route_families_observed"]


def test_metadata_capture_rejects_message_status_change_side_effect():
    capture = _base_capture(
        [
            build_request_event(
                method="POST",
                url="https://mc.shop.kaspi.kz/chats/api/mobile/api/v1/messageStatus/changeStatus",
                resource_type="xhr",
            )
        ]
    )

    validation = validate_capture(capture)

    assert validation["gate"] == RED_GATE
    assert validation["accepted"] is False
    assert "message_status_change_route_observed_read_side_effect_unknown" in validation["blockers"]
    assert "message_status_read_side_effect_risk" in validation["chat_route_families_observed"]


def test_metadata_capture_warns_on_load_more_messages_open_chat_risk():
    capture = _base_capture(
        [
            build_request_event(
                method="POST",
                url="https://mc.shop.kaspi.kz/chats/api/mobile/api/v1/history/loadMoreMessages",
                resource_type="xhr",
            )
        ]
    )

    validation = validate_capture(capture)

    assert validation["gate"] == YELLOW_GATE
    assert validation["accepted"] is False
    assert validation["blockers"] == []
    assert "load_more_messages_route_observed_open_chat_risk" in validation["warnings"]
    assert "load_more_messages" in validation["chat_route_families_observed"]


def test_metadata_capture_classifies_websocket_and_group_routes():
    capture = _base_capture(
        [
            build_request_event(
                method="WEBSOCKET",
                url="wss://mc.shop.kaspi.kz/ws/chats/ws?appId=redacted",
                resource_type="websocket",
            ),
            build_request_event(
                method="POST",
                url="https://mc.shop.kaspi.kz/chats/api/mobile/api/v1/group/loadGroups/chat",
                resource_type="xhr",
            ),
            build_request_event(
                method="POST",
                url="https://mc.shop.kaspi.kz/chats/api/mobile/api/v1/group/getDiffGroups/chat",
                resource_type="xhr",
            ),
            build_request_event(
                method="POST",
                url="https://mc.shop.kaspi.kz/chats/api/mobile/api/v1/chat/search",
                resource_type="xhr",
            ),
        ]
    )

    validation = validate_capture(capture)

    assert validation["gate"] == GREEN_GATE
    assert validation["accepted"] is True
    assert validation["blockers"] == []
    assert validation["route_family_counts"] == {
        "chat_api_mobile": 3,
        "chat_search": 1,
        "chat_websocket": 1,
        "group_diff": 1,
        "group_load": 1,
    }


def test_metadata_capture_allows_token_like_query_key_names_without_values():
    capture = _base_capture(
        [
            build_request_event(
                method="WEBSOCKET",
                url=(
                    "wss://mc.shop.kaspi.kz/ws/chats/ws"
                    "?appId=web&clientType=merchant&merchantId=redacted&tToken=redacted"
                ),
                resource_type="websocket",
            )
        ]
    )

    validation = validate_capture(capture)

    assert validation["gate"] == GREEN_GATE
    assert validation["accepted"] is True
    assert validation["blockers"] == []
    assert validation["route_family_counts"] == {"chat_websocket": 1}


def test_metadata_capture_allows_secret_words_inside_safe_path_labels():
    capture = _base_capture(
        [
            build_request_event(
                method="GET",
                url="https://kaspi.kz/mc/ab/tests/script-cookie?ui=seller",
                resource_type="script",
            ),
            build_request_event(
                method="GET",
                url="https://mc.shop.kaspi.kz/oauth2/authorization/1",
                resource_type="document",
            ),
        ]
    )

    validation = validate_capture(capture)

    assert validation["gate"] == GREEN_GATE
    assert validation["accepted"] is True
    assert validation["blockers"] == []


def test_metadata_capture_incomplete_browser_capture_stays_yellow_not_green():
    capture = _base_capture(
        [
            build_request_event(
                method="GET",
                url="https://kaspi.kz/mc/",
                resource_type="document",
            )
        ]
    )
    capture["blockers"] = ["orders_search_input_not_visible_or_login_gate_before_timeout"]

    validation = validate_capture(capture)

    assert validation["gate"] == YELLOW_GATE
    assert validation["accepted"] is False
    assert validation["blockers"] == []
    assert (
        "capture_incomplete:orders_search_input_not_visible_or_login_gate_before_timeout"
        in validation["warnings"]
    )


def test_metadata_capture_cli_writes_redacted_validation_and_closeout(tmp_path, capsys):
    capture_path = tmp_path / "capture.json"
    validation_path = tmp_path / "validation.json"
    closeout_path = tmp_path / "closeout.md"
    capture = _base_capture(
        [
            build_request_event(
                method="GET",
                url="https://mc.shop.kaspi.kz/ws/chats/ws?conversation=hidden",
                resource_type="websocket",
            )
        ]
    )
    capture_path.write_text(json.dumps(capture, ensure_ascii=False), encoding="utf-8")

    rc = metadata_probe_main(
        [
            "--validate-only",
            "--capture-json",
            str(capture_path),
            "--validation-json",
            str(validation_path),
            "--closeout-md",
            str(closeout_path),
            "--require-green",
        ]
    )
    capsys.readouterr()

    assert rc == 0
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    closeout = closeout_path.read_text(encoding="utf-8")
    validation_text = validation_path.read_text(encoding="utf-8")
    assert validation["gate"] == GREEN_GATE
    assert f"Gate: {GREEN_GATE}" in closeout
    assert "hidden" not in validation_text
    assert "headers" not in validation_text.lower()
    assert "authorization" not in validation_text.lower()
