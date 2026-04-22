from __future__ import annotations

import json
from pathlib import Path

from core.integrations.google_ops_board import load_ops_board_contract
from scripts import sync_google_ops_board_sizes_to_db as size_sync_mod


class _FakeClient:
    def __init__(self, matrix):
        self._matrix = matrix

    def get_tab_values(self, _tab_name):
        return self._matrix


def test_size_writeback_apply_skips_db_backup_when_no_updates(monkeypatch, tmp_path: Path) -> None:
    contract = load_ops_board_contract()
    headers = contract.tabs["SalesRaw_Today"].headers
    matrix = [
        headers,
        [""] * len(headers),
    ]
    row = {header: "" for header in headers}
    row["_db_row_id"] = "1"
    row["MY_SIZE"] = "L"
    matrix[1] = [row.get(header, "") for header in headers]
    output_json = tmp_path / "size_writeback.json"
    svc = tmp_path / "svc.json"
    svc.write_text("{}", encoding="utf-8")

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
                "store_code": "UNIVERSAL",
                "sku_key": "CL_TEST",
                "product_type": "CL",
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
        ]
    )

    assert rc == 0
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["updates_count"] == 0
    assert payload["updates_applied"] == 0
    assert payload["db_backup_path"] is None
    assert payload["skipped_db_backup"] is True
    assert payload["noop"] is True
