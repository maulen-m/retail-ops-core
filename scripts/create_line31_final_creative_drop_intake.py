#!/usr/bin/env python3
"""Create a local LINE31 final creative drop-intake folder without publishing."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_line31_final_creative_mapping import (  # noqa: E402
    DEFAULT_MAPPING,
)
from scripts.validate_line31_launch_readiness import (  # noqa: E402
    DEFAULT_EVIDENCE_ROOT,
)

ALMATY_TZ = ZoneInfo("Asia/Almaty")
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation"
DEFAULT_APPROVAL_PHRASE_PATH = (
    DEFAULT_EVIDENCE_ROOT / "final_creative_publish_intake_and_approval.md"
)
FINAL_CHECK_COMMANDS = [
    "python3 scripts/build_line31_current_noncreative_gate_matrix.py --json",
    "python3 scripts/validate_line31_owner_objective_source_freshness.py --json",
    "python3 scripts/build_line31_launch_preflight_packet.py --json",
    "python3 scripts/audit_line31_active_goal_completion.py --json",
    "python3 scripts/validate_line31_final_creative_mapping.py",
    "python3 scripts/validate_line31_launch_readiness.py",
]
ADVISORY_REPO_HEALTH_COMMANDS = [
    "python3 scripts/validate_params.py --strict",
    "python3 scripts/run_end_of_day.py --dry-run --skip-api-sync --verbose",
]
FINAL_MAPPING_REQUIRED_FIELDS = [
    "assets[0].creative_id",
    "assets[0].final_asset_uri",
    "assets[0].thumbnail_path_or_uri",
    "assets[0].landing_url",
    "assets[0].kaspi_marketplace_cta_url",
    "assets[0].video_sha256",
    "assets[0].duration_seconds",
    "assets[0].aspect_ratio",
    "assets[0].language",
    "assets[0].primary_cta",
    "assets[0].utm_content",
    "assets[0].utm_placement",
    "creative_ready_declaration_received",
    "publish_authority.approved",
    "publish_authority.approval_evidence_path",
    "publish_authority.approval_evidence_sha256",
    "tracking_redirect_qa.gate",
    "tracking_redirect_qa.evidence_path",
    "tracking_redirect_qa.evidence_sha256",
]


def _write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _mapping_only_command(*, asset_dir: Path, final_asset_uri: str) -> str:
    return (
        "python3 scripts/prepare_line31_final_creative_mapping.py "
        "--creative-id line31_countrywide_v1 "
        f"--asset-dir {asset_dir} "
        f"--final-asset-uri {final_asset_uri} "
        "--duration-seconds 18 "
        "--utm-placement reels "
        "--landing-url 'https://acmewear.pro/line31' "
        "--kaspi-marketplace-cta-url 'https://kaspi.kz/shop/p/REPLACE_WITH_FINAL_LINE31_PRODUCT_SLUG/' "
        "--creative-ready-declared "
        "--tracking-qa-evidence-file /absolute/path/to/current_line31_tracking_redirect_qa.json "
        f"--output {DEFAULT_EVIDENCE_ROOT / DEFAULT_MAPPING.name} "
        "--overwrite"
    )


def _one_shot_command(*, asset_dir: Path, approval_text_file: Path, final_asset_uri: str) -> str:
    return (
        "python3 scripts/prepare_line31_launch_readiness_from_assets.py "
        "--creative-id line31_countrywide_v1 "
        f"--asset-dir {asset_dir} "
        f"--final-asset-uri {final_asset_uri} "
        "--duration-seconds 18 "
        "--utm-placement reels "
        "--landing-url 'https://acmewear.pro/line31' "
        "--kaspi-marketplace-cta-url 'https://kaspi.kz/shop/p/REPLACE_WITH_FINAL_LINE31_PRODUCT_SLUG/' "
        "--creative-ready-declared "
        f"--approval-text-file {approval_text_file} "
        "--tracking-qa-evidence-file /absolute/path/to/current_line31_tracking_redirect_qa.json "
        "--overwrite "
        "--json"
    )


def _readme(
    *,
    generated_at: str,
    intake_dir: Path,
    asset_dir: Path,
    approval_text_file: Path,
    final_asset_uri: str,
) -> str:
    mapping_command = _mapping_only_command(
        asset_dir=asset_dir,
        final_asset_uri=final_asset_uri,
    )
    one_shot_command = _one_shot_command(
        asset_dir=asset_dir,
        approval_text_file=approval_text_file,
        final_asset_uri=final_asset_uri,
    )
    checklist_path = intake_dir / "FINAL_CREATIVE_DROP_CHECKLIST.json"
    return f"""# LINE31 Final Creative Drop Intake

Generated: {generated_at}

Purpose: provide one clean local folder for the final LINE31 countrywide Meta creative assets and exact owner approval evidence. This folder is intake-only. It does not publish, mutate Meta/Kaspi/WebUI/API, change campaign state, change price/stock/cash/PO, write production DB/workbook, or authorize owner publication.

## What To Put Here

1. Put exactly one final video file into:

`{asset_dir}`

2. Put exactly one final thumbnail image into the same folder.

3. Paste the exact owner approval phrase into:

`{approval_text_file}`

Do not use the approval placeholder until the final creative mapping is filled and verified.

4. Provide a current LINE31 tracking/redirect QA JSON evidence file and pass it as
`--tracking-qa-evidence-file`. Strict publish readiness requires this file's
`gate=GREEN` plus a matching SHA-256 in the mapping.

## Supported Asset Extensions

Video: `.mp4`, `.mov`, `.m4v`, `.webm`

Thumbnail: `.png`, `.jpg`, `.jpeg`, `.webp`

The helpers fail closed if the asset folder contains zero or multiple candidate videos/thumbnails.

## Machine-Readable Checklist

Use this first when assigning or executing the final-assets lane:

`{checklist_path}`

## Replace Before Running

Commands below intentionally contain `REPLACE_WITH...` placeholders. Do not run
them as-is for launch. Replace the final video URI and Kaspi product slug first;
strict validators reject placeholder/demo URLs.

## Mapping-Only Command

Validate the folder first. This rejects ambiguous media, placeholder asset URLs, and optional approval-text mistakes before the one-shot helper writes the mapping:

```bash
python3 scripts/validate_line31_final_creative_drop_intake.py --asset-dir {asset_dir} --final-asset-uri {final_asset_uri} --kaspi-marketplace-cta-url 'https://kaspi.kz/shop/p/REPLACE_WITH_FINAL_LINE31_PRODUCT_SLUG/' --json
```

Use this if you want to create the mapping first and record approval later:

```bash
{mapping_command}
```

## Preferred One-Shot Command

Use this after the exact owner approval phrase has been pasted into the approval file:

```bash
{one_shot_command}
```

## Launch-Blocking Final Checks

```bash
{chr(10).join(FINAL_CHECK_COMMANDS)}
```

## Advisory Repo Health Checks

These commands keep broader Autonomous_business health visible, but they are
not LINE31 launch-blocking unless the current non-creative matrix maps a failure
to `scope=line31_launch_blocking`.

```bash
{chr(10).join(ADVISORY_REPO_HEALTH_COMMANDS)}
```

## Canonical Paths

- Intake folder: `{intake_dir}`
- Final assets folder: `{asset_dir}`
- Approval placeholder: `{approval_text_file}`
- Approval phrase source: `{DEFAULT_APPROVAL_PHRASE_PATH}`
- Mapping output: `{DEFAULT_EVIDENCE_ROOT / DEFAULT_MAPPING.name}`
"""


def _checklist(
    *,
    generated_at: str,
    intake_dir: Path,
    asset_dir: Path,
    approval_text_file: Path,
    final_asset_uri: str,
) -> dict[str, Any]:
    return {
        "generated_at": generated_at,
        "gate": "PENDING_FINAL_CREATIVE_ASSETS",
        "intake_dir": str(intake_dir),
        "asset_dir": str(asset_dir),
        "approval_text_file": str(approval_text_file),
        "mapping_output": str(DEFAULT_EVIDENCE_ROOT / DEFAULT_MAPPING.name),
        "approval_phrase_source": str(DEFAULT_APPROVAL_PHRASE_PATH),
        "required_asset_files": {
            "video": {
                "count": "exactly_one",
                "extensions": [".m4v", ".mov", ".mp4", ".webm"],
            },
            "thumbnail": {
                "count": "exactly_one",
                "extensions": [".jpeg", ".jpg", ".png", ".webp"],
            },
        },
        "required_mapping_fields": FINAL_MAPPING_REQUIRED_FIELDS,
        "placeholder_values_to_replace": [
            final_asset_uri,
            "https://kaspi.kz/shop/p/REPLACE_WITH_FINAL_LINE31_PRODUCT_SLUG/",
        ],
        "approval_policy": {
            "paste_exact_owner_phrase_only_after_mapping_ready": True,
            "standalone_approval_requires_mapping_ready": True,
            "strict_publish_requires_tracking_redirect_qa": True,
            "preferred_route": "prepare_line31_launch_readiness_from_assets.py one-shot",
        },
        "tracking_redirect_qa_policy": {
            "required_for_strict_publish": True,
            "evidence_file_argument": "--tracking-qa-evidence-file",
            "expected_gate": "GREEN",
            "sha256_recorded_in_mapping": True,
        },
        "safety_boundaries": {
            "publishes_meta": False,
            "mutates_kaspi_or_webui": False,
            "writes_production_db_or_workbook": False,
            "changes_campaign_price_stock_cash_or_po": False,
        },
        "internal_kaspi_policy": "KEEP_INTERNAL_KASPI_LINE31_CAMPAIGNS_ON_UNTIL_SEPARATE_OWNER_APPROVAL",
        "final_check_commands": FINAL_CHECK_COMMANDS,
        "advisory_repo_health_commands": ADVISORY_REPO_HEALTH_COMMANDS,
    }


def create_intake(args: argparse.Namespace) -> dict[str, Any]:
    generated_at = datetime.now(ALMATY_TZ).isoformat(timespec="seconds")
    run_id = args.run_id or datetime.now(ALMATY_TZ).strftime("%Y%m%d_%H%M%S")
    output_root = args.output_root.expanduser().resolve()
    intake_dir = output_root / f"line31_final_creative_drop_intake_{run_id}"
    if intake_dir.exists() and not args.overwrite:
        raise ValueError(f"intake folder exists; pass --overwrite to replace it: {intake_dir}")

    asset_dir = intake_dir / "final_assets"
    approval_dir = intake_dir / "approval"
    asset_dir.mkdir(parents=True, exist_ok=True)
    approval_dir.mkdir(parents=True, exist_ok=True)

    approval_text_file = approval_dir / "PASTE_EXACT_OWNER_APPROVAL_HERE.txt"
    if not approval_text_file.exists() or args.overwrite:
        _write_text(
            approval_text_file,
            (
                "Paste the exact LINE31 owner Meta publish approval phrase here only after "
                "final creative mapping is filled and verified.\n"
                f"Phrase source: {DEFAULT_APPROVAL_PHRASE_PATH}\n"
            ),
        )

    final_asset_uri = args.final_asset_uri_placeholder
    readme = _readme(
        generated_at=generated_at,
        intake_dir=intake_dir,
        asset_dir=asset_dir,
        approval_text_file=approval_text_file,
        final_asset_uri=final_asset_uri,
    )
    _write_text(intake_dir / "README.md", readme)
    checklist = _checklist(
        generated_at=generated_at,
        intake_dir=intake_dir,
        asset_dir=asset_dir,
        approval_text_file=approval_text_file,
        final_asset_uri=final_asset_uri,
    )
    checklist_path = intake_dir / "FINAL_CREATIVE_DROP_CHECKLIST.json"
    _write_json(checklist_path, checklist)

    manifest = {
        "generated_at": generated_at,
        "intake_dir": str(intake_dir),
        "asset_dir": str(asset_dir),
        "checklist_path": str(checklist_path),
        "approval_text_file": str(approval_text_file),
        "approval_phrase_path": str(DEFAULT_APPROVAL_PHRASE_PATH),
        "mapping_output": str(DEFAULT_EVIDENCE_ROOT / DEFAULT_MAPPING.name),
        "mapping_only_command": _mapping_only_command(
            asset_dir=asset_dir,
            final_asset_uri=final_asset_uri,
        ),
        "drop_validator_command": (
            "python3 scripts/validate_line31_final_creative_drop_intake.py "
            f"--asset-dir {asset_dir} "
            f"--final-asset-uri {final_asset_uri} "
            "--kaspi-marketplace-cta-url "
            "'https://kaspi.kz/shop/p/REPLACE_WITH_FINAL_LINE31_PRODUCT_SLUG/' "
            "--json"
        ),
        "one_shot_command": _one_shot_command(
            asset_dir=asset_dir,
            approval_text_file=approval_text_file,
            final_asset_uri=final_asset_uri,
        ),
        "final_check_commands": FINAL_CHECK_COMMANDS,
        "advisory_repo_health_commands": ADVISORY_REPO_HEALTH_COMMANDS,
        "final_asset_uri_placeholder": final_asset_uri,
        "commands_contain_placeholders": True,
        "replace_placeholders_before_launch": True,
        "no_external_writes_performed": True,
        "publish_authority_granted": False,
    }
    _write_json(intake_dir / "line31_final_creative_drop_intake_manifest.json", manifest)
    return manifest


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--final-asset-uri-placeholder",
        default="https://cdn.acmewear.kz/line31/REPLACE_WITH_FINAL_VIDEO.mp4",
        help="Placeholder URI to render in generated commands; replace before real launch.",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = create_intake(args)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(result["intake_dir"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
