---
name: transport-api-test-writer
description: >-
  Use this skill whenever the user wants to write, add, or scaffold backend API automation tests
  in the transport module of gojek-backend-tests (transport/src/test/java/**, covering ride-hailing
  booking (rideService/FBON), pickup/dispatch, tracking, driver karma/tipping, profitability/
  payments, GoCorp, and rentals). Trigger this any time the user gives a cURL, endpoint definition,
  or API doc targeting a transport host/path and asks for a new test case, test class,
  Endpoint/Client/Controller/DTO, or feature folder. Also use it when the user references
  TransportController, TransportTestBase, BookingFlowController, BaseApiEndPoint, or
  RSCustomerPool.
---

# transport API Automation Test Writer

**Prerequisite:** read `.claude/skills/backend-automation/SKILL.md` first if you haven't already
this task — it defines the common module-identification, local-framework-discovery,
search-before-create, never-invent-data, and compile-check workflow. This file only covers what's
specific to transport on top of that.

**Note on `transport/README.md`:** it is ~4 years stale (claims Java 1.8/"Gradle 1.8.0_222"; the
module is actually on Java 17 — confirmed via `build.gradle`'s `--add-opens java.base/... //Mandatory
for JDK17` comment and the repo's Gradle 8.3 wrapper). Its service list is still roughly accurate,
but do not trust its build/version claims. This is a live example of "verify documentation before
trusting it" from the common skill.

## Architecture

```
TestNG @Test  →  Flow Controller (controllers.flowControllers.*, orchestrates multiple API calls
                                   using cached state from a prior step, e.g. BookingFlowController)
                     →  API Controller (controllers.apiControllers.*, one per domain, e.g.
                                         BookingApiController — reached directly by tests that don't
                                         need orchestration)
                         →  Client (clients.*, mirrors serviceEndpoints/ by vertical; some call
                                     endpoint.call() directly, bypassing clients.BaseClient)
                             →  Endpoint (restidioms.serviceEndpoints.*, extends
                                          restidioms.BaseApiEndPoint<T>, which implements
                                          IServiceEndpoint and does the RestAssured call itself
                                          inside call())
```

Every test class extends `testBases/TransportTestBase.java`, which itself extends
`controllers.TransportController` — a Lombok `@Delegate`-based aggregator of ~30 API controllers.
This means test methods call controller methods **unqualified** (e.g. `makeBooking(...)`,
`v2Estimates(...)`) — they're delegated through inheritance, not imported. Even the framework's
own code comments flag at least one delegated field (`TransportControllerUtil`) as something that
"should not be consumed outside TransportController... only if the use case outweighs any other
alternative approach" — be cautious about adding new delegated fields to this god-object rather
than calling the more specific controller/client directly.

## Local Client/Endpoint/Controller pattern

- `clients.BaseClient` (a thin RestAssured `RequestSpecification` wrapper) exists but is a
  **minority/legacy pattern** — most Clients (e.g. `V1MakeBookingClient`) bypass it entirely and
  call `new XyzApiEndPoint(request).call()` directly, since `BaseApiEndPoint.call()` does the
  RestAssured dispatch itself. Check the sibling Client before assuming either shape.
- Endpoints extend `restidioms.BaseApiEndPoint<T>` (`url()`, `httpMethod()`, `userType()`), which
  itself `implements restidioms.security.core.template.IServiceEndpoint` — confirming the shared
  interface convention holds here, just via this module's own abstract base.
- Request construction for complex flows goes through `builders/BaseBuilders/ApiRequestBuilder`
  and `ApiRequestHeadersBuilder` (auth, `X-App-Version`, `Gojek-Service-Area`, `Gojek-Country-Code`,
  `Gojek-Timezone`, etc.) rather than being built inline in the Controller.

## Request/response conventions

- Predominantly `@Getter`/`@Setter` (not `@Data`); `@Builder` on request-body builders.
- `@JsonIgnoreProperties(ignoreUnknown = true)` is standard on response DTOs (extends
  `entities.BaseResponse`). Some request fields use `@JsonProperty(...)` or
  `net.minidev.json.annotate.JsonIgnore` for computed-but-not-serialized fields.
- **Response DTOs commonly bundle their own assertion helper methods** (e.g.
  `V1MakeBookingResponse.assertErrorInvalidPayment()`, `.assertErrorConcurrentBooking()`) — check
  whether the response type you're using already has one before writing an inline assertion or a
  separate helper class.
- A **divergent legacy pattern** also exists: separate `SuccessResponse`/`ErrorResponse`
  (and even `Error401Response`) classes per HTTP outcome (`entities/BFFDriverProfile/*`,
  `entities/DriverTransactions/*`), instead of one response class with an `errors` list. Match
  whichever shape the specific feature area you're extending already uses.

## Authentication

- Bearer token formatting: `restidioms.security.utility.RequestHandler.getBearerTokenString(token)`
  (external, from the shared dependency) — used via `ApiRequestHeadersBuilder().withAuthorization(...)`.
- Customer pool: `testData.customers.customers.RSCustomerPool` (borrow/return via
  `statemanager.RHSBorrowManager`) — don't create a fresh customer per test if a pooled one fits.
- **Driver login here intentionally diverges from the shared login helper** — `LoginApiController.loginDriver`'s
  own code comment says: *"Implementation here is optimised for RHS and hence should not be
  directly swapped with loginDriver from gojek-commons LoginController."* Don't "fix" this by
  swapping in the gojek-commons version; it's a deliberate divergence, not an oversight.

## Test-data conventions

- **Dominant pattern**: `dataProviders.testIterator.TransportFlowsDataProvider` (`@DataProvider(name = "transportFlowsGenerator")`),
  driven by reflection-visible custom annotations (`@TestData`, `@FilterBy`, `@Sampling` from
  `dataProviders/annotations/*`) rather than a literal `Object[][]` — read the target test method's
  annotations to understand what data it'll actually receive.
- Secondary: CSV-driven `@DataProvider`s reading fixtures from `src/test/resources/testData/**`
  cross-checked against golden JSON under `src/test/resources/verificationData/**`.
  Fixed/small case spaces use literal `Object[][]` arrays directly (e.g.
  `dataProviders.serviceTypes.ServiceTypesDataProvider`).

## Validation patterns

- Negative assertions check `getHttpStatusCode()` plus `getErrors().get(0).getCode()`/`.getMessage()`
  directly on the response DTO — never status code alone for a business-rule failure.
- **Both `org.junit.Assert` and `org.testng.Assert` appear in sibling test classes in the same
  package** with no enforced standard — match whichever the specific file you're editing uses; a
  `SoftAssert` field is also available on `TransportTestBase` if you want to collect multiple
  failures.
- **Three separate hand-rolled async/retry loops solve overlapping problems** — don't invent a
  fourth. Pick the one matching what you're actually waiting for:
  `BookingApiController.waitUntilFBONState`/`waitUntilBookingStatus` (business-state polling, `Thread.sleep`-based),
  `clients.bookingExperience.fbon.V1BookingDetailsClient.executeWithRetry` (HTTP-status-only retry),
  `db.paymentProcessor.PaymentProcessorDBClient.getAndWaitLogsByOrderNumber` (DB-row-count polling).
- **Some DB-log assertions are commented out in real tests** (`GopayCoinsPaymentTests.java` has
  ~15 lines of commented-out `PaymentProcessorDBClient` assertions per method) — don't copy the
  surrounding pattern assuming the assertion call itself is active; check.

## Canonical tests (read these directly, don't guess)

- `src/test/java/tests/regression/bookingExperience/rideService/makeBooking/MakeBookingTest.java`
  + `controllers/flowControllers/BookingFlowController.makeBooking` — the best example of the
  orchestrated multi-controller flow pattern, with 3 distinct negative cases
  (invalid payment / insufficient balance / concurrent-booking-limit) in one file.
- `src/test/java/tests/regression/bookingExperience/rideService/drivernotfound/DriverNotFoundTest.java`
  + `controllers/apiControllers/FBONApiController.v1BookingDetails` — canonical example of the
  business-state polling pattern (`waitUntilFBONState`).

## Module-specific pitfalls

- Don't assume `clients.BaseClient` is used — most Clients bypass it.
- Don't "fix" `LoginApiController.loginDriver`'s divergence from the shared login helper — it's
  intentional.
- Don't add a 4th hand-rolled retry loop — reuse one of the three that already exist for the
  matching layer (business-state / HTTP-status / DB-row-count).
- Don't assume `org.junit.Assert` or `org.testng.Assert` is "the standard" — match the file.

## Legacy/dead patterns that must not be copied

- `clients.BaseClient` as a universal base — most Clients don't use it; `BaseApiEndPoint.call()`
  doing the dispatch directly is the more common shape.
- Separate `SuccessResponse`/`ErrorResponse`/`Error401Response` DTOs per outcome
  (`entities/BFFDriverProfile/*`, `entities/DriverTransactions/*`) — the single-response-with-`errors`-list
  shape (`V1MakeBookingResponse`) is the more current convention; only match the split-DTO shape if
  the specific feature area you're extending already uses it.
- Commented-out DB-log assertions in `GopayCoinsPaymentTests` and similar files — inert, not a
  template to restore without checking why it was disabled.
