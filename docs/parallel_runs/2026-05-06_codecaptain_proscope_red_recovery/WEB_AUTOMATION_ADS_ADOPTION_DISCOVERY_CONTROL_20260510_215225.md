# Web Automation Ads Adoption Discovery Control

Generated: `2026-05-10T21:52:25+0500`

Status: `READY_TO_LAUNCH_MONITOR_ONLY_READONLY`

Gate: `GREEN_TO_LAUNCH_READONLY_DISCOVERY_ONLY`

## Purpose

Launch three read-only discovery agents to research what can be adopted from `~/Docs/Web_automation` to reduce the Autonomous Business `ADS_SOURCE_STALE` risk and improve the next ads-source coverage/freshness plan.

This is a discovery wave only. It does not authorize live fetches, owner publication, owner send, scheduler automation, production DB/workbook mutation, external writes, ad-platform writes, cash movement, PO commitment, price/stock changes, or owner approval requests.

## CodeCaptain Boundary

Latest CodeCaptain sequence answer:

`~/Docs/Oracle/Autonomous_business/2026-05-10/203425_TASK-000_codecaptain-business-decision-system-sequence-reevaluation/answer/Code_Captain_10.05.2026_21_29_24.md`

Decision:

`YELLOW_AMEND_SEQUENCE_BEFORE_NEXT_LANE`

Controlling amendment:

Operator acceptance or amendment of the Cash Risk Daily review surface must come before owner-publication readiness. This discovery wave is allowed only as read-only adoption research; it must not become owner-publication readiness, live ads refresh, scheduler work, or production implementation.

## Current Ads Truth

Current proof evidence:

`~/Docs/Autonomous_business/exports/validation/option_c_validate_only/cash_risk_daily_20260510_180607`

Current ads-side risk:

- `ADS_SOURCE_STALE`
- `ads_source_fresh`: `PASS`, details `mode=live reason=stale age_hours=859.25 max_age_hours=36.0`
- `ads_mapping_coverage`: `PASS`, `coverage_pct=100.0 threshold=85.0 total_cost_kzt=1616866.33 gate_enabled=true`
- `ads_offer_universe_coverage`: `PASS`, with `unmapped_positive_spend_ads=0`, `missing_sold_offers=0`, `quarantined_sold_offers=0`, `truth_errors=[]`

Interpretation:

The immediate ads blocker is primarily source freshness and adoption path, not current mapping coverage.

## Agents

| Agent | Role | Assigned closeout |
|---|---|---|
| `754` | Web_automation ads fetch/storage inventory | `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_754_web_ads_fetch_storage_inventory_closeout.md` |
| `755` | Web_automation freshness/watchers/checkpoints inventory | `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_755_web_ads_freshness_watchers_inventory_closeout.md` |
| `756` | Autonomous Business ads adoption mapper | `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_756_ab_ads_adoption_mapper_closeout.md` |

All three agents run in parallel and must publish independent first-pass closeouts before reading sibling reports.

## Write Boundary

Allowed writes:

- The assigned closeout file.
- Files inside the assigned evidence directory under `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_<id>_*_evidence/`.
- Tmux orchestrator completion marker JSON written by `agent_complete.py`.

Forbidden writes:

- `~/Docs/Autonomous_business/db/app.db`
- `~/Docs/Autonomous_business/excel_ui/SALES_KSP_CRM_V3.xlsx`
- Any file under `~/Docs/Web_automation`
- Any Web_automation `runs/`, `data/`, `exports/`, `.env`, storage state, credential, or browser profile file
- Any scheduler, LaunchAgent, plist, external system, browser automation, ad platform, Kaspi, Google, bank, Web_automation live write, or owner-facing surface

Forbidden actions:

- live Kaspi Marketing fetch
- live browser login
- DirectAPI control
- `web-auto ... --confirm`
- `web-auto ... live-readonly`
- any mutation command in either repo
- reading secrets from `.env`, storage state, cookies, or browser profiles

## Expected Synthesis After Closeouts

After all closeouts are present, the orchestrator should synthesize:

1. Whether Web_automation already has enough reusable fetch/storage/heartbeat components for an AB-side ads freshness adapter.
2. Whether the next safest step is:
   - operator acceptance gate first,
   - Web_automation live-readonly proof with explicit approval,
   - AB adapter design-only memo,
   - CodeCaptain pack for ads freshness adoption,
   - or no adoption due to unresolved safety gaps.
3. What exact artifacts should become the next source-of-truth handoff.
