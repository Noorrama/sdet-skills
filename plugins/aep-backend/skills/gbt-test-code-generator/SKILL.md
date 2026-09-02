---
name: gbt-test-code-generator
description: Generate runnable GBT Java/TestNG test code from automation_plan.json (which carries the merged test_data_payloads), gbt_context.json, and method_decisions.json (which method to skip, modify, or add), writing files into the GBT repo with deterministic path and package anchoring plus a codegen manifest. Use after the human review gate in the agentic backend-test pipeline, or standalone to test code generation in isolation. Runs in Claude Code or Cursor with no Python pipeline. Reuses existing classes and methods rather than duplicating them.
version: 1
disable-model-invocation: true
---

# GBT Test-Code Generator

You are a Senior SDET turning an **approved** automation plan into runnable GBT Java. Unlike
`gbt-code-generation` — which is driven by a Python-assembled prompt — this skill reads its
inputs from disk, writes its outputs to disk, and runs unaided in Claude Code or Cursor.

It is the skills-only path to code generation, and it is individually testable. See
[reference.md](reference.md) for the standalone test procedure.

## Methodology comes from three other skills — load them first

**Do not restate GBT patterns in your head from this file.** This skill owns *orchestration*;
the patterns live elsewhere and are authoritative. Before generating anything, read:

1. **The `gbt-module-<normalized>` skill and its `reference.md`** for the target
   module — `:driver-platform` → `gbt-module-driver-platform`, `:services:foo` →
   `gbt-module-services-foo`. **Highest authority.** Its layer map, its 4-step endpoint
   existence & reuse protocol, and its coding-style rules override anything you would
   otherwise infer. Its `reference.md` carries verified real-code patterns — mirror them.
2. **The `gbt-code-understanding` skill** — the five-phase analysis method. Work
   through it before writing a line.
3. **The `gbt-code-generation` skill** — the emission rules, negative/edge
   catalogue, and quality checks.

All three ship alongside this skill in the `aep-backend` plugin. Load them by name where
skills are discovered; where they are not, read `SKILL.md` from the sibling directory of
this file.

If the module has no profile, say so in the manifest and proceed with 2 and 3 alone — but
flag it, because output quality drops sharply without one.

## Absolute rules (violating any is a critical failure)

1. **The review gate is a hard precondition.** Read `runs/<epic>/run.json`. Unless
   `review.status == "approved"` **for this pass**, reject. A gate enforced only by the UI is
   not enforced — this skill is directly invocable, so it must refuse on its own.
1a. **Check approval PER SCENARIO, and fail closed.** The run-level gate in rule 1 says the
    *pass* was reviewed; it does **not** say every scenario in the plan was approved. Before
    generating anything for a scenario, resolve its individual status and skip it unless it is
    explicitly approved. Resolve in this order, first hit wins:

    | Source | Approved when | Otherwise |
    |---|---|---|
    | `run.json` → `review.per_scenario[<scenario_id>]` | `"keep"` | skip — `"drop"`, `"changes_requested"`, or any other value |
    | the scenario's own `status` / `approval_status` field, when the plan carries one | `"approved"` | skip |
    | the plan's top-level `status` | `"approved"` — applies to every scenario that has no entry above | **reject the whole run** if present and not `"approved"` |
    | none of the above present | — | **skip the scenario.** Absence is not approval. |

    **Fail closed on an absent entry.** A `scenario_id` missing from `per_scenario` is *not*
    an implicit keep — it means the reviewer never saw it. Generating for it silently converts
    "unreviewed" into "approved", which is the one thing the gate exists to prevent. Skip it
    and say so.

    **Match the pass.** `review.pass` must equal the pass you are generating for. Pass 1
    approval does not authorise pass 2, and a `run.json` from an earlier pass left in place is
    a common way to run unapproved work.

    **Record every skip in `codegen_manifest.skipped[]`** with `reason` set to
    `not_approved` / `reviewer_dropped` / `no_approval_record`, and the scenario_id. A scenario
    silently absent from the output is indistinguishable from one that failed to generate.

    Note this is deliberately re-checked here even though `automation-plan-generator` rule 2
    already filters on `per_scenario`. That skill may not have run — this one is directly
    invocable with a hand-built plan — and a filter you inherit is not a gate you enforced.

    *Worked example (GOFOOD-SG-M5):* two plans were supplied for the same epic.
    `automation_plan_piyush.json` carried a top-level `"status": "approved"`;
    `enriched_automation_plan.json` carried **no status field at all**, and its first three
    scenarios were byte-identical to three already generated and pushed in an earlier pass.
    Without this rule the second plan would have run unapproved and duplicated three test
    methods onto a new branch. Both were caught by hand, which is exactly what a rule is for.

2. **`existing_paths` decides placement; `method_decisions.json` decides which method.** A
   `reuse` verdict carries a real path: **open that file**. Within it, follow the scenario's
   verdict in `method_decisions.json`:
   - `exact_match` → write nothing for that scenario (record it as already-covered).
   - `data_provider_new_row` → touch **only** the named `data_provider_class` /
     `data_provider_method`'s file, appending exactly `new_row` in the method's existing
     parameter order. Do not touch the `@Test` method or any other row.
   - `assertion_add` → **insert exactly the one assertion** in `assertion_add.addition`, and
     change nothing else. `assertion_location` decides the file: `"test_method"` appends it to
     the named `@Test` method's body (after the existing assertions, before any
     `assertAll()`); `"assertion_helper"` appends it inside the named
     `assertion_class`/`assertion_method`. Do **not** relocate the assertion between those two
     places — the decision-maker weighed the blast radius (`shared_with`) to pick one, and
     moving it either silently tightens other callers or drops the shared-contract check. If
     the helper uses `SoftAssert`, add a soft assertion in the same style, before `assertAll()`.
   - `closest_match_modify` → edit the named method's named assertion only, and touch nothing
     else in it.
   - `no_match` → add a new method, naming it per the module profile.
   **A `reuse` test-layer path is only valid for the endpoint that class already covers.** If the
   scenario's endpoint differs in method or path from the one the reused class tests, do not add a
   method to it — create a new test class in that class's directory, named for your endpoint, and
   note the override in `anchoring_notes`. One endpoint, one test class is the repo convention;
   a stale `reuse` verdict does not license breaking it. Use the class you were pointed at as the
   structural template, and call its controller for setup if you need the resource it creates.
   - `no_match` → **write a new method.** This is the straightforward case: nothing existing
     covers the scenario, so generate the method (and any missing Endpoint/Client/Controller/
     Response layer per the module profile's reuse protocol), naming it per the module
     profile. Do not hesitate or downgrade it to a TODO — `no_match` is a decided verdict.
     **If the decision carries `requires_new_test_class: true`, there is no existing test
     class — create it too**, named and placed per the module profile, extending the module's
     `<Svc>TestBase`, with the new `@Test` method as its first member. Same for a `create_new`
     layer verdict. Never append a method to a class you did not open, and never invent a
     "closest existing" class to host it: an endpoint with zero test coverage gets its own
     class, which is the normal outcome for a genuinely new endpoint, not an edge case.
   - `undecidable` → **write nothing for that scenario.** The decision-maker could not check
     coverage at all (the graph was unreachable, the endpoint never resolved). Record it under
     `skipped` with reason `undecidable`, copy its `signals` into `todos[]`, and move on.
     Treating this as `no_match` is what duplicates a test that already exists.
   Emit `"action": "update"` with the complete new file content in the
   `assertion_add`/`data_provider_new_row`/`closest_match_modify`/`no_match` cases. Never create a sibling
   class, and never add a data-provider row to a method other than the one named. A
   `create_new` verdict carries a *directory*; name the class per the module profile (every
   scenario routed to a `create_new` class is `no_match` by construction — there is no
   existing method to match against).
3. **Never fabricate an identifier.** Before calling any method on an existing Controller,
   Client, or Endpoint, **open the file named in `existing_paths` and read it.** Use a method
   that is actually declared. If the method you need does not exist, add it to that file as a
   new method — do not invent a call to something that isn't there. The module profile states
   this too ("never fabricate a plausible-sounding Controller/Client method name"); it is the
   most common and most expensive failure in generated GBT code.
4. **Anchor paths deterministically** (see the algorithm below). Never invent a package;
   `gbt_context.packages` is the source. The `package` declaration must always match the
   directory.
5. **The plan is the only source of truth for WHAT to test.** Never invent a scenario,
   endpoint, field, or assertion that is not in `automation_plan.json`.
6. **Every `@Test` carries its `SC-###` and `AC-###` in the `description`** so the MR diff is
   traceable to the requirement without opening the plan.
7. **Skip `is_dedup: true` scenarios.** Record them in the manifest as skipped with the
   reason. Never delete them from the plan — they stay in the manual matrix.
8. **Resolve every `{{fixture-id.field}}` through `automation_plan.test_data_payloads`.** The
   orchestrator merges `test-data-generator`'s output into the plan before this skill runs, so
   there is exactly one artifact to read. An unresolvable reference is a **reject**, not a
   `TODO` — it produces code that cannot run.
9. **Honour `implementation_constraints` verbatim.** *"Must reuse existing
   `CardValidationService` — do not introduce a new validator class"* means exactly that.
10. **Never hardcode a URL, host, token, credential, or real personal detail.** Hosts and
    paths resolve through the module's properties/config readers; secrets through its secret
    reader; test values come from `automation_plan.test_data_payloads`. This holds even in a
    comment or an example.
    - **An environment-dependent test-data id goes in the module's per-environment holder, never
      in a shared constants class.** Before adding one, look for an `I<Domain>Constants` +
      `<Domain>Constants{QA/PREPROD,Integration/int}` family (or the module's equivalent) in the feature area and
      add a getter plus an implementation in **every** environment class. Environment-independent
      values — enum literals, locales, and *deliberately invalid* ids — stay in the shared class.
      Keep the public constant name clean; if the value isn't provisioned yet, the placeholder and
      the `// TODO:` go in the per-environment implementation, not in the constant's name. See
      `backend-automation/references/environment-specific-test-data.md`.
    - **Extending an existing API means walking the whole request chain.** When a scenario adds a
      field to an already-automated endpoint, check each of request model, body builder, endpoint,
      client, controller (its pinned expected status especially), response model, shared assertion
      helper, and data provider — and record in `notes` what you did to each, including what you
      left unchanged and why. Adding the field to the DTO alone is the standard half-finished
      result. See `backend-automation/references/extending-an-existing-api.md` for the chain, the
      Lombok `@Builder` trap that a third field triggers, and the shared-assert rule.
11. **Unknowns become `// TODO(agent-pm): <what is missing and why>`** *and* an entry in
    `todos[]`. Guessing silently is the failure; a TODO is correct behaviour.
12. *(Renumbered — the original rule 12, "Write the files and the manifest", is now rule 19.
    Numbers 13-19 are referenced from `test-data-generator` and from merge-request text, so
    they are kept stable rather than closed up. No rule is missing.)*

13. **Mine the sibling methods before you write a single TODO.** The class named in
    `existing_paths.test` is the primary source for everything you would otherwise guess at:
    annotation values, constants, base class, groups, request-builder calls, error-assertion
    shape. **A `TODO(agent-pm)` is only legitimate for something the class, its assertion
    helpers, its data providers and its constants genuinely do not answer.** Before emitting
    any TODO, state to yourself which of those you checked. A TODO for a value sitting in the
    same file is worse than no comment — it sends a human to find something you were already
    looking at, and it leaves a test weaker than the ones beside it.

14. **Annotation completeness is per-field, never per-annotation.** When the sibling methods
    all carry the same annotation, copy the fields they agree on and TODO **only** the fields
    that are genuinely unknown. Dropping a whole annotation because one field is unavailable
    discards the fields that were free.
    *Worked example (GOFOOD-SG-M5):* all five methods in `CreateGroupOrderTests` carried
    `@TestInfo(projectId = TestRailConfig.GO_FOOD_PROJECT_ID, suiteId = TestRailConfig.GROUP_ORDER,
    testCaseIds = {...}, owner = ...)`. Only `testCaseIds` was unknowable. The correct output is a
    populated `@TestInfo` with a placeholder `testCaseIds` and a TODO naming that one field;
    omitting the annotation entirely — as was done — lost `projectId`, `suiteId` and `owner`
    for no reason and tripped the validator's `test-has-testinfo` rule.
    When inheriting an `owner`, say in the comment that it was inherited from the class so a
    reviewer can reassign it rather than silently owning someone else's work.

15. **Conventions come from THIS module, never from another one you have seen.** `enabled`,
    naming, assertion style, base class and annotation set are per-module. Read them off the
    target class. Never carry a convention across from a module you worked in earlier — and
    never claim a convention you have not checked in the file you are editing.
    *Worked example:* the new tests were shipped `enabled = false` and justified as "matching
    the house convention". None of the five sibling methods in that class is disabled — that
    was `:driver-platform`'s convention, from an unrelated task. Disabling was still defensible
    on its own merit; the stated reason was false, and a false justification in a code comment
    misleads every later reader.

16. **A test is disabled for exactly one stated blocker, and only a real one.** If you emit
    `enabled = false`, name the single blocking reason in the comment and confirm it still
    holds. Re-check each blocker against rule 13 first: a fixture marked `TDP_NOT_SUPPORTED`
    may already be satisfied by an existing constant, in which case it is not a blocker at all.
    *Worked example:* `FIX-GOFOODSG-001` ("group-order-enabled restaurant, max_participants 8")
    was reported `TDP_NOT_SUPPORTED`, and a TODO was written to replace `GO_RESTO_1` with a
    provisioned restaurant. But `assertCreateGroupOrder` asserts `max_participants == "8"` and
    `createSuccessGroupOrder` calls it with `GO_RESTO_1` — so `GO_RESTO_1` already **was** that
    fixture. The TDP verdict was irrelevant; nothing needed provisioning. Blocking a test on a
    fixture that already exists costs coverage for nothing.

17. **"No capability exists" requires a repo-wide search, and a distinction.** Before recording
    an expectation as unassertable, search the whole module and its Gradle dependencies — not
    one package — for the mechanism, and search by *behaviour* (`querySingleValue`, `fetch.*FromDb`,
    `stubFor`, `WireMock`) rather than by the directory you expect it in. Then separate two very
    different findings: **mechanism absent** (nothing in the repo can do this) versus
    **mechanism present, this route/config missing** (the pattern exists and needs one addition).
    The second is a small, assignable task; reporting it as the first tells a team to build
    something they already have.
    *Worked example:* SC-001's DB expectation was recorded as "no DB-assertion capability in the
    gofood module", on the evidence that `gofood/src/test/java/db` held one unrelated file. In
    fact `GenericUtils.fetchMealPlanBulkOrderDetailsFromDb` + `MealSchedulerDBResponse` +
    `mealSchedulerOrderController` are an established meal-scheduler inspection pattern over a
    `bakso` debug service. Nine `bakso` routes exist and none covers group-order sessions — so
    the honest finding was "add a bakso group-order-session route", not "this module cannot
    assert DB state".

18. **Read `test_data_output` for EVERY fixture of EVERY scenario, and when TDP supports it,
    GENERATE THE ACQUISITION CODE — never settle for the class default.** This block is not a
    go/no-go flag. It names *how to obtain* the fixture, and every field in it is actionable:

    | Field | What you must do with it |
    |---|---|
    | `test_data_status` | Route per the table below. Never read only this field and stop. |
    | `tdp_test_data_category` | Map to the module's pool API and emit that call — e.g. `CUSTOMER_WITH_GO_PAY` → `foodTestDataController.setAEPPoolCustomer(CustomerType.CUSTOMER_WITH_GO_PAY)`, or the equivalent flag on the module's test-data annotation (`@FoodTestDataManager(needsGopayCustomer = true)`). |
    | `test_data_operations[]` | Every entry with `operationSupported: true` is a provisioning step, in order, with its `operationInput`. Emit them, or the module's equivalent API calls. |
    | `test_data_type_signals` | The state the fixture must be in. Use it to choose between several plausible pool categories or annotation flags. |
    | `test_buddy_prompt` | The human-readable acquisition instruction. Carry it into a comment so a reviewer can provision by hand. |
    | `match_confidence` | `low` means the category was a guess — say so in a comment rather than presenting it as settled. |
    | `identification_notes` | Why a category was chosen or rejected. Quote it when it explains a placeholder. |

    Routing by status:

    | `test_data_status` | Action |
    |---|---|
    | `TDP_SUPPORTED` | **Emit the acquisition code.** Wire `tdp_test_data_category` to the module's pool API or annotation flag. Do **not** fall back to the class's default customer/merchant. |
    | `TDP_OPERATION_FALLBACK` | No single category exists but `test_data_operations[]` are supported. Emit them in order as setup. If you deliberately use the module's own API instead, say in a comment that supported operations existed and why you did not use them. |
    | `ALREADY_SATISFIED` | An existing constant or helper covers it (rule 16). Use the one named in `already_satisfied_by`; provision nothing. |
    | `TDP_NOT_SUPPORTED` | Placeholder plus a TODO naming the missing operation, per rule 16. |

    **Judged per fixture, never per scenario.** When a scenario has two fixtures and only one is
    `TDP_SUPPORTED`, the supported one is still wired properly; only the unsupported one becomes
    a placeholder, and the TODO names *which* fixture blocks the test. Disabling a test is not a
    licence to leave its other fixtures on the class default.

    *Worked example (GOFOOD-SG-M5):* `FIX-GOFOODSG-003` and `-006` were `TDP_SUPPORTED` with
    `tdp_test_data_category: CUSTOMER_WITH_GO_PAY`, `test_buddy_prompt: "Create
    CUSTOMER_WITH_GO_PAY"`, and signals `['GoPay', 'Linked Wallet', ...]`. The generator read
    only `test_data_status`, emitted `customer_aep.get()` under the class's default
    `@FoodTestDataManager(skipBaksoCustomer = true)` — which carries **no GoPay guarantee** —
    and shipped SC-005 and SC-011 **enabled** against a possibly wrong customer. The hook was
    there all along: `foodTestDataController.setAEPPoolCustomer(CustomerType.CUSTOMER_WITH_GO_PAY)`
    appears four times in `tests/cashier/settlement/MafCashierSettlementTest`, and
    `@FoodTestDataManager` exposes `needsGopayCustomer()`. One of seven fields was used. An
    enabled test on the wrong fixture is worse than a disabled one: it reports green while
    exercising something the scenario never asked for.

19. **Write the files and the manifest.** This skill's deliverable is files on disk, not a
    JSON blob in the chat.

## Inputs

| Path | Required | Used for |
|---|---|---|
| `runs/<epic>/pass1/artifacts/automation_plan.json` | yes | scenarios, routing, `existing_paths`, constraints, and `test_data_payloads` for `{{…}}` resolution |
| `runs/<epic>/pass1/gbt_context.json` | yes | packages, module root, exemplars, layer verdicts |
| `runs/<epic>/pass1/artifacts/method_decisions.json` | yes | per-scenario method verdict: `exact_match` (skip) / `assertion_add` (insert one new assertion, in the test method or the named assertion helper) / `data_provider_new_row` (append one row to the named data provider) / `closest_match_modify` (edit named method+assertion) / `no_match` (write a new method — **plus a new test class when `requires_new_test_class: true`**) / `undecidable` (write nothing, TODO — coverage was never checked) |
| `runs/<epic>/run.json` | yes | the review gate |
| the run's worktree | yes | read existing files, write new ones. `workspace.gbt_repo` from `runs/<epic>/pass1/artifacts/workspace.json` (the per-run worktree created by `gbt-workspace-prep`). Standalone, fall back to the base-clone resolution order in `code-gen-orchestrator`. Never generate into the base clone. |

`automation_plan.json` is expected to already carry `test_data_payloads` — the orchestrator
(`code-gen-skill`) merges `test-data-generator`'s output into the plan before invoking this
skill, so `test_data.json` is never read here directly. If `test_data_payloads` is absent,
treat it exactly like a missing required input (`missing_input`) — do not fall back to
reading a standalone `test_data.json`, since that file's presence does not guarantee it is the
version that was merged.

Pass 2 reads the same files under `pass2/`.

## Definition of Ready (DoR)

- All three JSON inputs present and parseable, and `automation_plan.json` contains a
  non-empty `test_data_payloads`.
- Every non-`is_dedup` scenario in `automation_plan.json` has a corresponding entry in
  `method_decisions.decisions`.
- `run.json` shows `review.status == "approved"` **and `review.pass` equal to the pass being
  generated** — an earlier pass's `run.json` left in place is not approval for this one.
- **At least one scenario resolves to approved under rule 1a.** A plan whose scenarios are all
  unapproved, dropped, or carry no approval record is not ready, however valid the plan is.
- The resolved GBT clone exists and `{module_root}` resolves to a real directory inside it.
- At least one scenario with `is_dedup: false`.
- Every `reuse` path in `existing_paths` exists on disk.

## Reject if

| Reason | Detail |
|---|---|
| `review_not_approved` | Run-level gate is `pending` or `changes_requested`, **or `review.pass` does not match the pass being generated** |
| `plan_not_approved` | The plan carries a top-level `status` that is present and not `"approved"`. Reject the whole run rather than filtering scenario by scenario |
| `no_scenario_approved` | Every scenario resolved to skipped under rule 1a — dropped, not approved, or with no approval record at all. Say which of the three, per scenario; "nothing to generate" without that breakdown sends a reader hunting for a bug that is really a missing review |
| `missing_input` | Any of the three inputs absent or unparseable, or `automation_plan.test_data_payloads` absent |
| `missing_method_decision` | A non-`is_dedup` scenario has no entry in `method_decisions.decisions` — never default it to `no_match` silently |
| `gbt_repo_missing` | No candidate in the resolution order is a git work tree, or `{module_root}` is not in the one found. Never create or clone it to recover — set `GBT_REPO_PATH` instead |
| `stale_gbt_context` | A `reuse` path does not exist on disk — the graph is stale; regenerate `gbt_context` rather than generating against a fiction |
| `stale_method_decision` | A `closest_match_modify`/`exact_match`/`data_provider_new_row` verdict names a method or data provider that is no longer present in the target file — regenerate `method_decisions` rather than editing against a fiction |
| `unresolvable_fixture` | A `{{fixture-id.field}}` has no entry in `automation_plan.test_data_payloads` |
| `nothing_to_generate` | Every scenario is `is_dedup`, `exact_match`, or `undecidable`. **Approval skips are `no_scenario_approved`, not this** — conflating "the reviewer said no" with "there was nothing to do" hides the gate. A legitimate outcome, not a bug — say so, and if the reason is `undecidable` name the remediation (re-run `automation-plan-test-enricher`, then `gbt-method-decision-maker`) rather than reporting it as "already covered" |

Write `runs/<epic>/pass1/rejects/gbt-test-code-generator.json`:

```json
{"stage": "gbt-test-code-generator", "reason": "<code>", "detail": "<what and where>",
 "remediation": "<the exact command or stage to run>"}
```

and **write no Java**. Always include `remediation`.

## Path and package anchoring

Apply to every file before writing. This reproduces what `agent/automation_agent._anchor_files`
does in the Python pipeline, so output is identical whichever path produced it.

1. **Classify by role** from the class kind:
   `endpoint` | `client` | `controller` → `src/main`; everything else
   (`test`, `test_base`, `response`, `assertion`, `data_provider`, `helper`) → `src/test`.

   **The module profile's layer map outranks this default, and frequently contradicts it.**
   On `:driver-platform`, for instance, `response` and `request` are `src/main` types under
   `entities/<svc>/`, while `client`, `controller`, `assertion`, and `data_provider` live in
   **flat** single-class-per-service directories (`client/BffServiceClient.java`,
   `assertions/BffServiceAssertions.java`). Read the profile; do not assume a pluralised
   `endpoints/`-style layout.
2. **Package** = `gbt_context.packages.test` for `src/test` files,
   `gbt_context.packages.main` for `src/main`. If `main` is empty, fall back to `test` — a
   consistent wrong package is far easier for a human to fix than a file at the module root.
3. **Path** = `{module_root}/src/{srcset}/java/{package with . → /}/{ClassName}.java`
4. **Rewrite the `package` declaration** to match the directory, always. Replace an existing
   declaration; prepend one if absent.
5. **`reuse` overrides all of the above.** Write to the exact path from `existing_paths`; do
   not relocate an existing file.
6. If `gbt_context.packages.test_confidence == "unverified"`, still write the file, and add a
   `needs_human_placement` entry to the manifest naming the file and why.

Record every relocation and package rewrite in the manifest's `anchoring_notes`.

## Procedure

1. Read the three inputs. Run the DoR and reject checks. Stop on any failure.
2. Load the three methodology skills (above).
3. For each scenario with `is_dedup: false`, in `automation_plan.automation_scenarios` order:
   a. Read every file named in `existing_paths` with a `reuse` verdict. **Actually open
      them** — this is rule 3, and it is what prevents fabricated method names.
   b. Read the scenario's entry in `method_decisions.decisions`.
      - `exact_match` → write nothing for this scenario; record it under `skipped` with
        reason `exact_match` and the covering method name.
      - `data_provider_new_row` → open `data_provider_class`, append `new_row` to
        `data_provider_method` in the method's existing parameter order, and leave the
        `@Test` method and every other row untouched.
      - `closest_match_modify` → open `target_method` in `target_class`, change only the
        named `assertion_change`, and leave the rest of the method untouched.
      - `no_match` → follow the module profile's endpoint existence & reuse protocol to
        generate only the layers that are genuinely missing, then write a new method into the
        reused test class — **or, when `requires_new_test_class: true` (or the layer verdict
        is `create_new`), create the test class first** (module profile naming, extending the
        module's `<Svc>TestBase`, anchored via `gbt_context.packages.test` + `module_root`)
        and write the method into it as `"action": "create"`.
      - `assertion_add` → open the file named by `assertion_location` (the test class, or the
        `assertion_class`), insert the single `addition` assertion in the module profile's
        assertion style, and emit `"action": "update"`. When
        `assertion_location: "assertion_helper"`, list every entry of `shared_with` in the
        manifest `reason` — the diff touches those tests too, and a reviewer must see that.
      - `undecidable` → write nothing. Add a `skipped` entry with reason `undecidable` and a
        `todos[]` line carrying the decision's `signals` verbatim, so the reviewer sees which
        scenario was never checked and why.
   c. Resolve `{{fixture-id.field}}` through `automation_plan.test_data_payloads`.
4. Anchor every file per the algorithm above.
5. Write the files into `workspace.gbt_repo` — the run's worktree, never the base clone.
6. Write `codegen_manifest.json`.
7. Print a one-screen summary: files written, actions, scenarios skipped, TODO count.

## OUTPUT — write `runs/<epic>/pass1/artifacts/codegen_manifest.json`

Exactly one JSON object. The Java goes to disk; this manifest is the record of what happened.

```json
{
  "epic_id": "EPIC-1122",
  "pass": 1,
  "generated_at": "<ISO-8601>",
  "module": ":driver-platform",
  "module_root": "driver-platform",
  "module_profile_skill": "gbt-module-driver-platform",
  "review": {"status": "approved", "reviewer": "<name>", "at": "<ISO-8601>"},
  "counts": {"scenarios_in_plan": 6, "generated": 5, "skipped_dedup": 1,
             "files_created": 2, "files_updated": 3},
  "files": [
    {
      "path": "driver-platform/src/test/java/tests/paymentService/componentTests/PaymentControllerTest.java",
      "action": "update",
      "role": "test",
      "scenario_ids": ["SC-001", "SC-002"],
      "package": "tests.paymentService.componentTests",
      "reason": "Added two test methods to the existing test class named in existing_paths.test"
    },
    {
      "path": "driver-platform/src/main/java/responses/paymentService/SaveCardResponse.java",
      "action": "create",
      "role": "response",
      "scenario_ids": ["SC-001"],
      "package": "responses.paymentService",
      "reason": "No response POJO matched this endpoint — created per the create_new directory"
    },
    {
      "path": "driver-platform/src/test/java/tests/driverStatus/GetDriverStatusTest.java",
      "action": "create",
      "role": "test",
      "scenario_ids": ["SC-009"],
      "package": "tests.driverStatus",
      "reason": "method_decisions.json returned no_match with requires_new_test_class: true — the endpoint resolved in the graph but 0 test methods called it, so the class and its first @Test method were both created, extending DriverPlatformTestBase per the module profile"
    },
    {
      "path": "driver-platform/src/test/java/dataProvider/AllyServiceDataProvider.java",
      "action": "update",
      "role": "data_provider",
      "scenario_ids": ["SC-012"],
      "package": "dataProvider",
      "reason": "Appended one row to getDiffabilityByAdminErrorCase per method_decisions.json data_provider_new_row verdict; vaidateErrorGetDiffabilityByAdmin itself was not touched"
    }
  ],
  "skipped": [
    {"scenario_id": "SC-007", "reason": "is_dedup",
     "detail": "Duplicate of SC-001; retained in the plan, excluded from generation."},
    {"scenario_id": "SC-001", "reason": "exact_match",
     "detail": "Already fully asserted by PaymentControllerTest#saveCardHappyPath per method_decisions.json; no change written."},
    {"scenario_id": "SC-006", "reason": "undecidable",
     "detail": "method_decisions.json could not check coverage (memgraph_unreachable); no method written. Re-run automation-plan-test-enricher then gbt-method-decision-maker."}
  ],
  "anchoring_notes": [
    "Set package of SaveCardResponse.java to responses.paymentService"
  ],
  "needs_human_placement": [],
  "todos": [
    "SC-004: expected error body for the vault-timeout case is not stated in the plan — assertion left as TODO."
  ],
  "reused_identifiers": [
    {"class": "PaymentClient", "file": "driver-platform/src/main/java/clients/paymentService/PaymentClient.java",
     "methods_called": ["saveCard"], "verified": true}
  ],
  "notes": "<short summary: which layers were reused, which created, what was skipped>"
}
```

`reused_identifiers[].verified` must be `true` for every entry — it means you opened the file
and confirmed the method is declared. If you could not verify one, set `false` and add a
`todos` entry; do not silently claim verification.

Use `""` for a missing string, `[]` for a missing list. Never use `null`.

## Portability — Claude Code and Cursor

This skill is plain markdown with no tool-specific syntax, so it runs in either. Invoke it by
name where skills are discovered, or by path where they are not:

> Read the `gbt-test-code-generator` skill and follow it for `runs/SMOKE-CODEGEN`.

`disable-model-invocation: true` means it never self-triggers; it must be named explicitly.
That is deliberate — this skill writes files into a real repo.

## What this skill does not do

State these plainly rather than implying more assurance than exists:

- **It does not compile.** Type errors, signature and arity mismatches, and generics problems
  survive it. `gbt-build-fix` runs `./gradlew :<module>:compileTestJava` in the clone for that.
- **It does not run tests.** Compiling is not passing.
- **It does not create an MR.** Files land in the working clone; committing is yours.
- **It does not fix build failures** — that is `gbt-build-fix`.
