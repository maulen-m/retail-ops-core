# plan_oracle_automation.md
**Purpose:** eliminate manual Oracle pack creation after each Codex task by generating deterministic, reviewable packs from git signals (no API usage).

## Scope (this plan)
✅ Auto-generate Oracle **packs to disk** after a task (manual trigger first).  
❌ No auto-posting into ChatGPT UI (explicitly out of scope).  
✅ Keep workstreams separate:
- **A)** Oracle automation (this plan)
- **B)** P2 internal pipeline fixes (separate)

---

## 1) What we’re building
A single command that creates a timestamped markdown pack:

`~/Docs/Oracle/<project>/<YYYY-MM-DD>/<HHMMSS>_<task>.md`

Pack contents must include:
- Task metadata (repo, branch, head, range, who/when, “commands run”, tests)
- Git diff summary + full diff for the selected range
- Full content for changed files (or an excerpt if too large)
- Always-include “high-signal” files via allowlist (docs + entrypoints)
- Deterministic selection rules (reviewable policy)

We generate the pack by:
1) computing the **file list** (changed + allowlist + policy adds)
2) generating two temporary files:
   - `0_META.md` (metadata)
   - `0_DIFF.md` (diff stat + full diff)
3) calling Oracle in **render-only mode** and redirecting stdout to the target `.md` file:
   - `oracle --render -p "<prompt>" --file <paths...> > output.md`

No API keys required.

---

## 2) Oracle dependency choice (local vs npx)
Preferred (deterministic, offline):
- Use local oracle repo binary (after build):
  - `~/Docs/steipete/oracle-main/dist/bin/oracle-cli.js`

Fallback:
- `npx -y @steipete/oracle`

Our script will auto-detect the local binary, otherwise fallback to npx.

---

## 3) File selection policy (deterministic)

### Inputs (default)
- `--range HEAD~1..HEAD` (last commit), and require a clean working tree.

### Always include (allowlist)
- `.claude/CLAUDE.md` (or repo agent brain if present)
- `AGENTS.md` (Codex brain)
- `db/schema.sql`
- `scripts/run_end_of_day.py`
- `scripts/validate_params.py`
- `docs/DAILY_SOP.md`
- `docs/protocol/VALIDATION_CHECKLIST.md`
- `docs/protocol/FX_RATES_MECHANISM_V1.md` (if present)

### Include (from git)
- All files changed in the range, excluding denylist patterns and binaries.

### Policy-based adds (optional, deterministic)
- If any changed file matches `core/calc/**` → include `docs/inventory/Master_Inventory_Rules_v6.md` (if present)
- If any changed file matches `core/po/**` → include `docs/protocol/PO_making_logic_v2.md` (if present)
- If any changed file matches `core/capital/**` or `scripts/execute_po_draft.py` → include `core/capital/guardrails.py` and `docs/protocol/VALIDATION_CHECKLIST.md`

### Denylist (never include content, but diff still captured)
- `.env`, `db/app.db`, `db/*.db`, `exports/**`, `excel/**`, `**/.DS_Store`
- `*.pdf`, `*.png`, `*.jpg`, `*.zip`, `*.sqlite`, `*.xlsx` (unless explicitly changed and needed)

### Size limit
- Default max content per file: 300 KB (configurable).
- If bigger: include an excerpt file (first/last N lines) and keep full diff.

---

## 4) Trigger strategy (Phase 0 → Phase 1)
### Phase 0 (recommended now): manual trigger
- Codex finishes task → runs:
  - `scripts/oracle_pack.sh --task P2 --range HEAD~1..HEAD --cmd "pytest ..." --cmd "python scripts/run_end_of_day.py --verbose"`
- Human pastes pack into Code Captain.

### Phase 1 (optional later): git post-commit hook
- Only on `task/*` branches:
  - run generator automatically after commit.
- Keep it opt-in.

---

## 5) Update to workflow rules (agents.md)
Definition of done for Codex tasks:
- ✅ gates green (or known xfail documented)
- ✅ atomic commits
- ✅ oracle pack generated to ~/Docs/Oracle/... and linked in handoff

---

## 6) Acceptance criteria
1) Running one command produces a `.md` pack at the required path.
2) Pack contains metadata + diff + file contents (changed + allowlist).
3) No manual file picking or prompt writing required.
4) Works with no API usage.
