from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from scripts.import_web_automation_offer_identity import (
    _parse_snapshot_sku_field,
    import_web_automation_offer_identity,
)
from scripts.identity_stabilization_common import StatusError


def _snapshot_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "SKU": "1001",
                "resolved_kaspi_offer_name": "Offer A",
                "resolved_sku_key": "SKU_A",
                "effective_sku_key": "SKU_A",
                "effective_final_size": "XL",
                "mapping_status": "matched",
                "mapping_method": "manual_exact",
                "identity_status": "matched",
                "resolved_url": "https://kaspi.kz/shop/p/1001/",
                "Human_edit_sku_key": "",
                "Human_edit_size": "",
            },
            {
                "SKU": "1002",
                "resolved_kaspi_offer_name": "Offer B",
                "resolved_sku_key": "",
                "effective_sku_key": "",
                "effective_final_size": "",
                "mapping_status": "new",
                "mapping_method": "auto",
                "identity_status": "unresolved",
                "resolved_url": "https://kaspi.kz/shop/p/1002/",
                "Human_edit_sku_key": "",
                "Human_edit_size": "",
            },
        ]
    )


def _write_snapshot(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _snapshot_frame().to_excel(path, index=False)


def _write_snapshot_custom(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_excel(path, index=False)


def test_parse_snapshot_sku_field_tab_inline_offer() -> None:
    sku, offer = _parse_snapshot_sku_field("102529963\tCL_OC_MEN_LINE52_BLACK_2XL_102529963")
    assert sku == "102529963"
    assert offer == "CL_OC_MEN_LINE52_BLACK_2XL_102529963"


def test_import_web_automation_offer_identity_pass(tmp_path: Path) -> None:
    web_root = tmp_path / "web"
    snapshots = web_root / "exports" / "pricelist_snapshots"
    _write_snapshot(snapshots / "universal_snapshot_2026-03-03.xlsx")
    _write_snapshot(snapshots / "store-b_snapshot_2026-03-03.xlsx")

    report = import_web_automation_offer_identity(
        as_of=date(2026, 3, 4),
        web_root=web_root,
        snapshot_files=[],
        output_root=tmp_path / "out",
        reference_root=tmp_path / "ref",
        db_path=tmp_path / "app.db",
        apply=False,
        strict=True,
        backup_root=tmp_path / "backups",
        override_csv=None,
    )
    assert report["status"] == "PASS"
    assert report["reference_rows"] == 4
    assert report["unresolved_rows"] == 2
    assert (tmp_path / "out" / "2026-03-04" / "offer_identity_reference.csv").exists()
    assert (tmp_path / "out" / "2026-03-04" / "source_manifest.json").exists()


def test_import_web_automation_offer_identity_fails_on_stale_snapshot(tmp_path: Path) -> None:
    web_root = tmp_path / "web"
    snapshots = web_root / "exports" / "pricelist_snapshots"
    _write_snapshot(snapshots / "universal_snapshot_2026-02-20.xlsx")
    _write_snapshot(snapshots / "store-b_snapshot_2026-02-20.xlsx")

    with pytest.raises(StatusError, match="EXTERNAL_MAPPING_STALE"):
        import_web_automation_offer_identity(
            as_of=date(2026, 3, 4),
            web_root=web_root,
            snapshot_files=[],
            output_root=tmp_path / "out",
            reference_root=tmp_path / "ref",
            db_path=tmp_path / "app.db",
            apply=False,
            strict=True,
            backup_root=tmp_path / "backups",
            override_csv=None,
        )


def test_import_web_automation_offer_identity_applies_repo_override(tmp_path: Path) -> None:
    web_root = tmp_path / "web"
    snapshots = web_root / "exports" / "pricelist_snapshots"
    _write_snapshot(snapshots / "universal_snapshot_2026-03-03.xlsx")
    _write_snapshot(snapshots / "store-b_snapshot_2026-03-03.xlsx")

    override_csv = tmp_path / "overrides.csv"
    override_csv.write_text(
        "\n".join(
            [
                "store_code,sku_id_ksp,effective_sku_key,effective_size,note",
                "STOREB,1002,CL_OC_MEN_LINE52_BLACK_2XL_1002,2XL,test",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = import_web_automation_offer_identity(
        as_of=date(2026, 3, 4),
        web_root=web_root,
        snapshot_files=[],
        output_root=tmp_path / "out",
        reference_root=tmp_path / "ref",
        db_path=tmp_path / "app.db",
        apply=False,
        strict=True,
        backup_root=tmp_path / "backups",
        override_csv=override_csv,
    )
    assert report["status"] == "PASS"
    assert report["overrides_applied"] == 1
    assert report["unresolved_rows"] == 1


def test_import_web_automation_offer_identity_override_matches_tabbed_sku(tmp_path: Path) -> None:
    web_root = tmp_path / "web"
    snapshots = web_root / "exports" / "pricelist_snapshots"
    _write_snapshot(snapshots / "universal_snapshot_2026-03-03.xlsx")
    _write_snapshot_custom(
        snapshots / "store-b_snapshot_2026-03-03.xlsx",
        pd.DataFrame(
            [
                {
                    "SKU": "102529963\tCL_OC_MEN_LINE52_BLACK_2XL_102529963",
                    "resolved_kaspi_offer_name": "",
                    "resolved_sku_key": "",
                    "effective_sku_key": "",
                    "effective_final_size": "",
                    "mapping_status": "new",
                    "mapping_method": "auto",
                    "identity_status": "unmatched_offer_row",
                    "resolved_url": "",
                    "Human_edit_sku_key": "",
                    "Human_edit_size": "",
                }
            ]
        ),
    )

    override_csv = tmp_path / "overrides.csv"
    override_csv.write_text(
        "\n".join(
            [
                "store_code,sku_id_ksp,effective_sku_key,effective_size,note",
                "STOREB,102529963,CL_OC_MEN_LINE52_BLACK_2XL_102529963,2XL,test",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = import_web_automation_offer_identity(
        as_of=date(2026, 3, 4),
        web_root=web_root,
        snapshot_files=[],
        output_root=tmp_path / "out",
        reference_root=tmp_path / "ref",
        db_path=tmp_path / "app.db",
        apply=False,
        strict=True,
        backup_root=tmp_path / "backups",
        override_csv=override_csv,
    )
    assert report["status"] == "PASS"
    assert report["overrides_applied"] == 1
    assert report["unresolved_rows"] == 1

    ref = pd.read_csv(tmp_path / "out" / "2026-03-04" / "offer_identity_reference.csv", dtype=str, keep_default_na=False)
    row = ref[ref["store_code"] == "STOREB"].iloc[0]
    assert row["sku_id_ksp"] == "102529963"
    assert row["kaspi_offer_name"] == "CL_OC_MEN_LINE52_BLACK_2XL_102529963"
    assert row["effective_sku_key"] == "CL_OC_MEN_LINE52_BLACK_2XL_102529963"
