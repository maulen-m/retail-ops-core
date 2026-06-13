from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scripts.materialize_meta_external_ads_spend import (
    ENV_GATE,
    MetaExternalAdsSpendError,
    materialize_meta_external_ads_spend,
)


def _write_packet(root: Path, *, any_spend_found: bool = True) -> Path:
    run_root = root / "runs" / "ab_source_freshness_20260613_acmewear_meta_spend_boundary"
    raw_path = run_root / "raw_meta_source" / "2026-06-13" / "meta_insights_live_readonly_2026-06-13.json"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_text(
        json.dumps(
            {
                "run_id": "ads_monitoring_2026-06-13_165359",
                "run_date": "2026-06-13",
                "fetched_at": "2026-06-13T11:54:03Z",
                "account_id": "1517999585924947",
                "levels": {"campaign": []},
            }
        ),
        encoding="utf-8",
    )
    packet = {
        "generated_at_utc": "2026-06-13T16:21:25Z",
        "gate": "YELLOW",
        "dates_requested": ["2026-06-13"],
        "dates_successfully_fetched": ["2026-06-13"],
        "source_freshness_cleared_by_date": {"2026-06-13": True},
        "row_counts_by_date_and_level": {
            "2026-06-13": {"campaign": 4, "adset": 12, "ad": 12}
        },
        "spend_by_date": {"2026-06-13": 124.64},
        "raw_evidence_paths": {"2026-06-13": str(raw_path)},
        "raw_source_run_id": "ads_monitoring_2026-06-13_165359",
        "raw_source_fetched_at": "2026-06-13T11:54:03Z",
        "platform_writes_occurred": False,
        "budget_status_campaign_adset_ad_writes_occurred": False,
        "autonomous_business_writes_performed": False,
        "deterministic_purchase_attribution_claimed": False,
        "any_spend_found": any_spend_found,
        "date_results": [
            {
                "date": "2026-06-13",
                "source_status": "SUCCESS",
                "clears_source_freshness": True,
                "any_spend_found": any_spend_found,
                "spend": 124.64 if any_spend_found else 0.0,
                "spend_basis": "campaign",
                "raw_evidence_path": str(raw_path),
                "row_counts_by_level": {"campaign": 4, "adset": 12, "ad": 12},
            }
        ],
    }
    packet_path = run_root / "meta_live_refresh_summary.json"
    packet_path.write_text(json.dumps(packet, indent=2), encoding="utf-8")
    return packet_path


def test_meta_external_ads_spend_materializer_dry_run_does_not_create_table(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "app.db"
    sqlite3.connect(db_path).close()
    packet = _write_packet(tmp_path / "Facebook_ads")

    report = materialize_meta_external_ads_spend(
        db_path=db_path,
        packet_path=packet,
        store_code="ACMEWEAR",
        run_id="pytest-meta-spend",
        output_root=tmp_path / "out",
        apply=False,
    )

    assert report["candidate_rows"] == 1
    assert report["candidate_spend_amount"] == 124.64
    assert report["account_ids"] == ["1517999585924947"]
    with sqlite3.connect(db_path) as conn:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta_external_ads_spend_daily'"
        ).fetchone()
    assert exists is None


def test_meta_external_ads_spend_materializer_apply_requires_env_gate(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    sqlite3.connect(db_path).close()
    packet = _write_packet(tmp_path / "Facebook_ads")

    with pytest.raises(MetaExternalAdsSpendError, match=ENV_GATE):
        materialize_meta_external_ads_spend(
            db_path=db_path,
            packet_path=packet,
            store_code="ACMEWEAR",
            run_id="pytest-meta-spend",
            output_root=tmp_path / "out",
            apply=True,
        )


def test_meta_external_ads_spend_materializer_applies_provenance_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "app.db"
    sqlite3.connect(db_path).close()
    packet = _write_packet(tmp_path / "Facebook_ads")
    monkeypatch.setenv(ENV_GATE, "1")

    report = materialize_meta_external_ads_spend(
        db_path=db_path,
        packet_path=packet,
        store_code="ACMEWEAR",
        run_id="pytest-meta-spend",
        output_root=tmp_path / "out",
        apply=True,
    )

    assert report["table_count_before"] == 0
    assert report["table_count_after"] == 1
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT date, store_code, source_system, account_id, spend_amount,
                   publication_attribution_claimed, packet_sha256, raw_evidence_sha256
            FROM meta_external_ads_spend_daily
            """
        ).fetchone()
    assert row == (
        "2026-06-13",
        "ACMEWEAR",
        "meta_instagram",
        "1517999585924947",
        124.64,
        0,
        report["packet_sha256"],
        report["rows"][0]["raw_evidence_sha256"],
    )
