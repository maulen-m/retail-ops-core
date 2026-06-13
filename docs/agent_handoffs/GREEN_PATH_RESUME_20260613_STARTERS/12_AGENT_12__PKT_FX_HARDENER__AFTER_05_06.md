# Agent 12 - PKT-FX Writer Hardener

Assigned closeout:
`~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_12_pkt_fx_hardener_closeout.md`

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/handoff/ORCHESTRATOR_HANDOFF.md`
4. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/GREEN_PATH_RESUME_ADDENDUM_20260613.md`
5. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/starter_pack/03_packets_phase2.md`
6. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/OWNER_DECISIONS_RECORDED.yaml`
7. `~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_6_pkt_fx_apply_readiness_closeout.md`
8. Agent 5 `PKT-LINES` closeout after it exists

Role: code/test hardening agent for `PKT-FX`. This lane prepares the FX writer for safe production use; it does not apply FX rows to production DB.

Scope:

- Objective: make `scripts/upsert_fx_rates.py` safe for future env-gated production apply.
- Allowed writes: `scripts/upsert_fx_rates.py`, focused tests, assigned closeout, and minimal evidence under `exports/validation` if needed.
- Forbidden writes: production DB mutation, actual FX row apply, broad FX source imports, Web_automation, pricing, cash, stock, profit, ads, workbooks, LaunchAgents, and external systems.

Implementation contract:

- Patch `scripts/upsert_fx_rates.py` so live writes require both `--apply` and `ENABLE_FX_RATES_WRITE=1`.
- Preserve `--dry-run` and `--show-latest`; default without `--apply` must be no-write validation/dry-run.
- Avoid schema creation/ALTER during dry-run against production DB.
- Add a backup requirement for apply: either create a backup through repo `scripts.backup_db.backup_database()` or require an explicit backup directory/path. Record the chosen contract in `--help`.
- Add focused tests proving:
  - default invocation does not write;
  - `--apply` without env gate fails;
  - env gate plus `--apply` writes exactly one expected row on a temp DB;
  - dry-run does not create schema on an empty/prod-like DB;
  - `--show-latest` remains read-only.

Validation:

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q \
  tests/test_fx_rates_seed.py \
  tests/test_business_params.py \
  tests/test_fx_derive.py \
  tests/test_fx_defaults_runtime_paths.py \
  tests/test_upsert_fx_rates_gate.py
```

Also run a no-write live help/show/dry-run smoke against production `db/app.db` only if it cannot mutate:

```bash
PYTHONPATH=. .venv/bin/python scripts/upsert_fx_rates.py --help
PYTHONPATH=. .venv/bin/python scripts/upsert_fx_rates.py --db db/app.db --show-latest
PYTHONPATH=. .venv/bin/python scripts/upsert_fx_rates.py --db db/app.db --effective-date 2026-06-13 --usdt-kzt 485 --usdt-cny 6.7361111111 --usd-kzt 485 --dlv-rate-usd-kg 2.66 --provider OWNER_ACTUAL --source "NO_WRITE_SMOKE" --dry-run --verbose
```

Closeout requirements:

- Standalone line `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Include files changed, behavior contract, tests run, smoke outputs, and exact future apply command shape.
- Use `Gate: GREEN` only if tests pass and production no-write smokes prove no DB mutation.
- Use `Gate: YELLOW` if code is safe but full repo gates still fail on pre-existing unrelated green-path blockers.
- Use `Gate: RED` if apply gating cannot be proven.
