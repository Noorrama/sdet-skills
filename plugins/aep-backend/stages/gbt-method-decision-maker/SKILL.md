---
name: gbt-method-decision-maker
description: Resolve, for each scenario in the enriched automation_plan.json, exactly which @Test method already covers it, nearly covers it and needs one assertion changed, is already covered by the method's shape but needs a new @DataProvider row for this input, or is genuinely new — writing method_decisions.json. Reads each scenario's scenario_gbt_context (written by automation-plan-test-enricher from Memgraph) to find the test, assertion, and data-provider classes to open, summarises them at method / assertion / data-provider level, and compares that summary against the scenario's steps and description. Use after automation-plan-test-enricher and the test_data merge, and before gbt-test-code-generator, in the agentic backend-test pipeline. Operates only within the classes the enricher's call-graph evidence named; never searches for a class of its own.
version: 1
disable-model-invocation: true
---

# GBT Method Decision Maker

You are a Senior SDET answering the question the enrichment step deliberately leaves open:
*given the test methods that provably already call this endpoint, which one — if any — already
covers this specific scenario?* `automation-plan-test-enricher` decides **what exists** (which
methods call the endpoint, and which assertion and data-provider classes they use, from the
Memgraph call graph). `automation-plan-generator` decides **what to test** (the scenario).
Neither decides **which method the new behavior belongs to** — that gap is why a requirement that
merely tightens an existing assertion (a field going from optional to mandatory, say) can end
up as a redundant new method instead of a one-line change to the method that already asserts
that field. It is also why a scenario that is really just **new input for an already-correct,
already-parameterised method** (e.g. `vaidateErrorGetDiffabilityByAdmin(String testName,
String driverId, String errorMessage)` in `DiffabilityAdminTest.java`, driven by
`AllyServiceDataProvider#getDiffabilityByAdminErrorCase`) can end up as a redundant new method
or a needless method edit, when the correct change is a single new row in the `@DataProvider`.

Your output is `runs/<epic_id>/pass1/artifacts/method_decisions.json`.

## Absolute rules (violating any is a critical failure)

1. **Never fabricate a method, field, or assertion.** Every entry in a method summary must
   come from a file you actually opened and parsed. If a path named in `scenario_gbt_context`
   does not exist on disk, that is a **reject** (`stale_scenario_gbt_context`) — not a silent
   `no_match`, which would hide a stale graph index behind a plausible-looking verdict.
1a. **No existing test class is not "nothing to do" — it is a new class.** When
   `test_methods_calling_endpoint` is empty, the endpoint resolved in the graph but no test
   exercises it. That is a real, common, actionable outcome: emit `no_match` **and set
   `requires_new_test_class: true`** so `gbt-test-code-generator` creates a new test class
   *and* its first `@Test` method, rather than trying to append a method to a class that does
   not exist. Never let an empty candidate set become a skip, a reject, or an `undecidable` —
   an uncovered endpoint is precisely the case the pipeline exists to fix.
2. **You operate only within the classes `scenario_gbt_context` names.** Do not re-evaluate
   whether some other class would fit better, and do not search the repo for candidates of
   your own — the enricher's `test_methods_calling_endpoint` is *proven* call-graph evidence
   and is the whole candidate set. If it names methods across several test files, summarize
   all of them, but do not pick a class on the enricher's behalf — that ambiguity must reach
   the reviewer via your own gap entry.
2a. **An `error` in `scenario_gbt_context` is never `no_match`.** Empty lists mean *matched,
   nothing found* — a genuinely uncovered endpoint, which **is** a legitimate `no_match`. An
   `error` (`memgraph_unreachable`, `no_endpoint_match`, `query_failed`, `no_module`,
   `no_endpoint`) means *nothing was checked*, and calling that `no_match` is how the pipeline
   duplicates a test that already exists. Emit `undecidable`, copy the `error` string
   verbatim into `signals`, and record an `enrichment_error` gap. Preserving this distinction
   is the single most important rule in this file.
3. **`exact_match` requires the existing method to already assert the scenario's expected
   behavior in full**, not just call the same endpoint. Calling the same controller method is
   necessary but not sufficient — an existing happy-path test and a new negative-path scenario
   on the same endpoint are never `exact_match`.
3a. **Match a gRPC scenario on `grpc_service` + `rpc_method`, never on a URL.** A gRPC endpoint
   has no path, so the "same endpoint" test that gates every verdict below is the
   service+method pair. Two RPCs on the same service are different endpoints, exactly as two
   paths would be. When you name an assertion to add or change for a gRPC scenario, express it
   in gRPC terms — a generated proto getter (`response.getX()`), or a status assertion
   (`Status.Code`, `StatusRuntimeException`) — never an HTTP status code and never a
   `deserialize(...)` DTO field. Note the failure shape differs per client in `gopay`: some
   catch the exception and return an error-bearing response, some let
   `StatusRuntimeException` propagate. If you cannot tell which applies to the target method,
   say so rather than guessing — the wrong one makes the generated test unrunnable.
4. **`closest_match_modify` must name the real method and the real assertion to change.**
   `{field, from, to}` must describe an assertion that is actually present in the method today
   (`from`) and the concrete change the scenario requires (`to`). A vague "update this
   method's assertions" is not a valid verdict — it pushes the judgement you were asked to
   make back onto codegen.
4a. **`assertion_add` is for a purely additive change, and it is the common case.** When an
   existing method already exercises the scenario's flow and the only thing missing is one
   more check — a field the requirement now says must be present, a status code the method
   never asserted — the correct answer is to **add** that assertion, not to duplicate the
   whole method as `no_match`. Distinguish it from `closest_match_modify` by asking whether
   anything existing has to change: additive → `assertion_add`; an existing assertion's value
   or strictness changes → `closest_match_modify`. Name the concrete assertion to add
   (`target`, `assertion_type`, `expected`, `message`), never "add a check for X".
4b. **Adding to a shared assertion helper has a blast radius; state it or stay out.** An
   assertion added inside `<Svc>Assertions.verifyX()` runs for **every** test that calls it —
   the parser's `called_by` list is exactly that set. Emit
   `assertion_location: "assertion_helper"` only when the new assertion holds for every
   existing caller; populate `shared_with` with the other callers so a reviewer sees the
   reach. If you cannot establish that it holds for all of them, **put the assertion in the
   test method instead** and record a `shared_assertion_blast_radius` gap explaining why the
   helper was left alone. Never silently tighten shared test infrastructure.
4c. **A data-provided method's body runs for every row.** An assertion added to such a
   method — helper or inline — must hold for **all** existing provider rows, not just the
   scenario's new one. If it only holds for the new input, this is not `assertion_add`: it is
   `no_match` (a separate method), and saying so is the correct answer. This is the quietest
   way to break a suite: one added assertion turning nine passing rows red.
5. **`data_provider_new_row` requires the method's assertions to already match the scenario's
   expectation *shape* exactly** — same flow, same assertion targets/types, same expected
   *pattern* (e.g. "returns this error shape for an invalid id") — with the only difference
   being concrete input/output **values** that the method's `@DataProvider` supplies as
   parameters. If the assertion logic itself would need to change (not just which row drives
   it), that is `closest_match_modify` or `no_match`, never this verdict.
6. **Never claim `data_provider_new_row` without reading the actual `@DataProvider` method.**
   Resolve `dataProviderClass` + `dataProvider` from the `@Test` annotation, open that class,
   and enumerate its **existing rows** verbatim. Only emit this verdict if the scenario's input
   tuple is genuinely absent from those rows — if an equivalent row already exists, the
   scenario is `exact_match` (nothing to add), not `data_provider_new_row`.
7. **`no_match` must not invent a method name.** Naming the new method is
   `gbt-test-code-generator`'s job, guided by the module profile — the same boundary
   `gbt-context-builder` already respects for `create_new` classes (directory, never a
   filename). You only say a new method is needed and why.
8a. **An `unsatisfiable_expectations` entry is a claim about the whole repo, and it must be
   earned.** Before recording a scenario expectation as unassertable, search the target module
   **and its Gradle dependencies** by *behaviour* — `querySingleValue`, `fetch.*FromDb`,
   `.*Queries`, `stubFor`, `WireMock`, `MockServer` — not by the directory you expect the
   capability to live in. Then distinguish **mechanism absent** (nothing in the repo can do
   this) from **mechanism present, this route or config missing** (an established pattern
   exists and needs one addition). Record which of the two it is, with the evidence.
   *Worked example (GOFOOD-SG-M5):* a DB expectation was recorded as "no DB-assertion capability
   in the gofood module" on the evidence that `gofood/src/test/java/db` held one unrelated file.
   The module in fact has an established meal-scheduler inspection pattern
   (`GenericUtils.fetchMealPlanBulkOrderDetailsFromDb` → `MealSchedulerDBResponse` →
   `mealSchedulerOrderController`) over a `bakso` debug service with nine routes, none of which
   covers group-order sessions. The correct finding was "add a bakso group-order-session route",
   a small assignable task — not "this module cannot assert DB state", which tells a team to
   build what they already have.

8b. **Apply the same discipline to every scenario, not just the one you noticed it on.** If an
   expectation class (a DB read, a stub call-log, a clock skew) is unassertable for one scenario,
   check every other scenario in the run for the same expectation before emitting. A `partial`
   flag on one scenario and silence on two others that share the identical gap reads as
   "those two are fully covered", which is the opposite of true.
   *Worked example:* `unsatisfiable_expectations` was first recorded on SC-002 only. SC-001 and
   SC-003 carried the same DB and stub expectations and were emitted as unqualified — the
   inconsistency was caught in review, not by the skill.

8c. **A fixture's provisioning status is not the same as its availability.** `TDP_NOT_SUPPORTED`
   from `test-data-generator` means *the TDP catalog cannot create it* — it does **not** mean the
   target module lacks it. Before treating a fixture as a blocker, check the target class's
   constants and the assertions that already run against them.
   *Worked example:* `FIX-GOFOODSG-001` ("group-order-enabled restaurant, max_participants 8")
   was `TDP_NOT_SUPPORTED`, yet `GroupOrderConstants.GO_RESTO_1` already satisfied it —
   `assertCreateGroupOrder` asserts `max_participants == "8"` and an existing method calls it with
   exactly that constant. Treating the TDP verdict as a blocker would have disabled a test for a
   fixture that was already there.

8. **Confidence and signals are mandatory on every verdict, including `exact_match`.** This is
   the one inference this skill makes (parsing is mechanical; matching is judgement) — never
   omit the evidence, mirroring how `dedup-generator` reports `similarity` + `signals` for the
   same reason.
9. **An ambiguous match is a gap, not a guess.** If two methods are both plausible targets for
   `closest_match_modify`/`data_provider_new_row` and neither is clearly closer, emit both
   under `ambiguous_candidates` and record the `method_match_ambiguous` gap for a reviewer to
   resolve — do not pick one arbitrarily.
10. **Strip comments and normalize whitespace before comparing assertion text**, reusing the
    normalization approach `dedup-generator/reference.md` already defines for the same reason
    (formatting differences are not semantic differences) — do not re-derive a different
    normalization here.
11. **Output exactly one JSON object.** No prose, no markdown fences, no commentary.

## Before you build

Your single input is the **enriched** plan —
`runs/<epic_id>/pass1/artifacts/automation_plan_enriched.json`. From each scenario read both
halves:

| From the scenario itself | From its `scenario_gbt_context` |
|---|---|
| `description`, the scenario's **steps**, `endpoint`, `expected_response`, `implementation_constraints`, `test_data` — *what the scenario requires* | `test_methods_calling_endpoint` (`(test_file, test_method)` pairs), `test_assertions` (assertion classes those methods use), `test_data_providers` (`@DataProvider` methods they use), `endpoint_file` — *what already exists* |

Open, from `workspace.gbt_repo` (the run's worktree): every `test_file` in `test_methods_calling_endpoint`, every class in
`test_assertions`, and every class in `test_data_providers`. For any `@Test` method that
declares `dataProvider`/`dataProviderClass`, **resolve the provider from the `@Test`
annotation** rather than trusting `test_data_providers` to be the right one — the enricher
reports providers used by the endpoint's methods collectively, and a given method's provider
is not always the one listed first.

`test_assertions` matters as much as the methods: a GBT assertion helper
(`<Svc>Assertions.verifyX(...)`) holds the real assertion logic, so a method whose body is a
single helper call is **not** assertion-free. Summarise the helper's assertions and attribute
them to the calling method, or you will read a fully-asserted method as an empty one and
return a spurious `no_match`.

## Definition of Ready (DoR)

- The enriched plan is present, schema-valid, and every non-`is_dedup` scenario carries a
  `scenario_gbt_context` object (either populated or holding an `error`).
- At least one scenario with `is_dedup: false`.
- Every path named in a populated `scenario_gbt_context` exists on disk in `workspace.gbt_repo`.

## Reject if

| Reason | Detail |
|---|---|
| `missing_input` | The enriched plan is absent or unparseable |
| `missing_enrichment` | A non-`is_dedup` scenario has no `scenario_gbt_context` key at all — `automation-plan-test-enricher` did not run, or ran against a different plan. Reject rather than treating an unenriched scenario as uncovered |
| `stale_scenario_gbt_context` | A path named in `scenario_gbt_context` does not exist on disk — the graph index is stale; re-index and re-run the enricher rather than deciding against a fiction |
| `enrichment_unusable` | **Every** non-`is_dedup` scenario's `scenario_gbt_context` holds an `error`. Nothing was checked, so no verdict is defensible. Copy one `error` verbatim as the detail |
| `unparseable_test_class` | A named file exists but its `@Test` methods could not be parsed (e.g. malformed Java) — reject rather than silently skipping it, since a skipped class could hide an `exact_match` |
| `unparseable_data_provider` | A method declares `dataProvider`/`dataProviderClass` but that class could not be opened or its rows could not be parsed — reject rather than guessing `data_provider_new_row` against unknown rows |

A **mix** of errored and populated contexts is not a reject: decide the populated ones, mark
the errored ones `undecidable` per rule 2a, and carry both into `gaps`.

On reject, write `runs/<epic_id>/pass1/rejects/gbt-method-decision-maker.json`:

```json
{"stage": "gbt-method-decision-maker", "reason": "<code>", "detail": "<what and where>",
 "remediation": "<the exact command or stage to run>"}
```

## Step 0 — run the parser, do not parse by eye

The mechanical half of step 3 is done by
[references/parse_test_classes.py](references/parse_test_classes.py) — stdlib only, no venv,
no pip. It reads the enriched plan, opens every class named across all
`scenario_gbt_context` objects, and emits `method_summaries`, `assertion_summaries` and
`data_provider_summaries` ready to drop into your output.

```bash
CYPHER_SKIP=1  # no graph needed here
SCRIPT=$( { [ -n "$CLAUDE_PLUGIN_ROOT" ] && find "$CLAUDE_PLUGIN_ROOT" -name parse_test_classes.py 2>/dev/null; \
  find "${CI_PROJECT_DIR:-.}" "$HOME/.claude/plugins" -name parse_test_classes.py 2>/dev/null; } | head -1)
python3 "$SCRIPT" \
  --plan runs/"$EPIC"/pass1/artifacts/automation_plan_enriched.json \
  --repo "$GBT_REPO" \
  --out  runs/"$EPIC"/pass1/artifacts/parsed_classes.json
```

It is ~4s for the whole `driver-platform` tree (2,886 files, 1,364 `@Test` methods), so there
is no reason to skip it and count data-provider columns manually.

**Read `parse_report` before trusting the rest**, and treat these three fields as reject
triggers rather than noise:

| Field | Means | Do |
|---|---|---|
| `unreadable_files[]` | a path in `scenario_gbt_context` could not be opened | reject `stale_scenario_gbt_context` |
| `providers_with_unparsed_rows[]` | that provider builds rows dynamically (loop, builder, stream), so `rows` is **not** the full set | reject `unparseable_data_provider` for any scenario you would otherwise call `data_provider_new_row` on it — never guess a row against an unknown set |
| `assertion_helpers_called[].resolved == false` | a bare `verifyX(...)` whose class the static imports did not pin down | locate the class yourself before judging the method's assertions; do not treat it as assertion-free |

The script is deliberately narrow: it reports structure, never verdicts. If its output and the
file disagree, the file wins — open it.

## Procedure

1. Read the enriched plan and run the parser (step 0). Run DoR and reject checks.
2. **Partition the scenarios** by their `scenario_gbt_context`:
   - holds an `error` → `undecidable` (rule 2a); no files to open.
   - populated with an empty `test_methods_calling_endpoint` → `no_match` directly, **with
     `requires_new_test_class: true`** (rule 2b); the endpoint resolved but nothing tests it,
     so there is no class to add a method to. Record `signals: ["endpoint matched in graph, 0
     test methods call it"]` so the verdict is distinguishable from an unchecked one.
   - populated with at least one `(test_file, test_method)` → goes to the summary pass below.
3. **Build the three-level summary** for every scenario in the last bucket — from
   `parsed_classes.json` (step 0), which already contains all three levels. Your work here is
   to *inline and verify*, not to re-parse:
   a. **Method level** — `method_summaries[].methods[]` gives
      `{method_name, groups, description, parameters, flow, assertions,
      assertion_helpers_called, data_provider}`. Keep only the methods named in this
      scenario's `test_methods_calling_endpoint`; the file may hold many others.
   b. **Assertion level** — for each `assertion_helpers_called` entry, find the matching
      `assertion_summaries[].methods[]` and **inline its `asserts` into the calling method's
      `assertions` list, tagged `via: "<Class>#<method>"`**. This is the step that keeps a
      GBT test honest: a method whose whole body is `verifyGetCommsResponseValid(response)`
      asserts three things, and reading it as assertion-free returns a spurious `no_match`.
      Where `resolved: false`, open the class yourself first.
   c. **Data-provider level** — `data_provider_summaries[]` gives
      `{data_provider_class, data_provider_method, rows: [{row_index, values}], rows_parsed}`,
      `values` already in the `@Test` method's parameter order. If `rows_parsed` is `false`,
      the row set is unknown — reject rather than compare against it.
4. **Compare the scenario against the summary.** For each scenario with `is_dedup: false` in
   the summary bucket, match its **steps** and `description` — plus `expected_response`,
   `implementation_constraints`, and `test_data`-implied behaviour — against every method
   summary built in step 3. Match the scenario's steps to the method's `flow` (does it exercise
   the same call sequence?) and its `description`/`expected_response` to the method's inlined
   `assertions` (is the same thing asserted, and to the same strictness?):
   a. If the method is **not** data-provided, and its assertions already cover the scenario's
      expected behavior in full → `exact_match`.
   b. If the method **is** data-provided, and its assertion shape (rule 5) already matches the
      scenario, check whether the scenario's input tuple already appears in the provider's
      rows (compare against `test_data`/`expected_response`, mapped through the method's
      parameter order):
      - Row already present → `exact_match` (nothing to add).
      - Row absent → `data_provider_new_row`, naming `target_class`, `target_method`,
        `data_provider_class`, `data_provider_method`, and the exact `new_row` values in
        parameter order (rule 6).
   c. Else if a method exercises the same flow and the scenario's expectation is satisfied by
      **adding** an assertion — nothing existing has to change — → `assertion_add` (rule 4a).
      Decide `assertion_location` deliberately:
      - the scenario checks something specific to *this* case → `"test_method"`.
      - the scenario tightens the endpoint's shared contract, and the field is present for
        every existing caller → `"assertion_helper"`, naming the helper and its `shared_with`
        blast radius.
   d. Else if a method shares the same flow and an **existing** assertion must change value or
      strictness → `closest_match_modify`, naming the exact assertion delta.
   e. Else → `no_match`.
   f. If steps (b)–(d) find more than one comparably-close method, emit them under
      `ambiguous_candidates` and record the `method_match_ambiguous` gap instead of picking.
5. Every non-`is_dedup` scenario must end with exactly one entry in `decisions` — including
   the `undecidable` and direct-`no_match` buckets from step 2. `gbt-test-code-generator`
   rejects with `missing_method_decision` on any gap here, so never drop a scenario silently.
6. Write `method_decisions.json`.

## OUTPUT — return ONLY a single valid JSON object

```json
{
  "epic_id": "EPIC-1122",
  "pass": 1,
  "generated_at": "<ISO-8601>",
  "method_summaries": [
    {
      "class": "PaymentControllerTest",
      "path": "driver-platform/src/test/java/tests/paymentService/componentTests/PaymentControllerTest.java",
      "methods": [
        {
          "method_name": "saveCardHappyPath",
          "groups": ["smoke", "regression", "component"],
          "parameters": [],
          "flow": ["paymentController.saveCard(request)"],
          "assertions": [
            {"target": "response.token", "assertion_type": "assertNotNull", "expected": "non-null"},
            {"target": "response.httpStatusCode", "assertion_type": "assertEquals", "expected": "200"}
          ]
        }
      ]
    },
    {
      "class": "DiffabilityAdminTest",
      "path": "driver-platform/src/test/java/tests/allyService/DiffabilityAdminTest.java",
      "methods": [
        {
          "method_name": "vaidateErrorGetDiffabilityByAdmin",
          "groups": ["ALLY_SERVICE_COMPONENT"],
          "parameters": ["testName", "driverId", "errorMessage"],
          "flow": ["allyServiceController.getDiffabilityAdminResponse(driverId)"],
          "assertions": [
            {"target": "response.error", "assertion_type": "assertEquals", "expected": "errorMessage", "via": "AllyServiceAssertions#verifyNotFoundGetDiffabilityResponse"},
            {"target": "response.httpStatusCode", "assertion_type": "assertEquals", "expected": "404", "via": "AllyServiceAssertions#verifyNotFoundGetDiffabilityResponse"}
          ],
          "data_provider": {"data_provider_class": "AllyServiceDataProvider", "data_provider_method": "getDiffabilityByAdminErrorCase"}
        }
      ]
    }
  ],
  "assertion_summaries": [
    {
      "assertion_class": "AllyServiceAssertions",
      "path": "driver-platform/src/test/java/assertions/AllyServiceAssertions.java",
      "methods": [
        {
          "assertion_method": "verifyNotFoundGetDiffabilityResponse",
          "soft": true,
          "asserts": [
            {"target": "response.error", "assertion_type": "assertEquals", "expected": "errorMessage (parameter)"},
            {"target": "response.httpStatusCode", "assertion_type": "assertEquals", "expected": "404"}
          ],
          "called_by": ["DiffabilityAdminTest#vaidateErrorGetDiffabilityByAdmin"]
        }
      ]
    }
  ],
  "data_provider_summaries": [
    {
      "data_provider_class": "AllyServiceDataProvider",
      "data_provider_method": "getDiffabilityByAdminErrorCase",
      "rows": [
        {"row_index": 0, "values": ["invalid driver id", "not-a-real-driver-id", "Driver not found"]}
      ]
    }
  ],
  "decisions": [
    {
      "scenario_id": "SC-004",
      "endpoint": "POST /payment/v1/cards",
      "verdict": "closest_match_modify",
      "target_class": "PaymentControllerTest",
      "target_method": "saveCardHappyPath",
      "data_provider_class": "",
      "data_provider_method": "",
      "new_row": [],
      "assertion_change": {
        "target": "response.cardHolderName",
        "from": "no assertion present (field was optional)",
        "to": "assertNotNull(response.cardHolderName, \"cardHolderName is now mandatory\")"
      },
      "confidence": 0.88,
      "signals": ["same endpoint and flow", "same fixture shape", "field named explicitly in scenario expected_response"],
      "requires_new_test_class": false,
      "ambiguous_candidates": []
    },
    {
      "scenario_id": "SC-015",
      "endpoint": "GET /ally/v1/diffability/admin/{driverId}",
      "verdict": "assertion_add",
      "target_class": "DiffabilityAdminTest",
      "target_method": "vaidateErrorGetDiffabilityByAdmin",
      "data_provider_class": "",
      "data_provider_method": "",
      "new_row": [],
      "assertion_change": null,
      "assertion_add": {
        "assertion_location": "assertion_helper",
        "assertion_class": "AllyServiceAssertions",
        "assertion_method": "verifyNotFoundGetDiffabilityResponse",
        "addition": {
          "target": "response.errorCode",
          "assertion_type": "assertEquals",
          "expected": "AllyErrorCode.DRIVER_NOT_FOUND",
          "message": "\"errorCode must be present on the not-found response\""
        },
        "shared_with": ["DiffabilityAdminTest#vaidateGetDiffabilityByAdminForbidden"],
        "holds_for_all_callers": true,
        "holds_for_all_provider_rows": true
      },
      "confidence": 0.86,
      "signals": ["method already exercises the not-found flow", "requirement adds errorCode to the shared not-found contract", "both callers assert the same not-found shape, so the addition holds for each", "all 4 provider rows are not-found cases"],
      "requires_new_test_class": false,
      "ambiguous_candidates": []
    },
    {
      "scenario_id": "SC-001",
      "endpoint": "POST /payment/v1/cards",
      "verdict": "exact_match",
      "target_class": "PaymentControllerTest",
      "target_method": "saveCardHappyPath",
      "data_provider_class": "",
      "data_provider_method": "",
      "new_row": [],
      "assertion_change": null,
      "confidence": 0.95,
      "signals": ["same expected_response fields and values already asserted"],
      "requires_new_test_class": false,
      "ambiguous_candidates": []
    },
    {
      "scenario_id": "SC-012",
      "endpoint": "GET /ally/v1/diffability/admin/{driverId}",
      "verdict": "data_provider_new_row",
      "target_class": "DiffabilityAdminTest",
      "target_method": "vaidateErrorGetDiffabilityByAdmin",
      "data_provider_class": "AllyServiceDataProvider",
      "data_provider_method": "getDiffabilityByAdminErrorCase",
      "new_row": ["expired driver id", "expired-driver-999", "Driver not found"],
      "assertion_change": null,
      "confidence": 0.9,
      "signals": ["same method, same flow, same not-found assertion shape", "input tuple absent from existing rows", "only the driverId/errorMessage values differ"],
      "requires_new_test_class": false,
      "ambiguous_candidates": []
    },
    {
      "scenario_id": "SC-009",
      "endpoint": "POST /payment/v1/cards/vault-timeout",
      "verdict": "no_match",
      "target_class": "",
      "target_method": "",
      "data_provider_class": "",
      "data_provider_method": "",
      "new_row": [],
      "assertion_change": null,
      "confidence": 1.0,
      "signals": ["endpoint matched in graph, 0 test methods call it", "no existing test class for this endpoint — codegen must create the class and its first method"],
      "requires_new_test_class": true,
      "ambiguous_candidates": []
    },
    {
      "scenario_id": "SC-006",
      "endpoint": "GET /driver/v1/status",
      "verdict": "undecidable",
      "target_class": "",
      "target_method": "",
      "data_provider_class": "",
      "data_provider_method": "",
      "new_row": [],
      "assertion_change": null,
      "confidence": 0.0,
      "signals": ["memgraph_unreachable: bolt://<host>:7687 - ServiceUnavailable: failed to connect"],
      "requires_new_test_class": false,
      "ambiguous_candidates": []
    }
  ],
  "gaps": [
    {"gap": "enrichment_error", "scenario_id": "SC-006",
     "detail": "scenario_gbt_context held an error; no coverage was checked. Do NOT read this as an uncovered endpoint.",
     "remediation": "Restore bolt connectivity and re-run automation-plan-test-enricher, then re-run this skill."}
  ],
  "warnings": []
}
```

Use `""` for a missing string, `[]` for a missing list, `null` only for `assertion_change`
when the verdict is not `closest_match_modify`. `data_provider_class`/`data_provider_method`
are `""` and `new_row` is `[]` except on `data_provider_new_row`.

`verdict` is one of `exact_match`, `assertion_add`, `closest_match_modify`,
`data_provider_new_row`, `no_match`, `undecidable`. `assertion_add` is `null`/omitted on every
verdict except `assertion_add`, and `assertion_change` is `null` except on
`closest_match_modify` — the two are mutually exclusive by construction: one adds, the other
alters.

The distinction that decides between them, and it is worth being pedantic about:

| The scenario needs… | Verdict |
|---|---|
| a check that is not there yet; nothing existing changes | `assertion_add` |
| an existing check to assert a different value or be stricter | `closest_match_modify` |
| the same checks against a new input tuple | `data_provider_new_row` |
| a different flow, or an addition that would break other rows/callers | `no_match` |

**`undecidable` is not a soft `no_match`** — `no_match` instructs
codegen to write a new method, `undecidable` instructs it to write nothing and record a
reviewer TODO. Emitting `no_match` where `undecidable` belongs is how an unreachable graph
becomes a duplicated test suite.

`requires_new_test_class` is mandatory on every decision and is `false` everywhere except a
`no_match` whose `scenario_gbt_context` had an empty `test_methods_calling_endpoint` — i.e.
there is no existing test class for this endpoint, so codegen must create the class *and* its
first `@Test` method. Do **not** name the class here; naming stays `gbt-test-code-generator`'s
job with the module profile's conventions (rule 7). The three states codegen must be able to
tell apart:

| `scenario_gbt_context` | Verdict | `requires_new_test_class` | Codegen writes |
|---|---|---|---|
| populated, methods found, none cover the scenario | `no_match` | `false` | a new method in the existing class |
| populated, `test_methods_calling_endpoint` empty | `no_match` | `true` | a **new test class + first method** |
| holds an `error` | `undecidable` | `false` | nothing, plus a reviewer TODO |

## What this skill does not do

- **It does not find the candidate classes.** `automation-plan-test-enricher` does, from the
  Memgraph call graph, and this skill treats `scenario_gbt_context` as input — never
  re-queried, never supplemented with a repo search of its own.
- **It does not parse Java by eye.** `references/parse_test_classes.py` does the structural
  work — `@Test` attributes, static-import resolution, assertion-helper bodies, and
  data-provider rows in parameter order. This skill spends its judgement on *matching*, which
  is the part a script cannot do. The script reports structure and never a verdict.
- **It does not decide file placement or packages.** That is `gbt-context-builder`, which runs
  *after* this skill in the orchestrated order and answers a different question: where a
  *new* file goes, not which existing method to touch.
- **It does not name new methods.** `no_match` says a new method is needed; naming it is
  `gbt-test-code-generator`'s job with the module profile's conventions.
- **It does not write or modify any file** — not the test method, and not the data provider.
  It reports a decision, including the exact new row for `data_provider_new_row`;
  `gbt-test-code-generator` executes it — same separation `test-code-validator` keeps from
  `gbt-build-fix`.
- **It is not duplicate detection.** `dedup-generator` answers "is this scenario/method
  already written somewhere, near-identically" (a binary-ish near-duplicate check); this
  skill answers "which specific existing method, if any, is the right place for this new
  behavior, and what exactly changes in it."
