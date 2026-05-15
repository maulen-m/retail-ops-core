PLAN

Purpose

Patch the frozen-window order-entry production apply readiness packet per CodeCaptain YELLOW decision, with STOREB evidence boundary split from ads/policy/publication blockers.

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

- `~/Docs/Autonomous_business_agent_handoffs/2026-05-14_codecaptain-storeb-readiness-packet-patch`

As-of window

- `2026-05-14`

Role split

Agent A

- execution agent
- only writer in the repo
- only agent allowed to mutate `db/app.db`
- reads analyst reports and executes the repair path

Agent B

- read-only analyst
- focus: read-only STOREB refresh evidence boundary review for order 918424218 and the 31 missing statusChangeDate records

Agent C

- read-only analyst
- focus: read-only preflight command, stop-condition, backup/rollback, and non-authorization review

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
- run dir `~/Docs/Autonomous_business/docs/parallel_runs/2026-05-14_codecaptain-storeb-readiness-packet-patch`

CodeCaptain decision source

- `~/Docs/Oracle/Autonomous_business/2026-05-14/114527_TASK-000_frozen-window-option1-2-combined-copy-proof-final3/Answer/Code_Captain_14.05.2026_17_52_25.md`

Target packet

- `~/Docs/Autonomous_business/exports/validation/frozen_window_option1_2_combined_copy_proof/20260514_113412/production_readiness/ORDER_ENTRY_PRODUCTION_APPLY_READINESS_PACKET.md`

Starter prompt folder

- `~/Docs/Autonomous_business/docs/agent_handoffs/CODECAPTAIN_STOREB_READINESS_PACKET_PATCH_20260514_STARTERS`

Concrete launch sequence

1. Launch Agent 802 and Agent 803 in parallel, read-only.
2. Review their closeouts.
3. Launch Agent 801 only if both analyst closeouts exist and neither gate is RED.

Non-authorization boundary

- This rollout may patch readiness/evidence artifacts only.
- This rollout does not authorize production DB mutation, workbook mutation, scheduler mutation, external writes, ad-platform writes, owner publication, owner approval request, cash movement, PO commitment, price changes, or stock changes.
