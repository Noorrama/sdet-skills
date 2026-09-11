---
name: gbt-workspace-prep
description: "Prepare an isolated, up-to-date GBT working tree before any code generation: fetch the base clone, resolve the project's default branch, cut the run's branch off fresh origin/<default>, and create a per-run git worktree that every later stage works in. Writes workspace.json, which downstream stages read to resolve the repo. Runs first in the orchestrated backend-test pipeline so decisions, generation, compilation, and the MR all see one identical tree. Never writes into the base clone, never touches the default branch, and supports an offline mode that records base staleness instead of silently generating against an old base."
version: 1
disable-model-invocation: true
---

# GBT Workspace Prep

You are giving one pipeline run its own tree. Without this stage, generation happens in the
shared base clone on whatever branch is checked out — then `gbt-mr-raiser` fetches and cuts a
branch off *fresh* `origin/<default>`, so the code was decided and compiled against one base
and diffed against another. Two runs at once also overwrite each other.

This mirrors `_prepare_worktree()` / `gradle_runner.ensure_base_repo` + `create_worktree` in
the Python job, so both paths isolate the same way.

## What this stage guarantees to every later stage

1. The tree is a **fresh** checkout of `origin/<default branch>` (or explicitly flagged stale).
2. It is **isolated** — the base clone's working tree and default branch are never modified.
3. The run's **branch already exists**, so `gbt-mr-raiser` commits onto the same tree the
   decisions were made on; its own fetch becomes a confirmation, not a base change.
4. Concurrent runs cannot collide, because the worktree path contains the branch's unique hex.

## Absolute rules (violating any is a critical failure)

1. **Never generate in the base clone.** The base clone is fetched and read; the run happens
   in the worktree. If a worktree cannot be created, that is a **reject** — never fall back to
   "just use the base clone", which is precisely the failure this stage exists to remove.
2. **Never check out, reset, or commit on the default branch.** Fetch updates
   `refs/remotes/origin/*` only. The base clone's checked-out branch must be exactly what it
   was when you started; verify that before you finish.
3. **The branch is created here, once, and its name is an output.** `gbt-mr-raiser` must read
   `workspace.branch` rather than recomputing it — two independent computations of a name
   containing random hex will not agree, and the push would go to a branch nobody reviewed.
4. **A failed fetch is not a silent stale base.** If the fetch fails and the caller did not
   pass `--offline`, reject `fetch_failed`. With `--offline`, proceed from the existing
   `origin/<default>` ref and set `base_may_be_stale: true` **and** a `todos[]` line that
   reaches the MR body. A reviewer must never have to guess whether the base was current.
5. **Never use a credential embedded in a remote URL.** If `origin` is of the form
   `https://<user>:<token>@host/…`, do not fetch through it: use `GBT_FETCH_REMOTE` (or an SSH
   remote) and add a `warnings[]` entry that the embedded credential should be rotated. Never
   print the URL, and never write it into `workspace.json`.
6. **Refuse a branch that is already checked out somewhere.** `git worktree add` fails on such
   a branch; detect it first (`git worktree list`) and reject `branch_already_checked_out`
   rather than emitting a half-made workspace. Stale worktree bookkeeping copied between
   clones makes this more common than it sounds.
7. **Leave the workspace on failure, remove it only when told.** Teardown is a separate,
   explicit action (`--teardown`) so a failed run stays inspectable. Never remove a worktree
   holding uncommitted changes unless `--force` is passed.
8. **Output exactly one JSON object.** No prose outside it.

## Environment

```
GBT_REPO_PATH=                    # base clone override; else $CLAUDE_PLUGIN_ROOT/.gbt_repo, else ./.gbt_repo
GBT_WORKTREES_DIR=.gbt_worktrees  # where per-run trees live; relative to CWD, gitignored
GBT_FETCH_REMOTE=                 # use instead of `origin` when origin embeds a credential
GBT_BASE_BRANCH=                  # pin the base; default is the remote's HEAD
```

Keep `GBT_WORKTREES_DIR` **outside** the plugin directory. A worktree inside
`plugins/aep-backend/` is at the mercy of `claude plugin update`, which re-syncs that tree.

## Inputs

| Path | Required | Used for |
|---|---|---|
| `runs/<epic>/run.json` | yes | the review gate, and `prd_title` for the branch name |
| `runs/<epic>/pass1/artifacts/automation_plan.json` | yes | `module` for the branch name |
| the base GBT clone | yes | resolved per the order below; fetched, never modified |

Base-clone resolution, first hit wins — the same order the rest of the pipeline uses:
`$GBT_REPO_PATH` → `$CLAUDE_PLUGIN_ROOT/.gbt_repo` → `./.gbt_repo`.

## Definition of Ready (DoR)

- `run.json` shows `review.status == "approved"` for this pass.
- The base clone resolves, is a git work tree, and has a clean working tree — a dirty base
  means someone is mid-edit, and its changes would leak into the new worktree.
- No rebase/merge/bisect in progress in the base clone.
- `GBT_WORKTREES_DIR` is writable and is not inside `$CLAUDE_PLUGIN_ROOT`.

## Reject if

| Reason | Detail |
|---|---|
| `review_not_approved` | Gate is `pending` or `changes_requested` |
| `missing_input` | `run.json` or `automation_plan.json` absent/unparseable |
| `gbt_repo_missing` | No candidate in the resolution order is a git work tree — **or** `GBT_REPO_PATH` was set and is not one. An explicit override that does not resolve is an error, never a fallback to another clone |
| `base_clone_dirty` | Uncommitted changes in the base clone. Name the files; do not stash them on the user's behalf |
| `fetch_failed` | Fetch failed and `--offline` was not passed (rule 4). Include git's error verbatim, minus any URL |
| `default_branch_unresolved` | Neither `origin/HEAD` nor `GBT_BASE_BRANCH` yields a branch that exists on the remote |
| `branch_already_checked_out` | The computed branch is checked out in another worktree (rule 6) |
| `worktree_create_failed` | `git worktree add` failed. Report git's error; never degrade to the base clone |
| `worktrees_dir_inside_plugin` | `GBT_WORKTREES_DIR` resolves inside `$CLAUDE_PLUGIN_ROOT` — a plugin update would destroy the run |

Write `runs/<epic>/pass1/rejects/gbt-workspace-prep.json` with
`{"stage": "gbt-workspace-prep", "reason": "<code>", "detail": "...", "remediation": "..."}`.

## Procedure

```bash
set -eu
BASE_REPO="$GBT_REPO"                    # resolved per the order above
REMOTE="${GBT_FETCH_REMOTE:-origin}"

# 0. base clone must be clean, and remember where it was
[ -z "$(git -C "$BASE_REPO" status --porcelain)" ] || { echo "base_clone_dirty"; exit 1; }
ORIG_BRANCH=$(git -C "$BASE_REPO" rev-parse --abbrev-ref HEAD)

# 1. refuse a credential-bearing remote (rule 5)
case "$(git -C "$BASE_REPO" remote get-url "$REMOTE")" in
  *://*:*@*) echo "origin embeds a credential — set GBT_FETCH_REMOTE" >&2; exit 1 ;;
esac

# 2. fetch, or record staleness
if git -C "$BASE_REPO" fetch "$REMOTE" --prune --quiet; then STALE=false; else
  [ "${OFFLINE:-0}" = "1" ] || { echo "fetch_failed"; exit 1; }; STALE=true
fi

# 3. default branch
BASE_BRANCH="${GBT_BASE_BRANCH:-$(git -C "$BASE_REPO" symbolic-ref --quiet --short \
  "refs/remotes/$REMOTE/HEAD" 2>/dev/null | sed "s|^$REMOTE/||")}"
[ -n "$BASE_BRANCH" ] || { echo "default_branch_unresolved"; exit 1; }
BASE_SHA=$(git -C "$BASE_REPO" rev-parse "$REMOTE/$BASE_BRANCH")

# 4. branch name — same convention as gbt-mr-raiser, computed once, here
slug() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]\+/-/g;s/^-//;s/-$//'; }
BRANCH="automate/$(slug "$PRD_TITLE")-$(slug "$MODULE")-$(openssl rand -hex 3)"
git -C "$BASE_REPO" worktree list --porcelain | grep -qx "branch refs/heads/$BRANCH" \
  && { echo "branch_already_checked_out"; exit 1; }

# 5. isolated worktree off the fresh base
WT="$(cd "${GBT_WORKTREES_DIR:-.gbt_worktrees}" 2>/dev/null && pwd || \
      { mkdir -p "${GBT_WORKTREES_DIR:-.gbt_worktrees}" && cd "$_" && pwd; })/${BRANCH##*/}"
git -C "$BASE_REPO" worktree add -b "$BRANCH" "$WT" "$REMOTE/$BASE_BRANCH" --quiet

# 6. the base clone must be exactly where it was (rule 2)
[ "$(git -C "$BASE_REPO" rev-parse --abbrev-ref HEAD)" = "$ORIG_BRANCH" ] || \
  { echo "base clone branch changed — aborting"; exit 1; }
echo "workspace ready: $WT on $BRANCH (base $REMOTE/$BASE_BRANCH @ ${BASE_SHA:0:8})"
```

Then write `workspace.json`. Every later stage resolves the repo from it — the worktree path,
not the base clone.

## Teardown — `--teardown`

Run after `gbt-mr-raiser` succeeds, never before. Removing the worktree before the MR exists
discards the generated code.

```bash
git -C "$BASE_REPO" worktree remove "$WT"        # add --force only if asked
git -C "$BASE_REPO" worktree prune
```

Keep the branch: it is what the MR is built from. Skip teardown when the run rejected, and say
so — a failed run's tree is the only evidence of what went wrong.

## OUTPUT — write `runs/<epic>/pass1/artifacts/workspace.json`

```json
{
  "epic_id": "EPIC-1122",
  "pass": 1,
  "generated_at": "<ISO-8601>",
  "base_repo": "/abs/path/to/.gbt_repo",
  "base_branch": "master",
  "base_sha": "7281071881c0f1a1d2e3f4a5b6c7d8e9fa0b1c2d",
  "base_may_be_stale": false,
  "branch": "automate/payment-card-vaulting-driver-platform-a1b2c3",
  "worktree_path": "/abs/path/to/.gbt_worktrees/payment-card-vaulting-driver-platform-a1b2c3",
  "gbt_repo": "/abs/path/to/.gbt_worktrees/payment-card-vaulting-driver-platform-a1b2c3",
  "module": ":driver-platform",
  "module_root": "driver-platform",
  "offline": false,
  "warnings": [],
  "todos": [],
  "notes": "<what was fetched, what the base was, anything a reviewer should know>"
}
```

`gbt_repo` is the field downstream stages read — it is the **worktree**, deliberately duplicated
from `worktree_path` so a stage never has to know which of the two to prefer. `base_repo` is
for git plumbing only (`git -C "$base_repo" worktree …`); nothing generates into it.

Use `""` for a missing string, `[]` for a missing list. Never use `null`. Never write a remote
URL, token, or credential into this file.

## What this skill does not do

- **It does not generate, compile, commit, push, or open an MR.** It prepares a tree and gets
  out of the way.
- **It does not pull or rebase the run's branch afterwards.** The base is pinned at `base_sha`
  for the whole run on purpose: a base that moves mid-run is what makes a decision and its diff
  disagree. If the base has moved by MR time, that is the reviewer's merge to do.
- **It does not clone.** A missing base clone is `gbt_repo_missing`, not an invitation to
  create one.
- **It does not delete anything on the happy path.** Teardown is explicit and separate.
