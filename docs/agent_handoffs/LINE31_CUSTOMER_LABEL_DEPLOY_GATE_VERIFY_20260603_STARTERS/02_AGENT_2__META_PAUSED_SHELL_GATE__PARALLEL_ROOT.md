# Agent 2: LINE31 Meta Paused Shell Gate

Gate Target: GREEN if Meta live read-only evidence confirms the campaign/adset are paused, daily budget is `3093`, and ad count is `0`; YELLOW if read-only evidence is incomplete; RED if any Meta write is attempted.

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_CUSTOMER_LABEL_DEPLOY_GATE_VERIFY_20260603_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_CUSTOMER_LABEL_DEPLOY_GATE_VERIFY_20260603_STARTERS/02_AGENT_2__META_PAUSED_SHELL_GATE__PARALLEL_ROOT.md`

## Scope

Read-only evidence only. Do not create/update/delete Meta campaigns, adsets, ads, creatives, budgets, states, or targeting. Do not mutate website, Kaspi, DB, workbook, scheduler, source pointers, cash, PO, stock, or price.

## Inputs

- Meta repo env: `~/Docs/Business_3/Facebook_ads/.env` (read token only; do not print secrets)
- Campaign ID: `120245481137650641`
- Adset ID: `120245481997290641`
- Expected current state:
  - campaign status/effective_status: `PAUSED`
  - adset status/effective_status: `PAUSED`
  - adset daily_budget: `3093`
  - ad count under campaign: `0`

## Work

1. Run a read-only Meta Graph API state check using the existing token without printing secrets.
2. Verify campaign status/effective_status.
3. Verify adset status/effective_status and daily budget.
4. Verify ad count under the campaign.
5. Write closeout to:

```text
~/Docs/Autonomous_business_agent_handoffs/2026-06-03_line31_customer_label_deploy_gate_verify/agent2_meta_paused_shell_gate_closeout.md
```

## Closeout Requirements

The closeout must include:

- standalone line `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`
- campaign status/effective_status
- adset status/effective_status
- adset daily_budget
- ad count
- commands run, with secrets redacted
- explicit statement that no Meta write was performed
