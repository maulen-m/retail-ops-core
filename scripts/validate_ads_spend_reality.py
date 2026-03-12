#!/usr/bin/env python3
"""Validate ads spend realism by month/store for sold universe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_ads_offer_universe_coverage import (
    AdsOfferCoverageError,
    validate_ads_offer_universe_coverage,
)


class AdsSpendRealityError(RuntimeError):
    """Raised when strict ads spend reality validation fails."""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate ads spend realism by month/store.")
    parser.add_argument("--start", default="2026-01-01")
    parser.add_argument("--end", default="2026-02-29")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--db-path", default="db/app.db")
    parser.add_argument("--truth-source", choices=["db", "webui_archive"], default="db")
    parser.add_argument("--ledger-root", type=Path, default=None)
    parser.add_argument("--as-of", default="2026-03-06")
    parser.add_argument("--stores-config", default="config/kaspi_stores.yaml")
    parser.add_argument("--gap-quarantine-config", type=Path, default=None)
    parser.add_argument("--max-ads-to-net-rev-ratio", type=float, default=0.8)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser


def validate_ads_spend_reality(
    *,
    start: str,
    end: str,
    strict: bool,
    db_path: Path,
    truth_source: str = "db",
    ledger_root: Path | None = None,
    as_of: str = "2026-03-06",
    stores_config: Path,
    gap_quarantine_config: Path | None = None,
    max_ads_to_net_rev_ratio: float,
    output_dir: Path | None = None,
) -> dict[str, object]:
    output_dir = (
        output_dir
        if output_dir is not None
        else (
            REPO_ROOT / "exports" / "validation" / "webui_archive_single_truth" / as_of
            if truth_source == "webui_archive"
            else REPO_ROOT / "exports" / "validation" / "crm_north_star_restate" / "2026-03-06"
        )
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    coverage_input_dir = output_dir / "_ads_spend_reality_offer_input"
    coverage_input_dir.mkdir(parents=True, exist_ok=True)

    payload = validate_ads_offer_universe_coverage(
        start=start,
        end=end,
        strict=False,
        min_coverage=0.0,
        max_ads_to_net_rev_ratio=float(max_ads_to_net_rev_ratio),
        db_path=db_path,
        truth_source=truth_source,
        ledger_root=ledger_root,
        as_of=as_of,
        stores_config=stores_config,
        gap_quarantine_config=gap_quarantine_config,
        output_dir=coverage_input_dir,
        truth_output_dir=output_dir,
    )

    spend_reality_fail_pairs = int(payload.get("spend_reality_fail_pairs", 0))
    truth_errors = payload.get("truth_errors") or []
    status = "PASS" if spend_reality_fail_pairs == 0 and not truth_errors else "FAIL"
    report_json = output_dir / "ads_spend_reality_report.json"
    report_md = output_dir / "ads_spend_reality_report.md"
    out: dict[str, object] = {
        "status": status,
        "strict": strict,
        "truth_source": truth_source,
        "period": {"start": start, "end": end},
        "gap_quarantine_config": (
            str(gap_quarantine_config.resolve()) if gap_quarantine_config is not None else None
        ),
        "max_ads_to_net_rev_ratio": float(max_ads_to_net_rev_ratio),
        "spend_reality_fail_pairs": spend_reality_fail_pairs,
        "truth_errors": truth_errors,
        "source_offer_coverage_report_json": payload["outputs"]["ads_offer_universe_report_json"],
        "outputs": {
            "ads_spend_reality_by_month_store_csv": payload["outputs"]["ads_spend_reality_by_month_store_csv"],
            "ads_spend_reality_report_json": str(report_json.resolve()),
            "ads_spend_reality_report_md": str(report_md.resolve()),
        },
    }
    report_json.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    report_md.write_text(
        "\n".join(
            [
                "# Ads Spend Reality",
                "",
                f"- period: `{start}`..`{end}`",
                f"- status: `{status}`",
                f"- truth_source: `{truth_source}`",
                f"- max_ads_to_net_rev_ratio: `{float(max_ads_to_net_rev_ratio)}`",
                f"- spend_reality_fail_pairs: `{spend_reality_fail_pairs}`",
                f"- truth_errors: `{len(truth_errors)}`",
                f"- source_offer_coverage_report_json: `{out['source_offer_coverage_report_json']}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    if strict and status != "PASS":
        raise AdsSpendRealityError(
            (
                "Ads spend reality failed: "
                f"spend_reality_fail_pairs={spend_reality_fail_pairs}, truth_errors={len(truth_errors)}"
            )
        )
    return out


def main() -> int:
    args = _build_parser().parse_args()
    try:
        payload = validate_ads_spend_reality(
            start=args.start,
            end=args.end,
            strict=args.strict,
            db_path=Path(args.db_path),
            truth_source=str(args.truth_source),
            ledger_root=args.ledger_root,
            as_of=str(args.as_of),
            stores_config=Path(args.stores_config),
            gap_quarantine_config=args.gap_quarantine_config,
            max_ads_to_net_rev_ratio=float(args.max_ads_to_net_rev_ratio),
            output_dir=args.output_dir,
        )
    except (AdsSpendRealityError, AdsOfferCoverageError) as exc:
        print(str(exc))
        return 1
    print(f"ads_spend_reality_report_json={payload['outputs']['ads_spend_reality_report_json']}")
    print(f"status={payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
