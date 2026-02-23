from __future__ import annotations

from pathlib import Path

from core.stores.roster import load_active_store_codes


AUTHORITY_DOC = Path("docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md")
STORE_MAP = {
    "Universal": "UNIVERSAL",
    "AcmeWear": "ACMEWEAR",
    "11KZ": "11KZ",
    "Store-C": "MELVIS",
    "STORE-B": "STOREB",
}


def _extract_authority_store_codes() -> set[str]:
    text = AUTHORITY_DOC.read_text(encoding="utf-8")
    marker = "## Multi-Store Scale Roster"
    assert marker in text, "missing roster section in authority doc"
    section = text.split(marker, 1)[1]
    section = section.split("\n## ", 1)[0]
    lines = [line.strip() for line in section.splitlines() if line.strip().startswith("- ")]
    names = [line[2:].strip() for line in lines]
    return {STORE_MAP[name] for name in names if name in STORE_MAP}


def test_store_roster_config_matches_authority_doc() -> None:
    config_codes = set(load_active_store_codes())
    authority_codes = _extract_authority_store_codes()
    assert config_codes == authority_codes
