#!/usr/bin/env python3
"""Build a DB-independent WebUI shipped-event projection from pack + ledger lineage."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.webui_archive_truth_utils import DEFAULT_LEDGER_ROOT, load_pack_rows, load_status_ledger, resolve_latest_dir

DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "webui_projection"


class WebuiShippedProjectionError(RuntimeError):
    """Raised when the shipped projection cannot be built deterministically."""


def _resolve_ledger_root(ledger_root: Path | None) -> Path:
    if ledger_root is None:
        return resolve_latest_dir(DEFAULT_LEDGER_ROOT)
    candidate = ledger_root.expanduser()
    if candidate.exists():
        return candidate.resolve()
    alt = DEFAULT_LEDGER_ROOT / candidate
    if alt.exists():
        return alt.resolve()
    raise FileNotFoundError(f"ledger root not found: {ledger_root}")


def _resolve_pack_roots(ledger_manifest: dict[str, Any]) -> list[Path]:
    pack_roots = [Path(path).expanduser().resolve() for path in ledger_manifest.get("pack_roots", []) if str(path).strip()]
    if not pack_roots:
        raise WebuiShippedProjectionError("ledger manifest missing pack_roots")
    return pack_roots


def _last_nonblank(series: pd.Series) -> str:
    values = [str(value).strip() for value in series.tolist() if str(value).strip()]
    return values[-1] if values else ""


def _first_nonblank(series: pd.Series) -> str:
    values = [str(value).strip() for value in series.tolist() if str(value).strip()]
    return values[0] if values else ""


def build_webui_shipped_projection(
    *,
    ledger_root: Path,
    output_root: Path,
    run_id: str,
    start: str,
    end: str,
) -> dict[str, Any]:
    resolved_ledger_root = _resolve_ledger_root(ledger_root)
    ledger, ledger_manifest = load_status_ledger(resolved_ledger_root)
    pack_roots = _resolve_pack_roots(ledger_manifest)
    pack_frames = [load_pack_rows(path) for path in pack_roots]
    pack_rows = (
        pd.concat(pack_frames, ignore_index=True)
        if pack_frames
        else pd.DataFrame()
    )
    if pack_rows.empty:
        raise WebuiShippedProjectionError("pack rows are empty")

    returned_keys = {
        (str(row["store_code"]).strip().upper(), str(row["order_id"]).strip())
        for _, row in ledger.iterrows()
        if str(row.get("returned_at") or "").strip()
    }
    delivered_rows = pack_rows[pack_rows["status_internal"].astype(str) == "DELIVERED"].copy()
    if delivered_rows.empty:
        raise WebuiShippedProjectionError("pack contains 0 delivered rows")
    delivered_rows["_order_key"] = list(
        zip(
            delivered_rows["store_code"].astype(str).str.strip().str.upper(),
            delivered_rows["order_id"].astype(str).str.strip(),
        )
    )
    delivered_rows = delivered_rows[~delivered_rows["_order_key"].isin(returned_keys)].copy()

    order_event = (
        delivered_rows.groupby(["store_code", "order_id"], as_index=False)
        .agg(
            planned_courier_at=("planned_courier_at", _last_nonblank),
            created_at=("created_at", "min"),
            delivered_at=("status_change_at", _last_nonblank),
            article=("article", _first_nonblank),
            first_seen_pack=("pack_id", "min"),
            last_seen_pack=("pack_id", "max"),
        )
    )
    order_event["event_date_source"] = order_event["planned_courier_at"].astype(str).str.strip().map(
        lambda value: "planned_courier_at" if value else "created_at_fallback"
    )
    order_event["sale_date"] = order_event["planned_courier_at"].where(
        order_event["planned_courier_at"].astype(str).str.strip() != "",
        order_event["created_at"],
    )
    eligible_orders = order_event[
        (order_event["sale_date"].astype(str) >= str(start))
        & (order_event["sale_date"].astype(str) <= str(end))
    ].copy()

    projection = delivered_rows.merge(
        eligible_orders[
            [
                "store_code",
                "order_id",
                "sale_date",
                "event_date_source",
                "planned_courier_at",
                "created_at",
                "delivered_at",
                "first_seen_pack",
                "last_seen_pack",
            ]
        ],
        on=["store_code", "order_id"],
        how="inner",
        suffixes=("", "_order"),
    )
    projection = projection.rename(
        columns={
            "quantity": "units",
            "planned_courier_at_order": "webui_planned_courier_at",
            "created_at_order": "webui_created_at",
            "delivered_at": "webui_delivered_at",
        }
    )
    projection["units"] = pd.to_numeric(projection["units"], errors="coerce").fillna(0.0)
    projection["net_rev_kzt"] = pd.to_numeric(projection["net_rev_kzt"], errors="coerce").fillna(0.0)
    projection["truth_source"] = "webui_archive"
    projection["truth_event"] = "shipped_projection"
    projection = projection[
        [
            "store_code",
            "order_id",
            "sale_date",
            "event_date_source",
            "article",
            "units",
            "net_rev_kzt",
            "truth_source",
            "truth_event",
            "webui_planned_courier_at",
            "webui_created_at",
            "webui_delivered_at",
            "first_seen_pack",
            "last_seen_pack",
            "source_file",
            "source_row_number",
        ]
    ].sort_values(["sale_date", "store_code", "order_id", "article", "source_row_number"])

    run_root = output_root.resolve() / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    projection_csv = run_root / "webui_shipped_projection.csv"
    projection.to_csv(projection_csv, index=False, encoding="utf-8")

    manifest = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "run_id": run_id,
        "ledger_root": str(resolved_ledger_root),
        "pack_roots": [str(path) for path in pack_roots],
        "period": {"start": start, "end": end},
        "projected_rows": int(len(projection)),
        "projected_orders": int(projection["order_id"].nunique()) if not projection.empty else 0,
        "orders_returned_excluded": int(len(returned_keys)),
        "orders_with_planned_courier_at": int(
            eligible_orders["event_date_source"].eq("planned_courier_at").sum()
        ),
        "orders_with_created_fallback": int(
            eligible_orders["event_date_source"].eq("created_at_fallback").sum()
        ),
        "projection_csv": str(projection_csv),
    }
    manifest_path = run_root / "projection_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "run_root": run_root,
        "projection_csv": projection_csv,
        "projection_manifest_path": manifest_path,
        "projection_manifest": manifest,
        "projection": projection,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build WebUI shipped projection from pack+ledger lineage")
    parser.add_argument("--ledger-root", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", default=f"webui_shipped_projection_{datetime.now():%Y%m%d}")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        report = build_webui_shipped_projection(
            ledger_root=args.ledger_root,
            output_root=args.output_root,
            run_id=str(args.run_id),
            start=str(args.start),
            end=str(args.end),
        )
    except WebuiShippedProjectionError as exc:
        print("status=FAIL")
        print("error_code=WEBUI_SHIPPED_PROJECTION_FAIL")
        print(f"message={exc}")
        return 1

    print(f"projection_csv={report['projection_csv']}")
    print(f"projection_manifest_json={report['projection_manifest_path']}")
    print("status=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
