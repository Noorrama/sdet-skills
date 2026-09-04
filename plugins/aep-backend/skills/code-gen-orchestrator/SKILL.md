---
name: code-gen-orchestrator
description: Master orchestrator for the agentic backend-test codegen path — takes an approved automation_plan.json, extracts each scenario's (module, endpoint), enriches the plan with existing GBT coverage via automation-plan-test-enricher (Memgraph), then sequences gbt-method-decision-maker (method-level reuse decision from scenario_gbt_context), the module profile resolver, gbt-code-understanding, gbt-context-builder (placement and packages), gbt-test-code-generator, and test-code-validator's fix-and-revalidate loop into one epic run. Use after the SDET plan's human review gate is approved, when you want the whole plan-through-validated-code path run in order instead of invoking each stage skill by hand. Does not re-implement any stage's logic — it sequences the existing skills and enforces the same gates and reject conventions they already have.
version: 1
disable-model-invocation: true
---

# Code Gen Skill (Master Orchestrator)

You are sequencing existing, independently-correct skills into one run for one epic. You own
**ordering, handoff, and the validate-fix loop** — you do not re-decide anything a stage skill
already decided. If you find yourself re-picking a test class, re-judging which method a
scenario belongs to, or second-guessing a Memgraph result, stop: those decisions belong to
`automation-plan-test-enricher`, `gbt-method-decision-maker`, and `gbt-context-builder`, not
to you.

## The chronology, in one paragraph

You start from an **approved `automation_plan.json`** — not from the extractors. For each
scenario you read its `(module, endpoint)` and hand the plan to
`automation-plan-test-enricher`, which queries the GBT dependency graph in **Memgraph** and
writes `scenario_gbt_context` back onto every scenario: the endpoint's declaring file, its
upstream/downstream files, the `@Test` methods proven to call it, and the data providers and
assertion classes those methods use. That **enriched plan** is what
`gbt-method-decision-maker` consumes: it opens the real test classes, assertion classes, and
data-provider classes named in `scenario_gbt_context`, builds a summary at **method,
assertion, and data-provider level**, compares that summary against each scenario's steps and
`description` in the plan, and decides which existing `@Test` method the scenario belongs to —
or which method codegen must modify, which data provider needs one new row, and which
scenarios are genuinely new. Only then do you resolve the **module profile** skill, load
`gbt-code-understanding`, and run `gbt-context-builder` for placement and packages, so
`gbt-test-code-generator` can emit code against verified anchors.

Your output is the same set of artifacts the stages would produce if run by hand, plus two
transformations you own: the merged `test_data_payloads` on the plan, and the enrichment
handoff. The endpoint-level coverage discovery (`automation-plan-test-enricher`), the
method-level reuse decision (`gbt-method-decision-maker`), and the placement/package decision
(`gbt-context-builder`) stay as separate artifacts, each owned by the skill that produced it.

## Absolute rules (violating any is a critical failure)

1. **Never skip the human review gate.** Stop after `sdet-plan-generator` and wait for
   `runs/<epic_id>/run.json` `review.status == "approved"` before running
   `automation-plan-generator`. This is the same gate those skills already enforce
   individually — you must not route around it by, say, calling `gbt-test-code-generator`
   directly with a hand-built plan.
2. **Run stages in this exact order, and stop on the first reject.** Do not run a later stage
   against a partial or rejected earlier artifact — that is how a "graph was down" reject
   becomes indistinguishable from "nothing to cover" several stages downstream.
3. **Do not re-derive a decision a stage skill already made.** The enricher's Memgraph
   results, `gbt-context-builder`'s layer verdicts, `automation-plan-generator`'s routing
   fields, and `gbt-test-code-generator`'s file placement are each that skill's
   responsibility. Your job ends at handing its output to the next stage unmodified, except
   for the two explicit transformations named in rules 4 and 4a.
3a. **Carry `protocol` and the gRPC transport fields through every stage, unchanged.** When a
   scenario carries `protocol: "grpc"`, it and its `grpc_service`, `rpc_method`, `request_type`,
   `response_type`, `proto_reference`, `rpc_type` and `expected_status` must survive each handoff
   verbatim. Never coerce them into REST fields (`http_method`, `path`, `headers`, `request_dto`,
   `response_dto`, `http_status`) to satisfy a stage's schema — if a stage rejects because it
   cannot express a gRPC scenario, that is a reject to surface, not to work around. A scenario
   with no `protocol` key is REST by definition, so existing plans pass through untouched. When
   resolving the module skill, resolve it on **(module, transport)**: gRPC scenarios route to
   `gopay-grpc-api-test-writer` / `gofood-grpc-api-test-writer`, everything else to the REST
   writer. A single plan may legitimately mix both.
4. **The `test_data_payloads` merge is one of exactly two artifact transformations you
   perform.** After `test-data-generator` writes `test_data.json`, copy its array verbatim
   into the plan under a new top-level key `test_data_payloads`, then re-write the plan. Do
   not alter any existing field while doing this, and do not drop `test_data.json` from disk —
   it stays as the record of what that stage produced.
4a. **Endpoint extraction is the other, and it is read-only on the plan.** You read
   `(module, endpoint)` — falling back to `service_name` when `module` is absent — off each
   scenario and hand them to `automation-plan-test-enricher` as its `$module`/`$endpoint`
   inputs. **You do not normalise, strip, or guess them yourself**: the verb/scheme/host
   stripping and the module→repo-directory fallback ladder are the enricher's Step 2
   derivation rules, and duplicating them here is how the two copies drift. A scenario with
   neither `module` nor `service_name`, or with an empty `endpoint`, is handed over as-is —
   the enricher records `no_module`/`no_endpoint` on it and the run continues.
4b. **Never fabricate coverage when enrichment fails.** `scenario_gbt_context` carrying an
   `error` is not the same as one carrying empty lists. Empty lists mean *matched, nothing
   found* — a genuinely uncovered endpoint, and `gbt-method-decision-maker` must treat it as
   `no_match` with `requires_new_test_class: true`, which makes
   `gbt-test-code-generator` create a new test class **and** its first `@Test` method. An
   `error` means *could not resolve*, becomes `undecidable`, and writes nothing. Preserve the
   distinction verbatim; never collapse an `error` into an empty list to keep the pipeline
   moving, and never treat an empty candidate set as a reason to skip a scenario — an endpoint
   with zero coverage is the case this pipeline exists to fix.
5. **The validate-fix loop has a bounded budget, never an open one.** Re-run
   `gbt-test-code-generator`'s fix path only within the existing budgets
   (`GBT_MAX_FIX_RETRIES` for compile/CI-class failures, `GBT_MAX_PROFILE_FIX_RETRIES` for
   profile/rule violations from `test-code-validator`) — these are the same budgets
   `agent/automation_agent.py` / `agent/automation_job.py` already use, not new numbers you
   invent for the orchestrated path.
6. **Reject, don't degrade, at the orchestrator level too.** If any stage rejects, write
   `runs/<epic_id>/pass<N>/rejects/code-gen-skill.json` naming which stage failed and copy
   that stage's own reject payload in verbatim — do not paraphrase or summarize a reject.
7. **Output exactly one JSON run summary at the end.** No prose, no markdown fences outside
   the final summary object.

## Resolving the GBT repo

Once stage 0 has run there is only one answer: **`workspace.gbt_repo`** — the per-run
worktree. Stages 1-13 read that field and nothing else.

The order below resolves the **base clone**, which is stage 0's own input (and the fallback for
running a stage standalone, outside an orchestrated run). First hit wins:

1. **`$GBT_REPO_PATH`** — an explicit override, absolute or relative to CWD. Always respected.
2. **`$CLAUDE_PLUGIN_ROOT/.gbt_repo`** — the clone shipped alongside this plugin
   (`plugins/aep-backend/.gbt_repo`). This is the normal case when running from Claude Code.
3. **`./.gbt_repo`** — a clone in the current working directory (the agentPM layout).

**Never generate into the base clone during an orchestrated run.** It is fetched and read;
the run happens in the worktree. A stage that resolves to the base clone while
`workspace.json` exists is a bug, not a fallback.

```bash
resolve_gbt_repo() {
  # An explicit override is authoritative: if it is set but not a git work tree,
  # FAIL — never fall through. Falling through means a typo'd GBT_REPO_PATH
  # silently generates into whichever clone happens to be next in the list.
  if [ -n "${GBT_REPO_PATH:-}" ]; then
    if [ -d "$GBT_REPO_PATH/.git" ]; then
      GBT_REPO=$(cd "$GBT_REPO_PATH" && pwd); return 0
    fi
    echo "gbt_repo_missing: GBT_REPO_PATH=$GBT_REPO_PATH is not a git work tree" >&2
    return 1
  fi
  for c in "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/.gbt_repo}" "./.gbt_repo"; do
    [ -n "$c" ] && [ -d "$c/.git" ] && { GBT_REPO=$(cd "$c" && pwd); return 0; }
  done
  echo "gbt_repo_missing: set GBT_REPO_PATH" >&2; return 1
}
resolve_gbt_repo && echo "GBT_REPO=$GBT_REPO"
```

**`GBT_REPO_PATH` set but invalid is a hard `gbt_repo_missing`, never a fallback.** Silently
using a different clone than the operator named is worse than stopping: the run would read,
generate, and commit against a repo nobody asked for.

Resolve **once** and pass the absolute path down; never re-resolve per file. Two stages
resolving differently is how generated code lands in one tree and gets committed from another.

`$CLAUDE_PLUGIN_ROOT` is set by Claude Code when a plugin skill runs. It is **not** set when a
skill is read by path (Cursor, or `cat SKILL.md`), so candidate 2 silently drops out there —
which is why candidate 1 exists. Never hardcode an absolute path to the clone: it differs per
machine, and the plugin is distributed.

## Stage order

| # | Stage skill | Reads | Writes | Gate before running |
|---|---|---|---|---|
| 0 | `gbt-workspace-prep` | `run.json`, `automation_plan.json`, the base clone | `workspace.json` — fetched base, run branch, isolated **worktree** | **human review gate approved**; base clone clean; network (or `--offline`) |
| 1 | **endpoint extraction (this skill)** | `automation_plan.json` — `module`/`service_name` + `endpoint` per scenario | nothing (read-only; the pairs are passed in-memory to step 2) | **human review gate approved** (`run.json`), plan present with ≥1 `is_dedup: false` scenario |
| 2 | `automation-plan-test-enricher` | the plan + the GBT dependency graph in **Memgraph** (bolt) | `automation_plan_enriched.json` — `scenario_gbt_context` per scenario | bolt reachable; `endpoint_context.cypher` resolved |
| 3 | `test-data-generator` | enriched plan, `rfc_context.json`, `sdet_plan.json` | `test_data.json` | step 2 succeeded, non-empty `to_generate` |
| 4 | **merge step (this skill)** | `test_data.json` | enriched plan (adds `test_data_payloads`) | step 3 succeeded |
| 5 | `gbt-method-decision-maker` | **`scenario_gbt_context` from the enriched plan** + the real test / assertion / data-provider classes it names, from `$GBT_REPO_PATH`; each scenario's steps + `description` | `method_decisions.json` | enriched plan merged (step 4) |
| 6 | **module profile resolver (this skill)** | the target module → `gbt-module-<normalized>` (`:driver-platform` → `gbt-module-driver-platform`) | nothing written — loaded into context | step 5 succeeded |
| 7 | `gbt-code-understanding` | the enriched plan, the module profile, `$GBT_REPO_PATH` | nothing written — the five-phase analysis loaded into context | module profile resolved (or explicitly absent) |
| 8 | `gbt-context-builder` | `rfc_context.json`, `tasks_context.json`, `regression_context.json`, code graph | `gbt_context.json` — `packages`, `module_root`, exemplars, layer verdicts | code graph reachable for target module |
| 9 | `gbt-test-code-generator` | enriched plan (merged), `gbt_context.json`, `method_decisions.json`, `run.json` | `.java` files, `codegen_manifest.json` | review gate still approved |
| 10 | `test-code-validator` | generated Java, `rules.json`, the enriched plan | `validation_report.json` | at least one file generated |
| 11 | validate-fix loop | `validation_report.json` errors | re-invokes step 9 on `implicated_files`, then re-runs step 10 | `validation_report.blocked == true` and retry budget remains |
| 12 | `gbt-build-fix` | `codegen_manifest.json`, the clone | compiled module; corrected `.java` files in place | validate-fix loop settled |
| 13 | `gbt-mr-raiser` | `codegen_manifest.json`, `validation_report.json`, `method_decisions.json`, `run.json`, the clone | branch + commit + **Draft MR** | step 12 settled (compiling, or budget exhausted with TODOs recorded); **explicit human go-ahead** |

### Why the order is this way

- **Stage 0 exists because generation and the MR must see one tree.** Without it, stages 1-12
  run against whatever branch the shared clone happens to be on, and stage 13 then cuts its
  branch from *fresh* `origin/<default>` — so a scenario can be judged `exact_match` against a
  stale tree, or `no_match` because a test landed upstream an hour earlier and was never seen.
  `git switch -c` can also refuse outright when upstream touched the same file, stranding a
  full generate-and-compile run in `push_failed`. Stage 0 pins the base once, at `base_sha`,
  and every later stage works in that worktree.

- **Steps 1–2 before 5** because the decision-maker's candidate classes now come from
  Memgraph's `test_methods_calling_endpoint`, which is *proven* call-graph evidence, rather
  than from a name-similarity ranking. Enrich first or the decision-maker has nothing to open.
- **Step 8 after 5**, not before it. `gbt-context-builder` answers *where a file goes* —
  `packages.test`/`packages.main`, `module_root`, exemplars — which `gbt-test-code-generator`
  needs for path anchoring. It does **not** need to run before the decision-maker any more,
  because the enricher now supplies the reuse evidence the decision-maker used to take from
  `gbt_context.decisions.test`.
- **Steps 6–7 are context loads, not artifact stages.** They write nothing. Skipping them does
  not fail the run, but output quality drops sharply — record it in the summary if a module
  has no profile.
- **Steps 10–12 are three different questions, in the only order that works.**
  `test-code-validator` (10) asks *does this follow the rules and the module profile* — cheap,
  static, and worth fixing before spending a Gradle cycle. `gbt-build-fix` (12) asks *does it
  compile* — the expensive check, so it runs once the rule violations are already settled.
  Running 12 before 10 means recompiling after every profile fix. Neither runs the tests; CI
  does, after 13 pushes.
- **Step 13 is the only stage that leaves the machine,** and the only one that is not
  idempotent from a reviewer's point of view — a pushed branch and an opened MR are visible to
  the team. It runs **last**, and never without explicit human go-ahead. `fix_budget_exhausted:
  true` from either loop does **not** block it: a Draft MR carrying honest TODOs is more useful
  than generated code stranded in a working clone. Say so in the MR body.
- **The two budgets are separate and must not be pooled.**
  `GBT_MAX_PROFILE_FIX_RETRIES` bounds the step 10–11 loop; `GBT_MAX_FIX_RETRIES` bounds step
  12's compile loop. Spending one on the other is how a run burns its compile attempts on
  formatting violations and pushes code that never compiled.

`sdet-plan-generator`, `automation-plan-generator`, and the extractors before them are **not**
run by this skill — it starts from an already-approved `automation_plan.json`. Wire
`automation-plan-generator` in ahead of step 1 only if the epic has no plan yet.

## The validate-fix loop, precisely

1. Run `test-code-validator`. If `passed: true`, stop — done.
2. If `blocked: true` and the profile-fix budget is not exhausted, send
   `validation_report.implicated_files` (already capped and ordered by the validator) back to
   `gbt-test-code-generator`'s fix path with the specific violations, decrement the budget,
   and re-run only those files. Do not re-run `gbt-method-decision-maker` for a fix pass — its
   verdict was about placement, not about the rule violations this loop is fixing. Do not
   re-run `automation-plan-test-enricher` either: a fix pass changes generated files, not the
   graph, and re-querying Memgraph mid-loop can silently swap the coverage evidence the
   decision-maker already ruled on.
3. Re-run `test-code-validator` on the updated files. Go to 1.
4. If the budget is exhausted and errors remain, **stop the loop** (do not loop indefinitely),
   write the remaining `validation_report` findings into `codegen_manifest.todos[]` as
   reviewer TODOs, and record `fix_budget_exhausted: true` in the final run summary. This is a
   legitimate stopping condition, not a reject — partially-fixed generated code with clear
   TODOs is still useful to a reviewer.

## Definition of Ready (DoR)

- `runs/<epic_id>/pass1/artifacts/automation_plan.json` exists, is schema-valid, and its pass
  has an approved `run.json` gate — or the caller explicitly asks this skill to run
  `automation-plan-generator` first.
- At least one scenario with `is_dedup: false`, and at least one of those carries a non-empty
  `endpoint` (otherwise there is nothing for the enricher to resolve).
- **Memgraph is reachable over bolt** for the enricher, and its `endpoint_context.cypher`
  resolves. Checked at step 2 — do not trust a prior run's liveness.
- The code graph is reachable for the target module (checked again at step 8, independently of
  the Memgraph check — they are different backends and either can be down alone).
- The **base clone** resolves, is clean, and its `./gradlew` is executable (stage 0 fetches it; step 12
  cannot compile without it).
- For step 13 only: `GITLAB_URL`, `GBT_PROJECT_ID`, and `GITLAB_TOKEN` are available. Check
  this **before** step 1, not at step 13 — discovering the push has no credentials after a
  full generate-and-compile run wastes the whole run.

## Reject if

Any individual stage's own reject conditions fire — see that stage's `SKILL.md`. This skill
adds exactly one orchestration-level reject:

| Reason | Detail |
|---|---|
| `stage_order_violated` | A later stage was about to run without its declared upstream artifact present — refuse rather than run against a stale or missing file |
| `review_gate_not_approved` | Attempted to run stage 1 or later before `run.json.review.status == "approved"` |
| `fix_loop_would_be_unbounded` | The validate-fix loop was about to run without a tracked remaining budget |
| `enrichment_unusable` | Every non-`is_dedup` scenario came back from step 2 with an `error` in `scenario_gbt_context`. The graph is down or the module never resolves — running `gbt-method-decision-maker` on this would turn "could not check" into a plan-wide `no_match` and duplicate every existing test. Copy the enricher's own stderr summary in verbatim |
| `enrichment_partial_unacknowledged` | Some scenarios errored and some enriched. **Not a reject on its own** — continue, but record every errored `scenario_id` with its verbatim `error` in the run summary's `enrichment` block. Rejecting here is wrong: the enriched scenarios are still actionable. Silently proceeding is also wrong |

On reject, write `runs/<epic_id>/pass<N>/rejects/code-gen-skill.json`:

```json
{"stage": "code-gen-skill", "failed_at": "<stage-name>",
 "upstream_reject": {"...": "verbatim contents of that stage's own reject file"},
 "remediation": "<the exact command or stage to re-run>"}
```

## OUTPUT — return ONLY a single valid JSON object

Written to `runs/<epic_id>/pass1/artifacts/code_gen_run.json` (or `pass2/` on Pass 2), as the
one summary of the whole orchestrated run — every artifact it references was written by the
stage skill responsible for it, not by this skill.

```json
{
  "epic_id": "EPIC-1122",
  "pass": 1,
  "started_at": "<ISO-8601>",
  "finished_at": "<ISO-8601>",
  "stages": [
    {"stage": "gbt-workspace-prep", "status": "completed", "artifact": "runs/EPIC-1122/pass1/artifacts/workspace.json", "detail": "worktree on automate/... off master@72810718; base fresh"},
    {"stage": "endpoint_extraction", "status": "completed", "detail": "6 scenarios, 5 distinct (module, endpoint) pairs extracted; 1 scenario has no endpoint (DB-only)"},
    {"stage": "automation-plan-test-enricher", "status": "completed", "artifact": "runs/EPIC-1122/pass1/artifacts/automation_plan_enriched.json", "detail": "5 enriched, 1 errored, 6 total"},
    {"stage": "test-data-generator", "status": "completed", "artifact": "runs/EPIC-1122/pass1/artifacts/test_data.json"},
    {"stage": "merge_test_data_into_plan", "status": "completed", "detail": "test_data_payloads set from test_data.json, 5 entries"},
    {"stage": "gbt-method-decision-maker", "status": "completed", "artifact": "runs/EPIC-1122/pass1/artifacts/method_decisions.json", "detail": "1 exact_match, 1 closest_match_modify, 1 data_provider_new_row, 2 no_match"},
    {"stage": "module_profile_resolver", "status": "completed", "skill": "gbt-module-driver-platform"},
    {"stage": "gbt-code-understanding", "status": "loaded", "detail": "five-phase analysis applied; no artifact written"},
    {"stage": "gbt-context-builder", "status": "completed", "artifact": "runs/EPIC-1122/pass1/gbt_context.json"},
    {"stage": "gbt-test-code-generator", "status": "completed", "artifact": "runs/EPIC-1122/pass1/artifacts/codegen_manifest.json"},
    {"stage": "test-code-validator", "status": "completed_after_fix", "attempts": 2, "artifact": "runs/EPIC-1122/pass1/artifacts/validation_report.json"},
    {"stage": "gbt-build-fix", "status": "completed", "detail": "compileTestJava failed on 1 fabricated method signature; fixed in 1 attempt, module now compiles"},
    {"stage": "gbt-mr-raiser", "status": "completed", "detail": "Draft MR !4821 opened from automate/... with 3 TODOs carried", "mr_url": "<web_url>"}
  ],
  "compile": {"passed": true, "attempts_used": 1, "budget": 2, "fix_budget_exhausted": false},
  "enrichment": {
    "enriched": 5, "errored": 1, "total": 6,
    "module_fallbacks": [{"scenario_id": "SC-004", "matched_as": "driver_platform"}],
    "errors": [{"scenario_id": "SC-006", "error": "no_endpoint: scenario SC-006 has an empty endpoint (DB/infra-only test?)"}],
    "uncovered_endpoints": ["SC-005: matched /driver/v1/status, 0 test methods call it"]
  },
  "fix_loop": {"attempts_used": 1, "budget": 2, "fix_budget_exhausted": false},
  "final_validation": {"passed": true, "counts": {"error": 0, "warning": 1}},
  "files_written": {"created": 2, "updated": 3},
  "blocked": false,
  "reviewer_todos": [],
  "notes": "<one-paragraph summary of what ran, what was reused vs created, and anything a reviewer should check first>"
}
```

Use `""` for a missing string, `[]` for a missing list. Never use `null`.

## What this skill does not do

- **It does not query Memgraph itself.** That is `automation-plan-test-enricher` end to end,
  including the Cypher, the endpoint normalisation, and the module fallback ladder. This skill
  hands over `(module, endpoint)` and reads `scenario_gbt_context` back — it never builds a
  query, and never edits an enricher result.
- **It does not decide test placement, class names, or reuse-vs-create.** That is
  `gbt-context-builder` end to end — see its `reference.md` for the ranking rule this skill
  relies on but never overrides.
- **It does not decide which method a scenario belongs to,** and it does not build the
  method/assertion/data-provider summary that decision rests on. That is
  `gbt-method-decision-maker` end to end — this skill only sequences it after enrichment and
  the plan merge, and never re-evaluates an `exact_match`/`assertion_add`/
  `closest_match_modify`/`data_provider_new_row`/`no_match`/`undecidable` verdict. In
  particular it never second-guesses an `assertion_add` whose `assertion_location` is
  `assertion_helper`: that placement was a blast-radius judgement, not a formatting choice.
- **It does not write test scenarios.** `sdet-plan-generator` (and the human review gate) own
  that; this skill starts from an already-approved plan.
- **It does not add a new fix-retry mechanism, and does not diagnose build failures itself.**
  `gbt-build-fix` owns compiling and root-causing end to end, within `GBT_MAX_FIX_RETRIES`;
  the profile-fix path owns rule violations, within `GBT_MAX_PROFILE_FIX_RETRIES`. This skill
  reuses both budgets as they are and only sequences when they run — it never edits Java, and
  never re-reads a Gradle log to second-guess a root cause.
- **It does not prepare or tear down the workspace.** `gbt-workspace-prep` owns the fetch,
  the branch, and the worktree; this skill runs it first, reads `workspace.gbt_repo`, and
  passes that one absolute path to every later stage. It never re-fetches mid-run — the base is
  pinned at `base_sha` on purpose.
- **It does not create the MR itself, or run tests.** `gbt-mr-raiser` owns branch, commit,
  push, and the Draft MR end to end — including the confirmation prompt and the secret scan.
  This skill only sequences it last, and never waives its human go-ahead on its behalf. CI
  runs the tests once the branch is pushed.
