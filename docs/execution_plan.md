# Execution Plan — Steipete-inspired workflow upgrade (Codex-first)

## Scope
Implement the minimal workflow upgrades + unblock the end-of-day pipeline:
- Add repo-root AGENTS.md
- Add scripts/committer helper
- Add/extend .gitignore for local artifacts
- Fix log_audit ImportError blocking run_end_of_day Step 2

## Preconditions
- Work on a fresh branch: task/TASK-XXX-agentic-workflow-upgrade
- Do NOT edit .env
- Do NOT run destructive git commands (reset --hard / restore older commits) unless user says so.

---

## Step 1 — Add AGENTS.md (repo root)

Create file: AGENTS.md
- Include: current state, entrypoints, non-negotiables, doc index, commands, prompt templates.

Acceptance:
- File exists at repo root.
- Codex can “see” it without hunting in .claude/.

---

## Step 2 — Add scripts/committer

Create file: scripts/committer
- Copy exact content from steipete gist:
  https://gist.github.com/steipete/88a38157e8c9d1896443eca09e95e163
- Ensure executable bit set (chmod +x scripts/committer)

Acceptance:
- Running `scripts/committer "chore: test" AGENTS.md` works (with actual staged changes).
- It stages only explicitly listed files.

---

## Step 3 — Add/extend .gitignore

Edit: .gitignore (create if missing)
Add entries (minimum):
- db/app.db
- exports/
- *.xlsx
- ~$*.xlsx
- .DS_Store
- __pycache__/
- *.pyc

Acceptance:
- `git status` no longer shows db/app.db or exports/ as untracked noise (once removed from index if previously tracked).

---

## Step 4 — Fix end-of-day pipeline blocker: log_audit import

Current failure:
- scripts/run_end_of_day.py → sync_crm_to_db.py → core/ingest/sales_ingest.py imports:
  from core.db.ledger import add_ledger_event, log_audit
- core/db/ledger.py does not export log_audit → ImportError.

Choose ONE solution (prefer A for auditability):

A) Implement log_audit in core/db/ledger.py
- Define `log_audit(conn, event_type, payload, run_id=None, step_name=None, created_at=None)`
- Store audit events in an existing table if present (or create a small fact_audit_log table if schema supports).
- Keep idempotency: inserting the same audit line twice should not break the pipeline.
- Add unit test verifying log_audit exists and is callable.

B) Remove log_audit dependency from sales_ingest
- Replace log_audit calls with RunTracker step logging or standard logger.
- This is faster but reduces auditability.

Acceptance:
- `python scripts/run_end_of_day.py --verbose` passes Step 2 (Sync CRM to DB).
- Add at least 1 targeted test that would have caught this (import-level test).

---

## Step 5 — Verification gates

Run:
1) python scripts/validate_params.py --strict
2) python scripts/run_end_of_day.py --verbose
3) python -m pytest tests/ -q (or at least the tests relevant to ingest/ledger)

Acceptance:
- Step 0 and Step 2 no longer fail.
- Test suite remains green (or document known xfails).

---

## Step 6 — Commit discipline

Commits MUST be atomic. Suggested commit split:
1) docs: add AGENTS.md
2) chore: add scripts/committer + .gitignore updates
3) fix: implement log_audit (or remove import) + tests

Use scripts/committer for each commit.

---

## Step 7 — Handoff summary (for Code Captain review)

Provide:
- branch name
- commit hashes
- commands run + outputs (especially run_end_of_day Step 2)
- any tradeoffs/decisions made
