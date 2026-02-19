from __future__ import annotations

from pathlib import Path

import pytest


CONTRACT_DOC = Path("docs/WRITE_SIDE_GATING_CONTRACT.md")

WRITE_GATED_SCRIPTS = [
    ("scripts/rebuild_cashflow_calendar.py", "ENABLE_CASHFLOW_WRITE"),
    ("scripts/sync_opex_schedule.py", "ENABLE_CASHFLOW_WRITE"),
    ("scripts/reconcile_on_delivery_settlement.py", "ENABLE_CASHFLOW_WRITE"),
    ("scripts/sync_po_parts_from_inbound_calendar.py", "ENABLE_PO_PART_SYNC_WRITE"),
    ("scripts/sync_dim_sku_from_dim_sku_light.py", "ENABLE_DIM_SKU_SYNC_WRITE"),
    ("scripts/migrate_023_po_parts_schema.py", "ENABLE_SCHEMA_WRITE"),
    ("scripts/migrate_025_dim_sku_weight_guard.py", "ENABLE_SCHEMA_WRITE"),
]


def test_write_side_contract_doc_exists_and_declares_fail_closed_policy() -> None:
    assert CONTRACT_DOC.exists(), "missing write-side gating contract doc"
    text = CONTRACT_DOC.read_text(encoding="utf-8")
    assert "fail-closed" in text.lower()
    assert "--apply" in text
    assert "ENABLE_" in text


@pytest.mark.parametrize(("script_path", "env_gate"), WRITE_GATED_SCRIPTS)
def test_write_side_scripts_require_env_gate_and_apply_flag(script_path: str, env_gate: str) -> None:
    script = Path(script_path)
    text = script.read_text(encoding="utf-8")
    assert "--apply" in text, f"{script_path} missing --apply flag"
    assert env_gate in text, f"{script_path} missing env gate {env_gate}"

