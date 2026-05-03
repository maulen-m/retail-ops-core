# Google Ops Board Schema Hardening Plan

Purpose

- Prevent employee-facing Google Sheet structural drift from blocking daily Telegram bundle closeout or silently shifting operational fields.

Repo

- `~/Docs/Autonomous_business`

Canonical protocol

- `~/Docs/Autonomous_business/docs/PARALLEL_EXECUTION_PROTOCOL.md`

Shared handoff folder

- `~/Docs/Autonomous_business_agent_handoffs/2026-04-30_google-ops-board-schema-hardening`

Execution posture

- Sequential execution agents only.
- Do not run these three as parallel writers because they touch the same Google Ops Board contract/parser/protection surface.
- Every agent writes fail-first or success-verifiable tests before code changes.
- Live Google Sheet writes require explicit write gates, before/after layout evidence, and rollback notes.
- No Kaspi shipping, Telegram production bundle send, WhatsApp send, or DB mutation is part of this rollout unless explicitly stated by the assigned starter.

Scope

1. Auto-repair blank spacer columns before closeout.
2. Add a pre-closeout schema canary with Telegram/owner alerting.
3. Add stricter protection validation so sheet protections are auditable and drift-resistant.

Launch order

1. Agent 1: `~/Docs/Autonomous_business/docs/parallel_runs/2026-04-30_google-ops-board-schema-hardening/01_AGENT_1__AUTO_REPAIR_SCHEMA__SEQUENTIAL.md`
2. Agent 2: `~/Docs/Autonomous_business/docs/parallel_runs/2026-04-30_google-ops-board-schema-hardening/02_AGENT_2__TELEGRAM_SCHEMA_CANARY__AFTER_01.md`
3. Agent 3: `~/Docs/Autonomous_business/docs/parallel_runs/2026-04-30_google-ops-board-schema-hardening/03_AGENT_3__STRICT_PROTECTION_VALIDATION__AFTER_01_02.md`

Required closeout files

- Agent 1: `~/Docs/Autonomous_business_agent_handoffs/2026-04-30_google-ops-board-schema-hardening/agent_1_auto_repair_closeout.md`
- Agent 2: `~/Docs/Autonomous_business_agent_handoffs/2026-04-30_google-ops-board-schema-hardening/agent_2_schema_canary_closeout.md`
- Agent 3: `~/Docs/Autonomous_business_agent_handoffs/2026-04-30_google-ops-board-schema-hardening/agent_3_protection_validation_closeout.md`

Success criteria

- Blank spacer column drift is automatically repairable before closeout without losing `MY_SIZE`.
- Non-blank unexpected headers or missing required headers still fail closed.
- Owner receives a clear schema-canary alert when layout drift is repaired or blocks closeout.
- Protection validation confirms `SalesRaw_Today` exposes only `MY_SIZE` and `Run_Control` exposes only `ready_for_closeout`.
- Focused pytest passes, docs lint passes if docs changed, and DB guard passes.
