# Agent814 - Ads Current Source Packet

Gate target: `GREEN` if current ads source evidence is captured or proven enough for the next copied-temp ads replay route; `YELLOW` if a safe live-readonly source command or required account/source remains missing.

## Bootstrap Context

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-15_post_order_entry_next_phase_proof_wave/PLAN.md`
4. `~/Docs/Autonomous_business/exports/validation/order_entry_apply_and_daily_survival_parallel/20260515_085748/agent810_ads_storeb_gap/ADS_STOREB_GAP_STATUS.md`
5. `~/Docs/Autonomous_business/docs/validation/ADS_WEB_AUTOMATION_SOURCE_PACKET_CONTRACT.md`
6. `~/Docs/Autonomous_business/docs/validation/ADS_ACTIVE_SCOPE_CONTRACT.md`
7. this starter prompt

Sibling Agents812, 813, 815, and 816 are parallel. Do not wait for them.

## Human-Approved Live-Readonly Scope

The human owner approved live-readonly ads source capture for STOREB, ACMEWEAR, and required Meta/Facebook evidence for the current window. This authorizes read-only source fetching and local evidence packet creation only.

It does not authorize Web_automation mutation, ad-platform writes, bid/budget changes, DB production writes, owner publication, price, stock, cash, PO, workbook, or scheduler mutation.

## Assignment

Build the current ads source packet/status for `2026-05-12..2026-05-15` or the tightest current window required by validators.

Must preserve:

- `business_store_code=STOREB`
- `access_store_code=UNIVERSAL_SWITCHER_FOR_STOREB`
- ACMEWEAR ads source separate from STOREB
- Meta/Facebook evidence separate from Kaspi internal marketing

Write evidence only under:

`~/Docs/Autonomous_business/exports/validation/post_order_entry_next_phase_proof_wave/20260515_0920/agent814_ads_current_source_packet/`

Required output:

`~/Docs/Autonomous_business/exports/validation/post_order_entry_next_phase_proof_wave/20260515_0920/agent814_ads_current_source_packet/ADS_CURRENT_SOURCE_PACKET_STATUS.md`

Closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-15_post_order_entry_next_phase_proof_wave/agent814_ads_current_source_packet_closeout.md`

## Expected Checks

- Validate any source packet with `scripts/validate_ads_source_packet_contract.py` when a manifest exists.
- Run ads sidecar/source freshness validators read-only or against copied DB only.
- Keep offer-universe/spend-reality separate from source-freshness. Passing coverage is not source freshness.

## Boundaries

Read-only source capture and local evidence writes only. No Web_automation mutation, source-pointer mutation, production DB writes, workbook writes, scheduler changes, external writes, owner publication, ad-platform writes, bid/budget changes, price, stock, cash, or PO action.

Gate: GREEN
