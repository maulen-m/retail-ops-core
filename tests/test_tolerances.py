from pathlib import Path

import pytest

from core.validation.tolerances import parse_po_contract_tolerances

PROJECT_ROOT = Path(__file__).parent.parent
CONTRACT_PATH = PROJECT_ROOT / "docs" / "validation" / "PO_CONTRACT.md"


def test_tolerance_percent_points_parsing():
    tolerances = parse_po_contract_tolerances(CONTRACT_PATH)
    assert tolerances["d_30_ratio"] == pytest.approx(0.0025)


def test_tolerance_missing_key_raises(tmp_path: Path):
    contract = tmp_path / "PO_CONTRACT.md"
    contract.write_text(
        "\n".join(
            [
                "D_30_pct_points: 0.25",
                "SS_total_pct_points: 0.25",
                # ROIC_pct_points missing
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Missing tolerances"):
        parse_po_contract_tolerances(contract)

