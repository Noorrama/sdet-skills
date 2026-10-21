---
name: gbt-mr-raiser
description: "Branch, commit, push, and open a Draft merge request for the test code gbt-test-code-generator wrote into .gbt_repo, using the codegen manifest as the authoritative file list and carrying its TODOs into the MR description as a reviewer checklist. Runs last in the orchestrated backend-test pipeline, after test-code-validator. Two push paths: a local git worktree push, or the GitLab API when no local push is possible. Never pushes to the default branch, never commits a file the manifest does not name, and always opens the MR as a Draft."
version: 1
disable-model-invocation: true
---

# GBT MR Raiser

You are turning the working-tree changes `gbt-test-code-generator` made in the **stage-0
worktree** (`workspace.gbt_repo` from `workspace.json`) into a **Draft merge request** on
`gojek-backend-tests`. That path is **not** necessarily the operator’s main IDE checkout — it is
the isolated `automate/…` worktree `gbt-workspace-prep` created under `GBT_WORKTREES_DIR` off the
**base clone** (`GBT_REPO_PATH` or plugin `./.gbt_repo`). Every earlier stage in this pipeline
is read-or-write-local; this is the **only stage that leaves the machine**. Treat it that way.

This skill mirrors what `agent/automation_job.py` already does in the Python pipeline, so an
MR raised from the skills path is indistinguishable from one raised by the job.

## Absolute rules (violating any is a critical failure)

1. **Get explicit human go-ahead before the first outward call.** Print the plan — branch
   name, target branch, file list with actions, commit message, MR title — and wait for
   confirmation. A push and an MR are visible to the whole team and cannot be quietly undone.
   `--yes` from the caller (or `GBT_MR_AUTO_CONFIRM=1`) is the only thing that waives this.
2. **The manifest is the file list. Never `git add -A`.** Commit exactly the paths in
   `codegen_manifest.files[].path`. A blanket add sweeps in `.gbt-venv/`, gradle caches,
   `local.properties`, and whatever else the working clone accumulated — that is how a
   credential reaches a remote.
3. **Never push to the default branch.** Use it only as the MR *target*, and refuse if the
   source branch equals it (`refuses_default_branch`).
3a. **Take the branch from `workspace.json`; never recompute it.** Stage 0 already created
   `workspace.branch` and the worktree is already on it, so there is nothing to compute and
   nothing to switch. Recomputing a name that contains random hex cannot agree with the one
   that exists, and you would push a branch holding none of the generated code. Verify
   `git rev-parse --abbrev-ref HEAD` equals `workspace.branch` and reject
   `workspace_branch_mismatch` if not.
3b. **Confirm the base has not moved under the run.** Fetch and compare
   `origin/<base_branch>` against `workspace.base_sha`. Equal → proceed. Moved → still proceed
   (the run is internally consistent, and a reviewer merges), but add a `warnings[]` entry and
   an MR-body note naming both SHAs. Never rebase or reset the branch to the new base: that
   silently changes code that was already validated and compiled.
4. **Always `draft: true`.** Never open a ready MR, never mark ready, never merge. A human
   moves it out of Draft once CI is green.
5. **Credentials come from the environment, never from a URL, argument, or this file.** Read
   `GITLAB_TOKEN` from the environment or the team's secret store. Never echo it, never
   interpolate it into a remote URL, never write it into a log line, MR body, or run summary.
   If the clone's `origin` already embeds a token, **do not use that URL** — use `GITLAB_URL`
   + `GBT_PROJECT_ID` with the token supplied out-of-band, and warn that the embedded
   credential should be rotated.
6. **Never commit a secret or real personal data.** Before committing, scan the manifest's
   files for anything matching a token/key/password shape or a real phone/email/NIK. A hit is
   a **reject** (`secret_in_generated_code`), not a warning — the upstream fix is
   `gbt-test-code-generator` rule 10, which forbids hardcoded credentials in the first place.
7. **Idempotent, not duplicating.** If the branch already exists, push onto it. If an open MR
   already exists for that source branch, **update it** (description refresh) and return its
   existing IID and URL. Never open a second MR for the same branch.
8. **Carry the TODOs across verbatim.** `codegen_manifest.todos[]`, plus any
   `needs_human_placement` entry and any `undecidable` scenario from `method_decisions.json`,
   become an unchecked checklist in the MR description. A TODO that only exists in a JSON
   artifact on someone's laptop is a TODO nobody will action.
9. **Output exactly one JSON object.** No prose outside it.

## Environment

```
GITLAB_URL=https://<your-gitlab-host>       # no trailing slash
GITLAB_TOKEN=                                # TODO: Securely load this value from an environment variable or secrets vault. Do not hardcode.
GBT_PROJECT_ID=                              # numeric project id, or URL-encoded path
# the repo is workspace.gbt_repo (stage 0); GBT_REPO_PATH is only for standalone use
GBT_MR_AUTO_CONFIRM=0                        # 1 waives rule 1 — CI only
```

Verify reachability and scope before doing anything mutating:

```bash
: "${GITLAB_URL:?set GITLAB_URL}"; : "${GBT_PROJECT_ID:?set GBT_PROJECT_ID}"
[ -n "${GITLAB_TOKEN:-}" ] || { echo "GITLAB_TOKEN not set — refusing"; exit 1; }
curl -sS --fail-with-body -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  "$GITLAB_URL/api/v4/projects/$GBT_PROJECT_ID" -o /dev/null && echo "project reachable"
```

Never add `-v`, and never print the header — `curl -v` writes `PRIVATE-TOKEN` to stderr.

## Naming conventions (match the Python job exactly — do not invent your own)

| Thing | Value |
|---|---|
| Branch | **read from `workspace.branch`** — created by `gbt-workspace-prep` as `automate/<slug(prd_title)>-<slug(module)>-<6 hex>`. Never recomputed here (rule 3a) |
| Commit message | `test(automation): <prd_title> [<module>]` |
| MR title | `Automated backend tests: <prd_title> [<module>]` |
| Target branch | the project's default branch, resolved at run time — never hardcoded |
| Draft | always |

## Inputs

| Path | Required | Used for |
|---|---|---|
| `runs/<epic>/pass1/artifacts/codegen_manifest.json` | yes | the authoritative file list, `todos[]`, `needs_human_placement`, counts, `module` |
| `runs/<epic>/pass1/artifacts/validation_report.json` | yes | whether CI-blocking findings remain; summarised into the MR body |
| `runs/<epic>/pass1/artifacts/method_decisions.json` | no | `undecidable` scenarios, appended to the TODO checklist |
| `runs/<epic>/pass1/artifacts/workspace.json` | yes | `gbt_repo` (the worktree to commit from), `branch`, `base_branch`, `base_sha`, `base_may_be_stale` |
| `{codegen_dir}/run.json` (`run_json` in spawn prompt) | yes | **Codegen** review gate, and `prd_title` for the commit/MR strings |
| the run's worktree | yes | `workspace.gbt_repo` — the tree holding the generated files. Never the base clone. |

## Definition of Ready (DoR)

- `run.json` shows `review.status == "approved"` for this pass.
- `codegen_manifest.json` exists with at least one entry in `files[]`.
- Every `files[].path` exists on disk inside the clone, and `git status` shows it as modified
  or untracked — a manifest entry with no corresponding change means the manifest is stale.
- `workspace.json` present; the worktree exists and its HEAD is `workspace.branch`.
- The worktree is on a clean footing: no merge/rebase in progress, no detached HEAD.
- `GITLAB_URL`, `GBT_PROJECT_ID`, `GITLAB_TOKEN` all present; project reachable.

## Reject if

| Reason | Detail |
|---|---|
| `review_not_approved` | Gate is `pending` or `changes_requested` |
| `missing_input` | `codegen_manifest.json` or `run.json` absent/unparseable |
| `nothing_to_commit` | `files[]` empty, or no manifest path is actually dirty in git. Legitimate outcome — say so, do not open an empty MR |
| `stale_manifest` | A manifest path does not exist on disk, or is not dirty — regenerate rather than committing a partial set |
| `gbt_repo_missing` | No candidate in the resolution order is a git work tree |
| `refuses_default_branch` | The source branch equals the default branch |
| `workspace_missing` | No `workspace.json` — `gbt-workspace-prep` did not run. Do not fall back to computing a branch in the base clone |
| `workspace_branch_mismatch` | The worktree's HEAD is not `workspace.branch` — something switched branches mid-run |
| `secret_in_generated_code` | A manifest file contains something matching a credential or real-PII shape. Name the file and the line, **never the value** |
| `credentials_unavailable` | `GITLAB_TOKEN` unset, or the project probe returned 401/403 |
| `push_failed` | Local push and API fallback both failed — report both errors verbatim |
| `not_confirmed` | Rule 1 confirmation was neither given nor waived |

Write `runs/<epic>/pass1/rejects/gbt-mr-raiser.json` with
`{"stage": "gbt-mr-raiser", "reason": "<code>", "detail": "...", "remediation": "..."}`
and **make no outward call**.

## Procedure

1. Read the inputs. Run DoR and reject checks. Scan for secrets (rule 6) **before** anything
   mutating — a secret found after the push is already leaked.
2. Read `workspace.json`. Confirm HEAD equals `workspace.branch` (rule 3a) and that it differs
   from `workspace.base_branch`. Fetch and compare `origin/<base_branch>` to
   `workspace.base_sha` (rule 3b).
3. Print the plan and get confirmation (rule 1).
4. **Push — local path first.** The worktree is already on the run's branch, cut from the
   pinned base; there is no branch to create and nothing to switch. **Do not** `cd` to
   `GBT_REPO_PATH`, the plugin `.gbt_repo`, or the user's unrelated local clone — only
   `workspace.gbt_repo`.
   ```bash
   cd "$(jq -r .gbt_repo "$WORKSPACE")"   # the worktree, never the base clone
   git add -- $MANIFEST_PATHS             # never -A, never .
   git commit -m "$COMMIT_MSG"
   git push -u origin "$(jq -r .branch "$WORKSPACE")"
   ```
   No `git switch` here is deliberate: switching with uncommitted generated changes is what
   fails when upstream touched the same file, and stage 0 removed the need for it.
5. **Fallback — API path.** If the local push fails (no push rights on the clone, or its
   remote embeds a credential you must not use), degrade to the API and say so in the summary:
   `POST /projects/:id/repository/branches` then
   `POST /projects/:id/repository/commits` with one action per manifest file (`create` or
   `update`, matching the manifest's own `action`), content read from disk.
6. **Open the Draft MR** — `POST /projects/:id/merge_requests` with `source_branch`,
   `target_branch` = default, the conventional title, the description from the template below,
   and `draft: true`. If an open MR already exists for the source branch, `PUT` its
   description instead (rule 7).
7. Write the run record and print the summary. Include the MR URL and IID; never the token.

## MR description template

Mirrors `_mr_description` in the Python job, so both paths read alike:

```markdown
Automated backend tests generated by **Agent PM**.

- Test files created: **<counts.files_created>**
- Test files updated: **<counts.files_updated>**
- Scenarios covered: **<counts.generated>**
- Scenarios skipped: **<counts.skipped_dedup + exact_match + undecidable>** (see checklist)

**Notes:** <codegen_manifest.notes>

**Validation:** <passed | N errors, M warnings> — from validation_report.json

### TODOs needing your help
- [ ] <each codegen_manifest.todos[] entry>
- [ ] <each needs_human_placement entry — file + why placement is unverified>
- [ ] <each undecidable scenario — scenario_id + the enricher error, coverage never checked>

_This MR is a Draft until CI is green._
```

If `workspace.base_may_be_stale` is true, or the base moved since `base_sha`, say so in
**Notes** with both SHAs — a reviewer needs to know the diff's base is not current HEAD.

If `fix_budget_exhausted` was true upstream, say so in **Notes** explicitly — a reviewer must
know the code stopped being auto-fixed rather than converged.

## OUTPUT — return ONLY a single valid JSON object

```json
{
  "epic_id": "EPIC-1122",
  "pass": 1,
  "generated_at": "<ISO-8601>",
  "module": ":driver-platform",
  "push_path": "local",
  "branch": "automate/payment-card-vaulting-driver-platform-a1b2c3",
  "target_branch": "<default branch>",
  "commit": {"sha": "<short sha>", "message": "test(automation): Payment card vaulting [:driver-platform]"},
  "files_committed": [
    {"path": "driver-platform/src/test/java/tests/paymentService/componentTests/PaymentControllerTest.java", "action": "update"}
  ],
  "mr": {"iid": 4821, "url": "<web_url>", "draft": true, "created": true},
  "todos_carried": 3,
  "validation": {"passed": false, "errors": 0, "warnings": 1},
  "warnings": ["origin remote embeds a credential — used API path instead; rotate that token"],
  "notes": "<what was pushed, which path was used, what a reviewer should look at first>"
}
```

`push_path` is `local` or `api`. `mr.created` is `false` when an existing MR was updated.
Use `""` for a missing string, `[]` for a missing list. Never use `null`. **Never include a
token, a tokenised remote URL, or any credential value in this object.**

## What this skill does not do

- **It does not generate or edit test code.** That is `gbt-test-code-generator`; this skill
  commits what it already wrote and fails on a stale manifest rather than patching a gap.
- **It does not compile or run tests.** CI does, once the branch is pushed. `gbt-build-fix`
  owns local compile failures, and should have run before this stage.
- **It does not mark the MR ready, approve it, or merge it.** Draft in, human out.
- **It does not decide whether the tests are good.** `test-code-validator`'s report is
  summarised into the MR body for a reviewer, never gated on by this skill.
