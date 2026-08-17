---
name: gopay-api-test-writer
description: >-
  Use this skill whenever the user wants to write, add, or scaffold API automation test cases
  in the gopay backend-tests repo, specifically under gopay/src/test/java/userJourneyTests/userspend/
  (or a similar userJourneyTests subtree). Trigger this any time the user gives a scenario
  description plus a target package/folder and asks for a new test case, a new test class, or a
  new feature folder for an API, even if they do not say skill or name the pattern explicitly.
  Also use it when the user references MiniAppClient, MiniAppHelper, ServiceEndpoint,
  RequestBody or ResponseBody POJOs, or asks to follow the miniapp/parking test pattern. This
  skill knows the exact layered convention (Endpoint to RequestBody/Response POJOs to Client to
  Helper to TestNG test class) used across this repo and should be consulted before writing any
  new Java test file here.
---

# Gopay API Automation Test Writer

**Prerequisite:** read `.claude/skills/backend-automation/SKILL.md` first (or `.cursor/skills/backend-automation/SKILL.md` — same file) if you haven't already this task. It defines the common module-identification, local-framework-discovery, search-before-create, never-invent-data, and compile-check workflow. This file only covers what's specific to gopay's REST/miniapp path on top of that. **If the target is `gopay/src/test/java/paymentTooling/**` (OMS/Boomerang/Emoney/PRS/Subscription Engine — the gRPC/proto path) rather than `userJourneyTests/userspend/**`, this file does not apply** — read `gopay/.gitlab/skills/qa-intern/qa-intern.md` and its `playbooks/` instead; that's a different, gRPC-based paradigm this file doesn't cover.

This repo (`gopay/src/test/java/userJourneyTests/userspend/**`) follows a strict layered
convention for API tests, most visible in the `miniapp` and `parking` packages. The point of
this convention is separation of concerns: a test method should read like a business scenario
("given an unlinked user, calling get-profile returns 401"), while all the HTTP/serialization
plumbing lives in reusable layers underneath. When adding new tests, match this shape rather
than writing ad-hoc RestAssured calls inside the test method — that's what keeps 40+ existing
test classes consistent and lets Helper/Client methods get reused across scenarios.

Read `references/templates.md` for full, copy-pasteable code templates of every layer
(Endpoint, RequestBody, Response, Client method, Helper method, Test class) before writing
code — it has more complete examples than what's summarized below.

## Inputs to gather from the user first

Before writing anything, get clear on:
1. **Target folder/package** — e.g. `gopay/src/test/java/userJourneyTests/userspend/miniapp/<feature>`
   or a brand-new folder under `userspend/<domain>/<feature>`. This tells you whether you're
   adding to an existing feature (reuse Helper/Client) or creating a new one (need new
   Endpoint/RequestBody/Response/Client-method/Helper-method too). Always required.
2. Whether there's an existing curl/API contract (URL, method, headers, request/response
   shape) or an existing sibling feature to base the new endpoint on. If the user has a curl
   command or Swagger/OpenAPI snippet, use it directly to fill in URL, method, headers, and
   body/response fields. Always required.
3. **Scenarios** — the list of test cases to cover (happy path, validation errors, auth
   failures, edge cases). This can arrive in either of two forms:
   - An explicit case list (e.g. pasted from BrowserStack/TestRail/Zephyr, one ID/title/type
     block per case) — turn each block into one `@Test` method directly, using the given ID
     for `testCaseIds`.
   - **Acceptance criteria from a PRD (optional)** — a plain paste of acceptance-criteria
     bullets or a paragraph from a PRD/spec doc, with no test-case IDs attached. When this is
     what you get instead of (or alongside) an explicit case list, read through the criteria
     and derive one scenario per distinct behavior/condition called out (each "should"/"must"/
     "when X then Y" statement is usually one scenario). Restate the derived scenario list back
     to the user briefly before writing code if the acceptance criteria are ambiguous or could
     be split multiple ways — don't silently invent scenarios that aren't implied by the text.
     Since PRD acceptance criteria won't carry a real TestRail case ID, leave the `testCaseIds`
     placeholder clearly marked (see the TestRail rule under "Conventions to always follow")
     and tell the user it needs a real one.
   If the user only gives one scenario, ask if there are adjacent ones worth covering in the
   same class (e.g. unauthorized, invalid input, not-found).

If any of this is missing and can't be inferred by inspecting the target folder, ask —
don't guess at endpoint URLs or auth requirements.

## The layered flow (how a test actually calls an API)

```
Test method (@Test)
   -> Helper method (business-level convenience, builds request body from simple args)
       -> Client method (4-line pattern: build Endpoint, RequestHandler().processRequest(),
                          .as(ResponseClass), setHttpStatusCode, return)
           -> Endpoint class (url/method/headers/params/body — extends BaseEndpoint or
                               implements IServiceEndpoint directly)
               -> RequestHandler (shared, don't touch — the only place RestAssured is called)
```

Assertions happen back in the test method, directly against the returned Response POJO,
using `org.testng.Assert` (`assertEquals`, `assertTrue`, `assertNotNull`, ...), e.g.:

```java
Assert.assertEquals(response.getHttpStatusCode(), HttpStatus.SC_OK, "Status code should be 200");
Assert.assertTrue(response.isSuccess(), "Response should be successful");
Assert.assertEquals(response.getErrors().getCode(), SOME_ERROR_CODE, "...");
```

## Case 1: Adding a test case to an EXISTING feature

If the target folder already has a `<Feature>Tests.java` class (or a Helper/Client method
already exists for the API you need):

1. Open the existing test class and follow its exact conventions (imports, `@BeforeClass`/
   `@BeforeMethod` fixture pattern, `groups = {Categories...}`, `@TestInfo(...)`).
2. Add one new `@Test` method per scenario, named `verify<Behavior>` (camelCase, descriptive
   — e.g. `verifyGetProfileAPIForUnLinkedUser`).
3. Reuse the existing Helper method. Only touch the Client/Endpoint/POJOs if the scenario
   needs a request variant they don't already support (e.g. a missing optional field) — in
   that case extend the existing Helper with an overload rather than duplicating the Client
   method.
4. If a scenario needs new fixture values (tokens, IDs, expected error text), add constants to
   the domain's test-data classes (e.g. `MiniApp.java` and its QA counterpart, or
   `Parking.java`) rather than hardcoding literals in the test.

## Case 2: Adding a brand-new API/feature

If there's no existing Client method for the API yet, build all layers, in this order:

1. **Endpoint URL** — add a `public static String <name> = String.format(...)` constant to
   `GopayProperties.java` under the relevant domain comment block.
2. **Endpoint class** — new package `apis/gopayAPIs/<domain>/<feature>/`, class
   `<Feature>Endpoint` extending `BaseEndpoint<T>` (reuse its default headers if the API is a
   standard customer-facing call) or implementing `IServiceEndpoint` directly for anything
   with bespoke headers/auth. Override `url()`, `httpMethod()`, and whichever of
   `headers()`/`pathParameters()`/`queryParameters()`/`body()` differ from the base.
3. **RequestBody POJO** (if the call has a body) — `<Feature>RequestBody` (or `...Request`,
   whichever suffix the sibling files in that package already use), Lombok `@Builder` (or
   `@SuperBuilder` if it needs to extend another builder), `@Getter @Setter`, and
   `@JsonIgnoreProperties(ignoreUnknown = true)` on every nested static class too.
4. **Response POJO** — `<Feature>Response` extending `BaseResponse<Data, Errors>`, with nested
   static `Data`/`Errors` classes. Check whether the API's error field is a single object or a
   list (`List<Errors>`) before assuming — miniapp and parking differ here — and match whatever
   the actual API contract returns.
5. **Client method** — add to `MiniAppClient.java` (or the shared `CustomerAdapterClient.java`
   for parking-style domains, or a new `<Domain>Client.java` for a genuinely new domain).
   Follow the exact 4-line pattern shown in `references/templates.md` — don't skip the
   `setHttpStatusCode` line, tests depend on it.
6. **Helper method** — add to `MiniAppHelper.java` (or write a `<Feature>Builder.java` inside
   the test tree if following the parking convention, which has no dedicated Helper). Either
   thin-delegate to the Client (simple GETs) or assemble the RequestBody from primitive args +
   shared constants before delegating (POSTs with nested bodies).
7. **Test class** — new file `userJourneyTests/userspend/<domain>/<feature>/<Feature>Tests.java`,
   extending `testBase.TestBase`, with `@BeforeClass(alwaysRun = true)` (or `@BeforeMethod` if
   fixtures must be fresh per test, as parking often needs for QR codes) wiring up
   Helper/Client + any test customer via `customerHelper.getCustomer(CustomerGroup.X)`. One
   `@Test` per scenario as in Case 1.
8. If no `Categories.kt` constant exists for this domain/tag yet, add one rather than using an
   ad-hoc string literal in `groups = {...}`.

## Conventions to always follow

- **TestNG**, not JUnit: `org.testng.annotations.Test/BeforeClass/BeforeMethod`,
  `org.testng.Assert`.
- Every `@Test` method carries a `groups` array (domain category, smoke-or-regression
  category, country code) and a `@TestInfo` annotation with a real TestRail case ID, for
  example:
  `groups = {Categories.MINI_APP, Categories.MINI_APP_SMOKE, Countries.ID}` and
  `@TestInfo(projectId = ..., suiteId = ..., owner = ..., testCaseIds = {"4900174"})`.
  If you don't have a real TestRail case ID, leave a clear placeholder and tell the user it
  needs one — don't invent a fake-looking ID.
- If this repo has an `AI_GENERATED` category constant (check `Categories.kt`), add it to the
  `groups` of any test class you write via this skill, so these are identifiable later.
- Method names: `verify<Scenario>`, descriptive, one behavior per test.
- POJOs: Lombok (`@Getter @Setter @Builder`/`@SuperBuilder`) + Jackson
  (`@JsonIgnoreProperties(ignoreUnknown = true)`) on every class, including nested statics.
- Package-to-folder mapping is a direct 1:1 (standard Maven/Gradle layout) — a new package
  `userJourneyTests.userspend.foo.bar` lives at
  `gopay/src/test/java/userJourneyTests/userspend/foo/bar/`.
- Don't call RestAssured directly in test/Helper/Client code — always go through
  `RequestHandler().processRequest(...)`, which is the shared chokepoint for logging, retries,
  and cURL capture on failure.
- Before inventing a naming/suffix choice (e.g. `Request` vs `RequestBody`), check what
  sibling files in the same target package already use, and match them — consistency within
  a package matters more than a universal rule.

## After writing the code

Eyeball import correctness and that every abstract method from `IServiceEndpoint`/`BaseEndpoint`
is implemented. For the compile-check command and the reused-vs-created summary, see the common
skill (`./gradlew :gopay:compileTestJava`). Real customer/test-data provisioning if `CustomerGroup`
needs a new enum value lives outside this repo — flag it, don't invent a value.
