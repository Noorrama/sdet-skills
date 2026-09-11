---
name: gbt-module-driver-platform
description: Authoritative module profile for the driver-platform module of gojek-backend-tests (GBT). Inlined as fixed grounding during codegen so generated tests strictly mirror this module's real structure, dependency graph, and coding style. Covers the layered Endpoint->Client->Controller->Response->Test pattern, test base hierarchy, assertions, data providers, async/retry, DB and JSON-schema validation, and cross-module driver/booking creation.
disable-model-invocation: true
---

# MODULE PROFILE — driver-platform

This is the authoritative description of the `driver-platform` GBT module. When
generating tests for this module, follow it STRICTLY and prefer it over patterns
inferred from live exemplars. It is Java 17 + TestNG + REST Assured (wrapped by
the internal `restidioms` framework), Lombok POJOs, Jackson, AssertJ, Failsafe.

## Layered pattern (every new API touches the same layers)

```
Test (src/test/java/tests/<svc>)        extends <Svc>TestBase -> DriverServiceTestBase/DriverPlatformTestBase
  -> Controller (src/main/java/controller/<Svc>)   @SneakyThrows, deserialize, setHttpStatusCode
       -> Client (src/main/java/client/<Svc>)      new RequestHandler().processAPIRequest(endpoint)
            -> Endpoint (src/main/java/entities/<svc>/endpoint)  implements IServiceEndpoint
  -> Response POJO (src/main/java/entities/<svc>/response)  extends BaseResponse, Lombok, @JsonIgnoreProperties
  -> DataProvider (src/test/java/dataProvider)  + testData props + ConfigLoader
  -> Assertions (src/test/java/assertions/<Svc>Assertions)  SoftAssert / Assert / ObjectComparator
```

## Endpoint existence & reuse protocol (run this BEFORE writing the test)
1. **Search first, exact match.** Look for the exact API under test (same HTTP
   method + same path, allowing path-param placeholders like `{driverId}`) in
   EXISTING ENDPOINT MATCHES / the module's `entities/<svc>/endpoint` sources.
   Do not treat a similarly-named or same-feature-area endpoint as a match —
   only an exact method+path match counts.
2. **Match found -> backtrack, don't invent.** From the matched Endpoint class,
   trace forward to its Client (the class whose method constructs and calls
   that Endpoint via `RequestHandler`) and its Controller (the class whose
   method calls that Client method and deserializes the response). Use those
   EXACT class names and method signatures in the generated test — never
   fabricate a plausible-sounding Controller/Client method name. If a step in
   the chain (Endpoint found but no Client/Controller wraps it yet) is missing,
   generate ONLY the missing layer(s); do not regenerate layers that exist.
3. **No match -> generate all layers, correct package.** If no exact match
   exists anywhere in the module, do not call a nonexistent method. Instead,
   generate the full Endpoint -> Client -> Controller chain for the new API,
   placed under this module's real package roots (`entities/<svc>/endpoint`,
   `client/<Svc>`, `controller/<Svc>`, matching an existing `<svc>` if the
   service already has other endpoints, otherwise the closest analogous
   service directory) — then the test on top of them.
4. **Same module only.** The search in step 1 is scoped to THIS module. An
   endpoint that exists in a different Gradle module is not a match — do not
   import/call across modules; treat it as "no match" and follow rule 3.

## Strict coding-style rules
1. Reuse, never reinvent. If an endpoint/client/controller/response/builder/
   assertion/data-provider already exists for the API, REUSE it and add only the
   new test method(s). Mirror the closest existing `<Svc>` slice. (See the
   Endpoint existence & reuse protocol above for HOW to confirm "already exists.")
2. HTTP only through the framework: `Endpoint implements IServiceEndpoint`
   (override `url()/httpMethod()/userType()/headers()/body()/pathParameters()/
   queryParameters()`); `Client` runs `new RequestHandler().processAPIRequest(endpoint)`;
   `Controller` is `@SneakyThrows`, calls `response.deserialize(X.class)` then
   `x.setHttpStatusCode(response.getStatusCode().getCode())`.
3. URLs come from `properties.DriverPlatformPropertiesInternal`; hosts via
   `ConfigurationReader`; secrets via `AEPFortknoxReaderHelper`. NEVER hardcode
   URLs, hosts, tokens, or environment values.
4. Response POJOs `extends entities.BaseResponse` (gojek-commons), `@Getter
   @Setter @JsonIgnoreProperties(ignoreUnknown = true)`, with nested `static`
   sub-classes for nested JSON.
5. Test class extends the service base (`<Svc>TestBase`), declares
   `private static final Logger log`, and a controller field. Each `@Test` has
   `groups = {<Svc>TestCategories.*}` + `description`, and
   `@TestInfo(projectId/suiteId/testCaseIds/owner = TestRailConfig.*)`.
6. Assertions: reuse the existing `assertions/<Svc>Assertions` (SoftAssert for
   multi-field, ending in `assertAll()`); hard TestNG `Assert.*(actual, expected,
   message)` with a MANDATORY message for status/success; `BaseResponse
   .assertHttpStatusToBe(int)` / `getHttpStatusCode()` for status.
7. Never assert immediately after an async write. Wrap flaky read+assert in
   `Failsafe.with(retryPolicyForFailure).run(() -> { call; assert; })` and/or a
   fixed `TestHelper.wait(ms)`; capture results via `AtomicReference`.
8. Create drivers/customers/bookings ONLY through the shared helpers
   (`BookingHelper.getDesiredStateDriverResponse(type)`, `DriverStateManager
   .setupDriver(...)`, `BookingController.createBooking(row)`), never bespoke
   setup. Tear down anything you create (`finally`/`@AfterMethod`/`@AfterSuite`).
9. JSON-schema validation belongs in the controller
   (`response.validateJsonSchema("schema/<svc>/X.json")`), not the test.
10. Package = directory: tests under `src/test/java/...`, helper/client/endpoint
    under `src/main/java/...`, flat package roots (`tests`, `controller`,
    `client`, `entities`, `assertions`, `dataProvider`, `builder`, `helper`).

## Dependency graph (summary)
- Gradle: `:driver-platform` -> `:gojek-commons`, `:transport`, `:gofood`,
  `:go-logistics` (with exclusions), `:cartography`, `:gomart`; external libs
  `json-schema-validator` (networknt 1.0.73), `assertj` 3.22.0, `failsafe`
  (net.jodah 2.4.4), zxing, `kafka-protobuf-serializer`, `common-integrations`.
- Base hierarchy: `<Svc>TestBase` -> `DriverServiceTestBase`/`DriverServiceBaseTests`
  -> `DriverPlatformTestBase` (suite `@BeforeClass`/`@AfterSuite`). Most bases
  `implement ITest` for dynamic ReportPortal names.
- Data graph (setup): `getDesiredStateDriverResponse` (Test-Data-Pool-first,
  create-fallback) -> `DriverStateManager.setupDriver(profile)` ->
  `BookingController.createBooking(row)` (or `BookingKafkaHelper.publishKafkaTest`)
  -> API under test -> verify (response and/or `<Svc>DbClient` + `<Svc>Assertions`).

For the full Gradle/intra-module/API dependency graphs (mermaid), the complete
Dracarys vertical-slice exemplar, the 12 test patterns with real trimmed
snippets, and the naming/placement tables, see [reference.md](reference.md).
