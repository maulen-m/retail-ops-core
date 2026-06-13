# Green Path Phase 2 Final Blocker Wave Starters - 2026-06-13

Gate: STARTERS_READY

Repo: `~/Docs/Autonomous_business`
Branch: `greenpath/20260613-phase2-truth`

## Current Production State

Cashflow D1 repair has been applied to production and validated:

- closeout: `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_PHASE2_CASHFLOW_PROD_APPLY_20260613.md`
- evidence: `~/Docs/Autonomous_business/exports/validation/agent18_cashflow_d1_cash_in_prod_apply_20260613/`
- `cashflow_source_truth`: `PASS`
- `cash_in_missing_count`: `0`
- daily operations verified paused after apply: `0/10 loaded`

Retained publication blockers:

- `ads_source_truth`
- `source_freshness`
- `stock_source_truth`

Strict source freshness retained blockers:

- `src_ab_db_ads_truth`: `STALE`
- `src_ab_db_stock_truth`: `STALE`
- `src_facebook_ads_external_ads`: `BLOCKED`

## Launch Order

Parallel group `final_blocker_green_proofs`:

- Agent 21: ads external and AB-local truth green proof.
- Agent 22: source-backed stock negative-balance repair green proof.

Both agents must not mutate production `db/app.db`. They may create copied DBs and evidence only. If an agent needs code changes, it must either keep the patch narrowly scoped to its lane or stop `YELLOW` with the exact missing contract/script. Production DB apply remains serialized by the orchestrator after reading closeouts.

## Required Closeout Contract

Every closeout must include a standalone line:

`Gate: GREEN`

or:

`Gate: YELLOW`

or:

`Gate: RED`

`GREEN` means the agent proved a safe copied-DB repair path with exact production apply commands, expected row counts, backup requirements, validators, and rollback instructions.

`YELLOW` means the blocker is narrowed but still needs another source, owner decision, or code change before production apply.

`RED` means integrity/truth regressed, an external write occurred, a production write leaked outside scope, or rollback would be needed if it had been production.

## Starter Files

- `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_PHASE2_FINAL_BLOCKER_WAVE_20260613_STARTERS/21_AGENT_21__ADS_EXTERNAL_AND_AB_TRUTH_GREEN_PROOF__PARALLEL_ROOT.md`
- `~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_PHASE2_FINAL_BLOCKER_WAVE_20260613_STARTERS/22_AGENT_22__STOCK_SOURCE_BACKED_NEGATIVE_REPAIR_GREEN_PROOF__PARALLEL_ROOT.md`

## Preferred Tmux Launch

```bash
python3 ~/.codex/skills/tmux-agent-orchestrator/scripts/launch_tmux_agents.py \
  --repo ~/Docs/Autonomous_business \
  --starter-folder ~/Docs/Autonomous_business/docs/agent_handoffs/GREEN_PATH_PHASE2_FINAL_BLOCKER_WAVE_20260613_STARTERS \
  --session autonomous_business \
  --run-id green_path_phase2_final_blocker_wave_20260613 \
  --window-name greenpath_final_blockers_20260613 \
  --agents 21,22 \
  --agent-command codex \
  --mode hybrid \
  --orchestrator-ping-mode monitor-only
```

