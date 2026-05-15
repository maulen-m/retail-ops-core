# 2026-05-15 MVOS Execution Wave Plan

Created: `2026-05-15T11:11:24+0500`

Repo: `~/Docs/Autonomous_business`

## Source Decision

This plan implements the owner-approved `2026-05-15 MVOS execution envelope` after CodeCaptain's `GO` answer:

`~/Docs/Oracle/Autonomous_business/2026-05-15/0920_TASK-000_post-order-entry-next-phase-proof-wave-codecaptain/Answer/Code Captain_15.05.2026_11_07_20.md`

CodeCaptain target: launch a parallel read-only/copied-temp wave now, keep production writes separately gated, and produce the first survival-grade operating surface today.

## Current Accepted Boundary

Production DB SHA:

`9702c20cad71b808e52cf746c8574506aafe3f1f4d18fc6a2c48ee4880f98816`

Protected workbook SHA:

`eb873974e05247eb30f8db0ce3d38db430eaa9d17afa2d698e1345bae8d91ba0`

Order-entry recovery is already production-applied under prior authorization: `426` API-backed rows for `419` order-store pairs, `0` quarantine rows, workbook untouched.

## Owner Approval Boundary

Approved in chat:

```text
I approve the 2026-05-15 MVOS execution envelope in Autonomous_business: read-only analysis, copied-temp
proofs, validator reruns, Daily Survival Brief drafts, internal board updates, source freshness maps, and
one serialized repo code/test implementation lane at a time under orchestrator supervision. This does not
authorize production DB writes, workbook writes, scheduler/LaunchAgent/cron changes, external writes,
Web_automation writes, Kaspi/API writes, ad-platform writes, bank writes, owner publication/send, cash
movement, supplier payment, PO commitment, ad spend, stock changes, or price changes.
```

## Goal

Reach survival-grade MVOS usefulness today, not full automation. Success means the owner/operator gets a reliable current brief and command board with allowed, review, and blocked decisions backed by current DB/source proof.

## Launch Now

Parallel proof group `mvos_readonly_root`:

- Agent818: Daily Survival Brief v1.
- Agent819: Ads copied-temp adoption proof.
- Agent820: WebUI lifecycle/status copied-temp proof.
- Agent821: Sales-fact strict blocker resolver.
- Agent822: Cashflow source/cost packet.
- Agent823: PO/inbound decision proof analyst.
- Agent824: Exception queue copied-temp encoding proof.
- Agent825: Boundary/release anchor monitor.

Serialized implementation group `mvos_impl_slot`:

- Agent826: Stock-ledger materializer hardening. This is the only write-capable lane in this wave. It may edit code/tests only, may mutate copied DBs under its evidence root, and may not mutate production DB, workbook, scheduler, external systems, stock, price, cash, PO, ads, or owner-publication surfaces.

Hold until root review:

- Agent827: MVOS command-board and integration writer. Launch only after Agents818-826 closeouts are reviewed.

## Shared Paths

Starter folder:

`~/Docs/Autonomous_business/docs/agent_handoffs/MVOS_EXECUTION_WAVE_20260515_STARTERS/`

Evidence root:

`~/Docs/Autonomous_business/exports/validation/mvos_execution_wave/20260515_111124/`

Closeout root:

`~/Docs/Autonomous_business_agent_handoffs/2026-05-15_mvos_execution_wave/`

## Hard Stoplines

Stop immediately and write `Gate: RED` or `Gate: YELLOW` if:

- production `db/app.db` mutation is required or attempted;
- protected workbook mutation is required or attempted;
- scheduler, LaunchAgent, cron, or plist mutation is required or attempted;
- external write, Web_automation write, Kaspi/API write, ad-platform write, bank write, owner publication/send, cash movement, supplier payment, PO commitment, ad spend, stock change, or price change is required or attempted;
- STOREB business identity is collapsed into Universal access identity;
- missing ads/source rows are treated as zero spend without source-backed proof;
- header-only order-entry rows are productized into stock, sales, or cash truth;
- production anchor files are used as authority when the prompt requires explicit evidence paths;
- boundary hash, integrity, holder, or sidecar checks conflict with this accepted boundary.

## Completion Rules

Each agent writes its assigned closeout first with a standalone `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED` line, then runs the tmux orchestrator completion helper from the generated prompt footer.

The completion ping is only a wake-up signal. The closeout file and evidence root are the authority.

Gate: GREEN_TO_LAUNCH_AGENTS_818_826
