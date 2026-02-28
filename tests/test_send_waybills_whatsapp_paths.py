from pathlib import Path

from scripts.send_waybills_whatsapp import collect_all_pdfs, find_store_folders


def _write_store_fixture(store_dir: Path, pdf_name: str = "sample.pdf") -> Path:
    store_dir.mkdir(parents=True, exist_ok=True)
    (store_dir / "manifest_normal_singles.csv").write_text("type,order_id\n", encoding="utf-8")
    pdf_path = store_dir / "NORMAL_singles" / pdf_name
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.0\n")
    return pdf_path


def test_collect_all_pdfs_legacy_today_layout(tmp_path: Path) -> None:
    today_root = tmp_path / "Today"
    store_dir = today_root / "TODAY" / "28.02.26_Universal_qnt1"
    _write_store_fixture(store_dir, "legacy.pdf")

    pdfs = collect_all_pdfs(today_root)

    assert len(pdfs) == 1
    assert pdfs[0]["store"] == "28.02.26_Universal_qnt1"
    assert pdfs[0]["relative"].startswith("TODAY/")


def test_collect_all_pdfs_prefers_per_store_layout_when_present(tmp_path: Path) -> None:
    today_root = tmp_path / "Today"

    # Legacy-style folder exists but should be ignored when PER_STORE exists.
    legacy_store = today_root / "TODAY" / "28.02.26_Universal_qnt1"
    _write_store_fixture(legacy_store, "legacy.pdf")

    per_store = today_root / "PER_STORE" / "TODAY" / "28.02.26_Universal_qnt1"
    _write_store_fixture(per_store, "per_store.pdf")

    folders = find_store_folders(today_root)
    pdfs = collect_all_pdfs(today_root)

    assert len(folders) == 1
    assert folders[0] == per_store
    assert len(pdfs) == 1
    assert pdfs[0]["filename"] == "per_store.pdf"
    assert pdfs[0]["relative"].startswith("PER_STORE/")
