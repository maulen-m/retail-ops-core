from pathlib import Path

from scripts.send_waybills_whatsapp import (
    SOURCE_MERGED,
    collect_all_pdfs,
    find_store_folders,
    order_pdfs_for_sending,
)


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


def test_collect_all_pdfs_prefers_merged_layout_when_present(tmp_path: Path) -> None:
    today_root = tmp_path / "Today"

    # Legacy/per-store folders exist but should be ignored when MERGED exists.
    legacy_store = today_root / "TODAY" / "28.02.26_Universal_qnt1"
    _write_store_fixture(legacy_store, "legacy.pdf")

    per_store = today_root / "PER_STORE" / "TODAY" / "28.02.26_Universal_qnt1"
    _write_store_fixture(per_store, "per_store.pdf")

    merged_store = today_root / "MERGED" / "TODAY" / "28.02.26_MERGED_qnt1"
    _write_store_fixture(merged_store, "merged.pdf")

    folders = find_store_folders(today_root)
    pdfs = collect_all_pdfs(today_root)

    assert len(folders) == 1
    assert folders[0] == merged_store
    assert len(pdfs) == 1
    assert pdfs[0]["filename"] == "merged.pdf"
    assert pdfs[0]["relative"].startswith("MERGED/")


def test_collect_all_pdfs_can_force_merged_source(tmp_path: Path) -> None:
    today_root = tmp_path / "Today"
    merged_store = today_root / "MERGED" / "TODAY" / "28.02.26_MERGED_qnt1"
    _write_store_fixture(merged_store, "merged_only.pdf")

    folders = find_store_folders(today_root, source_mode=SOURCE_MERGED)
    pdfs = collect_all_pdfs(today_root, source_mode=SOURCE_MERGED)

    assert len(folders) == 1
    assert folders[0] == merged_store
    assert len(pdfs) == 1
    assert pdfs[0]["filename"] == "merged_only.pdf"


def test_ordering_size_rises_within_same_item_family() -> None:
    pdfs = [
        {
            "filename": "CL_NEW-CLO_MEN_RUSH_WHITE_XL-2.pdf",
            "category": "NORMAL_singles",
            "family_key": "RUSH",
            "size_rank": 13,
        },
        {
            "filename": "CL_NEW-CLO_MEN_RUSH_WHITE_S-1.pdf",
            "category": "NORMAL_singles",
            "family_key": "RUSH",
            "size_rank": 10,
        },
        {
            "filename": "CL_NEW-CLO_MEN_RUSH_WHITE_M-1.pdf",
            "category": "NORMAL_singles",
            "family_key": "RUSH",
            "size_rank": 11,
        },
    ]

    ordered = order_pdfs_for_sending(pdfs)

    assert [x["filename"] for x in ordered] == [
        "CL_NEW-CLO_MEN_RUSH_WHITE_S-1.pdf",
        "CL_NEW-CLO_MEN_RUSH_WHITE_M-1.pdf",
        "CL_NEW-CLO_MEN_RUSH_WHITE_XL-2.pdf",
    ]


def test_ordering_interleaves_same_family_with_other_items() -> None:
    pdfs = [
        {
            "filename": "CL_NEW-CLO_MEN_RUSH_WHITE_S-1.pdf",
            "category": "NORMAL_singles",
            "family_key": "RUSH",
            "size_rank": 10,
        },
        {
            "filename": "CL_NEW-CLO_MEN_RUSH-PRO_BLACK_M-1.pdf",
            "category": "NORMAL_singles",
            "family_key": "RUSH",
            "size_rank": 11,
        },
        {
            "filename": "CL_NEW-CLO_MEN_TAICI_BLACK_M-1.pdf",
            "category": "NORMAL_singles",
            "family_key": "TAICI",
            "size_rank": 11,
        },
    ]

    ordered = order_pdfs_for_sending(pdfs)
    names = [x["filename"] for x in ordered]

    assert names[0] == "CL_NEW-CLO_MEN_RUSH_WHITE_S-1.pdf"
    assert names[1] == "CL_NEW-CLO_MEN_TAICI_BLACK_M-1.pdf"
    assert names[2] == "CL_NEW-CLO_MEN_RUSH-PRO_BLACK_M-1.pdf"
