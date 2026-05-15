# Boundary Drift Forensics And Readonly Hardening - 2026-05-13 14:05:35 +0500

Gate: YELLOW_REANCHORED_FOR_REVIEW_ONLY_SOURCE_PROOF

## Owner Direction

Human owner instruction:

> okay then proceed, it should not require approval, Apply the most efficient next steps Given the situation, even if something goes unexpectedly.

This instruction authorizes the orchestrator to take the most efficient safe next steps without stopping for another approval. It does not authorize production DB mutation, workbook mutation, scheduler restore/mutation, external writes, owner publication, owner approval requests, cash movement, PO commitment, ad spend, price changes, or stock changes.

## Reclassified Boundary

Previous accepted review-only boundary:

- DB SHA256: `7cfe3ebc5df4867e28c57b4ed392f665dfa8143c44db4d54dde11fdb41f889d6`
- DB mtime: `2026-05-12T19:11:05+0500`
- Workbook SHA256: `4e7d18e16d2c16779de5f1f91eadea231c92143c1da29cdee9d0441c7592444c`
- Workbook mtime: `2026-05-12T17:06:10+0500`

Current reanchored review-only boundary:

- DB SHA256: `04c76434399eb7e146037271fa121d69f71ae64195ac5a3436ccfed080b18f99`
- DB mtime: `2026-05-13T12:21:48+0500`
- DB integrity: `ok`
- Workbook SHA256: `4e7d18e16d2c16779de5f1f91eadea231c92143c1da29cdee9d0441c7592444c`
- Workbook mtime: `2026-05-12T17:06:10+0500`

The current DB boundary is accepted only for review-only copied-temp/source-proof continuation. It is not owner-publication authority and it is not production apply authority.

## Forensic Result

Evidence root:

`~/Docs/Autonomous_business/exports/validation/source_truth_unblock_wave/20260513_121500/orchestrator_boundary_drift_forensics_20260513_134220`

Findings:

- User-table logical comparison found no changed tables between the `7cfe...` freeze and the `04c764...` live bytecopy.
- Full `.dump` hashes matched: `702b53e67d397d3dfcaaafcc55e92abf04519e1b4d932a4f76abb6579df5a641`.
- `sqlite_sequence` comparison matched.
- SQLite page size, page count, freelist count, user version, application id, journal mode, and WAL checkpoint values matched.
- Only SQLite header/schema-cookie metadata moved: `schema_version` changed from `43398` to `43406`.
- Byte comparison found exactly three byte differences: offsets `28`, `44`, and `96`.

Conclusion: the observed `7cfe...` to `04c764...` DB SHA change is header-only SQLite metadata drift, not business table/data drift.

The exact originating writer is not fully proven. Agent792 evidence captured PID `11505` holding `db/app.db` while running `scripts/materialize_policy_gate_results.py --db db/app.db --as-of 2026-05-12 --run-id agent790_ads_source_readiness_dryrun_20260513_121500 --json`, and Agent790 also ran `scripts/materialize_policy_source_freshness.py` without `--apply`. Reproduction of those dry-runs on a `7cfe...` freeze copy did not reproduce the header drift, so this memo reclassifies the boundary safely but does not overclaim root cause.

## Hardening Applied

Dry-run policy materialization and policy validators now use a readonly SQLite connection:

- `core/ops/policy_registry_c3.py`: added `connect_readonly(...)` with SQLite URI `mode=ro` and `PRAGMA query_only=ON`.
- `core/ops/policy_registry_c3.py`: validator paths now use readonly connections.
- `core/ops/policy_materialization_c3.py`: `_materialize(...)` uses readonly connection when `apply=False` and writable connection only when `apply=True`.
- `tests/test_policy_materialization_c3.py`: added byte-stability coverage for readonly dry-run policy gate materialization.

Validation run:

- `pytest -q tests/test_policy_materialization_c3.py::test_policy_gate_materializer_dry_run_accepts_readonly_db_without_byte_drift` -> passed.
- `pytest -q tests/test_policy_materialization_c3.py` -> `22 passed`.
- `python3 -m json.tool docs/parallel_runs/2026-05-06_codecaptain_proscope_red_recovery/current_gate_status_agent750_waiting_codecaptain.json` -> passed before this memo update.

Production read-only dry-run proof after hardening:

- `scripts/materialize_policy_source_freshness.py --db db/app.db --as-of 2026-05-12 --run-id orchestrator_readonly_hardened_source_probe_20260513 --json`
- `scripts/materialize_policy_gate_results.py --db db/app.db --as-of 2026-05-12 --run-id orchestrator_readonly_hardened_gate_probe_20260513 --json`
- DB stayed `04c76434399eb7e146037271fa121d69f71ae64195ac5a3436ccfed080b18f99` before and after.
- Workbook stayed `4e7d18e16d2c16779de5f1f91eadea231c92143c1da29cdee9d0441c7592444c` before and after.
- `schema_version` stayed `43406` before and after.

## Still Blocked

The source-truth unblock wave remains red by domain even after header-only reanchor:

- Agent788 cashflow: missing unit-cost decisions and stale bank/manual cashflow source evidence.
- Agent789 stock/order: missing accepted identity-bearing order-entry evidence for `2026-05-05..2026-05-11`.
- Agent790 ads: local ads evidence does not clear the `2026-05-12` ads blocker; bounded read-only source capture remains needed.
- Agent791 PO inbound: canonical inbound workbook/source remains stale and validator failures remain.
- Agent792 exceptions: owner/source facts are unresolved for exception closure/reopen decisions.

## Next Safe Execution Route

Proceed from the `04c764...` DB and `4e7...` workbook as the current review-only copied-temp/source-proof boundary.

Fastest safe route:

- Launch a reanchored read-only/source-capture wave against the current `04c764...` boundary.
- Keep all source lanes artifact-backed and fail-closed.
- Allow agents to ping the orchestrator only through the attested tmux completion helper after closeout.
- Do not run owner publication, scheduler restore, production apply, workbook mutation, external writes, cash movement, PO commitment, ad spend, price changes, or stock changes from this memo.
