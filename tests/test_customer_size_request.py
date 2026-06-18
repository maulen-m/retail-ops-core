import json
import sqlite3
import argparse
from datetime import date, datetime
from pathlib import Path

from core.ops.customer_size_request import (
    DEFAULT_REQUEST_TEMPLATE,
    build_customer_size_next_actions,
    build_update_plan_from_ledger_snapshot,
    build_live_ui_canary_targets,
    build_google_board_update_plan,
    build_request_ledger_plan,
    export_customer_size_ledger_snapshot,
    inspect_chat_trigger_html,
    record_synthetic_reply_observations,
    load_missing_size_candidates,
    parse_size_reply,
    private_hash,
    record_live_send_canary_acceptance,
    record_customer_reply_observations,
    request_template_hash,
    summarize_live_ui_targets_by_store,
    summarize_customer_size_ledger,
    suggest_merchant_status_filter,
    upsert_request_ledger_plan,
)
from scripts.plan_kaspi_customer_size_requests import main as plan_main
from scripts.build_kaspi_customer_chat_live_canary_packet import main as canary_packet_main
from scripts.build_kaspi_customer_size_google_board_patch_packet import (
    main as google_board_patch_packet_main,
)
from scripts.build_kaspi_customer_size_cadence_readiness_packet import (
    main as cadence_readiness_packet_main,
)
from scripts.build_kaspi_customer_chat_live_send_canary_approval_packet import (
    main as live_send_approval_packet_main,
)
from scripts.build_kaspi_customer_chat_live_send_canary_execution_handoff import (
    main as live_send_execution_handoff_main,
)
from scripts.build_kaspi_customer_chat_chrome_reconnect_packet import (
    CHROME_PLUGIN_ROOT_ENV,
    _resolve_chrome_plugin_root,
    main as chrome_reconnect_packet_main,
)
from scripts.build_kaspi_customer_size_workflow_readiness_packet import (
    main as workflow_readiness_packet_main,
)
from scripts.build_kaspi_customer_size_owner_dashboard import (
    main as owner_dashboard_main,
)
from scripts.build_kaspi_customer_size_automation_options_matrix import (
    main as automation_options_matrix_main,
)
from scripts.resolve_kaspi_customer_chat_canary_runtime_secret import main as resolve_canary_secret_main
from scripts.resolve_kaspi_customer_size_order_runtime_secret import (
    main as resolve_customer_size_order_secret_main,
)
from scripts.record_kaspi_customer_chat_no_send_manual_proof import (
    main as record_manual_no_send_proof_main,
)
from scripts.record_kaspi_customer_size_reply_observations import (
    main as record_reply_observations_main,
)
from scripts.run_kaspi_customer_size_after_reply_observation import (
    main as after_reply_observation_main,
)
from scripts.record_kaspi_customer_size_live_send_canary_acceptance import (
    main as record_live_send_canary_acceptance_main,
)
from scripts.build_kaspi_customer_size_reply_polling_handoff import (
    main as reply_polling_handoff_main,
)
from scripts.build_kaspi_customer_size_google_board_apply_handoff import (
    main as google_board_apply_handoff_main,
)
from scripts.apply_kaspi_customer_size_google_board_my_size_patch import (
    NARROW_WRITE_ENV_GATE,
    plan_board_cell_updates,
    validate_apply_authority,
)
from scripts.probe_kaspi_customer_chat_live_playwright_no_send import (
    _build_result as build_playwright_no_send_result,
)
from scripts.refresh_kaspi_customer_chat_playwright_session import (
    GREEN_GATE as SESSION_REFRESH_GREEN_GATE,
    _build_closeout as build_session_refresh_closeout,
    _build_manifest as build_session_refresh_manifest,
    _default_persistent_profile_dir as default_session_refresh_profile_dir,
    _default_storage_state as default_session_refresh_storage_state,
    _login_state_from_url as login_state_from_url,
    _safe_url as safe_session_refresh_url,
    _target_url as session_refresh_target_url,
)
from scripts.report_kaspi_customer_size_next_action import (
    main as next_action_report_main,
)
from scripts.run_kaspi_customer_size_no_send_green_followup import (
    main as no_send_green_followup_main,
)
from scripts.run_kaspi_customer_size_post_canary_sequence import (
    main as post_canary_sequence_main,
)
from scripts.run_kaspi_customer_size_after_live_send_watch import (
    main as after_live_send_watch_main,
)
from scripts.run_kaspi_customer_size_after_board_apply_readiness import (
    main as after_board_apply_readiness_main,
)
from scripts.run_kaspi_customer_size_request_control_plane import main as control_plane_main
from scripts.run_kaspi_customer_size_request_scheduler_preflight import main as scheduler_preflight_main
from scripts.build_kaspi_customer_size_early_send_priority_packet import (
    main as early_send_priority_packet_main,
)
from scripts.validate_kaspi_customer_chat_live_canary_result import (
    main as validate_canary_result_main,
)
from scripts.validate_kaspi_customer_chat_live_send_canary_result import (
    _load_raw_order_id_for_scan,
    main as validate_live_send_canary_result_main,
)
from core.integrations.google_ops_board import load_ops_board_contract


def _make_orders_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE fact_orders_kaspi (
            id INTEGER PRIMARY KEY,
            order_id TEXT,
            store_code TEXT,
            sku_key TEXT,
            sku_id TEXT,
            my_size TEXT,
            assigned_size TEXT,
            customer_height_cm INTEGER,
            customer_weight_kg INTEGER,
            internal_status TEXT,
            kaspi_status TEXT,
            planned_shipment_date TEXT,
            created_at TEXT
        )
        """
    )
    rows = [
        (
            1,
            "938710785",
            "ACMEWEAR",
            "CL_OC_MEN_LINE51_WHITE",
            "CL_OC_MEN_LINE51_WHITE_XL",
            None,
            None,
            None,
            None,
            "NEW",
            "APPROVED_BY_BANK",
            "2026-06-15",
            "2026-06-15 09:00:00",
        ),
        (
            2,
            "938710786",
            "ACMEWEAR",
            "CL_OC_MEN_LINE51_WHITE",
            "CL_OC_MEN_LINE51_WHITE_L",
            "L",
            None,
            None,
            None,
            "NEW",
            "APPROVED_BY_BANK",
            "2026-06-15",
            "2026-06-15 09:00:00",
        ),
        (
            3,
            "938710787",
            "ACMEWEAR",
            "CL_OC_MEN_LINE51_WHITE",
            "CL_OC_MEN_LINE51_WHITE_2XL",
            None,
            None,
            None,
            None,
            "SHIPPED",
            "COMPLETED",
            "2026-06-15",
            "2026-06-15 09:00:00",
        ),
        (
            4,
            "938710788",
            "UNIVERSAL",
            "CL_OC_MEN_LINE51_WHITE",
            "CL_OC_MEN_LINE51_WHITE_M",
            None,
            None,
            None,
            None,
            "READY",
            "ACCEPTED_BY_MERCHANT",
            "2026-06-14",
            "2026-06-14 09:00:00",
        ),
    ]
    conn.executemany(
        """
        INSERT INTO fact_orders_kaspi (
            id, order_id, store_code, sku_key, sku_id, my_size, assigned_size,
            customer_height_cm, customer_weight_kg, internal_status, kaspi_status,
            planned_shipment_date, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()


def test_parse_size_reply_extracts_russian_height_weight_without_raw_text():
    facts = parse_size_reply("Рост 180, вес 85 кг", product_type="CL")

    assert facts.height_cm == 180
    assert facts.weight_kg == 85
    assert facts.parse_confidence == "HIGH"
    assert facts.reply_hash.startswith("sha256:")
    assert "Рост" not in str(facts)


def test_parse_size_reply_extracts_explicit_size():
    facts = parse_size_reply("берите пожалуйста XXL", product_type="CL")

    assert facts.explicit_size == "2XL"
    assert facts.parse_confidence == "MEDIUM"


def test_candidate_loader_filters_active_missing_size_and_redacts_order_id(tmp_path):
    db_path = tmp_path / "orders.db"
    _make_orders_db(db_path)

    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
    )
    evidence = [candidate.to_redacted_dict() for candidate in candidates]

    assert [candidate.raw_order_id for candidate in candidates] == ["938710788", "938710785"]
    assert all("order_id" not in row for row in evidence)
    assert all(row["order_ref"].startswith("sha256:") for row in evidence)
    assert all("missing_size" in row["reason_codes"] for row in evidence)


def test_request_ledger_plan_is_stable_and_no_send(tmp_path):
    db_path = tmp_path / "orders.db"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )

    first = build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE)
    second = build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE)

    assert len(first) == 1
    assert first[0]["ledger_key"] == second[0]["ledger_key"]
    assert first[0]["status"] == "SEND_PLANNED_NO_SEND"
    assert first[0]["send_allowed"] is False
    assert first[0]["template_hash"] == request_template_hash(DEFAULT_REQUEST_TEMPLATE)


def test_local_request_ledger_upsert_is_idempotent_and_redacted(tmp_path):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    plan = build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE)

    first = upsert_request_ledger_plan(ledger_path, plan)
    second = upsert_request_ledger_plan(ledger_path, plan)
    snapshot = export_customer_size_ledger_snapshot(ledger_path)
    snapshot_text = json.dumps(snapshot, ensure_ascii=False)

    assert first == {"input_rows": 1, "inserted": 1, "updated": 0, "deduplicated": 0}
    assert second == {"input_rows": 1, "inserted": 0, "updated": 1, "deduplicated": 0}
    assert len(snapshot) == 1
    assert snapshot[0]["send_allowed"] == 0
    assert snapshot[0]["raw_order_id_exported"] == 0
    assert snapshot[0]["raw_reply_text_exported"] == 0
    assert "938710785" not in snapshot_text


def test_local_request_ledger_dedupes_same_order_when_sku_identity_improves(tmp_path):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    initial_plan = build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE)
    sparse_plan = [dict(initial_plan[0], sku_id=None, sku_key=None)]
    upsert_request_ledger_plan(ledger_path, sparse_plan)
    record_synthetic_reply_observations(
        ledger_path,
        [
            {
                "order_ref": initial_plan[0]["order_ref"],
                "reply_text": "рост 175 вес 75",
                "product_type": "CL",
            }
        ],
    )

    stats = upsert_request_ledger_plan(ledger_path, initial_plan)
    snapshot = export_customer_size_ledger_snapshot(ledger_path)

    assert stats["input_rows"] == 1
    assert stats["updated"] == 1
    assert stats["deduplicated"] == 0
    assert len(snapshot) == 1
    assert snapshot[0]["status"] == "CLASSIFICATION_READY"
    assert snapshot[0]["planned_size"] == "L"
    assert snapshot[0]["sku_id"] == "CL_OC_MEN_LINE51_WHITE_XL"


def test_local_request_ledger_dedupes_same_order_across_channels(tmp_path):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    plan = build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE)
    prior_browser_gateway_row = dict(
        plan[0],
        ledger_key="legacy_browser_gateway_key",
        channel="KASPI_MERCHANT_CHAT_BROWSER_RESIDENT_FIXTURE",
        status="REQUEST_SENT",
    )

    upsert_request_ledger_plan(ledger_path, [prior_browser_gateway_row])
    stats = upsert_request_ledger_plan(ledger_path, plan)
    snapshot = export_customer_size_ledger_snapshot(ledger_path)

    assert stats["input_rows"] == 1
    assert stats["inserted"] == 0
    assert stats["updated"] == 1
    assert len(snapshot) == 1
    assert snapshot[0]["status"] == "REQUEST_SENT"
    assert snapshot[0]["order_ref"] == plan[0]["order_ref"]
    assert snapshot[0]["template_hash"] == plan[0]["template_hash"]


def test_synthetic_reply_ledger_classification_builds_redacted_update_plan(tmp_path):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    request_plan = build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE)
    upsert_request_ledger_plan(ledger_path, request_plan)

    stats = record_synthetic_reply_observations(
        ledger_path,
        [
            {
                "order_ref": request_plan[0]["order_ref"],
                "reply_text": "рост 175 вес 75",
                "product_type": "CL",
            }
        ],
    )
    snapshot = export_customer_size_ledger_snapshot(ledger_path)
    update_plan = build_update_plan_from_ledger_snapshot(snapshot)
    snapshot_text = json.dumps(snapshot, ensure_ascii=False)

    assert stats["matched"] == 1
    assert stats["classification_ready"] == 1
    assert snapshot[0]["status"] == "CLASSIFICATION_READY"
    assert update_plan[0]["planned_my_size"] == "L"
    assert update_plan[0]["write_allowed"] is False
    assert "рост 175 вес 75" not in snapshot_text


def test_customer_reply_observations_match_by_db_row_id_without_raw_text(tmp_path):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    request_plan = build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE)
    upsert_request_ledger_plan(ledger_path, request_plan)

    stats, observations = record_customer_reply_observations(
        ledger_path,
        [{"db_row_id": 1, "reply_text": "рост 175 вес 75", "product_type": "CL"}],
    )
    snapshot = export_customer_size_ledger_snapshot(ledger_path)
    snapshot_text = json.dumps(snapshot, ensure_ascii=False)
    observations_text = json.dumps(observations, ensure_ascii=False)

    assert stats["matched"] == 1
    assert stats["classification_ready"] == 1
    assert observations[0]["match_method"] == "db_row_id"
    assert observations[0]["planned_size"] == "L"
    assert snapshot[0]["status"] == "CLASSIFICATION_READY"
    assert "рост 175 вес 75" not in snapshot_text
    assert "рост 175 вес 75" not in observations_text


def test_reply_observations_cli_builds_redacted_packet_and_update_plan(tmp_path, capsys):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    reply_csv = tmp_path / "reply_input.csv"
    out_dir = tmp_path / "reply_packet"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    request_plan = build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE)
    upsert_request_ledger_plan(ledger_path, request_plan)
    reply_csv.write_text("db_row_id,reply_text,product_type\n1,рост 175 вес 75,CL\n", encoding="utf-8")

    rc = record_reply_observations_main(
        [
            "--ledger-db",
            str(ledger_path),
            "--reply-csv",
            str(reply_csv),
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    observations_text = (out_dir / "reply_observations_redacted.json").read_text(encoding="utf-8")
    update_plan = json.loads((out_dir / "reply_size_update_plan_dry_run.json").read_text(encoding="utf-8"))

    assert rc == 0
    assert manifest["gate"] == "GREEN_CUSTOMER_SIZE_REPLY_OBSERVATIONS_CLASSIFICATION_READY_NO_EXTERNAL_WRITE"
    assert manifest["classification_ready_rows"] == 1
    assert manifest["raw_reply_text_exported"] is False
    assert manifest["google_board_write_allowed"] is False
    assert update_plan[0]["planned_my_size"] == "L"
    assert "рост 175 вес 75" not in observations_text
    assert "рост 175 вес 75" not in (out_dir / "reply_size_update_plan_dry_run.json").read_text(
        encoding="utf-8"
    )


def test_reply_observations_cli_stays_yellow_for_unmatched_reply(tmp_path, capsys):
    ledger_path = tmp_path / "ledger.sqlite"
    reply_csv = tmp_path / "reply_input.csv"
    out_dir = tmp_path / "reply_packet"
    reply_csv.write_text(
        "db_row_id,reply_text,product_type\n999,рост 175 вес 75,CL\n",
        encoding="utf-8",
    )

    rc = record_reply_observations_main(
        [
            "--ledger-db",
            str(ledger_path),
            "--reply-csv",
            str(reply_csv),
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

    assert rc == 0
    assert manifest["gate"] == "YELLOW_CUSTOMER_SIZE_REPLY_OBSERVATIONS_REVIEW_NEEDED_NO_EXTERNAL_WRITE"
    assert manifest["unmatched_rows"] == 1
    assert "рост 175 вес 75" not in (out_dir / "reply_observations_redacted.json").read_text(
        encoding="utf-8"
    )


def test_after_reply_observation_builds_board_apply_handoff_without_external_writes(
    tmp_path, capsys
):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    reply_csv = tmp_path / "reply_input.csv"
    out_dir = tmp_path / "after_reply"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    request_plan = build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE)
    upsert_request_ledger_plan(ledger_path, request_plan)
    record_live_send_canary_acceptance(
        ledger_path,
        {
            "gate": "GREEN_LIVE_SEND_CANARY_RESULT_ACCEPTED_ONE_ORDER",
            "selected_order_ref": request_plan[0]["order_ref"],
        },
        now=datetime(2026, 6, 16, 15, 0, 0),
    )
    reply_csv.write_text("db_row_id,reply_text,product_type\n1,рост 175 вес 75,CL\n", encoding="utf-8")
    capsys.readouterr()

    rc = after_reply_observation_main(
        [
            "--reply-csv",
            str(reply_csv),
            "--db",
            str(db_path),
            "--ledger-db",
            str(ledger_path),
            "--target-date",
            "2026-06-15",
            "--lookback-days",
            "2",
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    reply_manifest = json.loads(
        (out_dir / "01_reply_observations" / "manifest.json").read_text(encoding="utf-8")
    )
    patch_manifest = json.loads(
        (out_dir / "02_google_board_patch_packet" / "manifest.json").read_text(encoding="utf-8")
    )
    apply_manifest = json.loads(
        (out_dir / "03_google_board_apply_handoff" / "manifest.json").read_text(encoding="utf-8")
    )
    snapshot = export_customer_size_ledger_snapshot(ledger_path)
    output_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in out_dir.rglob("*")
        if path.is_file() and path.suffix in {".json", ".md", ".txt", ".csv"}
    )

    assert rc == 0
    assert manifest["gate"] == "GREEN_AFTER_REPLY_OBSERVATION_GOOGLE_BOARD_APPLY_HANDOFF_READY_NO_EXTERNAL_WRITE"
    assert reply_manifest["gate"] == "GREEN_CUSTOMER_SIZE_REPLY_OBSERVATIONS_CLASSIFICATION_READY_NO_EXTERNAL_WRITE"
    assert patch_manifest["gate"] == "GREEN_GOOGLE_BOARD_SIZE_PATCH_PACKET_READY_NO_WRITE"
    assert apply_manifest["gate"] == "GREEN_GOOGLE_BOARD_MY_SIZE_APPLY_HANDOFF_READY_NO_WRITE"
    assert patch_manifest["patch_rows_count"] == 1
    assert snapshot[0]["status"] == "CLASSIFICATION_READY"
    assert snapshot[0]["planned_size"] == "L"
    assert manifest["google_board_write_allowed"] is False
    assert manifest["db_write_allowed"] is False
    assert manifest["telegram_send_allowed"] is False
    assert "рост 175 вес 75" not in output_text


def test_ledger_next_actions_prioritize_ready_size_before_send_canary(tmp_path):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
    )
    request_plan = build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE)
    upsert_request_ledger_plan(ledger_path, request_plan)
    record_synthetic_reply_observations(
        ledger_path,
        [
            {
                "order_ref": request_plan[0]["order_ref"],
                "reply_text": "рост 175 вес 75",
                "product_type": "CL",
            }
        ],
    )

    snapshot = export_customer_size_ledger_snapshot(ledger_path)
    actions = build_customer_size_next_actions(snapshot)
    summary = summarize_customer_size_ledger(snapshot)

    assert actions[0]["suggested_action"] == "GOOGLE_BOARD_SIZE_FILL_READY_DRY_RUN"
    assert actions[0]["planned_my_size"] == "L"
    assert actions[0]["google_board_write_allowed"] is False
    assert actions[0]["customer_send_allowed"] is False
    assert summary["google_board_size_fill_ready_count"] == 1
    assert summary["pending_live_send_canary_count"] == 1


def test_live_ui_canary_targets_are_store_and_status_aware(tmp_path):
    db_path = tmp_path / "orders.db"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
    )

    targets = build_live_ui_canary_targets(candidates)
    summary = summarize_live_ui_targets_by_store(targets)

    assert targets
    assert targets[0]["suggested_merchant_status_filter"] == "KASPI_DELIVERY_WAIT_FOR_COURIER"
    assert targets[0]["requires_matching_merchant_account"] is True
    assert targets[0]["raw_order_id_exported"] is False
    assert "status=KASPI_DELIVERY_WAIT_FOR_COURIER" in targets[0]["suggested_merchant_orders_url"]
    assert {row["store_code"] for row in summary} == {"ACMEWEAR", "UNIVERSAL"}


def test_status_filter_hint_for_new_order():
    assert suggest_merchant_status_filter({"internal_status": "NEW", "kaspi_status": ""}) == "NEW"


def test_status_filter_hint_for_accepted_kaspi_delivery_order():
    assert (
        suggest_merchant_status_filter(
            {"internal_status": "ACCEPTED", "kaspi_status": "KASPI_DELIVERY"}
        )
        == "KASPI_DELIVERY_CARGO_ASSEMBLY"
    )


def test_status_filter_hint_for_ready_kaspi_delivery_order():
    assert (
        suggest_merchant_status_filter(
            {"internal_status": "READY", "kaspi_status": "KASPI_DELIVERY"}
        )
        == "KASPI_DELIVERY_WAIT_FOR_COURIER"
    )


def test_google_board_update_plan_does_not_emit_raw_reply_text():
    plan = build_google_board_update_plan(
        [
            {
                "db_row_id": 7,
                "order_ref": "sha256:orderref",
                "reply_text": "рост 175 вес 75",
                "product_type": "CL",
            }
        ]
    )

    assert plan[0]["planned_my_size"] == "L"
    assert plan[0]["google_board_column"] == "MY_SIZE"
    assert plan[0]["write_allowed"] is False
    assert "reply_text" not in plan[0]


def test_chat_trigger_fixture_probe_finds_order_chat_without_send_surface():
    html = """
    <html><body>
      <button class="init-chat-button chat-section" type="CLIENT_SELLER_BY_ORDER">
        <span class="web-chat-trigger">Сообщения по заказу</span>
      </button>
    </body></html>
    """

    result = inspect_chat_trigger_html(html)

    assert result["gate"] == "GREEN_CHAT_TRIGGER_SELECTOR_FOUND_NO_SEND"
    assert result["order_chat_trigger_count"] == 1
    assert result["send_surface_marker_observed"] is False


def test_planner_cli_writes_redacted_evidence_without_db_mutation(tmp_path):
    db_path = tmp_path / "orders.db"
    out_dir = tmp_path / "out"
    _make_orders_db(db_path)

    rc = plan_main(
        [
            "--db",
            str(db_path),
            "--target-date",
            "2026-06-15",
            "--lookback-days",
            "2",
            "--store",
            "ACMEWEAR",
            "--output-dir",
            str(out_dir),
        ]
    )

    assert rc == 0
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    candidates_text = (out_dir / "missing_size_candidates_redacted.json").read_text(
        encoding="utf-8"
    )
    assert manifest["gate"] == "GREEN_NO_SEND_PLAN_GENERATED"
    assert manifest["db_unchanged"] is True
    assert manifest["candidate_count"] == 1
    assert manifest["live_ui_canary_target_count"] == 1
    assert manifest["live_ui_canary_requires_matching_merchant_account"] is True
    targets = json.loads((out_dir / "live_ui_canary_targets_redacted.json").read_text(encoding="utf-8"))
    assert targets[0]["raw_order_id_exported"] is False
    assert "938710785" not in candidates_text


def test_control_plane_cli_persists_local_ledger_and_keeps_app_db_unchanged(tmp_path):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "runtime" / "ledger.sqlite"
    out_dir = tmp_path / "out"
    replies_csv = tmp_path / "synthetic_replies.csv"
    _make_orders_db(db_path)

    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    request_plan = build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE)
    replies_csv.write_text(
        "order_ref,reply_text,product_type\n"
        f"{request_plan[0]['order_ref']},рост 175 вес 75,CL\n",
        encoding="utf-8",
    )

    rc = control_plane_main(
        [
            "--db",
            str(db_path),
            "--ledger-db",
            str(ledger_path),
            "--target-date",
            "2026-06-15",
            "--lookback-days",
            "2",
            "--store",
            "ACMEWEAR",
            "--synthetic-replies-csv",
            str(replies_csv),
            "--output-dir",
            str(out_dir),
        ]
    )

    assert rc == 0
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    snapshot_text = (out_dir / "ledger_snapshot_redacted.json").read_text(encoding="utf-8")
    update_plan = json.loads((out_dir / "reply_size_update_plan_dry_run.json").read_text(encoding="utf-8"))
    assert manifest["gate"] == "GREEN_LOCAL_CONTROL_PLANE_NO_SEND"
    assert manifest["app_db_unchanged"] is True
    assert manifest["ledger_db_exists"] is True
    assert manifest["customer_send_allowed"] is False
    assert manifest["db_write_allowed"] is False
    assert manifest["google_board_write_allowed"] is False
    assert manifest["synthetic_reply_observation_stats"]["matched"] == 1
    assert update_plan[0]["planned_my_size"] == "L"
    assert "938710785" not in snapshot_text
    assert "рост 175 вес 75" not in snapshot_text


def test_scheduler_preflight_refreshes_ledger_without_installing_scheduler(tmp_path):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "runtime" / "ledger.sqlite"
    out_dir = tmp_path / "out"
    _make_orders_db(db_path)

    rc = scheduler_preflight_main(
        [
            "--db",
            str(db_path),
            "--ledger-db",
            str(ledger_path),
            "--target-date",
            "2026-06-15",
            "--lookback-days",
            "2",
            "--output-dir",
            str(out_dir),
        ]
    )

    assert rc == 0
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    next_actions_text = (out_dir / "next_actions_redacted.json").read_text(encoding="utf-8")
    size_fill_plan = json.loads(
        (out_dir / "google_board_size_fill_plan_dry_run.json").read_text(encoding="utf-8")
    )
    proposal_text = (out_dir / "scheduler_proposal_no_apply.md").read_text(encoding="utf-8")
    assert manifest["gate"] == "GREEN_SCHEDULER_PREFLIGHT_NO_SEND_READY"
    assert manifest["scheduler_installed"] is False
    assert manifest["customer_send_allowed"] is False
    assert manifest["kaspi_chat_write_allowed"] is False
    assert manifest["google_board_write_allowed"] is False
    assert manifest["db_write_allowed"] is False
    assert manifest["app_db_unchanged"] is True
    assert manifest["scheduler_summary"]["pending_live_send_canary_count"] == 2
    assert manifest["google_board_size_fill_plan_dry_run_count"] == 0
    assert size_fill_plan == []
    assert "938710785" not in next_actions_text
    assert "PROPOSAL_ONLY_NO_SCHEDULER_CHANGE" in proposal_text


def test_early_send_priority_packet_ranks_pending_targets_and_preserves_selector_gate(tmp_path):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "runtime" / "ledger.sqlite"
    out_dir = tmp_path / "priority"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
    )
    upsert_request_ledger_plan(
        ledger_path,
        build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE),
    )

    rc = early_send_priority_packet_main(
        [
            "--db",
            str(db_path),
            "--ledger-db",
            str(ledger_path),
            "--target-date",
            "2026-06-15",
            "--lookback-days",
            "2",
            "--as-of",
            "2026-06-15T10:30:00",
            "--output-dir",
            str(out_dir),
        ]
    )

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    rows = json.loads((out_dir / "priority_targets_redacted.json").read_text(encoding="utf-8"))
    rows_text = (out_dir / "priority_targets_redacted.json").read_text(encoding="utf-8")

    assert rc == 0
    assert manifest["gate"] == "GREEN_EARLY_SEND_PRIORITY_PACKET_READY_NO_WRITE"
    assert manifest["priority_target_count"] == 2
    assert manifest["customer_send_allowed"] is False
    assert manifest["kaspi_chat_write_allowed"] is False
    assert manifest["google_board_write_allowed"] is False
    assert manifest["app_db_unchanged"] is True
    assert manifest["ledger_db_unchanged"] is True
    assert rows[0]["sequence"] == 1
    assert rows[0]["store_code"] == "UNIVERSAL"
    assert rows[0]["expected_merchant_account_id"] == "30000001"
    assert rows[0]["requires_matching_merchant_account"] is True
    assert rows[0]["priority_band"] == "critical_over_120m"
    assert rows[1]["store_code"] == "ACMEWEAR"
    assert rows[1]["expected_merchant_account_id"] == "30137883"
    assert "938710785" not in rows_text
    assert "938710788" not in rows_text


def test_early_send_priority_packet_excludes_already_sent_rows(tmp_path):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "runtime" / "ledger.sqlite"
    out_dir = tmp_path / "priority"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
    )
    plan = build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE)
    upsert_request_ledger_plan(ledger_path, plan)
    acmewear_ref = next(row["order_ref"] for row in plan if row["store_code"] == "ACMEWEAR")
    with sqlite3.connect(ledger_path) as conn:
        conn.execute(
            """
            UPDATE customer_size_request_ledger
            SET status = 'REQUEST_SENT'
            WHERE order_ref = ?
            """,
            (acmewear_ref,),
        )
        conn.commit()

    rc = early_send_priority_packet_main(
        [
            "--db",
            str(db_path),
            "--ledger-db",
            str(ledger_path),
            "--target-date",
            "2026-06-15",
            "--lookback-days",
            "2",
            "--as-of",
            "2026-06-15T10:30:00",
            "--output-dir",
            str(out_dir),
        ]
    )

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    rows = json.loads((out_dir / "priority_targets_redacted.json").read_text(encoding="utf-8"))
    excluded = json.loads((out_dir / "excluded_current_candidates_redacted.json").read_text(encoding="utf-8"))

    assert rc == 0
    assert manifest["gate"] == "GREEN_EARLY_SEND_PRIORITY_PACKET_READY_NO_WRITE"
    assert manifest["priority_target_count"] == 1
    assert rows[0]["store_code"] == "UNIVERSAL"
    assert any(row["ledger_status"] == "REQUEST_SENT" for row in excluded)
    assert all(row["raw_order_id_exported"] is False for row in excluded)


def test_early_send_priority_packet_prioritizes_one_row_per_order_ref(tmp_path):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "runtime" / "ledger.sqlite"
    out_dir = tmp_path / "priority"
    _make_orders_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi (
                id, order_id, store_code, sku_key, sku_id, my_size, assigned_size,
                customer_height_cm, customer_weight_kg, internal_status, kaspi_status,
                planned_shipment_date, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                5,
                "938710785",
                "ACMEWEAR",
                "CL_OC_MEN_LINE51_WHITE",
                "CL_OC_MEN_LINE51_WHITE_M",
                None,
                None,
                None,
                None,
                "NEW",
                "APPROVED_BY_BANK",
                "2026-06-15",
                "2026-06-15 09:05:00",
            ),
        )
        conn.commit()
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
    )
    upsert_request_ledger_plan(
        ledger_path,
        build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE),
    )

    rc = early_send_priority_packet_main(
        [
            "--db",
            str(db_path),
            "--ledger-db",
            str(ledger_path),
            "--target-date",
            "2026-06-15",
            "--lookback-days",
            "2",
            "--as-of",
            "2026-06-15T10:30:00",
            "--output-dir",
            str(out_dir),
        ]
    )

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    rows = json.loads((out_dir / "priority_targets_redacted.json").read_text(encoding="utf-8"))
    excluded = json.loads((out_dir / "excluded_current_candidates_redacted.json").read_text(encoding="utf-8"))
    order_refs = [row["order_ref"] for row in rows]

    assert rc == 0
    assert manifest["gate"] == "GREEN_EARLY_SEND_PRIORITY_PACKET_READY_NO_WRITE"
    assert len(order_refs) == len(set(order_refs))
    assert manifest["priority_target_count"] == 2
    assert any(
        row["reason"] == "duplicate_current_candidate_same_order_ref_prioritized_once"
        for row in excluded
    )


def test_live_canary_packet_is_redacted_and_selects_store_priority(tmp_path):
    db_path = tmp_path / "orders.db"
    out_dir = tmp_path / "out"
    _make_orders_db(db_path)

    rc = canary_packet_main(
        [
            "--db",
            str(db_path),
            "--target-date",
            "2026-06-15",
            "--lookback-days",
            "2",
            "--store-priority",
            "ACMEWEAR",
            "--output-dir",
            str(out_dir),
        ]
    )

    assert rc == 0
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    target_text = (out_dir / "selected_live_ui_canary_target_redacted.json").read_text(
        encoding="utf-8"
    )
    handoff_text = (out_dir / "live_ui_no_send_canary_handoff.md").read_text(encoding="utf-8")
    assert manifest["gate"] == "GREEN_LIVE_UI_NO_SEND_CANARY_PACKET_READY"
    assert manifest["selected_store_code"] == "ACMEWEAR"
    assert manifest["db_unchanged"] is True
    assert manifest["raw_order_id_exported"] is False
    assert manifest["customer_send_allowed"] is False
    assert manifest["kaspi_chat_write_allowed"] is False
    assert "938710785" not in target_text
    assert "938710785" not in handoff_text
    assert "button.init-chat-button.chat-section" in handoff_text


def test_runtime_secret_resolver_prints_order_id_only_to_stdout_and_redacts_audit(
    tmp_path, capsys
):
    db_path = tmp_path / "orders.db"
    out_dir = tmp_path / "out"
    audit_path = out_dir / "runtime_secret_audit_redacted.json"
    _make_orders_db(db_path)
    assert (
        canary_packet_main(
            [
                "--db",
                str(db_path),
                "--target-date",
                "2026-06-15",
                "--lookback-days",
                "2",
                "--store-priority",
                "ACMEWEAR",
                "--output-dir",
                str(out_dir),
            ]
        )
        == 0
    )
    capsys.readouterr()

    rc = resolve_canary_secret_main(
        [
            "--db",
            str(db_path),
            "--packet-manifest",
            str(out_dir / "manifest.json"),
            "--audit-json",
            str(audit_path),
            "--print-raw-order-id",
        ]
    )
    captured = capsys.readouterr()
    audit_text = audit_path.read_text(encoding="utf-8")
    audit = json.loads(audit_text)

    assert rc == 0
    assert captured.out.strip() == "938710785"
    assert audit["gate"] == "GREEN_RUNTIME_SECRET_RESOLVED_REDACTED_AUDIT"
    assert audit["raw_order_id_printed_to_stdout"] is True
    assert audit["raw_order_id_exported"] is False
    assert audit["candidate_still_missing_size"] is True
    assert "938710785" not in audit_text


def test_runtime_secret_resolver_fails_closed_on_packet_hash_mismatch(tmp_path, capsys):
    db_path = tmp_path / "orders.db"
    out_dir = tmp_path / "out"
    audit_path = out_dir / "runtime_secret_audit_redacted.json"
    _make_orders_db(db_path)
    assert (
        canary_packet_main(
            [
                "--db",
                str(db_path),
                "--target-date",
                "2026-06-15",
                "--lookback-days",
                "2",
                "--store-priority",
                "ACMEWEAR",
                "--output-dir",
                str(out_dir),
            ]
        )
        == 0
    )
    manifest_path = out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["selected_order_ref"] = "sha256:tampered"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    capsys.readouterr()

    rc = resolve_canary_secret_main(
        [
            "--db",
            str(db_path),
            "--packet-manifest",
            str(manifest_path),
            "--audit-json",
            str(audit_path),
            "--print-raw-order-id",
        ]
    )
    captured = capsys.readouterr()
    audit_text = audit_path.read_text(encoding="utf-8")
    audit = json.loads(audit_text)

    assert rc == 2
    assert captured.out == ""
    assert audit["gate"] == "RED_RUNTIME_SECRET_ORDER_HASH_MISMATCH"
    assert audit["raw_order_id_exported"] is False
    assert "938710785" not in audit_text


def test_generic_customer_size_order_resolver_prints_raw_only_to_stdout_and_redacts_audit(
    tmp_path, capsys
):
    db_path = tmp_path / "orders.db"
    audit_path = tmp_path / "audit_redacted.json"
    _make_orders_db(db_path)
    order_ref = private_hash("kaspi_order_id", "938710785")

    rc = resolve_customer_size_order_secret_main(
        [
            "--db",
            str(db_path),
            "--db-row-id",
            "1",
            "--order-ref",
            order_ref,
            "--audit-json",
            str(audit_path),
            "--print-raw-order-id",
        ]
    )
    captured = capsys.readouterr()
    audit_text = audit_path.read_text(encoding="utf-8")
    audit = json.loads(audit_text)

    assert rc == 0
    assert captured.out.strip() == "938710785"
    assert audit["gate"] == "GREEN_RUNTIME_SECRET_RESOLVED_REDACTED_AUDIT"
    assert audit["resolved_order_ref"] == order_ref
    assert audit["raw_order_id_printed_to_stdout"] is True
    assert audit["raw_order_id_exported"] is False
    assert "938710785" not in audit_text


def test_generic_customer_size_order_resolver_fails_closed_on_ref_mismatch(
    tmp_path, capsys
):
    db_path = tmp_path / "orders.db"
    audit_path = tmp_path / "audit_redacted.json"
    _make_orders_db(db_path)

    rc = resolve_customer_size_order_secret_main(
        [
            "--db",
            str(db_path),
            "--db-row-id",
            "1",
            "--order-ref",
            "sha256:wrong",
            "--audit-json",
            str(audit_path),
            "--print-raw-order-id",
        ]
    )
    captured = capsys.readouterr()
    audit_text = audit_path.read_text(encoding="utf-8")
    audit = json.loads(audit_text)

    assert rc == 2
    assert captured.out == ""
    assert audit["gate"] == "RED_RUNTIME_SECRET_ORDER_HASH_MISMATCH"
    assert audit["raw_order_id_exported"] is False
    assert "938710785" not in audit_text


def _prepare_resolved_canary_packet(tmp_path: Path, capsys):
    db_path = tmp_path / "orders.db"
    out_dir = tmp_path / "out"
    _make_orders_db(db_path)
    assert (
        canary_packet_main(
            [
                "--db",
                str(db_path),
                "--target-date",
                "2026-06-15",
                "--lookback-days",
                "2",
                "--store-priority",
                "ACMEWEAR",
                "--output-dir",
                str(out_dir),
            ]
        )
        == 0
    )
    assert (
        resolve_canary_secret_main(
            [
                "--db",
                str(db_path),
                "--packet-manifest",
                str(out_dir / "manifest.json"),
                "--audit-json",
                str(out_dir / "runtime_secret_resolver_audit_redacted.json"),
            ]
        )
        == 0
    )
    capsys.readouterr()
    return db_path, out_dir


def _write_chrome_diagnostics_fixture(path: Path, *, extension_enabled: bool = True) -> None:
    payload = {
        "chrome_is_running": {"returncode": 0, "ok": True, "stdout_json": {"running": True}},
        "installed_browsers": {
            "returncode": 0,
            "ok": True,
            "stdout_json": {"installed_browsers": [{"name": "Google Chrome"}]},
        },
        "extension_installed": {
            "returncode": 0 if extension_enabled else 1,
            "ok": extension_enabled,
            "stdout_json": {
                "selectedProfileDirectory": "Profile 4",
                "installed": True,
                "enabled": extension_enabled,
            },
        },
        "native_host_manifest": {
            "returncode": 0,
            "ok": True,
            "stdout_json": {"correct": True},
        },
        "open_chrome_window_dry_run": {
            "returncode": 0,
            "ok": True,
            "stdout_json": {
                "dryRun": True,
                "profileDirectory": "Profile 4",
                "command": "open",
                "args": [
                    "-n",
                    "-a",
                    "/Applications/Google Chrome.app",
                    "--args",
                    "--profile-directory=Profile 4",
                    "--new-window",
                    "about:blank",
                ],
            },
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_json_fixture(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _missing_open_chat_args(tmp_path: Path) -> list[str]:
    return [
        "--open-chat-no-type-packet-manifest",
        str(tmp_path / "missing_open_chat_packet_manifest.json"),
        "--open-chat-no-type-result-validation-json",
        str(tmp_path / "missing_open_chat_result_validation.json"),
    ]


def _missing_resident_heartbeat_args(tmp_path: Path) -> list[str]:
    return [
        "--resident-heartbeat-manifest",
        str(tmp_path / "missing_resident_heartbeat.json"),
    ]


def test_chrome_reconnect_packet_resolves_latest_plugin_root(tmp_path, monkeypatch):
    base = tmp_path / "chrome"
    older = base / "26.1.0" / "scripts"
    newer = base / "26.2.0" / "scripts"
    older.mkdir(parents=True)
    newer.mkdir(parents=True)
    (older / "chrome-is-running.js").write_text("", encoding="utf-8")
    (newer / "chrome-is-running.js").write_text("", encoding="utf-8")
    monkeypatch.delenv(CHROME_PLUGIN_ROOT_ENV, raising=False)

    assert _resolve_chrome_plugin_root(base) == newer.parent

    override = tmp_path / "override"
    monkeypatch.setenv(CHROME_PLUGIN_ROOT_ENV, str(override))
    assert _resolve_chrome_plugin_root(base) == override.resolve()


def test_live_canary_result_validator_stays_yellow_when_browser_result_missing(tmp_path, capsys):
    _, out_dir = _prepare_resolved_canary_packet(tmp_path, capsys)
    validation_path = out_dir / "live_ui_canary_result_validation.json"

    rc = validate_canary_result_main(
        [
            "--packet-dir",
            str(out_dir),
            "--output-json",
            str(validation_path),
        ]
    )
    captured = capsys.readouterr()
    validation = json.loads(validation_path.read_text(encoding="utf-8"))

    assert rc == 0
    assert validation["gate"] == "YELLOW_LIVE_UI_RESULT_MISSING"
    assert "live_ui_probe_result_missing" in validation["blockers"]
    assert "938710785" not in captured.out
    assert "938710785" not in validation_path.read_text(encoding="utf-8")


def test_workflow_readiness_packet_summarizes_current_yellow_blockers(tmp_path, capsys):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    out_dir = tmp_path / "workflow"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    request_plan = build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE)
    upsert_request_ledger_plan(ledger_path, request_plan)
    live_ui_path = tmp_path / "live_ui.json"
    chrome_path = tmp_path / "chrome" / "chrome_reconnect_preflight_manifest.json"
    send_path = tmp_path / "send" / "manifest.json"
    patch_path = tmp_path / "patch" / "manifest.json"
    cadence_path = tmp_path / "cadence" / "manifest.json"
    _write_json_fixture(live_ui_path, {"gate": "YELLOW_LIVE_UI_RESULT_INCOMPLETE"})
    _write_json_fixture(
        chrome_path,
        {"gate": "YELLOW_CHROME_RECONNECT_APPROVAL_REQUIRED_NO_UI_ACTION"},
    )
    _write_json_fixture(
        send_path,
        {"gate": "YELLOW_LIVE_SEND_CANARY_APPROVAL_PACKET_BLOCKED_NO_SEND"},
    )
    _write_json_fixture(
        patch_path,
        {"gate": "GREEN_GOOGLE_BOARD_SIZE_PATCH_PACKET_READY_NO_WRITE", "patch_rows_count": 0},
    )
    _write_json_fixture(
        cadence_path,
        {"gate": "YELLOW_CUSTOMER_SIZE_CADENCE_READY_WITH_RETAINED_BLOCKERS_NO_APPLY"},
    )

    rc = workflow_readiness_packet_main(
        [
            "--db",
            str(db_path),
            "--ledger-db",
            str(ledger_path),
            "--live-ui-validation-json",
            str(live_ui_path),
            "--chrome-reconnect-manifest",
            str(chrome_path),
            "--live-send-approval-manifest",
            str(send_path),
            *_missing_resident_heartbeat_args(tmp_path),
            *_missing_open_chat_args(tmp_path),
            "--google-board-patch-manifest",
            str(patch_path),
            "--cadence-manifest",
            str(cadence_path),
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    blockers = json.loads((out_dir / "retained_blockers.json").read_text(encoding="utf-8"))
    stages = json.loads((out_dir / "workflow_stages.json").read_text(encoding="utf-8"))

    assert rc == 0
    assert manifest["gate"] == "YELLOW_CUSTOMER_SIZE_WORKFLOW_READY_WITH_RETAINED_BLOCKERS_NO_EXTERNAL_WRITE"
    assert manifest["customer_send_allowed"] is False
    assert manifest["ledger_summary"]["pending_live_send_canary_count"] == 1
    assert {row["blocker"] for row in blockers} == {
        "live_ui_no_send_not_green",
        "chrome_reconnect_approval_required",
    }
    assert any(row["stage"] == "reply_observation_and_size_classification" for row in stages)
    assert "938710785" not in (out_dir / "next_actions_redacted.json").read_text(encoding="utf-8")


def test_workflow_readiness_packet_can_go_green_when_source_gates_are_green(tmp_path, capsys):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    out_dir = tmp_path / "workflow"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    request_plan = build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE)
    upsert_request_ledger_plan(ledger_path, request_plan)
    live_ui_path = tmp_path / "live_ui.json"
    chrome_path = tmp_path / "chrome" / "chrome_reconnect_preflight_manifest.json"
    send_path = tmp_path / "send" / "manifest.json"
    patch_path = tmp_path / "patch" / "manifest.json"
    cadence_path = tmp_path / "cadence" / "manifest.json"
    _write_json_fixture(live_ui_path, {"gate": "GREEN_LIVE_UI_NO_SEND_CANARY_RESULT_ACCEPTED"})
    _write_json_fixture(chrome_path, {"gate": "GREEN_CHROME_RECONNECTED"})
    _write_json_fixture(send_path, {"gate": "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY"})
    _write_json_fixture(
        patch_path,
        {"gate": "GREEN_GOOGLE_BOARD_SIZE_PATCH_PACKET_READY_NO_WRITE", "patch_rows_count": 0},
    )
    _write_json_fixture(cadence_path, {"gate": "GREEN_CUSTOMER_SIZE_CADENCE_READY_NO_APPLY"})

    rc = workflow_readiness_packet_main(
        [
            "--db",
            str(db_path),
            "--ledger-db",
            str(ledger_path),
            "--live-ui-validation-json",
            str(live_ui_path),
            "--chrome-reconnect-manifest",
            str(chrome_path),
            "--live-send-approval-manifest",
            str(send_path),
            *_missing_resident_heartbeat_args(tmp_path),
            *_missing_open_chat_args(tmp_path),
            "--google-board-patch-manifest",
            str(patch_path),
            "--cadence-manifest",
            str(cadence_path),
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    blockers = json.loads((out_dir / "retained_blockers.json").read_text(encoding="utf-8"))

    assert rc == 0
    assert manifest["gate"] == "GREEN_CUSTOMER_SIZE_WORKFLOW_READY_FOR_OWNER_SEND_APPROVAL"
    assert blockers == []
    assert manifest["customer_send_allowed"] is False


def test_workflow_readiness_packet_accepts_computer_use_no_send_green_despite_chrome_yellow(
    tmp_path, capsys
):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    out_dir = tmp_path / "workflow"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    upsert_request_ledger_plan(
        ledger_path,
        build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE),
    )
    live_ui_path = tmp_path / "live_ui.json"
    chrome_path = tmp_path / "chrome" / "chrome_reconnect_preflight_manifest.json"
    send_path = tmp_path / "send" / "manifest.json"
    _write_json_fixture(live_ui_path, {"gate": "GREEN_LIVE_UI_NO_SEND_CANARY_RESULT_ACCEPTED"})
    _write_json_fixture(
        chrome_path,
        {"gate": "YELLOW_CHROME_EXTENSION_CHANNEL_UNAVAILABLE_AFTER_APPROVED_RETRY"},
    )
    _write_json_fixture(send_path, {"gate": "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND"})

    rc = workflow_readiness_packet_main(
        [
            "--db",
            str(db_path),
            "--ledger-db",
            str(ledger_path),
            "--live-ui-validation-json",
            str(live_ui_path),
            "--chrome-reconnect-manifest",
            str(chrome_path),
            "--live-send-approval-manifest",
            str(send_path),
            *_missing_resident_heartbeat_args(tmp_path),
            *_missing_open_chat_args(tmp_path),
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    blockers = json.loads((out_dir / "retained_blockers.json").read_text(encoding="utf-8"))

    assert rc == 0
    assert manifest["gate"] == "GREEN_CUSTOMER_SIZE_WORKFLOW_READY_FOR_OWNER_SEND_APPROVAL"
    assert blockers == []
    assert manifest["customer_send_allowed"] is False


def test_workflow_readiness_packet_accepts_resident_button_green_as_current_no_send_proof(
    tmp_path, capsys
):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    out_dir = tmp_path / "workflow"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    upsert_request_ledger_plan(
        ledger_path,
        build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE),
    )
    live_ui_path = tmp_path / "live_ui.json"
    resident_button_path = tmp_path / "resident" / "manifest.json"
    chrome_path = tmp_path / "chrome" / "chrome_reconnect_preflight_manifest.json"
    send_path = tmp_path / "send" / "manifest.json"
    send_execution_path = tmp_path / "send_execution" / "manifest.json"
    reply_polling_path = tmp_path / "reply_polling" / "manifest.json"
    _write_json_fixture(live_ui_path, {"gate": "YELLOW_OLDER_LIVE_UI_NO_SEND_NOT_CURRENT"})
    _write_json_fixture(
        resident_button_path,
        {
            "gate": "GREEN_KASPI_CUSTOMER_CHAT_MESSAGE_BUTTON_PROVEN_NO_SEND",
            "requires_matching_merchant_account": True,
            "expected_merchant_account_id": "30137883",
        },
    )
    _write_json_fixture(
        chrome_path,
        {"gate": "YELLOW_CHROME_EXTENSION_CHANNEL_UNAVAILABLE_AFTER_APPROVED_RETRY"},
    )
    _write_json_fixture(send_path, {"gate": "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND"})
    _write_json_fixture(
        send_execution_path,
        {"gate": "YELLOW_LIVE_SEND_CANARY_EXECUTION_PREFLIGHT_AWAITING_OWNER_APPROVAL_NO_SEND"},
    )
    _write_json_fixture(
        reply_polling_path,
        {
            "gate": "YELLOW_REPLY_POLLING_EXECUTION_PREFLIGHT_NO_POLLABLE_ROWS_NO_SEND",
            "poll_target_count": 0,
        },
    )

    rc = workflow_readiness_packet_main(
        [
            "--db",
            str(db_path),
            "--ledger-db",
            str(ledger_path),
            "--live-ui-validation-json",
            str(live_ui_path),
            "--resident-button-manifest",
            str(resident_button_path),
            "--chrome-reconnect-manifest",
            str(chrome_path),
            "--live-send-approval-manifest",
            str(send_path),
            *_missing_resident_heartbeat_args(tmp_path),
            *_missing_open_chat_args(tmp_path),
            "--live-send-execution-preflight-manifest",
            str(send_execution_path),
            "--reply-polling-preflight-manifest",
            str(reply_polling_path),
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    blockers = json.loads((out_dir / "retained_blockers.json").read_text(encoding="utf-8"))
    stages = json.loads((out_dir / "workflow_stages.json").read_text(encoding="utf-8"))
    proof_stage = next(row for row in stages if row["stage"] == "live_ui_no_send_proof")
    execution_stage = next(
        row for row in stages if row["stage"] == "single_order_live_send_canary_execution_preflight"
    )
    reply_polling_stage = next(row for row in stages if row["stage"] == "reply_polling_preflight")

    assert rc == 0
    assert manifest["gate"] == "GREEN_CUSTOMER_SIZE_WORKFLOW_READY_FOR_OWNER_SEND_APPROVAL"
    assert blockers == []
    assert manifest["source_manifests"]["resident_button_manifest"] == str(resident_button_path)
    assert proof_stage["allowed_now"] is True
    assert proof_stage["resident_button_gate"] == "GREEN_KASPI_CUSTOMER_CHAT_MESSAGE_BUTTON_PROVEN_NO_SEND"
    assert execution_stage["gate"] == "YELLOW_LIVE_SEND_CANARY_EXECUTION_PREFLIGHT_AWAITING_OWNER_APPROVAL_NO_SEND"
    assert reply_polling_stage["current_count"] == 0
    assert manifest["customer_send_allowed"] is False


def test_workflow_readiness_packet_requires_open_chat_no_type_when_packet_exists(
    tmp_path, capsys
):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    out_dir = tmp_path / "workflow"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    upsert_request_ledger_plan(
        ledger_path,
        build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE),
    )
    resident_button_path = tmp_path / "resident" / "manifest.json"
    send_path = tmp_path / "send" / "manifest.json"
    open_chat_packet_path = tmp_path / "open_chat" / "manifest.json"
    open_chat_approval_path = (
        tmp_path / "open_chat" / "REQUIRED_EXACT_OPEN_CHAT_NO_TYPE_APPROVAL_PHRASE.txt"
    )
    open_chat_result_path = tmp_path / "open_chat_result" / "open_chat_no_type_result_validation.json"
    _write_json_fixture(
        resident_button_path,
        {"gate": "GREEN_KASPI_CUSTOMER_CHAT_MESSAGE_BUTTON_PROVEN_NO_SEND"},
    )
    _write_json_fixture(send_path, {"gate": "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND"})
    _write_json_fixture(
        open_chat_packet_path,
        {"gate": "GREEN_OPEN_CHAT_NO_TYPE_CANARY_PACKET_READY_NO_SEND"},
    )
    _write_json_fixture(
        open_chat_result_path,
        {
            "gate": "YELLOW_OPEN_CHAT_NO_TYPE_CANARY_RESULT_MISSING",
            "blockers": ["open_chat_no_type_result_missing"],
        },
    )

    rc = workflow_readiness_packet_main(
        [
            "--db",
            str(db_path),
            "--ledger-db",
            str(ledger_path),
            "--resident-button-manifest",
            str(resident_button_path),
            "--live-send-approval-manifest",
            str(send_path),
            *_missing_resident_heartbeat_args(tmp_path),
            "--open-chat-no-type-packet-manifest",
            str(open_chat_packet_path),
            "--open-chat-no-type-result-validation-json",
            str(open_chat_result_path),
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    blockers = json.loads((out_dir / "retained_blockers.json").read_text(encoding="utf-8"))
    stages = json.loads((out_dir / "workflow_stages.json").read_text(encoding="utf-8"))
    open_chat_stage = next(row for row in stages if row["stage"] == "open_chat_no_type_side_effect_canary")
    approval_stage = next(row for row in stages if row["stage"] == "single_order_live_send_canary_approval_packet")

    assert rc == 0
    assert manifest["gate"] == "YELLOW_CUSTOMER_SIZE_WORKFLOW_READY_WITH_RETAINED_BLOCKERS_NO_EXTERNAL_WRITE"
    assert manifest["critical_next_stage"] == "open_chat_no_type_side_effect_canary"
    assert blockers == [
        {
            "stage": "open_chat_no_type_side_effect_canary",
            "blocker": "open_chat_no_type_result_not_accepted",
            "packet_gate": "GREEN_OPEN_CHAT_NO_TYPE_CANARY_PACKET_READY_NO_SEND",
            "result_gate": "YELLOW_OPEN_CHAT_NO_TYPE_CANARY_RESULT_MISSING",
            "approval_phrase_file": str(open_chat_approval_path.resolve()),
        }
    ]
    assert open_chat_stage["allowed_now"] is False
    assert approval_stage["allowed_now"] is False
    assert manifest["customer_send_allowed"] is False


def test_workflow_readiness_packet_prioritizes_login_heartbeat_before_open_chat(
    tmp_path, capsys
):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    out_dir = tmp_path / "workflow"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    upsert_request_ledger_plan(
        ledger_path,
        build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE),
    )
    heartbeat_path = tmp_path / "heartbeat.json"
    resident_button_path = tmp_path / "resident" / "manifest.json"
    send_path = tmp_path / "send" / "manifest.json"
    open_chat_packet_path = tmp_path / "open_chat" / "manifest.json"
    open_chat_result_path = tmp_path / "open_chat_result" / "open_chat_no_type_result_validation.json"
    _write_json_fixture(
        heartbeat_path,
        {
            "gate": "YELLOW_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_WAITING_FOR_LOGIN",
            "orders_search_input_visible": False,
            "safe_current_url": "https://idmc.shop.kaspi.kz/login",
            "browser_should_remain_open": True,
        },
    )
    _write_json_fixture(
        resident_button_path,
        {"gate": "GREEN_KASPI_CUSTOMER_CHAT_MESSAGE_BUTTON_PROVEN_NO_SEND"},
    )
    _write_json_fixture(send_path, {"gate": "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND"})
    _write_json_fixture(
        open_chat_packet_path,
        {"gate": "GREEN_OPEN_CHAT_NO_TYPE_CANARY_PACKET_READY_NO_SEND"},
    )
    _write_json_fixture(
        open_chat_result_path,
        {"gate": "YELLOW_OPEN_CHAT_NO_TYPE_CANARY_RESULT_MISSING"},
    )

    rc = workflow_readiness_packet_main(
        [
            "--db",
            str(db_path),
            "--ledger-db",
            str(ledger_path),
            "--resident-heartbeat-manifest",
            str(heartbeat_path),
            "--resident-button-manifest",
            str(resident_button_path),
            "--live-send-approval-manifest",
            str(send_path),
            "--open-chat-no-type-packet-manifest",
            str(open_chat_packet_path),
            "--open-chat-no-type-result-validation-json",
            str(open_chat_result_path),
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    blockers = json.loads((out_dir / "retained_blockers.json").read_text(encoding="utf-8"))

    assert rc == 0
    assert manifest["critical_next_stage"] == "resident_session_heartbeat"
    assert {
        "stage": "resident_session_heartbeat",
        "blocker": "resident_heartbeat_not_green",
        "gate": "YELLOW_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_WAITING_FOR_LOGIN",
        "orders_search_input_visible": False,
        "safe_current_url": "https://idmc.shop.kaspi.kz/login",
    } in blockers
    assert any(row["stage"] == "open_chat_no_type_side_effect_canary" for row in blockers)
    assert manifest["customer_send_allowed"] is False


def test_workflow_readiness_packet_flags_chrome_retry_failure_as_access_blocker(
    tmp_path, capsys
):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    out_dir = tmp_path / "workflow"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    upsert_request_ledger_plan(
        ledger_path,
        build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE),
    )
    live_ui_path = tmp_path / "live_ui.json"
    chrome_path = tmp_path / "chrome" / "chrome_reconnect_preflight_manifest.json"
    _write_json_fixture(live_ui_path, {"gate": "YELLOW_LIVE_UI_RESULT_INCOMPLETE"})
    _write_json_fixture(
        chrome_path,
        {"gate": "YELLOW_CHROME_EXTENSION_CHANNEL_UNAVAILABLE_AFTER_APPROVED_RETRY"},
    )

    rc = workflow_readiness_packet_main(
        [
            "--db",
            str(db_path),
            "--ledger-db",
            str(ledger_path),
            "--live-ui-validation-json",
            str(live_ui_path),
            "--chrome-reconnect-manifest",
            str(chrome_path),
            *_missing_resident_heartbeat_args(tmp_path),
            *_missing_open_chat_args(tmp_path),
            "--output-dir",
            str(out_dir),
        ]
    )
    blockers = json.loads((out_dir / "retained_blockers.json").read_text(encoding="utf-8"))

    assert rc == 0
    assert {row["blocker"] for row in blockers} == {
        "live_ui_no_send_not_green",
        "chrome_or_computer_use_access_not_green",
    }


def test_owner_dashboard_builds_markdown_and_html_with_exact_next_approval(
    tmp_path, capsys
):
    workflow_dir = tmp_path / "workflow"
    approval_dir = tmp_path / "chrome"
    approval_path = approval_dir / "REQUIRED_EXACT_CHROME_RECONNECT_APPROVAL_PHRASE.txt"
    approval_text = (
        "I approve opening a new Google Chrome window for selected Profile 4 solely "
        "to reconnect the Codex Chrome Extension and retry the Kaspi live UI no-send canary."
    )
    _write_json_fixture(
        workflow_dir / "manifest.json",
        {
            "gate": "YELLOW_CUSTOMER_SIZE_WORKFLOW_READY_WITH_RETAINED_BLOCKERS_NO_EXTERNAL_WRITE",
            "ledger_summary": {
                "ledger_rows": 18,
                "pending_live_send_canary_count": 17,
                "google_board_size_fill_ready_count": 1,
            },
            "blockers_count": 2,
        },
    )
    _write_json_fixture(
        workflow_dir / "workflow_stages.json",
        [
            {
                "sequence": 20,
                "stage": "chrome_or_computer_use_access",
                "gate": "YELLOW_CHROME_RECONNECT_APPROVAL_REQUIRED_NO_UI_ACTION",
                "current_count": 1,
                "next_action": "paste_exact_chrome_reconnect_approval_phrase",
            }
        ],
    )
    _write_json_fixture(
        workflow_dir / "retained_blockers.json",
        [
            {
                "stage": "chrome_or_computer_use_access",
                "blocker": "chrome_reconnect_approval_required",
                "approval_phrase_file": str(approval_path),
            }
        ],
    )
    approval_path.parent.mkdir(parents=True)
    approval_path.write_text(approval_text + "\n", encoding="utf-8")

    rc = owner_dashboard_main(
        [
            "--workflow-dir",
            str(workflow_dir),
            "--output-dir",
            str(tmp_path / "dashboard"),
        ]
    )
    manifest = json.loads((tmp_path / "dashboard" / "manifest.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "dashboard" / "owner_dashboard.md").read_text(encoding="utf-8")
    html_text = (tmp_path / "dashboard" / "owner_dashboard.html").read_text(encoding="utf-8")

    assert rc == 0
    assert manifest["gate"] == "GREEN_OWNER_DASHBOARD_BUILT_FROM_REDACTED_WORKFLOW_PACKET"
    assert manifest["approval_phrase_included"] is True
    assert approval_text in markdown
    assert "paste_exact_chrome_reconnect_approval_phrase" in html_text
    assert "938710785" not in markdown
    assert "рост 175 вес 75" not in markdown


def test_owner_dashboard_handles_missing_approval_phrase_file(tmp_path, capsys):
    workflow_dir = tmp_path / "workflow"
    _write_json_fixture(
        workflow_dir / "manifest.json",
        {
            "gate": "YELLOW_CUSTOMER_SIZE_WORKFLOW_READY_WITH_RETAINED_BLOCKERS_NO_EXTERNAL_WRITE",
            "ledger_summary": {},
            "blockers_count": 1,
        },
    )
    _write_json_fixture(workflow_dir / "workflow_stages.json", [])
    _write_json_fixture(
        workflow_dir / "retained_blockers.json",
        [
            {
                "stage": "live_ui_no_send_proof",
                "blocker": "live_ui_no_send_not_green",
            }
        ],
    )

    rc = owner_dashboard_main(
        [
            "--workflow-dir",
            str(workflow_dir),
            "--output-dir",
            str(tmp_path / "dashboard"),
        ]
    )
    manifest = json.loads((tmp_path / "dashboard" / "manifest.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "dashboard" / "owner_dashboard.md").read_text(encoding="utf-8")

    assert rc == 0
    assert manifest["approval_phrase_included"] is False
    assert "No approval phrase file was available" in markdown


def test_owner_dashboard_keeps_current_blocker_phrase_over_live_send_fallback(
    tmp_path, capsys
):
    workflow_dir = tmp_path / "workflow"
    open_chat_dir = tmp_path / "open_chat"
    live_send_dir = tmp_path / "live_send"
    open_chat_phrase_path = open_chat_dir / "REQUIRED_EXACT_OPEN_CHAT_NO_TYPE_APPROVAL_PHRASE.txt"
    live_send_phrase_path = live_send_dir / "REQUIRED_EXACT_LIVE_SEND_CANARY_APPROVAL_PHRASE.txt"
    open_chat_phrase = "I approve OPEN_CHAT_NO_TYPE current blocker phrase."
    live_send_phrase = "I approve LIVE_SEND fallback phrase that must not override current blocker."
    _write_json_fixture(
        workflow_dir / "manifest.json",
        {
            "gate": "YELLOW_CUSTOMER_SIZE_WORKFLOW_READY_WITH_RETAINED_BLOCKERS_NO_EXTERNAL_WRITE",
            "ledger_summary": {},
            "blockers_count": 1,
        },
    )
    _write_json_fixture(
        workflow_dir / "workflow_stages.json",
        [
            {
                "sequence": 40,
                "stage": "open_chat_no_type_side_effect_canary",
                "gate": "YELLOW_OPEN_CHAT_NO_TYPE_CANARY_RESULT_MISSING",
                "current_count": 1,
                "next_action": "run_or_validate_exact_one_order_open_chat_no_type_canary_before_live_send",
            }
        ],
    )
    _write_json_fixture(
        workflow_dir / "retained_blockers.json",
        [
            {
                "stage": "open_chat_no_type_side_effect_canary",
                "blocker": "open_chat_no_type_result_not_accepted",
                "approval_phrase_file": str(open_chat_phrase_path),
            }
        ],
    )
    open_chat_phrase_path.parent.mkdir(parents=True)
    live_send_phrase_path.parent.mkdir(parents=True)
    open_chat_phrase_path.write_text(open_chat_phrase + "\n", encoding="utf-8")
    live_send_phrase_path.write_text(live_send_phrase + "\n", encoding="utf-8")

    rc = owner_dashboard_main(
        [
            "--workflow-dir",
            str(workflow_dir),
            "--live-send-approval-dir",
            str(live_send_dir),
            "--output-dir",
            str(tmp_path / "dashboard"),
        ]
    )
    manifest = json.loads((tmp_path / "dashboard" / "manifest.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / "dashboard" / "owner_dashboard.md").read_text(encoding="utf-8")

    assert rc == 0
    assert manifest["approval_phrase_included"] is True
    assert manifest["approval_phrase_source"] == str(open_chat_phrase_path)
    assert open_chat_phrase in markdown
    assert live_send_phrase not in markdown


def test_automation_options_matrix_ranks_safe_paths_from_workflow_evidence(tmp_path, capsys):
    workflow_dir = tmp_path / "workflow"
    synthesis_path = tmp_path / "synthesis.md"
    out_dir = tmp_path / "matrix"
    _write_json_fixture(
        workflow_dir / "manifest.json",
        {
            "gate": "YELLOW_CUSTOMER_SIZE_WORKFLOW_READY_WITH_RETAINED_BLOCKERS_NO_EXTERNAL_WRITE",
            "ledger_summary": {"ledger_rows": 18},
        },
    )
    _write_json_fixture(
        workflow_dir / "workflow_stages.json",
        [
            {
                "stage": "live_ui_no_send_proof",
                "gate": "YELLOW_LIVE_UI_RESULT_INCOMPLETE",
            },
            {
                "stage": "chrome_or_computer_use_access",
                "gate": "YELLOW_CHROME_RECONNECT_APPROVAL_REQUIRED_NO_UI_ACTION",
            },
            {
                "stage": "google_board_my_size_patch_packet",
                "gate": "GREEN_GOOGLE_BOARD_SIZE_PATCH_PACKET_READY_NO_WRITE",
            },
        ],
    )
    synthesis_path.write_text(
        "Observed possible /api/v1/messages/sendMessage endpoint, but no safe send proof.",
        encoding="utf-8",
    )

    rc = automation_options_matrix_main(
        [
            "--workflow-dir",
            str(workflow_dir),
            "--synthesis-closeout",
            str(synthesis_path),
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    rows = json.loads((out_dir / "automation_options_matrix.json").read_text(encoding="utf-8"))
    markdown = (out_dir / "automation_options_matrix.md").read_text(encoding="utf-8")

    assert rc == 0
    assert manifest["gate"] == "GREEN_AUTOMATION_OPTIONS_MATRIX_BUILT_FROM_REDACTED_EVIDENCE"
    assert manifest["customer_send_allowed"] is False
    assert rows[0]["option"] == "official_kaspi_order_api_for_detection"
    assert rows[1]["option"] == "kaspi_merchant_ui_browser_automation"
    assert rows[2]["option"] == "hardened_no_send_chat_metadata_capture"
    assert rows[2]["current_status"] == "READY_BUT_STATIC_ONLY_TARGETS_NEED_RECHECK"
    assert rows[3]["option"] == "direct_kaspi_chat_network_api"
    assert rows[3]["current_status"] == "PROMISING_BUT_UNPROVEN"
    assert all(row["customer_send_allowed"] is False for row in rows)
    assert "Best immediate path: Chrome/Profile 4 reconnect" in markdown


def test_automation_options_matrix_promotes_live_confirmed_metadata_capture(tmp_path, capsys):
    workflow_dir = tmp_path / "workflow"
    synthesis_path = tmp_path / "live_synthesis.md"
    out_dir = tmp_path / "matrix"
    _write_json_fixture(
        workflow_dir / "manifest.json",
        {
            "gate": "GREEN_CUSTOMER_SIZE_WORKFLOW_READY_FOR_OWNER_SEND_APPROVAL",
            "ledger_summary": {"ledger_rows": 58},
        },
    )
    _write_json_fixture(
        workflow_dir / "workflow_stages.json",
        [
            {
                "stage": "live_ui_no_send_proof",
                "gate": "GREEN_ALL_PRIORITY_RESIDENT_NO_SEND_BATCH_CHAT_BUTTON_PROOF",
            },
            {
                "stage": "chrome_or_computer_use_access",
                "gate": "YELLOW_CHROME_EXTENSION_TRANSPORT_UNAVAILABLE_AFTER_APPROVED_RETRY",
            },
            {
                "stage": "google_board_my_size_patch_packet",
                "gate": "GREEN_GOOGLE_BOARD_SIZE_PATCH_PACKET_READY_NO_WRITE",
            },
        ],
    )
    synthesis_path.write_text(
        "LIVE observed mc.shop.kaspi.kz/chats/api/mobile/api/v1/group/getDiffGroups/chat, "
        "but messages/sendMessage remains unproven and blocked.",
        encoding="utf-8",
    )

    rc = automation_options_matrix_main(
        [
            "--workflow-dir",
            str(workflow_dir),
            "--synthesis-closeout",
            str(synthesis_path),
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    rows = json.loads((out_dir / "automation_options_matrix.json").read_text(encoding="utf-8"))
    markdown = (out_dir / "automation_options_matrix.md").read_text(encoding="utf-8")

    assert rc == 0
    assert manifest["recommended_immediate_path"] == "computer_use_helper_visual_no_send_proof_then_send_canary"
    assert rows[2]["option"] == "hardened_no_send_chat_metadata_capture"
    assert rows[2]["current_status"] == "READY_TO_RUN_NO_SEND_WITH_OWNER_LOGGED_IN_PROFILE"
    assert rows[2]["evidence_gate"] == "GREEN_LIVE_CHAT_API_BASE_CONFIRMED_NO_SEND"
    assert rows[3]["option"] == "direct_kaspi_chat_network_api"
    assert rows[3]["current_status"] == "LIVE_SURFACE_CONFIRMED_SEND_UNPROVEN"
    assert "do not replay" in rows[3]["next_step"]
    assert all(row["customer_send_allowed"] is False for row in rows)
    assert "938710785" not in markdown


def test_automation_options_matrix_switches_to_computer_use_after_chrome_retry_failure(
    tmp_path, capsys
):
    workflow_dir = tmp_path / "workflow"
    out_dir = tmp_path / "matrix"
    _write_json_fixture(
        workflow_dir / "manifest.json",
        {
            "gate": "YELLOW_CUSTOMER_SIZE_WORKFLOW_READY_WITH_RETAINED_BLOCKERS_NO_EXTERNAL_WRITE",
            "ledger_summary": {"ledger_rows": 18},
        },
    )
    _write_json_fixture(
        workflow_dir / "workflow_stages.json",
        [
            {
                "stage": "live_ui_no_send_proof",
                "gate": "YELLOW_LIVE_UI_RESULT_INCOMPLETE",
            },
            {
                "stage": "chrome_or_computer_use_access",
                "gate": "YELLOW_CHROME_EXTENSION_CHANNEL_UNAVAILABLE_AFTER_APPROVED_RETRY",
            },
        ],
    )

    rc = automation_options_matrix_main(
        [
            "--workflow-dir",
            str(workflow_dir),
            "--synthesis-closeout",
            str(tmp_path / "missing_synthesis.md"),
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    rows = json.loads((out_dir / "automation_options_matrix.json").read_text(encoding="utf-8"))
    markdown = (out_dir / "automation_options_matrix.md").read_text(encoding="utf-8")
    chrome_row = next(row for row in rows if row["option"] == "chrome_profile_session_reuse")

    assert rc == 0
    assert (
        manifest["recommended_immediate_path"]
        == "computer_use_helper_visual_no_send_proof_then_send_canary"
    )
    assert chrome_row["current_status"] == "EXTENSION_CHANNEL_UNAVAILABLE_AFTER_APPROVED_RETRY"
    assert "Computer Use/helper visual proof" in markdown
    assert all(row["customer_send_allowed"] is False for row in rows)


def test_chrome_reconnect_packet_emits_exact_approval_when_preconditions_hold(
    tmp_path, capsys
):
    _, out_dir = _prepare_resolved_canary_packet(tmp_path, capsys)
    diagnostics_path = tmp_path / "chrome_diagnostics.json"
    reconnect_dir = tmp_path / "reconnect"
    _write_chrome_diagnostics_fixture(diagnostics_path, extension_enabled=True)

    rc = chrome_reconnect_packet_main(
        [
            "--packet-dir",
            str(out_dir),
            "--diagnostics-json",
            str(diagnostics_path),
            "--output-dir",
            str(reconnect_dir),
        ]
    )
    manifest = json.loads(
        (reconnect_dir / "chrome_reconnect_preflight_manifest.json").read_text(encoding="utf-8")
    )
    phrase = (reconnect_dir / "REQUIRED_EXACT_CHROME_RECONNECT_APPROVAL_PHRASE.txt").read_text(
        encoding="utf-8"
    )

    assert rc == 0
    assert manifest["gate"] == "YELLOW_CHROME_RECONNECT_APPROVAL_REQUIRED_NO_UI_ACTION"
    assert manifest["chrome_window_opened"] is False
    assert manifest["customer_send_allowed"] is False
    assert manifest["diagnostic_summary"]["selected_profile_directory"] == "Profile 4"
    assert "--profile-directory=Profile 4" in manifest["diagnostic_summary"]["dry_run_command"]
    assert "No customer message typing/sending" in phrase
    assert "938710785" not in phrase


def test_chrome_reconnect_packet_blocks_when_extension_not_enabled(tmp_path, capsys):
    _, out_dir = _prepare_resolved_canary_packet(tmp_path, capsys)
    diagnostics_path = tmp_path / "chrome_diagnostics.json"
    reconnect_dir = tmp_path / "reconnect"
    _write_chrome_diagnostics_fixture(diagnostics_path, extension_enabled=False)

    rc = chrome_reconnect_packet_main(
        [
            "--packet-dir",
            str(out_dir),
            "--diagnostics-json",
            str(diagnostics_path),
            "--output-dir",
            str(reconnect_dir),
        ]
    )
    manifest = json.loads(
        (reconnect_dir / "chrome_reconnect_preflight_manifest.json").read_text(encoding="utf-8")
    )

    assert rc == 1
    assert manifest["gate"] == "YELLOW_CHROME_RECONNECT_PREFLIGHT_NOT_READY_NO_UI_ACTION"
    assert "extension_enabled_in_selected_profile_not_true" in manifest["blockers"]
    assert not (reconnect_dir / "REQUIRED_EXACT_CHROME_RECONNECT_APPROVAL_PHRASE.txt").exists()


def test_live_canary_result_validator_accepts_green_redacted_no_send_result(tmp_path, capsys):
    _, out_dir = _prepare_resolved_canary_packet(tmp_path, capsys)
    result_path = out_dir / "live_ui_probe_result_redacted.json"
    closeout_path = out_dir / "live_ui_no_send_probe_closeout.md"
    validation_path = out_dir / "live_ui_canary_result_validation.json"
    result_path.write_text(
        json.dumps(
            {
                "gate": "GREEN_LIVE_ORDER_CHAT_BUTTON_PROVEN_NO_SEND",
                "merchant_account_match_proven": True,
                "order_search_performed": True,
                "order_detail_or_result_reached": True,
                "chat_button_present": True,
                "chat_opened": False,
                "message_text_typed": False,
                "message_sent": False,
                "raw_order_id_exported": False,
                "raw_customer_text_exported": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    closeout_path.write_text(
        "# Live UI No-Send Canary Closeout\n\n"
        "Gate: GREEN_LIVE_ORDER_CHAT_BUTTON_PROVEN_NO_SEND\n\n"
        "- Raw order ID exported: false\n"
        "- Message sent: false\n",
        encoding="utf-8",
    )

    rc = validate_canary_result_main(
        [
            "--packet-dir",
            str(out_dir),
            "--output-json",
            str(validation_path),
            "--require-green",
        ]
    )
    validation = json.loads(validation_path.read_text(encoding="utf-8"))

    assert rc == 0
    assert validation["gate"] == "GREEN_LIVE_UI_NO_SEND_CANARY_RESULT_ACCEPTED"
    assert validation["accepted"] is True
    assert validation["blockers"] == []
    assert "938710785" not in validation_path.read_text(encoding="utf-8")


def test_no_send_green_followup_blocks_when_live_ui_validation_not_green(tmp_path, capsys):
    db_path, out_dir = _prepare_resolved_canary_packet(tmp_path, capsys)
    ledger_path = tmp_path / "ledger.sqlite"
    output_root = tmp_path / "followup"
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    upsert_request_ledger_plan(
        ledger_path,
        build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE),
    )

    rc = no_send_green_followup_main(
        [
            "--packet-dir",
            str(out_dir),
            "--db",
            str(db_path),
            "--ledger-db",
            str(ledger_path),
            "--output-root",
            str(output_root),
        ]
    )
    manifest = json.loads((output_root / "manifest.json").read_text(encoding="utf-8"))

    assert rc == 1
    assert manifest["gate"] == "YELLOW_NO_SEND_GREEN_FOLLOWUP_BLOCKED_VALIDATION_NOT_GREEN"
    assert manifest["approval_packet_generated"] is False
    assert not (output_root / "live_send_approval").exists()


def test_live_send_execution_handoff_blocks_without_green_approval_packet(tmp_path, capsys):
    approval_dir = tmp_path / "approval"
    output_dir = tmp_path / "handoff"
    _write_json_fixture(
        approval_dir / "manifest.json",
        {
            "gate": "YELLOW_LIVE_SEND_CANARY_APPROVAL_PACKET_BLOCKED_NO_SEND",
            "approval_phrase_generated": False,
        },
    )

    rc = live_send_execution_handoff_main(
        [
            "--approval-dir",
            str(approval_dir),
            "--output-dir",
            str(output_dir),
        ]
    )
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

    assert rc == 1
    assert manifest["gate"] == "YELLOW_LIVE_SEND_EXECUTION_HANDOFF_BLOCKED_APPROVAL_NOT_GREEN"
    assert "approval_packet_not_green" in manifest["blockers"]
    assert "approval_phrase_missing" in manifest["blockers"]
    assert not (
        output_dir / "KASPI_CUSTOMER_SIZE_LIVE_SEND_CANARY_EXECUTION_HANDOFF.md"
    ).exists()


def test_no_send_green_followup_generates_owner_approval_after_manual_green_proof(
    tmp_path, capsys
):
    db_path, out_dir = _prepare_resolved_canary_packet(tmp_path, capsys)
    ledger_path = tmp_path / "ledger.sqlite"
    output_root = tmp_path / "followup"
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    upsert_request_ledger_plan(
        ledger_path,
        build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE),
    )
    assert (
        record_manual_no_send_proof_main(
            [
                "--packet-dir",
                str(out_dir),
                "--proof-source",
                "computer_use_visual",
                "--owner-confirmed-no-send",
                "--merchant-account-match-proven",
                "--order-search-performed",
                "--order-detail-or-result-reached",
                "--chat-button-present",
                "--require-green",
            ]
        )
        == 0
    )

    rc = no_send_green_followup_main(
        [
            "--packet-dir",
            str(out_dir),
            "--db",
            str(db_path),
            "--ledger-db",
            str(ledger_path),
            "--output-root",
            str(output_root),
        ]
    )
    manifest = json.loads((output_root / "manifest.json").read_text(encoding="utf-8"))
    approval_manifest = json.loads(
        (output_root / "live_send_approval" / "manifest.json").read_text(encoding="utf-8")
    )
    execution_manifest = json.loads(
        (output_root / "live_send_execution_handoff" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    execution_handoff = (
        output_root
        / "live_send_execution_handoff"
        / "KASPI_CUSTOMER_SIZE_LIVE_SEND_CANARY_EXECUTION_HANDOFF.md"
    ).read_text(encoding="utf-8")
    dashboard_text = (
        output_root / "workflow_readiness" / "owner_dashboard" / "owner_dashboard.md"
    ).read_text(encoding="utf-8")

    assert rc == 0
    assert manifest["gate"] == "GREEN_NO_SEND_GREEN_FOLLOWUP_READY_FOR_OWNER_LIVE_SEND_APPROVAL"
    assert manifest["approval_phrase_generated"] is True
    assert manifest["customer_send_allowed_now"] is False
    assert approval_manifest["gate"] == "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND"
    assert (
        execution_manifest["gate"]
        == "GREEN_LIVE_SEND_EXECUTION_HANDOFF_READY_NO_SEND_PERFORMED"
    )
    assert execution_manifest["customer_send_allowed_now"] is False
    assert "Do not send anything until this exact approval phrase is present" in execution_handoff
    assert "GREEN_LIVE_SIZE_REQUEST_TEMPLATE_SENT_ONE_ORDER" in execution_handoff
    assert "Expected Kaspi merchant account ID: `30137883`" in execution_handoff
    assert "ID - 30137883" in execution_handoff
    assert "UNIVERSAL -> ID - 30000001" in execution_handoff
    assert "STOREB -> ID - 30000002" in execution_handoff
    assert "MELVIS -> ID - 30362323" in execution_handoff
    assert "11KZ -> ID - 30290083" in execution_handoff
    assert "Do not close Chrome" in execution_handoff
    assert "do not force a fresh login/SMS cycle" in execution_handoff
    assert "I approve KASPI_CUSTOMER_SIZE_REQUEST_LIVE_SEND_CANARY_ONE_ORDER_20260616" in dashboard_text
    assert "938710785" not in execution_handoff
    assert "938710785" not in dashboard_text


def test_live_canary_result_validator_fails_red_when_raw_order_leaks(tmp_path, capsys):
    _, out_dir = _prepare_resolved_canary_packet(tmp_path, capsys)
    result_path = out_dir / "live_ui_probe_result_redacted.json"
    validation_path = out_dir / "live_ui_canary_result_validation.json"
    result_path.write_text(
        json.dumps(
            {
                "gate": "GREEN_LIVE_ORDER_CHAT_BUTTON_PROVEN_NO_SEND",
                "merchant_account_match_proven": True,
                "order_search_performed": True,
                "order_detail_or_result_reached": True,
                "chat_button_present": True,
                "message_text_typed": False,
                "message_sent": False,
                "raw_order_id_exported": False,
                "raw_customer_text_exported": False,
                "bad_note": "938710785",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rc = validate_canary_result_main(
        [
            "--packet-dir",
            str(out_dir),
            "--output-json",
            str(validation_path),
        ]
    )
    validation = json.loads(validation_path.read_text(encoding="utf-8"))

    assert rc == 2
    assert validation["gate"] == "RED_LIVE_UI_CANARY_REDACTION_SCAN_FAILED"
    assert validation["violations"][0]["violation"] == "raw_order_id"
    assert "938710785" not in validation_path.read_text(encoding="utf-8")


def test_manual_no_send_proof_recorder_creates_green_validator_artifacts(tmp_path, capsys):
    _, out_dir = _prepare_resolved_canary_packet(tmp_path, capsys)
    validation_path = out_dir / "live_ui_canary_result_validation.json"

    rc = record_manual_no_send_proof_main(
        [
            "--packet-dir",
            str(out_dir),
            "--proof-source",
            "computer_use_visual",
            "--owner-confirmed-no-send",
            "--merchant-account-match-proven",
            "--order-search-performed",
            "--order-detail-or-result-reached",
            "--chat-button-present",
            "--validation-json",
            str(validation_path),
            "--require-green",
        ]
    )
    captured = capsys.readouterr()
    result_text = (out_dir / "live_ui_probe_result_redacted.json").read_text(encoding="utf-8")
    closeout_text = (out_dir / "live_ui_no_send_probe_closeout.md").read_text(encoding="utf-8")
    validation = json.loads(validation_path.read_text(encoding="utf-8"))

    assert rc == 0
    assert validation["gate"] == "GREEN_LIVE_UI_NO_SEND_CANARY_RESULT_ACCEPTED"
    assert validation["accepted"] is True
    assert "Gate: GREEN_LIVE_ORDER_CHAT_BUTTON_PROVEN_NO_SEND" in closeout_text
    assert "938710785" not in captured.out
    assert "938710785" not in result_text
    assert "938710785" not in closeout_text


def test_manual_no_send_proof_recorder_stays_yellow_without_owner_no_send_confirmation(
    tmp_path, capsys
):
    _, out_dir = _prepare_resolved_canary_packet(tmp_path, capsys)
    validation_path = out_dir / "live_ui_canary_result_validation.json"

    rc = record_manual_no_send_proof_main(
        [
            "--packet-dir",
            str(out_dir),
            "--merchant-account-match-proven",
            "--order-search-performed",
            "--order-detail-or-result-reached",
            "--chat-button-present",
            "--validation-json",
            str(validation_path),
            "--require-green",
        ]
    )
    validation = json.loads(validation_path.read_text(encoding="utf-8"))

    assert rc == 1
    assert validation["gate"] == "YELLOW_LIVE_UI_RESULT_NOT_GREEN"
    assert "live_ui_result_not_green" in validation["blockers"]
    assert "938710785" not in validation_path.read_text(encoding="utf-8")


def test_manual_no_send_proof_recorder_fails_red_if_send_is_recorded(tmp_path, capsys):
    _, out_dir = _prepare_resolved_canary_packet(tmp_path, capsys)
    validation_path = out_dir / "live_ui_canary_result_validation.json"

    rc = record_manual_no_send_proof_main(
        [
            "--packet-dir",
            str(out_dir),
            "--owner-confirmed-no-send",
            "--merchant-account-match-proven",
            "--order-search-performed",
            "--order-detail-or-result-reached",
            "--chat-button-present",
            "--message-sent",
            "--validation-json",
            str(validation_path),
        ]
    )
    validation = json.loads(validation_path.read_text(encoding="utf-8"))

    assert rc == 2
    assert validation["gate"] == "RED_LIVE_UI_RESULT_UNSAFE"
    assert "live_ui_unsafe_flags" in validation["blockers"]
    assert "938710785" not in validation_path.read_text(encoding="utf-8")


def test_google_board_patch_packet_builds_salesraw_my_size_patch_from_classification(
    tmp_path, capsys
):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    out_dir = tmp_path / "patch"
    replies_csv = tmp_path / "synthetic_replies.csv"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    request_plan = build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE)
    upsert_request_ledger_plan(ledger_path, request_plan)
    replies_csv.write_text(
        "order_ref,reply_text,product_type\n"
        f"{request_plan[0]['order_ref']},рост 175 вес 75,CL\n",
        encoding="utf-8",
    )
    assert (
        control_plane_main(
            [
                "--db",
                str(db_path),
                "--ledger-db",
                str(ledger_path),
                "--target-date",
                "2026-06-15",
                "--lookback-days",
                "2",
                "--store",
                "ACMEWEAR",
                "--synthetic-replies-csv",
                str(replies_csv),
                "--output-dir",
                str(tmp_path / "control"),
            ]
        )
        == 0
    )
    capsys.readouterr()

    rc = google_board_patch_packet_main(
        [
            "--db",
            str(db_path),
            "--ledger-db",
            str(ledger_path),
            "--target-date",
            "2026-06-15",
            "--lookback-days",
            "2",
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    patch_rows = json.loads(
        (out_dir / "google_board_my_size_patch_rows_no_write.json").read_text(encoding="utf-8")
    )
    patch_text = (out_dir / "google_board_my_size_patch_rows_no_write.json").read_text(
        encoding="utf-8"
    )

    assert rc == 0
    assert manifest["gate"] == "GREEN_GOOGLE_BOARD_SIZE_PATCH_PACKET_READY_NO_WRITE"
    assert manifest["patch_rows_count"] == 1
    assert manifest["google_board_write_allowed"] is False
    assert patch_rows[0]["target_tab"] == "SalesRaw_Today"
    assert patch_rows[0]["key_column"] == "_db_row_id"
    assert patch_rows[0]["source_column"] == "MY_SIZE"
    assert patch_rows[0]["planned_cell_value"] == "L"
    assert patch_rows[0]["db_target_column"] == "assigned_size"
    assert patch_rows[0]["raw_order_id_exported"] is False
    assert "938710785" not in patch_text


def test_google_board_apply_handoff_generates_exact_approval_from_green_patch_packet(
    tmp_path, capsys
):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    patch_dir = tmp_path / "patch"
    out_dir = tmp_path / "apply_handoff"
    replies_csv = tmp_path / "synthetic_replies.csv"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    request_plan = build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE)
    upsert_request_ledger_plan(ledger_path, request_plan)
    replies_csv.write_text(
        "order_ref,reply_text,product_type\n"
        f"{request_plan[0]['order_ref']},рост 175 вес 75,CL\n",
        encoding="utf-8",
    )
    assert (
        control_plane_main(
            [
                "--db",
                str(db_path),
                "--ledger-db",
                str(ledger_path),
                "--target-date",
                "2026-06-15",
                "--lookback-days",
                "2",
                "--store",
                "ACMEWEAR",
                "--synthetic-replies-csv",
                str(replies_csv),
                "--output-dir",
                str(tmp_path / "control"),
            ]
        )
        == 0
    )
    assert (
        google_board_patch_packet_main(
            [
                "--db",
                str(db_path),
                "--ledger-db",
                str(ledger_path),
                "--target-date",
                "2026-06-15",
                "--lookback-days",
                "2",
                "--output-dir",
                str(patch_dir),
            ]
        )
        == 0
    )
    capsys.readouterr()

    rc = google_board_apply_handoff_main(
        [
            "--patch-manifest",
            str(patch_dir / "manifest.json"),
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    phrase = (
        out_dir / "REQUIRED_EXACT_GOOGLE_BOARD_MY_SIZE_APPLY_APPROVAL_PHRASE.txt"
    ).read_text(encoding="utf-8")
    handoff = (out_dir / "KASPI_CUSTOMER_SIZE_GOOGLE_BOARD_MY_SIZE_APPLY_HANDOFF.md").read_text(
        encoding="utf-8"
    )
    rows = json.loads((out_dir / "google_board_my_size_apply_rows_redacted.json").read_text(encoding="utf-8"))
    output_text = "\n".join(path.read_text(encoding="utf-8") for path in out_dir.glob("*"))

    assert rc == 0
    assert manifest["gate"] == "GREEN_GOOGLE_BOARD_MY_SIZE_APPLY_HANDOFF_READY_NO_WRITE"
    assert manifest["patch_rows_count"] == 1
    assert manifest["approval_phrase_generated"] is True
    assert manifest["google_board_write_allowed_now"] is False
    assert rows[0]["planned_cell_value"] == "L"
    assert "KASPI_CUSTOMER_SIZE_GOOGLE_BOARD_MY_SIZE_PATCH_APPLY" in phrase
    assert "sync_google_ops_board_sizes_to_db.py" in handoff
    assert "938710785" not in output_text
    assert "рост 175 вес 75" not in output_text


def test_google_board_apply_handoff_blocks_when_patch_packet_not_green(tmp_path, capsys):
    patch_dir = tmp_path / "patch"
    out_dir = tmp_path / "apply_handoff"
    _write_json_fixture(
        patch_dir / "manifest.json",
        {
            "gate": "YELLOW_GOOGLE_BOARD_SIZE_PATCH_PACKET_NO_READY_ROWS_NO_WRITE",
            "patch_rows_count": 0,
        },
    )
    _write_json_fixture(patch_dir / "google_board_my_size_patch_rows_no_write.json", [])

    rc = google_board_apply_handoff_main(
        [
            "--patch-manifest",
            str(patch_dir / "manifest.json"),
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

    assert rc == 0
    assert manifest["gate"] == "YELLOW_GOOGLE_BOARD_MY_SIZE_APPLY_HANDOFF_BLOCKED_PATCH_NOT_READY"
    assert manifest["approval_phrase_generated"] is False
    assert "patch_manifest_not_green" in manifest["blockers"]
    assert not (
        out_dir / "REQUIRED_EXACT_GOOGLE_BOARD_MY_SIZE_APPLY_APPROVAL_PHRASE.txt"
    ).exists()


def test_next_action_report_keeps_ui_proof_as_critical_path_when_not_green(tmp_path, capsys):
    live_ui_path = tmp_path / "live_ui" / "live_ui_canary_result_validation.json"
    chrome_path = tmp_path / "chrome" / "chrome_reconnect_preflight_manifest.json"
    board_path = tmp_path / "board" / "manifest.json"
    out_dir = tmp_path / "next_action"
    _write_json_fixture(live_ui_path, {"gate": "YELLOW_LIVE_UI_RESULT_INCOMPLETE"})
    _write_json_fixture(
        chrome_path,
        {"gate": "YELLOW_CHROME_EXTENSION_CHANNEL_UNAVAILABLE_AFTER_APPROVED_RETRY"},
    )
    _write_json_fixture(
        board_path,
        {
            "gate": "GREEN_GOOGLE_BOARD_MY_SIZE_APPLY_HANDOFF_READY_NO_WRITE",
            "patch_rows_count": 1,
            "approval_phrase_path": "/tmp/approval.txt",
        },
    )

    rc = next_action_report_main(
        [
            "--live-ui-validation-json",
            str(live_ui_path),
            "--chrome-reconnect-manifest",
            str(chrome_path),
            "--google-board-apply-manifest",
            str(board_path),
            *_missing_open_chat_args(tmp_path),
            "--resident-resume-manifest",
            str(tmp_path / "missing_resident_resume.json"),
            "--resident-priority-enqueue-readiness-manifest",
            str(tmp_path / "missing_priority_enqueue.json"),
            "--resident-proof-followup-manifest",
            str(tmp_path / "missing_proof_followup.json"),
            "--runtime-control-probe",
            "mcp_chrome_devtools_transport_closed",
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    closeout = (out_dir / "closeout.md").read_text(encoding="utf-8")

    assert rc == 0
    assert manifest["gate"] == "YELLOW_CUSTOMER_SIZE_NEXT_ACTION_UI_PROOF_REQUIRED_NO_EXTERNAL_WRITE"
    assert manifest["critical_stage"] == "live_ui_no_send_proof"
    assert manifest["exact_next_action"].startswith("Use a helper runtime")
    assert manifest["customer_send_allowed"] is False
    assert manifest["google_board_write_allowed"] is False
    assert manifest["google_board_apply_ready_no_write"] is True
    assert "runtime_control_probe=mcp_chrome_devtools_transport_closed" in manifest["blockers"]
    assert manifest["helper_prompt_path"].endswith(
        "AGENT_1_LIVE_UI_NO_SEND_CANARY_CURRENT_REFRESH_20260616.md"
    )
    assert "Gate: YELLOW_CUSTOMER_SIZE_NEXT_ACTION_UI_PROOF_REQUIRED_NO_EXTERNAL_WRITE" in closeout


def test_next_action_report_prefers_session_refresh_handoff_for_login_blocker(tmp_path, capsys):
    live_ui_path = tmp_path / "live_ui" / "live_ui_canary_result_validation.json"
    chrome_path = tmp_path / "chrome" / "chrome_reconnect_preflight_manifest.json"
    out_dir = tmp_path / "next_action"
    _write_json_fixture(live_ui_path, {"gate": "YELLOW_LIVE_UI_RESULT_INCOMPLETE"})
    _write_json_fixture(
        chrome_path,
        {"gate": "YELLOW_CHROME_EXTENSION_CHANNEL_UNAVAILABLE_AFTER_APPROVED_RETRY"},
    )

    rc = next_action_report_main(
        [
            "--live-ui-validation-json",
            str(live_ui_path),
            "--chrome-reconnect-manifest",
            str(chrome_path),
            *_missing_open_chat_args(tmp_path),
            "--resident-resume-manifest",
            str(tmp_path / "missing_resident_resume.json"),
            "--resident-priority-enqueue-readiness-manifest",
            str(tmp_path / "missing_priority_enqueue.json"),
            "--resident-proof-followup-manifest",
            str(tmp_path / "missing_proof_followup.json"),
            "--runtime-control-probe",
            "playwright_headed_login_timeout_at_kaspi_login",
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

    assert rc == 0
    assert manifest["gate"] == "YELLOW_CUSTOMER_SIZE_NEXT_ACTION_UI_PROOF_REQUIRED_NO_EXTERNAL_WRITE"
    assert manifest["exact_next_action"].startswith(
        "Run the Agent 0 headed persistent-profile Kaspi session refresh"
    )
    assert manifest["helper_prompt_path"].endswith(
        "AGENT_0_SESSION_REFRESH_THEN_NO_SEND_PROOF_20260616.md"
    )


def test_next_action_report_moves_to_send_approval_after_no_send_green(tmp_path, capsys):
    live_ui_path = tmp_path / "live_ui" / "live_ui_canary_result_validation.json"
    send_path = tmp_path / "send" / "manifest.json"
    out_dir = tmp_path / "next_action"
    _write_json_fixture(live_ui_path, {"gate": "GREEN_LIVE_UI_NO_SEND_CANARY_RESULT_ACCEPTED"})
    _write_json_fixture(send_path, {"gate": "YELLOW_LIVE_SEND_CANARY_APPROVAL_PACKET_BLOCKED_NO_SEND"})

    rc = next_action_report_main(
        [
            "--live-ui-validation-json",
            str(live_ui_path),
            "--live-send-approval-manifest",
            str(send_path),
            *_missing_open_chat_args(tmp_path),
            "--resident-resume-manifest",
            str(tmp_path / "missing_resident_resume.json"),
            "--resident-priority-enqueue-readiness-manifest",
            str(tmp_path / "missing_priority_enqueue.json"),
            "--resident-proof-followup-manifest",
            str(tmp_path / "missing_proof_followup.json"),
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

    assert rc == 0
    assert manifest["gate"] == "YELLOW_CUSTOMER_SIZE_NEXT_ACTION_BUILD_SEND_APPROVAL_NO_EXTERNAL_WRITE"
    assert manifest["critical_stage"] == "single_order_live_send_canary_approval_packet"
    assert "run_kaspi_customer_size_no_send_green_followup.py" in manifest["after_green_followup_command"]
    assert manifest["customer_send_allowed"] is False
    assert manifest["kaspi_chat_write_allowed"] is False


def test_next_action_report_uses_resident_button_green_as_no_send_proof(tmp_path, capsys):
    resident_path = tmp_path / "resident" / "manifest.json"
    send_path = tmp_path / "send" / "manifest.json"
    out_dir = tmp_path / "next_action"
    _write_json_fixture(
        resident_path,
        {"gate": "GREEN_KASPI_CUSTOMER_CHAT_MESSAGE_BUTTON_PROVEN_NO_SEND"},
    )
    _write_json_fixture(send_path, {"gate": "YELLOW_LIVE_SEND_CANARY_APPROVAL_PACKET_BLOCKED_NO_SEND"})

    rc = next_action_report_main(
        [
            "--resident-button-manifest",
            str(resident_path),
            "--live-send-approval-manifest",
            str(send_path),
            *_missing_open_chat_args(tmp_path),
            "--resident-resume-manifest",
            str(tmp_path / "missing_resident_resume.json"),
            "--resident-priority-enqueue-readiness-manifest",
            str(tmp_path / "missing_priority_enqueue.json"),
            "--resident-proof-followup-manifest",
            str(tmp_path / "missing_proof_followup.json"),
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

    assert rc == 0
    assert manifest["gate"] == "YELLOW_CUSTOMER_SIZE_NEXT_ACTION_BUILD_SEND_APPROVAL_NO_EXTERNAL_WRITE"
    assert manifest["source_gates"]["resident_button"] == (
        "GREEN_KASPI_CUSTOMER_CHAT_MESSAGE_BUTTON_PROVEN_NO_SEND"
    )
    assert "--resident-button-manifest" in manifest["after_green_followup_command"]
    assert str(resident_path) in manifest["after_green_followup_command"]
    assert manifest["customer_send_allowed"] is False
    assert manifest["kaspi_chat_write_allowed"] is False


def test_next_action_report_points_to_current_green_live_send_approval_packet(tmp_path, capsys):
    resident_path = tmp_path / "resident" / "manifest.json"
    approval_dir = tmp_path / "selector_exact_approval"
    send_path = approval_dir / "manifest.json"
    phrase_path = approval_dir / "REQUIRED_EXACT_LIVE_SEND_CANARY_APPROVAL_PHRASE.txt"
    handoff_path = (
        approval_dir
        / "live_send_execution_handoff"
        / "KASPI_CUSTOMER_SIZE_LIVE_SEND_CANARY_EXECUTION_HANDOFF.md"
    )
    starter_path = approval_dir / "live_send_execution_handoff" / "ONE_SENTENCE_STARTER_PROMPT.txt"
    out_dir = tmp_path / "next_action"
    _write_json_fixture(
        resident_path,
        {"gate": "GREEN_KASPI_CUSTOMER_CHAT_MESSAGE_BUTTON_PROVEN_NO_SEND"},
    )
    _write_json_fixture(send_path, {"gate": "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND"})
    phrase_path.write_text("I approve selector-exact one-order canary\n", encoding="utf-8")
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    handoff_path.write_text("handoff\n", encoding="utf-8")
    starter_path.write_text("starter\n", encoding="utf-8")

    rc = next_action_report_main(
        [
            "--resident-button-manifest",
            str(resident_path),
            "--live-send-approval-manifest",
            str(send_path),
            *_missing_open_chat_args(tmp_path),
            "--resident-resume-manifest",
            str(tmp_path / "missing_resident_resume.json"),
            "--resident-priority-enqueue-readiness-manifest",
            str(tmp_path / "missing_priority_enqueue.json"),
            "--resident-proof-followup-manifest",
            str(tmp_path / "missing_proof_followup.json"),
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

    assert rc == 0
    assert manifest["gate"] == "GREEN_CUSTOMER_SIZE_NEXT_ACTION_READY_FOR_OWNER_SEND_APPROVAL_NO_WRITE"
    assert manifest["after_green_followup_command"] == f"cat {phrase_path.resolve()}"
    assert manifest["live_send_approval_phrase_path"] == str(phrase_path.resolve())
    assert manifest["live_send_execution_handoff_path"] == str(handoff_path.resolve())
    assert manifest["live_send_execution_starter_prompt_path"] == str(starter_path.resolve())
    assert "kaspi_customer_chat_live_send_canary_approval_AFTER_RESIDENT_GREEN_NO_SEND" not in json.dumps(
        manifest,
        ensure_ascii=False,
    )


def test_next_action_report_requires_open_chat_no_type_before_live_send_when_packet_exists(
    tmp_path, capsys
):
    resident_path = tmp_path / "resident" / "manifest.json"
    send_path = tmp_path / "send" / "manifest.json"
    open_chat_dir = tmp_path / "open_chat"
    open_chat_packet_path = open_chat_dir / "manifest.json"
    open_chat_result_path = tmp_path / "open_chat_result" / "open_chat_no_type_result_validation.json"
    approval_phrase_path = open_chat_dir / "REQUIRED_EXACT_OPEN_CHAT_NO_TYPE_APPROVAL_PHRASE.txt"
    out_dir = tmp_path / "next_action"
    _write_json_fixture(
        resident_path,
        {"gate": "GREEN_KASPI_CUSTOMER_CHAT_MESSAGE_BUTTON_PROVEN_NO_SEND"},
    )
    _write_json_fixture(send_path, {"gate": "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND"})
    _write_json_fixture(
        open_chat_packet_path,
        {"gate": "GREEN_OPEN_CHAT_NO_TYPE_CANARY_PACKET_READY_NO_SEND"},
    )
    _write_json_fixture(
        open_chat_result_path,
        {
            "gate": "YELLOW_OPEN_CHAT_NO_TYPE_CANARY_RESULT_MISSING",
            "blockers": ["open_chat_no_type_result_missing"],
        },
    )
    approval_phrase_path.write_text("I approve open chat no type\n", encoding="utf-8")

    rc = next_action_report_main(
        [
            "--resident-button-manifest",
            str(resident_path),
            "--live-send-approval-manifest",
            str(send_path),
            "--open-chat-no-type-packet-manifest",
            str(open_chat_packet_path),
            "--open-chat-no-type-result-validation-json",
            str(open_chat_result_path),
            "--resident-resume-manifest",
            str(tmp_path / "missing_resident_resume.json"),
            "--resident-priority-enqueue-readiness-manifest",
            str(tmp_path / "missing_priority_enqueue.json"),
            "--resident-proof-followup-manifest",
            str(tmp_path / "missing_proof_followup.json"),
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

    assert rc == 0
    assert manifest["gate"] == "YELLOW_CUSTOMER_SIZE_NEXT_ACTION_OPEN_CHAT_NO_TYPE_REQUIRED_NO_EXTERNAL_WRITE"
    assert manifest["critical_stage"] == "open_chat_no_type_side_effect_canary"
    assert manifest["after_green_followup_command"] == f"cat {approval_phrase_path.resolve()}"
    assert manifest["open_chat_no_type_approval_phrase_path"] == str(approval_phrase_path.resolve())
    assert "open_chat_no_type_result_blocker=open_chat_no_type_result_missing" in manifest["blockers"]
    assert manifest["customer_send_allowed"] is False
    assert manifest["kaspi_chat_write_allowed"] is False


def test_next_action_report_prioritizes_yellow_resident_heartbeat_before_open_chat(
    tmp_path, capsys
):
    resident_button_path = tmp_path / "resident_button" / "manifest.json"
    send_path = tmp_path / "send" / "manifest.json"
    heartbeat_path = tmp_path / "resident_heartbeat.json"
    resume_path = tmp_path / "resume" / "manifest.json"
    open_chat_dir = tmp_path / "open_chat"
    open_chat_packet_path = open_chat_dir / "manifest.json"
    open_chat_result_path = tmp_path / "open_chat_result" / "open_chat_no_type_result_validation.json"
    enqueue_script = tmp_path / "resume" / "02_guarded_enqueue_priority_no_send.sh"
    out_dir = tmp_path / "next_action"
    _write_json_fixture(
        resident_button_path,
        {"gate": "GREEN_KASPI_CUSTOMER_CHAT_MESSAGE_BUTTON_PROVEN_NO_SEND"},
    )
    _write_json_fixture(send_path, {"gate": "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND"})
    _write_json_fixture(
        heartbeat_path,
        {
            "gate": "YELLOW_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_WAITING_FOR_LOGIN",
            "orders_search_input_visible": False,
            "safe_current_url": "https://idmc.shop.kaspi.kz/login",
            "browser_should_remain_open": True,
        },
    )
    _write_json_fixture(
        resume_path,
        {
            "gate": "GREEN_KASPI_CUSTOMER_SIZE_RESIDENT_RESUME_PACKET_READY_NO_BROWSER_TOUCH",
            "enqueue_script_path": str(enqueue_script),
            "priority_command": {"profile_store_code": "ACMEWEAR"},
        },
    )
    _write_json_fixture(
        open_chat_packet_path,
        {"gate": "GREEN_OPEN_CHAT_NO_TYPE_CANARY_PACKET_READY_NO_SEND"},
    )
    _write_json_fixture(
        open_chat_result_path,
        {
            "gate": "YELLOW_OPEN_CHAT_NO_TYPE_CANARY_RESULT_MISSING",
            "blockers": ["open_chat_no_type_result_missing"],
        },
    )

    rc = next_action_report_main(
        [
            "--resident-heartbeat-manifest",
            str(heartbeat_path),
            "--resident-button-manifest",
            str(resident_button_path),
            "--live-send-approval-manifest",
            str(send_path),
            "--resident-resume-manifest",
            str(resume_path),
            "--open-chat-no-type-packet-manifest",
            str(open_chat_packet_path),
            "--open-chat-no-type-result-validation-json",
            str(open_chat_result_path),
            "--resident-priority-enqueue-readiness-manifest",
            str(tmp_path / "missing_priority_enqueue.json"),
            "--resident-proof-followup-manifest",
            str(tmp_path / "missing_proof_followup.json"),
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

    assert rc == 0
    assert manifest["gate"] == "YELLOW_CUSTOMER_SIZE_NEXT_ACTION_RESIDENT_SESSION_REQUIRED_NO_EXTERNAL_WRITE"
    assert manifest["critical_stage"] == "resident_session_heartbeat"
    assert manifest["source_gates"]["resident_heartbeat"] == (
        "YELLOW_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_WAITING_FOR_LOGIN"
    )
    assert "resident_heartbeat_gate=YELLOW_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_WAITING_FOR_LOGIN" in manifest["blockers"]
    assert "resident_orders_search_input_visible=False" in manifest["blockers"]
    assert manifest["after_green_followup_command"] == str(enqueue_script)
    assert "open-chat/no-type" not in manifest["exact_next_action"].lower()
    assert "do not start a second browser" in manifest["exact_next_action"].lower()


def test_next_action_report_allows_open_chat_gate_after_order_detail_button_green(
    tmp_path, capsys
):
    resident_button_path = tmp_path / "resident_button" / "manifest.json"
    send_path = tmp_path / "send" / "manifest.json"
    heartbeat_path = tmp_path / "resident_heartbeat.json"
    resume_path = tmp_path / "resume" / "manifest.json"
    open_chat_dir = tmp_path / "open_chat"
    open_chat_packet_path = open_chat_dir / "manifest.json"
    open_chat_result_path = tmp_path / "open_chat_result" / "open_chat_no_type_result_validation.json"
    approval_phrase_path = open_chat_dir / "REQUIRED_EXACT_OPEN_CHAT_NO_TYPE_APPROVAL_PHRASE.txt"
    out_dir = tmp_path / "next_action"
    _write_json_fixture(
        resident_button_path,
        {"gate": "GREEN_KASPI_CUSTOMER_CHAT_MESSAGE_BUTTON_PROVEN_NO_SEND"},
    )
    _write_json_fixture(send_path, {"gate": "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND"})
    _write_json_fixture(
        heartbeat_path,
        {
            "gate": "YELLOW_KASPI_CUSTOMER_CHAT_RESIDENT_NO_SEND_CONTROLLER_WAITING_FOR_LOGIN",
            "orders_search_input_visible": False,
            "safe_current_url": "https://kaspi.kz/mc/#/orders/[redacted]?[redacted]",
            "browser_should_remain_open": True,
            "last_command": {
                "gate": "GREEN_KASPI_CUSTOMER_CHAT_MESSAGE_BUTTON_PROVEN_NO_SEND",
            },
        },
    )
    _write_json_fixture(
        resume_path,
        {
            "gate": "GREEN_KASPI_CUSTOMER_SIZE_RESIDENT_RESUME_PACKET_READY_NO_BROWSER_TOUCH",
            "priority_command": {"profile_store_code": "ACMEWEAR"},
        },
    )
    _write_json_fixture(
        open_chat_packet_path,
        {"gate": "GREEN_OPEN_CHAT_NO_TYPE_CANARY_PACKET_READY_NO_SEND"},
    )
    _write_json_fixture(
        open_chat_result_path,
        {
            "gate": "YELLOW_OPEN_CHAT_NO_TYPE_CANARY_RESULT_MISSING",
            "blockers": ["open_chat_no_type_result_missing"],
        },
    )
    approval_phrase_path.write_text("approve open chat no type\n", encoding="utf-8")

    rc = next_action_report_main(
        [
            "--resident-heartbeat-manifest",
            str(heartbeat_path),
            "--resident-button-manifest",
            str(resident_button_path),
            "--live-send-approval-manifest",
            str(send_path),
            "--resident-resume-manifest",
            str(resume_path),
            "--open-chat-no-type-packet-manifest",
            str(open_chat_packet_path),
            "--open-chat-no-type-result-validation-json",
            str(open_chat_result_path),
            "--resident-priority-enqueue-readiness-manifest",
            str(tmp_path / "missing_priority_enqueue.json"),
            "--resident-proof-followup-manifest",
            str(tmp_path / "missing_proof_followup.json"),
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

    assert rc == 0
    assert manifest["gate"] == "YELLOW_CUSTOMER_SIZE_NEXT_ACTION_OPEN_CHAT_NO_TYPE_REQUIRED_NO_EXTERNAL_WRITE"
    assert manifest["critical_stage"] == "open_chat_no_type_side_effect_canary"
    assert manifest["after_green_followup_command"] == f"cat {approval_phrase_path.resolve()}"
    assert "resident_heartbeat_gate=" not in " ".join(manifest["blockers"])


def test_next_action_report_prefers_current_priority_resident_proof_over_stale_green(tmp_path, capsys):
    resident_path = tmp_path / "resident" / "manifest.json"
    send_path = tmp_path / "send" / "manifest.json"
    resume_path = tmp_path / "resume" / "manifest.json"
    enqueue_path = tmp_path / "enqueue" / "manifest.json"
    followup_path = tmp_path / "followup" / "manifest.json"
    out_dir = tmp_path / "next_action"
    start_script = tmp_path / "resume" / "01_start_resident_controller_preserve_session.sh"
    enqueue_script = tmp_path / "resume" / "02_guarded_enqueue_priority_no_send.sh"
    followup_script = tmp_path / "resume" / "03_watch_resident_proof_and_build_approval.sh"
    _write_json_fixture(
        resident_path,
        {"gate": "GREEN_KASPI_CUSTOMER_CHAT_MESSAGE_BUTTON_PROVEN_NO_SEND"},
    )
    _write_json_fixture(send_path, {"gate": "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND"})
    _write_json_fixture(
        resume_path,
        {
            "gate": "GREEN_KASPI_CUSTOMER_SIZE_RESIDENT_RESUME_PACKET_READY_NO_BROWSER_TOUCH",
            "start_script_path": str(start_script),
            "enqueue_script_path": str(enqueue_script),
            "proof_followup_script_path": str(followup_script),
            "priority_command": {
                "profile_store_code": "ACMEWEAR",
                "target_db_row_ids": "36170",
                "target_order_refs": "sha256:3a507903190c4097e2d211ee",
            },
        },
    )
    _write_json_fixture(
        enqueue_path,
        {
            "gate": "YELLOW_PRIORITY_COMMAND_NOT_ENQUEUED_RESIDENT_NOT_READY",
            "blockers": ["resident_heartbeat_stale"],
            "command_profile_store_code": "ACMEWEAR",
        },
    )
    _write_json_fixture(
        followup_path,
        {"gate": "YELLOW_RESIDENT_PROOF_FOLLOWUP_WAITING_OR_BLOCKED_NO_SEND"},
    )

    rc = next_action_report_main(
        [
            "--resident-button-manifest",
            str(resident_path),
            "--live-send-approval-manifest",
            str(send_path),
            *_missing_open_chat_args(tmp_path),
            "--resident-resume-manifest",
            str(resume_path),
            "--resident-priority-enqueue-readiness-manifest",
            str(enqueue_path),
            "--resident-proof-followup-manifest",
            str(followup_path),
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    closeout = (out_dir / "closeout.md").read_text(encoding="utf-8")

    assert rc == 0
    assert manifest["gate"] == "GREEN_CUSTOMER_SIZE_NEXT_ACTION_READY_FOR_OWNER_SEND_APPROVAL_NO_WRITE"
    assert manifest["critical_stage"] == "owner_live_send_canary_approval"
    assert manifest["current_priority_store"] == "ACMEWEAR"
    assert manifest["current_priority_expected_merchant_account_id"] == "30137883"
    assert manifest["after_green_followup_command"] == ""
    assert str(start_script) not in manifest["exact_next_action"]
    assert "resident_heartbeat_stale" not in " ".join(manifest["blockers"])
    assert "Required visible merchant selector ID: `30137883`" in closeout


def test_next_action_report_login_gated_resident_does_not_recommend_second_browser(tmp_path, capsys):
    resume_path = tmp_path / "resume" / "manifest.json"
    enqueue_path = tmp_path / "enqueue" / "manifest.json"
    followup_path = tmp_path / "followup" / "manifest.json"
    out_dir = tmp_path / "next_action"
    enqueue_script = tmp_path / "resume" / "02_guarded_enqueue_priority_no_send.sh"
    _write_json_fixture(
        resume_path,
        {
            "gate": "GREEN_KASPI_CUSTOMER_SIZE_RESIDENT_RESUME_PACKET_READY_NO_BROWSER_TOUCH",
            "start_script_path": str(tmp_path / "resume" / "01_start_resident_controller_preserve_session.sh"),
            "enqueue_script_path": str(enqueue_script),
            "proof_followup_script_path": str(tmp_path / "resume" / "03_watch_resident_proof_and_build_approval.sh"),
            "priority_command": {
                "profile_store_code": "ACMEWEAR",
                "target_db_row_ids": "36170",
                "target_order_refs": "sha256:3a507903190c4097e2d211ee",
            },
        },
    )
    _write_json_fixture(
        enqueue_path,
        {
            "gate": "YELLOW_PRIORITY_COMMAND_NOT_ENQUEUED_RESIDENT_NOT_READY",
            "blockers": [
                "resident_heartbeat_gate_not_green",
                "resident_orders_search_input_not_visible",
            ],
            "command_profile_store_code": "ACMEWEAR",
            "resident_process_count": 1,
        },
    )
    _write_json_fixture(
        followup_path,
        {"gate": "YELLOW_RESIDENT_PROOF_FOLLOWUP_WAITING_OR_BLOCKED_NO_SEND"},
    )

    rc = next_action_report_main(
        [
            "--resident-resume-manifest",
            str(resume_path),
            "--resident-priority-enqueue-readiness-manifest",
            str(enqueue_path),
            *_missing_open_chat_args(tmp_path),
            "--resident-proof-followup-manifest",
            str(followup_path),
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

    assert rc == 0
    assert manifest["gate"] == "YELLOW_CUSTOMER_SIZE_NEXT_ACTION_RESIDENT_PRIORITY_PROOF_REQUIRED_NO_EXTERNAL_WRITE"
    assert manifest["exact_next_action"].startswith("Complete Kaspi login/SMS once in the already-open")
    assert "do not start a second browser" in manifest["exact_next_action"].lower()
    assert manifest["after_green_followup_command"] == str(enqueue_script)


def test_next_action_report_green_followup_moves_to_owner_approval(tmp_path, capsys):
    resume_path = tmp_path / "resume" / "manifest.json"
    enqueue_path = tmp_path / "enqueue" / "manifest.json"
    followup_path = tmp_path / "followup" / "manifest.json"
    approval_dir = tmp_path / "followup" / "live_send_approval"
    send_path = approval_dir / "manifest.json"
    phrase_path = approval_dir / "REQUIRED_EXACT_LIVE_SEND_CANARY_APPROVAL_PHRASE.txt"
    handoff_path = (
        approval_dir
        / "live_send_execution_handoff"
        / "KASPI_CUSTOMER_SIZE_LIVE_SEND_CANARY_EXECUTION_HANDOFF.md"
    )
    starter_path = approval_dir / "live_send_execution_handoff" / "ONE_SENTENCE_STARTER_PROMPT.txt"
    out_dir = tmp_path / "next_action"
    _write_json_fixture(
        resume_path,
        {
            "gate": "GREEN_KASPI_CUSTOMER_SIZE_RESIDENT_RESUME_PACKET_READY_NO_BROWSER_TOUCH",
            "priority_command": {
                "profile_store_code": "ACMEWEAR",
                "target_db_row_ids": "36170",
                "target_order_refs": "sha256:3a507903190c4097e2d211ee",
            },
        },
    )
    _write_json_fixture(
        enqueue_path,
        {"gate": "GREEN_PRIORITY_COMMAND_ENQUEUED_TO_RESIDENT_NO_SEND", "command_profile_store_code": "ACMEWEAR"},
    )
    _write_json_fixture(
        followup_path,
        {
            "gate": "GREEN_RESIDENT_PROOF_FOLLOWUP_APPROVAL_READY_NO_SEND",
            "approval_dir": str(approval_dir),
        },
    )
    _write_json_fixture(send_path, {"gate": "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND"})
    phrase_path.write_text("I approve selector exact current priority canary\n", encoding="utf-8")
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    handoff_path.write_text("handoff\n", encoding="utf-8")
    starter_path.write_text("starter\n", encoding="utf-8")

    rc = next_action_report_main(
        [
            "--resident-resume-manifest",
            str(resume_path),
            "--resident-priority-enqueue-readiness-manifest",
            str(enqueue_path),
            "--resident-proof-followup-manifest",
            str(followup_path),
            *_missing_open_chat_args(tmp_path),
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))

    assert rc == 0
    assert manifest["gate"] == "GREEN_CUSTOMER_SIZE_NEXT_ACTION_READY_FOR_OWNER_SEND_APPROVAL_NO_WRITE"
    assert manifest["critical_stage"] == "owner_live_send_canary_approval"
    assert manifest["after_green_followup_command"] == f"cat {phrase_path.resolve()}"
    assert manifest["live_send_execution_handoff_path"] == str(handoff_path.resolve())
    assert manifest["customer_send_allowed"] is False


def test_google_board_patch_packet_blocks_when_db_row_already_has_different_size(
    tmp_path, capsys
):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    out_dir = tmp_path / "patch"
    replies_csv = tmp_path / "synthetic_replies.csv"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    request_plan = build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE)
    upsert_request_ledger_plan(ledger_path, request_plan)
    replies_csv.write_text(
        "order_ref,reply_text,product_type\n"
        f"{request_plan[0]['order_ref']},рост 175 вес 75,CL\n",
        encoding="utf-8",
    )
    assert (
        control_plane_main(
            [
                "--db",
                str(db_path),
                "--ledger-db",
                str(ledger_path),
                "--target-date",
                "2026-06-15",
                "--lookback-days",
                "2",
                "--store",
                "ACMEWEAR",
                "--synthetic-replies-csv",
                str(replies_csv),
                "--output-dir",
                str(tmp_path / "control"),
            ]
        )
        == 0
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE fact_orders_kaspi SET assigned_size = 'XL' WHERE id = 1")
        conn.commit()
    capsys.readouterr()

    rc = google_board_patch_packet_main(
        [
            "--db",
            str(db_path),
            "--ledger-db",
            str(ledger_path),
            "--target-date",
            "2026-06-15",
            "--lookback-days",
            "2",
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    blockers = json.loads((out_dir / "blockers_redacted.json").read_text(encoding="utf-8"))
    blockers_text = (out_dir / "blockers_redacted.json").read_text(encoding="utf-8")

    assert rc == 0
    assert manifest["gate"] == "YELLOW_GOOGLE_BOARD_SIZE_PATCH_PACKET_HAS_BLOCKERS_NO_WRITE"
    assert manifest["patch_rows_count"] == 0
    assert blockers[0]["blocker"] == "db_row_already_has_different_size"
    assert blockers[0]["raw_order_id_exported"] is False
    assert "938710785" not in blockers_text


def test_cadence_readiness_packet_shows_live_ui_blocker_without_writes(tmp_path, capsys):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    scheduler_dir = tmp_path / "scheduler"
    patch_dir = tmp_path / "patch"
    out_dir = tmp_path / "cadence"
    _make_orders_db(db_path)
    assert (
        scheduler_preflight_main(
            [
                "--db",
                str(db_path),
                "--ledger-db",
                str(ledger_path),
                "--target-date",
                "2026-06-15",
                "--lookback-days",
                "2",
                "--output-dir",
                str(scheduler_dir),
            ]
        )
        == 0
    )
    assert (
        google_board_patch_packet_main(
            [
                "--db",
                str(db_path),
                "--ledger-db",
                str(ledger_path),
                "--target-date",
                "2026-06-15",
                "--lookback-days",
                "2",
                "--output-dir",
                str(patch_dir),
            ]
        )
        == 0
    )
    capsys.readouterr()

    rc = cadence_readiness_packet_main(
        [
            "--db",
            str(db_path),
            "--ledger-db",
            str(ledger_path),
            "--target-date",
            "2026-06-15",
            "--google-board-patch-manifest",
            str(patch_dir / "manifest.json"),
            "--live-ui-validation-json",
            str(tmp_path / "missing_live_ui_validation.json"),
            "--open-chat-no-type-packet-manifest",
            str(tmp_path / "missing_open_chat_packet_manifest.json"),
            "--open-chat-no-type-result-validation-json",
            str(tmp_path / "missing_open_chat_result_validation.json"),
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    blockers = json.loads((out_dir / "retained_blockers.json").read_text(encoding="utf-8"))
    slots = json.loads((out_dir / "cadence_slots_no_apply.json").read_text(encoding="utf-8"))
    output_text = (out_dir / "next_actions_redacted.json").read_text(encoding="utf-8")

    assert rc == 0
    assert manifest["gate"] == "YELLOW_CUSTOMER_SIZE_CADENCE_READY_WITH_RETAINED_BLOCKERS_NO_APPLY"
    assert manifest["db_unchanged"] is True
    assert manifest["customer_send_allowed"] is False
    assert manifest["google_board_write_allowed"] is False
    assert manifest["telegram_send_allowed"] is False
    assert blockers[0]["blocker"] == "live_ui_no_send_canary_validation_missing"
    assert {slot["stage"] for slot in slots} >= {
        "missing_size_detection_refresh",
        "open_chat_no_type_side_effect_canary",
        "reply_polling_windows",
        "google_board_my_size_patch_packet",
        "telegram_pdf_waybill_closeout",
    }
    open_chat_slot = next(
        slot for slot in slots if slot["stage"] == "open_chat_no_type_side_effect_canary"
    )
    send_slot = next(slot for slot in slots if slot["stage"] == "customer_size_request_send_lane")
    assert open_chat_slot["status"] == "PACKET_MISSING"
    assert send_slot["status"] == "BLOCKED_OPEN_CHAT_NO_TYPE_RESULT_NOT_ACCEPTED"
    assert "938710785" not in output_text


def test_cadence_readiness_packet_requires_open_chat_no_type_before_send_lane(
    tmp_path, capsys
):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    patch_dir = tmp_path / "patch"
    out_dir = tmp_path / "cadence"
    live_ui_validation = tmp_path / "live_ui_validation.json"
    open_chat_packet = tmp_path / "open_chat_packet" / "manifest.json"
    open_chat_result = tmp_path / "open_chat_result" / "open_chat_no_type_result_validation.json"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    request_plan = build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE)
    upsert_request_ledger_plan(ledger_path, request_plan)
    assert (
        google_board_patch_packet_main(
            [
                "--db",
                str(db_path),
                "--ledger-db",
                str(ledger_path),
                "--target-date",
                "2026-06-15",
                "--lookback-days",
                "2",
                "--output-dir",
                str(patch_dir),
            ]
        )
        == 0
    )
    live_ui_validation.write_text(
        json.dumps(
            {
                "gate": "GREEN_LIVE_UI_NO_SEND_CANARY_RESULT_ACCEPTED",
                "accepted": True,
                "raw_order_id_exported": False,
                "raw_customer_text_exported": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    open_chat_packet.parent.mkdir(parents=True, exist_ok=True)
    open_chat_packet.write_text(
        json.dumps(
            {
                "gate": "GREEN_OPEN_CHAT_NO_TYPE_CANARY_PACKET_READY_NO_SEND",
                "customer_send_allowed": False,
                "kaspi_chat_write_allowed": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    open_chat_result.parent.mkdir(parents=True, exist_ok=True)
    open_chat_result.write_text(
        json.dumps(
            {
                "gate": "YELLOW_OPEN_CHAT_NO_TYPE_CANARY_RESULT_MISSING",
                "blockers": ["open_chat_no_type_result_missing"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    capsys.readouterr()

    rc = cadence_readiness_packet_main(
        [
            "--db",
            str(db_path),
            "--ledger-db",
            str(ledger_path),
            "--target-date",
            "2026-06-15",
            "--live-ui-validation-json",
            str(live_ui_validation),
            "--open-chat-no-type-packet-manifest",
            str(open_chat_packet),
            "--open-chat-no-type-result-validation-json",
            str(open_chat_result),
            "--google-board-patch-manifest",
            str(patch_dir / "manifest.json"),
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    blockers = json.loads((out_dir / "retained_blockers.json").read_text(encoding="utf-8"))
    slots = json.loads((out_dir / "cadence_slots_no_apply.json").read_text(encoding="utf-8"))
    open_chat_slot = next(
        slot for slot in slots if slot["stage"] == "open_chat_no_type_side_effect_canary"
    )
    send_slot = next(slot for slot in slots if slot["stage"] == "customer_size_request_send_lane")

    assert rc == 0
    assert manifest["gate"] == "YELLOW_CUSTOMER_SIZE_CADENCE_READY_WITH_RETAINED_BLOCKERS_NO_APPLY"
    assert manifest["open_chat_no_type_packet_gate"] == "GREEN_OPEN_CHAT_NO_TYPE_CANARY_PACKET_READY_NO_SEND"
    assert manifest["open_chat_no_type_result_gate"] == "YELLOW_OPEN_CHAT_NO_TYPE_CANARY_RESULT_MISSING"
    assert {row["blocker"] for row in blockers} == {"open_chat_no_type_result_not_accepted"}
    assert open_chat_slot["status"] == "WAITING_ON_OPEN_CHAT_NO_TYPE_RESULT"
    assert open_chat_slot["allowed_now"] is False
    assert send_slot["status"] == "BLOCKED_OPEN_CHAT_NO_TYPE_RESULT_NOT_ACCEPTED"
    assert send_slot["allowed_now"] is False


def test_cadence_readiness_packet_goes_green_when_no_send_proof_and_patch_are_clean(
    tmp_path, capsys
):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    replies_csv = tmp_path / "synthetic_replies.csv"
    patch_dir = tmp_path / "patch"
    out_dir = tmp_path / "cadence"
    live_ui_validation = tmp_path / "live_ui_validation.json"
    open_chat_packet = tmp_path / "open_chat_packet" / "manifest.json"
    open_chat_result = tmp_path / "open_chat_result" / "open_chat_no_type_result_validation.json"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    request_plan = build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE)
    upsert_request_ledger_plan(ledger_path, request_plan)
    replies_csv.write_text(
        "order_ref,reply_text,product_type\n"
        f"{request_plan[0]['order_ref']},рост 175 вес 75,CL\n",
        encoding="utf-8",
    )
    assert (
        control_plane_main(
            [
                "--db",
                str(db_path),
                "--ledger-db",
                str(ledger_path),
                "--target-date",
                "2026-06-15",
                "--lookback-days",
                "2",
                "--store",
                "ACMEWEAR",
                "--synthetic-replies-csv",
                str(replies_csv),
                "--output-dir",
                str(tmp_path / "control"),
            ]
        )
        == 0
    )
    assert (
        google_board_patch_packet_main(
            [
                "--db",
                str(db_path),
                "--ledger-db",
                str(ledger_path),
                "--target-date",
                "2026-06-15",
                "--lookback-days",
                "2",
                "--output-dir",
                str(patch_dir),
            ]
        )
        == 0
    )
    live_ui_validation.write_text(
        json.dumps(
            {
                "gate": "GREEN_LIVE_UI_NO_SEND_CANARY_RESULT_ACCEPTED",
                "accepted": True,
                "raw_order_id_exported": False,
                "raw_customer_text_exported": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    open_chat_packet.parent.mkdir(parents=True, exist_ok=True)
    open_chat_packet.write_text(
        json.dumps(
            {
                "gate": "GREEN_OPEN_CHAT_NO_TYPE_CANARY_PACKET_READY_NO_SEND",
                "customer_send_allowed": False,
                "kaspi_chat_write_allowed": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    open_chat_result.parent.mkdir(parents=True, exist_ok=True)
    open_chat_result.write_text(
        json.dumps(
            {
                "gate": "GREEN_OPEN_CHAT_NO_TYPE_CANARY_RESULT_ACCEPTED_NO_SEND",
                "chat_opened": True,
                "message_text_typed": False,
                "message_sent": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    capsys.readouterr()

    rc = cadence_readiness_packet_main(
        [
            "--db",
            str(db_path),
            "--ledger-db",
            str(ledger_path),
            "--target-date",
            "2026-06-15",
            "--live-ui-validation-json",
            str(live_ui_validation),
            "--open-chat-no-type-packet-manifest",
            str(open_chat_packet),
            "--open-chat-no-type-result-validation-json",
            str(open_chat_result),
            "--google-board-patch-manifest",
            str(patch_dir / "manifest.json"),
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    slots = json.loads((out_dir / "cadence_slots_no_apply.json").read_text(encoding="utf-8"))
    board_slot = next(slot for slot in slots if slot["stage"] == "google_board_my_size_patch_packet")
    open_chat_slot = next(
        slot for slot in slots if slot["stage"] == "open_chat_no_type_side_effect_canary"
    )
    send_slot = next(slot for slot in slots if slot["stage"] == "customer_size_request_send_lane")

    assert rc == 0
    assert manifest["gate"] == "GREEN_CUSTOMER_SIZE_CADENCE_PACKET_READY_NO_APPLY"
    assert manifest["retained_blockers_count"] == 0
    assert manifest["open_chat_no_type_result_gate"] == "GREEN_OPEN_CHAT_NO_TYPE_CANARY_RESULT_ACCEPTED_NO_SEND"
    assert manifest["google_board_patch_rows_count"] == 1
    assert open_chat_slot["status"] == "ACCEPTED_NO_SEND"
    assert open_chat_slot["allowed_now"] is True
    assert board_slot["status"] == "READY_NO_WRITE_PATCH_ROWS"
    assert send_slot["status"] == "BLOCKED_NO_LIVE_SEND_APPROVAL"
    assert send_slot["allowed_now"] is False


def test_live_send_approval_packet_blocks_until_no_send_canary_is_green(tmp_path, capsys):
    db_path = tmp_path / "orders.db"
    packet_dir = tmp_path / "packet"
    approval_dir = tmp_path / "approval"
    _make_orders_db(db_path)
    assert (
        canary_packet_main(
            [
                "--db",
                str(db_path),
                "--target-date",
                "2026-06-15",
                "--lookback-days",
                "2",
                "--store-priority",
                "ACMEWEAR",
                "--output-dir",
                str(packet_dir),
            ]
        )
        == 0
    )
    yellow_validation = packet_dir / "live_ui_canary_result_validation_pending.json"
    yellow_validation.write_text(
        json.dumps(
            {
                "gate": "YELLOW_LIVE_UI_RESULT_MISSING",
                "selected_order_ref": "sha256:pending",
                "raw_order_id_exported": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    capsys.readouterr()

    rc = live_send_approval_packet_main(
        [
            "--packet-dir",
            str(packet_dir),
            "--live-ui-validation-json",
            str(yellow_validation),
            "--output-dir",
            str(approval_dir),
        ]
    )
    manifest = json.loads((approval_dir / "manifest.json").read_text(encoding="utf-8"))
    closeout_text = (approval_dir / "closeout.md").read_text(encoding="utf-8")

    assert rc == 0
    assert manifest["gate"] == "YELLOW_LIVE_SEND_CANARY_APPROVAL_PACKET_BLOCKED_NO_SEND"
    assert manifest["approval_phrase_generated"] is False
    assert manifest["customer_send_allowed_now"] is False
    assert manifest["kaspi_chat_write_performed"] is False
    assert "live_ui_no_send_validation_not_green" in manifest["blockers"]
    assert not (approval_dir / "REQUIRED_EXACT_LIVE_SEND_CANARY_APPROVAL_PHRASE.txt").exists()
    assert "938710785" not in closeout_text


def test_live_send_approval_packet_accepts_strict_resident_button_proof(tmp_path, capsys):
    approval_dir = tmp_path / "approval"
    resident_manifest = tmp_path / "resident" / "manifest.json"
    order_ref = private_hash("kaspi_order_id", "938710785")
    _write_json_fixture(
        resident_manifest,
        {
            "gate": "GREEN_KASPI_CUSTOMER_CHAT_MESSAGE_BUTTON_PROVEN_NO_SEND",
            "target_date": "2026-06-17",
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
                    "db_row_id": 1,
                    "order_ref": order_ref,
                    "store_code": "ACMEWEAR",
                    "status_filter": "KASPI_DELIVERY_CARGO_ASSEMBLY",
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
        },
    )

    rc = live_send_approval_packet_main(
        [
            "--resident-button-manifest",
            str(resident_manifest),
            "--output-dir",
            str(approval_dir),
        ]
    )
    manifest = json.loads((approval_dir / "manifest.json").read_text(encoding="utf-8"))
    derived_packet = json.loads(
        (approval_dir / "resident_selected_live_ui_canary_packet_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    phrase = (approval_dir / "REQUIRED_EXACT_LIVE_SEND_CANARY_APPROVAL_PHRASE.txt").read_text(
        encoding="utf-8"
    )

    assert rc == 0
    assert manifest["gate"] == "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND"
    assert manifest["source_mode"] == "resident_button_manifest"
    assert manifest["approval_phrase_generated"] is True
    assert manifest["selected_order_ref"] == order_ref
    assert manifest["selected_db_row_id"] == 1
    assert manifest["requires_matching_merchant_account"] is True
    assert manifest["expected_merchant_account_id"] == "30137883"
    assert manifest["merchant_account_match_proven"] is True
    assert derived_packet["selected_store_code"] == "ACMEWEAR"
    assert derived_packet["expected_merchant_account_id"] == "30137883"
    assert derived_packet["merchant_account_match_proven"] is True
    assert derived_packet["raw_order_id_exported"] is False
    assert "expected Kaspi merchant account ID: 30137883" in phrase
    assert "visible Kaspi store selector is on that exact merchant account ID before search" in phrase
    assert "938710785" not in phrase
    assert manifest["customer_send_allowed_now"] is False
    assert manifest["kaspi_chat_write_performed"] is False


def test_live_send_approval_packet_rejects_resident_button_without_store_match(
    tmp_path, capsys
):
    approval_dir = tmp_path / "approval"
    resident_manifest = tmp_path / "resident" / "manifest.json"
    _write_json_fixture(
        resident_manifest,
        {
            "gate": "GREEN_KASPI_CUSTOMER_CHAT_MESSAGE_BUTTON_PROVEN_NO_SEND",
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
                    "db_row_id": 1,
                    "order_ref": "sha256:order-ref",
                    "store_code": "ACMEWEAR",
                    "status_filter": "KASPI_DELIVERY_CARGO_ASSEMBLY",
                    "merchant_account_match_proven": False,
                    "result_or_detail_reached": True,
                    "chat_button_present": True,
                    "chat_opened": False,
                    "message_text_typed": False,
                    "message_sent": False,
                    "raw_order_id_exported": False,
                    "raw_customer_text_exported": False,
                }
            ],
        },
    )

    rc = live_send_approval_packet_main(
        [
            "--resident-button-manifest",
            str(resident_manifest),
            "--output-dir",
            str(approval_dir),
        ]
    )
    manifest = json.loads((approval_dir / "manifest.json").read_text(encoding="utf-8"))

    assert rc == 0
    assert manifest["gate"] == "YELLOW_LIVE_SEND_CANARY_APPROVAL_PACKET_BLOCKED_NO_SEND"
    assert manifest["approval_phrase_generated"] is False
    assert "resident_button_manifest_no_qualified_selected_result" in manifest["blockers"]
    assert not (approval_dir / "REQUIRED_EXACT_LIVE_SEND_CANARY_APPROVAL_PHRASE.txt").exists()


def test_live_send_approval_and_result_validator_accept_exact_one_send(tmp_path, capsys):
    db_path = tmp_path / "orders.db"
    packet_dir = tmp_path / "packet"
    approval_dir = tmp_path / "approval"
    validation_path = packet_dir / "live_ui_canary_result_validation.json"
    _make_orders_db(db_path)
    assert (
        canary_packet_main(
            [
                "--db",
                str(db_path),
                "--target-date",
                "2026-06-15",
                "--lookback-days",
                "2",
                "--store-priority",
                "ACMEWEAR",
                "--output-dir",
                str(packet_dir),
            ]
        )
        == 0
    )
    manifest = json.loads((packet_dir / "manifest.json").read_text(encoding="utf-8"))
    validation_path.write_text(
        json.dumps(
            {
                "gate": "GREEN_LIVE_UI_NO_SEND_CANARY_RESULT_ACCEPTED",
                "selected_order_ref": manifest["selected_order_ref"],
                "selected_db_row_id": manifest["selected_db_row_id"],
                "selected_store_code": manifest["selected_store_code"],
                "selected_status_filter": manifest["selected_status_filter"],
                "accepted": True,
                "raw_order_id_exported": False,
                "raw_customer_text_exported": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    assert (
        live_send_approval_packet_main(
            [
                "--packet-dir",
                str(packet_dir),
                "--live-ui-validation-json",
                str(validation_path),
                "--output-dir",
                str(approval_dir),
            ]
        )
        == 0
    )
    approval_manifest = json.loads((approval_dir / "manifest.json").read_text(encoding="utf-8"))
    result_path = approval_dir / "live_send_canary_result_redacted.json"
    closeout_path = approval_dir / "live_send_canary_closeout.md"
    result_path.write_text(
        json.dumps(
            {
                "gate": "GREEN_LIVE_SIZE_REQUEST_TEMPLATE_SENT_ONE_ORDER",
                "selected_order_ref": approval_manifest["selected_order_ref"],
                "template_hash": approval_manifest["template_hash"],
                "merchant_account_match_proven": True,
                "visible_merchant_selector_id": approval_manifest["expected_merchant_account_id"],
                "store_scoped_selector_map_applied": True,
                "browser_session_preserved": True,
                "order_search_performed": True,
                "chat_opened": True,
                "message_text_typed": True,
                "message_sent": True,
                "send_confirmation_observed": True,
                "sent_count": 1,
                "other_customer_messages_sent": False,
                "raw_order_id_exported": False,
                "raw_customer_text_exported": False,
                "raw_phone_exported": False,
                "cookie_token_session_exported": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    closeout_path.write_text(
        "# Live Send Canary Closeout\n\n"
        "Gate: GREEN_LIVE_SIZE_REQUEST_TEMPLATE_SENT_ONE_ORDER\n\n"
        "- Sent count: 1\n"
        "- Raw order ID exported: false\n",
        encoding="utf-8",
    )
    capsys.readouterr()

    rc = validate_live_send_canary_result_main(
        [
            "--approval-dir",
            str(approval_dir),
            "--output-json",
            str(approval_dir / "live_send_canary_result_validation.json"),
            "--require-green",
        ]
    )
    validation = json.loads(
        (approval_dir / "live_send_canary_result_validation.json").read_text(encoding="utf-8")
    )

    assert rc == 0
    assert approval_manifest["gate"] == "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND"
    assert approval_manifest["approval_phrase_generated"] is True
    assert approval_manifest["customer_send_allowed_now"] is False
    assert validation["gate"] == "GREEN_LIVE_SEND_CANARY_RESULT_ACCEPTED_ONE_ORDER"
    assert validation["accepted"] is True
    assert "938710785" not in (approval_dir / "live_send_canary_result_validation.json").read_text(
        encoding="utf-8"
    )


def test_live_send_validator_rejects_wrong_visible_merchant_selector(tmp_path, capsys):
    approval_dir = tmp_path / "approval"
    approval_dir.mkdir(parents=True, exist_ok=True)
    template_hash = request_template_hash(DEFAULT_REQUEST_TEMPLATE)
    _write_json_fixture(
        approval_dir / "manifest.json",
        {
            "gate": "GREEN_LIVE_SEND_CANARY_APPROVAL_PACKET_READY_NO_SEND",
            "approval_phrase_generated": True,
            "selected_order_ref": "sha256:order1",
            "selected_db_row_id": 36170,
            "selected_store_code": "ACMEWEAR",
            "expected_merchant_account_id": "30137883",
            "template_hash": template_hash,
        },
    )
    _write_json_fixture(
        approval_dir / "live_send_canary_result_redacted.json",
        {
            "gate": "GREEN_LIVE_SIZE_REQUEST_TEMPLATE_SENT_ONE_ORDER",
            "selected_order_ref": "sha256:order1",
            "template_hash": template_hash,
            "merchant_account_match_proven": True,
            "visible_merchant_selector_id": "30000001",
            "store_scoped_selector_map_applied": True,
            "browser_session_preserved": True,
            "order_search_performed": True,
            "chat_opened": True,
            "message_text_typed": True,
            "message_sent": True,
            "send_confirmation_observed": True,
            "sent_count": 1,
            "other_customer_messages_sent": False,
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
            "raw_phone_exported": False,
            "cookie_token_session_exported": False,
        },
    )
    (approval_dir / "live_send_canary_closeout.md").write_text(
        "# Live Send Canary Closeout\n\nGate: GREEN_LIVE_SIZE_REQUEST_TEMPLATE_SENT_ONE_ORDER\n",
        encoding="utf-8",
    )
    capsys.readouterr()

    rc = validate_live_send_canary_result_main(
        [
            "--approval-dir",
            str(approval_dir),
            "--output-json",
            str(approval_dir / "live_send_canary_result_validation.json"),
            "--require-green",
        ]
    )
    validation = json.loads(
        (approval_dir / "live_send_canary_result_validation.json").read_text(encoding="utf-8")
    )

    assert rc == 1
    assert validation["gate"] == "RED_LIVE_SEND_CANARY_VISIBLE_MERCHANT_SELECTOR_MISMATCH"
    assert "visible_merchant_selector_id_mismatch" in validation["blockers"]


def test_live_send_validator_skips_raw_order_scan_when_resident_packet_has_no_db_path(tmp_path):
    packet_manifest = tmp_path / "approval" / "resident_selected_live_ui_canary_packet_manifest.json"
    _write_json_fixture(
        packet_manifest,
        {
            "gate": "GREEN_RESIDENT_BUTTON_PROOF_DERIVED_LIVE_UI_PACKET_READY_NO_SEND",
            "selected_db_row_id": 36189,
            "selected_order_ref": "sha256:order",
            "raw_order_id_exported": False,
        },
    )

    raw_order_id = _load_raw_order_id_for_scan({"packet_manifest_path": str(packet_manifest)})

    assert raw_order_id is None


def test_live_send_acceptance_recorder_marks_request_sent_and_schedules_reply_polling(
    tmp_path, capsys
):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    packet_dir = tmp_path / "packet"
    approval_dir = tmp_path / "approval"
    output_dir = tmp_path / "post_send"
    validation_path = packet_dir / "live_ui_canary_result_validation.json"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    upsert_request_ledger_plan(
        ledger_path,
        build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE),
    )
    assert (
        canary_packet_main(
            [
                "--db",
                str(db_path),
                "--target-date",
                "2026-06-15",
                "--lookback-days",
                "2",
                "--store-priority",
                "ACMEWEAR",
                "--output-dir",
                str(packet_dir),
            ]
        )
        == 0
    )
    packet_manifest = json.loads((packet_dir / "manifest.json").read_text(encoding="utf-8"))
    validation_path.write_text(
        json.dumps(
            {
                "gate": "GREEN_LIVE_UI_NO_SEND_CANARY_RESULT_ACCEPTED",
                "selected_order_ref": packet_manifest["selected_order_ref"],
                "selected_db_row_id": packet_manifest["selected_db_row_id"],
                "selected_store_code": packet_manifest["selected_store_code"],
                "selected_status_filter": packet_manifest["selected_status_filter"],
                "accepted": True,
                "raw_order_id_exported": False,
                "raw_customer_text_exported": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    assert (
        live_send_approval_packet_main(
            [
                "--packet-dir",
                str(packet_dir),
                "--live-ui-validation-json",
                str(validation_path),
                "--output-dir",
                str(approval_dir),
            ]
        )
        == 0
    )
    approval_manifest = json.loads((approval_dir / "manifest.json").read_text(encoding="utf-8"))
    (approval_dir / "live_send_canary_result_redacted.json").write_text(
        json.dumps(
            {
                "gate": "GREEN_LIVE_SIZE_REQUEST_TEMPLATE_SENT_ONE_ORDER",
                "selected_order_ref": approval_manifest["selected_order_ref"],
                "template_hash": approval_manifest["template_hash"],
                "merchant_account_match_proven": True,
                "visible_merchant_selector_id": approval_manifest["expected_merchant_account_id"],
                "store_scoped_selector_map_applied": True,
                "browser_session_preserved": True,
                "order_search_performed": True,
                "chat_opened": True,
                "message_text_typed": True,
                "message_sent": True,
                "send_confirmation_observed": True,
                "sent_count": 1,
                "other_customer_messages_sent": False,
                "raw_order_id_exported": False,
                "raw_customer_text_exported": False,
                "raw_phone_exported": False,
                "cookie_token_session_exported": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (approval_dir / "live_send_canary_closeout.md").write_text(
        "# Live Send Canary Closeout\n\nGate: GREEN_LIVE_SIZE_REQUEST_TEMPLATE_SENT_ONE_ORDER\n",
        encoding="utf-8",
    )
    capsys.readouterr()

    rc = record_live_send_canary_acceptance_main(
        [
            "--approval-dir",
            str(approval_dir),
            "--ledger-db",
            str(ledger_path),
            "--output-dir",
            str(output_dir),
            "--reply-poll-window-minutes",
            "10,30",
        ]
    )
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    schedule = json.loads((output_dir / "reply_poll_schedule_redacted.json").read_text(encoding="utf-8"))
    snapshot = export_customer_size_ledger_snapshot(ledger_path)
    summary = summarize_customer_size_ledger(snapshot)
    output_text = "\n".join(path.read_text(encoding="utf-8") for path in output_dir.glob("*"))

    assert rc == 0
    assert (
        manifest["gate"]
        == "GREEN_LIVE_SEND_CANARY_ACCEPTANCE_RECORDED_REPLY_POLL_READY_NO_EXTERNAL_WRITE"
    )
    assert manifest["record_stats"]["updated_to_request_sent"] == 1
    assert snapshot[0]["status"] == "REQUEST_SENT"
    assert snapshot[0]["request_sent_at"]
    assert summary["reply_poll_pending_count"] == 1
    assert [row["poll_after_minutes"] for row in schedule] == [10, 30]
    assert all(row["kaspi_chat_write_allowed"] is False for row in schedule)
    assert "938710785" not in output_text


def test_reply_polling_handoff_builds_redacted_targets_for_request_sent_rows(tmp_path, capsys):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    out_dir = tmp_path / "reply_poll"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    request_plan = build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE)
    upsert_request_ledger_plan(ledger_path, request_plan)
    record_live_send_canary_acceptance(
        ledger_path,
        {
            "gate": "GREEN_LIVE_SEND_CANARY_RESULT_ACCEPTED_ONE_ORDER",
            "selected_order_ref": request_plan[0]["order_ref"],
        },
        now=datetime(2026, 6, 16, 15, 0, 0),
    )

    rc = reply_polling_handoff_main(
        [
            "--db",
            str(db_path),
            "--ledger-db",
            str(ledger_path),
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    targets = json.loads((out_dir / "reply_poll_targets_redacted.json").read_text(encoding="utf-8"))
    handoff = (out_dir / "KASPI_CUSTOMER_SIZE_REPLY_POLLING_HANDOFF.md").read_text(
        encoding="utf-8"
    )
    template = (out_dir / "TRANSIENT_REPLY_CSV_TEMPLATE_NO_CUSTOMER_TEXT.csv").read_text(
        encoding="utf-8"
    )
    all_text = "\n".join(path.read_text(encoding="utf-8") for path in out_dir.glob("*"))

    assert rc == 0
    assert manifest["gate"] == "GREEN_REPLY_POLLING_HANDOFF_READY_NO_EXTERNAL_WRITE"
    assert manifest["poll_target_count"] == 1
    assert manifest["ledger_unchanged"] is True
    assert targets[0]["status"] == "REQUEST_SENT"
    assert targets[0]["requires_matching_merchant_account"] is True
    assert targets[0]["expected_merchant_account_id"] == "30137883"
    assert targets[0]["raw_order_id_exported"] is False
    assert "expected_merchant_account_id" in handoff
    assert "resolve_kaspi_customer_size_order_runtime_secret.py" in handoff
    assert "record_kaspi_customer_size_reply_observations.py" in handoff
    assert "build_kaspi_customer_size_google_board_patch_packet.py" in handoff
    assert "reply_text" in template
    assert "938710785" not in all_text
    assert "рост 175 вес 75" not in all_text


def test_reply_polling_handoff_stays_yellow_without_request_sent_rows(tmp_path, capsys):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    out_dir = tmp_path / "reply_poll"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    upsert_request_ledger_plan(
        ledger_path,
        build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE),
    )

    rc = reply_polling_handoff_main(
        [
            "--db",
            str(db_path),
            "--ledger-db",
            str(ledger_path),
            "--output-dir",
            str(out_dir),
        ]
    )
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    targets = json.loads((out_dir / "reply_poll_targets_redacted.json").read_text(encoding="utf-8"))

    assert rc == 0
    assert manifest["gate"] == "YELLOW_REPLY_POLLING_HANDOFF_NO_POLLABLE_ROWS_NO_EXTERNAL_WRITE"
    assert manifest["poll_target_count"] == 0
    assert targets == []
    assert "938710785" not in (out_dir / "KASPI_CUSTOMER_SIZE_REPLY_POLLING_HANDOFF.md").read_text(
        encoding="utf-8"
    )


def test_live_send_acceptance_recorder_blocks_without_green_validation(tmp_path, capsys):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    approval_dir = tmp_path / "approval"
    output_dir = tmp_path / "post_send"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    upsert_request_ledger_plan(
        ledger_path,
        build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE),
    )
    _write_json_fixture(
        approval_dir / "manifest.json",
        {
            "gate": "YELLOW_LIVE_SEND_CANARY_APPROVAL_PACKET_BLOCKED_NO_SEND",
            "approval_phrase_generated": False,
        },
    )

    rc = record_live_send_canary_acceptance_main(
        [
            "--approval-dir",
            str(approval_dir),
            "--ledger-db",
            str(ledger_path),
            "--output-dir",
            str(output_dir),
        ]
    )
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    snapshot = export_customer_size_ledger_snapshot(ledger_path)

    assert rc == 1
    assert manifest["gate"] == "YELLOW_LIVE_SEND_CANARY_ACCEPTANCE_BLOCKED_RESULT_NOT_GREEN"
    assert manifest["ledger_updated"] is False
    assert not (output_dir / "reply_poll_schedule_redacted.json").exists()
    assert snapshot[0]["status"] == "SEND_PLANNED_NO_SEND"


def test_post_canary_sequence_blocks_until_live_send_result_is_green(tmp_path, capsys):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    packet_dir = tmp_path / "packet"
    approval_dir = tmp_path / "approval"
    output_dir = tmp_path / "post_canary_sequence"
    validation_path = packet_dir / "live_ui_canary_result_validation.json"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    upsert_request_ledger_plan(
        ledger_path,
        build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE),
    )
    assert (
        canary_packet_main(
            [
                "--db",
                str(db_path),
                "--target-date",
                "2026-06-15",
                "--lookback-days",
                "2",
                "--store-priority",
                "ACMEWEAR",
                "--output-dir",
                str(packet_dir),
            ]
        )
        == 0
    )
    packet_manifest = json.loads((packet_dir / "manifest.json").read_text(encoding="utf-8"))
    validation_path.write_text(
        json.dumps(
            {
                "gate": "GREEN_LIVE_UI_NO_SEND_CANARY_RESULT_ACCEPTED",
                "selected_order_ref": packet_manifest["selected_order_ref"],
                "selected_db_row_id": packet_manifest["selected_db_row_id"],
                "selected_store_code": packet_manifest["selected_store_code"],
                "selected_status_filter": packet_manifest["selected_status_filter"],
                "accepted": True,
                "raw_order_id_exported": False,
                "raw_customer_text_exported": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    assert (
        live_send_approval_packet_main(
            [
                "--packet-dir",
                str(packet_dir),
                "--live-ui-validation-json",
                str(validation_path),
                "--output-dir",
                str(approval_dir),
            ]
        )
        == 0
    )
    capsys.readouterr()

    rc = post_canary_sequence_main(
        [
            "--approval-dir",
            str(approval_dir),
            "--db",
            str(db_path),
            "--ledger-db",
            str(ledger_path),
            "--output-dir",
            str(output_dir),
        ]
    )
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    snapshot = export_customer_size_ledger_snapshot(ledger_path)

    assert rc == 1
    assert manifest["gate"] == "YELLOW_POST_CANARY_SEQUENCE_BLOCKED_LIVE_SEND_RESULT_NOT_GREEN_NO_EXTERNAL_WRITE"
    assert manifest["ledger_updated"] is False
    assert "live_send_acceptance_gate=YELLOW_LIVE_SEND_CANARY_ACCEPTANCE_BLOCKED_RESULT_NOT_GREEN" in manifest["blockers"]
    assert snapshot[0]["status"] == "SEND_PLANNED_NO_SEND"
    assert not (output_dir / "02_reply_polling_handoff").exists()


def test_post_canary_sequence_blocks_on_live_send_preflight_target_mismatch(tmp_path, capsys):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    packet_dir = tmp_path / "packet"
    approval_dir = tmp_path / "approval"
    output_dir = tmp_path / "post_canary_sequence"
    preflight_manifest_path = tmp_path / "preflight" / "manifest.json"
    validation_path = packet_dir / "live_ui_canary_result_validation.json"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    upsert_request_ledger_plan(
        ledger_path,
        build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE),
    )
    assert (
        canary_packet_main(
            [
                "--db",
                str(db_path),
                "--target-date",
                "2026-06-15",
                "--lookback-days",
                "2",
                "--store-priority",
                "ACMEWEAR",
                "--output-dir",
                str(packet_dir),
            ]
        )
        == 0
    )
    packet_manifest = json.loads((packet_dir / "manifest.json").read_text(encoding="utf-8"))
    validation_path.write_text(
        json.dumps(
            {
                "gate": "GREEN_LIVE_UI_NO_SEND_CANARY_RESULT_ACCEPTED",
                "selected_order_ref": packet_manifest["selected_order_ref"],
                "selected_db_row_id": packet_manifest["selected_db_row_id"],
                "selected_store_code": packet_manifest["selected_store_code"],
                "selected_status_filter": packet_manifest["selected_status_filter"],
                "accepted": True,
                "raw_order_id_exported": False,
                "raw_customer_text_exported": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    assert (
        live_send_approval_packet_main(
            [
                "--packet-dir",
                str(packet_dir),
                "--live-ui-validation-json",
                str(validation_path),
                "--output-dir",
                str(approval_dir),
            ]
        )
        == 0
    )
    approval_manifest = json.loads((approval_dir / "manifest.json").read_text(encoding="utf-8"))
    _write_json_fixture(
        preflight_manifest_path,
        {
            "gate": "GREEN_LIVE_SEND_CANARY_EXECUTION_PREFLIGHT_READY_NO_SEND",
            "selected_order_ref": "sha256:different-target",
            "selected_db_row_id": approval_manifest["selected_db_row_id"],
            "selected_store_code": approval_manifest["selected_store_code"],
            "template_hash": approval_manifest["template_hash"],
            "expected_merchant_account_id": approval_manifest["expected_merchant_account_id"],
        },
    )
    capsys.readouterr()

    rc = post_canary_sequence_main(
        [
            "--approval-dir",
            str(approval_dir),
            "--db",
            str(db_path),
            "--ledger-db",
            str(ledger_path),
            "--live-send-execution-preflight-manifest",
            str(preflight_manifest_path),
            "--output-dir",
            str(output_dir),
        ]
    )
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    snapshot = export_customer_size_ledger_snapshot(ledger_path)

    assert rc == 1
    assert manifest["gate"] == "YELLOW_POST_CANARY_SEQUENCE_BLOCKED_LIVE_SEND_PREFLIGHT_ALIGNMENT_NO_EXTERNAL_WRITE"
    assert "approval_preflight_target_mismatch:selected_order_ref" in manifest["blockers"]
    assert manifest["ledger_updated"] is False
    assert snapshot[0]["status"] == "SEND_PLANNED_NO_SEND"
    assert not (output_dir / "01_live_send_acceptance").exists()


def test_post_canary_sequence_builds_reply_polling_and_board_packets_after_green_send(
    tmp_path, capsys
):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    packet_dir = tmp_path / "packet"
    approval_dir = tmp_path / "approval"
    output_dir = tmp_path / "post_canary_sequence"
    reuse_manifest = tmp_path / "resident_reuse" / "manifest.json"
    validation_path = packet_dir / "live_ui_canary_result_validation.json"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    upsert_request_ledger_plan(
        ledger_path,
        build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE),
    )
    _write_json_fixture(
        reuse_manifest,
        {
            "gate": "GREEN_KASPI_CUSTOMER_CHAT_RESIDENT_SESSION_REUSE_READY_NO_SEND",
            "no_send_invariants": {
                "customer_send_allowed": False,
                "kaspi_chat_write_allowed": False,
                "chat_open_allowed": False,
                "message_text_typed": False,
                "message_sent": False,
                "raw_order_id_exported": False,
                "raw_customer_text_exported": False,
                "raw_phone_exported": False,
                "raw_session_material_exported": False,
            },
        },
    )
    assert (
        canary_packet_main(
            [
                "--db",
                str(db_path),
                "--target-date",
                "2026-06-15",
                "--lookback-days",
                "2",
                "--store-priority",
                "ACMEWEAR",
                "--output-dir",
                str(packet_dir),
            ]
        )
        == 0
    )
    packet_manifest = json.loads((packet_dir / "manifest.json").read_text(encoding="utf-8"))
    validation_path.write_text(
        json.dumps(
            {
                "gate": "GREEN_LIVE_UI_NO_SEND_CANARY_RESULT_ACCEPTED",
                "selected_order_ref": packet_manifest["selected_order_ref"],
                "selected_db_row_id": packet_manifest["selected_db_row_id"],
                "selected_store_code": packet_manifest["selected_store_code"],
                "selected_status_filter": packet_manifest["selected_status_filter"],
                "accepted": True,
                "raw_order_id_exported": False,
                "raw_customer_text_exported": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    assert (
        live_send_approval_packet_main(
            [
                "--packet-dir",
                str(packet_dir),
                "--live-ui-validation-json",
                str(validation_path),
                "--output-dir",
                str(approval_dir),
            ]
        )
        == 0
    )
    approval_manifest = json.loads((approval_dir / "manifest.json").read_text(encoding="utf-8"))
    _write_json_fixture(
        approval_dir / "live_send_canary_result_redacted.json",
        {
            "gate": "GREEN_LIVE_SIZE_REQUEST_TEMPLATE_SENT_ONE_ORDER",
            "selected_order_ref": approval_manifest["selected_order_ref"],
            "template_hash": approval_manifest["template_hash"],
            "merchant_account_match_proven": True,
            "visible_merchant_selector_id": approval_manifest["expected_merchant_account_id"],
            "store_scoped_selector_map_applied": True,
            "browser_session_preserved": True,
            "order_search_performed": True,
            "chat_opened": True,
            "message_text_typed": True,
            "message_sent": True,
            "send_confirmation_observed": True,
            "sent_count": 1,
            "other_customer_messages_sent": False,
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
            "raw_phone_exported": False,
            "cookie_token_session_exported": False,
        },
    )
    (approval_dir / "live_send_canary_closeout.md").write_text(
        "# Live Send Canary Closeout\n\nGate: GREEN_LIVE_SIZE_REQUEST_TEMPLATE_SENT_ONE_ORDER\n",
        encoding="utf-8",
    )
    capsys.readouterr()

    rc = post_canary_sequence_main(
        [
            "--approval-dir",
            str(approval_dir),
            "--db",
            str(db_path),
            "--ledger-db",
            str(ledger_path),
            "--resident-session-reuse-manifest",
            str(reuse_manifest),
            "--target-date",
            "2026-06-15",
            "--lookback-days",
            "2",
            "--reply-poll-window-minutes",
            "10,30",
            "--output-dir",
            str(output_dir),
        ]
    )
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    reply_preflight = json.loads(
        (output_dir / "03_reply_polling_preflight" / "manifest.json").read_text(encoding="utf-8")
    )
    reply_targets = json.loads(
        (output_dir / "03_reply_polling_preflight" / "reply_poll_targets_redacted.json").read_text(
            encoding="utf-8"
        )
    )
    patch_manifest = json.loads(
        (output_dir / "04_google_board_patch_packet" / "manifest.json").read_text(encoding="utf-8")
    )
    snapshot = export_customer_size_ledger_snapshot(ledger_path)
    text_artifacts = "\n".join(
        path.read_text(encoding="utf-8")
        for path in output_dir.rglob("*")
        if path.is_file() and path.suffix in {".json", ".md", ".txt", ".csv"}
    )

    assert rc == 0
    assert manifest["gate"] == "GREEN_POST_CANARY_SEQUENCE_LOCAL_REPLY_POLLING_READY_NO_EXTERNAL_WRITE"
    assert snapshot[0]["status"] == "REQUEST_SENT"
    assert reply_preflight["gate"] == "YELLOW_REPLY_POLLING_EXECUTION_PREFLIGHT_AWAITING_OWNER_APPROVAL_NO_SEND"
    assert reply_preflight["approval_phrase_generated"] is True
    assert reply_targets[0]["requires_matching_merchant_account"] is True
    assert reply_targets[0]["expected_merchant_account_id"] == "30137883"
    assert patch_manifest["gate"] == "YELLOW_GOOGLE_BOARD_SIZE_PATCH_PACKET_NO_READY_ROWS_NO_WRITE"
    assert (output_dir / "02_reply_polling_handoff" / "KASPI_CUSTOMER_SIZE_REPLY_POLLING_HANDOFF.md").exists()
    assert (output_dir / "03_reply_polling_preflight" / "REQUIRED_EXACT_REPLY_POLLING_APPROVAL_PHRASE.txt").exists()
    assert manifest["customer_send_allowed"] is False
    assert manifest["google_board_write_allowed"] is False
    assert "938710785" not in text_artifacts


def test_after_live_send_watch_blocks_until_ui_helper_result_exists(tmp_path, capsys):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    packet_dir = tmp_path / "packet"
    approval_dir = tmp_path / "approval"
    preflight_path = tmp_path / "preflight" / "manifest.json"
    output_dir = tmp_path / "after_live_send_watch"
    validation_path = packet_dir / "live_ui_canary_result_validation.json"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    upsert_request_ledger_plan(
        ledger_path,
        build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE),
    )
    assert (
        canary_packet_main(
            [
                "--db",
                str(db_path),
                "--target-date",
                "2026-06-15",
                "--lookback-days",
                "2",
                "--store-priority",
                "ACMEWEAR",
                "--output-dir",
                str(packet_dir),
            ]
        )
        == 0
    )
    packet_manifest = json.loads((packet_dir / "manifest.json").read_text(encoding="utf-8"))
    validation_path.write_text(
        json.dumps(
            {
                "gate": "GREEN_LIVE_UI_NO_SEND_CANARY_RESULT_ACCEPTED",
                "selected_order_ref": packet_manifest["selected_order_ref"],
                "selected_db_row_id": packet_manifest["selected_db_row_id"],
                "selected_store_code": packet_manifest["selected_store_code"],
                "selected_status_filter": packet_manifest["selected_status_filter"],
                "accepted": True,
                "raw_order_id_exported": False,
                "raw_customer_text_exported": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    assert (
        live_send_approval_packet_main(
            [
                "--packet-dir",
                str(packet_dir),
                "--live-ui-validation-json",
                str(validation_path),
                "--output-dir",
                str(approval_dir),
            ]
        )
        == 0
    )
    approval_manifest = json.loads((approval_dir / "manifest.json").read_text(encoding="utf-8"))
    _write_json_fixture(
        preflight_path,
        {
            "gate": "GREEN_LIVE_SEND_CANARY_EXECUTION_PREFLIGHT_READY_NO_SEND",
            "selected_order_ref": approval_manifest["selected_order_ref"],
            "selected_db_row_id": approval_manifest["selected_db_row_id"],
            "selected_store_code": approval_manifest["selected_store_code"],
            "template_hash": approval_manifest["template_hash"],
            "expected_merchant_account_id": approval_manifest["expected_merchant_account_id"],
        },
    )
    capsys.readouterr()

    rc = after_live_send_watch_main(
        [
            "--approval-dir",
            str(approval_dir),
            "--live-send-execution-preflight-manifest",
            str(preflight_path),
            "--db",
            str(db_path),
            "--ledger-db",
            str(ledger_path),
            "--wait-seconds",
            "0",
            "--output-dir",
            str(output_dir),
        ]
    )
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    snapshot = export_customer_size_ledger_snapshot(ledger_path)

    assert rc == 1
    assert manifest["gate"] == "YELLOW_AFTER_LIVE_SEND_RESULT_NOT_READY_NO_EXTERNAL_WRITE"
    assert manifest["live_send_validation_gate"] == "YELLOW_LIVE_SEND_CANARY_RESULT_MISSING"
    assert manifest["customer_send_performed_by_this_helper"] is False
    assert snapshot[0]["status"] == "SEND_PLANNED_NO_SEND"
    assert not (output_dir / "post_canary_sequence").exists()


def test_after_live_send_watch_runs_post_canary_after_valid_ui_helper_result(tmp_path, capsys):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    packet_dir = tmp_path / "packet"
    approval_dir = tmp_path / "approval"
    preflight_path = tmp_path / "preflight" / "manifest.json"
    output_dir = tmp_path / "after_live_send_watch"
    validation_path = packet_dir / "live_ui_canary_result_validation.json"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    upsert_request_ledger_plan(
        ledger_path,
        build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE),
    )
    assert (
        canary_packet_main(
            [
                "--db",
                str(db_path),
                "--target-date",
                "2026-06-15",
                "--lookback-days",
                "2",
                "--store-priority",
                "ACMEWEAR",
                "--output-dir",
                str(packet_dir),
            ]
        )
        == 0
    )
    packet_manifest = json.loads((packet_dir / "manifest.json").read_text(encoding="utf-8"))
    validation_path.write_text(
        json.dumps(
            {
                "gate": "GREEN_LIVE_UI_NO_SEND_CANARY_RESULT_ACCEPTED",
                "selected_order_ref": packet_manifest["selected_order_ref"],
                "selected_db_row_id": packet_manifest["selected_db_row_id"],
                "selected_store_code": packet_manifest["selected_store_code"],
                "selected_status_filter": packet_manifest["selected_status_filter"],
                "accepted": True,
                "raw_order_id_exported": False,
                "raw_customer_text_exported": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    assert (
        live_send_approval_packet_main(
            [
                "--packet-dir",
                str(packet_dir),
                "--live-ui-validation-json",
                str(validation_path),
                "--output-dir",
                str(approval_dir),
            ]
        )
        == 0
    )
    approval_manifest = json.loads((approval_dir / "manifest.json").read_text(encoding="utf-8"))
    _write_json_fixture(
        preflight_path,
        {
            "gate": "GREEN_LIVE_SEND_CANARY_EXECUTION_PREFLIGHT_READY_NO_SEND",
            "selected_order_ref": approval_manifest["selected_order_ref"],
            "selected_db_row_id": approval_manifest["selected_db_row_id"],
            "selected_store_code": approval_manifest["selected_store_code"],
            "template_hash": approval_manifest["template_hash"],
            "expected_merchant_account_id": approval_manifest["expected_merchant_account_id"],
        },
    )
    _write_json_fixture(
        approval_dir / "live_send_canary_result_redacted.json",
        {
            "gate": "GREEN_LIVE_SIZE_REQUEST_TEMPLATE_SENT_ONE_ORDER",
            "selected_order_ref": approval_manifest["selected_order_ref"],
            "selected_db_row_id": approval_manifest["selected_db_row_id"],
            "selected_store_code": approval_manifest["selected_store_code"],
            "selected_status_filter": approval_manifest["selected_status_filter"],
            "template_hash": approval_manifest["template_hash"],
            "merchant_account_match_proven": True,
            "visible_merchant_selector_id": approval_manifest["expected_merchant_account_id"],
            "store_scoped_selector_map_applied": True,
            "browser_session_preserved": True,
            "order_search_performed": True,
            "chat_opened": True,
            "message_text_typed": True,
            "message_sent": True,
            "send_confirmation_observed": True,
            "sent_count": 1,
            "other_customer_messages_sent": False,
            "raw_order_id_exported": False,
            "raw_customer_text_exported": False,
            "raw_phone_exported": False,
            "cookie_token_session_exported": False,
        },
    )
    (approval_dir / "live_send_canary_closeout.md").write_text(
        "# Live Send Canary Closeout\n\nGate: GREEN_LIVE_SIZE_REQUEST_TEMPLATE_SENT_ONE_ORDER\n",
        encoding="utf-8",
    )
    capsys.readouterr()

    rc = after_live_send_watch_main(
        [
            "--approval-dir",
            str(approval_dir),
            "--live-send-execution-preflight-manifest",
            str(preflight_path),
            "--db",
            str(db_path),
            "--ledger-db",
            str(ledger_path),
            "--target-date",
            "2026-06-15",
            "--lookback-days",
            "2",
            "--reply-poll-window-minutes",
            "10,30",
            "--wait-seconds",
            "0",
            "--output-dir",
            str(output_dir),
        ]
    )
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    post_canary = json.loads(
        (output_dir / "post_canary_sequence" / "manifest.json").read_text(encoding="utf-8")
    )
    snapshot = export_customer_size_ledger_snapshot(ledger_path)

    assert rc == 0
    assert manifest["gate"] == "GREEN_AFTER_LIVE_SEND_LOCAL_POST_CANARY_READY_NO_EXTERNAL_WRITE"
    assert manifest["live_send_validation_gate"] == "GREEN_LIVE_SEND_CANARY_RESULT_ACCEPTED_ONE_ORDER"
    assert manifest["post_canary_gate"] == "GREEN_POST_CANARY_SEQUENCE_LOCAL_REPLY_POLLING_READY_NO_EXTERNAL_WRITE"
    assert post_canary["gate"] == "GREEN_POST_CANARY_SEQUENCE_LOCAL_REPLY_POLLING_READY_NO_EXTERNAL_WRITE"
    assert snapshot[0]["status"] == "REQUEST_SENT"
    assert (output_dir / "post_canary_sequence" / "03_reply_polling_preflight" / "manifest.json").exists()
    assert manifest["customer_send_performed_by_this_helper"] is False


def test_after_board_apply_readiness_goes_green_from_verified_apply_and_dry_runs(
    tmp_path, capsys
):
    apply_manifest = tmp_path / "board_apply" / "manifest.json"
    size_report = tmp_path / "size_writeback_dry_run.json"
    readiness_report = tmp_path / "closeout_readiness.json"
    output_dir = tmp_path / "after_board"
    _write_json_fixture(
        apply_manifest,
        {
            "gate": "GREEN_GOOGLE_BOARD_MY_SIZE_PATCH_APPLIED_AND_READBACK_VERIFIED",
            "apply": True,
            "google_board_write_performed": True,
            "post_apply_readback_verified": True,
            "live_board_readback": True,
            "raw_order_id_exported": False,
            "raw_reply_text_exported": False,
        },
    )
    _write_json_fixture(
        size_report,
        {
            "apply": False,
            "updates_count": 1,
            "updates_applied": 0,
            "invalid_rows_count": 0,
            "db_backup_path": None,
            "updates_planned": [
                {
                    "target_key": "36140",
                    "new_assigned_size": "L",
                    "old_assigned_size": "",
                    "store_code": "ACMEWEAR",
                }
            ],
        },
    )
    _write_json_fixture(
        readiness_report,
        {
            "target_date": "2026-06-15",
            "ready": True,
            "run_control_target_match": True,
            "run_control_ready_value": "READY",
            "run_control_ready_ok": True,
            "salesraw_row_count": 1,
            "blank_size_count": 0,
            "blank_size_rows": [],
            "invalid_size_count": 0,
            "invalid_size_rows": [],
            "pending_db_writeback_count": 1,
        },
    )
    capsys.readouterr()

    rc = after_board_apply_readiness_main(
        [
            "--google-board-apply-manifest",
            str(apply_manifest),
            "--size-writeback-report",
            str(size_report),
            "--closeout-readiness-report",
            str(readiness_report),
            "--target-date",
            "2026-06-15",
            "--lookback-days",
            "2",
            "--output-dir",
            str(output_dir),
        ]
    )
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    phrase = (
        output_dir / "REQUIRED_EXACT_CLOSEOUT_RESUME_AFTER_BOARD_APPLY_APPROVAL_PHRASE.txt"
    ).read_text(encoding="utf-8")
    handoff = (
        output_dir / "KASPI_CUSTOMER_SIZE_AFTER_BOARD_APPLY_CLOSEOUT_RESUME_HANDOFF.md"
    ).read_text(encoding="utf-8")
    readiness_summary = json.loads(
        (output_dir / "closeout_readiness_summary_redacted.json").read_text(encoding="utf-8")
    )

    assert rc == 0
    assert manifest["gate"] == "GREEN_AFTER_GOOGLE_BOARD_MY_SIZE_APPLY_CLOSEOUT_RESUME_READY_NO_WRITE"
    assert manifest["approval_phrase_generated"] is True
    assert manifest["db_write_performed"] is False
    assert manifest["telegram_send_performed"] is False
    assert manifest["customer_chat_send_or_read_performed"] is False
    assert manifest["size_writeback_pending_updates_count"] == 1
    assert readiness_summary["raw_order_id_exported"] is False
    assert "run_google_ops_board_closeout.py" in handoff
    assert "KASPI_CUSTOMER_SIZE_AFTER_BOARD_APPLY_CLOSEOUT_RESUME" in phrase


def test_after_board_apply_readiness_blocks_prefight_only_board_apply_manifest(
    tmp_path, capsys
):
    apply_manifest = tmp_path / "board_apply" / "manifest.json"
    size_report = tmp_path / "size_writeback_dry_run.json"
    readiness_report = tmp_path / "closeout_readiness.json"
    output_dir = tmp_path / "after_board"
    _write_json_fixture(
        apply_manifest,
        {
            "gate": "GREEN_GOOGLE_BOARD_MY_SIZE_PATCH_PREFLIGHT_READY_NO_WRITE",
            "apply": False,
            "google_board_write_performed": False,
            "post_apply_readback_verified": False,
        },
    )
    _write_json_fixture(
        size_report,
        {"apply": False, "updates_count": 1, "updates_applied": 0, "invalid_rows_count": 0},
    )
    _write_json_fixture(
        readiness_report,
        {
            "target_date": "2026-06-15",
            "ready": True,
            "run_control_target_match": True,
            "run_control_ready_value": "READY",
            "run_control_ready_ok": True,
            "blank_size_count": 0,
            "invalid_size_count": 0,
        },
    )
    capsys.readouterr()

    rc = after_board_apply_readiness_main(
        [
            "--google-board-apply-manifest",
            str(apply_manifest),
            "--size-writeback-report",
            str(size_report),
            "--closeout-readiness-report",
            str(readiness_report),
            "--target-date",
            "2026-06-15",
            "--lookback-days",
            "2",
            "--output-dir",
            str(output_dir),
        ]
    )
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

    assert rc == 1
    assert manifest["gate"] == "YELLOW_AFTER_GOOGLE_BOARD_MY_SIZE_APPLY_CLOSEOUT_RESUME_BLOCKED_NO_WRITE"
    assert "google_board_apply_gate=GREEN_GOOGLE_BOARD_MY_SIZE_PATCH_PREFLIGHT_READY_NO_WRITE" in manifest["blockers"]
    assert manifest["approval_phrase_generated"] is False
    assert not (
        output_dir / "REQUIRED_EXACT_CLOSEOUT_RESUME_AFTER_BOARD_APPLY_APPROVAL_PHRASE.txt"
    ).exists()
    assert manifest["db_write_performed"] is False
    assert manifest["telegram_send_performed"] is False


def test_live_send_acceptance_core_keeps_later_reply_state(tmp_path):
    db_path = tmp_path / "orders.db"
    ledger_path = tmp_path / "ledger.sqlite"
    _make_orders_db(db_path)
    candidates = load_missing_size_candidates(
        db_path,
        target_date=date(2026, 6, 15),
        lookback_days=2,
        stores=["ACMEWEAR"],
    )
    request_plan = build_request_ledger_plan(candidates, template=DEFAULT_REQUEST_TEMPLATE)
    upsert_request_ledger_plan(ledger_path, request_plan)
    record_synthetic_reply_observations(
        ledger_path,
        [
            {
                "order_ref": request_plan[0]["order_ref"],
                "reply_text": "рост 175 вес 75",
                "product_type": "CL",
            }
        ],
    )

    stats, schedule = record_live_send_canary_acceptance(
        ledger_path,
        {
            "gate": "GREEN_LIVE_SEND_CANARY_RESULT_ACCEPTED_ONE_ORDER",
            "selected_order_ref": request_plan[0]["order_ref"],
        },
        now=datetime(2026, 6, 16, 15, 0, 0),
    )
    snapshot = export_customer_size_ledger_snapshot(ledger_path)

    assert stats["already_after_send_or_reply"] == 1
    assert snapshot[0]["status"] == "CLASSIFICATION_READY"
    assert snapshot[0]["planned_size"] == "L"
    assert len(schedule) == 4


def test_live_send_result_validator_rejects_multiple_sends(tmp_path, capsys):
    db_path = tmp_path / "orders.db"
    packet_dir = tmp_path / "packet"
    approval_dir = tmp_path / "approval"
    validation_path = packet_dir / "live_ui_canary_result_validation.json"
    _make_orders_db(db_path)
    assert (
        canary_packet_main(
            [
                "--db",
                str(db_path),
                "--target-date",
                "2026-06-15",
                "--lookback-days",
                "2",
                "--store-priority",
                "ACMEWEAR",
                "--output-dir",
                str(packet_dir),
            ]
        )
        == 0
    )
    packet_manifest = json.loads((packet_dir / "manifest.json").read_text(encoding="utf-8"))
    validation_path.write_text(
        json.dumps(
            {
                "gate": "GREEN_LIVE_UI_NO_SEND_CANARY_RESULT_ACCEPTED",
                "selected_order_ref": packet_manifest["selected_order_ref"],
                "selected_db_row_id": packet_manifest["selected_db_row_id"],
                "selected_store_code": packet_manifest["selected_store_code"],
                "selected_status_filter": packet_manifest["selected_status_filter"],
                "accepted": True,
                "raw_order_id_exported": False,
                "raw_customer_text_exported": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    assert (
        live_send_approval_packet_main(
            [
                "--packet-dir",
                str(packet_dir),
                "--live-ui-validation-json",
                str(validation_path),
                "--output-dir",
                str(approval_dir),
            ]
        )
        == 0
    )
    approval_manifest = json.loads((approval_dir / "manifest.json").read_text(encoding="utf-8"))
    (approval_dir / "live_send_canary_result_redacted.json").write_text(
        json.dumps(
            {
                "gate": "GREEN_LIVE_SIZE_REQUEST_TEMPLATE_SENT_ONE_ORDER",
                "selected_order_ref": approval_manifest["selected_order_ref"],
                "template_hash": approval_manifest["template_hash"],
                "merchant_account_match_proven": True,
                "visible_merchant_selector_id": approval_manifest["expected_merchant_account_id"],
                "store_scoped_selector_map_applied": True,
                "browser_session_preserved": True,
                "order_search_performed": True,
                "chat_opened": True,
                "message_text_typed": True,
                "message_sent": True,
                "send_confirmation_observed": True,
                "sent_count": 2,
                "other_customer_messages_sent": False,
                "raw_order_id_exported": False,
                "raw_customer_text_exported": False,
                "raw_phone_exported": False,
                "cookie_token_session_exported": False,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (approval_dir / "live_send_canary_closeout.md").write_text(
        "# Live Send Canary Closeout\n\nGate: GREEN_LIVE_SIZE_REQUEST_TEMPLATE_SENT_ONE_ORDER\n",
        encoding="utf-8",
    )
    capsys.readouterr()

    rc = validate_live_send_canary_result_main(
        [
            "--approval-dir",
            str(approval_dir),
            "--output-json",
            str(approval_dir / "live_send_canary_result_validation.json"),
        ]
    )
    validation = json.loads(
        (approval_dir / "live_send_canary_result_validation.json").read_text(encoding="utf-8")
    )

    assert rc == 2
    assert validation["gate"] == "RED_LIVE_SEND_CANARY_SENT_COUNT_NOT_ONE"
    assert "sent_count_not_one" in validation["blockers"]


def test_google_board_my_size_patch_plans_only_target_cell():
    contract = load_ops_board_contract()
    headers = contract.tabs["SalesRaw_Today"].headers
    row = {header: "" for header in headers}
    row.update({"Status": "NEW", "_db_row_id": "36140", "MY_SIZE": ""})
    matrix = [headers, [row.get(header, "") for header in headers]]

    updates, blockers = plan_board_cell_updates(
        contract=contract,
        patch_rows=[
            {
                "target_tab": "SalesRaw_Today",
                "key_column": "_db_row_id",
                "key_value": 36140,
                "source_column": "MY_SIZE",
                "planned_cell_value": "M",
            }
        ],
        board_matrix=matrix,
    )

    assert blockers == []
    assert updates == [
        {
            "range": "SalesRaw_Today!I2",
            "tab": "SalesRaw_Today",
            "column": "MY_SIZE",
            "key_column": "_db_row_id",
            "key_value": "36140",
            "sheet_row": 2,
            "value": "M",
            "current_value": "",
        }
    ]


def test_google_board_my_size_patch_blocks_conflicting_nonblank_size():
    contract = load_ops_board_contract()
    headers = contract.tabs["SalesRaw_Today"].headers
    row = {header: "" for header in headers}
    row.update({"Status": "NEW", "_db_row_id": "36140", "MY_SIZE": "S"})
    matrix = [headers, [row.get(header, "") for header in headers]]

    updates, blockers = plan_board_cell_updates(
        contract=contract,
        patch_rows=[
            {
                "target_tab": "SalesRaw_Today",
                "key_column": "_db_row_id",
                "key_value": "36140",
                "source_column": "MY_SIZE",
                "planned_cell_value": "M",
            }
        ],
        board_matrix=matrix,
    )

    assert updates == []
    assert blockers == [
        {
            "blocker": "target_my_size_conflicting_nonblank",
            "key_value": "36140",
            "current_value": "S",
            "planned_value": "M",
        }
    ]


def test_google_board_my_size_apply_requires_exact_approval_and_env():
    blockers = validate_apply_authority(
        apply=True,
        expected_approval="I approve exact",
        supplied_approval="wrong",
        contract_write_env_gate="ENABLE_GOOGLE_OPS_BOARD_WRITE",
        environ={
            "ENABLE_GOOGLE_OPS_BOARD_WRITE": "1",
            NARROW_WRITE_ENV_GATE: "0",
        },
    )

    assert blockers == [
        "owner_approval_text_mismatch",
        f"{NARROW_WRITE_ENV_GATE}_not_1",
    ]

    assert (
        validate_apply_authority(
            apply=True,
            expected_approval="I approve exact",
            supplied_approval="I approve exact",
            contract_write_env_gate="ENABLE_GOOGLE_OPS_BOARD_WRITE",
            environ={
                "ENABLE_GOOGLE_OPS_BOARD_WRITE": "1",
                NARROW_WRITE_ENV_GATE: "1",
            },
        )
        == []
    )


def test_playwright_no_send_result_contract_goes_green_only_when_all_required_flags_true():
    manifest = {
        "selected_order_ref": "sha256:abc",
        "selected_db_row_id": 36140,
        "selected_store_code": "ACMEWEAR",
        "selected_status_filter": "KASPI_DELIVERY_WAIT_FOR_COURIER",
    }

    green = build_playwright_no_send_result(
        manifest=manifest,
        proof_source="test",
        merchant_account_match_proven=True,
        order_search_performed=True,
        order_detail_or_result_reached=True,
        chat_button_present=True,
        notes=[],
    )
    yellow = build_playwright_no_send_result(
        manifest=manifest,
        proof_source="test",
        merchant_account_match_proven=True,
        order_search_performed=True,
        order_detail_or_result_reached=True,
        chat_button_present=False,
        notes=["chat_button_not_visible_after_search"],
    )

    assert green["gate"] == "GREEN_LIVE_ORDER_CHAT_BUTTON_PROVEN_NO_SEND"
    assert yellow["gate"] == "YELLOW_LIVE_ORDER_CHAT_BUTTON_NOT_PROVEN_NO_SEND"
    assert green["message_sent"] is False
    assert green["raw_order_id_exported"] is False
    assert yellow["notes"] == ["chat_button_not_visible_after_search"]


def test_playwright_no_send_probe_writes_yellow_artifacts_when_runtime_resolver_blocks(
    tmp_path,
    monkeypatch,
):
    import scripts.probe_kaspi_customer_chat_live_playwright_no_send as probe
    from scripts.resolve_kaspi_customer_chat_canary_runtime_secret import ResolverError

    packet_dir = tmp_path / "packet"
    packet_dir.mkdir()
    (packet_dir / "manifest.json").write_text(
        json.dumps(
            {
                "selected_order_ref": "sha256:redacted",
                "selected_db_row_id": 36140,
                "selected_store_code": "ACMEWEAR",
                "selected_status_filter": "KASPI_DELIVERY_WAIT_FOR_COURIER",
                "db_path": str(tmp_path / "missing.db"),
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    def _blocked_resolver(_args):
        raise ResolverError(
            "YELLOW_RUNTIME_SECRET_CANDIDATE_NO_LONGER_ACTIVE_MISSING_SIZE",
            "Resolved row is no longer active",
            exit_code=3,
        )

    monkeypatch.setattr(probe, "resolve_runtime_secret", _blocked_resolver)

    summary = probe.run(
        argparse.Namespace(
            packet_dir=packet_dir,
            db=tmp_path / "missing.db",
            storage_state=tmp_path / "missing_storage_state.json",
            headful=False,
            timeout_ms=1,
            result_json=None,
            diagnostics_json=None,
            validation_json=None,
            closeout_md=None,
            require_green=False,
        )
    )

    audit = json.loads((packet_dir / "runtime_secret_resolver_audit_redacted.json").read_text())
    result = json.loads((packet_dir / "live_ui_probe_result_redacted.json").read_text())
    diagnostics = json.loads((packet_dir / "live_playwright_no_send_diagnostics_redacted.json").read_text())
    validation = json.loads((packet_dir / "live_ui_canary_result_validation.json").read_text())
    closeout = (packet_dir / "live_ui_no_send_probe_closeout.md").read_text(encoding="utf-8")

    assert summary["gate"] == "YELLOW_LIVE_ORDER_CHAT_BUTTON_NOT_PROVEN_NO_SEND"
    assert audit["gate"] == "YELLOW_RUNTIME_SECRET_CANDIDATE_NO_LONGER_ACTIVE_MISSING_SIZE"
    assert audit["raw_order_id_exported"] is False
    assert audit["raw_customer_text_exported"] is False
    assert result["proof_source"] == "runtime_secret_resolver_blocked"
    assert result["message_sent"] is False
    assert result["raw_order_id_exported"] is False
    assert diagnostics["resolver_blocked_before_browser_action"] is True
    assert validation["gate"] == "YELLOW_RUNTIME_SECRET_AUDIT_NOT_GREEN"
    assert "Gate: YELLOW_LIVE_ORDER_CHAT_BUTTON_NOT_PROVEN_NO_SEND" in closeout


def test_session_refresh_helpers_redact_urls_and_classify_login_state():
    target = session_refresh_target_url("KASPI_DELIVERY_WAIT_FOR_COURIER")

    assert target == "https://kaspi.kz/mc/#/orders-new?status=KASPI_DELIVERY_WAIT_FOR_COURIER"
    assert (
        safe_session_refresh_url(target)
        == "https://kaspi.kz/mc/#/orders-new?[redacted]"
    )
    assert login_state_from_url("https://idmc.shop.kaspi.kz/login") == "login"
    assert (
        login_state_from_url("https://merchant.kaspi.kz/new/account/entrance")
        == "login"
    )
    assert login_state_from_url("https://kaspi.kz/mc/#/orders-new") == "unknown_or_logged_in"
    assert default_session_refresh_storage_state("acmewear").name == "kaspi_webui_archive_session_ACMEWEAR.json"
    assert (
        default_session_refresh_profile_dir("acmewear").name
        == "kaspi_customer_chat_profile_ACMEWEAR"
    )


def test_session_refresh_manifest_and_closeout_are_no_send_safe(tmp_path):
    diagnostics_path = tmp_path / "diag.json"
    storage_state = tmp_path / "state.json"
    profile_dir = tmp_path / "profile"
    manifest = build_session_refresh_manifest(
        gate=SESSION_REFRESH_GREEN_GATE,
        store_code="ACMEWEAR",
        status_filter="KASPI_DELIVERY_WAIT_FOR_COURIER",
        target_url="https://kaspi.kz/mc/#/orders-new?status=KASPI_DELIVERY_WAIT_FOR_COURIER",
        storage_state=storage_state,
        persistent_profile_dir=profile_dir,
        diagnostics_path=diagnostics_path,
        blockers=[],
        manual_login_timeout_seconds=900.0,
    )
    closeout = build_session_refresh_closeout(manifest)

    assert manifest["gate"] == SESSION_REFRESH_GREEN_GATE
    assert manifest["customer_send_allowed"] is False
    assert manifest["kaspi_chat_write_allowed"] is False
    assert manifest["order_search_performed"] is False
    assert manifest["chat_opened"] is False
    assert manifest["message_text_typed"] is False
    assert manifest["message_sent"] is False
    assert manifest["persistent_profile_mode"] is True
    assert manifest["persistent_profile_dir_path"].endswith("profile")
    assert manifest["raw_order_id_exported"] is False
    assert manifest["raw_customer_text_exported"] is False
    assert manifest["raw_phone_exported"] is False
    assert manifest["raw_session_material_exported"] is False
    assert "Gate: GREEN_KASPI_CUSTOMER_CHAT_PLAYWRIGHT_SESSION_READY_NO_SEND" in closeout
    assert "Persistent profile mode: true" in closeout
    assert "Message sent: false" in closeout
