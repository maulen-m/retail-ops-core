from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validate_ops_selection_parity import validate_ops_selection_parity


def _write_archive_input(base: Path, as_of: str, *, selected: int, copied: int, missing: int, ids: list[str]) -> Path:
    archive_dir = base / f"input_{as_of}_183543"
    waybill_dir = archive_dir / "waybills"
    waybill_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "selected_count": selected,
        "copied_waybills": copied,
        "missing_waybills": missing,
    }
    (archive_dir / "archive_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for order_id in ids:
        (waybill_dir / f"{order_id}.pdf").write_bytes(b"%PDF")
    return archive_dir


def test_ops_selection_parity_pass(tmp_path: Path) -> None:
    as_of = "2026-02-26"
    import_log = tmp_path / "kaspi_import_stdout.log"
    import_log.write_text(
        f"SUCCESS_GATE_OK: activeorders snapshot parity (target_date={as_of}, orders=8)\n",
        encoding="utf-8",
    )
    waybill_log = tmp_path / "kaspi_waybill_deadline_stdout.log"
    waybill_log.write_text(
        f"Time: {as_of} 18:30:21\n"
        "  Summary\n"
        "  Shipped: 4\n"
        "  Summary\n"
        "  Shipped: 3\n",
        encoding="utf-8",
    )

    archive_root = tmp_path / "archive"
    ids = [f"83{i:06d}" for i in range(1, 11)]
    _write_archive_input(archive_root, as_of, selected=10, copied=10, missing=0, ids=ids)

    cache = tmp_path / "_waybill_selection_orders.json"
    cache.write_text(
        json.dumps(
            {
                "target_date": as_of,
                "stores": {"UNIVERSAL": ids},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    report = validate_ops_selection_parity(
        as_of=as_of,
        import_log=import_log,
        waybill_log=waybill_log,
        archive_root=archive_root,
        selection_cache=cache,
        output_root=tmp_path / "out",
        strict=False,
    )
    assert report["status"] == "PASS"
    assert report["errors"] == []


def test_ops_selection_parity_strict_fails_on_manifest_mismatch(tmp_path: Path) -> None:
    as_of = "2026-02-26"
    (tmp_path / "import.log").write_text(
        f"SUCCESS_GATE_OK: activeorders snapshot parity (target_date={as_of}, orders=3)\n",
        encoding="utf-8",
    )
    (tmp_path / "waybill.log").write_text(
        f"Time: {as_of} 18:30:00\n  Summary\n  Shipped: 2\n",
        encoding="utf-8",
    )
    archive_root = tmp_path / "archive"
    _write_archive_input(
        archive_root,
        as_of,
        selected=5,
        copied=3,
        missing=1,  # selected != copied + missing -> fail
        ids=["835000001", "835000002", "835000003"],
    )
    cache = tmp_path / "cache.json"
    cache.write_text(json.dumps({"target_date": as_of, "stores": {"UNIVERSAL": ["835000001"]}}), encoding="utf-8")

    with pytest.raises(RuntimeError, match="ops selection parity validation failed"):
        validate_ops_selection_parity(
            as_of=as_of,
            import_log=tmp_path / "import.log",
            waybill_log=tmp_path / "waybill.log",
            archive_root=archive_root,
            selection_cache=cache,
            output_root=tmp_path / "out",
            strict=True,
        )
