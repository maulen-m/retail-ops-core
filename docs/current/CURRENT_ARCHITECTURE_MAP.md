# CURRENT_ARCHITECTURE_MAP

Status: ACTIVE_PHASE0_ROUTE_INDEX
Created: 2026-05-21

This file describes the current operating architecture for routing agents. It does not replace `ARCHITECTURE.md`, data-model docs, inventory docs, or validator contracts.

## Layer Map

```text
External/manual sources
  -> accepted source contracts and source packets
  -> copied-temp materialization and validators
  -> production preflight packet, only after proof review
  -> serialized production apply, only after exact owner phrase
  -> repeated-run, scheduler, and owner-publication gates
```

## Current Stack

| layer | owns | current route |
| --- | --- | --- |
| Source acquisition | Kaspi API/WebUI, WebUI ArchiveOrders, ads, bank/manual cash, inbound workbook, physical stock, supplier/PO evidence | Read-only or copied-temp only unless exact owner authority exists. |
| Source contracts | Substitutions, exclusions, retained blockers, proof scope, forbidden claims | `docs/contracts/mvos_source_contracts/ACTIVE_MVOS_SOURCE_CONTRACT_REGISTRY.json` |
| Operational truth | Business facts and event tables | `db/app.db`, production-write blocked in Phase 0. |
| Materialization | Import/bridge/source packet transforms | Must stay dry-run/read-only or copied-temp unless production apply is explicitly authorized. |
| Validators | Gate truth and stoplines | `scripts/validate_*.py`, test fixtures, and copied-temp proof boards. |
| Derived outputs | Dashboards, exports, owner reports, workbook views | Must not silently recompute formulas or hide retained blockers. |
| Automation | LaunchAgents, cron, daily order processing, board and Telegram workflows | Currently paused under evidence; resume requires exact owner labels/groups. |

## Execution Topology

Default topology from `docs/PARALLEL_EXECUTION_PROTOCOL.md`:

- Main Orchestrator owns shared repo-state changes and closeout.
- Read-only analysts inspect and write only to out-of-repo handoff folders.
- Only one write-capable execution lane may write shared repo state at a time.
- DB writes must be serialized and backup-first.
- Tmux completion pings are wake-up signals only; the closeout file plus standalone `Gate:` line is the authority.

## Active Scope Distinction

| scope | meaning | current use |
| --- | --- | --- |
| `MVOS_SCOPE_ACTIVE_BUSINESS_THREE_STORE` | STOREB, ACMEWEAR, UNIVERSAL | Current operating proof route where declared. |
| `MVOS_SCOPE_FULL_FIVE_STORE` | STOREB, ACMEWEAR, UNIVERSAL, 11KZ, MELVIS | Cannot be claimed unless five-store status-ledger and source gates pass. |

Scoped proof must preserve the scope label downstream. A scoped green is never a full-business green unless the full scope actually passes.

## Survival Ops Vs 10/10 Cleanup

| track | purpose | rule |
| --- | --- | --- |
| Daily survival operations | Ship daily orders and keep business workflow alive | Can resume only with exact owner-approved automation labels/groups and live safety checks. |
| 10/10 cleanup | Source truth, validators, proof, production readiness, owner publication | Runs from frozen/read-only/copied-temp state unless an exact write authority opens a lane. |
