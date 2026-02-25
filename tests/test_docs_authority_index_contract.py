from __future__ import annotations

from pathlib import Path


def test_docs_authority_index_contract() -> None:
    index_path = Path("docs/authority/INDEX.md")
    assert index_path.exists(), f"missing authority index: {index_path}"
    text = index_path.read_text(encoding="utf-8")
    for required in [
        "# Authority Index",
        "## Operations",
        "## Inventory",
        "## PO Engine",
        "## Cashflow",
        "## API + Shipment",
        "## Governance",
    ]:
        assert required in text, f"missing section: {required}"
    assert "/Users/" not in text, "authority index must not include absolute personal paths"

