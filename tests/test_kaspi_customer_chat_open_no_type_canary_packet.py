import json
import hashlib

from scripts.build_kaspi_customer_chat_open_no_type_canary_packet import main


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _resident_manifest(order_ref="sha256:3a507903190c4097e2d211ee"):
    return {
        "gate": "GREEN_KASPI_CUSTOMER_CHAT_MESSAGE_BUTTON_PROVEN_NO_SEND",
        "target_date": "2026-06-18",
        "lookback_days": 5,
        "profile_store_code": "ACMEWEAR",
        "unsafe_event_count": 0,
        "customer_send_allowed": False,
        "kaspi_chat_write_allowed": False,
        "chat_opened": False,
        "message_text_typed": False,
        "message_sent": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
        "results": [
            {
                "db_row_id": 36170,
                "order_ref": order_ref,
                "store_code": "ACMEWEAR",
                "status_filter": "NEW",
                "merchant_account_match_proven": True,
                "result_or_detail_reached": True,
                "chat_button_present": True,
                "chat_opened": False,
                "message_text_typed": False,
                "message_sent": False,
                "raw_order_id_exported": False,
                "raw_customer_text_exported": False,
            }
        ],
    }


def _preflight(order_ref="sha256:3a507903190c4097e2d211ee"):
    return {
        "gate": "GREEN_LIVE_SEND_CANARY_EXECUTION_PREFLIGHT_READY_NO_SEND",
        "selected_order_ref": order_ref,
        "selected_db_row_id": 36170,
        "selected_store_code": "ACMEWEAR",
        "expected_merchant_account_id": "30137883",
        "customer_send_performed": False,
        "kaspi_chat_write_performed": False,
        "blockers": [],
        "unsafe_blockers": [],
    }


def _heartbeat():
    return {
        "gate": "GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_READY",
        "profile_store_code": "ACMEWEAR",
        "orders_search_input_visible": True,
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


def _selector_diagnostic(order_ref="sha256:3a507903190c4097e2d211ee"):
    return {
        "gate": "GREEN_KASPI_CUSTOMER_CHAT_OPEN_SELECTOR_DOM_DIAGNOSTIC_NO_CLICK_READY",
        "target_date": "2026-06-18",
        "selected_order_ref": order_ref,
        "selected_db_row_id": "36170",
        "selected_store_code": "ACMEWEAR",
        "expected_merchant_account_id": "30137883",
        "visible_merchant_selector_id": "30137883",
        "merchant_account_match_proven": True,
        "probe_result_or_detail_reached": True,
        "probe_chat_button_present": True,
        "chat_opened": False,
        "message_text_typed": False,
        "message_sent": False,
        "customer_send_performed": False,
        "kaspi_chat_write_performed": False,
        "raw_order_id_exported": False,
        "raw_customer_text_exported": False,
        "raw_phone_exported": False,
        "raw_session_material_exported": False,
        "selector_dom_diagnostic": {
            "visible_enabled_candidate_count": 18,
            "visible_enabled_click_target_count": 1,
            "recommended_click_selector": "init-chat-button[type='CLIENT_SELLER_BY_ORDER']",
            "raw_html_exported": False,
            "raw_text_exported": False,
            "raw_href_exported": False,
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
            "raw_phone_exported": False,
            "raw_session_material_exported": False,
        },
        "blockers": [],
        "unsafe_blockers": [],
    }


def test_open_chat_no_type_packet_builds_exact_green_approval(tmp_path):
    resident = tmp_path / "resident.json"
    preflight = tmp_path / "preflight.json"
    heartbeat = tmp_path / "heartbeat.json"
    out = tmp_path / "packet"
    _write(resident, _resident_manifest())
    _write(preflight, _preflight())
    _write(heartbeat, _heartbeat())

    rc = main(
        [
            "--resident-button-manifest",
            str(resident),
            "--live-send-execution-preflight-manifest",
            str(preflight),
            "--resident-heartbeat",
            str(heartbeat),
            "--output-dir",
            str(out),
        ]
    )

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    phrase = (out / "REQUIRED_EXACT_OPEN_CHAT_NO_TYPE_APPROVAL_PHRASE.txt").read_text(
        encoding="utf-8"
    )
    result_template = json.loads(
        (out / "open_chat_no_type_result_template_redacted.json").read_text(encoding="utf-8")
    )
    all_text = "\n".join(path.read_text(encoding="utf-8") for path in out.rglob("*") if path.is_file())

    assert rc == 0
    assert manifest["gate"] == "GREEN_OPEN_CHAT_NO_TYPE_CANARY_PACKET_READY_NO_SEND"
    assert manifest["selected_db_row_id"] == 36170
    assert manifest["expected_merchant_account_id"] == "30137883"
    packet_manifest_path = out / "open_chat_no_type_packet_lock.json"
    assert manifest["packet_manifest_path"] == str(packet_manifest_path.resolve())
    assert manifest["packet_manifest_sha256"] == hashlib.sha256(
        packet_manifest_path.read_bytes()
    ).hexdigest()
    assert manifest["approval_phrase_generated"] is True
    assert manifest["customer_send_allowed_now"] is False
    assert manifest["chat_opened_by_this_builder"] is False
    assert result_template["message_text_typed"] is False
    assert result_template["message_sent"] is False
    assert "type nothing, send nothing" in phrase
    assert str(packet_manifest_path.resolve()) in phrase
    assert manifest["packet_manifest_sha256"] in phrase
    assert "messageStatus/changeStatus" in phrase
    assert "938710785" not in all_text


def test_open_chat_no_type_packet_accepts_green_selector_diagnostic(tmp_path):
    selector = tmp_path / "selector.json"
    preflight = tmp_path / "preflight.json"
    heartbeat = tmp_path / "heartbeat.json"
    out = tmp_path / "packet"
    _write(selector, _selector_diagnostic())
    _write(preflight, _preflight())
    _write(heartbeat, _heartbeat())

    rc = main(
        [
            "--selector-diagnostic-manifest",
            str(selector),
            "--live-send-execution-preflight-manifest",
            str(preflight),
            "--resident-heartbeat",
            str(heartbeat),
            "--output-dir",
            str(out),
        ]
    )

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    lock = json.loads((out / "open_chat_no_type_packet_lock.json").read_text(encoding="utf-8"))
    phrase = (out / "REQUIRED_EXACT_OPEN_CHAT_NO_TYPE_APPROVAL_PHRASE.txt").read_text(
        encoding="utf-8"
    )
    all_text = "\n".join(path.read_text(encoding="utf-8") for path in out.rglob("*") if path.is_file())

    assert rc == 0
    assert manifest["gate"] == "GREEN_OPEN_CHAT_NO_TYPE_CANARY_PACKET_READY_NO_SEND"
    assert manifest["proof_source"] == "selector_diagnostic_manifest"
    assert manifest["selector_diagnostic_manifest_path"] == str(selector.resolve())
    assert manifest["no_open_proof_path"] == str(selector.resolve())
    assert manifest["no_open_proof_sha256"] == hashlib.sha256(selector.read_bytes()).hexdigest()
    assert manifest["selected_db_row_id"] == "36170"
    assert manifest["expected_merchant_account_id"] == "30137883"
    assert lock["proof_source"] == "selector_diagnostic_manifest"
    assert lock["no_open_proof_sha256"] == manifest["no_open_proof_sha256"]
    assert "No-open selector/button proof SHA256" in phrase
    assert "938710785" not in all_text


def test_open_chat_no_type_packet_blocks_preflight_target_mismatch(tmp_path):
    resident = tmp_path / "resident.json"
    preflight = tmp_path / "preflight.json"
    heartbeat = tmp_path / "heartbeat.json"
    out = tmp_path / "packet"
    _write(resident, _resident_manifest())
    _write(preflight, _preflight(order_ref="sha256:other"))
    _write(heartbeat, _heartbeat())

    rc = main(
        [
            "--resident-button-manifest",
            str(resident),
            "--live-send-execution-preflight-manifest",
            str(preflight),
            "--resident-heartbeat",
            str(heartbeat),
            "--output-dir",
            str(out),
        ]
    )

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))

    assert rc == 1
    assert manifest["gate"] == "YELLOW_OPEN_CHAT_NO_TYPE_CANARY_PACKET_BLOCKED_NO_SEND"
    assert "preflight_selected_order_ref_mismatch" in manifest["blockers"]
    assert manifest["approval_phrase_generated"] is False
    assert not (out / "REQUIRED_EXACT_OPEN_CHAT_NO_TYPE_APPROVAL_PHRASE.txt").exists()


def test_open_chat_no_type_packet_blocks_unsafe_heartbeat(tmp_path):
    resident = tmp_path / "resident.json"
    preflight = tmp_path / "preflight.json"
    heartbeat = tmp_path / "heartbeat.json"
    out = tmp_path / "packet"
    bad_heartbeat = _heartbeat()
    bad_heartbeat["chat_opened"] = True
    _write(resident, _resident_manifest())
    _write(preflight, _preflight())
    _write(heartbeat, bad_heartbeat)

    rc = main(
        [
            "--resident-button-manifest",
            str(resident),
            "--live-send-execution-preflight-manifest",
            str(preflight),
            "--resident-heartbeat",
            str(heartbeat),
            "--output-dir",
            str(out),
        ]
    )

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))

    assert rc == 1
    assert manifest["gate"] == "YELLOW_OPEN_CHAT_NO_TYPE_CANARY_PACKET_BLOCKED_NO_SEND"
    assert "resident_heartbeat_chat_opened_true" in manifest["blockers"]
    assert manifest["message_sent"] is False
