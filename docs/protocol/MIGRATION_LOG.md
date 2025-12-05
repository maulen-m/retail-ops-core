# MIGRATION_LOG
## Purpose

Track every **intentional reuse** of code, ideas, or workflows from the legacy `kaspi_etl` repos into the new **Autonomous_business** repo.

Goals:

- Avoid blindly copying legacy complexity.
- Make every reuse decision explicit, with ROI and risk.
- Keep a single place where we can see **what still depends on legacy assumptions**.

---

## 1. How to Use This Log

- One row = one **migration unit** (module, script, function, pattern, or protocol).
- Log *only* things that are **actually reused** (code, algorithms, or designs), not just inspiration.
- For each row:
  - Be explicit about **reuse level** (Idea / Re‑implement / Partial copy / Full copy).
  - Capture **why** we reused it (time saved vs building from scratch).
  - Capture **what protects us** (tests, guards, simplifications).

Update this file **whenever**:

- You copy or heavily adapt code from legacy repos.
- You port an algorithm or business rule from legacy docs.
- You adopt a legacy process/protocol (e.g. `TASKS.yaml`, `PROTECTED_PATHS.yaml` style).

---

## 2. Reuse Levels

Use these exact labels in the `Reuse_Level` column:

- `IDEA_ONLY` – We only took the concept, re‑designed from scratch.
- `REIMPLEMENTED` – Algorithm/logic reused, but code is new and simplified.
- `PARTIAL_COPY` – Some functions/blocks adapted from the legacy file.
- `FULL_COPY` – File/Module copied with minimal changes (should be rare).

---

## 3. Status Values

Use these in the `Status` column:

- `PLANNED` – Approved to migrate, not started.
- `IN_PROGRESS` – Being ported / refactored.
- `ACTIVE` – In production use in new repo.
- `DEPRECATED` – Replaced in new repo; legacy dependency removed.

---

## 4. Migration Entries

> Add new rows to this table; keep sorted by `ID` (M‑001, M‑002, …).

| ID   | Date       | Actor | Legacy_Source_Path                          | New_Target_Path                                   | Scope                    | Reuse_Level     | Status      | Rationale (time saved / why worth it)                              | Risks / Legacy Assumptions to Watch                            | Tests / Guards (how we know it's safe)                           |
|------|------------|-------|---------------------------------------------|---------------------------------------------------|--------------------------|-----------------|------------|--------------------------------------------------------------------|-----------------------------------------------------------------|------------------------------------------------------------------|
| M-000| 2025-12-xx | Adil  | `backend/utils/excel_safe_writer.py`       | `autonomous_business/core/excel_safe_writer.py`   | Excel writer + blocklist | REIMPLEMENTED   | PLANNED    | Example row – delete or adapt. Safe-writer pattern is solid and saves days vs rewriting. | Assumes same Excel engine semantics; must recheck for Mac Excel | New unit tests for writer; dry-run on `Inventory_Core_V15_FINAL.xlsx` |

_Add your first real row as `M-001`._

---

## 5. Migration Rules

1. **Default = Do NOT migrate.** Only reuse when:
   - It clearly saves multiple hours/days **and**
   - It doesn’t drag in legacy complexity you don’t need.

2. **Every FULL_COPY must be temporary.**
   - Mark with a note: “To be simplified or replaced by date YYYY‑MM”.

3. **One migration unit at a time.**
   - No giant “copy half the repo” moves.
   - Prefer thin slices: a single script, a single pattern, or a single protocol.

4. **Each migration must have a test or check.**
   - New code must be covered by a unit/integration test, or a clearly defined manual check.

5. **Never overwrite new‑repo patterns.**
   - If legacy style conflicts with Autonomous_business conventions (paths, naming, config), **new repo wins.**

---

## 6. Open Questions / Parking Lot

Use this section to capture items you *might* want to migrate later:

- [ ] Candidate: `scripts/orders_audit.py` – good pattern for gap detection, but heavy; maybe only reuse the *idea*.
- [ ] Candidate: `docs/protocol/RULES.md` – some rules can be ported into new repo’s `RULES.md`.
