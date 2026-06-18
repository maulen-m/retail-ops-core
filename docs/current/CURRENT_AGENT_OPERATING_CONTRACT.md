# CURRENT_AGENT_OPERATING_CONTRACT

Status: ACTIVE_PHASE0_ROUTE_INDEX
Created: 2026-05-21

This contract describes how agents operate while the Autonomous Business repo moves toward the 10/10 target. It does not grant write authority to protected business surfaces.

## Agent Roles

| role | authority | write boundary |
| --- | --- | --- |
| Main Orchestrator | Owns sequencing, integration, blocker board, gate matrix, and final closeout. | May write approved docs/current, run docs, and minimal `.claude/*` status logs for this Phase 0 lane. |
| Read-only analyst agents | Inspect evidence and publish independent reports. | May write only their assigned out-of-repo closeout files unless the prompt says otherwise. |
| Write-capable execution agent | Performs the single serialized shared repo write lane when approved. | Writes only inside its assigned scope; no protected-surface writes without exact authority. |
| CodeCaptain | Independent review for big authority gates. | No local mutation authority. |
| Human Owner | Grants exact approvals for production, external, automation, cash, PO, stock, price, owner-publication, and business-risk decisions. | Human approvals must be literal enough to bind scope. |

## Closeout Authority

- Tmux completion pings are wake-up signals only.
- The closeout file plus a standalone `Gate:` line is the source for agent completion status.
- A green closeout for a routing artifact does not imply production green, publication green, scheduler green, or final 10/10 green.
- If an agent reports YELLOW or RED, the blocker must remain visible until a later gate actually clears it.

## Parallel Rules

- Default mode is one write-capable execution agent plus read-only analysts.
- Analysts do not read each other's first-pass reports before publishing.
- Shared repo-state writes are serialized.
- DB writes are serialized, backup-first, and require explicit production authority.
- If multiple agents run, each task must name its owner output, source gate, or capital-risk blocker.

## Fail-Closed Rules

- Missing source data is not zero.
- Copied-temp proof is not production truth.
- Scoped proof is not full-scope proof.
- Offer availability is not physical stock.
- Workbook/dashboard/export logic is not business-rule authority.
- Owner publication is blocked unless publication gates pass or retained blockers are visible and explicitly non-decision-grade.
- Production apply is blocked until copied-temp proof, CodeCaptain-reviewed preflight, exact owner phrase, env gate, `--apply`, backup, rollback, and post-apply validation are all present.

## Current Phase Labels

| label | meaning |
| --- | --- |
| `PHASE0_CANONICAL_ROUTE_GREEN` | Docs/current is complete and required Phase 0 gates pass. |
| `PHASE0_YELLOW_ROUTE_INCOMPLETE` | Route exists but a required docs/current row, gate, or file is missing or a Phase 0 gate failed. |
| `PHASE0_RED_AUTHORITY_CONFLICT` | Active authority conflicts and must be reviewed before continuation. |
