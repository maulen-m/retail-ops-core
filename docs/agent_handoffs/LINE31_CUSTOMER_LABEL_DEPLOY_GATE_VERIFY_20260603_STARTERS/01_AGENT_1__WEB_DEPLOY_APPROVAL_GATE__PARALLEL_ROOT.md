# Agent 1: LINE31 Web Deploy Approval Gate

Gate Target: GREEN if the deploy packet is internally consistent and the only blocker is the owner approval hash mismatch; YELLOW if evidence is incomplete or contradictory; RED if any live write/deploy is attempted.

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_CUSTOMER_LABEL_DEPLOY_GATE_VERIFY_20260603_STARTERS/00_ORCHESTRATOR_HANDOFF.md`
4. `~/Docs/Autonomous_business/docs/agent_handoffs/LINE31_CUSTOMER_LABEL_DEPLOY_GATE_VERIFY_20260603_STARTERS/01_AGENT_1__WEB_DEPLOY_APPROVAL_GATE__PARALLEL_ROOT.md`

## Scope

Read-only and local evidence only. Do not deploy. Do not run `wrangler deploy`. Do not post live QA events. Do not mutate website, Meta, Kaspi, DB, workbook, scheduler, source pointers, cash, PO, stock, or price.

## Inputs

- Website packet: `~/Docs/acmewear_web_v2/docs/90_REPORTS/line31_customer_label_deploy_liveqa_approval_20260603_214427/deploy_preflight_manifest.json`
- Website closeout: `~/Docs/acmewear_web_v2/docs/90_REPORTS/line31_customer_label_deploy_liveqa_approval_20260603_214427/deploy_preflight_closeout.md`
- Autonomous Business mirror: `~/Docs/Autonomous_business/exports/validation/line31_web_deploy_approval_packet_20260603_customer_label_214427/deploy_preflight_manifest.json`
- Current status pointer: `~/Docs/Autonomous_business/docs/current/LINE31_LAUNCH_CURRENT_STATUS.json`
- Owner-pasted hash from chat: `d545a308136352b8561c933e101c1ad1cf5e62a3d6c73b421d36af60d1dc47f92049`
- Expected packet build hash: `d545a308136352b856b0200bc39add9fbb3c6b2bd85a4d6f3a2502369284f817`

## Work

1. JSON-parse both deploy manifests.
2. Recompute current `workspace/landing_build/dist` tree SHA256 using the same deterministic method recorded by the orchestrator if practical.
3. Confirm local source/dist has no customer-visible `ACMEWEAR LINE31` or `AcmeWear LINE31` outside explicit forbidden-copy guard/evidence text.
4. Read-only `curl -skL --max-time 20 https://acmewear.pro/line31` and record whether live still contains old copy and whether it contains `AcmeWear 3в1`.
5. Compare owner-pasted hash with packet build hash and state whether deployment is authorized. Expected: not authorized due hash mismatch.
6. Write closeout to:

```text
~/Docs/Autonomous_business_agent_handoffs/2026-06-03_line31_customer_label_deploy_gate_verify/agent1_web_deploy_approval_gate_closeout.md
```

## Closeout Requirements

The closeout must include:

- standalone line `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`
- exact packet build hash
- exact owner-pasted hash
- deploy authorized: true/false
- live old-copy present: true/false
- live new-copy present: true/false
- exact corrected approval phrase if deployment is not authorized only due hash mismatch
- commands run
- explicit statement that no deploy or live write was performed
