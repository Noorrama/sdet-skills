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
2. **`existing_paths` decides placement; `method_decisions.json` decides which method.** A
   `reuse` verdict carries a real path: **open that file**. Within it, follow the scenario's
   verdict in `method_decisions.json`:
   - `exact_match` → write nothing for that scenario (record it as already-covered).
   - `data_provider_new_row` → touch **only** the named `data_provider_class` /
     `data_provider_method`'s file, appending exactly `new_row` in the method's existing
     parameter order. Do not touch the `@Test` method or any other row.
   - `closest_match_modify` → edit the named method's named assertion only, and touch nothing
     else in it.
   - `no_match` → add a new method, naming it per the module profile.
   Emit `"action": "update"` with the complete new file content in the
   `data_provider_new_row`/`closest_match_modify`/`no_match` cases. Never create a sibling
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
11. **Unknowns become `// TODO(agent-pm): <what is missing and why>`** *and* an entry in
    `todos[]`. Guessing silently is the failure; a TODO is correct behaviour.
12. **Write the files and the manifest.** This skill's deliverable is files on disk, not a
    JSON blob in the chat.

## Inputs

| Path | Required | Used for |
|---|---|---|
| `runs/<epic>/pass1/artifacts/automation_plan.json` | yes | scenarios, routing, `existing_paths`, constraints, and `test_data_payloads` for `{{…}}` resolution |
| `runs/<epic>/pass1/gbt_context.json` | yes | packages, module root, exemplars, layer verdicts |
| `runs/<epic>/pass1/artifacts/method_decisions.json` | yes | per-scenario method verdict: `exact_match` (skip) / `data_provider_new_row` (append one row to the named data provider) / `closest_match_modify` (edit named method+assertion) / `no_match` (new method) |
| `runs/<epic>/run.json` | yes | the review gate |
| `.gbt_repo/` | yes | the working clone — read existing files, write new ones |

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
- `run.json` shows `review.status == "approved"` for this pass.
- `.gbt_repo` exists and `{module_root}` resolves to a real directory inside it.
- At least one scenario with `is_dedup: false`.
- Every `reuse` path in `existing_paths` exists on disk.

## Reject if

| Reason | Detail |
|---|---|
| `review_not_approved` | Gate is `pending` or `changes_requested` |
| `missing_input` | Any of the three inputs absent or unparseable, or `automation_plan.test_data_payloads` absent |
| `missing_method_decision` | A non-`is_dedup` scenario has no entry in `method_decisions.decisions` — never default it to `no_match` silently |
| `gbt_repo_missing` | No `.gbt_repo`, or `{module_root}` not found in it |
| `stale_gbt_context` | A `reuse` path does not exist on disk — the graph is stale; regenerate `gbt_context` rather than generating against a fiction |
| `stale_method_decision` | A `closest_match_modify`/`exact_match`/`data_provider_new_row` verdict names a method or data provider that is no longer present in the target file — regenerate `method_decisions` rather than editing against a fiction |
| `unresolvable_fixture` | A `{{fixture-id.field}}` has no entry in `automation_plan.test_data_payloads` |
| `nothing_to_generate` | Every scenario is `is_dedup`, `exact_match`, or dropped. A legitimate outcome, not a bug — say so |

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
        reused test class (or a new class when the layer verdict is `create_new`).
   c. Resolve `{{fixture-id.field}}` through `automation_plan.test_data_payloads`.
4. Anchor every file per the algorithm above.
5. Write the files into `.gbt_repo`.
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
     "detail": "Already fully asserted by PaymentControllerTest#saveCardHappyPath per method_decisions.json; no change written."}
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
  survive it. Run `.gbt_repo/gradlew :<module>:compileTestJava` for that.
- **It does not run tests.** Compiling is not passing.
- **It does not create an MR.** Files land in the working clone; committing is yours.
- **It does not fix build failures** — that is `gbt-build-fix`.
