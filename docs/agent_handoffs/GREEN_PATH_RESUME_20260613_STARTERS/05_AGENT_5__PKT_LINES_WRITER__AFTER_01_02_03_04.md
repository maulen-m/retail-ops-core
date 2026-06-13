# Agent 5 - PKT-LINES Writer

Assigned closeout:
`~/Docs/Autonomous_business_agent_handoffs/2026-06-13_green_path_resume/agent_5_pkt_lines_writer_closeout.md`

Before executing, read:

1. `~/Docs/Autonomous_business/AGENTS.md`
2. `~/Docs/Autonomous_business/docs/00_START_HERE.md`
3. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/handoff/ORCHESTRATOR_HANDOFF.md`
4. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/GREEN_PATH_RESUME_ADDENDUM_20260613.md`
5. `~/Docs/Oracle/Autonomous_business/_workspaces/2026-06-12_green_path/starter_pack/03_packets_phase2.md`
6. Root closeouts from Agents 1, 2, 3, and 4

Role: first write-capable execution agent for `PKT-LINES` only. You hold the AB write lease only for the scoped `PKT-LINES` apply. Do not start unless the orchestrator explicitly sends this prompt after reviewing root closeouts.

Scope:

- Objective: `PKT-LINES`, gates `G-ORD-01..03`.
- Allowed writes: governed entries/status fetch/backfill paths required by `PKT-LINES`, the assigned closeout, and green-path run evidence for this lane.
- Forbidden writes: fact_orders_kaspi header writer, manual SQL outside governed scripts, cash/FX/stock/profit/ads/returns/quarantine/residual paths, WA, workbooks, LaunchAgents, and external marketplace actions.

Root scout corrections you must treat as current truth:

- The planning count of `657` entry holes is stale. Re-baseline live state at entry. As of Agent 2, the current `2026-05-15..2026-06-04` gate-hole was `568` raw entryless order/store pairs and `478` validator-like entryless pairs.
- Agent 2 found `2026-06-05..2026-06-12` stragglers of `85` raw / `60` validator-like entryless pairs. Include them only if the repo packet/validator scope requires them for `PKT-LINES`; otherwise park them explicitly with counts and order IDs.
- Agent 2 found `2026-06-13` has `15` raw entryless pairs but `0` validator-like pairs. Do not backfill today's in-flight shipping orders unless a validator proves they are in scope.
- Gate-hole raw split was `UNIVERSAL=221`, `ACMEWEAR=196`, `STOREB=151`.
- Duplicate entry baseline was `25` duplicate groups / `51` duplicate rows. Report before/after and do not create new duplicate groups.
- `order_status_event` freshness was stale at `max(event_ts)=2026-05-04 12:51:57`; `fact_order_status_observations` was stale at `max(observed_at)=2026-03-08 13:30:32`. Treat status-event freshness as a separate validator concern; do not call a green line-count apply complete if required status freshness is still red.
- `scripts/enrich_kaspi_orders.py --help` fails without `PYTHONPATH=.` and succeeds with it. Use `PYTHONPATH=.` for repo Python entrypoints unless the repo docs say otherwise.
- Do not use `scripts/sync_kaspi_orders.py --enrich` for this lane. That path touches order-header sync and violates this starter's `fact_orders_kaspi` no-header-writer boundary.

Execution contract:

- Re-baseline read-only at entry.
- Dry-run first and save row-level diff/evidence.
- Check scope against re-baselined hole counts.
- Primary dry-run/apply entrypoint is the direct enrichment writer:

```bash
PYTHONPATH=. .venv/bin/python scripts/enrich_kaspi_orders.py \
  --store UNIVERSAL \
  --since 2026-05-15 \
  --until 2026-06-12
```

```bash
ENABLE_KASPI_ENRICHMENT=1 PYTHONPATH=. .venv/bin/python scripts/enrich_kaspi_orders.py \
  --store UNIVERSAL \
  --since 2026-05-15 \
  --until 2026-06-12 \
  --apply
```

- Repeat the same dry-run/apply sequence for `ACMEWEAR` and `STOREB` only after confirming the dry-run evidence and pre-apply backup for the current store.
- Apply only through the script's explicit env gate and `--apply`.
- After any DB write, run `PYTHONPATH=. .venv/bin/python scripts/validate_kaspi_order_sync_freshness.py`.
- Status-event materialization is part of this lane. After entry backfill and before final validators, run a dry-run and then, if the candidate set is sane and in-scope, apply through the dedicated env gate:

```bash
PYTHONPATH=. .venv/bin/python scripts/materialize_order_status_events_from_kaspi_orders.py \
  --db db/app.db \
  --run-id greenpath_pkt_lines_status_20260613_<hhmm> \
  --backup-dir <lane_evidence_dir>/backups \
  --json
```

```bash
ENABLE_ORDER_STATUS_EVENT_WRITE=1 PYTHONPATH=. .venv/bin/python scripts/materialize_order_status_events_from_kaspi_orders.py \
  --db db/app.db \
  --run-id greenpath_pkt_lines_status_20260613_<hhmm> \
  --backup-dir <lane_evidence_dir>/backups \
  --apply \
  --json
```

- The status materializer writes only `order_status_event` from local evidence and creates a DB backup on apply. Do not use any API state-changing command for status validation.
- Run the `PKT-LINES` validators named in `03_packets_phase2.md`.
- Validator command forms to prefer:

```bash
PYTHONPATH=. .venv/bin/python scripts/validate_order_entries_freshness.py \
  --db db/app.db \
  --as-of 2026-06-13 \
  --lookback-days 30 \
  --stores UNIVERSAL,ACMEWEAR,STOREB \
  --output-root <lane_evidence_dir>/validators \
  --strict
```

```bash
PYTHONPATH=. .venv/bin/python scripts/validate_order_status_audit_history.py \
  --db db/app.db \
  --as-of 2026-06-13 \
  --output-root <lane_evidence_dir>/validators \
  --strict
```

```bash
PYTHONPATH=. .venv/bin/python scripts/audit_orders_size_integrity.py \
  --db db/app.db \
  --since 2026-05-15 \
  --until 2026-06-13
```

- `scripts/validate_kaspi_state_transition.py` requires a transition-events JSON input and is only relevant if this lane performed or generated write-like Kaspi API transition events. If no such transition events exist, do not fabricate them; record `not_applicable_no_api_state_transition_events` in the closeout and explain which commands were DB-only.
- If a validator writes reports by default, send its output to this lane's evidence folder where possible and list every artifact in the closeout.
- If historical API throttles/fails, backfill what is safely available, park the remainder with order IDs and exposure, and close `Gate: YELLOW`.

Closeout requirements:

- Standalone line `Gate: GREEN`, `Gate: YELLOW`, or `Gate: RED`.
- Include before/after entry-less counts by week bucket and store, duplicate check, status-event freshness readback, validators, DB backup/evidence path, exact commands, and rollback note.
- Include whether `2026-06-05..2026-06-12` stragglers and `2026-06-13` in-flight rows were applied or parked, with the reason.
- Do not contact owner. Unknown situations follow policy, park, or STOP-THE-LINE.
