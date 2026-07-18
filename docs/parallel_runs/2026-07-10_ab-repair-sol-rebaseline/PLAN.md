PLAN

Purpose

Rebaseline and safely repair the Autonomous_business green path and connected commerce truth without live business mutations.

Repo

- `~/Docs/Autonomous_business`

Canonical protocol

- `docs/PARALLEL_EXECUTION_PROTOCOL.md`

Read first

- `AGENTS.md`
- `docs/00_START_HERE.md`
- `docs/PARALLEL_EXECUTION_PROTOCOL.md`

Execution posture

- one write-capable execution agent
- two read-only analyst agents
- fail-closed
- no hidden provenance

Shared handoff folder

- `~/Docs/Autonomous_business_agent_handoffs/2026-07-10_ab-repair-sol-rebaseline`

As-of window

- `2026-07-10`

Role split

Agent A

- execution agent
- only writer in the repo
- production `db/app.db` mutation is NOT authorized in this run
- may write only approved local repo artifacts and isolated shadow/copy data
- reads analyst reports and executes the repair path

Agent B

- read-only analyst
- focus: Read-only audit of current 71-gate, acceptance, blocker, cash/OPEX, validator-safety, and stale-run-state evidence. No repo, DB, scheduler, workbook, or external writes.

Agent C

- read-only analyst
- focus: Read-only cross-repo audit of LINE51 ads scale-up, Web_automation marketing/offer truth, shipping no-send readiness, direct CRM, Sourcing, and relevant M5 handoffs. No API or repo writes.

First-pass independence rule

- Agent B publishes before reading Agent C
- Agent C publishes before reading Agent B
- Agent A consumes both reports
- second-pass cross-review happens only if Agent A explicitly requests it

Required handoff files

- `README.md`
- `status_board.md`
- `agent_b_report.md`
- `agent_c_report.md`
- `agent_a_execution_log.md`

Launch order

1. Agent B
2. Agent C
3. Agent A after B and C publish first-pass reports

Stop rules

- analysts do not modify repo state
- no agent mutates production DB, workbook-source truth, schedulers, live orders/stock/prices/offers, Kaspi, Repricer, Meta, Google, Telegram, WhatsApp, payments, cash/PO systems, customer communications, or any external system
- uncertain validators run only in an isolated shadow checkout or remain explicitly unverified
- no agent sends keys to tmux panes or submits staged pane input; pane `%242` is especially protected
- historical owner approvals and the superseded `20260709_234642` run authorize nothing in this run
- no source swap without explicit provenance

Generated from

- `python3 scripts/init_parallel_rollout.py`
- repo `Autonomous_business`
- run dir `~/Docs/Autonomous_business/docs/parallel_runs/2026-07-10_ab-repair-sol-rebaseline`
