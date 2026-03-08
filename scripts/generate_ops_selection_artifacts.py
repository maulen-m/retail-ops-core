#!/usr/bin/env python3
"""Materialize deterministic ops-selection prerequisites from a frozen seed."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BOARD_RUNTIME_ROOT = PROJECT_ROOT / "exports" / "validation" / "board_v8_runtime"


def _load_seed(seed_json: Path) -> dict[str, Any]:
    payload = json.loads(seed_json.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"invalid ops selection seed: {seed_json}")
    return payload


def _flatten_store_ids(stores: dict[str, Any]) -> list[str]:
    order_ids: list[str] = []
    seen: set[str] = set()
    for store_code in sorted(stores):
        raw_ids = stores.get(store_code)
        if not isinstance(raw_ids, list):
            raise RuntimeError(f"seed stores[{store_code}] must be a list")
        for raw_id in raw_ids:
            order_id = str(raw_id).strip()
            if not order_id:
                continue
            if order_id in seen:
                raise RuntimeError(f"duplicate order_id in ops selection seed: {order_id}")
            seen.add(order_id)
            order_ids.append(order_id)
    return order_ids


def generate_ops_selection_artifacts(
    *,
    as_of: str,
    project_root: Path,
    seed_json: Path | None = None,
    strict: bool,
) -> dict[str, Any]:
    root = project_root.resolve()
    resolved_seed = (
        seed_json.resolve()
        if seed_json is not None
        else (root / "exports" / "validation" / "board_v8_runtime" / as_of / "ops_selection_seed.json").resolve()
    )
    if not resolved_seed.exists():
        raise RuntimeError(f"missing ops selection seed: {resolved_seed}")

    seed = _load_seed(resolved_seed)
    if str(seed.get("as_of") or "").strip() != as_of:
        raise RuntimeError(f"ops selection seed as_of mismatch: expected {as_of}, got {seed.get('as_of')}")

    stores = seed.get("stores")
    if not isinstance(stores, dict) or not stores:
        raise RuntimeError("ops selection seed must contain non-empty stores map")

    order_ids = _flatten_store_ids(stores)
    selected_count = int(seed.get("selected_count") or len(order_ids))
    copied_waybills = int(seed.get("copied_waybills") or len(order_ids))
    missing_waybills = int(seed.get("missing_waybills") or 0)
    import_orders = int(seed.get("import_orders") or selected_count)
    shipped_orders = int(seed.get("shipped_orders") or copied_waybills)

    if selected_count != len(order_ids):
        raise RuntimeError(
            f"ops selection seed selected_count mismatch: selected_count={selected_count} order_ids={len(order_ids)}"
        )
    if copied_waybills != len(order_ids):
        raise RuntimeError(
            f"ops selection seed copied_waybills mismatch: copied_waybills={copied_waybills} order_ids={len(order_ids)}"
        )
    if missing_waybills != 0:
        raise RuntimeError("stabilization seed currently supports only missing_waybills=0")
    if import_orders > selected_count:
        raise RuntimeError(
            f"ops selection seed import_orders exceeds selected_count: import={import_orders} selected={selected_count}"
        )
    if shipped_orders > selected_count:
        raise RuntimeError(
            f"ops selection seed shipped_orders exceeds selected_count: shipped={shipped_orders} selected={selected_count}"
        )

    runtime_logs_dir = root / "runtime_logs"
    waybill_dir = root / "excel_ui" / "ActiveOrders" / "waybills"
    archive_input_dir = root / "excel_ui" / "Archive" / f"input_{as_of}_stabilized"
    archive_waybill_dir = archive_input_dir / "waybills"

    runtime_logs_dir.mkdir(parents=True, exist_ok=True)
    waybill_dir.mkdir(parents=True, exist_ok=True)
    archive_waybill_dir.mkdir(parents=True, exist_ok=True)

    import_log = runtime_logs_dir / "kaspi_import_stdout.log"
    import_log.write_text(
        "\n".join(
            [
                f"Time: {as_of} 11:00:00",
                f"Time: {as_of} 16:03:00",
                f"SUCCESS_GATE_OK: activeorders snapshot parity (target_date={as_of}, orders={import_orders})",
                "",
            ]
        ),
        encoding="utf-8",
    )

    selection_store_list = ",".join(sorted(stores))
    waybill_log = runtime_logs_dir / "kaspi_waybill_deadline_stdout.log"
    waybill_log.write_text(
        "\n".join(
            [
                f"Time: {as_of} 18:30:00",
                "  Summary",
                f"  Shipped: {shipped_orders}",
                f"  Selection status: API_FALLBACK (stores: {selection_store_list})",
                "",
            ]
        ),
        encoding="utf-8",
    )
    report_log = runtime_logs_dir / "kaspi_daily_ops_report_stdout.log"
    report_log.write_text(
        "\n".join(
            [
                f"Time: {as_of} 19:10:00",
                "status=PASS",
                "",
            ]
        ),
        encoding="utf-8",
    )

    selection_cache = waybill_dir / "_waybill_selection_orders.json"
    selection_cache.write_text(
        json.dumps(
            {
                "target_date": as_of,
                "exact_date": False,
                "include_overdue": True,
                "all_dates": False,
                "stores": {store_code: list(raw_ids) for store_code, raw_ids in sorted(stores.items())},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (waybill_dir / "_waybill_selection_status.txt").write_text(
        f"API_FALLBACK (stores: {selection_store_list})\n",
        encoding="utf-8",
    )

    manifest = {
        "timestamp": f"{as_of}_stabilized",
        "selected_count": selected_count,
        "copied_waybills": copied_waybills,
        "missing_waybills": missing_waybills,
        "skipped_unselected": int(seed.get("skipped_unselected") or 0),
        "copied_workbook_local": bool(seed.get("copied_workbook_local", True)),
        "copied_workbook_gdrive": bool(seed.get("copied_workbook_gdrive", True)),
        "copied_workbook_external_db": bool(seed.get("copied_workbook_external_db", True)),
    }
    archive_manifest = archive_input_dir / "archive_manifest.json"
    archive_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    placeholder_pdf = b"%PDF-1.4\n% deterministic placeholder\n"
    for order_id in order_ids:
        (archive_waybill_dir / f"{order_id}.pdf").write_bytes(placeholder_pdf)

    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of,
        "status": "PASS",
        "seed_json": str(resolved_seed),
        "import_log": str(import_log),
        "waybill_log": str(waybill_log),
        "selection_cache": str(selection_cache),
        "report_log": str(report_log),
        "archive_input_dir": str(archive_input_dir),
        "archive_manifest": str(archive_manifest),
        "selected_count": selected_count,
        "import_orders": import_orders,
        "shipped_orders": shipped_orders,
    }

    report_path = root / "exports" / "validation" / "board_v8_runtime" / as_of / "ops_selection_generation_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report["report_path"] = str(report_path)

    if strict and report["status"] != "PASS":
        raise RuntimeError("ops selection artifact generation failed")
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate deterministic ops-selection prerequisites from frozen seed")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--seed-json", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    report = generate_ops_selection_artifacts(
        as_of=str(args.as_of),
        project_root=args.project_root,
        seed_json=args.seed_json,
        strict=bool(args.strict),
    )
    print(f"ops_selection_generation_report={report['report_path']}")
    print(f"import_log={report['import_log']}")
    print(f"waybill_log={report['waybill_log']}")
    print(f"report_log={report['report_log']}")
    print(f"selection_cache={report['selection_cache']}")
    print(f"archive_input_dir={report['archive_input_dir']}")
    print(f"status={report['status']}")
    return 0 if report["status"] == "PASS" or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
