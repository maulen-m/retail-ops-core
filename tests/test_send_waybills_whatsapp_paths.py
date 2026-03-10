from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.send_waybills_whatsapp import (
    MERGED_SEND_ROOT_NAME,
    SOURCE_MERGED,
    WhatsAppSender,
    _normalize_chat_key,
    _recover_missing_pdf_path,
    collect_store_order_bundle_stats,
    collect_all_pdfs,
    find_store_folders,
    format_post_send_status_table,
    format_pre_send_status_table,
    order_pdfs_for_sending,
    resolve_send_root,
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
    merged_store = today_root / "MERGED" / MERGED_SEND_ROOT_NAME / "28.02.26_MERGED_qnt1"
    _write_store_fixture(merged_store, "merged_only.pdf")

    folders = find_store_folders(today_root, source_mode=SOURCE_MERGED)
    pdfs = collect_all_pdfs(today_root, source_mode=SOURCE_MERGED)

    assert len(folders) == 1
    assert folders[0] == merged_store
    assert len(pdfs) == 1
    assert pdfs[0]["filename"] == "merged_only.pdf"


def test_collect_all_pdfs_merged_mode_does_not_fallback_to_partitioned_merged_root(tmp_path: Path) -> None:
    today_root = tmp_path / "Today"
    merged_store = today_root / "MERGED" / "TODAY" / "28.02.26_MERGED_qnt1"
    _write_store_fixture(merged_store, "partitioned_only.pdf")

    resolved_root = resolve_send_root(today_root, source_mode=SOURCE_MERGED)
    folders = find_store_folders(today_root, source_mode=SOURCE_MERGED)
    pdfs = collect_all_pdfs(today_root, source_mode=SOURCE_MERGED)

    assert resolved_root == today_root / "MERGED" / MERGED_SEND_ROOT_NAME
    assert folders == []
    assert pdfs == []


def test_collect_all_pdfs_prefers_merged_send_root_when_present(tmp_path: Path) -> None:
    today_root = tmp_path / "Today"
    merged_store = today_root / "MERGED" / "TODAY" / "28.02.26_MERGED_qnt1"
    send_store = today_root / "MERGED" / MERGED_SEND_ROOT_NAME / "28.02.26_MERGED_qnt1"
    _write_store_fixture(merged_store, "partitioned.pdf")
    _write_store_fixture(send_store, "send_ready.pdf")

    resolved_root = resolve_send_root(today_root, source_mode=SOURCE_MERGED)
    folders = find_store_folders(today_root, source_mode=SOURCE_MERGED)
    pdfs = collect_all_pdfs(today_root, source_mode=SOURCE_MERGED)

    assert resolved_root == today_root / "MERGED" / MERGED_SEND_ROOT_NAME
    assert folders == [send_store]
    assert [pdf["filename"] for pdf in pdfs] == ["send_ready.pdf"]
    assert pdfs[0]["batch_label"] == "28.02.26_MERGED_qnt1"


def test_collect_all_pdfs_recurses_nested_category_folders(tmp_path: Path) -> None:
    today_root = tmp_path / "Today"
    merged_store = today_root / "MERGED" / MERGED_SEND_ROOT_NAME / "28.02.26_MERGED_qnt2"
    _write_store_fixture(merged_store, "top_level.pdf")

    nested_pdf = merged_store / "NORMAL_singles" / "New Folder With Items" / "nested.pdf"
    nested_pdf.parent.mkdir(parents=True, exist_ok=True)
    nested_pdf.write_bytes(b"%PDF-1.0\n")

    pdfs = collect_all_pdfs(today_root, source_mode=SOURCE_MERGED)
    names = sorted(x["filename"] for x in pdfs)

    assert names == ["nested.pdf", "top_level.pdf"]
    assert all(x["relative"].startswith(f"MERGED/{MERGED_SEND_ROOT_NAME}/") for x in pdfs)


def test_recover_missing_pdf_path_finds_moved_file_with_same_name(tmp_path: Path) -> None:
    today_root = tmp_path / "Today"
    store = today_root / "MERGED" / "TODAY" / "01.03.26_MERGED_qnt1"
    category = store / "NORMAL_singles"
    category.mkdir(parents=True, exist_ok=True)

    old_path = category / "Sample_L-1.pdf"
    moved_path = category / "New Folder With Items" / "Sample_L-1.pdf"
    moved_path.parent.mkdir(parents=True, exist_ok=True)
    moved_path.write_bytes(b"%PDF-1.0\n")

    entry = {
        "path": old_path,
        "store": "01.03.26_MERGED_qnt1",
        "category": "NORMAL_singles",
        "filename": "Sample_L-1.pdf",
        "relative": "MERGED/TODAY/01.03.26_MERGED_qnt1/NORMAL_singles/Sample_L-1.pdf",
    }

    recovered = _recover_missing_pdf_path(entry, today_root)
    assert recovered == moved_path
    assert entry["path"] == moved_path
    assert "New Folder With Items" in entry["relative"]


def test_collect_all_pdfs_reads_sku_key_from_manifest_output_mapping(tmp_path: Path) -> None:
    today_root = tmp_path / "Today"
    store = today_root / "TODAY" / "28.02.26_Universal_qnt1"
    store.mkdir(parents=True, exist_ok=True)
    (store / "manifest_normal_singles.csv").write_text(
        "type,store,order_id,sku_key,sku_id,output\n"
        "NORMAL,Universal,100,LINE52_BLACK,LINE52_BLACK_XL,NORMAL_singles/Принт_5в1_черный_XL-1.pdf\n",
        encoding="utf-8",
    )
    pdf_path = store / "NORMAL_singles" / "Принт_5в1_черный_XL-1.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.0\n")

    pdfs = collect_all_pdfs(today_root)

    assert len(pdfs) == 1
    assert pdfs[0]["sku_key"] == "LINE52_BLACK"
    assert pdfs[0]["sku_id"] == "LINE52_BLACK_XL"


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


def test_ordering_keeps_sku_block_contiguous_with_rising_sizes() -> None:
    pdfs = [
        {
            "filename": "CL_NEW-CLO_MEN_RUSH_WHITE_S-1.pdf",
            "category": "NORMAL_singles",
            "family_key": "RUSH",
            "sku_key": "LINE52_BLACK",
            "size_rank": 10,
        },
        {
            "filename": "CL_NEW-CLO_MEN_RUSH-PRO_BLACK_M-1.pdf",
            "category": "NORMAL_singles",
            "family_key": "RUSH",
            "sku_key": "LINE52_BLACK",
            "size_rank": 11,
        },
        {
            "filename": "CL_NEW-CLO_MEN_TAICI_BLACK_M-1.pdf",
            "category": "NORMAL_singles",
            "family_key": "TAICI",
            "sku_key": "TAICI_BLACK",
            "size_rank": 11,
        },
    ]

    ordered = order_pdfs_for_sending(pdfs)
    names = [x["filename"] for x in ordered]

    assert names[0] == "CL_NEW-CLO_MEN_RUSH_WHITE_S-1.pdf"
    assert names[1] == "CL_NEW-CLO_MEN_RUSH-PRO_BLACK_M-1.pdf"
    assert names[2] == "CL_NEW-CLO_MEN_TAICI_BLACK_M-1.pdf"


def test_ordering_uses_sku_key_not_family_for_grouping() -> None:
    pdfs = [
        {
            "filename": "Rush_white_S-1.pdf",
            "category": "NORMAL_singles",
            "family_key": "RUSH",
            "sku_key": "RUSH_WHITE",
            "size_rank": 10,
        },
        {
            "filename": "Tshirt_black_M-1.pdf",
            "category": "NORMAL_singles",
            "family_key": "RUSH",
            "sku_key": "RUSH_BLACK",
            "size_rank": 11,
        },
        {
            "filename": "Taici_black_M-1.pdf",
            "category": "NORMAL_singles",
            "family_key": "TAICI",
            "sku_key": "RUSH_WHITE",
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


def test_ordering_sends_multi_bundles_before_normal_singles() -> None:
    pdfs = [
        {
            "filename": "normal_singles.pdf",
            "category": "NORMAL_singles",
            "family_key": "NORMAL",
            "sku_key": "NORMAL_SKU",
            "size_rank": 10,
        },
        {
            "filename": "multi_qty.pdf",
            "category": "SPECIAL_multi_qty",
            "family_key": "MQTY",
            "sku_key": "MQTY_SKU",
            "size_rank": 10,
        },
        {
            "filename": "multi_line.pdf",
            "category": "SPECIAL_multi_line",
            "family_key": "MLINE",
            "sku_key": "MLINE_SKU",
            "size_rank": 10,
        },
    ]

    ordered = order_pdfs_for_sending(pdfs)
    assert [x["filename"] for x in ordered] == [
        "multi_line.pdf",
        "multi_qty.pdf",
        "normal_singles.pdf",
    ]


def test_ordering_treats_category_aliases_as_multi_priority() -> None:
    pdfs = [
        {
            "filename": "normal.pdf",
            "category": "NORMAL_singles",
            "family_key": "NORMAL",
            "sku_key": "NORMAL_SKU",
            "size_rank": 10,
        },
        {
            "filename": "alias_mqty.pdf",
            "category": "special-multi-qty",
            "family_key": "MQTY",
            "sku_key": "MQTY_SKU",
            "size_rank": 10,
        },
    ]

    ordered = order_pdfs_for_sending(pdfs)
    assert [x["filename"] for x in ordered] == ["alias_mqty.pdf", "normal.pdf"]


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


class _AlwaysDetachedTarget:
    def click(self, timeout=1500, force=False):
        raise RuntimeError("detached")

    def evaluate(self, _script):
        raise RuntimeError("locator evaluate timeout")


class _FakeLocator:
    def __init__(self, target=None):
        self._target = target

    def count(self):
        return 1 if self._target is not None else 0

    @property
    def first(self):
        return self if self._target is None else self._target


class _FakePage:
    def __init__(self, selectors=None, *, js_clickable=None):
        self._selectors = selectors or {}
        self._js_clickable = set(js_clickable or [])
        self.wait_calls = []
        self.js_clicks = []

    def locator(self, selector):
        return self._selectors.get(selector, _FakeLocator())

    def wait_for_timeout(self, ms):
        self.wait_calls.append(ms)

    def evaluate(self, script, selector=None):
        if "document.querySelector" in script:
            if selector in self._js_clickable:
                self.js_clicks.append(selector)
                return True
            return False
        raise AssertionError(f"Unexpected evaluate call: {script!r}")


class _ReadyLocator:
    def __init__(self, target=None):
        self._target = target

    def count(self):
        return 1 if self._target is not None else 0

    @property
    def first(self):
        return self

    def wait_for(self, timeout=None):
        if self._target is None:
            raise RuntimeError("missing target")
        if hasattr(self._target, "wait_for"):
            return self._target.wait_for(timeout=timeout)
        return None

    def click(self, timeout=None, force=False):
        if self._target is None:
            raise RuntimeError("missing target")
        return self._target.click(timeout=timeout, force=force)

    def fill(self, value):
        if self._target is None:
            raise RuntimeError("missing target")
        return self._target.fill(value)

    def locator(self, _selector, **_kwargs):
        return _ReadyLocator()

    def get_by_text(self, *_args, **_kwargs):
        return _ReadyLocator()


class _SearchTarget:
    def __init__(self):
        self.actions = []

    def wait_for(self, timeout=None):
        self.actions.append(("wait_for", timeout))

    def click(self, timeout=None, force=False):
        self.actions.append(("click", timeout, force))

    def fill(self, value):
        self.actions.append(("fill", value))


class _SidebarReadyPage:
    def __init__(self, selectors=None):
        self._selectors = selectors or {}
        self.wait_calls = []

    def locator(self, selector):
        return self._selectors.get(selector, _ReadyLocator())

    def get_by_text(self, *_args, **_kwargs):
        return _ReadyLocator()

    def wait_for_timeout(self, ms):
        self.wait_calls.append(ms)


def test_safe_click_selectors_uses_page_level_js_fallback() -> None:
    selector = "button[aria-label='Attach']"
    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp"),
        profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
    )
    fake_page = _FakePage(
        selectors={selector: _FakeLocator(_AlwaysDetachedTarget())},
        js_clickable={selector},
    )
    sender._ctx = SimpleNamespace(page=fake_page)

    sender._safe_click_selectors([selector], "attach button", timeout_ms=500)

    assert fake_page.js_clicks == [selector]


def test_wait_for_chat_list_ready_accepts_alternative_sidebar_search_selector() -> None:
    chat_list_target = _SearchTarget()
    sidebar_search_target = _SearchTarget()
    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp"),
        profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
    )
    sender._ctx = SimpleNamespace(
        page=_SidebarReadyPage(
            selectors={
                "div[aria-label='Chat list']": _ReadyLocator(chat_list_target),
                "div[contenteditable='true'][role='textbox'][data-tab='3']": _ReadyLocator(sidebar_search_target),
            }
        )
    )

    sender._wait_for_chat_list_ready()

    assert any(action[0] == "wait_for" for action in chat_list_target.actions)
    assert any(action[0] == "wait_for" for action in sidebar_search_target.actions)


def test_open_chat_uses_alternative_sidebar_search_selector(monkeypatch: pytest.MonkeyPatch) -> None:
    search_target = _SearchTarget()
    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp"),
        profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
    )
    sender._ctx = SimpleNamespace(
        page=_SidebarReadyPage(
            selectors={
                "div[aria-label='Chat list']": _ReadyLocator(_SearchTarget()),
                "div[contenteditable='true'][role='textbox'][data-tab='3']": _ReadyLocator(search_target),
            }
        )
    )
    click_calls = {"count": 0}

    def _fake_try_click(_candidates, timeout_ms=3500):
        click_calls["count"] += 1
        return click_calls["count"] > 1

    monkeypatch.setattr(sender, "_try_click_candidate", _fake_try_click)
    monkeypatch.setattr(sender, "_assert_active_target_chat", lambda: None)
    monkeypatch.setattr(sender, "_resolve_composer", lambda *args, **kwargs: None)
    monkeypatch.setattr(sender, "_active_chat_title", lambda: "")

    sender.open_chat("Заказы")

    assert click_calls["count"] == 2
    assert ("fill", "") in search_target.actions
    assert ("fill", "Заказы") in search_target.actions


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

    stats = collect_store_order_bundle_stats(
        [store],
        order_store_map={"1": "UNIVERSAL", "2": "UNIVERSAL", "3": "UNIVERSAL"},
    )

    assert stats["Universal"]["orders_target"] == 3
    assert stats["Universal"]["orders_ready"] == 3


def test_collect_store_order_bundle_stats_maps_merged_rows_by_order_store_map(tmp_path: Path) -> None:
    root = tmp_path / "merged"
    store = root / "TODAY" / "01.03.26_MERGED_qnt2"
    store.mkdir(parents=True, exist_ok=True)
    (store / "manifest_normal_singles.csv").write_text(
        "type,store,order_id,output\n"
        "NORMAL,MERGED,1001;1002,NORMAL_singles/a.pdf\n"
        "NORMAL,MERGED,2001,NORMAL_singles/b.pdf\n",
        encoding="utf-8",
    )

    stats = collect_store_order_bundle_stats(
        [store],
        order_store_map={
            "1001": "UNIVERSAL",
            "1002": "ACMEWEAR",
            "2001": "STOREB",
            "9999": "MELVIS",
        },
    )

    assert stats["Universal"]["orders_ready"] == 1
    assert stats["AcmeWear"]["orders_ready"] == 1
    assert stats["STORE-B"]["orders_ready"] == 1
    assert stats["Store-C"]["orders_target"] == 1


def test_pre_and_post_status_table_contains_totals() -> None:
    stats = {
        "STORE-B": {"orders_target": 51, "orders_ready": 44},
        "AcmeWear": {"orders_target": 5, "orders_ready": 4},
        "Universal": {"orders_target": 45, "orders_ready": 32},
    }

    pre = format_pre_send_status_table(stats, bundles_target=40)
    post = format_post_send_status_table(
        stats,
        {"STORE-B": 44, "AcmeWear": 4, "Universal": 32},
        bundles_target=40,
        bundles_sent=40,
    )

    assert "STORE" in pre and "Orders Target" in pre and "TOTAL" in pre
    assert "Orders Sent" in post and "Bundles: target=40, sent=40" in post
    assert "| TOTAL" in post
