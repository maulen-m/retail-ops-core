from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from scripts.validate_status_ledger_continuity import (
    StatusLedgerContinuityError,
    validate_status_ledger_continuity,
)


_SHA = "a" * 64


def _write_stores(path: Path) -> None:
    path.write_text(
        yaml.safe_dump({"stores": {"ACMEWEAR": {"enabled": True}}}),
        encoding="utf-8",
    )


def _write_ledger(root: Path, *, pack_windows: list[dict[str, str]]) -> Path:
    ledger_root = root / "ledger"
    ledger_root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "run_id": "ledger",
        "pack_windows": pack_windows,
        "ledger_sha256": "sha",
    }
    (ledger_root / "ledger_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    pd.DataFrame(
        [
            {
                "store_code": "ACMEWEAR",
                "order_id": "1",
                "status_internal": "DELIVERED",
                "status_change_at": "2026-01-05",
            }
        ]
    ).to_csv(ledger_root / "webui_status_ledger.csv", index=False, encoding="utf-8")
    return ledger_root


def test_validate_status_ledger_continuity_pass(tmp_path: Path) -> None:
    stores = tmp_path / "stores.yaml"
    _write_stores(stores)
    ledger = _write_ledger(
        tmp_path,
        pack_windows=[
            {
                "store_code": "ACMEWEAR",
                "window_since": "2026-01-01",
                "window_until": "2026-01-31",
                "source_file_sha256": _SHA,
                "window_provenance": "source_path",
                "source_file": "store_ACMEWEAR/ArchiveOrders_ACMEWEAR_2026-01-01_to_2026-01-31.xlsx",
            }
        ],
    )

    report = validate_status_ledger_continuity(
        ledger_root=ledger,
        start="2026-01-01",
        end="2026-01-31",
        stores_config=stores,
        strict=True,
    )
    assert report["status"] == "PASS"


def test_validate_status_ledger_continuity_strict_fail_on_gap(tmp_path: Path) -> None:
    stores = tmp_path / "stores.yaml"
    _write_stores(stores)
    ledger = _write_ledger(
        tmp_path,
        pack_windows=[
            {
                "store_code": "ACMEWEAR",
                "window_since": "2026-01-10",
                "window_until": "2026-01-31",
                "source_file_sha256": _SHA,
                "window_provenance": "source_path",
                "source_file": "store_ACMEWEAR/ArchiveOrders_ACMEWEAR_2026-01-10_to_2026-01-31.xlsx",
            }
        ],
    )

    with pytest.raises(StatusLedgerContinuityError):
        validate_status_ledger_continuity(
            ledger_root=ledger,
            start="2026-01-01",
            end="2026-01-31",
            stores_config=stores,
            strict=True,
        )


def test_validate_status_ledger_continuity_strict_fail_on_hand_edited_window(tmp_path: Path) -> None:
    stores = tmp_path / "stores.yaml"
    _write_stores(stores)
    ledger = _write_ledger(
        tmp_path,
        pack_windows=[
            {
                "store_code": "ACMEWEAR",
                "window_since": "2026-01-01",
                "window_until": "2026-01-31",
                "source_file": "store_ACMEWEAR/ArchiveOrders.xlsx",
            }
        ],
    )

    with pytest.raises(StatusLedgerContinuityError) as exc:
        validate_status_ledger_continuity(
            ledger_root=ledger,
            start="2026-01-01",
            end="2026-01-31",
            stores_config=stores,
            strict=True,
        )
    assert "pack_window_provenance_error_count=2" in str(exc.value)
