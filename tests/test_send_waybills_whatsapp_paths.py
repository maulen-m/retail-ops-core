from pathlib import Path

import pytest

from scripts.send_waybills_whatsapp import (
    RISK_DIVERSIFIER,
    RISK_HIGH_SIMILAR,
    SOURCE_MERGED,
    WhatsAppSender,
    _normalize_chat_key,
    collect_store_order_bundle_stats,
    collect_all_pdfs,
    find_store_folders,
    format_post_send_status_table,
    format_pre_send_status_table,
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


def test_collect_all_pdfs_recurses_nested_category_folders(tmp_path: Path) -> None:
    today_root = tmp_path / "Today"
    merged_store = today_root / "MERGED" / "TODAY" / "28.02.26_MERGED_qnt2"
    _write_store_fixture(merged_store, "top_level.pdf")

    nested_pdf = merged_store / "NORMAL_singles" / "New Folder With Items" / "nested.pdf"
    nested_pdf.parent.mkdir(parents=True, exist_ok=True)
    nested_pdf.write_bytes(b"%PDF-1.0\n")

    pdfs = collect_all_pdfs(today_root, source_mode=SOURCE_MERGED)
    names = sorted(x["filename"] for x in pdfs)

    assert names == ["nested.pdf", "top_level.pdf"]
    assert all(x["relative"].startswith("MERGED/") for x in pdfs)


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


def test_ordering_splits_high_similarity_when_diversifier_exists() -> None:
    pdfs = [
        {
            "filename": "Rush_white_S-1.pdf",
            "category": "NORMAL_singles",
            "family_key": "RUSH_WHITE",
            "risk_group": RISK_HIGH_SIMILAR,
            "size_rank": 10,
        },
        {
            "filename": "Tshirt_black_M-1.pdf",
            "category": "NORMAL_singles",
            "family_key": "TSHIRT_BLACK",
            "risk_group": RISK_HIGH_SIMILAR,
            "size_rank": 11,
        },
        {
            "filename": "Taici_black_M-1.pdf",
            "category": "NORMAL_singles",
            "family_key": "TAICI",
            "risk_group": RISK_DIVERSIFIER,
            "size_rank": 11,
        },
    ]

    ordered = order_pdfs_for_sending(pdfs)
    names = [x["filename"] for x in ordered]
    assert names == [
        "Rush_white_S-1.pdf",
        "Taici_black_M-1.pdf",
        "Tshirt_black_M-1.pdf",
    ]


def test_ordering_allows_high_similarity_neighbors_if_no_diversifier_left() -> None:
    pdfs = [
        {
            "filename": "Rush_white_S-1.pdf",
            "category": "NORMAL_singles",
            "family_key": "RUSH_WHITE",
            "risk_group": RISK_HIGH_SIMILAR,
            "size_rank": 10,
        },
        {
            "filename": "Tshirt_black_M-1.pdf",
            "category": "NORMAL_singles",
            "family_key": "TSHIRT_BLACK",
            "risk_group": RISK_HIGH_SIMILAR,
            "size_rank": 11,
        },
    ]

    ordered = order_pdfs_for_sending(pdfs)
    assert [x["filename"] for x in ordered] == [
        "Rush_white_S-1.pdf",
        "Tshirt_black_M-1.pdf",
    ]


def test_ordering_kids_sizes_before_adult_sizes() -> None:
    pdfs = [
        {
            "filename": "KidSuit_S-1.pdf",
            "category": "NORMAL_singles",
            "family_key": "KIDSUIT",
            "size_rank": 10,
        },
        {
            "filename": "KidSuit_30-1.pdf",
            "category": "NORMAL_singles",
            "family_key": "KIDSUIT",
            "size_rank": 5,
        },
        {
            "filename": "KidSuit_24-1.pdf",
            "category": "NORMAL_singles",
            "family_key": "KIDSUIT",
            "size_rank": 2,
        },
    ]

    ordered = order_pdfs_for_sending(pdfs)

    assert [x["filename"] for x in ordered] == [
        "KidSuit_24-1.pdf",
        "KidSuit_30-1.pdf",
        "KidSuit_S-1.pdf",
    ]


def test_normalize_chat_key_trims_and_casefolds() -> None:
    assert _normalize_chat_key("  Заказы  ") == _normalize_chat_key("заказы")


def test_sender_blocks_forbidden_target_chat_without_launching() -> None:
    with pytest.raises(ValueError, match="blocked"):
        WhatsAppSender(
            chat_title="order 2",
            user_data_dir=Path("/tmp"),
            profile_directory="Profile 2",
            blocked_chat_titles=["order 2"],
        )


def test_collect_store_order_bundle_stats_counts_unique_orders(tmp_path: Path) -> None:
    root = tmp_path / "stats"
    store = root / "TODAY" / "28.02.26_Universal_qnt3"
    store.mkdir(parents=True, exist_ok=True)
    (store / "manifest_normal_singles.csv").write_text(
        "type,store,order_id,output\n"
        "NORMAL,Universal,1,NORMAL_singles/a.pdf\n"
        "NORMAL,Universal,2;3,NORMAL_singles/b.pdf\n",
        encoding="utf-8",
    )
    (store / "manifest_special_multi_qty.csv").write_text(
        "type,store,order_id,output\n"
        "MULTI_QTY,Universal,3,SPECIAL_multi_qty/c.pdf\n",
        encoding="utf-8",
    )

    stats = collect_store_order_bundle_stats([store])

    assert stats["Universal"]["orders"] == 3
    assert stats["Universal"]["bundles_target"] == 3


def test_pre_and_post_status_table_contains_totals() -> None:
    stats = {
        "STORE-B": {"orders": 51, "bundles_target": 26},
        "AcmeWear": {"orders": 5, "bundles_target": 3},
        "Universal": {"orders": 45, "bundles_target": 20},
    }

    pre = format_pre_send_status_table(stats)
    post = format_post_send_status_table(
        stats,
        {"STORE-B": 26, "AcmeWear": 3, "Universal": 20},
    )

    assert "STORE" in pre and "Orders" in pre and "TOTAL" in pre
    assert "Bundles Target" in post and "Bundles Sent" in post
    assert "| TOTAL" in post
