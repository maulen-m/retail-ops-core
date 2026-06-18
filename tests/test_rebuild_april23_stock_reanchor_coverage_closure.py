from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.rebuild_april23_stock_reanchor_coverage_closure import (
    INACTIVE_STORE_OLD_BLOCKER,
    build_delta,
    manifest_covers_window,
    relabel_inactive_store_coverage_notes,
    remove_retained_blocker,
)


def test_manifest_covers_active_store_window_with_inactive_omissions() -> None:
    manifest = {
        "since": "2026-03-01",
        "until": "2026-05-26",
        "target_stores": ["ACMEWEAR", "STOREB", "UNIVERSAL"],
        "omitted_enabled_stores": ["11KZ", "MELVIS"],
        "status": "PASS",
        "ok": True,
    }

    assert manifest_covers_window(manifest, stores=("STOREB", "ACMEWEAR", "UNIVERSAL"))


def test_inactive_store_blocker_is_removed_but_other_blockers_remain() -> None:
    frame = pd.DataFrame(
        [
            {
                "retained_blockers": (
                    "NO_RETURN_QC_ACCEPTANCE_SOURCE; "
                    f"{INACTIVE_STORE_OLD_BLOCKER}; "
                    "CHILD_BUNDLE_COMPONENT_STOCK_SPLIT_NOT_PROVEN"
                )
            }
        ]
    )

    cleaned = remove_retained_blocker(frame, INACTIVE_STORE_OLD_BLOCKER)

    blockers = cleaned.iloc[0]["retained_blockers"]
    assert INACTIVE_STORE_OLD_BLOCKER not in blockers
    assert "NO_RETURN_QC_ACCEPTANCE_SOURCE" in blockers
    assert "CHILD_BUNDLE_COMPONENT_STOCK_SPLIT_NOT_PROVEN" in blockers


def test_relabels_inactive_store_coverage_notes_as_non_blocking_disclosure() -> None:
    ledger = pd.DataFrame(
        [
            {"coverage_note": "manual_webui_only_storeb_acmewear_universal_omits_store-d_store-c"},
            {"coverage_note": "manual_webui_2026-05-26_storeb_acmewear_universal_omits_store-d_store-c"},
        ]
    )

    relabeled = relabel_inactive_store_coverage_notes(ledger)

    assert relabeled["coverage_note"].str.contains("inactive_not_blocker").all()


def test_build_delta_includes_total_sku_size_and_blocker_counts(tmp_path: Path) -> None:
    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    old_dir.mkdir()
    new_dir.mkdir()
    pd.DataFrame(
        [{"metric": "physical_estimated_warehouse_on_hand_qty", "value": "10", "date_basis": "ship_date"}]
    ).to_csv(old_dir / "summary.csv", index=False)
    new_summary = pd.DataFrame(
        [{"metric": "physical_estimated_warehouse_on_hand_qty", "value": 8.0, "date_basis": "ship_date"}]
    )
    old_physical = pd.DataFrame(
        [
            {
                "family": "LINE61",
                "sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                "my_size": "XL",
                "estimated_warehouse_on_hand_qty": "10",
            }
        ]
    )
    new_physical = pd.DataFrame(
        [
            {
                "family": "LINE61",
                "sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                "my_size": "XL",
                "estimated_warehouse_on_hand_qty": "8",
            }
        ]
    )
    old_economic = old_physical.rename(columns={"estimated_warehouse_on_hand_qty": "estimated_final_sales_stock_qty"})
    new_economic = new_physical.rename(columns={"estimated_warehouse_on_hand_qty": "estimated_final_sales_stock_qty"})
    old_exposure = pd.DataFrame(
        [
            {
                "family": "LINE61",
                "sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                "my_size": "XL",
                "on_delivery_exposure_qty": "1",
                "missing_shipped_source_gap_qty": "0",
            }
        ]
    )
    new_exposure = pd.DataFrame(
        [
            {
                "family": "LINE61",
                "sku_key": "CL_NEW-CLO2_MEN_SUIT-61_BLACK",
                "my_size": "XL",
                "on_delivery_exposure_qty": "0",
                "missing_shipped_source_gap_qty": "2",
            }
        ]
    )
    for directory, physical, economic, exposure, blocker in [
        (old_dir, old_physical, old_economic, old_exposure, INACTIVE_STORE_OLD_BLOCKER),
        (new_dir, new_physical, new_economic, new_exposure, "NO_RETURN_QC_ACCEPTANCE_SOURCE"),
    ]:
        physical.to_csv(directory / "physical_warehouse_stock_estimate_by_sku_size.csv", index=False)
        economic.to_csv(directory / "economic_final_sales_stock_by_sku_size.csv", index=False)
        exposure.to_csv(directory / "inventory_on_delivery_exposure_by_sku_size.csv", index=False)
        pd.DataFrame(
            [{"stock_view": "ECONOMIC_FINAL_SALES_STOCK", "sku_key": "sku", "my_size": "XL", "blocker": blocker}]
        ).to_csv(directory / "retained_blockers.csv", index=False)

    delta = build_delta(old_dir, new_summary, new_dir)

    total = delta[(delta["scope"] == "TOTAL") & (delta["metric"] == "physical_estimated_warehouse_on_hand_qty")]
    blocker = delta[(delta["scope"] == "BLOCKER_COUNT") & (delta["metric"] == INACTIVE_STORE_OLD_BLOCKER)]
    sku_size = delta[
        (delta["scope"] == "SKU_SIZE")
        & (delta["metric"] == "PHYSICAL_WAREHOUSE_STOCK_ESTIMATE.estimated_warehouse_on_hand_qty")
    ]
    assert total.iloc[0]["delta"] == -2.0
    assert blocker.iloc[0]["delta"] == -1
    assert sku_size.iloc[0]["family"] == "LINE61"
