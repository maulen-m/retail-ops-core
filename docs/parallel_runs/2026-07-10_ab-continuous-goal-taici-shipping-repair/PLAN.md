PLAN

Purpose

Continue the green-path repair with one exact WHITE TAICI live stock-off lane, local-only daily-shipping autonomy repairs, copied-DB P0 advancement, and strict final-acceptance evidence

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

- `~/Docs/Autonomous_business_agent_handoffs/2026-07-10_ab-continuous-goal-taici-shipping-repair`

As-of window

- `2026-07-10`

Role split

Agent A

- execution agent
- only writer in the repo
- production `db/app.db`, Google Sheets, schedulers, Telegram, WhatsApp, and
  unrelated external systems are not authorized
- the only authorized live/external mutation is the exact six-offer WHITE
  TAICI action copied verbatim in `PROMPT_AGENT_A.md`
- reads analyst reports and executes the repair path

Agent B

- read-only analyst
- focus: current acceptance/P0/cash/returns evidence and safe causal order

Agent C

- read-only analyst
- focus: daily-shipping retry/carryover/naming/Telegram-only local repair map

Agent D

- read-only analyst
- focus: fresh WHITE TAICI six-row/store/SKU identity and live-execution
  preflight without mutation

First-pass independence rule

- Agent B publishes before reading Agent C
- Agent C publishes before reading Agent B
- Agent D publishes independently
- Agent A consumes all three reports
- second-pass cross-review happens only if Agent A explicitly requests it

Required handoff files

- `README.md`
- `status_board.md`
- `agent_b_report.md`
- `agent_c_report.md`
- `agent_d_report.md`
- `agent_a_execution_log.md`

Launch order

1. Agent B
2. Agent C
3. Agent D
4. Agent A after B, C, and D publish first-pass reports

Stop rules

- analysts do not modify repo state
- analysts may use read-only APIs but must not alter external state
- no production DB mutation is authorized
- daily-shipping code/tests/docs may be repaired only in an isolated worktree;
  stop before scheduler activation, Sheet/DB/Kaspi-order writes, or any Telegram
  send because the pasted goal did not contain the standing-autopilot approval
- the WHITE TAICI live lane must stop on any identity/count/hash/history/
  readback/non-target mismatch and must never widen into broad DLRO, competitor,
  or redflag execution
- pane `%242` and all staged text in existing panes remain untouched
- no source swap without explicit provenance

Generated from

- `python3 scripts/init_parallel_rollout.py`
- repo `Autonomous_business`
- run dir `~/Docs/Autonomous_business/docs/parallel_runs/2026-07-10_ab-continuous-goal-taici-shipping-repair`
