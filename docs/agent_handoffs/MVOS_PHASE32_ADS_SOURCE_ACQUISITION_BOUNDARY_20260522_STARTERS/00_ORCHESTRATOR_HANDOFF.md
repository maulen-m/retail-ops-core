# MVOS Phase32 Ads Source Acquisition Boundary - Orchestrator Handoff

Status: `READY_AFTER_EXACT_OWNER_APPROVAL_OR_CODECAPTAIN_CLEARANCE`

This starter pack exists so the next source acquisition wave can launch quickly without weakening the current yellow stopline.

Do not launch these agents unless the owner has pasted the exact Phase32 approval phrase from:

`~/Docs/Autonomous_business/docs/parallel_runs/2026-05-22_mvos_phase32_ads_source_acquisition_boundary/PHASE32_ADS_SOURCE_ACQUISITION_BOUNDARY.md`

## Sequence

| Agent | Prompt | Dependency | Gate required |
| --- | --- | --- | --- |
| 32A | `01_AGENT_32A__KASPI_MARKETING_CURRENT_PACKET__PARALLEL_AFTER_APPROVAL.md` | exact Phase32 owner approval or CodeCaptain clearance | `GREEN` packet or `YELLOW` exact blocker |
| 32B | `02_AGENT_32B__META_FACEBOOK_CURRENT_PACKET__PARALLEL_AFTER_APPROVAL.md` | exact Phase32 owner approval or CodeCaptain clearance | `GREEN` packet or `YELLOW` exact blocker |
| 32C | `03_AGENT_32C__AB_COPIED_TEMP_ADS_RERUN__AFTER_32A_32B_GREEN.md` | 32A `GREEN` and 32B `GREEN` | copied-temp validators pass or `YELLOW` exact retained blockers |

Agents 32A and 32B may run in parallel after approval. Agent 32C must not run unless both source packets are `GREEN` and protected-surface checks pass.

## Launch Lines

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_PHASE32_ADS_SOURCE_ACQUISITION_BOUNDARY_20260522_STARTERS/01_AGENT_32A__KASPI_MARKETING_CURRENT_PACKET__PARALLEL_AFTER_APPROVAL.md.
```

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_PHASE32_ADS_SOURCE_ACQUISITION_BOUNDARY_20260522_STARTERS/02_AGENT_32B__META_FACEBOOK_CURRENT_PACKET__PARALLEL_AFTER_APPROVAL.md.
```

After 32A and 32B are both `GREEN`:

```text
Read the repo bootstrap context and execute ~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_PHASE32_ADS_SOURCE_ACQUISITION_BOUNDARY_20260522_STARTERS/03_AGENT_32C__AB_COPIED_TEMP_ADS_RERUN__AFTER_32A_32B_GREEN.md.
```
