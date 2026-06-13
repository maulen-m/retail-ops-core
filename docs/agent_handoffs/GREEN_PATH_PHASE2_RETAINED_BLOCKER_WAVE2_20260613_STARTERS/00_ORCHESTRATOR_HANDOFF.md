# Green Path Phase 2 Retained Blocker Wave 2 Starters - 2026-06-13

Gate: STARTERS_READY

Repo: `~/Docs/Autonomous_business`
Branch: `greenpath/20260613-phase2-truth`

## Current State

Production cashflow D1 repair is applied and validated.

The June 13 `ACMEWEAR/LINE-31-TS` ads sold-offer sub-gap is now contract-quarantined and validated:

- closeout: `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_PHASE2_ADS_LINE31TS_QUARANTINE_20260613.md`
- commit: `8cb0b1f docs: quarantine june beli ads gap`
- ads offer-universe `2026-06-13..2026-06-13`: `PASS`
- ads spend reality `2026-06-13..2026-06-13`: `PASS`
- ads sidecar readiness live strict: `PASS`

Retained blockers after that micro-repair:

- `src_facebook_ads_external_ads`: `BLOCKED`
- `src_ab_db_stock_truth`: `STALE`
- C3 gates: `ads_source_truth`, `source_freshness`, `stock_source_truth`

## Launch Order

Parallel group `wave2_readonly_root`:

- Agent 23: Meta/Facebook positive-spend ingestion contract and copied-DB proof boundary.
- Agent 24: governed stock repair source/approval matrix and copied-DB proof boundary.

Both agents are read-only/copy-DB analysts. They must not mutate production `db/app.db`, external systems, workbooks, Telegram, LaunchAgents, pricing, customer messages, or operator messages. The orchestrator remains the only write-capable execution lane.

## Required Closeout Contract

Every closeout must include a standalone line:

`Gate: GREEN`

or:

`Gate: YELLOW`

or:

`Gate: RED`

`GREEN` means the agent proved an existing safe copied-DB path with exact production apply commands, expected row counts, backup requirements, validators, and rollback instructions.

`YELLOW` means the blocker is narrowed but still needs a source, owner approval, or code/schema change before production apply.

`RED` means an integrity/truth regression, external write, production write, or unsafe recommendation occurred.

## Starter Files

- `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_PHASE2_RETAINED_BLOCKER_WAVE2_20260613_STARTERS/23_AGENT_23__META_POSITIVE_SPEND_INGESTION_BOUNDARY__PARALLEL_ROOT.md`
- `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_PHASE2_RETAINED_BLOCKER_WAVE2_20260613_STARTERS/24_AGENT_24__STOCK_GOVERNED_REPAIR_APPROVAL_BOUNDARY__PARALLEL_ROOT.md`

## Preferred Tmux Launch

```bash
python3 ~/.codex/skills/tmux-agent-orchestrator/scripts/launch_tmux_agents.py \
  --repo ~/Docs/Autonomous_business \
  --starter-folder ~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_PHASE2_RETAINED_BLOCKER_WAVE2_20260613_STARTERS \
  --session autonomous_business \
  --run-id green_path_phase2_retained_blocker_wave2_20260613 \
  --window-name greenpath_final_blockers_r2_20260613 \
  --agents 23,24 \
  --agent-command codex \
  --mode hybrid \
  --orchestrator-ping-mode monitor-only
```
