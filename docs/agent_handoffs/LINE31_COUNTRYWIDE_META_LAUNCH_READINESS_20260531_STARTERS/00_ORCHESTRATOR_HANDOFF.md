# Orchestrator Handoff - LINE31 Countrywide Meta Launch Readiness

Created: 2026-05-31 21:06 +05

Gate: ROOT_READY_NO_LIVE_WRITES

## Objective

Launch a tmux-orchestrated, no-live-write implementation wave that tailors the Strategy Expert LINE31 countrywide Meta tracking plan to the internal repos.

The wave should produce launch-readiness scaffold, tracking QA, read-only internal Kaspi context, daily bridge reporting, and a final readiness packet. It must not launch Meta, deploy the website, mutate Kaspi/WebUI/API/CRM/Meta, pause LINE31 internal Kaspi marketing, change seller bonus, or change price/stock/cash/PO/supplier surfaces.

## Canonical Plan

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-31_line31_countrywide_meta_launch_readiness/PLAN.md`

## Starter Folder

`~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_COUNTRYWIDE_META_LAUNCH_READINESS_20260531_STARTERS`

## Shared Handoff Folder

`~/Docs/Autonomous_business_agent_handoffs/2026-05-31_line31_countrywide_meta_launch_readiness`

## Source Inputs

- Strategy answer: `~/Docs/Oracle/Autonomous_business/2026-05-31/193438_TASK-000_line31-countrywide-meta-tracking-expert-plan/Answer/Strategy_expert_31.05.2026_20_33_01.md`
- Expert assets: `~/Docs/Oracle/Autonomous_business/2026-05-31/193438_TASK-000_line31-countrywide-meta-tracking-expert-plan/Answer/LINE31_countrywide_meta_launch_readiness_pack_20260531`
- Cashflow cockpit workbook: `~/Docs/Oracle/Autonomous_business/2026-05-30/131112_TASK-000_cashflow-po-decision-workbook-external-eval-20260530/Answer/assets_of_answer/ACMEWEAR_cashflow_inventory_po_decision_cockpit_20260530.xlsx`

## Current Owner Authorization

The user asked to implement the plan after reviewing the approval boundary. Treat this as authorization for repo-local docs/scripts/tests, read-only source inspection, dry-run scaffold, local evidence generation, and tmux-orchestrated execution only.

It does not authorize production DB writes, production workbook writes, scheduler or source-pointer changes, website deploys, Meta/Kaspi/WebUI/API/CRM mutations, campaign bid/budget/state/creative/audience changes, price changes, stock changes, cash movement, supplier payment, PO commitment, owner publication, internal LINE31 Kaspi isolation, or Meta publish.

## Launch Order

Launch Agents 1-4 in parallel:

- Agent 1: Facebook_ads LINE31 Meta scaffold.
- Agent 2: acmewear_web_v2 landing and tracking QA.
- Agent 3: Web_automation read-only LINE31 internal Kaspi context.
- Agent 4: Autonomous_business LINE31 daily bridge report.

Do not launch Agent 5 until Agents 1-4 write closeouts and the orchestrator reviews the gates.

Launch Agent 5 after root review:

- Agent 5: final readiness synthesis and next approval packet.

## Assigned Closeouts

- Agent 1: `~/Docs/Autonomous_business_agent_handoffs/2026-05-31_line31_countrywide_meta_launch_readiness/agent1_facebook_ads_scaffold_closeout.md`
- Agent 2: `~/Docs/Autonomous_business_agent_handoffs/2026-05-31_line31_countrywide_meta_launch_readiness/agent2_acmewear_web_tracking_qa_closeout.md`
- Agent 3: `~/Docs/Autonomous_business_agent_handoffs/2026-05-31_line31_countrywide_meta_launch_readiness/agent3_web_automation_line31_context_closeout.md`
- Agent 4: `~/Docs/Autonomous_business_agent_handoffs/2026-05-31_line31_countrywide_meta_launch_readiness/agent4_ab_daily_bridge_closeout.md`
- Agent 5: `~/Docs/Autonomous_business_agent_handoffs/2026-05-31_line31_countrywide_meta_launch_readiness/agent5_line31_readiness_synthesis_closeout.md`

## Anti-Drift Rules

- Do not treat the Strategy Expert answer as live approval.
- Do not publish Meta campaigns or create Meta custom conversions live.
- Do not deploy `acmewear.pro` or mutate Cloudflare.
- Do not pause, disable, isolate, or edit LINE31 internal Kaspi campaigns or seller bonus.
- Do not change prices, stocks, offers, pricelists, campaigns, budgets, bids, creatives, or promo state.
- Do not write production DB or production workbooks.
- Do not call website events `Purchase`.
- Do not claim deterministic Meta purchase attribution while internal LINE31 Kaspi surfaces remain active.

## Launch Lines

Root agents:

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_COUNTRYWIDE_META_LAUNCH_READINESS_20260531_STARTERS/01_AGENT_1__FACEBOOK_ADS_SCAFFOLD__PARALLEL_ROOT.md.
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_COUNTRYWIDE_META_LAUNCH_READINESS_20260531_STARTERS/02_AGENT_2__ACMEWEAR_WEB_TRACKING_QA__PARALLEL_ROOT.md.
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_COUNTRYWIDE_META_LAUNCH_READINESS_20260531_STARTERS/03_AGENT_3__WEB_AUTOMATION_LINE31_CONTEXT__PARALLEL_ROOT.md.
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_COUNTRYWIDE_META_LAUNCH_READINESS_20260531_STARTERS/04_AGENT_4__AB_DAILY_BRIDGE_REPORT__PARALLEL_ROOT.md.
```

Final synthesis, locked until Agents 1-4 close out:

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_COUNTRYWIDE_META_LAUNCH_READINESS_20260531_STARTERS/05_AGENT_5__READINESS_SYNTHESIS__AFTER_1_2_3_4.md.
```

## Suggested Tmux Commands

Register the current orchestrator chat if a human-visible ping is desired:

```bash
python3 ~/.codex/skills/tmux-agent-orchestrator/scripts/register_orchestrator_chat.py --repo ~/Docs/Autonomous_business --pane "$TMUX_PANE"
```

Launch root agents:

```bash
python3 ~/.codex/skills/tmux-agent-orchestrator/scripts/launch_tmux_agents.py \
  --repo ~/Docs/Autonomous_business \
  --starter-folder ~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_COUNTRYWIDE_META_LAUNCH_READINESS_20260531_STARTERS \
  --session autonomous_business \
  --window-name line31_meta_readiness \
  --orchestrator-ping-mode receiver \
  --auto-create-orchestrator-receiver \
  --orchestrator-pane AUTO \
  --visibility-pane LIVE \
  --agents 1,2,3,4 \
  --agent-command codex \
  --mode hybrid \
  --parallel-groups 1=root,2=root,3=root,4=root
```

After Agents 1-4 close out, launch Agent 5 manually or via the manifest:

```bash
python3 ~/.codex/skills/tmux-agent-orchestrator/scripts/send_agent_prompt.py --manifest <manifest_path> --agent 5
```
