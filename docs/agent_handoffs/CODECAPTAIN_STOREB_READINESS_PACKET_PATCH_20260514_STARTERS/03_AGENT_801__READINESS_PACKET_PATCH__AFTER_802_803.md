# Agent 801 - Readiness Packet Patch Execution

Before executing, read:
1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`
4. `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-14_codecaptain-storeb-readiness-packet-patch/PLAN.md`
5. `~/Docs/Autonomous_business/docs/agent_handoffs/CODECAPTAIN_STOREB_READINESS_PACKET_PATCH_20260514_STARTERS/03_AGENT_801__READINESS_PACKET_PATCH__AFTER_802_803.md`
6. `~/Docs/Oracle/Autonomous_business/2026-05-14/114527_TASK-000_frozen-window-option1-2-combined-copy-proof-final3/Answer/Code_Captain_14.05.2026_17_52_25.md`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-05-14_codecaptain-storeb-readiness-packet-patch/agent802_storeb_evidence_boundary_closeout.md`
8. `~/Docs/Autonomous_business_agent_handoffs/2026-05-14_codecaptain-storeb-readiness-packet-patch/agent803_preflight_command_boundary_closeout.md`

Assigned closeout:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-14_codecaptain-storeb-readiness-packet-patch/agent801_packet_patch_execution_closeout.md`

## Role

You are the only write-capable execution agent for this rollout.

You may edit only:

- `~/Docs/Autonomous_business/exports/validation/frozen_window_option1_2_combined_copy_proof/20260514_113412/production_readiness/ORDER_ENTRY_PRODUCTION_APPLY_READINESS_PACKET.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-14_codecaptain-storeb-readiness-packet-patch/agent_a_execution_log.md`
- `~/Docs/Autonomous_business_agent_handoffs/2026-05-14_codecaptain-storeb-readiness-packet-patch/status_board.md`
- your assigned closeout

Do not edit `db/app.db`, workbook files, scheduler files, config files, code files, tests, `.claude/*`, or external systems.

## Dependency Gate

Do not begin patching until both analyst closeouts exist and their standalone gate lines are not `RED`.

If either analyst closeout is missing or `RED`, write your closeout as blocked with `Gate: RED` or `Gate: YELLOW` and stop.

## Patch Requirements

Patch the readiness packet per CodeCaptain's YELLOW decision:

1. Add a section named `STOREB Refresh Evidence Boundary`.
2. Add a section named `Excluded From Owner Phrase Request`.
3. Add a pre-apply validator/sidecar requirement that the dry-run output explicitly reports the recovery source hierarchy.
4. Preserve that this packet is `DRAFT_ONLY_NOT_AUTHORIZED`.
5. Preserve that this does not authorize production apply, owner publication, workbook mutation, scheduler mutation, external writes, ad-platform writes, cash movement, PO commitment, stock changes, or price changes.
6. Preserve exact key counts unless an analyst report gives a reviewed reason to change them: `398` would/insert rows, `391` target order-store pairs, `0` quarantine rows.
7. Preserve the unresolved `31` completed STOREB orders missing `statusChangeDate`, including `918424218`, as outside the narrow production apply request.

Minimum language to include, adjusted only for grammar:

```text
The targeted STOREB refresh root may be used only as API raw order-entry line-item evidence for the strict order-entry materializer. It must not be used as order lifecycle truth, statusChangeDate truth, archive-completeness truth, cashflow trigger truth, owner-publication truth, ads truth, or policy-source freshness truth. The 31 completed STOREB orders missing statusChangeDate remain an unresolved source-quality issue outside this narrow production apply request. Production apply may proceed only if the current-production dry-run still returns strict pass, 398 would-insert entry rows, 391 target order-store pairs or reviewed-equivalent target set, 0 quarantine rows, no use of workbook or WebUI archive sources, source_mode=api_raw_order_entries_only, and status/lifecycle truth sourced from existing production DB order facts, not from the targeted refresh export.
```

```text
This owner phrase request, if later prepared, covers only DB order-entry recovery using reviewed API raw order-entry evidence. It does not approve owner publication, ads freshness, policy gate clearing, profit-after-ads, ad spend, cash movement, supplier payment, PO commitment, stock changes, price changes, workbook writes, scheduler changes, external writes, or ad-platform writes.
```

```text
The dry-run output must explicitly report the recovery source hierarchy and confirm API_RAW_ORDER_ENTRIES only, workbook_sources_used=false, webui_archive_sources_used=false, quarantine_rows=0, and no statusChangeDate fields from the targeted STOREB refresh are used as lifecycle authority.
```

## Verification

Run the smallest relevant checks:

- `scripts/lint_docs.sh`
- a grep/readback proving all new required section names and stopline phrases exist.

If `scripts/lint_docs.sh` is too broad or fails on unrelated existing docs, record that honestly and provide the focused grep/readback evidence.

## Required Output

Write the assigned closeout with:

- analyst closeouts consumed and gates;
- files edited;
- exact verification commands and results;
- whether production apply remains blocked;
- next action for orchestrator;
- standalone gate line: `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
