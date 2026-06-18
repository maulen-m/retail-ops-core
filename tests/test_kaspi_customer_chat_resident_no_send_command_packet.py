import json

from scripts.build_kaspi_customer_chat_resident_no_send_command_packet import main


def _priority_rows():
    return [
        {
            "sequence": 1,
            "priority_score": 220,
            "priority_band": "critical_over_120m",
            "order_ref": "sha256:universal-order",
            "db_row_id": 4,
            "store_code": "UNIVERSAL",
            "expected_merchant_account_id": "30000001",
            "requires_matching_merchant_account": True,
            "suggested_merchant_status_filter": "KASPI_DELIVERY_WAIT_FOR_COURIER",
            "ledger_status": "SEND_PLANNED_NO_SEND",
            "template_hash": "template-hash",
            "raw_order_id": "938710788",
        },
        {
            "sequence": 2,
            "priority_score": 100,
            "priority_band": "normal_under_120m",
            "order_ref": "sha256:acmewear-order",
            "db_row_id": 1,
            "store_code": "ACMEWEAR",
            "expected_merchant_account_id": "30137883",
            "requires_matching_merchant_account": True,
            "suggested_merchant_status_filter": "NEW",
            "ledger_status": "SEND_PLANNED_NO_SEND",
            "template_hash": "template-hash",
            "raw_order_id": "938710785",
        },
    ]


def test_resident_no_send_command_packet_builds_store_scoped_commands(tmp_path):
    priority_path = tmp_path / "priority_targets_redacted.json"
    out_dir = tmp_path / "packet"
    priority_path.write_text(json.dumps(_priority_rows(), ensure_ascii=False), encoding="utf-8")

    rc = main(
        [
            "--priority-targets",
            str(priority_path),
            "--target-date",
            "2026-06-18",
            "--output-dir",
            str(out_dir),
        ]
    )

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    index = json.loads((out_dir / "command_index_redacted.json").read_text(encoding="utf-8"))
    first_command = json.loads((out_dir / "command_queue" / f"{index[0]['command_id']}.json").read_text())
    second_command = json.loads((out_dir / "command_queue" / f"{index[1]['command_id']}.json").read_text())
    all_text = "\n".join(path.read_text(encoding="utf-8") for path in out_dir.rglob("*") if path.is_file())

    assert rc == 0
    assert manifest["gate"] == "GREEN_RESIDENT_NO_SEND_COMMAND_PACKET_READY"
    assert manifest["command_count"] == 2
    assert manifest["customer_send_allowed"] is False
    assert manifest["message_sent"] is False
    assert index[0]["expected_merchant_selector_text"] == "ID - 30000001"
    assert index[1]["expected_merchant_selector_text"] == "ID - 30137883"
    assert first_command["stores"] == "UNIVERSAL"
    assert first_command["profile_store_code"] == "UNIVERSAL"
    assert first_command["expected_merchant_account_id"] == "30000001"
    assert first_command["extra_status_filters"] == "KASPI_DELIVERY_WAIT_FOR_COURIER"
    assert first_command["target_db_row_ids"] == "4"
    assert first_command["target_order_refs"] == "sha256:universal-order"
    assert first_command["max_candidates"] == 1
    assert first_command["requires_matching_merchant_account"] is True
    assert first_command["customer_send_allowed"] is False
    assert first_command["kaspi_chat_write_allowed"] is False
    assert first_command["chat_open_allowed"] is False
    assert first_command["message_text_typed"] is False
    assert first_command["message_sent"] is False
    assert second_command["stores"] == "ACMEWEAR"
    assert second_command["expected_merchant_account_id"] == "30137883"
    assert "938710788" not in all_text
    assert "938710785" not in all_text


def test_resident_no_send_command_packet_blocks_missing_selector(tmp_path):
    rows = _priority_rows()
    rows[0]["store_code"] = "UNKNOWN_STORE"
    rows[0]["expected_merchant_account_id"] = ""
    priority_path = tmp_path / "priority_targets_redacted.json"
    out_dir = tmp_path / "packet"
    priority_path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")

    rc = main(
        [
            "--priority-targets",
            str(priority_path),
            "--target-date",
            "2026-06-18",
            "--output-dir",
            str(out_dir),
        ]
    )

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

    assert rc == 1
    assert manifest["gate"] == "YELLOW_RESIDENT_NO_SEND_COMMAND_PACKET_BLOCKED"
    assert "expected_merchant_account_id_missing" in manifest["blockers"]
    assert manifest["message_sent"] is False


def test_resident_no_send_command_packet_honors_max_targets(tmp_path):
    priority_path = tmp_path / "priority_targets_redacted.json"
    out_dir = tmp_path / "packet"
    priority_path.write_text(json.dumps(_priority_rows(), ensure_ascii=False), encoding="utf-8")

    rc = main(
        [
            "--priority-targets",
            str(priority_path),
            "--target-date",
            "2026-06-18",
            "--output-dir",
            str(out_dir),
            "--max-targets",
            "1",
        ]
    )

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    index = json.loads((out_dir / "command_index_redacted.json").read_text(encoding="utf-8"))

    assert rc == 0
    assert manifest["command_count"] == 1
    assert len(index) == 1
    assert index[0]["store_code"] == "UNIVERSAL"
