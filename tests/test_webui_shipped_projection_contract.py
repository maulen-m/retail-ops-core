from pathlib import Path


def test_webui_shipped_projection_contract_exists_and_declares_event_basis() -> None:
    path = Path("docs/validation/WEBUI_SHIPPED_EVENT_PROJECTION_CONTRACT.md")
    assert path.exists(), "missing shipped projection contract"
    text = path.read_text(encoding="utf-8")
    assert "planned_courier_at" in text
    assert "created_at" in text
    assert "not depend on DB-matched rows" in text
    assert "returned orders are excluded" in text
    assert "fail-closed" in text.lower()
