# Git Governance Contract

Status: canonical for `~/Docs/Autonomous_business`.

This contract governs agents, automation, and owner-operated Git work in this
repository. More restrictive safety rules still apply.

## 1. Branching model

- The trunk is `greenpath/20260613-phase2-truth`.
- G4 owns the pending default-branch migration. Until G4 lands, no other branch
  may be treated as trunk.
- Work uses short-lived `lane/<name>` or `task/<name>` branches.
- A concurrent lane uses a dedicated worktree under exactly one of:
  `~/Docs/worktrees/<repo>/` or `~/.claude-worktrees/`.
- A worktree must never be created inside the repository tree.
- Every lane removes its worktree when the lane closes.

## 2. Commit contract

- The subject is at most 72 characters.
- The preferred subject is lowercase `scope: summary`.
- A conventional-commit subject such as `fix(import): preserve row identity`
  is also valid.
- The body is free-form.
- Agent commits MUST include at least one `Co-Authored-By:` trailer.
- Agent commits SHOULD reference the owning spec or run folder in the body.
- Merge commits and revert commits are exempt from the subject-format rule.

## 3. Precision-commit doctrine

- Commit with explicit paths: `git commit --only <paths>`.
- Never use `git add -A` or `git commit -a`.
- Review `git diff --cached --name-status` before committing.
- More than eight staged files is blocked by the shared pre-commit hook.
- A deliberate commit above that limit requires
  `GIT_GOVERNANCE_OVERRIDE=1` and an audit record.
- An override narrows one named exception; it does not waive unrelated rules.

## 4. Push cadence

- Trunk is pushed at least nightly by the backup-push agent.
- A production-critical landing is pushed immediately after its acceptance
  gates pass.
- The day-end unpushed-work SLO is zero commits.
- A failed backup push produces an operations-outbox WARN and remains unresolved
  until a later push proves zero unpushed commits.

## 5. Forbidden operations

The following are forbidden unless the owner authorizes the exact exception and
the applicable bypass is explicit:

- `git commit --no-verify` or `git commit -n`;
- force push, including `--force`, `-f`, and `--force-with-lease`;
- `git reset --hard`;
- `git clean -fd` or any broader forced clean;
- `git stash drop` or `git stash clear`;
- history rewriting, including filter tools and rewriting pushed refs;
- any local or global `core.hooksPath` change.

Harness-level exceptions require owner-authorized `DCG_BYPASS=1`. Hook-level
exceptions require owner-authorized `GIT_GOVERNANCE_OVERRIDE=1`. A command that
crosses both layers needs both; neither variable is standing permission.

## 6. Override semantics and audit

`GIT_GOVERNANCE_OVERRIDE=1` permits only the rule named by the hook message. The
hook appends one JSON object per exception to:

`~/Docs/Oracle/agent-scripts-main/hooks/override_audit.jsonl`

Each object contains `ts`, `repo`, `hook`, `rule`, `cwd`, and
`message_subject`. An unwritable audit path emits a warning but does not turn an
authorized override into a block. Audit-write failure never weakens the normal
rule check when no override is present.

`--no-verify` bypasses client hooks before they can audit. It therefore remains
a harness/CI prohibition, not a valid hook override.

## 7. Enforcement map

| Rule | DCG harness | Shared hook | CI | Advisory |
|---|---|---|---|---|
| Valid subject and 72-character limit | — | `commit-msg` block | candidate | contract |
| Agent co-author trailer | — | cannot identify agent | candidate | contract |
| Explicit-path commit; no blanket add/commit | proposed | staged-count proxy | candidate | contract |
| More than eight staged files | — | `pre-commit` block + audited override | candidate | contract |
| Secret/protected/large-file floor | — | `pre-commit` block | existing repo gates | contract |
| No `--no-verify` / `-n` | proposed | intrinsically bypassed | candidate | contract |
| No non-fast-forward trunk push | proposed | `pre-push` block + audited override | remote protection pending | contract |
| No force/reset-hard/clean/stash-drop/history rewrite | proposed | force-to-trunk proxy only | remote protection pending | contract |
| No `core.hooksPath` changes | proposed | cannot self-protect | candidate | contract |
| Nightly zero-unpushed SLO | — | `pre-push` warning | weekly report | contract |
| Worktree roots and lane cleanup | — | — | candidate | contract |

“Proposed” means the exact deny-rule changes require separate orchestrator
review and activation. The shared hooks do not claim to observe command-line
force flags; `pre-push` blocks a provable non-fast-forward update to trunk.

## 8. Dirty-tree lane adjudication

1. Snapshot branch, HEAD, remotes, staged paths, and the complete porcelain
   status before writing.
2. Attribute every dirty path to its lane or owner. Unknown ownership is a stop
   condition, not permission to tidy.
3. Preserve unrelated changes. Never stash, unstage, discard, or fold them into
   the current lane.
4. If paths do not overlap, work only on the named paths and use
   `git commit --only` at handoff.
5. If paths overlap or ownership is ambiguous, move the new lane to an allowed
   worktree or stop for owner/orchestrator adjudication.
6. DB writers serialize and isolate `AB_DATA_DIR` as required by the repo
   parallel-execution protocol.
7. At lane close, record exact verification and rollback commands, prove the
   intended branch is pushed, and remove the lane worktree.
