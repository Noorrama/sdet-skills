---
name: code-gen-orchestrator
description: Master orchestrator for backend-test codegen: takes approved automation_plan.json from plan_dir, copies it into codegen pass artifacts, enriches via automation-plan-test-enricher (Memgraph), then sequences gbt-method-decision-maker, module profile resolver, gbt-code-understanding, gbt-context-builder, gbt-test-code-generator, and test-code-validator's fix loop. Use after automation-plan review (codegen/run.json) when you want the full plan-through-validated-code path. Dispatches stages as subagents; writes raw payloads to qa-artifacts/<epic>/codegen/pass<N>/logs/ (legacy runs/<epic>/pass<N>/).
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
scenarios are genuinely new. Only then do you resolve the **module profile**, load
`gbt-code-understanding`, and run `gbt-context-builder` for placement and packages, so
`gbt-test-code-generator` can emit code against verified anchors.

Your output is the same set of artifacts the stages would produce if run by hand, plus two
transformations you own: the merged `test_data_payloads` on the plan, and the enrichment
handoff. The endpoint-level coverage discovery (`automation-plan-test-enricher`), the
method-level reuse decision (`gbt-method-decision-maker`), and the placement/package decision
(`gbt-context-builder`) stay as separate artifacts, each owned by the skill that produced it.

## Absolute rules (violating any is a critical failure)

1. **Two gates — do not merge them.**
   - **SDET gate** (`{plan_dir}/sdet_plan.json` root `status == "approved"`): required only to
     spawn optional `gbt-automation-plan-generator` when `{plan_dir}/automation_plan.json` is
     missing. This skill does **not** run `sdet-plan-generator`.
   - **Codegen gate** (`{codegen_dir}/run.json` → `review.status == "approved"` and
     `review.pass` equals the pass being run): required before **stage 0** and before any
     stage that writes generated code. SDET approval alone does **not** satisfy this gate.
   Never call `gbt-test-code-generator` with a hand-built plan to bypass either gate.
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
   resolving the module writer, resolve it on **(module, transport)**: gRPC scenarios route to
   the `gbt-codegen:gopay-grpc-api-test-writer` / `gbt-codegen:gofood-grpc-api-test-writer` agent, everything else to the
   REST writer agent for that module. A single plan may legitimately mix both. Module writers are
   agents, not skills — their documents live at `reference/module-writers/<name>/SKILL.md`.
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
   `{run_dir}/rejects/code-gen-skill.json` naming which stage failed and copy
   that stage's own reject payload in verbatim — do not paraphrase or summarize a reject.
7. **Output exactly one JSON run summary at the end.** No prose, no markdown fences outside
   the final summary object.

8. **Every stage runs as its named subagent — never inline, never as a skill.** The stage
   documents live under `$CLAUDE_PLUGIN_ROOT/stages/` and are deliberately not skills: they are
   not user-invocable and you cannot load them as skills. Dispatch by `subagent_type` from the
   stage table. If an agent does not resolve, reject with `stage_agent_unavailable` — doing the
   stage's work yourself produces an artifact that claims a provenance it does not have.
9. **You own the human go-ahead for step 13, because the agent cannot ask.** `gbt-mr-raiser` runs
   in an isolated context with no access to this conversation. Obtain the go-ahead here — naming
   the branch, the file count, and that the MR opens as a Draft — and pass `go_ahead: "granted"`
   into its spawn prompt. Never spawn it and assume the agent will confirm; it will reject.
10. **The debug trail is mandatory, not best-effort.** Before each dispatch write the prompt echo
   and the `dispatch` record; after each return write the `return` record and verify the agent's
   log exists. The stages are subagents nobody else can see — a run whose trail is missing cannot
   be debugged without repeating it. See **Debug output**.

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

**Cursor / local workspace:** If the user already has `gojek-backend-tests` cloned, ask once (or
read from env) and set **`GBT_REPO_PATH`** to that absolute path before stage 0, and
**`GBT_WORKTREES_DIR`** to a writable directory outside the plugin (e.g. a sibling
`gojek-backend-tests-worktrees/`). Stage 0 still creates `automate/…` in a **worktree**, not on
the user's current branch in the base clone — but fetch, remotes, and push auth follow their
clone. Echo `workspace.gbt_repo` in the run summary so they open the tree that actually holds
generated `.java` files before `gbt-mr-raiser` pushes.

## Stage order

| # | Stage | Agent (`subagent_type`) | Reads | Writes | Gate before running |
|---|---|---|---|---|---|
| 0 | `gbt-workspace-prep` | `gbt-codegen:gbt-workspace-prep` | `run_json`, `{run_dir}/artifacts/automation_plan.json`, the base clone | `workspace.json` — fetched base, run branch, isolated **worktree** | **codegen gate** approved; plan copy done; base clone clean; network (or `--offline`) |
| 1 | **endpoint extraction (this skill)** | — (this skill) | `{run_dir}/artifacts/automation_plan.json` — `module`/`service_name` + `endpoint` per scenario | nothing (read-only; the pairs are passed in-memory to step 2) | **codegen gate** approved; plan present with ≥1 `is_dedup: false` scenario |
| 2 | `automation-plan-test-enricher` | `gbt-codegen:gbt-plan-enricher` | the plan + the GBT dependency graph in **Memgraph** (bolt) | `automation_plan_enriched.json` — `scenario_gbt_context` per scenario | bolt reachable; `endpoint_context.cypher` resolved |
| 3 | `test-data-generator` | `gbt-codegen:gbt-test-data-generator` | enriched plan, `{plan_dir}/rfc_context.json`, `{plan_dir}/sdet_plan.json` | `test_data.json` | step 2 succeeded, non-empty `to_generate` |
| 4 | **merge step (this skill)** | — (this skill) | `test_data.json` | enriched plan (adds `test_data_payloads`) | step 3 succeeded |
| 5 | `gbt-method-decision-maker` | `gbt-codegen:gbt-method-decision-maker` | **`scenario_gbt_context` from the enriched plan** + the real test / assertion / data-provider classes it names, from `$GBT_REPO_PATH`; each scenario's steps + `description` | `method_decisions.json` | enriched plan merged (step 4) |
| 6 | **module profile resolver (this skill)** | — (`Read` `reference/gbt-module-<normalized>/SKILL.md`) | the target module → `gbt-module-<normalized>` (`:driver-platform` → `gbt-module-driver-platform`) | nothing written — loaded into context | step 5 succeeded |
| 7 | `gbt-code-understanding` | — (`Read` `reference/gbt-code-understanding/SKILL.md`) | the enriched plan, the module profile, `$GBT_REPO_PATH` | nothing written — the five-phase analysis loaded into context | module profile resolved (or explicitly absent) |
| 8 | `gbt-context-builder` | `gbt-codegen:gbt-context-builder` | `{plan_dir}/rfc_context.json`, `{plan_dir}/tasks_context.json`, `{plan_dir}/regression_context.json`, code graph | `gbt_context.json` — `packages`, `module_root`, exemplars, layer verdicts | code graph reachable for target module |
| 9 | `gbt-test-code-generator` | `gbt-codegen:gbt-test-code-generator` | enriched plan (merged), `gbt_context.json`, `method_decisions.json`, `run_json` | `.java` files, `codegen_manifest.json` | codegen gate still approved |
| 10 | `test-code-validator` | `gbt-codegen:gbt-test-code-validator` | generated Java, `rules.json`, the enriched plan | `validation_report.json` | at least one file generated |
| 11 | validate-fix loop | `gbt-codegen:gbt-test-code-generator` + `gbt-codegen:gbt-test-code-validator` | `validation_report.json` errors | re-invokes step 9 on `implicated_files`, then re-runs step 10 | `validation_report.blocked == true` and retry budget remains |
| 12 | `gbt-build-fix` | `gbt-codegen:gbt-build-fix` | `codegen_manifest.json`, the clone | compiled module; corrected `.java` files in place | validate-fix loop settled |
| 13 | `gbt-mr-raiser` | `gbt-codegen:gbt-mr-raiser` | `codegen_manifest.json`, `validation_report.json`, `method_decisions.json`, `run_json`, the clone | branch + commit + **Draft MR** | step 12 settled (compiling, or budget exhausted with TODOs recorded); **explicit human go-ahead** |

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
  the team. It runs **last**, and never without explicit human go-ahead — which **you** obtain in this
  conversation before spawning it (rule 9), since the agent cannot prompt anyone. `fix_budget_exhausted:
  true` from either loop does **not** block it: a Draft MR carrying honest TODOs is more useful
  than generated code stranded in a working clone. Say so in the MR body.
- **The two budgets are separate and must not be pooled.**
  `GBT_MAX_PROFILE_FIX_RETRIES` bounds the step 10–11 loop; `GBT_MAX_FIX_RETRIES` bounds step
  12's compile loop. Spending one on the other is how a run burns its compile attempts on
  formatting violations and pushes code that never compiled.

`sdet-plan-generator` and the extractors before it are **not** run by this skill — it starts from
an already-approved automation plan in **`plan_dir`**. If `{plan_dir}/automation_plan.json` is
missing, spawn `gbt-automation-plan-generator` only when the **SDET gate** passes; it writes to
`plan_dir`. If the epic has no codegen copy yet, you still run the **plan → artifacts copy** below
before stage 0.

## Epic layout resolution (ALWAYS FIRST)

Read `references/common/epic-artifact-layout/SKILL.md`. Given `epic_id` (or `epic_root` from the
caller), resolve:

| Variable | Default |
|---|---|
| `epic_root` | `qa-artifacts/<epic_id>/` (absolute under CWD unless caller passes absolute `epic_root`) |
| `plan_dir` | `{epic_root}/plan/` when that folder exists or is being created; else `{epic_root}/` if `{epic_root}/sdet_plan.json` exists (legacy flat) |
| `codegen_dir` | `{epic_root}/codegen/` when present or when starting a new codegen run; else `{repo-root}/runs/<epic_id>/` (legacy) |
| `run_dir` | `{codegen_dir}/pass<N>/` |
| `run_json` | `{codegen_dir}/run.json` |

Log `epic_root`, `plan_dir`, `codegen_dir`, and `run_dir` in `logs/orchestrator.jsonl` before any gate.

### Preflight gates (in order)

1. **Codegen gate** — read `run_json`. Unless `review.status == "approved"` and `review.pass == N`,
   reject with `review_gate_not_approved` (do not spawn stage 0+). This check is **only** about
   automation-plan / codegen review, not SDET.
2. **Plan lane source** — require `{plan_dir}/automation_plan.json` **or**
   `{plan_dir}/enriched_automation_plan.json`. If both missing and caller asked to run APG, check
   **SDET gate** on `{plan_dir}/sdet_plan.json`; if not approved, reject `sdet_gate_not_approved`;
   else spawn `gbt-automation-plan-generator` with `plan_dir` (writes `{plan_dir}/automation_plan.json`).
3. **Plan → pass copy (orchestrator-owned)** — before stage 0, ensure `{run_dir}/artifacts/` exists
   and copy byte-identically:
   - from `{plan_dir}/enriched_automation_plan.json` if present, else `{plan_dir}/automation_plan.json`
   - to `{run_dir}/artifacts/automation_plan.json`
   Log the source path in `orchestrator.jsonl` (`event: inline`, `stage: plan_copy`).
4. **`@TestInfo.owner` (test author email)** — before spawning **`gbt-test-code-generator`**
   (stage 9), resolve the corporate email that owns generated tests. **Do not rely on exemplar
   classes** for this — wrong-owner `@TestInfo` is a common silent defect.

   Resolve in order (first hit wins):

   | Source | Use when |
   |---|---|
   | Spawn prompt `testinfo_owner` | Human passed email in this conversation or CI job env |
   | `run_json` → `test_author.email` | Written at codegen approval time (preferred durable record) |
   | Human in chat | Orchestrator **must ask explicitly**: *"What corporate email should `@TestInfo.owner` use for generated tests? (e.g. first.last@gojek.com)"* — then persist to `run.json` under `test_author` before stage 9 |

   If still missing after one ask, **reject** with `test_author_email_missing` — do not spawn
   codegen. Log the resolved email in `orchestrator.jsonl` (never log secrets; email is fine).

   Pass to **every** stage from workspace-prep onward when useful, and **mandatorily** on the
   stage 9 spawn prompt: `testinfo_owner: <email>` plus `run_json` path.

Stages that need RFC/tasks/regression/SDET read **`plan_dir`** via absolute paths in spawn prompts
(e.g. `{plan_dir}/rfc_context.json`).

## Dispatching a stage

Every stage with an agent in the table above runs as a **subagent**, spawned with the Agent tool
using that `subagent_type`. You never inline a stage's logic, never read its `SKILL.md` to do the
work yourself, and never invoke it as a skill — those documents now live under
`$CLAUDE_PLUGIN_ROOT/stages/` and are not skills any more. The agent reads its own spec.

**The stage agents live in `agents/gbt-codegen/`, so their `subagent_type` is namespaced by that
folder** — `gbt-codegen:gbt-workspace-prep`, and fully qualified
`aep-backend:gbt-codegen:gbt-workspace-prep`. Use the value in the stage table's Agent column; if
it does not resolve, retry once with the fully-qualified form before rejecting with
`stage_agent_unavailable`.

**One at a time, in the foreground.** The pipeline is strictly sequential — each stage reads the
previous stage's artifact off disk — so never spawn two stages in parallel and never background
one. Wait for each to return before evaluating its gate and dispatching the next.

**The spawn prompt must stand alone.** A subagent sees none of this conversation. Every prompt
carries, at minimum:

- `epic_root`, `plan_dir`, `codegen_dir` — absolute (see Epic layout resolution)
- `run_dir` — absolute `{codegen_dir}/pass<N>/`
- `run_json` — absolute `{codegen_dir}/run.json`
- `testinfo_owner` — corporate email for `@TestInfo.owner` on **new** methods (required for
  `gbt-test-code-generator`; see `test_author` in `epic-artifact-layout/SKILL.md`)
- `epic_id`, `pass`
- `gbt_repo` — the absolute `workspace.gbt_repo` from stage 0, never the base clone (omit for APG-only spawn)
- the absolute path of every artifact that stage reads, and of the artifact it must write
  (`plan_dir` for plan-lane contexts; `run_dir/artifacts/` for pass artifacts)
- the remaining retry budget, when the stage is inside a fix loop

Resolve `gbt_repo` **once**, at stage 0, and pass that same absolute string to every later stage.
Two stages resolving it differently is how generated code lands in one tree and gets committed
from another.

Steps 6 and 7 have no agent on purpose: they are context loads, not stages. `Read`
`$CLAUDE_PLUGIN_ROOT/reference/gbt-code-understanding/SKILL.md` and the resolved
`reference/gbt-module-<normalized>/SKILL.md` **into your own context** and apply them when
composing step 9's prompt. Spawning them as subagents would strand their analysis in an isolated
context and silently degrade generation.

**Module writers are agents too, and step 9 owns them.** `go-logistics-api-test-writer`,
`gopay-api-test-writer`, `gopay-grpc-api-test-writer`, `gofood-api-test-writer`,
`gofood-grpc-api-test-writer`, `driver-platform-api-test-writer`, `transport-api-test-writer`,
`payment-core-api-test-writer`, `scp-api-test-writer`, `marketplace-api-test-writer`,
`midtrans-core-api-test-writer`, `customer-platforms-api-test-writer` and
`iris-api-test-writer` are subagents, not user-invocable skills; their documents live at
`$CLAUDE_PLUGIN_ROOT/reference/module-writers/<name>/SKILL.md`. Name the resolved
(module, transport) writer in step 9's spawn prompt and let `gbt-test-code-generator` read or
spawn it — do not spawn a writer yourself as a parallel stage, and do not add it to `stages[]`.

## Debug output

**Every stage runs inside a subagent the user cannot see, invoke, or interrupt.** The debug trail
below is therefore the *only* way anyone reconstructs what happened — treat writing it as part of
running the stage, not as optional bookkeeping. A stage that completed but left no trace is a
stage nobody can debug, and re-running the pipeline to find out what it did costs a full run.

Artifacts remain the contract between stages; logs are the record of how each artifact came to be.

### The `logs/` directory

Create `logs/` at stage 0, beside `artifacts/` and `rejects/`. Every dispatched stage lands
exactly these files:

| # | Stage | Agent log (written by the agent) | Prompt echo (written by you) |
|---|---|---|---|
| 0 | gbt-workspace-prep | `logs/workspace-prep.json` | `logs/workspace-prep.prompt.txt` |
| 2 | automation-plan-test-enricher | `logs/plan-enricher.json` | `logs/plan-enricher.prompt.txt` |
| 3 | test-data-generator | `logs/test-data-generator.json` | `logs/test-data-generator.prompt.txt` |
| 5 | gbt-method-decision-maker | `logs/method-decision-maker.json` | `logs/method-decision-maker.prompt.txt` |
| 8 | gbt-context-builder | `logs/context-builder.json` | `logs/context-builder.prompt.txt` |
| 9 | gbt-test-code-generator | `logs/test-code-generator.json` | `logs/test-code-generator.prompt.txt` |
| 10 | test-code-validator | `logs/test-code-validator.json` | `logs/test-code-validator.prompt.txt` |
| 11 | fix attempt `<n>` | `logs/test-code-generator.attempt-<n>.json` | `logs/test-code-generator.attempt-<n>.prompt.txt` |
| 12 | gbt-build-fix | `logs/build-fix.json` | `logs/build-fix.prompt.txt` |
| 13 | gbt-mr-raiser | `logs/mr-raiser.json` | `logs/mr-raiser.prompt.txt` |
| opt | gbt-automation-plan-generator | `logs/automation-plan-generator.json` | `logs/automation-plan-generator.prompt.txt` |

The agent log is that agent's **complete return payload, verbatim** — never a summary, never
reformatted. The prompt echo is the **exact spawn prompt you sent**, written before you dispatch.
Together they make a stage replayable: a developer can re-spawn that one agent with that one
prompt and get the same behaviour without re-running the pipeline.

Steps 1, 4, 6 and 7 have no agent, so they have no agent log — but they still get a timeline
entry (below), because "which module profile did it resolve?" and "how many pairs did endpoint
extraction find?" are exactly the questions a failed run raises.

### The run timeline — `logs/orchestrator.jsonl`

You write this yourself, one JSON object per line, appended as the run proceeds. It is the
single file to open first when a run goes wrong, because it interleaves *your* decisions with the
agents' results in the order they actually happened.

Append a `dispatch` record immediately before spawning, and a `return` record immediately after:

```json
{"ts":"<ISO-8601>","event":"dispatch","step":2,"stage":"automation-plan-test-enricher","agent":"gbt-codegen:gbt-plan-enricher","prompt_log":"logs/plan-enricher.prompt.txt","inputs":{"plan":"artifacts/automation_plan.json","gbt_repo":"<abs path>"},"gate":"passed: bolt reachable, 6 scenarios with endpoints"}
{"ts":"<ISO-8601>","event":"return","step":2,"stage":"automation-plan-test-enricher","status":"completed","duration_s":74,"artifact":"artifacts/automation_plan_enriched.json","log":"logs/plan-enricher.json","detail":"5 enriched, 1 errored, 6 total"}
```

For the four stages you run yourself, write a single `inline` record carrying the decision:

```json
{"ts":"<ISO-8601>","event":"inline","step":1,"stage":"endpoint_extraction","detail":"6 scenarios, 5 distinct (module, endpoint) pairs","data":{"pairs":[["gofood","POST /gofood/v1/sessions"]],"skipped":["SC-006: no_endpoint"]}}
{"ts":"<ISO-8601>","event":"inline","step":6,"stage":"module_profile_resolver","detail":"resolved :driver-platform → gbt-module-driver-platform","data":{"read":"reference/gbt-module-driver-platform/SKILL.md","found":true}}
```

Record a **skip** the same way, with `event: "skip"` and the reason — a stage that silently did
not run is the single most confusing thing to debug later.

### What to echo to the user, live

The user sees no subagent output at all, so narrate the run at exactly one line per event — never
the agent's full report, never nothing:

```
▸ stage 2 · automation-plan-test-enricher · dispatching gbt-codegen:gbt-plan-enricher
✔ stage 2 · completed · 74s · artifacts/automation_plan_enriched.json · 5 enriched, 1 errored
```

Use `▸` on dispatch, `✔` on completion, `⚠` on a non-fatal partial (e.g. `enrichment_partial`),
`⛔` on a reject. On a reject, follow the one-liner with the agent's verbatim `reject` and
`detail` fields and the path of its log — the user cannot open the subagent's transcript, so if
you paraphrase the reject here it is lost for good.

### After every stage returns, in this order

1. Confirm the agent's log file exists. If it is missing, write it yourself from the returned
   payload and set `"log_written_by":"orchestrator"` on that stage's summary entry — a missing
   log is a defect in that agent worth reporting, not a reason to lose the payload.
2. Confirm the artifact the stage promised exists and parses. A `completed` status with no
   artifact on disk is a **`stage_order_violated`** reject, not a pass — catch it here rather
   than three stages later.
3. Append the `return` record to `logs/orchestrator.jsonl` and the stage entry to `stages[]`.
4. Echo the one-liner.

### On reject

`rejects/code-gen-skill.json` copies the agent's payload in **verbatim** (rule 6). The log file
is the source for that copy — never paraphrase it, and never summarise a reject into your own
words. Leave every log written so far in place: the run stops, the trail does not.

### Pointing a human at the trail

Close every run — successful or not — by telling the user where the evidence is:

```
Debug trail: {codegen_dir}/pass<N>/logs/
  orchestrator.jsonl        — the full timeline, one line per event
  <stage>.json              — each agent's verbatim return payload
  <stage>.prompt.txt        — the exact prompt it was spawned with (re-spawn to reproduce)
```

## The validate-fix loop, precisely

1. Run `test-code-validator`. If `passed: true`, stop — done.
2. If `blocked: true` and the profile-fix budget is not exhausted, spawn a **fresh**
   `gbt-test-code-generator` with `mode: "fix"`. It keeps no memory of the generation pass, so
   the prompt must restate `validation_report.implicated_files` (already capped and ordered by
   the validator), the specific violations, the attempt number, and `retries_remaining`.
   Decrement the budget and re-run only those files. Do not re-run `gbt-method-decision-maker` for a fix pass — its
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

- `{run_dir}/artifacts/automation_plan.json` exists (from **plan → pass copy** or prior pass), is
  schema-valid, and `run_json` shows **codegen gate** approved for this pass — or the caller
  explicitly asks this skill to run `gbt-automation-plan-generator` first (SDET gate required).
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
| `review_gate_not_approved` | Attempted to run stage 0+ before `{codegen_dir}/run.json` `review.status == "approved"` for this pass |
| `sdet_gate_not_approved` | Attempted to spawn `gbt-automation-plan-generator` while `{plan_dir}/sdet_plan.json` is not approved |
| `plan_copy_missing_source` | Neither `{plan_dir}/enriched_automation_plan.json` nor `{plan_dir}/automation_plan.json` exists to copy into pass artifacts |
| `fix_loop_would_be_unbounded` | The validate-fix loop was about to run without a tracked remaining budget |
| `enrichment_unusable` | Every non-`is_dedup` scenario came back from step 2 with an `error` in `scenario_gbt_context`. The graph is down or the module never resolves — running `gbt-method-decision-maker` on this would turn "could not check" into a plan-wide `no_match` and duplicate every existing test. Copy the enricher's own stderr summary in verbatim |
| `stage_agent_unavailable` | The `subagent_type` named in the stage table did not resolve — the plugin is not installed, or a rename drifted. Refuse. Falling back to doing the stage's work yourself is exactly what rule 3 forbids, and it produces an artifact nobody can attribute |
| `mr_go_ahead_missing` | Step 13 was about to be spawned without an explicit human go-ahead obtained in this conversation. `gbt-mr-raiser` cannot prompt the user itself |
| `enrichment_partial_unacknowledged` | Some scenarios errored and some enriched. **Not a reject on its own** — continue, but record every errored `scenario_id` with its verbatim `error` in the run summary's `enrichment` block. Rejecting here is wrong: the enriched scenarios are still actionable. Silently proceeding is also wrong |

On reject, write `{run_dir}/rejects/code-gen-skill.json`:

```json
{"stage": "code-gen-skill", "failed_at": "<stage-name>",
 "upstream_reject": {"...": "verbatim contents of that stage's own reject file"},
 "remediation": "<the exact command or stage to re-run>"}
```

## OUTPUT — return ONLY a single valid JSON object

Written to `{run_dir}/artifacts/code_gen_run.json`, as the
one summary of the whole orchestrated run — every artifact it references was written by the
stage skill responsible for it, not by this skill.

```json
{
  "epic_id": "EPIC-1122",
  "pass": 1,
  "started_at": "<ISO-8601>",
  "finished_at": "<ISO-8601>",
  "stages": [
    {"stage": "gbt-workspace-prep", "status": "completed", "artifact": "runs/EPIC-1122/pass1/artifacts/workspace.json", "detail": "worktree on automate/... off master@72810718; base fresh", "log": "runs/EPIC-1122/pass1/logs/workspace-prep.json"},
    {"stage": "endpoint_extraction", "status": "completed", "detail": "6 scenarios, 5 distinct (module, endpoint) pairs extracted; 1 scenario has no endpoint (DB-only)", "log": ""},
    {"stage": "gbt-plan-enricher", "status": "completed", "artifact": "runs/EPIC-1122/pass1/artifacts/automation_plan_enriched.json", "detail": "5 enriched, 1 errored, 6 total", "log": "runs/EPIC-1122/pass1/logs/plan-enricher.json", "duration_s": 74},
    {"stage": "gbt-test-data-generator", "status": "completed", "artifact": "runs/EPIC-1122/pass1/artifacts/test_data.json", "log": "runs/EPIC-1122/pass1/logs/test-data-generator.json"},
    {"stage": "merge_test_data_into_plan", "status": "completed", "detail": "test_data_payloads set from test_data.json, 5 entries", "log": ""},
    {"stage": "gbt-method-decision-maker", "status": "completed", "artifact": "runs/EPIC-1122/pass1/artifacts/method_decisions.json", "detail": "1 exact_match, 1 closest_match_modify, 1 data_provider_new_row, 2 no_match", "log": "runs/EPIC-1122/pass1/logs/method-decision-maker.json"},
    {"stage": "module_profile_resolver", "status": "completed", "profile": "reference/gbt-module-driver-platform/SKILL.md", "log": ""},
    {"stage": "gbt-code-understanding", "status": "loaded", "detail": "five-phase analysis applied; no artifact written", "log": ""},
    {"stage": "gbt-context-builder", "status": "completed", "artifact": "runs/EPIC-1122/pass1/gbt_context.json", "log": "runs/EPIC-1122/pass1/logs/context-builder.json"},
    {"stage": "gbt-test-code-generator", "status": "completed", "artifact": "runs/EPIC-1122/pass1/artifacts/codegen_manifest.json", "log": "runs/EPIC-1122/pass1/logs/test-code-generator.json", "writer_agent": "gbt-codegen:gofood-api-test-writer"},
    {"stage": "gbt-test-code-validator", "status": "completed_after_fix", "attempts": 2, "artifact": "runs/EPIC-1122/pass1/artifacts/validation_report.json", "log": "runs/EPIC-1122/pass1/logs/test-code-validator.json", "attempt_logs": ["runs/EPIC-1122/pass1/logs/test-code-generator.attempt-1.json"]},
    {"stage": "gbt-build-fix", "status": "completed", "detail": "compileTestJava failed on 1 fabricated method signature; fixed in 1 attempt, module now compiles", "log": "runs/EPIC-1122/pass1/logs/build-fix.json"},
    {"stage": "gbt-mr-raiser", "status": "completed", "detail": "Draft MR !4821 opened from automate/... with 3 TODOs carried", "mr_url": "<web_url>", "log": "runs/EPIC-1122/pass1/logs/mr-raiser.json"}
  ],
  "debug": {
    "logs_dir": "runs/EPIC-1122/pass1/logs/",
    "timeline": "runs/EPIC-1122/pass1/logs/orchestrator.jsonl",
    "missing_logs": [],
    "note": "every stage log holds that agent's verbatim return payload; the matching .prompt.txt re-spawns it"
  },
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
  This skill only sequences it last, and never waives its human go-ahead — it merely *collects*
  that go-ahead on the agent's behalf, because a subagent has no way to ask. CI
  runs the tests once the branch is pushed.
