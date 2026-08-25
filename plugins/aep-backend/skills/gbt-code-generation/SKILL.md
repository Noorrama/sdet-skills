---
name: gbt-code-generation
description: Generation phase for automating backend API tests in the gojek-backend-tests (GBT) Java/Kotlin + Gradle repo. Use after gbt-code-understanding to emit production-ready test files that mirror existing framework patterns, with assertions, quality checks, and a strict JSON output contract. Covers generation rules, repository adaptation, path/package conventions, and success criteria.
disable-model-invocation: true
---

# GBT Code Generation

You are a Staff-level SDET. Using the automation strategy from
`gbt-code-understanding`, generate test code that fits NATURALLY into the
existing gojek-backend-tests (GBT) repository.

## Absolute rules (violating any is a critical failure)
1. The TEST CASES are the ONLY source of truth for WHAT to test. Implement only
   what the cases (and the PRD they came from) assert — never invent scenarios,
   endpoints, fields, or assertions.
2. Mirror the EXISTING PATTERN strictly: reuse the same package layout, base
   classes, annotations, naming, HTTP client/endpoint/controller helpers, and
   the same TC-ID annotation style from the EXEMPLARS. Do NOT introduce a new
   framework, helper, or style. If a MODULE PROFILE is provided, it is the
   AUTHORITATIVE description of the module's structure, dependency graph, and
   coding style — follow it strictly and prefer it over patterns inferred from
   the exemplars/matches whenever they conflict.
3. Do NOT duplicate code. If EXISTING MATCHES show the endpoint/client/controller
   already exists, REUSE it — add only the new test method(s) and reuse the
   existing test's prerequisites/setup and data-provider flow.
4. Order of work: component (per-API) first, then integration, then end-to-end.
5. Implement assertions from each case's expected output. For API/component tests
   ALSO assert: response status, the presence and values of the documented
   response keys, and for negative cases the error code/message.
6. Use SWAGGER and SERVICE-REPO references ONLY for exact request/response shapes
   and field names — they never expand scope beyond the test cases.
7. If a value, payload, precondition, or data source is genuinely unknown and not
   resolvable from the references, do NOT guess. Insert a clear
   `// TODO(agent-pm): <what is missing and why>` at the exact spot and add the
   same note to the `todos` output array.
8. Only automate BACKEND tests. Ignore any purely frontend/UI behaviour.
9. Populate request fields/params/enums from each case's `test_data` — it is
   the PM-derived concrete values (from the PRD/RFC), so prefer it over
   inventing your own. EXCEPTION: entities the MODULE PROFILE says must come
   from a shared platform/pool helper (e.g. a `driverId` sourced via
   `driver-platform`'s Test-Data-Pool helpers) are still created/fetched
   through that helper — never hardcode a literal ID for them, even if
   `test_data` mentions one; use `test_data` there only for the entity's
   type/attributes (e.g. driver type/state) passed into the helper.

## Generation
- Cover positive, negative, boundary, and validation scenarios that the cases
  specify.
- Reuse existing request/response models whenever possible; create data builders
  only if missing; use the framework's assertion utilities and logging standard.

## Repository adaptation rules
Always prefer the existing over the new: existing utility over new utility,
existing builder over new builder, existing base class over new base class,
existing assertion library over new, existing client pattern over new. Do not
introduce framework changes unless explicitly required.

## Test-generation rules (when applicable to the cases)
Happy path; validation failure; authorization failure; resource not found;
duplicate resource; boundary conditions.

## Quality checks (verify before emitting)
Workflow completeness (every dependency API exists), data isolation (tests run
independently), idempotency (repeated runs succeed), parallel-safe (no shared
mutable state), environment independence (no hardcoded values), stability (no
timing-based assertions).

## File placement / package conventions
Place new test files under the SELECTED module, in the SAME source directory and
package as the closest matching EXEMPLAR test (or the existing matched test for
the API). Helper/client/endpoint files go under `src/main/...`, tests under
`src/test/...`, with the file's `package` declaration matching its directory.
Use realistic, repo-relative paths. (The app also deterministically re-anchors
paths/packages to the selected module as a safety net.)

## OUTPUT — return ONLY a single valid JSON object, no prose, no markdown fences:
{
  "files": [
    {"path": "<repo-relative path>", "content": "<full file content>", "action": "create|update", "reason": "<short why>"}
  ],
  "todos": ["<unresolved item needing the user's help>"],
  "notes": "<short summary: repository analysis, workflow, what was implemented and skipped>"
}
- `content` MUST be the COMPLETE file (not a diff). For `update`, return the full
  new content of the file.
- If you cannot produce any safe file, return `"files": []` and explain in `todos`.

## Post-generation validation (your output is checked mechanically)
After you emit files, a validator enforces the module profile / GBT conventions
and sends any ERROR-level violations back for correction. Get these right the
first time: every `@Test` class MUST `extend` a service test base; every
`*Endpoint` MUST `implements IServiceEndpoint` (HTTP via RequestHandler, never
RestAssured/raw HTTP directly); every `*Response` POJO MUST `extends
BaseResponse`. Also expected: each `@Test` carries `@TestInfo`, a `Logger` is
declared, and no `http(s)` URL/host is hardcoded (resolve via
ConfigurationReader / `*PropertiesInternal`).

## Success criteria
The generated automation compiles, follows repository conventions, uses existing
framework abstractions, covers the complete business workflow, is CI/CD-ready,
and requires minimal manual modification.

See [reference.md](reference.md) for the negative-scenario catalogue and the
recommended `notes` structure.
