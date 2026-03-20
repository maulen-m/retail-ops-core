from __future__ import annotations

import json
from pathlib import Path

from scripts.generate_ops_selection_artifacts import generate_ops_selection_artifacts
from scripts.validate_ops_selection_parity import validate_ops_selection_parity


def _write_seed(path: Path) -> dict[str, object]:
    seed = {
        "as_of": "2026-03-08",
        "import_orders": 69,
        "shipped_orders": 78,
        "selected_count": 78,
        "copied_waybills": 78,
        "missing_waybills": 0,
        "stores": {
            "STOREB": [str(845000000 + idx) for idx in range(1, 27)],
            "ACMEWEAR": [str(846000000 + idx) for idx in range(1, 15)],
            "UNIVERSAL": [str(847000000 + idx) for idx in range(1, 39)],
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return seed


def test_generate_ops_selection_artifacts_materializes_parity_inputs(tmp_path: Path) -> None:
    seed_path = tmp_path / "exports" / "validation" / "board_v8_runtime" / "2026-03-08" / "ops_selection_seed.json"
    _write_seed(seed_path)

    report = generate_ops_selection_artifacts(
        as_of="2026-03-08",
        project_root=tmp_path,
        seed_json=seed_path,
        strict=True,
    )

    assert report["status"] == "PASS"
    assert Path(report["import_log"]).exists()
    assert Path(report["waybill_log"]).exists()
    assert Path(report["selection_cache"]).exists()
    assert Path(report["archive_manifest"]).exists()
    assert len(list((Path(report["archive_input_dir"]) / "waybills").glob("*.pdf"))) == 78
    assert "Time: 2026-03-08 11:00:00" in Path(report["import_log"]).read_text(encoding="utf-8")
    assert "Time: 2026-03-08 16:03:00" in Path(report["import_log"]).read_text(encoding="utf-8")
    assert "Time: 2026-03-08 19:10:00" in Path(report["report_log"]).read_text(encoding="utf-8")

    parity = validate_ops_selection_parity(
        as_of="2026-03-08",
        import_log=Path(report["import_log"]),
        waybill_log=Path(report["waybill_log"]),
        archive_root=tmp_path / "excel_ui" / "Archive",
        selection_cache=Path(report["selection_cache"]),
        output_root=tmp_path / "exports" / "validation" / "ops_selection_parity",
        strict=True,
        max_import_overflow=5,
    )
    assert parity["status"] == "PASS"
    assert parity["import_orders"] == 69
    assert parity["waybill_selected_orders"] == 78
    assert parity["shipped_orders"] == 78


def test_generate_ops_selection_artifacts_is_idempotent(tmp_path: Path) -> None:
    seed_path = tmp_path / "exports" / "validation" / "board_v8_runtime" / "2026-03-08" / "ops_selection_seed.json"
    _write_seed(seed_path)

    first = generate_ops_selection_artifacts(
        as_of="2026-03-08",
        project_root=tmp_path,
        seed_json=seed_path,
        strict=True,
    )
    first_import = Path(first["import_log"]).read_text(encoding="utf-8")
    first_waybill = Path(first["waybill_log"]).read_text(encoding="utf-8")
    first_manifest = Path(first["archive_manifest"]).read_text(encoding="utf-8")

    second = generate_ops_selection_artifacts(
        as_of="2026-03-08",
        project_root=tmp_path,
        seed_json=seed_path,
        strict=True,
    )

    assert first["archive_input_dir"] == second["archive_input_dir"]
    assert Path(second["import_log"]).read_text(encoding="utf-8") == first_import
    assert Path(second["waybill_log"]).read_text(encoding="utf-8") == first_waybill
    assert Path(second["archive_manifest"]).read_text(encoding="utf-8") == first_manifest
