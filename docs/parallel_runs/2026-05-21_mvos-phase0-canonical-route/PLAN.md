PLAN

Purpose

Phase 0 canonical docs/current route with two read-only analysts before 10/10 implementation resumes

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

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-21_mvos-phase0-canonical-route`

As-of window

- `2026-05-21`

Role split

Agent A

- execution agent
- only writer in the repo
- only agent allowed to mutate `db/app.db`
- reads analyst reports and executes the repair path

Agent B

- read-only analyst
- focus: Read-only dirty diff, plan sprawl, doc canonicalization, supersession map

Agent C

- read-only analyst
- focus: Read-only retained blocker, source truth, gate matrix, owner/CodeCaptain request routing

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
- execution agent does not start DB mutation before upstream analysis unless running intentionally in single-agent mode
- no source swap without explicit provenance

Generated from

- `python3 scripts/init_parallel_rollout.py`
- repo `Autonomous_business`
- run dir `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-21_mvos-phase0-canonical-route`
