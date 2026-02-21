from __future__ import annotations

import json
import subprocess
from pathlib import Path

import openpyxl


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "validate_inbound_sheet_consistency.py"


def _make_workbook(path: Path, *, cargo_qty: int, actual_qty: int, ordered_qty: int = 3980) -> None:
    wb = openpyxl.Workbook()

    ws_inbounds = wb.active
    ws_inbounds.title = "Inbounds_sheet"
    ws_inbounds.append(["PO_part_id", "SKU_key", "Qty", "Actual_qty"])
    ws_inbounds.append(["PO-5.2", "CL_OC_MEN_LINE52_BLACK", ordered_qty, actual_qty])

    ws_totals = wb.create_sheet("PO_part_id_Totals")
    ws_totals.append(["PO_part_id", "Total Units"])
    ws_totals.append(["PO-5.2", actual_qty])

    ws_cargo = wb.create_sheet("Cargo_send_31.1.2026_PO-5.2_4.2")
    ws_cargo.append(["PO_part_id", "SKU_key", "Qty"])
    ws_cargo.append(["PO-5.2", "CL_OC_MEN_LINE52_BLACK", cargo_qty])

    wb.save(path)


def _run(xlsx: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--xlsx",
            str(xlsx),
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_flags_qty_mismatch_between_cargo_and_inbounds(tmp_path: Path) -> None:
    xlsx = tmp_path / "inbound.xlsx"
    _make_workbook(xlsx, cargo_qty=3940, actual_qty=3980)

    proc = _run(xlsx)
    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    mismatches = payload["mismatches"]
    assert mismatches
    first = mismatches[0]
    assert first["po_part_id"] == "PO-5.2"
    assert first["sku_key"] == "CL_OC_MEN_LINE52_BLACK"
    assert first["expected_qty"] == 3980
    assert first["observed_qty"] == 3940


def test_reports_authoritative_sheet_precedence(tmp_path: Path) -> None:
    xlsx = tmp_path / "inbound.xlsx"
    # Qty != Actual_qty; validator must prefer Actual_qty as authoritative.
    _make_workbook(xlsx, cargo_qty=3980, actual_qty=3980, ordered_qty=4200)

    proc = _run(xlsx)
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["authoritative_sheet"] == "Inbounds_sheet"
    assert payload["authoritative_quantity_column"] == "Actual_qty"


def test_exit_nonzero_on_contract_breach(tmp_path: Path) -> None:
    xlsx = tmp_path / "inbound.xlsx"
    _make_workbook(xlsx, cargo_qty=3950, actual_qty=3980)

    proc = _run(xlsx)
    assert proc.returncode != 0
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert payload["mismatch_count"] >= 1
