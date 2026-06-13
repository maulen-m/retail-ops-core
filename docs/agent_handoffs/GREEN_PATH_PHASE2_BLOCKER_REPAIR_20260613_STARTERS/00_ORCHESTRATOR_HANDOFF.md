# Green Path Phase 2 Blocker Repair Starters - 2026-06-13

Gate: STARTERS_READY

This starter pack follows the YELLOW closeout from:

`~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_REMAINING_BLOCKERS_20260613_STARTERS/RUN_CLOSEOUT.md`

The goal is to prove the next safe repair path for the retained Phase-2 blockers without granting parallel production DB writers.

## Launch Order

Parallel group `phase2_blocker_temp_proofs`:

- Agent 18: cashflow D1 cash-in source-truth temp proof.
- Agent 19: AB/Kaspi ads truth temp proof.
- Agent 20: stock negative-balance and snapshot-rebuild temp proof.

All three agents may run in parallel because they must not mutate production `db/app.db`. Each agent may write only evidence, copied DBs, tests/code proposals if explicitly needed, and its assigned closeout. Production apply is reserved for the orchestrator after reading closeouts and serializing a write lease.

## Current Retained Blockers

- `cashflow_source_truth`: BLOCKED by `CASHFLOW_D1_CASH_IN_MISSING`.
- `src_ab_db_ads_truth`: STALE; AB ads tables still max `2026-05-11`.
- `src_facebook_ads_external_ads`: BLOCKED because current Meta evidence contains spend and the no-spend clearance contract cannot pass.
- `src_ab_db_stock_truth`: STALE; `stock_ledger` reaches `2026-06-13`, but `fact_inventory_snapshot_size` remains `2026-05-31` because snapshot rebuild refuses 15 negative ledger balances.

## Required Closeout Contract

Every agent closeout must include a standalone line:

`Gate: GREEN`

or:

`Gate: YELLOW`

or:

`Gate: RED`

`GREEN` means the agent proved a safe copied-DB repair path with exact production apply commands, expected row counts, backup requirements, and validators.

`YELLOW` means the blocker is narrowed but still needs another source, owner decision, or code change before production apply.

`RED` means a copied-DB proof regressed integrity/truth, a write leaked outside scope, or rollback would be needed if it had been production.

## Starter Files

- `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_PHASE2_BLOCKER_REPAIR_20260613_STARTERS/18_AGENT_18__CASHFLOW_D1_CASH_IN_TEMP_PROOF__PARALLEL_ROOT.md`
- `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_PHASE2_BLOCKER_REPAIR_20260613_STARTERS/19_AGENT_19__ADS_TRUTH_TEMP_PROOF__PARALLEL_ROOT.md`
- `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_PHASE2_BLOCKER_REPAIR_20260613_STARTERS/20_AGENT_20__STOCK_NEGATIVE_BALANCE_TEMP_PROOF__PARALLEL_ROOT.md`

## Tmux Launch

Preferred launch:

```bash
python3 ~/.codex/skills/tmux-agent-orchestrator/scripts/launch_tmux_agents.py \
  --repo ~/Docs/Autonomous_business \
  --starter-folder ~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_PHASE2_BLOCKER_REPAIR_20260613_STARTERS \
  --session autonomous_business \
  --run-id green_path_phase2_blocker_repair_20260613 \
  --window-name greenpath_phase2_repair_20260613 \
  --agents 18,19,20 \
  --agent-command codex \
  --mode hybrid \
  --orchestrator-ping-mode monitor-only
```

