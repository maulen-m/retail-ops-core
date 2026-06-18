#!/usr/bin/env python3
"""Report docs-before-code coverage for changed business-rule surfaces."""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "exports" / "validation" / "docs_before_code_review"


@dataclass(frozen=True)
class DomainRule:
    domain: str
    code_patterns: tuple[str, ...]
    owning_docs: tuple[str, ...]


DOMAIN_RULES: tuple[DomainRule, ...] = (
    DomainRule(
        "sales_cogs_profit",
        (
            "core/calc/**",
            "core/config/business_params.py",
            "core/db/sales_truth_query_guard.py",
            "core/ingest/**",
            "core/sales/**",
            "scripts/apply_956748585_freeze_cost_basis.py",
            "scripts/apply_exact_kaspi_api_order_entries.py",
            "scripts/apply_fact_sales_derived_replay.py",
            "scripts/apply_workbook_anchor_date_drift_repair.py",
            "scripts/generate_business_insides.py",
            "scripts/rebuild_sales_fact_v2_from_kaspi_entries.py",
            "scripts/materialize_stock_ledger_sales_from_sales_fact_v2.py",
            "scripts/validate_business_insides.py",
            "scripts/validate_cogs*.py",
            "scripts/validate_data_completeness.py",
            "scripts/validate_profit_publication_integrity.py",
            "scripts/apply_*cogs*.py",
            "scripts/apply_sales_fact*.py",
        ),
        (
            "docs/inventory/Sales_Data_Model_V16.md",
            "docs/validation/COGS_FORENSIC_REFERENCE_SUPERSESSION_DECISION.md",
            "docs/validation/DAY_COMPLETE_CONTRACT.md",
        ),
    ),
    DomainRule(
        "inventory_stock_po",
        (
            "core/excel/dim_sku_light_parser.py",
            "core/ops/manual_stock_count_manifest.py",
            "core/ops/policy_registry_c3.py",
            "scripts/clamp_negative_ledger.py",
            "scripts/*stock*.py",
            "scripts/*inventory*.py",
            "scripts/*inbound*.py",
            "scripts/*po*.py",
            "scripts/*sku*.py",
            "scripts/materialize_c3_policy_state.py",
            "scripts/materialize_policy_source_freshness.py",
            "scripts/validate_status_ledger_continuity.py",
            "config/transfer_ledger_sync.yaml",
        ),
        (
            "docs/inventory/Master_Inventory_Rules_v9.md",
            "docs/inventory/Sales_Data_Model_V16.md",
            "docs/protocol/active/PO_making_logic_v3.md",
            "docs/transfer_ledger/README.md",
        ),
    ),
    DomainRule(
        "cashflow",
        (
            "core/cashflow/**",
            "scripts/*cash*.py",
            "scripts/reconcile_on_delivery_settlement.py",
            "scripts/sync_transaction_receipts.py",
            "scripts/translate_orders_to_cashflow_events.py",
            "scripts/validate_opex_readiness.py",
            "scripts/validate_po_money_gate.py",
        ),
        (
            "docs/KASPI_ORDER_CASHFLOW_TRACKING.md",
            "docs/transfer_ledger/README.md",
        ),
    ),
    DomainRule(
        "daily_ops_waybill",
        (
            "core/integrations/google_ops_board.py",
            "core/integrations/telegram_bot.py",
            "core/sync/order_sync_engine.py",
            "scripts/*google_ops_board*.py",
            "scripts/*waybill*.py",
            "scripts/sync_kaspi_orders.py",
            "scripts/download_waybills_api.py",
            "scripts/build_daily_waybills.py",
        ),
        (
            "docs/DAILY_SOP.md",
            "docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md",
            "docs/ops/KASPI_DAILY_OPS_ORCHESTRATOR_RUNBOOK.md",
            "KASPI_API_INTEGRATION.md",
        ),
    ),
    DomainRule(
        "customer_size_chat",
        (
            "core/ops/customer_size_request.py",
            "scripts/*kaspi_customer*.py",
            "scripts/*customer_size*.py",
        ),
        (
            "docs/DAILY_SOP.md",
            "docs/ops/KASPI_DAILY_OPS_WORKFLOW_CONTRACT.md",
        ),
    ),
    DomainRule(
        "product_truth_catalog",
        (
            "core/product_truth/**",
            "config/product_truth*.json",
            "config/owner_decisions/*.json",
            "scripts/*product_truth*.py",
            "scripts/apply_owner_confirmed_article_map_overrides.py",
            "scripts/materialize_merchant_cabinet_offer_availability.py",
            "scripts/repair_rombik*.py",
            "scripts/validate_product_truth_canonicalization.py",
        ),
        (
            "docs/plan/green_path_2026-06/OWNER_DECISIONS_RECORDED.yaml",
            "docs/plan/green_path_2026-06/OWNER_DECISION_PACK.md",
            "docs/contracts/PRODUCT_TRUTH_CANONICALIZATION_2026_05_28.md",
            "docs/inventory/Master_Inventory_Rules_v9.md",
            "docs/inventory/Sales_Data_Model_V16.md",
        ),
    ),
    DomainRule(
        "webui_archive_truth",
        (
            "scripts/*webui_archive*.py",
            "scripts/playwright/download_kaspi_archive_webui.py",
            "core/parsers/kaspi_export_parser.py",
            "core/parsers/kaspi_parser.py",
            "config/anchors/*.json",
            "config/anchors/kaspi_webui_archive_downloads.json",
        ),
        (
            "docs/validation/WEBUI_ARCHIVE_AUTONOMOUS_REFRESH_WORKFLOW.md",
            "docs/validation/WEBUI_ARCHIVE_SINGLE_TRUTH_CONTRACT.md",
            "docs/validation/KASPI_ARCHIVE_UI_PACK_CONTRACT.md",
        ),
    ),
    DomainRule(
        "fx_rates",
        (
            "config/cogs_forensic_reference.yaml",
            "scripts/*fx*.py",
            "scripts/validate_cogs_realism_vs_forensic.py",
        ),
        (
            "docs/protocol/active/FX_RATES_MECHANISM_V1.md",
            "docs/validation/COGS_FORENSIC_REFERENCE_SUPERSESSION_DECISION.md",
        ),
    ),
    DomainRule(
        "alerts_scheduler_day_complete",
        (
            "core/validation/day_complete.py",
            "scripts/run_end_of_day.py",
            "scripts/run_strict_daily_preflight.py",
            "scripts/validate_day_complete.py",
            "scripts/validate_single_truth*.py",
            "scripts/validate_transfer_ledger_sync_freshness.py",
            "config/write_side_gating_manifest.yaml",
        ),
        (
            "docs/validation/DAY_COMPLETE_CONTRACT.md",
            "docs/validation/WEBUI_ARCHIVE_SINGLE_TRUTH_CONTRACT.md",
            "docs/DAILY_SOP.md",
        ),
    ),
    DomainRule(
        "ads_line31_marketing",
        (
            "scripts/*ads*.py",
            "scripts/*line31*.py",
            "config/ads*.yaml",
            "docs/plan_line31*.py",
        ),
        (
            "docs/validation/LINE31_SPEND_VS_STOCK_GUARD.md",
            "docs/validation/LINE31_FINAL_CREATIVE_LAUNCH_READINESS_CONTRACT.md",
            "docs/validation/LINE31_POST_EXPERT_STRICT_PUBLISH_GATE_ADDENDUM_20260602.md",
        ),
    ),
    DomainRule(
        "returns_quarantine",
        (
            "scripts/*return*.py",
            "scripts/*quarantine*.py",
            "scripts/validate_returns_economics_audit.py",
        ),
        (
            "docs/inventory/Sales_Data_Model_V16.md",
            "docs/inventory/Master_Inventory_Rules_v9.md",
        ),
    ),
    DomainRule(
        "repo_guard_docs",
        (
            "core/db/validation_copy.py",
            "config/business_automation_manifest.json",
            "config/validation/**",
            "scripts/check_validation_disk_runway.py",
            "scripts/cleanup_validation_db_artifacts.py",
            "scripts/create_copied_temp_db.py",
            "scripts/identity_stabilization_common.py",
            "scripts/lint_docs*.py",
            "scripts/materialize_copied_temp_source_freshness_bridge.py",
            "scripts/plan_validation_db_cleanup.py",
            "scripts/preflight_copied_temp_wave.py",
            "scripts/report_docs_before_code_review.py",
            "scripts/run_phase2_june15_production_apply.py",
            "scripts/triage_owner_truth_stoplines.py",
            "scripts/audit_dashboard_output.py",
            "scripts/validate_mvos_source_contract_registry.py",
            "scripts/validate_no_help_command_writes.py",
            "scripts/validate_params.py",
            "scripts/validate_write_side_gating.py",
            "tests/test_lint_docs_contract.py",
        ),
        (
            "docs/validation/DOCS_BEFORE_CODE_CHANGE_REVIEW.md",
            "docs/validation/LINE31_SPEND_VS_STOCK_GUARD.md",
            "docs/ops/BUSINESS_AUTOMATION_CONTROL_RUNBOOK.md",
            "docs/authority/INDEX.md",
            "docs/00_START_HERE.md",
        ),
    ),
)


IGNORE_PATTERNS = (
    ".claude/**",
    "claude/**",
    "db/**",
    "exports/**",
    "imports/**",
    "logs/**",
    "runtime/**",
    "tests/**",
    "docs/**",
    "*.md",
    "*.csv",
    "*.json",
    "*.sqlite",
    "*.db",
)

SOURCE_PATTERNS = (
    "core/**/*.py",
    "scripts/**/*.py",
    "scripts/*.py",
    "config/*.json",
    "config/**/*.yaml",
    "config/**/*.yml",
    "config/**/*.json",
)


def _now_token() -> str:
    return datetime.now(timezone(timedelta(hours=5))).strftime("%Y%m%d_%H%M%S")


def _matches(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def _run_git(root: Path, args: list[str]) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def discover_changed_files(root: Path) -> list[str]:
    tracked = _run_git(root, ["diff", "--name-only"])
    untracked = _run_git(root, ["ls-files", "--others", "--exclude-standard"])
    return sorted(dict.fromkeys([*tracked, *untracked]))


def is_reviewable_source(path: str) -> bool:
    if _matches(path, SOURCE_PATTERNS):
        return True
    if _matches(path, IGNORE_PATTERNS):
        return False
    return False


def classify_review(
    changed_files: list[str],
    *,
    rules: tuple[DomainRule, ...] = DOMAIN_RULES,
) -> dict[str, Any]:
    changed = sorted(dict.fromkeys(changed_files))
    changed_set = set(changed)
    reviewable = [path for path in changed if is_reviewable_source(path)]
    ignored = [path for path in changed if path not in reviewable]

    domain_rows: list[dict[str, Any]] = []
    matched_files: set[str] = set()
    for rule in rules:
        files = [path for path in reviewable if _matches(path, rule.code_patterns)]
        if not files:
            continue
        matched_files.update(files)
        updated_docs = [doc for doc in rule.owning_docs if doc in changed_set]
        domain_rows.append(
            {
                "domain": rule.domain,
                "changed_files": files,
                "owning_docs": list(rule.owning_docs),
                "updated_owning_docs": updated_docs,
                "status": "doc_updated" if updated_docs else "needs_doc_review",
            }
        )

    unmatched = [path for path in reviewable if path not in matched_files]
    blockers: list[str] = []
    for row in domain_rows:
        if row["status"] == "needs_doc_review":
            blockers.append(f"{row['domain']}: no owning doc changed")
    for path in unmatched:
        blockers.append(f"unmatched business-rule source/config: {path}")

    return {
        "ok": not blockers,
        "schema_version": "docs_before_code_change_review.v1",
        "changed_file_count": len(changed),
        "reviewable_source_count": len(reviewable),
        "ignored_file_count": len(ignored),
        "changed_files": changed,
        "reviewable_source_files": reviewable,
        "ignored_files": ignored,
        "domains": domain_rows,
        "unmatched_reviewable_source_files": unmatched,
        "blockers": blockers,
    }


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Docs-Before-Code Change Review",
        "",
        f"- Generated at: `{payload['generated_at']}`",
        f"- Gate: `{'GREEN' if payload['ok'] else 'ARMED'}`",
        f"- Changed files: `{payload['changed_file_count']}`",
        f"- Reviewable source/config files: `{payload['reviewable_source_count']}`",
        f"- Blockers: `{len(payload['blockers'])}`",
        "",
        "## Domain Rows",
        "",
        "| Domain | Status | Changed Files | Updated Owning Docs |",
        "|---|---|---:|---|",
    ]
    for row in payload["domains"]:
        lines.append(
            "| {domain} | {status} | {count} | {docs} |".format(
                domain=row["domain"],
                status=row["status"],
                count=len(row["changed_files"]),
                docs=", ".join(row["updated_owning_docs"]) or "",
            )
        )
    lines.extend(["", "## Blockers", ""])
    if payload["blockers"]:
        lines.extend(f"- {blocker}" for blocker in payload["blockers"])
    else:
        lines.append("- None")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_report(
    *,
    project_root: Path,
    output_dir: Path,
    changed_files: list[str] | None = None,
) -> dict[str, Any]:
    root = project_root.resolve()
    changed = changed_files if changed_files is not None else discover_changed_files(root)
    payload = classify_review(changed)
    payload.update(
        {
            "generated_at": datetime.now(timezone(timedelta(hours=5))).isoformat(timespec="seconds"),
            "project_root": str(root),
        }
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "docs_before_code_change_review.json"
    md_path = output_dir / "docs_before_code_change_review.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_markdown(md_path, payload)
    payload["output_json"] = str(json_path)
    payload["output_markdown"] = str(md_path)
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Report docs-before-code coverage for changed files")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT / _now_token(),
    )
    parser.add_argument("--changed-file", action="append", default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    payload = build_report(
        project_root=args.project_root,
        output_dir=args.output_dir,
        changed_files=list(args.changed_file) if args.changed_file else None,
    )
    summary = {
        "ok": payload["ok"],
        "output_json": payload["output_json"],
        "output_markdown": payload["output_markdown"],
        "reviewable_source_count": payload["reviewable_source_count"],
        "blocker_count": len(payload["blockers"]),
    }
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("docs_before_code_review: OK" if payload["ok"] else "docs_before_code_review: BLOCKED")
        print(f"output_json: {payload['output_json']}")
        print(f"blockers: {len(payload['blockers'])}")
    return 1 if args.strict and not payload["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
