from __future__ import annotations

import sqlite3
from pathlib import Path

import core.ops.google_ops_board_attribution as attribution


def _db(
    tmp_path: Path,
    rows: list[tuple[str, str, str, str]],
    *,
    order_identity: tuple[str, str, str, str] | None = (
        "ORDER-1",
        "UNIVERSAL",
        "ARTICLE-41",
        "CL_EXACT",
    ),
) -> Path:
    path = tmp_path / "app.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE dim_kaspi_article_map (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_code TEXT,
            kaspi_article TEXT,
            kaspi_offer_name TEXT,
            sku_key TEXT,
            sku_id TEXT,
            kaspi_name_core TEXT,
            active_flag INTEGER,
            updated_at TEXT
        );
        CREATE TABLE fact_orders_kaspi (
            id INTEGER PRIMARY KEY,
            order_id TEXT,
            store_code TEXT,
            kaspi_article TEXT,
            sku_key TEXT
        );
        """
    )
    conn.executemany(
        """
        INSERT INTO dim_kaspi_article_map
        (store_code, kaspi_offer_name, sku_key, kaspi_name_core, active_flag, updated_at)
        VALUES (?, ?, ?, ?, 1, '2026-07-15T00:00:00+05:00')
        """,
        rows,
    )
    if order_identity is not None:
        order_id, store_code, article, sku_key = order_identity
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi
            (id, order_id, store_code, kaspi_article, sku_key)
            VALUES (41, ?, ?, ?, ?)
            """,
            (order_id, store_code, article, sku_key),
        )
        conn.execute(
            """
            UPDATE dim_kaspi_article_map
            SET kaspi_article = ?
            WHERE UPPER(TRIM(store_code)) = UPPER(TRIM(?))
              AND UPPER(TRIM(sku_key)) = UPPER(TRIM(?))
            """,
            (article, store_code, sku_key),
        )
    conn.commit()
    conn.close()
    return path


def _row(**overrides) -> dict:
    row = {
        "OrderID": "ORDER-1",
        "_db_row_id": "41",
        "STORE_NAME": "Universal",
        "KASPI_OFFER_NAME": "Exact offer",
        "SKU_key": "CL_EXACT",
        "Kaspi_name_core": "Exact_Core",
    }
    row.update(overrides)
    return row


def test_attribution_audit_accepts_exact_safe_mapping(tmp_path: Path) -> None:
    db_path = _db(tmp_path, [("UNIVERSAL", "Exact offer", "CL_EXACT", "Exact_Core")])

    report = attribution.audit_salesraw_name_core_attribution(
        rows=[_row()],
        db_path=db_path,
        include_safe_rows=True,
    )

    assert report["ok"] is True
    assert report["safe_rows"] == 1
    assert report["findings"][0]["resolution_source"] == "article_identity"


def test_attribution_audit_blocks_raw_offer_fallback(tmp_path: Path) -> None:
    db_path = _db(tmp_path, [])

    report = attribution.audit_salesraw_name_core_attribution(
        rows=[_row(SKU_key="", Kaspi_name_core="Exact_offer")],
        db_path=db_path,
    )

    assert report["ok"] is False
    assert report["blocked_rows"] == 1
    finding = report["findings"][0]
    assert "UNMAPPED_OR_UNSAFE_ATTRIBUTION" in finding["issues"]
    assert finding["unsafe_fallback_source"] == "raw_offer_extract"


def test_attribution_audit_blocks_ambiguous_store_offer(tmp_path: Path) -> None:
    db_path = _db(
        tmp_path,
        [
            ("UNIVERSAL", "Exact offer", "CL_A", "Core_A"),
            ("UNIVERSAL", "Exact offer", "CL_B", "Core_B"),
        ],
    )

    report = attribution.audit_salesraw_name_core_attribution(
        rows=[_row(SKU_key="", Kaspi_name_core="Core_A")],
        db_path=db_path,
    )

    assert report["ok"] is False
    assert "AMBIGUOUS_STORE_OFFER_MAP" in report["findings"][0]["issues"]


def test_attribution_audit_accepts_exact_order_override(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = _db(
        tmp_path,
        [("UNIVERSAL", "Exact offer", "OF_LINE31_ST_IV", "Mapped_Core")],
        order_identity=("ORDER-1", "UNIVERSAL", "ARTICLE-IVORY", "OF_LINE31_ST_IV"),
    )
    monkeypatch.setattr(
        attribution,
        "load_order_name_core_overrides",
        lambda: {"ORDER-1": "Женский_3в1_БЕЖЕВЫЙ"},
    )

    report = attribution.audit_salesraw_name_core_attribution(
        rows=[_row(SKU_key="OF_LINE31_ST_IV", Kaspi_name_core="Женский_3в1_БЕЖЕВЫЙ")],
        db_path=db_path,
        include_safe_rows=True,
    )

    assert report["ok"] is True
    assert report["findings"][0]["resolution_source"] == "forced_core"


def test_line31_ivory_exact_sku_mapping_beats_shared_ambiguous_title(tmp_path: Path) -> None:
    shared_title = "ACMEWEAR OF_LINE31_ST_SB_XL"
    ivory_sku = "CL_OF_ARC_WM_LINE31_C-011_IVORY"
    ivory_core = "Женский_3в1_БЕЖЕВЫЙ"
    db_path = _db(
        tmp_path,
        [
            ("ACMEWEAR", shared_title, "CL_OF_ARC_WM_LINE31_C-008_ESPRESSO", "Женский_3в1_КОРИЧНЕВЫЙ"),
            ("ACMEWEAR", shared_title, "CL_OF_ARC_WM_LINE31_C-010_IRIS-PURPLE", "Женский_3в1_СИРЕНЕВЫЙ"),
            (
                "ACMEWEAR",
                "ACMEWEAR Женский спортивный костюм 3 в 1 молочный L",
                ivory_sku,
                ivory_core,
            ),
        ],
        order_identity=("ORDER-1", "ACMEWEAR", "ARTICLE-IVORY", ivory_sku),
    )

    report = attribution.audit_salesraw_name_core_attribution(
        rows=[
            _row(
                STORE_NAME="ACMEWEAR",
                KASPI_OFFER_NAME=shared_title,
                SKU_key=ivory_sku,
                Kaspi_name_core=ivory_core,
            )
        ],
        db_path=db_path,
        include_safe_rows=True,
    )

    assert report["ok"] is True
    assert report["safe_rows"] == 1
    assert report["findings"][0]["resolution_source"] == "article_identity"
    assert report["findings"][0]["resolved_core"] == ivory_core


def test_exact_store_article_identity_beats_historical_sku_core_conflict(
    tmp_path: Path,
) -> None:
    db_path = _db(
        tmp_path,
        [
            ("UNIVERSAL", "Old alias", "CL_LINE52", "Line51"),
            ("UNIVERSAL", "Current offer", "CL_LINE52", "Принт_5в1_черный"),
        ],
        order_identity=None,
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE dim_kaspi_article_map SET kaspi_article='ARTICLE_CURRENT' WHERE kaspi_offer_name='Current offer'"
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi
            (id, order_id, store_code, kaspi_article, sku_key)
            VALUES (41, 'ORDER-1', 'UNIVERSAL', 'ARTICLE_CURRENT', 'CL_LINE52')
            """
        )
        conn.commit()

    report = attribution.audit_salesraw_name_core_attribution(
        rows=[
            _row(
                SKU_key="CL_LINE52",
                KASPI_OFFER_NAME="Current offer",
                Kaspi_name_core="Принт_5в1_черный",
            )
        ],
        db_path=db_path,
        include_safe_rows=True,
    )

    assert report["ok"] is True
    assert report["findings"][0]["resolution_source"] == "article_identity"
    assert report["findings"][0]["kaspi_article"] == "ARTICLE_CURRENT"
    assert report["findings"][0]["article_map_ids"]


def test_conflicting_exact_store_article_identity_remains_blocked(
    tmp_path: Path,
) -> None:
    db_path = _db(tmp_path, [], order_identity=None)
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO dim_kaspi_article_map (
                store_code, kaspi_article, kaspi_offer_name, sku_key,
                kaspi_name_core, active_flag, updated_at
            ) VALUES ('UNIVERSAL', 'ARTICLE_CURRENT', 'Current offer',
                      'CL_LINE52', ?, 1, '2026-07-16')
            """,
            [("Core_A",), ("Core_B",)],
        )
        conn.execute(
            """
            INSERT INTO fact_orders_kaspi
            (id, order_id, store_code, kaspi_article, sku_key)
            VALUES (41, 'ORDER-1', 'UNIVERSAL', 'ARTICLE_CURRENT', 'CL_LINE52')
            """
        )
        conn.commit()

    report = attribution.audit_salesraw_name_core_attribution(
        rows=[_row(SKU_key="CL_LINE52", KASPI_OFFER_NAME="Current offer")],
        db_path=db_path,
    )

    assert report["ok"] is False
    assert "AMBIGUOUS_ARTICLE_IDENTITY" in report["findings"][0]["issues"]


def test_generic_sku_mapping_cannot_replace_missing_exact_article_identity(
    tmp_path: Path,
) -> None:
    db_path = _db(tmp_path, [("UNIVERSAL", "Exact offer", "CL_EXACT", "Exact_Core")])
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE dim_kaspi_article_map SET kaspi_article = NULL")
        conn.commit()

    report = attribution.audit_salesraw_name_core_attribution(
        rows=[_row()],
        db_path=db_path,
    )

    assert report["ok"] is False
    finding = report["findings"][0]
    assert "MISSING_ARTICLE_IDENTITY" in finding["issues"]
    assert finding["resolution_source"] == "sku_key"


def test_board_row_id_must_bind_to_same_order_store_and_sku(tmp_path: Path) -> None:
    db_path = _db(tmp_path, [("UNIVERSAL", "Exact offer", "CL_EXACT", "Exact_Core")])

    cases = [
        ({"OrderID": "ORDER-OTHER"}, "DB_ROW_ORDER_ID_MISMATCH"),
        ({"STORE_NAME": "ACMEWEAR"}, "DB_ROW_STORE_MISMATCH"),
        ({"SKU_key": "CL_OTHER"}, "DB_ROW_SKU_KEY_MISMATCH"),
    ]
    for row_changes, expected_issue in cases:
        report = attribution.audit_salesraw_name_core_attribution(
            rows=[_row(**row_changes)],
            db_path=db_path,
        )
        assert report["ok"] is False
        assert expected_issue in report["findings"][0]["issues"]


def test_missing_invalid_and_unknown_board_row_ids_fail_closed(tmp_path: Path) -> None:
    db_path = _db(tmp_path, [("UNIVERSAL", "Exact offer", "CL_EXACT", "Exact_Core")])

    cases = [
        ("", "MISSING_DB_ROW_ID"),
        ("not-a-row", "INVALID_DB_ROW_ID"),
        ("999", "DB_ROW_ID_NOT_FOUND"),
    ]
    for row_id, expected_issue in cases:
        report = attribution.audit_salesraw_name_core_attribution(
            rows=[_row(_db_row_id=row_id)],
            db_path=db_path,
        )
        assert report["ok"] is False
        assert expected_issue in report["findings"][0]["issues"]


def test_forced_override_does_not_bypass_missing_exact_article_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = _db(tmp_path, [], order_identity=("ORDER-1", "UNIVERSAL", "ARTICLE-41", "CL_EXACT"))
    monkeypatch.setattr(
        attribution,
        "load_order_name_core_overrides",
        lambda: {"ORDER-1": "Forced_Core"},
    )

    report = attribution.audit_salesraw_name_core_attribution(
        rows=[_row(Kaspi_name_core="Forced_Core")],
        db_path=db_path,
    )

    assert report["ok"] is False
    assert report["findings"][0]["resolution_source"] == "forced_core"
    assert "MISSING_ARTICLE_IDENTITY" in report["findings"][0]["issues"]


def test_inactive_and_sku_incompatible_exact_article_rows_fail_closed(
    tmp_path: Path,
) -> None:
    db_path = _db(tmp_path, [("UNIVERSAL", "Exact offer", "CL_EXACT", "Exact_Core")])
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE dim_kaspi_article_map SET active_flag = 0")
        conn.commit()
    inactive = attribution.audit_salesraw_name_core_attribution(
        rows=[_row()], db_path=db_path
    )
    assert "INACTIVE_ARTICLE_IDENTITY" in inactive["findings"][0]["issues"]

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE dim_kaspi_article_map SET active_flag = 1, sku_key = 'CL_OTHER'"
        )
        conn.commit()
    incompatible = attribution.audit_salesraw_name_core_attribution(
        rows=[_row()], db_path=db_path
    )
    assert "SKU_INCOMPATIBLE_ARTICLE_IDENTITY" in incompatible["findings"][0]["issues"]


def test_cross_store_exact_article_core_conflict_fails_closed(tmp_path: Path) -> None:
    db_path = _db(tmp_path, [("UNIVERSAL", "Exact offer", "CL_EXACT", "Exact_Core")])
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO dim_kaspi_article_map (
                store_code, kaspi_article, kaspi_offer_name, sku_key,
                kaspi_name_core, active_flag, updated_at
            ) VALUES (
                'STORE-B', 'ARTICLE-41', 'Conflicting offer', 'CL_EXACT',
                'Wrong_Core', 1, '2026-07-16'
            )
            """
        )
        conn.commit()

    report = attribution.audit_salesraw_name_core_attribution(
        rows=[_row()], db_path=db_path
    )

    assert report["ok"] is False
    assert "CROSS_STORE_ARTICLE_CORE_CONFLICT" in report["findings"][0]["issues"]
