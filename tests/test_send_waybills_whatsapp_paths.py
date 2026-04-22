import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.send_waybills_whatsapp import (
    DEFAULT_CDP_ENDPOINT,
    DEFAULT_CDP_ENDPOINT_IPV6,
    MERGED_SEND_ROOT_NAME,
    SOURCE_MERGED,
    WhatsAppSender,
    _candidate_cdp_endpoints,
    _copy_profile_to_temp,
    capture_sender_failure_diagnostics,
    _normalize_chat_key,
    _resolve_live_cdp_endpoint,
    load_send_batch_manifest,
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


def test_candidate_cdp_endpoints_include_ipv6_fallback_for_default_ipv4() -> None:
    candidates = _candidate_cdp_endpoints(DEFAULT_CDP_ENDPOINT)
    assert candidates[0] == DEFAULT_CDP_ENDPOINT
    assert DEFAULT_CDP_ENDPOINT_IPV6 in candidates


def test_resolve_live_cdp_endpoint_falls_back_to_ipv6_when_ipv4_probe_is_dead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def _fake_fetch_once(endpoint: str, path: str):
        calls.append((endpoint, path))
        if endpoint == DEFAULT_CDP_ENDPOINT:
            raise RuntimeError("ipv4 endpoint unavailable")
        assert endpoint == DEFAULT_CDP_ENDPOINT_IPV6
        assert path == "/json/version"
        return {"webSocketDebuggerUrl": "ws://[::1]:9222/devtools/browser/demo"}

    monkeypatch.setattr("scripts.send_waybills_whatsapp._fetch_cdp_json_once", _fake_fetch_once)

    resolved = _resolve_live_cdp_endpoint(DEFAULT_CDP_ENDPOINT)

    assert resolved == DEFAULT_CDP_ENDPOINT_IPV6
    assert calls == [
        (DEFAULT_CDP_ENDPOINT, "/json/version"),
        (DEFAULT_CDP_ENDPOINT_IPV6, "/json/version"),
    ]


def test_copy_profile_to_temp_preserves_service_worker_state(tmp_path: Path) -> None:
    user_data_dir = tmp_path / "Chrome"
    profile = "Profile 2"
    profile_dir = user_data_dir / profile
    (profile_dir / "Service Worker" / "Database").mkdir(parents=True, exist_ok=True)
    (profile_dir / "Service Worker" / "Database" / "state.txt").write_text("ok", encoding="utf-8")
    (profile_dir / "Cache").mkdir(parents=True, exist_ok=True)
    (profile_dir / "Cache" / "cache.bin").write_text("skip", encoding="utf-8")
    (user_data_dir / "Local State").write_text("{}", encoding="utf-8")

    tmp_profile = _copy_profile_to_temp(user_data_dir, profile)
    try:
        assert (tmp_profile / profile / "Service Worker" / "Database" / "state.txt").read_text(encoding="utf-8") == "ok"
        assert not (tmp_profile / profile / "Cache").exists()
        assert (tmp_profile / "Local State").exists()
    finally:
        import shutil
        shutil.rmtree(tmp_profile, ignore_errors=True)


def test_copy_profile_to_temp_removes_singleton_locks(tmp_path: Path) -> None:
    user_data_dir = tmp_path / "Chrome"
    profile = "Profile 2"
    profile_dir = user_data_dir / profile
    profile_dir.mkdir(parents=True, exist_ok=True)
    (user_data_dir / "Local State").write_text("{}", encoding="utf-8")
    for root in (user_data_dir, profile_dir):
        for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
            (root / name).write_text("lock", encoding="utf-8")

    tmp_profile = _copy_profile_to_temp(user_data_dir, profile)
    try:
        for root in (tmp_profile, tmp_profile / profile):
            for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
                assert not (root / name).exists()
    finally:
        import shutil
        shutil.rmtree(tmp_profile, ignore_errors=True)


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


def test_load_send_batch_manifest_recovers_moved_pdf_path(tmp_path: Path) -> None:
    today_root = tmp_path / "Today"
    batch_root = today_root / "MERGED" / "SEND" / "11.03.26_MERGED_qnt2"
    moved_pdf = batch_root / "SPECIAL_multi_qty" / "New Folder With Items" / "Местовая-2)_Трусы_черные-2XL-2.pdf"
    moved_pdf.parent.mkdir(parents=True, exist_ok=True)
    moved_pdf.write_bytes(b"%PDF-1.0\n")
    (batch_root / "send_batch_manifest.json").write_text(
        '{"entries": ['
        '{"pdf_key": "k1", "filename": "Местовая-2)_Трусы_черные-2XL-2.pdf", '
        '"relative_output_path": "SPECIAL_multi_qty/Местовая-2)_Трусы_черные-2XL-2.pdf", '
        '"category": "SPECIAL_multi_qty", "store": "11.03.26_MERGED_qnt2"}'
        '] }',
        encoding="utf-8",
    )

    manifest = load_send_batch_manifest(today_root, source_mode=SOURCE_MERGED)

    assert manifest["entries"][0]["path"] == moved_pdf


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


def test_sender_start_uses_dedicated_new_page_instead_of_profile_picker_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp/chrome"),
        profile_name="",
        profile_directory="Profile 2",
        browser_mode="launch-temp",
        blocked_chat_titles=["order 2"],
    )

    class _FakePage:
        def __init__(self, name: str):
            self.name = name
            self.default_timeout = None
            self.goto_calls = []

        def set_default_timeout(self, timeout: int) -> None:
            self.default_timeout = timeout

        def goto(self, url: str, wait_until: str | None = None) -> None:
            self.goto_calls.append((url, wait_until))

    class _FakeContext:
        def __init__(self):
            self.pages = [_FakePage("profile_picker")]
            self.created = _FakePage("dedicated_whatsapp")
            self.closed = False

        def new_page(self):
            return self.created

        def close(self) -> None:
            self.closed = True

    class _FakePlaywrightInstance:
        def __init__(self):
            self.context = _FakeContext()
            self.launch_kwargs = None
            self.chromium = SimpleNamespace(
                launch_persistent_context=self._launch_persistent_context
            )
            self.stopped = False

        def _launch_persistent_context(self, **kwargs):
            self.launch_kwargs = kwargs
            return self.context

        def stop(self) -> None:
            self.stopped = True

    class _FakeSyncPlaywright:
        def __init__(self, instance):
            self.instance = instance

        def start(self):
            return self.instance

    fake_playwright = _FakePlaywrightInstance()

    monkeypatch.setattr(
        "playwright.sync_api.sync_playwright",
        lambda: _FakeSyncPlaywright(fake_playwright),
    )
    monkeypatch.setattr(
        "scripts.send_waybills_whatsapp._copy_profile_to_temp",
        lambda user_data_dir, profile_directory, verbose=False: Path("/tmp/fake-whatsapp-profile"),
    )
    monkeypatch.setattr(sender, "_assert_session_ready", lambda *args, **kwargs: None)
    monkeypatch.setattr(sender, "_wait_for_chat_list_ready", lambda: None)
    monkeypatch.setattr(sender, "open_chat", lambda title: None)

    sender.start()
    try:
        assert sender.page is fake_playwright.context.created
        assert fake_playwright.context.created.goto_calls == [
            ("https://web.whatsapp.com", "domcontentloaded")
        ]
        assert fake_playwright.context.pages[0].goto_calls == []
        assert fake_playwright.launch_kwargs["no_viewport"] is True
        assert "--start-maximized" in fake_playwright.launch_kwargs["args"]
    finally:
        sender.close()


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


def test_ordering_prefers_manifest_send_sequence_when_present() -> None:
    pdfs = [
        {
            "filename": "Nike_Футболка_белая_XL-1.pdf",
            "category": "NORMAL_singles",
            "family_key": "NIKE_ФУТБОЛКА",
            "sku_key": "NIKE_TEE_WHITE",
            "size_rank": 13,
            "send_sequence": 4,
        },
        {
            "filename": "Line51_L-1.pdf",
            "category": "NORMAL_singles",
            "family_key": "LINE51",
            "sku_key": "LINE51",
            "size_rank": 12,
            "send_sequence": 3,
        },
        {
            "filename": "Nike_Футболка_черная_2XL-1.pdf",
            "category": "NORMAL_singles",
            "family_key": "NIKE_ФУТБОЛКА",
            "sku_key": "NIKE_TEE_BLACK",
            "size_rank": 14,
            "send_sequence": 2,
        },
        {
            "filename": "Nike_Футболка_черная_XL-1.pdf",
            "category": "NORMAL_singles",
            "family_key": "NIKE_ФУТБОЛКА",
            "sku_key": "NIKE_TEE_BLACK",
            "size_rank": 13,
            "send_sequence": 1,
        },
    ]

    ordered = order_pdfs_for_sending(pdfs)

    assert [x["filename"] for x in ordered] == [
        "Nike_Футболка_черная_XL-1.pdf",
        "Nike_Футболка_черная_2XL-1.pdf",
        "Line51_L-1.pdf",
        "Nike_Футболка_белая_XL-1.pdf",
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

    def set_input_files(self, value, timeout=None):
        if self._target is None:
            raise RuntimeError("missing target")
        return self._target.set_input_files(value, timeout=timeout)

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


class _SessionBlockerLocator:
    def __init__(self, count: int):
        self._count = count

    def count(self):
        return self._count


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


def test_choose_file_via_document_menu_uses_hidden_document_input_when_present(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.0\n")

    class _FileInputTarget:
        def __init__(self) -> None:
            self.paths = []

        def set_input_files(self, value, timeout=None) -> None:
            self.paths.append((value, timeout))

    class _FileInputPage:
        def __init__(self, target) -> None:
            self._target = target
            self.expect_file_chooser_calls = 0

        def locator(self, selector):
            if selector.startswith("input[type='file']"):
                return _ReadyLocator(self._target)
            return _ReadyLocator()

        def expect_file_chooser(self, timeout=7000):
            self.expect_file_chooser_calls += 1
            raise AssertionError("document chooser fallback should not be needed")

        def wait_for_timeout(self, _ms):
            return None

    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp"),
        profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
    )
    target = _FileInputTarget()
    page = _FileInputPage(target)
    sender._ctx = SimpleNamespace(page=page)

    sender._choose_file_via_document_menu(pdf_path)

    assert [item[0] for item in target.paths] == [str(pdf_path)]
    assert page.expect_file_chooser_calls == 0


def test_choose_file_via_document_menu_tries_button_document_selector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.0\n")

    class _FakeChooser:
        def __init__(self) -> None:
            self.paths = []

        def set_files(self, value: str) -> None:
            self.paths.append(value)

    class _ExpectChooser:
        def __init__(self, chooser) -> None:
            self.value = chooser

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _MenuPage:
        def __init__(self, chooser) -> None:
            self._chooser = chooser

        def locator(self, _selector):
            return _ReadyLocator()

        def expect_file_chooser(self, timeout=7000):
            return _ExpectChooser(self._chooser)

        def wait_for_timeout(self, _ms):
            return None

    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp"),
        profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
    )
    chooser = _FakeChooser()
    sender._ctx = SimpleNamespace(page=_MenuPage(chooser))
    captured = {}

    def _fake_safe_click_selectors(selectors, label, timeout_ms=None):
        captured["selectors"] = list(selectors)
        captured["label"] = label
        captured["timeout_ms"] = timeout_ms

    monkeypatch.setattr(sender, "_safe_click_selectors", _fake_safe_click_selectors)

    sender._choose_file_via_document_menu(pdf_path)

    assert "button[aria-label='Document']" in captured["selectors"]
    assert "button[aria-label='Документ']" in captured["selectors"]
    assert chooser.paths == [str(pdf_path)]


def test_capture_sender_failure_diagnostics_writes_artifacts(tmp_path: Path) -> None:
    class _DiagPage:
        url = "https://web.whatsapp.com/"

        def screenshot(self, path: str, full_page: bool = True) -> None:
            Path(path).write_bytes(b"PNG")

        def content(self) -> str:
            return "<html><body>diag</body></html>"

        def evaluate(self, script: str):
            assert "document.title" in script
            return {
                "document_title": "WhatsApp",
                "active_chat_title": "Заказы",
                "chat_home_visible": False,
                "chat_list_visible": True,
                "composer_visible": True,
                "attach_button_visible": True,
                "document_controls_visible": True,
            }

    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp"),
        profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
    )
    sender._ctx = SimpleNamespace(page=_DiagPage())

    result = capture_sender_failure_diagnostics(
        sender,
        today_folder=tmp_path,
        failure_code="FAILED",
        batch_root=tmp_path / "batch",
        manifest_path=tmp_path / "batch" / "send_batch_manifest.json",
        pdf_filename="sample.pdf",
        detail="document menu item missing",
    )

    diag_dir = Path(result["diagnostics_dir"])
    assert diag_dir.exists()
    assert (diag_dir / "page.png").exists()
    assert (diag_dir / "page.html").read_text(encoding="utf-8") == "<html><body>diag</body></html>"
    summary = json.loads((diag_dir / "dom_summary.json").read_text(encoding="utf-8"))
    assert summary["active_chat_title"] == "Заказы"
    assert summary["document_controls_visible"] is True
    assert result["recovery_ladder"][0]["code"] == "playwright_retry"


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


def test_open_chat_retries_visible_candidates_when_sidebar_search_is_absent(monkeypatch: pytest.MonkeyPatch) -> None:
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
            }
        )
    )
    click_calls = {"count": 0}

    def _fake_try_click(_candidates, timeout_ms=3500):
        click_calls["count"] += 1
        return click_calls["count"] >= 2

    monkeypatch.setattr(sender, "_try_click_candidate", _fake_try_click)
    monkeypatch.setattr(sender, "_assert_active_target_chat", lambda: None)
    monkeypatch.setattr(sender, "_resolve_composer", lambda *args, **kwargs: None)
    monkeypatch.setattr(sender, "_active_chat_title", lambda: "")

    sender.open_chat("Заказы")

    assert click_calls["count"] == 2


def test_prepare_document_recovers_target_chat_when_active_chat_is_temporarily_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.0\n")

    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp"),
        profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
    )
    sender._ctx = SimpleNamespace(
        page=SimpleNamespace(
            wait_for_timeout=lambda _ms: None,
        )
    )

    state = {"ready": False}
    recovery_calls = []

    def _fake_assert_active_target_chat() -> None:
        if not state["ready"]:
            raise RuntimeError("Could not determine active WhatsApp chat title")

    def _fake_wait_for_chat_list_ready() -> None:
        recovery_calls.append("wait")

    def _fake_open_chat(title: str) -> None:
        recovery_calls.append(("open", title))
        state["ready"] = True

    monkeypatch.setattr(sender, "_assert_active_target_chat", _fake_assert_active_target_chat)
    monkeypatch.setattr(sender, "_wait_for_chat_list_ready", _fake_wait_for_chat_list_ready)
    monkeypatch.setattr(sender, "open_chat", _fake_open_chat)
    monkeypatch.setattr(sender, "_resolve_composer", lambda *args, **kwargs: object())
    monkeypatch.setattr(sender, "_attach_button_available", lambda: True)
    monkeypatch.setattr(sender, "_safe_click_selectors", lambda *args, **kwargs: None)
    monkeypatch.setattr(sender, "_choose_file_via_document_menu", lambda *_args, **_kwargs: None)

    sender.prepare_document(pdf_path)

    assert recovery_calls == ["wait", ("open", "Заказы")]


def test_prepare_document_retries_full_attachment_flow_after_ui_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.0\n")

    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp"),
        profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
    )
    sender._ctx = SimpleNamespace(
        page=SimpleNamespace(
            wait_for_timeout=lambda _ms: None,
            keyboard=SimpleNamespace(press=lambda _key: None),
        )
    )

    attempts = {"attach": 0, "choose": 0}
    recovery_calls = []

    monkeypatch.setattr(sender, "_ensure_target_chat_ready", lambda *args, **kwargs: None)

    def _fake_safe_click_selectors(*_args, **_kwargs) -> None:
        attempts["attach"] += 1
        if attempts["attach"] == 1:
            raise RuntimeError("attach button detached")

    def _fake_choose_file_via_document_menu(_pdf_path: Path) -> None:
        attempts["choose"] += 1

    monkeypatch.setattr(sender, "_safe_click_selectors", _fake_safe_click_selectors)
    monkeypatch.setattr(sender, "_choose_file_via_document_menu", _fake_choose_file_via_document_menu)
    monkeypatch.setattr(
        sender,
        "_recover_target_chat_after_ui_drift",
        lambda: recovery_calls.append("recover"),
    )

    sender.prepare_document(pdf_path)

    assert attempts == {"attach": 2, "choose": 1}
    assert recovery_calls == ["recover"]


def test_prepare_document_retries_when_global_share_modal_opens(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.0\n")

    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp"),
        profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
    )
    sender._ctx = SimpleNamespace(
        page=SimpleNamespace(
            wait_for_timeout=lambda _ms: None,
        )
    )

    attempts = {"choose": 0}
    recovery_calls = []

    monkeypatch.setattr(sender, "_ensure_target_chat_ready", lambda *args, **kwargs: None)
    monkeypatch.setattr(sender, "_safe_click_selectors", lambda *args, **kwargs: None)

    def _fake_choose_file_via_document_menu(_pdf_path: Path) -> None:
        attempts["choose"] += 1

    monkeypatch.setattr(sender, "_choose_file_via_document_menu", _fake_choose_file_via_document_menu)
    monkeypatch.setattr(
        sender,
        "_global_share_modal_visible",
        lambda: attempts["choose"] == 1,
    )
    monkeypatch.setattr(
        sender,
        "_recover_target_chat_after_ui_drift",
        lambda: recovery_calls.append("recover"),
    )

    sender.prepare_document(pdf_path)

    assert attempts["choose"] == 2
    assert recovery_calls == ["recover"]


def test_recover_target_chat_after_ui_drift_dismisses_blocking_dialog_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp"),
        profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
    )
    sender._ctx = SimpleNamespace(
        page=SimpleNamespace(
            wait_for_timeout=lambda _ms: None,
        )
    )

    calls: list[object] = []
    monkeypatch.setattr(sender, "_dismiss_blocking_dialog_if_present", lambda: calls.append("dismiss") or True)
    monkeypatch.setattr(sender, "_assert_session_ready", lambda timeout_ms=None: calls.append(("session", timeout_ms)))
    monkeypatch.setattr(sender, "_wait_for_chat_list_ready", lambda: calls.append("wait"))
    monkeypatch.setattr(sender, "open_chat", lambda title: calls.append(("open", title)))
    monkeypatch.setattr(sender, "_clear_ui_invalidated", lambda: calls.append("clear"))

    sender._recover_target_chat_after_ui_drift()

    assert calls[0] == "dismiss"
    assert calls[-2] == ("open", "Заказы")
    assert calls[-1] == "clear"


def test_dismiss_blocking_dialog_handles_use_here_modal() -> None:
    class _ClickTarget:
        def __init__(self) -> None:
            self.clicks = []

        def click(self, timeout=None, force=False):
            self.clicks.append((timeout, force))

    target = _ClickTarget()
    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp"),
        profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
    )
    sender._ctx = SimpleNamespace(
        page=_FakePage(
            selectors={
                "div[role='dialog'][aria-modal='true']": _ReadyLocator(target),
                "div[role='dialog'][aria-modal='true'] button:has-text('Use here')": _ReadyLocator(target),
            }
        )
    )

    assert sender._dismiss_blocking_dialog_if_present() is True
    assert target.clicks == [(1500, True)]
    assert sender.page.wait_calls == [300]


def test_send_text_message_retries_when_composer_click_detaches_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp"),
        profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
    )

    class _FakeComposer:
        def __init__(self) -> None:
            self.clicks = 0

        def click(self) -> None:
            self.clicks += 1
            if self.clicks == 1:
                raise RuntimeError("element was detached from the DOM")

        def press(self, _key: str) -> None:
            return None

    keyboard_actions = []
    sender._ctx = SimpleNamespace(
        page=SimpleNamespace(
            keyboard=SimpleNamespace(
                insert_text=lambda text: keyboard_actions.append(("insert_text", text)),
                press=lambda key: keyboard_actions.append(("press", key)),
            ),
            wait_for_timeout=lambda _ms: None,
        )
    )
    composer = _FakeComposer()
    recovery_calls = []

    monkeypatch.setattr(sender, "_assert_active_target_chat", lambda: None)
    monkeypatch.setattr(sender, "_resolve_composer", lambda *args, **kwargs: composer)
    monkeypatch.setattr(sender, "_wait_for_text_message_bubble", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sender, "_wait_for_last_outgoing_settled", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sender, "_wait_for_chat_list_ready", lambda: recovery_calls.append("wait"))
    monkeypatch.setattr(sender, "open_chat", lambda title: recovery_calls.append(("open", title)))

    sender.send_text_message("hello")

    assert composer.clicks == 2
    assert recovery_calls == ["wait", ("open", "Заказы")]
    assert ("insert_text", "hello") in keyboard_actions


def test_send_text_message_recovers_when_reload_happens_after_enter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp"),
        profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
    )

    class _FakeComposer:
        def click(self) -> None:
            return None

        def press(self, _key: str) -> None:
            return None

    keyboard_actions = []
    sender._ctx = SimpleNamespace(
        page=SimpleNamespace(
            keyboard=SimpleNamespace(
                insert_text=lambda text: keyboard_actions.append(("insert_text", text)),
                press=lambda key: keyboard_actions.append(("press", key)),
            ),
            wait_for_timeout=lambda _ms: None,
        )
    )
    state = {"bubble_attempts": 0}
    recovery_calls = []

    monkeypatch.setattr(sender, "_assert_active_target_chat", lambda: None)
    monkeypatch.setattr(sender, "_resolve_composer", lambda *args, **kwargs: _FakeComposer())
    monkeypatch.setattr(sender, "_outgoing_message_count", lambda: 10)
    monkeypatch.setattr(sender, "_wait_for_new_outgoing_message", lambda *_args, **_kwargs: None)

    def _fake_wait_for_text_message_bubble(*_args, **_kwargs) -> None:
        state["bubble_attempts"] += 1
        if state["bubble_attempts"] == 1:
            sender._mark_ui_invalidated("main frame navigated to https://web.whatsapp.com/")
            raise RuntimeError("Page.wait_for_function: Timeout 45000ms exceeded.")

    monkeypatch.setattr(sender, "_wait_for_text_message_bubble", _fake_wait_for_text_message_bubble)
    monkeypatch.setattr(sender, "_wait_for_last_outgoing_settled", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sender, "_wait_for_chat_list_ready", lambda: recovery_calls.append("wait"))
    monkeypatch.setattr(sender, "open_chat", lambda title: recovery_calls.append(("open", title)))

    sender.send_text_message("probe hello")

    assert state["bubble_attempts"] == 2
    assert recovery_calls == ["wait", ("open", "Заказы")]
    assert keyboard_actions.count(("insert_text", "probe hello")) == 1


def test_send_text_message_waits_for_exact_text_before_settled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp"),
        profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
    )

    class _FakeComposer:
        def click(self) -> None:
            return None

        def press(self, _key: str) -> None:
            return None

    keyboard_actions = []
    sender._ctx = SimpleNamespace(
        page=SimpleNamespace(
            keyboard=SimpleNamespace(
                insert_text=lambda text: keyboard_actions.append(("insert_text", text)),
                press=lambda key: keyboard_actions.append(("press", key)),
            ),
            wait_for_timeout=lambda _ms: None,
        )
    )
    calls = []

    monkeypatch.setattr(sender, "_assert_active_target_chat", lambda: None)
    monkeypatch.setattr(sender, "_resolve_composer", lambda *args, **kwargs: _FakeComposer())
    monkeypatch.setattr(
        sender,
        "_wait_for_text_message_bubble",
        lambda text, timeout_ms: calls.append(("text", text, timeout_ms)),
    )
    monkeypatch.setattr(
        sender,
        "_wait_for_last_outgoing_settled",
        lambda timeout_ms: calls.append(("settled", timeout_ms)),
    )

    sender.send_text_message("line one\nline two")

    assert ("insert_text", "line one") in keyboard_actions
    assert ("insert_text", "line two") in keyboard_actions
    assert ("press", "Shift+Enter") in keyboard_actions
    assert ("press", "Enter") in keyboard_actions
    assert calls[0][0] == "text"
    assert calls[0][1] == "line one\nline two"
    assert calls[1][0] == "settled"


def test_wait_for_text_message_bubble_uses_normalized_text_payload() -> None:
    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp"),
        profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
    )

    calls = []
    sender._ctx = SimpleNamespace(
        page=SimpleNamespace(
            wait_for_function=lambda script, arg=None, timeout=None: calls.append(
                {"script": script, "arg": arg, "timeout": timeout}
            ),
            evaluate=lambda script, arg=None: {
                "present": True,
                "sent": True,
                "delivered": True,
                "delivery_state": "delivered",
                "icons": ["msg-dblcheck"],
                "aria_labels": ["Delivered"],
            },
        )
    )

    sender._wait_for_text_message_bubble("Pre-send status:\n  TOTAL   71  \n", timeout_ms=1234)

    assert len(calls) == 1
    assert "message-out" in calls[0]["script"]
    assert "normalized" in calls[0]["script"]
    assert calls[0]["arg"]["collapsed"] == "pre-send status: total 71"
    assert calls[0]["arg"]["lines"] == ["pre-send status:", "total 71"]
    assert calls[0]["timeout"] == 1234


def test_outgoing_message_count_captures_recent_snapshot() -> None:
    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp"),
        profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
    )
    sender._ctx = SimpleNamespace(
        page=SimpleNamespace(
            evaluate=lambda _script: {
                "count": 7,
                "tail": [
                    "pdf old-message.pdf 17:22",
                    "pdf sample.pdf 18:01",
                ],
            }
        )
    )

    count = sender._outgoing_message_count()

    assert count == 7
    assert sender._last_outgoing_snapshot == [
        "pdf old-message.pdf 17:22",
        "pdf sample.pdf 18:01",
    ]


def test_wait_for_document_bubble_uses_previous_outgoing_snapshot_payload() -> None:
    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp"),
        profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
    )
    sender._last_outgoing_snapshot = [
        "pdf sample.pdf 17:22",
        "pdf another.pdf 17:23",
    ]

    calls = []
    sender._ctx = SimpleNamespace(
        page=SimpleNamespace(
            wait_for_function=lambda script, arg=None, timeout=None: calls.append(
                {"script": script, "arg": arg, "timeout": timeout}
            ),
            evaluate=lambda script, arg=None: {
                "present": True,
                "sent": True,
                "delivered": True,
                "delivery_state": "delivered",
                "icons": ["msg-dblcheck"],
                "aria_labels": ["Delivered"],
            },
        )
    )

    sender._wait_for_document_bubble("sample.pdf", timeout_ms=1234)

    assert len(calls) == 1
    assert "payload.seen" in calls[0]["script"]
    assert calls[0]["arg"]["seen"] == sender._last_outgoing_snapshot
    assert calls[0]["timeout"] == 1234


def test_wait_for_document_bubble_settled_uses_previous_outgoing_snapshot_payload() -> None:
    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp"),
        profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
    )
    sender._last_outgoing_snapshot = [
        "pdf sample.pdf 17:22",
    ]

    calls = []
    sender._ctx = SimpleNamespace(
        page=SimpleNamespace(
            wait_for_function=lambda script, arg=None, timeout=None: calls.append(
                {"script": script, "arg": arg, "timeout": timeout}
            ),
            evaluate=lambda script, arg=None: {
                "present": True,
                "sent": True,
                "delivered": True,
                "delivery_state": "delivered",
                "icons": ["msg-dblcheck"],
                "aria_labels": ["Delivered"],
            },
        )
    )

    sender._wait_for_document_bubble_settled("sample.pdf", timeout_ms=2345)

    assert len(calls) == 1
    assert "payload.seen" in calls[0]["script"]
    assert calls[0]["arg"]["seen"] == sender._last_outgoing_snapshot
    assert calls[0]["timeout"] == 2345


def test_assert_session_ready_blocks_login_qr_state() -> None:
    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp"),
        profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
    )
    sender._ctx = SimpleNamespace(
        page=SimpleNamespace(
            locator=lambda selector: {
                "[data-testid='qrcode']": _SessionBlockerLocator(1),
                "canvas[aria-label*='QR']": _SessionBlockerLocator(0),
                "div[aria-label='Scan this QR code to link a device!']": _SessionBlockerLocator(0),
            }.get(selector, _SessionBlockerLocator(0))
        )
    )

    with pytest.raises(RuntimeError, match="QR"):
        sender._assert_session_ready()


def test_assert_active_target_chat_rejects_whatsapp_home_screen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp"),
        profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
    )
    sender._ctx = SimpleNamespace(
        page=SimpleNamespace(
            wait_for_timeout=lambda _ms: None,
        )
    )

    monkeypatch.setattr(sender, "_active_chat_title", lambda: "Заказы")
    monkeypatch.setattr(sender, "_chat_home_screen_visible", lambda: True)

    with pytest.raises(RuntimeError, match="home screen"):
        sender._assert_active_target_chat()


def test_assert_active_target_chat_rejects_identity_fingerprint_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp"),
        profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
    )
    sender.expected_chat_identity = {
        "chat_title": "Заказы",
        "selected_row_data_id": "chat-123",
    }
    sender._ctx = SimpleNamespace(
        page=SimpleNamespace(
            wait_for_timeout=lambda _ms: None,
        )
    )

    monkeypatch.setattr(sender, "_chat_home_screen_visible", lambda: False)
    monkeypatch.setattr(
        sender,
        "_active_chat_fingerprint",
        lambda: {
            "chat_title": "Заказы",
            "selected_row_data_id": "chat-999",
            "header_subtitle": "Adil, Employee",
        },
    )

    with pytest.raises(RuntimeError, match="identity fingerprint mismatch"):
        sender._assert_active_target_chat()


def test_assert_active_target_chat_ignores_header_subtitle_drift_without_strong_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp"),
        profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
    )
    sender.expected_chat_identity = {
        "chat_title": "Заказы",
        "header_subtitle": "Maulen, Рустик, You",
    }
    sender._ctx = SimpleNamespace(
        page=SimpleNamespace(
            wait_for_timeout=lambda _ms: None,
        )
    )

    monkeypatch.setattr(sender, "_chat_home_screen_visible", lambda: False)
    monkeypatch.setattr(
        sender,
        "_active_chat_fingerprint",
        lambda: {
            "chat_title": "Заказы",
            "header_subtitle": "Changed subtitle",
        },
    )

    sender._assert_active_target_chat()


def test_bind_active_chat_identity_if_missing_prefers_strong_fields_over_header_subtitle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp"),
        profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
        chat_identity_file=tmp_path / "identity.json",
    )
    monkeypatch.setattr(
        sender,
        "_active_chat_fingerprint",
        lambda: {
            "chat_title": "Заказы",
            "selected_row_data_id": "chat-row-123",
            "header_subtitle": "Maulen, Рустик, You",
        },
    )

    bound = sender.bind_active_chat_identity_if_missing()

    assert bound["chat_title"] == "Заказы"
    assert bound["selected_row_data_id"] == "chat-row-123"
    assert "header_subtitle" not in bound


def test_confirm_text_message_delivered_waits_for_delivery_marker() -> None:
    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp"),
        profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
    )

    wait_calls = []
    evaluate_calls = []
    sender._ctx = SimpleNamespace(
        page=SimpleNamespace(
            wait_for_function=lambda script, arg=None, timeout=None: wait_calls.append(
                {"script": script, "arg": arg, "timeout": timeout}
            ),
            evaluate=lambda script, arg=None: evaluate_calls.append(
                {"script": script, "arg": arg}
            )
            or {
                "present": True,
                "sent": True,
                "delivered": True,
                "delivery_state": "delivered",
                "icons": ["msg-dblcheck"],
                "aria_labels": ["Delivered"],
            },
        )
    )
    sender._assert_active_target_chat = lambda: None

    sender.confirm_text_message_delivered("Probe: 53 bundles ready", timeout_ms=4321)

    assert len(wait_calls) == 1
    assert "status-clock" in wait_calls[0]["script"]
    assert wait_calls[0]["arg"]["collapsed"] == "probe: 53 bundles ready"
    assert wait_calls[0]["timeout"] == 4321
    assert len(evaluate_calls) == 1
    assert "dblcheck" in evaluate_calls[0]["script"]
    assert "status-check" in evaluate_calls[0]["script"]


def test_confirm_text_message_sent_accepts_single_check_as_stable_group_send() -> None:
    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp"),
        profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
    )

    wait_calls = []
    evaluate_calls = []
    sender._ctx = SimpleNamespace(
        page=SimpleNamespace(
            wait_for_function=lambda script, arg=None, timeout=None: wait_calls.append(
                {"script": script, "arg": arg, "timeout": timeout}
            ),
            evaluate=lambda script, arg=None: evaluate_calls.append(
                {"script": script, "arg": arg}
            )
            or {
                "present": True,
                "sent": True,
                "delivered": False,
                "delivery_state": "sent",
                "icons": ["msg-check"],
                "aria_labels": ["Sent"],
            },
        )
    )
    sender._assert_active_target_chat = lambda: None

    status = sender.confirm_text_message_sent("Probe: 53 bundles ready", timeout_ms=4321)

    assert status["sent"] is True
    assert status["delivered"] is False
    assert status["delivery_state"] == "sent"
    assert len(wait_calls) == 1
    assert "status-clock" in wait_calls[0]["script"]
    assert wait_calls[0]["arg"]["collapsed"] == "probe: 53 bundles ready"
    assert wait_calls[0]["timeout"] == 4321
    assert len(evaluate_calls) == 1
    assert "msg-check" in evaluate_calls[0]["script"]


def test_confirm_document_sent_waits_for_new_outgoing_message_before_matching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp"),
        profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
    )
    sender._ctx = SimpleNamespace(
        page=SimpleNamespace(
            wait_for_timeout=lambda _ms: None,
        )
    )
    calls = []

    monkeypatch.setattr(
        sender,
        "_wait_for_new_outgoing_message",
        lambda previous_count, timeout_ms: calls.append(("new", previous_count, timeout_ms)),
    )
    monkeypatch.setattr(
        sender,
        "_wait_for_document_bubble",
        lambda expected_filename, timeout_ms: calls.append(("bubble", expected_filename, timeout_ms)),
    )
    monkeypatch.setattr(
        sender,
        "_wait_for_document_bubble_settled",
        lambda expected_filename, timeout_ms: calls.append(("settled", expected_filename, timeout_ms)),
    )
    monkeypatch.setattr(sender, "_assert_active_target_chat", lambda: calls.append(("chat",)))

    sender.confirm_document_sent("sample.pdf", previous_outgoing=7)

    assert calls[0][0] == "new"
    assert calls[0][1] == 7
    assert calls[1][0] == "bubble"
    assert calls[2][0] == "settled"
    assert calls[3][0] == "chat"


def test_confirm_document_sent_falls_back_to_filename_match_when_count_gate_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp"),
        profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
    )
    sender._ctx = SimpleNamespace(
        page=SimpleNamespace(
            wait_for_timeout=lambda _ms: None,
        )
    )
    calls = []

    def _raise_count_timeout(previous_count: int, timeout_ms: int) -> None:
        calls.append(("new", previous_count, timeout_ms))
        raise RuntimeError("count gate timeout")

    monkeypatch.setattr(sender, "_wait_for_new_outgoing_message", _raise_count_timeout)
    monkeypatch.setattr(
        sender,
        "_wait_for_document_bubble",
        lambda expected_filename, timeout_ms: calls.append(("bubble", expected_filename, timeout_ms)),
    )
    monkeypatch.setattr(
        sender,
        "_wait_for_document_bubble_settled",
        lambda expected_filename, timeout_ms: calls.append(("settled", expected_filename, timeout_ms)),
    )
    monkeypatch.setattr(sender, "_assert_active_target_chat", lambda: calls.append(("chat",)))

    sender.confirm_document_sent("sample.pdf", previous_outgoing=7)

    assert calls[0][0] == "new"
    assert calls[1][0] == "bubble"
    assert calls[2][0] == "settled"
    assert calls[3][0] == "chat"


def test_confirm_document_sent_raises_when_count_gate_and_filename_match_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender = WhatsAppSender(
        chat_title="Заказы",
        user_data_dir=Path("/tmp"),
        profile_directory="Profile 2",
        blocked_chat_titles=["order 2"],
    )
    sender._ctx = SimpleNamespace(
        page=SimpleNamespace(
            wait_for_timeout=lambda _ms: None,
        )
    )

    monkeypatch.setattr(
        sender,
        "_wait_for_new_outgoing_message",
        lambda previous_count, timeout_ms: (_ for _ in ()).throw(RuntimeError("count gate timeout")),
    )
    monkeypatch.setattr(
        sender,
        "_wait_for_document_bubble",
        lambda expected_filename, timeout_ms: (_ for _ in ()).throw(RuntimeError("bubble timeout")),
    )
    monkeypatch.setattr(sender, "_wait_for_document_bubble_settled", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sender, "_assert_active_target_chat", lambda: None)

    with pytest.raises(RuntimeError, match="bubble timeout"):
        sender.confirm_document_sent("sample.pdf", previous_outgoing=7)


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
