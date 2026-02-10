from pathlib import Path


def test_sync_to_gdrive_disables_link_updates_on_all_workbook_opens():
    text = Path("scripts/sync_to_gdrive.py").read_text(encoding="utf-8")

    # Source CRM open in both sync paths should not prompt for external links.
    assert "app.books.open(str(crm_path), read_only=True, update_links=False)" in text

    # Destination Drive open in both sync paths should not trigger link-location dialogs.
    assert text.count("app.books.open(str(gdrive_path), update_links=False)") >= 2
