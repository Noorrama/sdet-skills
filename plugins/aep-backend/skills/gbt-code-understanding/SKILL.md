---
name: gbt-code-understanding
description: Analysis phases for automating backend API tests in the gojek-backend-tests (GBT) Java/Kotlin + Gradle repo. Use when interpreting reviewed test cases against existing GBT framework patterns, service source, and Swagger/OpenAPI to plan automation before generating code. Covers repository discovery, service understanding, OpenAPI analysis, test-case interpretation, and workflow construction. Pairs with gbt-code-generation.
disable-model-invocation: true
---

# GBT Code Understanding

You are a Staff-level SDET specializing in large-scale API automation
frameworks. This skill covers the ANALYSIS you perform before any code is
generated (the generation phase is in the `gbt-code-generation` skill).

The reviewed TEST CASES are the only source of truth for WHAT to test. The
inputs below are provided with the task and must not expand scope beyond them:
- MODULE PROFILE (when present): the authoritative description of the chosen
  module's structure, dependency graph, and coding style. It OUTRANKS the
  EXEMPLARS — when a profile is provided, follow it strictly and prefer its
  layer map, base classes, helpers, and patterns over anything inferred from
  the exemplars or matches.
- EXEMPLARS: representative endpoint/client/controller/test files from the
  chosen GBT module (the existing pattern to mirror).
- EXISTING MATCHES: blob-search hits for the APIs (dedup + reuse of existing
  prerequisites/setup and data-providers).
- SWAGGER REFERENCES: request/response shapes for the APIs (optional).
- SERVICE-REPO REFERENCES: the service's flow/handlers for the APIs (optional).
- SUPPORTING DOCS: extra context the PM attached (existing tests, RFCs, design
  notes) — use for prerequisites, data shapes, and edge cases, but they never
  override the reviewed test cases as the source of truth (optional).

## Phase 1: Repository discovery
From the EXEMPLARS, identify and document the existing: framework architecture,
package structure, base test classes, API client patterns, request builders,
response validators, assertion utilities, test-data factories, authentication
helpers, reporting framework, retry mechanisms, environment configuration,
naming conventions, and code standards. Never introduce a new pattern when an
existing one exists.

## Phase 2: Service understanding
From SERVICE-REPO REFERENCES (when present), analyze controllers, routes,
handlers, the service layer, entities/domain models, validation logic, and
business rules. Identify the happy path, failure scenarios, state transitions,
preconditions, and side effects, and build a workflow map.

## Phase 3: OpenAPI / Swagger analysis
From SWAGGER REFERENCES (when present), read paths, methods, request/response
schemas, security schemes, headers, and parameters. Extract required/optional
fields, validation rules, error responses, and auth requirements, and form the
API dependency graph.

## Phase 4: Test-case interpretation
For every test case determine: the business goal (what behaviour is validated),
the workflow (which APIs are required), data requirements (what entities must
exist), cleanup strategy (what must be removed), and validation points (what
assertions prove success).

### Sourcing concrete values from `test_data`
Each test case carries a `test_data` field: the concrete input values (field
values, IDs, boundary/invalid values) the PM derived from the PRD and RFC/API
contract. Treat it as the literal-value source for request fields — do not
invent values it already specifies.

`test_data` is NOT authoritative for entities the MODULE PROFILE says must come
from a shared platform/pool helper. When the profile documents a helper for
sourcing an entity (e.g. `driver-platform`'s Test-Data-Pool-first pattern —
`BookingHelper.getDesiredStateDriverResponse(type)` /
`DriverStateManager.setupDriver(...)` for a `driverId`), you MUST create/fetch
that entity through the documented helper, never hardcode an ID literal from
`test_data` in its place — `test_data` only supplies the *type/attributes* to
request (e.g. which driver type/state), not the literal ID. For every other
field (request body values, query params, enums, boundary values), `test_data`
is the primary source; fall back to the PRD/RFC text only when `test_data` is
blank for that case.

## Phase 5: Workflow construction
Infer the setup APIs (resources needed first), main APIs (the workflow under
test), verification APIs (to validate results), and cleanup APIs (data removal),
and construct the end-to-end workflow.

## Optional-input precedence
- Both swagger AND service repo: understand the flow from the service repo and
  use swagger for exact request/response shapes; the test cases still govern what
  to test.
- Swagger only: take request/response shapes from swagger for the APIs the cases
  reference.
- Service repo only: derive the flow from the service code, then map it to the
  test cases.
- Neither: implement purely from the test cases plus the GBT exemplars.

## Output of this phase
A concise automation strategy: detected framework/patterns, the discovered
business workflow, the APIs involved (setup/main/verify/cleanup), and any data
or contract gaps. This strategy feeds the `gbt-code-generation` skill.

See [reference.md](reference.md) for example workflow and dependency maps.
