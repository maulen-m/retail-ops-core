# Google Ops Board write-path ownership split

Status: DECIDED

Owner: daily shipping / Google Ops Board

Contract target: Google Ops Board v4 (`split_v1`)

## Decision

The durable TOCTOU fix is disjoint write ownership. Unattended automation must
never write a cell that carries employee intent. The probable-size fallback
writes only new automation-owned cells, and closeout resolves the effective size
and READY request from a fresh Board read. An employee value always wins. An
automation value is consulted only when the corresponding employee cell is
blank.

This replaces the current read-check-write mitigation. Google Sheets does not
provide the compare-and-set primitive needed to make the existing shared-cell
mutation safe. Another client-side re-read is not a fix.

The split is a Board contract and closeout-consumer change. It is not a new
database authority, a new scheduler, or a change to the 19:45 operational
containment window.

## Why the current contract is unsafe

The current fallback has two independent shared-cell races:

1. It re-reads `SalesRaw_Today`, observes blank `MY_SIZE`, and later writes the
   probable size into that same employee cell. An employee can write `MY_SIZE`
   between the read and the write.
2. It re-reads `Run_Control`, observes `HOLD`, and later writes
   `ready_for_closeout`, `ready_set_by`, and `ready_set_at`. An employee can
   press READY between the read and the write.

The same ownership issue exists in any publisher or status path that reads a
whole row, merges preserved values client-side, and then writes the whole row.
`merge_rows_preserving_editables()` is correct as a value-merging rule but is not
a concurrency boundary. Existing-row publishes therefore must become
column-sparse as part of D3-IMPL: they may update publisher-owned cells, but must
not send employee-owned or watcher-owned cells in the request.

## Contract v4 surfaces

All new columns are appended, not inserted. Appending keeps the existing
trailing-header migration path usable and avoids a destructive layout rewrite.

### `SalesRaw_Today`

| Column | Owner | UI | Publish behavior | Meaning |
| --- | --- | --- | --- | --- |
| `HEIGHT` | employee | editable | preserve; publisher never sends it for an existing row | Human input. |
| `WEIGHT` | employee | editable | preserve; publisher never sends it for an existing row | Human input. |
| `MY_SIZE` | employee | editable | preserve; publisher never sends it for an existing row | Human size decision. Any nonblank value has precedence, including an invalid value that must block rather than fall back. |
| `AUTO_SIZE_SUGGESTION` | closeout watcher | visible, protected | preserve; publisher never sends it for an existing row | Immutable-for-the-day fallback suggestion copied from the visible, valid `PROBABLE_SIZE`. It is not an employee answer. |
| Existing derived columns | publisher | protected | publisher-owned sparse updates | DB/API-derived visibility fields, including `PROBABLE_SIZE` and its provenance. |

`AUTO_SIZE_SUGGESTION` is appended after `ExpressDeliveryStatus`. It stays
visible so the employee and owner can audit what the fallback proposed. Its
source and write time remain in the existing JSON audit artifact; the Board
column is intentionally the minimal visible value surface.

### `Run_Control`

| Column | Owner | UI | Meaning |
| --- | --- | --- | --- |
| `ready_for_closeout` | employee or authenticated explicit owner command | editable | Blank means no employee decision. `READY` requests closeout. `HOLD` is an explicit human veto. |
| `ready_set_by` | employee/human-request path | protected legacy/optional identity input | Preserved. Unattended automation never writes it. |
| `ready_set_at` | employee/human-request path | protected legacy/optional identity input | Preserved. Unattended automation never writes it. When nonblank it is the human request timestamp. |
| `employee_ready_observed_at` | READY watcher | protected | One-time watcher observation used as the human request timestamp when the employee presses READY but `ready_set_at` is blank. It is cleared only after the watcher observes an employee `HOLD`, then re-stamped on a later READY transition. |
| `auto_ready_for_closeout` | closeout watcher | protected | Blank or `READY`. It never changes `ready_for_closeout`. |
| `auto_ready_set_by` | closeout watcher | protected | Constant `AUTO_CLOSEOUT_FALLBACK`; it is not time-label-coupled. |
| `auto_ready_set_at` | closeout watcher | protected | Timestamp for the auto request identity. |
| `notes`, `last_verified_ready_at`, `last_orchestrator_run_id`, `last_orchestrator_status` | automation | protected | Existing automation status/audit fields. Writes must be cell-sparse. |

The four new Run_Control fields are appended in this order:
`employee_ready_observed_at`, `auto_ready_for_closeout`, `auto_ready_set_by`,
`auto_ready_set_at`.

Direct Board edits and authenticated `/ready` or `/halt` commands are human
request paths. The authenticated command handler may express that explicit
request in the employee-owned cells and must record the actor. Unattended
publisher, watcher, closeout, recovery, and status paths may not write those
cells.

Contract v4 creates a new target-date Run_Control row with
`ready_for_closeout = ""`, not `HOLD`. This distinction is required: blank lets
the fallback be considered, while `HOLD` is an employee value and therefore
vetoes an auto request. A v3 row already containing `HOLD` is never cleared by
migration automation; split behavior becomes operational on the next rollover,
or after an explicit owner clear.

## Effective-value resolution at closeout read time

Resolution runs on a fresh `Run_Control` plus `SalesRaw_Today` snapshot before
readiness, request-identity binding, size-writeback scope construction, or any
external action. The raw snapshot is retained unchanged for evidence. The
resolver produces an in-memory effective view and structured
`resolution_events`; it never writes the resolved value back to the Board.

### Effective size

For each exact `_db_row_id` row:

1. If trimmed `MY_SIZE` is nonblank, use it with source
   `EMPLOYEE_MY_SIZE`.
2. Otherwise, if trimmed `AUTO_SIZE_SUGGESTION` is nonblank, use it with source
   `AUTO_SIZE_SUGGESTION`.
3. Otherwise the effective size is blank.

Precedence is applied before normalization. Therefore an invalid nonblank
employee value blocks closeout; a valid automation suggestion must not mask or
replace it. The effective row copy is what readiness validation,
`plan_size_writeback`, the request-bound writeback scope, and expected-order
construction consume. The raw `MY_SIZE` and `AUTO_SIZE_SUGGESTION` values plus
the chosen source are included in `readiness_report.json` and the pinned scope.

### Effective READY and request identity

Resolution is:

1. If `ready_for_closeout == HOLD`, effective state is HOLD. Any auto READY is
   ignored and event `AUTO_READY_DISCARDED_EMPLOYEE_HOLD` is recorded.
2. If `ready_for_closeout == READY`, effective state is READY with source
   `EMPLOYEE`. Its timestamp is `ready_set_at`, or
   `employee_ready_observed_at` when the human timestamp is blank. If both are
   blank, the request is not identity-valid yet; the watcher may write only
   `employee_ready_observed_at`, then the next fresh read resolves it. Any auto
   READY is ignored and event `AUTO_READY_DISCARDED_EMPLOYEE_READY` is recorded.
3. If `ready_for_closeout` is blank, `auto_ready_for_closeout == READY`, and
   `auto_ready_set_at` is nonblank, effective state is READY with source `AUTO`
   and timestamp `auto_ready_set_at`.
4. If the employee cell contains any other nonblank value, fail closed as an
   invalid employee value. Do not consult auto fields.
5. Otherwise effective state is HOLD/no request.

The canonical request identity becomes
`{target_date, ready_source, ready_set_at}`. Watcher debounce state, scheduler
arguments, halt-barrier evaluation, closeout checkpoint pins, resume checks, and
completion evidence must carry `ready_source` as well as the timestamp. This
prevents an ignored auto request and the winning employee request from becoming
indistinguishable.

When employee READY and auto READY coexist, discard means logical discard, not
cell deletion. The auto fields remain visible in raw evidence until rollover.
The resolver records `AUTO_READY_DISCARDED_EMPLOYEE_READY` in
`resolution_events`; closeout persists that list in `readiness_report.json` and
prints the event once while constructing the request scope. Only the employee
identity can launch or resume that closeout.

## Watcher behavior after the split

At the configured fallback time (operationally 19:45), the watcher:

1. Reads the exact target-date row and exact visible SalesRaw scope.
2. Stops on a partial v4 layout or an explicit employee `HOLD`.
3. For every row with blank `MY_SIZE` and blank `AUTO_SIZE_SUGGESTION`, copies a
   visible valid `PROBABLE_SIZE` into `AUTO_SIZE_SUGGESTION` only. Existing
   employee sizes and existing auto suggestions are never rewritten.
4. Re-reads the Board and resolves effective sizes. Blank or invalid effective
   sizes retain the current blocking reason behavior.
5. If every effective size is valid and the employee request cell remains blank,
   writes only `auto_ready_for_closeout`, `auto_ready_set_by`,
   `auto_ready_set_at`, and automation-owned audit/status cells.
6. Re-reads and resolves the effective request. Employee READY or HOLD wins even
   if it arrived between any two watcher calls. The watcher launches only the
   resolved identity.

The employee can write at every point in this sequence without losing a value,
because no watcher request contains `MY_SIZE`, `ready_for_closeout`,
`ready_set_by`, or `ready_set_at`.

The current `_stamp_blank_ready_identity` behavior is replaced. For manual READY
with no human timestamp, the watcher writes only
`employee_ready_observed_at`. The current whole-row Run_Control update must not
remain.

Auto audit output retains the current target date, fire time, applied order IDs,
source, and unresolved reasons, but uses `AUTO_SIZE_SUGGESTION` terminology and
records the final resolved READY source. A warning lists suggestions written and
whether an auto request marker was written; it must not claim an employee cell
was auto-filled.

## Publisher and closeout write rules

- Existing-row publishes use cell-sparse updates for publisher-owned columns.
  They never include employee-owned or watcher-owned columns in a Sheets write
  request. `editable_columns` alone is not a concurrency guarantee.
- Appending a genuinely new SalesRaw row may send the whole new row because no
  employee cell exists yet. Rollover may create the new target-date Run_Control
  row with blank employee values and blank auto values.
- Same-day layout migration may append header cells and apply protection/UI, but
  must not rewrite data rows to add blank trailing values.
- Closeout status writes update only automation status cells. Successful or
  failed unattended closeout must not change `ready_for_closeout`, `ready_set_by`,
  or `ready_set_at`. Completion truth and next-day rollover replace the old
  automatic READY-to-HOLD reset.
- Explicit authenticated `/ready` and `/halt` remain human-request writes. Every
  unattended bot poll, resume, scheduler, and recovery path consumes the same
  effective resolver and canonical identity.

## Migration and compatibility

The implementation supports three detected states using the actual header rows,
not only the repo YAML:

1. **Legacy v3:** none of the new columns exists. Use today's behavior exactly,
   including today's shared-cell fallback. Report `ownership_mode=legacy_v3`
   and do not claim the TOCTOU is fixed.
2. **Split v4:** every required appended column exists on both tabs. Use only the
   split behavior and report `ownership_mode=split_v1`.
3. **Partial layout:** at least one but not all required columns exists. Fail
   closed before auto-prepare or closeout and emit an explicit layout error. Do
   not mix shared-cell and split writes.

Compatibility is intentionally temporary. It allows code to land before the
external Board layout is migrated without making a phantom A1 write past a
missing header. It does not make a legacy Board arm-safe.

Rollout order:

1. Land dual-mode code, contract v4, validators, tests, runtime manifest, and
   generated runtime doc. Keep the current 19:45 containment.
2. Run all focused tests in local fakes. No live Board access is required for
   implementation acceptance.
3. In a separately authorized deployment lane, pause/serialize Board writers,
   take a readback snapshot, and apply the trailing-header/UI migration through
   the existing gated publisher. No data-row rewrite is allowed for the header
   extension.
4. Read back exact headers, protection, and sample values. A partial layout is a
   RED stopline.
5. Keep the current target-date v3 `HOLD` as-is. Split auto behavior becomes
   active at the next target-date rollover, whose v4 row starts blank, unless an
   owner explicitly clears the legacy HOLD.
6. Re-run the runtime and Board health contracts. Only a reported
   `ownership_mode=split_v1` plus full header readback closes L5C Q1.

The existing `config/business_automation_manifest.json` labels, groups, and risk
classification do not change: no scheduler or external capability is added.

`config/daily_shipping_runtime.json` must add Board ownership facts under
`watch`:

- `board_contract_version: 4`
- `board_ownership_mode: split_v1`
- `effective_resolution: employee_first_at_closeout_read`

`scripts/validate_daily_shipping_runtime.py` must cross-check those values
against `config/google_ops_board.yaml`, verify the exact required appended
columns and ownership sets, and render them into
`docs/ops/DAILY_SHIPPING_RUNTIME.generated.md`. The installed LaunchAgent and
its environment do not change for this design.

## Rollback

The safe rollback is additive-first:

1. Disable `AB_GOOGLE_OPS_BOARD_ALLOW_AUTO_PROBABLE_FILL` before reverting code.
2. Revert the runtime/contract/code changes. Leave the appended Board columns in
   place; v3 readers tolerate trailing columns and ignoring them is safer than a
   destructive column deletion.
3. Manual employee `MY_SIZE` and READY behavior continues. Old code ignores
   auto-only values, so an auto suggestion or auto READY cannot authorize a v3
   closeout by itself.
4. If a split-mode closeout reached DB size writeback but not irreversible
   shipping, restore the recorded closeout DB backup and checkpoint together.
   If external delivery already occurred, do not roll back blindly; completion
   evidence and the send ledger remain authority.
5. Removing the appended columns is optional cleanup and requires a separate
   snapshot, readback, and explicit Board-write authorization.

Rollback never copies an auto suggestion into `MY_SIZE` and never clears an
employee value.

## Effort estimate

- Implementation: one xhigh lane, approximately 4-6 focused hours.
- Independent adversarial verification and deployment-readiness gate:
  approximately 1-2 hours.
- Live header/UI migration is a separate owner-authorized deployment lane and is
  not included in the implementation estimate.

The high-risk portions are sparse publisher writes, canonical request-identity
propagation, and retaining halt/resume/completion behavior without the automatic
READY-to-HOLD reset.

## D3-IMPL dispatch spec

The following text is ready to dispatch verbatim:

```text
# SPEC D3-IMPL — Implement Google Ops Board split write ownership

Effort: xhigh. Repo: ~/Docs/Autonomous_business. Sandbox:
workspace-write. Production code changes are authorized only for the files below.
DO NOT stage or commit. No live Google Board reads or writes, no DB writes, no
Telegram/Kaspi calls, no LaunchAgent install. Closeout:
runs/tmux_orchestration/20260717_2200_fable5_final_window/closeouts/D3_IMPL_CLOSEOUT.md.

Authority: docs/ops/BOARD_WRITE_OWNERSHIP_DESIGN.md. Implement it exactly; do not
reopen the decided ownership model or invent a CAS/re-read alternative. Update
the owning contract doc before code. Keep the 19:45 containment unchanged.

STOP POINT 1: after converting the two strict-xfail D3-CONTRACT tests to real
passing tests, run only those tests. If either still writes MY_SIZE or employee
READY identity, stop RED before expanding the change.

STOP POINT 2: after local implementation and the full focused suite below, stop.
Do not migrate or inspect the live Board. A separate authorized lane owns the
external trailing-header/UI migration.

STOP POINT 3: stop RED on a partial-layout path that can write, any whole-row
existing-row publish containing preserved columns, any request identity lacking
ready_source, any regression in halt/resume/completion identity binding, or any
need to change files outside the list.

Required behavior:
1. Contract v4 appends SalesRaw_Today.AUTO_SIZE_SUGGESTION and Run_Control
   employee_ready_observed_at, auto_ready_for_closeout, auto_ready_set_by,
   auto_ready_set_at. Model and validate employee-owned, automation-owned, and
   publisher-preserved columns. New v4 Run_Control rows start with a blank
   ready_for_closeout; HOLD is an explicit employee veto.
2. Detect actual layout mode: no new columns => exact legacy_v3 behavior; all
   columns => split_v1; partial => fail closed with no auto-prepare/closeout write.
3. Add one shared pure resolver in core/integrations/google_ops_board.py. Employee
   MY_SIZE wins even when invalid. Auto size is used only when MY_SIZE is blank.
   Employee HOLD/READY wins over auto READY. Canonical identity is target_date +
   ready_source + ready_set_at. Emit structured resolution_events, including
   AUTO_READY_DISCARDED_EMPLOYEE_READY and AUTO_READY_DISCARDED_EMPLOYEE_HOLD.
4. Change the watcher fallback to write only AUTO_SIZE_SUGGESTION and auto-ready
   fields. Replace blank human identity stamping with a cell-sparse write to
   employee_ready_observed_at. Never send MY_SIZE, ready_for_closeout,
   ready_set_by, or ready_set_at in an unattended watcher request.
5. Make existing-row publisher updates cell-sparse by ownership. New-row append
   and rollover creation may write complete new rows. Trailing-header migration
   updates headers/UI without rewriting data rows.
6. Resolve effective rows and identity on every closeout/scheduler/writeback read
   boundary. Readiness, plan_size_writeback, pinned size scope, expected-order
   construction, debounce, halt barrier, checkpoint, resume, and completion use
   the same identity. Persist raw and effective values plus resolution_events.
7. Closeout status paths write only automation status fields. Do not auto-clear
   employee READY after success/failure. Completion truth prevents repeat work;
   next-day rollover creates the blank v4 employee state.
8. Authenticated Telegram /ready and /halt remain explicit human-request paths,
   record the actor, and all unattended bot paths consume the shared resolver.
9. Add runtime manifest cross-checks and generated-doc output. Do not change the
   business automation scope manifest or LaunchAgent configuration.
10. Remove strict xfail markers only when both D3-CONTRACT interleaving tests pass
    against production code. Add regression tests for legacy, full split, partial
    layout, sparse publish requests, precedence/invalid-value blocking, identity
    propagation, halt/resume, no automatic READY clear, and runtime drift.

File-by-file scope:
- docs/ops/GOOGLE_OPS_BOARD_PHASE1_CONTRACT.md — owning behavior first.
- config/google_ops_board.yaml — version 4, appended fields, ownership metadata,
  UI protection, blank v4 Run_Control default contract.
- core/integrations/google_ops_board.py — ownership metadata, layout-mode detector,
  pure effective resolver, sparse-cell update planning/validation.
- scripts/sync_google_ops_board.py — v4 payload, non-destructive trailing-header
  migration, sparse existing-row publisher writes.
- scripts/run_google_ops_board_closeout_watch_scheduler.py — split fallback,
  observation identity, audit/WARN terminology, resolved launch identity.
- scripts/google_ops_board_automation_common.py — debounce, halt, completion, and
  shared ready-source identity plumbing.
- scripts/run_google_ops_board_closeout_scheduler.py — resolve and compare the
  canonical identity, including --expected-ready-source.
- scripts/run_google_ops_board_closeout.py — fresh-read resolution, readiness,
  pinned scope/checkpoint evidence, sparse status writes, no automatic READY clear.
- scripts/sync_google_ops_board_sizes_to_db.py — consume only pinned effective size
  and preserve raw/effective provenance in plans/reports.
- scripts/waybill_telegram_control_bot.py — explicit human request semantics and
  resolved unattended identity checks.
- scripts/run_google_ops_board_prewindow_health.py — v4/legacy/partial layout and
  post-publish ownership parity.
- config/daily_shipping_runtime.json — v4 ownership facts only.
- scripts/validate_daily_shipping_runtime.py — cross-check contract/runtime facts.
- docs/ops/DAILY_SHIPPING_RUNTIME.generated.md — regenerate from manifest.
- tests/test_google_ops_board_early_closeout_watch.py — activate D3-CONTRACT tests
  and cover watcher/identity races.
- tests/test_google_ops_board.py — contract, layout migration, sparse publish
  requests, ownership invariants.
- tests/test_google_ops_board_closeout.py — size/READY precedence, invalid employee
  blocking, checkpoint and no-auto-clear behavior.
- tests/test_google_ops_board_size_writeback_noop.py — effective-size provenance and
  no unrelated writeback.
- tests/test_google_ops_board_prewindow_health.py — mode and parity gates.
- tests/test_waybill_telegram_control_bot.py — explicit request and resolved identity.
- tests/test_daily_shipping_runtime_contract.py — ownership drift fails closed.
- tests/test_google_ops_board_scheduler_contract.py — scheduler identity contract.

Tests first:
.venv/bin/python -m pytest tests/test_google_ops_board_early_closeout_watch.py -q -k D3

Focused acceptance:
.venv/bin/python -m pytest tests/test_google_ops_board_early_closeout_watch.py tests/test_google_ops_board.py tests/test_google_ops_board_closeout.py tests/test_google_ops_board_size_writeback_noop.py tests/test_google_ops_board_prewindow_health.py tests/test_waybill_telegram_control_bot.py tests/test_daily_shipping_runtime_contract.py tests/test_google_ops_board_scheduler_contract.py -q
scripts/lint_docs.sh
git diff --check -- docs/ops/GOOGLE_OPS_BOARD_PHASE1_CONTRACT.md config/google_ops_board.yaml core/integrations/google_ops_board.py scripts/sync_google_ops_board.py scripts/run_google_ops_board_closeout_watch_scheduler.py scripts/google_ops_board_automation_common.py scripts/run_google_ops_board_closeout_scheduler.py scripts/run_google_ops_board_closeout.py scripts/sync_google_ops_board_sizes_to_db.py scripts/waybill_telegram_control_bot.py scripts/run_google_ops_board_prewindow_health.py config/daily_shipping_runtime.json scripts/validate_daily_shipping_runtime.py docs/ops/DAILY_SHIPPING_RUNTIME.generated.md tests/test_google_ops_board_early_closeout_watch.py tests/test_google_ops_board.py tests/test_google_ops_board_closeout.py tests/test_google_ops_board_size_writeback_noop.py tests/test_google_ops_board_prewindow_health.py tests/test_waybill_telegram_control_bot.py tests/test_daily_shipping_runtime_contract.py tests/test_google_ops_board_scheduler_contract.py

Closeout must contain Gate GREEN/RED, exact files changed, full command outputs,
legacy/full/partial proof, both interleaving proofs, safety caveats, rollback, and
path-limited git commit --only commands. Do not stage or commit.
```

