# Agent732/733 Orchestrator Review - 2026-05-08

## Source Closeouts

- Agent732: `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_732_agent731_red_root_cause_forensics_closeout.md`
- Agent733: `~/Docs/Autonomous_business_agent_handoffs/2026-05-06_codecaptain_proscope_red_recovery/agent_733_agent731_red_temp_variant_proof_closeout.md`

## Gate

Agents732 and 733 both closed `GREEN`.

## Finding

Agent731's RED was not caused by production boundary drift. It was caused by a command-family contract mismatch:

- Agent70's accepted GREEN path used the simulation snapshot path.
- Agent72F/729 proved the ledger snapshot wrapper only in isolation.
- Agent731 combined sales/stock replay with the ledger-only wrapper and exposed negative ledger stoplines.

Agent733 Variant B proved that the Agent70-style sequence from the fresh Agent731 backup still reaches a green temp state:

- final policy source freshness passed;
- final operational validator passed with `GREEN`;
- `23` product-identity warnings and `251` header-only warnings were visible;
- strict/header quarantine tables contained `23` and `252` rows;
- combined order-level `CASH_IN` was preserved at `280` rows / `1116872.85` KZT;
- product leakage cleared.

Variant B is diagnostic only because it used direct `scripts/rebuild_snapshot.py --mode simulate --apply` and direct temp quarantine materializers.

## Implemented Orchestrator Patch Before Next Lane

The snapshot wrapper was extended locally to support `--mode simulate` under the same production-safe envelope:

- explicit env gate;
- expected pre-SHA;
- expected existing rows;
- expected rows/current/inbound controls;
- planning on a copy for simulate mode;
- backup;
- staging copy;
- integrity checks;
- rollback metadata;
- target replacement only after controls pass.

Focused verification after the patch:

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_apply_rebuild_snapshot_production_safe.py`: `9 passed`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q tests/test_apply_rebuild_snapshot_production_safe.py tests/test_rebuild_snapshot_negative_active_zero.py tests/test_validate_write_side_gating.py`: `14 passed`
- `python3 -m py_compile scripts/apply_rebuild_snapshot_production_safe.py scripts/rebuild_snapshot.py`: pass
- `python3 scripts/validate_write_side_gating.py --manifest config/write_side_gating_manifest.yaml`: `WRITE_SIDE_GATING PASS`, `checked_count=34`

## Next Lane

Launch Agent734 as a no-production-mutation full copied-DB proof:

- start from Agent731 backup DB;
- run sales fact and stock ledger replay;
- replace direct simulation snapshot with `scripts/apply_rebuild_snapshot_production_safe.py --mode simulate`;
- continue the Agent70 sequence;
- replace direct strict/header quarantine materializers with production-safe quarantine wrappers;
- run pinned `2026-05-04` validators;
- prove row counts, leakage, cash preservation, warning visibility, backup/rollback, and protected-surface cleanliness.

## Stoplines

- No owner request.
- No production apply.
- No live workbook mutation.
- No scheduler mutation.
- No external-system writes.
- No direct production SQL.
- No treating direct diagnostic Variant B as production-safe.
- No hiding warning-class visibility nuance: table counts are `23 + 252`, while validator visibility may be `23 + 251`.
