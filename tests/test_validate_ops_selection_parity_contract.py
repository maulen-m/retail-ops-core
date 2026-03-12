from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validate_ops_selection_parity import validate_ops_selection_parity


def test_validate_ops_selection_parity_fails_closed_without_import_log(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="missing import log"):
        validate_ops_selection_parity(
            as_of="2026-03-09",
            import_log=tmp_path / "runtime_logs" / "kaspi_import_stdout.log",
            waybill_log=tmp_path / "runtime_logs" / "kaspi_waybill_deadline_stdout.log",
            archive_root=tmp_path / "excel_ui" / "Archive",
            selection_cache=tmp_path / "excel_ui" / "ActiveOrders" / "waybills" / "_waybill_selection_orders.json",
            output_root=tmp_path / "exports" / "validation" / "ops_selection_parity",
            strict=True,
            max_import_overflow=5,
        )


def test_validate_ops_selection_parity_fails_closed_without_waybill_log(tmp_path: Path) -> None:
    import_log = tmp_path / "runtime_logs" / "kaspi_import_stdout.log"
    import_log.parent.mkdir(parents=True, exist_ok=True)
    import_log.write_text("", encoding="utf-8")

    with pytest.raises(RuntimeError, match="missing waybill log"):
        validate_ops_selection_parity(
            as_of="2026-03-09",
            import_log=import_log,
            waybill_log=tmp_path / "runtime_logs" / "kaspi_waybill_deadline_stdout.log",
            archive_root=tmp_path / "excel_ui" / "Archive",
            selection_cache=tmp_path / "excel_ui" / "ActiveOrders" / "waybills" / "_waybill_selection_orders.json",
            output_root=tmp_path / "exports" / "validation" / "ops_selection_parity",
            strict=True,
            max_import_overflow=5,
        )
