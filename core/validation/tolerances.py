"""Tolerance parsing for PO/Dashboard contracts (single source of truth)."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PO_CONTRACT = PROJECT_ROOT / "docs" / "validation" / "PO_CONTRACT.md"

_KEY_MAP = {
    "D_30_pct_points": "d_30_ratio",
    "SS_total_pct_points": "ss_total_ratio",
    "ROIC_pct_points": "roic_ratio",
}

_LEGACY_KEYS = {"D_30_pct", "SS_total_pct", "ROIC_pct"}


def parse_po_contract_tolerances(path: Path | None = None) -> dict[str, float]:
    """
    Parse PO_CONTRACT tolerances and return ratios (percent-points ÷ 100).

    Contract units are percent points (e.g., 0.25 means 0.25%).
    """
    contract_path = path or DEFAULT_PO_CONTRACT
    text = contract_path.read_text(encoding="utf-8")

    tolerances: dict[str, float] = {}
    legacy_hits = []

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key = line.split(":", 1)[0].strip()
        if key in _LEGACY_KEYS:
            legacy_hits.append(key)
            continue
        if key in _KEY_MAP:
            value_raw = line.split(":", 1)[1].strip()
            value = float(value_raw)
            tolerances[_KEY_MAP[key]] = value / 100.0

    if legacy_hits:
        raise ValueError(
            "Legacy tolerance keys found in PO_CONTRACT.md: "
            f"{', '.join(sorted(set(legacy_hits)))}. "
            "Use *_pct_points keys only."
        )

    missing = [v for v in _KEY_MAP.values() if v not in tolerances]
    if missing:
        raise ValueError(f"Missing tolerances in PO_CONTRACT.md: {missing}")

    return tolerances

