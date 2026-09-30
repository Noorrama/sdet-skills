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
   - ONE ENDPOINT, ONE TEST CLASS. This rule's reuse applies to the helper layers
     (endpoint/client/controller), which legitimately hold many endpoints. It does
     NOT apply to test classes: a scenario whose endpoint differs in method or path
     from the class you were pointed at gets its OWN test class in that class's
     directory, named for its endpoint. Use the sibling as the structural template
     and call its controller for setup.
   - EXTENDING AN EXISTING API MEANS THE WHOLE REQUEST CHAIN. When a case adds a
     field to an already-automated endpoint, walk request model → body builder →
     endpoint → client → controller → response model → assertion helper → data
     provider, and report what you did to each in `notes`, including what you left
     unchanged and why. Two specific traps: a failure-path controller method pins
     ONE expected status, so a new 400-validation path needs an overload that takes
     the expected status (never loosen it to `assertTrue(a || b)`); and a DTO whose
     class-level Lombok `@Builder` sits beside a hand-written constructor breaks the
     moment you add a third field — delete the unused constructor rather than
     demoting `@Builder` onto a new one. Full detail in
     `backend-automation/references/extending-an-existing-api.md`.
3c. TRANSPORT DECIDES THE STACK. A scenario carrying `protocol: "grpc"` (or a
   `grpc_service`/`rpc_method` pair) is generated against the module's gRPC
   stack, never the REST one: generated protobuf builders for the request,
   generated getters for the response, `Metadata.Key.of(..., ASCII_STRING_MARSHALLER)`
   for headers, the module's existing connection/client object for the call, and
   `io.grpc.Status` semantics for failures. Absent `protocol` means REST — existing
   plans are unaffected. Emitting an `IServiceEndpoint`, a `RequestHandler` call, a
   handwritten DTO in place of a generated proto type, or an HTTP-status assertion
   for a gRPC scenario is a critical failure. Never modify generated protobuf
   sources. See `backend-automation/references/grpc-transport-contract.md` and the
   module's gRPC writer agent (`gopay-grpc-api-test-writer`,
   `gofood-grpc-api-test-writer`) — its document is at
   `reference/module-writers/<writer-name>/SKILL.md`.
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
mutable state), stability (no timing-based assertions).

**Environment correctness** deserves its own check, because it fails silently —
green on QA, 404 on integration. Every provisioned entity id (restaurant,
merchant, customer, group, offer, voucher batch) must resolve through the
module's per-environment mechanism: an `I<Domain>Constants` +
`<Domain>Constants{Qa,Int,Uat}` family, a per-environment properties file, or a
runtime pool helper. Add a getter AND an implementation in every environment
class — a missing one should be a compile error. Only environment-INdependent
values belong in a shared constants class: enum/protocol literals, locale and
country headers, and deliberately-invalid ids that resolve nowhere by design.
Keep the public constant name clean — an unprovisioned value gets a placeholder
and a `// TODO:` inside the per-environment implementation, never a `DUMMY_`
prefix on the constant. See
`backend-automation/references/environment-specific-test-data.md`.

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

**Those three MUSTs are REST invariants and do not apply to a gRPC scenario.** A
gRPC endpoint implements the module's `IGrpcServiceEndpoint` (gofood) or has no
endpoint layer at all (gopay); there is no `RequestHandler`; and responses are
generated proto types that extend no `BaseResponse`. The gRPC equivalents are:
generated builders for requests, generated getters for responses, metadata via
`Metadata.Key.of`, the module's existing channel/connection, and `io.grpc.Status`
for failures. `@TestInfo` is also not universal on gopay's gRPC surface — match
the sibling class. The no-hardcoded-host rule holds for both transports.

## Success criteria
The generated automation compiles, follows repository conventions, uses existing
framework abstractions, covers the complete business workflow, is CI/CD-ready,
and requires minimal manual modification.

See [reference.md](reference.md) for the negative-scenario catalogue and the
recommended `notes` structure.
