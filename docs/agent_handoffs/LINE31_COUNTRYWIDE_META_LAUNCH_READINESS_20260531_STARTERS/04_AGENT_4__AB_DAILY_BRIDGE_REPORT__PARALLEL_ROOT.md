# Agent 4 Starter - Autonomous_business LINE31 Daily Bridge Report

You are Agent 4. Your lane builds a local LINE31 launch-readiness bridge report from cash, stock, order, redirect, and campaign-context inputs. No production DB or workbook write is authorized.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-31_line31_countrywide_meta_launch_readiness/PLAN.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_COUNTRYWIDE_META_LAUNCH_READINESS_20260531_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_COUNTRYWIDE_META_LAUNCH_READINESS_20260531_STARTERS/04_AGENT_4__AB_DAILY_BRIDGE_REPORT__PARALLEL_ROOT.md`

## Source Inputs

Read:

1. `~/Docs/Oracle/Autonomous_business/2026-05-31/193438_TASK-000_line31-countrywide-meta-tracking-expert-plan/Answer/LINE31_countrywide_meta_launch_readiness_pack_20260531/DAILY_CASHFLOW_REPORTING_SPEC.csv`
2. `~/Docs/Oracle/Autonomous_business/2026-05-31/193438_TASK-000_line31-countrywide-meta-tracking-expert-plan/Answer/LINE31_countrywide_meta_launch_readiness_pack_20260531/LAUNCH_GATES_AND_MONITORING_RULES.md`
3. `~/Docs/Oracle/Autonomous_business/2026-05-31/193438_TASK-000_line31-countrywide-meta-tracking-expert-plan/Answer/LINE31_countrywide_meta_launch_readiness_pack_20260531/ATTRIBUTION_AND_ISOLATION_POLICY.md`
4. `~/Docs/Oracle/Autonomous_business/2026-05-30/131112_TASK-000_cashflow-po-decision-workbook-external-eval-20260530/Answer/assets_of_answer/ACMEWEAR_cashflow_inventory_po_decision_cockpit_20260530.xlsx`
5. Relevant current Autonomous_business LINE31 product truth, WebUI archive, order, stock, and cashflow docs/scripts from the repo router.

## Scope

Allowed writes:

- repo-local docs/scripts/tests/config in `~/Docs/Autonomous_business` only when they support local LINE31 readiness reporting;
- local generated evidence under `~/Docs/Autonomous_business/exports/validation/line31_countrywide_meta_launch_readiness_20260531/agent4_daily_bridge/`;
- assigned closeout under the shared handoff folder.

Forbidden:

- production `db/app.db` writes;
- production workbook writes;
- source-pointer/scheduler changes;
- Meta/Kaspi/WebUI/API/CRM/platform mutations;
- price, stock, cash, supplier, payment, PO, owner-publication, website deploy, or campaign actions.

## Task

Build a local dry-run LINE31 daily bridge report contract and proof output.

Required metrics:

- Meta spend, LPV, website events, server redirects, and HighIntent when available from local/read-only sources;
- LINE31 order intake and final/economic order truth with source labels;
- LINE31 internal Kaspi campaign/promo context as context only;
- LINE31 sellable stock and reserve/not-for-sale treatment;
- cash after reserve, SHR payable exposure, and budget safety using the owner-ready cashflow cockpit workbook;
- launch-day freshness flags and action gates.

Keep these separate:

- actual source-backed values;
- modelled/projected values;
- owner-entered assumptions;
- stale/unavailable values.

If a script is added, it must default to dry-run/local-output behavior and never mutate production DB/workbooks.

## Required Outputs

Write these under your local evidence folder:

- `line31_daily_bridge_report.csv`
- `line31_cash_stock_gate.json`
- `line31_source_freshness_matrix.csv`
- `line31_bridge_contract.md`
- `COMMANDS_RUN.tsv`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-31_line31_countrywide_meta_launch_readiness/agent4_ab_daily_bridge_closeout.md`

The closeout must include:

- standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`;
- exact files created/changed;
- validation commands run;
- protected production DB/workbook hash evidence if inspected;
- explicit confirmation that no production DB/workbook write was performed.

Use `GREEN` only if the bridge report is generated and source freshness is clearly labeled. Use `YELLOW` if key current sources are missing/stale. Use `RED` for production mutation or mixed truth labels.
