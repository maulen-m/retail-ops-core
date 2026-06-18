# Orchestrator Handoff: MVOS Post-CodeCaptain Source-Contract Addition Wave

Workflow slug: `mvos_post_codecaptain_source_contract_addition_wave_20260517`

Canonical plan:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_post_codecaptain_source_contract_addition_wave/PLAN.md`

Starter folder:

`~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_POST_CODECAPTAIN_SOURCE_CONTRACT_ADDITION_WAVE_20260517_STARTERS`

Shared handoff folder:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-17_mvos_post_codecaptain_source_contract_addition_wave`

Evidence root:

`~/Docs/Autonomous_business/exports/validation/mvos_post_codecaptain_source_contract_addition_wave/20260517_210554`

Tmux execution manifest:

`~/Docs/Autonomous_business/runs/tmux_orchestration/mvos_post_cc_source_contract_20260517_211200/orchestration_manifest.json`

Dependent synthesis manifest:

`~/Docs/Autonomous_business/runs/tmux_orchestration/mvos_post_cc_synthesis_20260517_212300/orchestration_manifest.json`

Owner-QA priority integrated plan after CodeCaptain 22:06:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-17_mvos_post_codecaptain_source_contract_addition_wave/OWNER_QA_PRIORITY_INTEGRATED_PLAN_AFTER_CODECAPTAIN_220628.md`

Execution note:

The first attempt to create a new tmux window failed with `Too many open files` under the current macOS/tmux file limit. The orchestrator therefore reused completed Codex panes instead of spawning additional processes.

## Parallel Metadata

Root group `post_cc_source_contract_root`:

- `868`: ads DirectAPI plus Meta/Facebook scope addition, pane `%544`.
- `869`: payment evidence root or no-new-payment contract, pane `%543`.
- `870`: lifecycle cancellation WebUI/API contract, pane `%542`.
- `871`: status-ledger provenance and store-scope contract, pane `%541`.
- `872`: PO/day-complete blocker correction or scoped contract, pane `%540`.
- `873`: COGS route, tactical parent COGS, and ChildSum component-economics contract, pane `%526`.

Dependent group `after_868_869_870_871_872_873`:

- `874`: synthesis, copied-temp proof decision, and CodeCaptain packet draft, pane `%539`.

## Launch Lines

Root agents:

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_POST_CODECAPTAIN_SOURCE_CONTRACT_ADDITION_WAVE_20260517_STARTERS/01_AGENT_868__ADS_DIRECTAPI_META_SCOPE__PARALLEL_ROOT.md.
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_POST_CODECAPTAIN_SOURCE_CONTRACT_ADDITION_WAVE_20260517_STARTERS/02_AGENT_869__PAYMENT_EVIDENCE_CONTRACT__PARALLEL_ROOT.md.
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_POST_CODECAPTAIN_SOURCE_CONTRACT_ADDITION_WAVE_20260517_STARTERS/03_AGENT_870__LIFECYCLE_CANCELLATION_CONTRACT__PARALLEL_ROOT.md.
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_POST_CODECAPTAIN_SOURCE_CONTRACT_ADDITION_WAVE_20260517_STARTERS/04_AGENT_871__STATUS_LEDGER_SCOPE_PROVENANCE__PARALLEL_ROOT.md.
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_POST_CODECAPTAIN_SOURCE_CONTRACT_ADDITION_WAVE_20260517_STARTERS/05_AGENT_872__PO_DAY_COMPLETE_SCOPE__PARALLEL_ROOT.md.
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_POST_CODECAPTAIN_SOURCE_CONTRACT_ADDITION_WAVE_20260517_STARTERS/06_AGENT_873__COGS_CHILDSUM_ROUTE__PARALLEL_ROOT.md.
```

Dependent synthesis:

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_POST_CODECAPTAIN_SOURCE_CONTRACT_ADDITION_WAVE_20260517_STARTERS/07_AGENT_874__SYNTHESIS_COPIED_TEMP_PROOF__AFTER_868_869_870_871_872_873.md.
```

## Orchestrator Rules

- Treat closeout files with standalone `Gate:` lines as authority.
- Do not launch Agent874 until Agents868-873 close out and their closeouts are reviewed.
- If any root lane is `RED`, stop and write an orchestrator review instead of launching Agent874.
- If root lanes are mixed `GREEN`/`YELLOW`, Agent874 may synthesize but must preserve the final gate as `YELLOW` unless copied-temp validators genuinely pass.
- The final deliverable is a CodeCaptain-ready review pack or copied-temp proof result, not production apply.
