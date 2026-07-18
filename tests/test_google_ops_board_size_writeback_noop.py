from __future__ import annotations

import json
import hashlib
from pathlib import Path

from core.integrations.google_ops_board import (
    OWNERSHIP_MODE_LEGACY_V3,
    contract_for_ownership_mode,
    load_ops_board_contract,
)
from scripts import sync_google_ops_board_sizes_to_db as size_sync_mod


class _FakeClient:
    def __init__(self, matrix):
        self._matrix = matrix

    def get_tab_values(self, _tab_name):
        return self._matrix


def _identity_db_row() -> dict[str, object]:
    return {
        "assigned_size": "",
        "order_id": "1001",
        "store_code": "UNIVERSAL",
        "sku_key": "CL_TEST",
        "sku_id": "CL_TEST_L",
        "kaspi_offer_name": "Test offer",
        "quantity": 1,
        "planned_shipment_date": "2026-04-22",
        "line_identity_available": True,
        "product_type": "CL",
    }


def test_size_writeback_rejects_duplicate_db_row_id() -> None:
    rows = [
        {
            "_db_row_id": "1",
            "MY_SIZE": "L",
            "OrderID": "1001",
            "STORE_NAME": "Universal",
            "_line_key": "1001|2026-04-22|CL_TEST|Test offer|1",
        },
        {
            "_db_row_id": "1",
            "MY_SIZE": "XL",
            "OrderID": "1001",
            "STORE_NAME": "Universal",
            "_line_key": "1001|2026-04-22|CL_TEST|Test offer|1",
        },
    ]

    plan = size_sync_mod.plan_size_writeback(
        rows,
        {"1": _identity_db_row()},
        key_column="_db_row_id",
        source_column="MY_SIZE",
        require_visible_identity=True,
    )

    assert plan["invalid_rows"][0]["reason"] == "duplicate_db_row_id"


def test_size_writeback_rejects_missing_db_row_id() -> None:
    plan = size_sync_mod.plan_size_writeback(
        [{"_db_row_id": "", "MY_SIZE": "L", "OrderID": "1001", "STORE_NAME": "Universal"}],
        {},
        key_column="_db_row_id",
        source_column="MY_SIZE",
        require_visible_identity=True,
    )

    assert plan["updates"] == []
    assert plan["invalid_rows"] == [
        {"target_key": "", "raw_input_size": "L", "reason": "missing_db_row_id"}
    ]


def test_size_writeback_rejects_visible_line_identity_mismatch() -> None:
    plan = size_sync_mod.plan_size_writeback(
        [
            {
                "_db_row_id": "1",
                "MY_SIZE": "L",
                "OrderID": "OTHER",
                "STORE_NAME": "AcmeWear",
                "_line_key": "wrong",
            }
        ],
        {"1": _identity_db_row()},
        key_column="_db_row_id",
        source_column="MY_SIZE",
        require_visible_identity=True,
    )

    assert plan["updates"] == []
    assert plan["invalid_rows"][0]["reason"] == "visible_identity_mismatch"
    assert plan["invalid_rows"][0]["identity_issues"] == [
        "order_id_mismatch",
        "store_code_mismatch",
        "line_key_mismatch",
    ]


def test_size_writeback_plan_preserves_effective_size_provenance() -> None:
    row = {
        "_db_row_id": "1",
        "MY_SIZE": "XL",
        "raw_my_size": "",
        "raw_auto_size_suggestion": "XL",
        "effective_size": "XL",
        "effective_size_source": "AUTO_SIZE_SUGGESTION",
        "OrderID": "1001",
        "STORE_NAME": "Universal",
        "_line_key": "1001|2026-04-22|CL_TEST|Test offer|1",
    }

    plan = size_sync_mod.plan_size_writeback(
        [row],
        {"1": _identity_db_row()},
        key_column="_db_row_id",
        source_column="MY_SIZE",
        require_visible_identity=True,
    )

    assert plan["invalid_rows"] == []
    assert plan["updates"] == [
        {
            "target_key": "1",
            "raw_input_size": "XL",
            "new_assigned_size": "XL",
            "old_assigned_size": "",
            "store_code": "UNIVERSAL",
            "product_type": "CL",
            "raw_my_size": "",
            "raw_auto_size_suggestion": "XL",
            "effective_size": "XL",
            "effective_size_source": "AUTO_SIZE_SUGGESTION",
        }
    ]


def test_size_writeback_apply_skips_db_backup_when_no_updates(monkeypatch, tmp_path: Path) -> None:
    contract = contract_for_ownership_mode(
        load_ops_board_contract(), OWNERSHIP_MODE_LEGACY_V3
    )
    headers = contract.tabs["SalesRaw_Today"].headers
    matrix = [
        headers,
        [""] * len(headers),
    ]
    row = {header: "" for header in headers}
    row["_db_row_id"] = "1"
    row["MY_SIZE"] = "L"
    row["OrderID"] = "1001"
    row["STORE_NAME"] = "Universal"
    row["_line_key"] = "1001|2026-04-22|CL_TEST|Test offer|1"
    matrix[1] = [row.get(header, "") for header in headers]
    output_json = tmp_path / "size_writeback.json"
    svc = tmp_path / "svc.json"
    svc.write_text("{}", encoding="utf-8")
    scope_rows = [
        {
            "store_code": "UNIVERSAL",
            "order_id": "1001",
            "db_row_id": "1",
            "line_key": row["_line_key"],
            "my_size": "L",
        }
    ]
    scope_path = tmp_path / "scope.json"
    scope_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "target_date": "2026-04-22",
                "request_identity": {
                    "target_date": "2026-04-22",
                    "ready_set_at": "2026-04-22T17:00:00+05:00",
                },
                "orders": [{"store_code": "UNIVERSAL", "order_id": "1001"}],
                "rows": scope_rows,
                "scope_sha256": hashlib.sha256(
                    json.dumps(
                        scope_rows,
                        ensure_ascii=False,
                        sort_keys=True,
                    ).encode("utf-8")
                ).hexdigest(),
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv(contract.db_write_env_gate, "1")
    monkeypatch.setattr(
        size_sync_mod.GoogleOpsBoardClient,
        "from_service_account_file",
        lambda *_args, **_kwargs: _FakeClient(matrix),
    )
    monkeypatch.setattr(
        size_sync_mod,
        "_load_db_rows",
        lambda *_args, **_kwargs: {
            "1": {
                "assigned_size": "L",
                "order_id": "1001",
                "store_code": "UNIVERSAL",
                "sku_key": "CL_TEST",
                "product_type": "CL",
                "line_identity_available": False,
            }
        },
    )
    monkeypatch.setattr(
        size_sync_mod,
        "_backup_db",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("backup should not run")),
    )
    monkeypatch.setattr(
        size_sync_mod,
        "_apply_updates",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("apply should not run")),
    )

    rc = size_sync_mod.main(
        [
            "--apply",
            "--db",
            str(tmp_path / "app.db"),
            "--target-date",
            "2026-04-22",
            "--service-account-json",
            str(svc),
            "--spreadsheet-id",
            "sheet-id",
            "--output-json",
            str(output_json),
            "--allowed-order-scope-file",
            str(scope_path),
        ]
    )

    assert rc == 0
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["updates_count"] == 0
    assert payload["updates_applied"] == 0
    assert payload["db_backup_path"] is None
    assert payload["skipped_db_backup"] is True
    assert payload["noop"] is True
