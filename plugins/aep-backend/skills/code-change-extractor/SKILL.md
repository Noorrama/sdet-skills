---
name: backend-code-change-extractor
description: Post-build backend code-diff skill. Starts from a Jira Epic/Story/Task, discovers the GitLab MR links across every service, fetches each MR's diff (three-dot vs merge-base) + CR notes, and does two jobs into ONE artifact — code_change_context.json. (1) EXTRACT noise-filtered testable signal (new/changed endpoints, validation rules, error mappings, DB/enum/proto/flag/auth/dependency changes) — each tagged with its service. (2) When a baseline is supplied (an sdet_plan.json, or a Jira task/story's ACs), RECONCILE the diff against it into the embedded `reconciliation` object + a human code_diff_report.md — error-code mismatches (code returns a code no scenario asserts, or 409 where a scenario expects 422), contract changes with the scenarios they impact, information gaps the baseline missed, and suggested net-new tests. With no baseline the `reconciliation` object is null (extraction-only). Feeds sdet-plan-generator Code-change-context mode and automation-plan-generator. Use when the user says "diff the Epic MRs", "code diff", "reconcile the diff against the plan/task", "what changed vs our scenarios", or runs post-build QA on merged code.
---

# Backend Code Change Extractor (post-build code-diff + reconciliation)

At post-build, **the merged code is ground truth**. This skill produces **one JSON artifact** plus a human report:

1. `code_change_context.json` — the **extracted** testable surface, per service, **with an embedded `reconciliation` object**. The reconciliation is populated only when a baseline is supplied (an `sdet_plan.json`, or a Jira task/story's ACs); otherwise it is `null` (extraction-only). This is the single downstream contract.
2. `code_diff_report.md` — the human-facing view of the reconciliation: what the tests expect vs what the code does, and the gaps to close.

**Boundary — this skill surfaces facts; it does not author plan scenarios.** `sdet-plan-generator` Code-change-context mode still writes the delta scenarios and `existing_case_ref`/`regression_action` on the plan. Reconciliation gives that mode pre-matched signal (`impacted_scenarios[]`, `suggested_scenarios[]`) and gives a human the mismatch report to triage at the QA-Ready gate.

**Downstream consumers**
- `sdet-plan-generator` Code-change-context mode — reads `code_change_context.json` (delta scenarios) and its `reconciliation.impacted_scenarios[]` / `reconciliation.suggested_scenarios[]`.
- `automation-plan-generator` — reads exact class names, packages, `curl_reference`.

## Model
Fast tier — Haiku. Fetch + reconciliation matching is deterministic; extraction is noise-filtered pattern work.

---

## Input contract

The anchor is a **Jira key or URL** — Epic, Story, or Task. MRs usually hang off the child Stories/Tasks, not the Epic, so Phase 1 walks Epic → children. Resolve it in this order:

1. **Explicit link (preferred)** — the user gives a key (`EPIC-1122`) or URL (`…/browse/EPIC-1122`). Use it verbatim; unambiguous.
2. **Derive from `sdet_plan.json`** — when no link is given (the common run-folder case). The plan carries no structured Jira field, so parse the epic key from the trailing `(…)` in `feature_name` (e.g. `"Save Payment-Method API (EPIC-1122)"` → `EPIC-1122`). **Echo the derived key and get a yes before any fetch** — discovering MRs against the wrong epic is a silent wrong-answer failure.
3. If the plan yields no parseable key, **ask the user for it**. Never fabricate MRs.

The `*sdet_plan.json` you resolve from is also the Phase 4 reconciliation target, and its `canonical_team_id` / `code_module` route suggestions to the right team — so pointing the skill at the plan covers both the "which epic" and "reconcile against what" questions in one input.

> Note: `rfc_context.json` has a `jira_epic` field that would be the cleaner source if populated, but it is `null` in current runs — so the working fallback here is `sdet_plan.feature_name`. Not changing the other skills for now.

---

## Run order (four phases)

### Phase 1 — Discover MRs from Jira
Resolve the Jira key per the **Input contract** above. Then, using the Atlassian MCP:
1. `getJiraIssue` on the key. If it is an **Epic**, enumerate children — `searchJiraIssuesUsingJql` with `"parent" = KEY OR "Epic Link" = KEY` — and include the Epic itself. If it is a Story/Task, use it alone (plus its sub-tasks).
2. For each issue, `getJiraIssueRemoteIssueLinks` and scan the description/comments for GitLab MR URLs (`…/-/merge_requests/<iid>`). De-duplicate.
3. Record which child issue each MR came from (`story_ref`). The MR URL is self-describing: the project path's last segment is the **service**.

**Exclude test-automation repos.** Drop any MR whose project path contains **`gojek-backend-tests`** (or another test-code repo) — those are test MRs, not the system under test, and must never be diffed here. The fetch script enforces this too (`EXCLUDED_REPO_SEGMENTS`), reporting them under `excluded[]`.

**Input-sufficiency gate — reject, do not proceed, when after discovery + exclusion there is not a single usable MR.** This covers: no MR passed directly *and* the task/story has no MR link; an Epic whose children carry no MRs; or every candidate was a `gojek-backend-tests` MR. Stop and tell the user plainly, e.g.:
> "Inputs are not sufficient: no service MR was provided directly, and `<key>` (and its children) has no MR link — nothing to diff." (add "the only MR(s) found were in gojek-backend-tests, which are excluded" when that applies).

Never guess a repo, invent an MR, or fall back to extracting from the Jira description alone. Write the surviving set to `mr_links[]` (url, project, service, iid, story_ref).

### Phase 2 — Fetch per-service diffs
Run the helper (REST first, `glab` fallback; token from env, never hardcoded):
```bash
# SECURITY: token comes from GITLAB_TOKEN env var. Do not hardcode or echo it.
python3 ${CLAUDE_PLUGIN_ROOT}/skills/code-change-extractor/scripts/fetch_mr_diffs.py \
  --file mr_urls.txt --out diffs.json
```
It returns, per MR: the **three-dot diff vs merge-base** (GitLab `changes` API already diffs vs the merge base, so features already on the target branch and merge commits are excluded), the `merge_base` sha, and non-system CR notes. Group hunks by `service`.

If the fetch env is unavailable (no `GITLAB_TOKEN` and no authenticated `glab`), ask the user to paste the aggregated diff instead, and record `diff_unavailable` for any MR you could not fetch.

### Phase 3 — Extract → `code_change_context.json`
Extract **only signals that affect testable behaviour**, per the tables below. Tag every item with its `service`. Process the **aggregated** diff (feature-level), using CR notes to disambiguate intent.

### Phase 4 — Reconcile against a baseline → fill `code_change_context.json.reconciliation` + write `code_diff_report.md`
The baseline is one of: an **`sdet_plan.json`** (test design; resolve by suffix `*sdet_plan.json`), an **`automation_plan.json`** (the approved automation scenarios derived from the plan — richest baseline: each `automation_scenarios[]` carries `endpoint`, `curl_reference`, `step_descriptions[].check` assertions, and `test_data` fixtures; only `status:"approved"` scenarios are real coverage, `draft`/`deferred` are not), or a **Jira task/story's acceptance criteria**. Set `reconciliation.baseline_type` accordingly (`sdet_plan` | `automation_plan` | `jira_task`) and `reconciliation.sdet_plan_ref` to the plan/automation-plan path (null for a task baseline — the ticket is in `source_issue`).

> When reconciling against an **automation_plan**, coverage = only the `approved` automation_scenarios. Code behaviour not covered by an approved scenario is a real gap; but if most scenarios are still `draft`, say so in `unresolved[]` rather than emitting dozens of "uncovered" findings — the gap is "approval pending", not "test missing".

- **No baseline supplied** → set `reconciliation: null` (extraction-only run). Do not invent one.
- **Baseline present but a signal has no matching scenario/AC** → it becomes an `info_gap` / `suggested_scenario`; `blocking` only for genuine expectation conflicts (e.g. `status_mismatch`).

---

## What to extract (Phase 3)

| Category | Fields (each item also carries `service`) |
|---|---|
| New endpoints | `route`, `method`, `controller_class`, `controller_method`, `service_class`, `request_type`, `response_type`, `curl_reference`, `introduced_in_story` |
| Changed endpoints | `route`, `method`, `what_changed`, `previous_contract`, `new_contract` |
| Validation rules | `field` → `rule` → `error_code` → `http_status` → `layer` (`controller|service|repository`) → `class`, `story_ref` |
| Error mappings | `error_code` → `http_status` → `condition` (+ `exception` when present) |
| DB schema changes | `migration`, `table`, `type`, `columns[]`, `constraints[]`, `indexes[]`, `rollback` |
| New enums / constants | `class`, `package`, `new_values[]` |
| Dependency changes | `service` called, `endpoint`, `call_class`/`call_method`, `needs_mock`, `success_response`, `failure_response`, `failure_http_status`, `timeout_ms` |
| Auth / header changes | `header`, `type`, `required`, `change` |
| Feature flags | `flag`, `on_behaviour`, `off_behaviour`, `default_staging`, `default_production` |
| Proto changes | `proto_file`, `new_fields[]`, `changed_fields[]`, `new_rpcs[]`, **`dependency`** (the published artifact coordinate, e.g. `com.gopay:order-management-service-proto`), **`version`** (the new version, e.g. `30.27.0-RELEASE`), `previous_version` (when visible), `bumped_in[]` (the MRs/services that adopted it). Capture the artifact **version bump** even when the MR only edits a build file — the automation agent needs `dependency`+`version` to update the dep, recompile, and write tests against the new fields/RPCs. **Resolving the version:** for a *consumer* repo it's the pinned line (`implementation 'com.gopay:X:30.27.0-RELEASE'`). For the *producer* proto repo (which does not pin its own version), don't leave it null and don't confuse it with `protoVersion`/`protobufVersion` (that's the protoc toolchain, a different field) — resolve the published artifact version from the repo's **tags**: `GET /projects/:enc/repository/commits/:merge_sha/refs?type=tag` gives the tag(s) containing the change; the earliest is where it first shipped. Record `version` (first tag with this change), `latest_version`, and `min_version_for_all_epic_changes` when several MRs land across tags. |

**`curl_reference`**: minimal valid curl with placeholders (`{token}`, `{payment_id}`, `{amount}`) — no real values.

### What NOT to extract (noise filter)
- Logging, metrics, tracing additions
- Formatting / whitespace-only changes
- Private/internal methods with no public API impact
- The service's own unit-test files (dev test scope)
- Javadoc / comment-only changes
- Build config changes unless they introduce a feature flag

---

## Reconciliation rules (Phase 4)

**Every finding must carry a concrete `resolution` — or be dropped.** `error_code_mismatches[]`, `contract_changes[]` and `info_gaps[]` each require a `resolution` string that states the *answer* the diff gives, not a task:
- Plan left it unspecified → say **what it is now** (e.g. "gated by the global boolean `ENABLE_X` (default true), not a whitelist").
- Field/RPC renamed → say **what it was renamed to** (e.g. "plan's `UpdateRefundStatus` shipped as `SyncRefundOrderStatus(Order)→GenericResponse`").
- Error code/message changed → say **the new value** (e.g. "409 → 422", "`social_group_not_found` is swallowed; create returns 2xx").

If the diff does **not** yield a concrete resolution, **do not emit the finding** — never ship a bare "verify / confirm / capture / unspecified / TBD". (Put a genuine open question in `unresolved[]` instead, or make it a `suggested_scenario`.) `matched`/`covered` items state the resolution as the behaviour that matches.

All arrays below live **inside the `reconciliation` object** of `code_change_context.json`. Compare each extracted signal against the baseline. For an **sdet_plan** baseline: error codes live in `step_descriptions[].expected_result`, endpoints in `step_descriptions[].curl_reference`, flags in `tags[]`. For a **Jira task/story** baseline: parse the acceptance-criteria table (GIVEN/WHEN/THEN) and use each AC as a scenario — reference them by an AC label (e.g. `AC-CS-3`) since there are no `SC-` ids.

### A. Error-code mismatches → `error_code_mismatches[]`
For every `error_mappings[]` / `validation_rules[]` `(error_code, http_status)` in the diff:

| Situation | `type` | `disposition` |
|---|---|---|
| No scenario's `expected_result` mentions this error code | `code_uncovered` | `new_negative_scenario` — add a `suggested_scenario` |
| A scenario asserts this code but with a **different HTTP status** than the code returns | `status_mismatch` | `modify_scenario` — list `impacted_scenarios[]`, set `blocking:true` |
| A scenario asserts a code the diff **no longer produces** | `scenario_stale` | `modify_scenario` (or deprecate) — `impacted_scenarios[]` |
| Code and scenario agree | `matched` | `covered` (emit for audit; not a gap) |

A `status_mismatch` is the highest-value find: e.g. code now returns `422` where `SC-…` asserts `409`. Always `blocking:true` and name the scenario.

### B. Contract changes → `contract_changes[]`
New/removed endpoints, request/response field add/remove/type/required changes, proto field/RPC changes, new enum values, header changes. For each, list `impacted_scenarios[]` (scenarios whose `curl_reference`/`expected_result` touch that endpoint) and set `regression_action`:
- **`modify`** when the change alters what an existing test should assert — including the silent case: a **response POJO that tolerates unknown fields lets an existing test keep PASSING after a field is added while covering less**. Flag it; nobody re-runs their way to noticing.
- **`none`** for net-new endpoints with no existing coverage (→ `suggested_scenario`).

### C. Information gaps → `info_gaps[]`
Behaviour the diff reveals that the plan/RFC/PRD did not account for: a feature flag whose default differs from what the plan assumed, a new auth/header requirement, a boundary value (13–19 digits, 5000 ms timeout) not in any scenario, a new downstream dependency needing a mock, a DB constraint (`UNIQUE (customer_id, fingerprint)`) implying a duplicate-path test. Record `category`, `detail` (what the code does), `expected_from` (rfc/prd/plan/none), and `gap` (what the author must now decide/assert).

### D. Impacted existing scenarios → `impacted_scenarios[]`
The modify/reuse/deprecate shortlist the Code-change-context mode acts on. `suggested_action: modify` **requires** `change_required` — name the assertion that becomes insufficient, not merely "affected". Link back to the ECM-/CC-/IG- ids.

### E. Suggested new tests → `suggested_scenarios[]`
Signals with no covering scenario become **hints** (never `SC-` ids — use `SUG-###`). Give `name`, `test_layer`, `priority_hint`, `tags` (negative/boundary/flag_on/flag_off/…), `source_signal`, `owning_team` (canonical_id from `team_registry.json`), and a `curl_reference`. The Code-change-context mode owns the final scenario.

**Priority hint heuristic:** `P0` when the uncovered path is a money/state-mutating failure or a flag that gates the whole endpoint; `P1` for other negative/boundary paths; `P2` for cosmetic/response-shape additions.

### F. Reviewer-raised signals (CR notes)
Review comments are a signal source in their own right, not just diff-disambiguation — a reviewer often names an edge case, a wrong error code, a race, or a backward-compat risk that the diff alone does not reveal. Mine the non-system CR notes fetched in Phase 2 and route each test-relevant one:

| Reviewer comment says… | Route to |
|---|---|
| "returns 409 but should be 422 / wrong status" | `error_code_mismatches[]` (`status_mismatch`, likely `blocking`) |
| "did we handle timeout / null / empty / concurrent case?" | `suggested_scenarios[]` (tag `negative`/`boundary`/`concurrency`) if uncovered |
| "this changes the response shape / breaks callers" | `contract_changes[]` with `regression_action: modify` |
| "flag default / auth / dependency behaviour" note | `info_gaps[]` (matching `category`) |
| Open/unresolved thread on test-relevant behaviour | `unresolved[]` (`reason: ambiguous`), or a `suggested_scenario` flagged provisional |

Attribute the source in `code_ref` (`mr` + `condition: "reviewer @<user>: <gist>"`) and set `source_signal: "cr_note"` on any suggestion so a human can trace it back to the thread. **Skip nitpick/style comments** (formatting, naming, "LGTM", "nit:") — same noise bar as the diff filter. Never invent an assertion a reviewer merely *asked about*; an open question becomes a gap/`unresolved`, not a settled expectation.

---

## Multi-service handling
- One `code_change_context.json` (with its embedded `reconciliation`) for the **whole Epic**; every item carries `service`.
- Resolve each service to its `canonical_id` / module via `${CLAUDE_PLUGIN_ROOT}/config/team_registry.json` (match the service name against `aliases`; matching is case-insensitive and strips hyphens/spaces). Use it to set `owning_team` on suggestions and to route to the right BrowserStack project downstream.
- `services[]` at the root lists every service touched.

## `code_diff_report.md` (human-facing)
Ordered for triage at the QA-Ready gate:
1. **Blocking mismatches** — `status_mismatch` + any `blocking:true`, each with service, code_ref, and the scenario to modify.
2. **Error-code coverage** — table: error code · http status · covered? · scenario / suggestion.
3. **Contract changes** — endpoint · change · impacted scenarios · `regression_action`.
4. **Information gaps** — category · what the code does · what to decide.
5. **Suggested new tests** — name · layer · priority hint · rationale.
6. **Counts** — mirror `summary`.

Keep it factual. Do not editorialize who was "wrong".

## Guardrails
- **Reject on insufficient input.** If no MR is passed directly and none is found on the Jira task/story/epic (or every candidate is a `gojek-backend-tests` MR), stop with "inputs are not sufficient" — do not extract from the Jira text or guess a repo.
- **Never diff `gojek-backend-tests` (or other test-automation repos).** They are test code, not the system under test; exclude their MRs during discovery and even if passed directly.
- **Every reconciliation finding needs a concrete `resolution`** (what it is now / renamed to / updated to). Drop any finding you cannot resolve from the diff — do not emit "verify/confirm/unspecified".
- Process the **aggregated** Epic diff (feature is the unit of extraction), not individual commits.
- Use CR notes to clarify ambiguous diffs; never invent an error code, status, or field not in the diff.
- If a field appears in both a new endpoint and a validation rule, extract it in both places.
- Every error code in the diff must appear in exactly one `error_code_mismatches[]` row (even `matched`) — that is the coverage proof.
- **Never hardcode or echo the GitLab token**; it is read from `GITLAB_TOKEN` by the fetch script only.
- Do not write `SC-` ids — suggestions are `SUG-###`; only sdet-plan-generator mints scenario ids.
- If **no baseline** is supplied, set `reconciliation: null` (extraction-only) — do not fabricate a baseline. If a baseline is supplied but incomplete, prefer `info_gaps` / `unresolved` over guessing.

## Validate
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/code-change-extractor/scripts/validate.py code_change_context.json
```
Schema: `schemas/code_change_context.schema.json` (the `reconciliation` object is embedded and validated in place).

## Log
Counts per extract category; reconciliation `summary` (mismatches / contract changes / info gaps / impacted / suggested / blocking). Flag any validation-rule error code not found in `rfc_context.json error_codes` — a coverage gap signal.
