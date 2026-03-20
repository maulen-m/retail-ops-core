from __future__ import annotations

from pathlib import Path
import os

import pytest

from scripts.bootstrap_owner_truth_anchors import AnchorBootstrapError, bootstrap_owner_truth_anchors


def test_bootstrap_owner_truth_anchors_creates_required_symlinks(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    crm = tmp_path / "inputs" / "crm.xlsx"
    inbound = tmp_path / "inputs" / "inbound.xlsx"
    stock = tmp_path / "inputs" / "stock.xlsx"
    env_file = tmp_path / "inputs" / ".env"
    waybill_dir = tmp_path / "inputs" / "waybills"
    release_validation = tmp_path / "inputs" / "ads_scope_closeout" / "2026-03-08"
    for path in (crm, inbound, stock):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture", encoding="utf-8")
    env_file.write_text("KASPI_TOKEN_ACMEWEAR=fixture\n", encoding="utf-8")
    waybill_dir.mkdir(parents=True, exist_ok=True)
    (waybill_dir / "_waybill_selection_orders.json").write_text(
        "{\"target_date\":\"2026-03-08\"}\n",
        encoding="utf-8",
    )
    (waybill_dir / "850084962.pdf").write_text("fixture", encoding="utf-8")
    release_validation.mkdir(parents=True, exist_ok=True)
    (release_validation / "marker.txt").write_text("fixture", encoding="utf-8")

    report = bootstrap_owner_truth_anchors(
        project_root=project_root,
        crm_workbook=crm,
        inbound_workbook=inbound,
        stock_workbook=stock,
        env_file=env_file,
        waybill_selection_cache=waybill_dir,
        release_as_of="2026-03-08",
        release_validation_root=release_validation,
        validate_only=False,
    )

    anchors = project_root / "config" / "anchors"
    assert (anchors / "SALES_KSP_CRM_LATEST.xlsx").is_symlink()
    assert (anchors / "INBOUND_CALENDAR_LATEST.xlsx").is_symlink()
    assert (anchors / "STOCK_SNAPSHOT_LATEST.xlsx").is_symlink()
    assert (project_root / ".env").is_symlink()
    assert (project_root / "excel_ui" / "ActiveOrders" / "waybills").is_symlink()
    assert (
        project_root / "excel_ui" / "ActiveOrders" / "waybills" / "_waybill_selection_orders.json"
    ).exists()
    assert (project_root / "exports" / "validation" / "ads_scope_closeout" / "2026-03-08").is_symlink()
    assert Path(report["anchors"]["crm_anchor"]["target"]).resolve() == crm.resolve()
    assert Path(report["anchors"]["env_anchor"]["target"]).resolve() == env_file.resolve()
    assert Path(report["anchors"]["waybill_selection_anchor"]["target"]).resolve() == waybill_dir.resolve()
    assert Path(report["anchors"]["release_validation_anchor"]["target"]).resolve() == release_validation.resolve()


def test_bootstrap_owner_truth_anchors_fails_closed_when_inputs_missing(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    crm = tmp_path / "inputs" / "crm.xlsx"
    crm.parent.mkdir(parents=True, exist_ok=True)
    crm.write_text("fixture", encoding="utf-8")

    with pytest.raises(AnchorBootstrapError, match="missing required anchor input"):
        bootstrap_owner_truth_anchors(
            project_root=project_root,
            crm_workbook=crm,
            inbound_workbook=None,
            stock_workbook=None,
            env_file=None,
            waybill_selection_cache=None,
            release_as_of=None,
            release_validation_root=None,
            validate_only=False,
        )


def test_bootstrap_owner_truth_anchors_validate_only_requires_release_validation_anchor_when_requested(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "repo"
    anchors = project_root / "config" / "anchors"
    anchors.mkdir(parents=True, exist_ok=True)
    for name in (
        "SALES_KSP_CRM_LATEST.xlsx",
        "INBOUND_CALENDAR_LATEST.xlsx",
        "STOCK_SNAPSHOT_LATEST.xlsx",
    ):
        (anchors / name).write_text("fixture", encoding="utf-8")
    env_target = tmp_path / "inputs" / ".env"
    env_target.parent.mkdir(parents=True, exist_ok=True)
    env_target.write_text("KASPI_TOKEN_ACMEWEAR=fixture\n", encoding="utf-8")
    (project_root / ".env").symlink_to(env_target)
    waybill_dir = tmp_path / "inputs" / "waybills"
    waybill_dir.mkdir(parents=True, exist_ok=True)
    (waybill_dir / "_waybill_selection_orders.json").write_text(
        "{\"target_date\":\"2026-03-08\"}\n",
        encoding="utf-8",
    )
    waybill_anchor = project_root / "excel_ui" / "ActiveOrders" / "waybills"
    waybill_anchor.parent.mkdir(parents=True, exist_ok=True)
    waybill_anchor.symlink_to(waybill_dir, target_is_directory=True)

    with pytest.raises(AnchorBootstrapError, match="release_validation_anchor"):
        bootstrap_owner_truth_anchors(
            project_root=project_root,
            crm_workbook=None,
            inbound_workbook=None,
            stock_workbook=None,
            env_file=None,
            waybill_selection_cache=None,
            release_as_of="2026-03-08",
            release_validation_root=None,
            validate_only=True,
        )


def test_bootstrap_owner_truth_anchors_validate_only_requires_waybill_selection_anchor(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    anchors = project_root / "config" / "anchors"
    anchors.mkdir(parents=True, exist_ok=True)
    for name in (
        "SALES_KSP_CRM_LATEST.xlsx",
        "INBOUND_CALENDAR_LATEST.xlsx",
        "STOCK_SNAPSHOT_LATEST.xlsx",
    ):
        (anchors / name).write_text("fixture", encoding="utf-8")
    env_target = tmp_path / "inputs" / ".env"
    env_target.parent.mkdir(parents=True, exist_ok=True)
    env_target.write_text("KASPI_TOKEN_ACMEWEAR=fixture\n", encoding="utf-8")
    (project_root / ".env").symlink_to(env_target)

    with pytest.raises(AnchorBootstrapError, match="waybill_selection_anchor"):
        bootstrap_owner_truth_anchors(
            project_root=project_root,
            crm_workbook=None,
            inbound_workbook=None,
            stock_workbook=None,
            env_file=None,
            waybill_selection_cache=None,
            release_as_of=None,
            release_validation_root=None,
            validate_only=True,
        )


def test_bootstrap_owner_truth_anchors_replaces_existing_waybill_directory_with_symlink(tmp_path: Path) -> None:
    project_root = tmp_path / "repo"
    crm = tmp_path / "inputs" / "crm.xlsx"
    inbound = tmp_path / "inputs" / "inbound.xlsx"
    stock = tmp_path / "inputs" / "stock.xlsx"
    env_file = tmp_path / "inputs" / ".env"
    waybill_dir = tmp_path / "inputs" / "waybills"
    for path in (crm, inbound, stock):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture", encoding="utf-8")
    env_file.write_text("KASPI_TOKEN_ACMEWEAR=fixture\n", encoding="utf-8")
    waybill_dir.mkdir(parents=True, exist_ok=True)
    (waybill_dir / "_waybill_selection_orders.json").write_text(
        "{\"target_date\":\"2026-03-08\"}\n",
        encoding="utf-8",
    )
    existing_dir = project_root / "excel_ui" / "ActiveOrders" / "waybills"
    existing_dir.mkdir(parents=True, exist_ok=True)
    (existing_dir / "_waybill_selection_orders.json").write_text(
        "{\"target_date\":\"stale\"}\n",
        encoding="utf-8",
    )

    report = bootstrap_owner_truth_anchors(
        project_root=project_root,
        crm_workbook=crm,
        inbound_workbook=inbound,
        stock_workbook=stock,
        env_file=env_file,
        waybill_selection_cache=waybill_dir,
        release_as_of=None,
        release_validation_root=None,
        validate_only=False,
    )

    anchor = project_root / "excel_ui" / "ActiveOrders" / "waybills"
    assert anchor.is_symlink()
    assert os.readlink(anchor) == str(waybill_dir.resolve())
    assert Path(report["anchors"]["waybill_selection_anchor"]["target"]).resolve() == waybill_dir.resolve()
