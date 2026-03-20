# PLAN_OCEAN_DROP_ALIGNMENT_STATUSDATE_V1_2026-02-28

## Purpose
Make “ocean drop alignment” real and non-ambiguous:

1) BUSINESS_INSIDES must be **provably aligned** to the locked ocean-drop anchor for the defined metric/date semantics, or it must be **explicitly NOT decision-grade / fail in strict mode**.

2) Stop chasing “Дата изменения статуса / statusChangeDate” from sources that do not provide it at scale; instead, establish a **source-capability contract** and implement a reliable way to ingest that field (UI export / alternative official source) into the DB so the internal engine becomes self-sufficient.

## Baseline (already implemented; do not regress)
Branch (pack): `codex/TASK-post-ocean-drop-high-roi-economics-dailyops-v1` (oracle pack generated 2026-02-28T10:17:13)
- HEAD: `39ae725`
- Key commits: `6a7ffd7`, `31e5ae8`, `406b608` (plus journal/pack commits)
- Included gates wired into strict chain:
  - `scripts/validate_business_insides_economics_ready.py`
  - `scripts/validate_ops_selection_parity.py`
  - `scripts/validate_scheduler_heartbeat.py`
  - `scripts/validate_sales_vs_waybill_parity.py`
  - `scripts/run_h5_proving_day.py`
  - `scripts/system_doctor.py`

Observed problem (must be eliminated):
- BUSINESS_INSIDES artifact can be generated while external reference check is skipped and ArchiveOrders reference is disabled, which defeats the meaning of “ocean-drop aligned”.

## Definitions (MUST be locked in docs + enforced in code)
### D1. “Ocean-drop alignment”
Alignment means:
- Internal engine truth (DB-derived views / facts) == ocean-drop reference for the same:
  - metric definitions (units/revenue),
  - terminal status set (COMPLETED/DELIVERED, returns excluded as defined),
  - transaction date semantics (creation vs delivered-date),
  - store coverage,
  - as-of boundary rules.
- Alignment is proven by strict parity validators that produce diff artifacts and fail closed on mismatch.

### D2. “Decision-grade BUSINESS_INSIDES”
Decision-grade BUSINESS_INSIDES requires:
- Locked anchor metadata present in the file:
  - anchor path, sha256, row_count
  - transaction_date_mode (creation_date | delivered_status_date)
  - external parity check result (PASS/FAIL)
- In strict mode: if external check cannot run (missing anchor), BUSINESS_INSIDES must FAIL (stop-the-line) rather than quietly skipping.

### D3. “Transaction date mode”
We will support two explicit modes:
- `creation_date` (API-native; easy automation; not the real “buyer received” timestamp)
- `delivered_status_date` (the business meaning you want; requires a source that provides it reliably)

Rule:
- No implicit switching. Every output must declare its mode.
- In strict mode, you cannot claim “delivered_status_date” truth unless coverage is proven.

## Non‑Negotiables
- Fail-closed by default.
- Single-truth ladder:
  - Specs/docs define formulas and semantics; update docs first if semantics change.
  - DB is operational truth; external files are ingested as raw truth sources and then become DB truth.
  - BUSINESS_INSIDES is derived; it does not compute business math in Excel/UI.
- Writes are opt-in only:
  - `--apply` + ENV gate + DB backup + apply manifest.

---

## Phase List

### P0 — Stop ambiguity: BUSINESS_INSIDES must never be “ungated aligned”
**Goal (measurable)**
- BUSINESS_INSIDES generation in strict/autopilot mode cannot skip the external reference check when an anchor registry exists.
- Every BUSINESS_INSIDES file includes anchor + parity status block.

**Inputs**
- `scripts/generate_business_insides.py`
- anchor registry (existing or to standardize):
  - `config/anchors/ocean_drop_sales_anchor.json`
- existing parity validator (if present) or create:
  - `scripts/validate_sales_truth_ocean_drop_parity.py` (or equivalent)

**Outputs**
- Code:
  - Update `scripts/generate_business_insides.py` to:
    1) auto-load the locked anchor from `config/anchors/ocean_drop_sales_anchor.json` when present
    2) run parity check by default in `--strict` or `--decision-grade` modes
    3) embed an “Ocean Drop Provenance” section in the markdown output
- Tests:
  - `tests/test_business_insides_requires_anchor_in_strict.py` (NEW)
  - `tests/test_business_insides_embeds_anchor_metadata.py` (NEW)
- Artifacts:
  - `exports/validation/business_insides_ocean_drop_alignment/<AS_OF>/alignment_report.json`
  - `exports/validation/business_insides_ocean_drop_alignment/<AS_OF>/alignment_report.md`
  - `exports/validation/business_insides_ocean_drop_alignment/<AS_OF>/diff_missing_order_ids.csv`
  - `exports/validation/business_insides_ocean_drop_alignment/<AS_OF>/diff_extra_order_ids.csv`

**Definition of Done**
Accepted as done only when:
- `python3 scripts/generate_business_insides.py --as-of <AS_OF> --strict` either:
  - PASS + includes anchor metadata + parity PASS, OR
  - FAIL with an explicit reason and diff artifacts (no silent skip).
- Unit tests cover the “skip is impossible” behavior.

**Validation/Gates**
- Add to strict chain (doctor + H5 runner):
  - `python3 scripts/validate_business_insides_ocean_drop_alignment.py --as-of <AS_OF> --strict` (NEW)

**Rollback**
- Revert commit(s) (no DB writes).

**Stop-the-line**
- Any “External Reference Check: skipped” in a strict run.
- Any “ArchiveOrders source status: disabled” in a strict run when anchor registry exists.

---

### P1 — Source capability contract: separate API-archive vs UI-archive truth
**Goal (measurable)**
- Make it impossible to run an unsatisfiable gate.
- If API does not provide status-change date, the API-pack contract must not require it.
- The UI-pack contract can require it.

**Inputs**
- `scripts/validate_archive_export_integrity.py` (existing)
- archive integrity evidence: legacy pack has massive missing completed status-change dates.

**Outputs**
- Docs:
  - `docs/validation/KASPI_ARCHIVE_API_PACK_CONTRACT.md` (NEW)
  - `docs/validation/KASPI_ARCHIVE_UI_PACK_CONTRACT.md` (NEW)
- Code:
  - Rename or extend validator:
    - `scripts/validate_kaspi_archive_pack_integrity.py --source api|ui` (NEW or refactor)
  - Contract behaviors:
    - `--source=api`: validate coverage, row invariants, schema; do NOT require status-change date.
    - `--source=ui`: require “Дата изменения статуса” for COMPLETED rows (100% in strict).
- Tests:
  - `tests/test_validate_kaspi_archive_pack_integrity_api.py`
  - `tests/test_validate_kaspi_archive_pack_integrity_ui.py`

**Definition of Done**
Accepted as done only when:
- Running integrity validator on API pack passes under API contract.
- Running integrity validator on UI pack fails if completed rows miss status-change date.

**Validation/Gates**
- `python3 scripts/validate_kaspi_archive_pack_integrity.py --source api --strict ...`
- `python3 scripts/validate_kaspi_archive_pack_integrity.py --source ui --strict ...`

**Rollback**
- Revert only.

**Stop-the-line**
- Any attempt to “pretend” API provides status-change date by filling blanks.

---

### P2 — Build Kaspi UI exporter (automation) to obtain “Дата изменения статуса”
**Goal (measurable)**
- Produce a UI-export archive pack per store with 90-day blocks (or platform max), including “Дата изменения статуса”.
- Minimal human: only first-time login to create persistent cookies/contexts.

**Inputs**
- Kaspi merchant cabinet UI: orders archived page (“Архив”)
- 5 store accounts (profiles)

**Outputs**
- New script:
  - `scripts/export_kaspi_archive_ui_history.py` (NEW)
- Output structure:
  - `exports/kaspi_archive_ui_history_<since>_to_<until>_<ts>/`
    - `manifest.json`
    - `run_summary.md`
    - `store_<STORE>/raw/*.xlsx` (downloaded originals)
    - `store_<STORE>/ArchiveOrders_<STORE>.csv` (normalized)
    - `store_<STORE>/windows.csv`
- Contract validator:
  - `scripts/validate_kaspi_archive_pack_integrity.py --source ui --strict --export-root <ui_pack> ...`
- Tests (non-browser):
  - window planner correctness
  - manifest determinism
  - “resume from manifest” logic

**Definition of Done**
Accepted as done only when:
- UI pack exists for all 5 stores with 100% windows completed.
- UI integrity validator PASS (strict) for the target range.
- Any UI failure produces a resumable manifest and fails closed (no partial “success”).

**Validation/Gates**
- `python3 scripts/export_kaspi_archive_ui_history.py --since ... --until ... --strict --resume ...`
- `python3 scripts/validate_kaspi_archive_pack_integrity.py --source ui --strict --export-root <ui_pack>`

**Rollback**
- No DB writes; remove output pack if needed.

**Stop-the-line**
- UI export missing “Дата изменения статуса” column or completed rows have it empty.
- Script proceeds without persistent context in strict mode (must require authenticated context).

---

### P3 — Merge UI status-change dates into the canonical ocean-drop dataset (no row count drift)
**Goal (measurable)**
- Create a new “ocean-drop anchor dataset” where:
  - row set remains the API canonical base (stable coverage),
  - “Дата изменения статуса” is filled from UI pack by (store_code, order_id),
  - missing join coverage is explicit and fails strict if non-trivial.

**Inputs**
- API pack (existing): `.../kaspi_archive_history_.../ArchiveOrders_ALL_STORES.csv`
- UI pack (P2): `exports/kaspi_archive_ui_history_.../`
- Mapped SKU/size file (existing): `ArchiveOrders_ALL_STORES_mapped_*.csv` as needed

**Outputs**
- New builder:
  - `scripts/build_ocean_drop_anchor_dataset.py` (NEW)
- Produced artifacts:
  - `exports/ocean_drop/<ts>/ArchiveOrders_ALL_STORES_ocean_drop_<ts>.csv`
  - `exports/ocean_drop/<ts>/manifest.json` (hashes + join coverage)
  - `exports/validation/ocean_drop_merge/<AS_OF>/merge_report.json/.md`
  - `exports/validation/ocean_drop_merge/<AS_OF>/diff_missing_order_ids.csv`
  - `exports/validation/ocean_drop_merge/<AS_OF>/diff_extra_order_ids.csv`
- Update anchor registry (gated apply):
  - `config/anchors/ocean_drop_sales_anchor.json` updated to new path + sha256.

**Definition of Done**
Accepted as done only when:
- Base row count == output row count.
- status-change date coverage for COMPLETED rows meets threshold (100% for nonvolatile window).
- Anchor registry update is sha-locked and validated.

**Validation/Gates**
- `python3 scripts/build_ocean_drop_anchor_dataset.py --strict ...`
- `python3 scripts/validate_sales_truth_ocean_drop_parity.py --strict --ocean-drop <new_anchor> ...`

**Rollback**
- Revert anchor registry to prior sha/path.
- Keep old anchor dataset in exports for audit.

**Stop-the-line**
- Any silent row drop or duplicate expansion.
- Any registry update without sha lock.

---

### P4 — Ingest UI status-change dates into DB (engine becomes self-sufficient)
**Goal (measurable)**
- Internal engine computes delivered-day truth from DB without reading external files at runtime.
- External ocean drop remains validation + repair reference, not an override.

**Inputs**
- New anchor dataset (P3)
- DB schema (use minimal expansion)

**Outputs**
- DB migration:
  - either:
    - new raw table `fact_kaspi_archive_statusdates` keyed by (store_code, order_id) + date, OR
    - new columns on existing table if consistent with schema contracts
- Guarded ingest script:
  - `scripts/ingest_kaspi_statusdates_from_ui_pack.py --apply` (NEW)
  - ENV gate required: `ENABLE_STATUSDATE_INGEST_APPLY=1`
  - DB backup required (runtime/backups/...)
  - apply manifest: `exports/apply_manifests/statusdate_ingest_<ts>.json`
- Update sales rebuild to use official delivered-date when present:
  - `scripts/rebuild_sales_fact_v2_from_kaspi_entries.py` (update)
  - and/or truth views feeding BUSINESS_INSIDES

**Definition of Done**
Accepted as done only when:
- With ingested statusdates, internal truth daily delivered metrics match anchor dataset in strict parity checks.
- No reference table is used as override in published truth views.
- Writes are reversible via DB backup.

**Validation/Gates**
- `python3 scripts/validate_sales_engine_self_sufficient.py --strict ...` (if present)
- `python3 scripts/validate_sales_truth_ocean_drop_parity.py --strict ...` PASS
- `python3 scripts/validate_single_truth_system.py` PASS

**Rollback**
- Restore DB from backup.
- Re-run rebuild with prior state.

**Stop-the-line**
- Any write without env gate + backup.
- Any computed “delivered-date” truth when coverage is below threshold in nonvolatile window.

---

### P5 — BUSINESS_INSIDES surface alignment gate (end-to-end meaning achieved)
**Goal (measurable)**
- BUSINESS_INSIDES daily table values MUST match ocean-drop anchor for the same date semantics (delivered-date mode) in strict runs.

**Inputs**
- BUSINESS_INSIDES generator
- new anchor dataset

**Outputs**
- Validator:
  - `scripts/validate_business_insides_ocean_drop_alignment.py` (NEW)
- Wire into:
  - `scripts/system_doctor.py`
  - `scripts/run_h5_proving_day.py`
- Artifacts:
  - `exports/validation/business_insides_ocean_drop_alignment/<AS_OF>/alignment_report.json/.md`

**Definition of Done**
Accepted as done only when:
- Running `generate_business_insides --strict` produces:
  - anchor metadata block
  - parity PASS
  - alignment PASS (BI values match anchor)
- If mismatched: fails closed with diff artifacts listing mismatched days/order IDs.

**Validation/Gates**
- `python3 scripts/validate_business_insides_ocean_drop_alignment.py --as-of <AS_OF> --strict`

**Rollback**
- Revert only; do not patch markdown outputs.

**Stop-the-line**
- Any BI file presented as “truth” while alignment gate is skipped.

---

### P6 — Operationalize with ~0–5% human time
**Goal (measurable)**
- Daily/weekly automated maintenance:
  - UI export for last N days (or 90-day window) with resume
  - ingest into DB
  - rebuild + parity + BI generation
  - produce a single red/green status artifact
- Human only:
  - occasional relogin if session expires (cookie refresh)

**Outputs**
- Scheduler integration (optional):
  - new plist + installer + heartbeat checks
- Runbook:
  - `docs/ops/KASPI_UI_ARCHIVE_EXPORT_RUNBOOK.md` (NEW)
- Daily status artifacts:
  - `exports/daily/<DAY>/DAY_STATUS.md` (if not already present)

**Definition of Done**
Accepted as done only when:
- 7 consecutive days (initial) produce GREEN daily status with:
  - UI export success
  - ingest success
  - parity PASS
  - BI alignment PASS

**Stop-the-line**
- UI export fails and system tries to proceed using stale data without explicit “stale allowance” contract.

---

## If attachments are missing (assumptions policy)
- If an input required for strict mode is missing (anchor file, UI pack, runtime logs), the correct action is STOP and emit a “missing inputs” artifact:
  - `exports/validation/missing_inputs/<AS_OF>/missing_inputs.json`
- Never silently skip parity/alignment and still produce decision-grade outputs.