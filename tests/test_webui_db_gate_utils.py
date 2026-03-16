from __future__ import annotations

import json
from pathlib import Path

from scripts.webui_db_gate_utils import resolve_effective_missing_in_db_orders


def test_resolve_effective_missing_in_db_orders_matches_coerced_period_end(tmp_path: Path) -> None:
    ledger_root = tmp_path / "ledger"
    ledger_root.mkdir()
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    (output_dir / "webui_vs_db_report.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "ledger_root": str(ledger_root.resolve()),
                "period": {"start": "2026-01-01", "end": "2026-02-28"},
                "missing_in_db_orders": 0,
                "original_missing_in_db_orders": 6,
            }
        ),
        encoding="utf-8",
    )

    effective_missing, source_meta = resolve_effective_missing_in_db_orders(
        output_dir=output_dir,
        ledger_root=ledger_root,
        start="2026-01-01",
        end="2026-02-29",
        projection_meta={"missing_in_db_orders": 6},
    )

    assert effective_missing == 0
    assert source_meta is not None
    assert source_meta["payload"]["period"]["end"] == "2026-02-28"


def test_resolve_effective_missing_in_db_orders_preserves_raw_missing_when_ledger_differs(
    tmp_path: Path,
) -> None:
    ledger_root = tmp_path / "ledger"
    ledger_root.mkdir()
    other_ledger_root = tmp_path / "other_ledger"
    other_ledger_root.mkdir()
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    (output_dir / "webui_vs_db_report.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "ledger_root": str(other_ledger_root.resolve()),
                "period": {"start": "2026-01-01", "end": "2026-02-28"},
                "missing_in_db_orders": 0,
                "original_missing_in_db_orders": 6,
            }
        ),
        encoding="utf-8",
    )

    effective_missing, source_meta = resolve_effective_missing_in_db_orders(
        output_dir=output_dir,
        ledger_root=ledger_root,
        start="2026-01-01",
        end="2026-02-29",
        projection_meta={"missing_in_db_orders": 6},
    )

    assert effective_missing == 6
    assert source_meta is None


def test_resolve_effective_missing_in_db_orders_reads_nested_report_in_output_dir(
    tmp_path: Path,
) -> None:
    ledger_root = tmp_path / "ledger"
    ledger_root.mkdir()
    output_dir = tmp_path / "out"
    nested_dir = output_dir / "full_range_db_gate"
    nested_dir.mkdir(parents=True)

    (nested_dir / "webui_vs_db_report.json").write_text(
        json.dumps(
            {
                "status": "FAIL",
                "ledger_root": str(ledger_root.resolve()),
                "period": {"start": "2025-06-06", "end": "2026-03-08"},
                "missing_in_db_orders": 0,
                "original_missing_in_db_orders": 57,
            }
        ),
        encoding="utf-8",
    )

    effective_missing, source_meta = resolve_effective_missing_in_db_orders(
        output_dir=output_dir,
        ledger_root=ledger_root,
        start="2025-06-06",
        end="2026-03-08",
        projection_meta={"missing_in_db_orders": 57},
    )

    assert effective_missing == 0
    assert source_meta is not None
    assert source_meta["path"].endswith("full_range_db_gate/webui_vs_db_report.json")
