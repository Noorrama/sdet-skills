# go-logistics Architecture Deep Dive

This is the detailed reference behind `SKILL.md`. Read the relevant section before touching an
unfamiliar corner of the framework. Every claim here was verified by reading the actual source
in `go-logistics/` (plus its two external dependencies, `aep-backend-core` and
`gojek-test-integrations`, both checked out as sibling repos on this machine) — not inferred
from naming alone.

## 1. Module shape

- Gradle module, Java 17, TestNG runner, partial Kotlin (`src/main/kotlin/{common,goSend,
  goShop}/**` — framework code only; **there is no `src/test/kotlin`**, every `@Test` class in
  the repo is Java, even for the verticals that have Kotlin framework code underneath).
- No `testng.xml` suite file. Tests are selected purely by TestNG **group** filters passed as
  `-Dtag=<group>` to Gradle (see §6).
- `README.md` (repo root) and `Refactoring.md` (repo root) are both worth reading directly —
  they're short and this document quotes/expands on both.
- `go-logistics/{KILAT,GOSEND,TMS,GOBOX}_API_SCHEMA.md` and `*_API_TEST_MAPPING.md` (+
  `api-schema-viewer.html`) are pre-built endpoint/test/DTO indexes from a prior scanning effort
  — check the relevant one before assuming an endpoint is untested.

## 2. The call chain, layer by layer

```
Test (TestNG) -> Controller -> Client -> Endpoint -> RequestHandler (external) -> RestAssured -> HTTP
```

### Endpoint layer

Two live Java conventions coexist (a third, oldest, is described for recognition only):

**`IServiceEndpoint` implementer, explicit** — every method defined by hand:
```java
// src/main/java/endpoint/rhs/RHSCustomerEndPoint.java
public class RHSCustomerEndPoint implements IServiceEndpoint {
    private final ApiRequest apiRequest;
    public RHSCustomerEndPoint(ApiRequest apiRequest) { this.apiRequest = apiRequest; }
    @Override public String url() { return LogisticsProperties.borrowCustomerUrl; }
    @Override public HttpMethod httpMethod() { return HttpMethod.POST; }
    @Override public UserType userType() { return UserType.CUSTOMER; }
    @Override public List<Param> queryParameters() { return apiRequest.queryParameters(); }
    @Override public List<Param> pathParameters() { return apiRequest.pathParameters(); }
    @Override public List<Param> headers() { return apiRequest.headers(); }
    @Override public RequestBody body() { return apiRequest.body(); }
}
```
Or with an abstract vertical base doing some of this once
(`src/main/java/endpoint/store/BaseStoreEndpoint.java`, `endpoint/tms/DriverBaseEndPoint.java`
fixing `userType()`), so concrete endpoints only override `url()`/`httpMethod()`/`body()`.

**Oldest style, still alive** — endpoint takes the raw access token directly and builds its own
`Authorization` header (`entities/calculateBookingV1/CalculateBookingV1Endpoint.java`):
```java
public CalculateBookingV1Endpoint(String access_token, CalculateBookingV1RequestBody body) {...}
@Override public List<Param> headers() {
    return List.of(new Param("Authorization",
        restidioms.security.utility.RequestHandler.getBearerTokenString(access_token)));
}
```
Recognize this pattern but don't write new endpoints this way — thread a shared `ConsumerHeaders`
object instead (see §4).

**Kotlin (`BaseConsumerEndpoint`, only under `goShop/endpoints/**`)** — external base class
supplies sane customer-GET defaults, subclasses override only what differs:
```kotlin
class NearByMerchantsEndPointV1(headers: ConsumerHeaders) : BaseConsumerEndpoint(headers) {
    var pagesize: Int = 10
    var lat: String = ""
    override fun url() = GoShopUrls.v1NearByMerchants
    override fun httpMethod() = HttpMethod.GET
    override fun queryParameters(): MutableList<Param>? =
        arrayListOf(Param("pagesize", pagesize.toString()), Param("lat", lat) /* ... */)
}
```
Params here are mutable `var`s set by the **Client** after construction, not passed through the
constructor. POST bodies are always pre-serialized to a JSON `String` by a dedicated
`*SerializerVx` object before being wrapped in `RequestBody(String::class.java, body)` — see
`references/modern-kotlin-pattern.md`.

### URL / path-param resolution — `LogisticsProperties`

`src/main/java/properties/LogisticsProperties.java` is a flat registry of
`public static final String` URL constants, built as `String.format("%s/path/{param}", host)`
— path params are literal `{name}` placeholders, resolved later by the external `RequestHandler`
against whatever `Param`s `pathParameters()` returns with matching keys:
```java
public static final String driverReject =
    String.format("%s/v1/dispatch/bookings/{id}/reject", kilatDispatchInternalConsignorHost);
```
Host constants themselves come from `LogisticsPropertiesReader.java`, which resolves an
environment-specific `.properties` file:
- `System.getProperty("env")`, default `"integration"` (`getEnvName()`).
- If `System.getenv("INFRA")` is unset/blank or not one of `integration|tencent|staging`, the
  reader silently rewrites `logistics-integration.properties` -> `logistics-qa.properties`
  (`getUpdatedPropertiesFileName`) — a real gotcha if you're trying to reproduce a specific CI
  environment locally and wondering why host values look different than expected.
- If `-DusePropsOverrides=true` (the Gradle default), an `overrides/<env>.properties` file is
  layered on top (`src/main/resources/overrides/integration.properties` — 3 keys today).
- **No country switching happens at this layer.** `System.getProperty("country")` is never read
  in `src/main`. Country flows explicitly through method args and enums (`Country`,
  `CountryAndLanguage`) — see §5.

The Kotlin side does **not** use `LogisticsProperties`/env switching at all:
- `goSend/endpoints/GoSendUrls.kt` — hardcoded integration-only host string literals.
- `goShop/endpoints/GoShopUrls.kt` — loads a **static JSON file** via Moshi
  (`src/test/resources/goShop/testData/pools/goShopProperties.json`, 3 fields: consumer host,
  abacus endpoint, vouchers endpoint) — also integration-only, no env parameterization.
- Don't extend either Kotlin URL registry expecting it to respect `-Denv` — it won't. If a new
  Kotlin endpoint needs environment switching, either read `LogisticsProperties` directly from
  Kotlin (it's a plain Java class, fully callable) or flag the gap to the user.

### The TMS gateway-prefix quirk (read before adding any TMS endpoint)

TMS is reachable through two different hosts with two different path shapes for logically the
same route family, and picking the wrong pair 404s:
```java
// LogisticsProperties.java — direct-to-internal-service host, "/tms/internal/..." required
public static final String tmsInternalV1RouteUrl = String.format("%s/tms/internal/v1/routes", tmsInternalHost);
public static final String tmsInternalV3RouteUrl = String.format("%s/tms/internal/v3/routes", tmsInternalHost);
// gateway-fronted host, NO "internal" segment
public static final String routeV2Url = String.format("%s/tms/v2/routes", gojekDriverHost);
public static final String routeV3Url = String.format("%s/tms/v3/routes", gojekDriverHost);
```
`tmsInternalHost` is the raw internal service DNS name; `gojekDriverHost` is the externally
routable, gateway-fronted host (used by driver-app-facing flows). The same quirk is mirrored a
second time in `endpoint/tms/DriverUrlConstant.java` (direct-host constants all carry
`/tms/internal/...`; a `DRIVER_KONG_URL` gateway constant exists but has no matching
non-`/internal/` path constants defined for it yet — incomplete), and a third time, inconsistently,
in the dormant Kotlin `TMSHosts` class in `GoSendUrls.kt` (most fields prefix `/tms/internal/...`,
but `shipmentBundleRoute` deliberately omits it, and `driverPerformance` ignores the whole
host-resolution scheme and points at an unrelated hardcoded host). **When adding a new TMS
endpoint: check whether the analogous existing route in `LogisticsProperties` uses
`tmsInternalHost`+`/internal/` or `gojekDriverHost` without it, and copy that exact pairing** —
don't assume either is universally correct.

### Client layer

External shared base (`gojek-commons`, dependency, not in this repo):
```java
public class BaseClient {
    protected Response call(IServiceEndpoint endpoint) { return new RequestHandler().processRequest(endpoint); }
    protected <T extends BaseResponse> T call(IServiceEndpoint endpoint, Class<T> cls) {
        Response response = new RequestHandler().processRequest(endpoint);
        T body = response.as(cls);
        body.setHttpStatusCode(response.getStatusCode());
        return body;
    }
    // + get/put/patch/delete helpers, all through processRequest -> raw RestAssured Response
}
```
This is the **legacy** shape — `.as(Class)` deserialization by hand, raw `Response`. It still
backs a lot of existing code (`GoShopV1Client extends BaseClient`), but for anything new, prefer
the `processAPIRequest` shape instead, which several existing Java clients already use without
going through `BaseClient` at all:
```java
// src/main/java/clients/tms/TMSClient.java
public class TMSClient {
    RequestHandler handler = new RequestHandler();
    ConsumerHeaders headers;
    public TMSClient(CountryAndLanguage countryAndLanguage) {
        this.headers = new ConsumerHeaders("", countryAndLanguage);
    }
    public IAPIResponse createShipmentBundle(ShipmentBundleRequestDTO requestDTO) {
        CreateShipmentBundleEndpoint endpoint = new CreateShipmentBundleEndpoint(requestDTO, headers);
        SecurityHelper.runSecurityScanIfRequired(endpoint);
        return handler.processAPIRequest(endpoint);
    }
}
```
`processRequest` and `processAPIRequest` are two entry points on the *same* external
`RequestHandler` class (`restidioms.security.utility.RequestHandler`, in `aep-backend-core`) —
they both do the identical RestAssured request-building/HMAC-signing/retry/logging work
underneath (`makeRequest` -> `formRequestSpecification` -> RestAssured `.get/post/put/...`); the
only difference is the return type: `processRequest` -> raw `Response`, `processAPIRequest` ->
`IAPIResponse` (a `RestAssuredResponse` wrapping the same `Response`, adding `.deserialize(Class)`
[Jackson], `.deserializeKt(Class)` [Moshi], `.getStatusCode()`, `.getResponseText()`). Always
prefer `processAPIRequest` for new code — it's a strict superset of what `processRequest` gives
you, and it's what every negative/error-path assertion in this codebase already relies on for a
clean `response.getStatusCode().getCode()` check.

`SecurityHelper.runSecurityScanIfRequired(endpoint)` (Java) / the private
`runSecurityScanIfRequired` method seen in Kotlin clients (gated on
`System.getProperty("toBeRunForScan") == "true"`) is an opt-in security-scan hook (pipes the
request through an internal scanner, "Byomkesh"). It's safe to include for consistency with
sibling methods, and a no-op unless that system property is set.

### Controller layer

Flat package, `src/main/java/controller/` (no per-vertical subfolders) — one class per
domain/feature (`ShipmentController`, `GoShopController`, `DispatchController`,
`DirectIntegrationController`, `DocumentUploadController`, ...). A Controller method's job is:
build/accept the request DTO, call the Client, deserialize the response into a typed DTO, return
it. Per `Refactoring.md`, assertions should **not** live here (a lot of legacy code violates this
— don't copy that part):
```java
// Refactoring.md's own before/after example
// Before:
fun getBookingDetails(orderNo: String): Response {
    val endpoint = GetBookingDetailsEndpoint(headers, orderNo)
    return requestHandler.processRequest(endpoint)
}
// After:
fun getBookingDetails(orderNo: String): IAPIResponse {
    val endpoint = GetBookingDetailsEndpoint(headers, orderNo)
    return requestHandler.processAPIRequest(endpoint)
}
```
And separately, for deserialization at the call site:
```kotlin
// Before: baseHelper.serializer.adapter(ConsumerGetBookingResponse::class.java).fromJson(response.responseText)!!
// After:  response.deserializeKt(ConsumerGetBookingResponse::class.java)
```
For Java DTOs (the default), the equivalent is `response.deserialize(YourResponseDto.class)`
(Jackson, throws checked `JsonProcessingException` — wrap it, don't swallow it silently with a
bare `e.printStackTrace()` the way some legacy controllers do).

### DTO layer

See `references/templates.md` for full copy-paste examples. Summary of the conventions:

- **Java** (`src/main/java/dto/**`, dominant: 634 `@Data` classes vs. 8 `@Builder` classes):
  Lombok `@Data`, `@JsonIgnoreProperties(ignoreUnknown = true)` at the class level so unexpected
  server fields never break a test, `@JsonProperty("snake_case_name")` per field wherever the
  JSON key differs from the Java field name or would collide with a Java keyword (e.g. a JSON
  `"package"` field becomes a Java field annotated `@JsonProperty("package")` with a non-keyword
  name like `mypackage`). Response DTOs conventionally also carry `HttpStatuses statusCode` and
  `HashMap<String,String> responseHeaders` fields directly — the response POJO doubles as a thin
  HTTP envelope, not a pure body-shape object. Reach for Lombok `@Builder` only for objects
  constructed once from scratch in code (Alice/allocation-service payloads, driver-creation
  payloads) — not for anything loaded from a JSON template and then mutated, where plain setters
  are the existing convention.
- Gson (`@SerializedName`/`@Expose`) imports appear in ~13 files but are **dead** — unused on
  the actual fields, a leftover from an earlier era. Jackson (`ObjectMapper`,
  `Utilities.convertJsonToDto`) is the real, live Java serializer. Don't add new Gson
  annotations expecting them to do anything.
- **Kotlin** (`goShop/**` only — `goSend`'s Kotlin tree has no DTOs of its own, it reuses the
  Java `dto/consumer/**` classes): `data class` + Moshi `@JsonClass(generateAdapter = true)` +
  `@Json(name = ...)`. Request-side fields are typically `var` with no default (must be supplied
  at construction or immediately after); response-side fields are nullable with defaults
  (`Int? = null`, `List<X>? = null`) since server responses aren't guaranteed to include every
  field. Nested JSON objects are modeled as nested `data class`es declared *inside* the parent
  type. `@Transient` excludes a field from the generated Moshi adapter. The "builder" for a
  Kotlin request is a hand-rolled fluent class that seeds itself from a JSON template via a
  `*SerializerVx.getBodyFromTemplate()` call, then exposes `setX(...): ThisBuilder` chain methods
  and a final `build()` — it does not use Kotlin's own `data class` `copy()` or any annotation
  magic.

### Serialization core (external, `aep-backend-core`)

```kotlin
// BaseHelper.kt
open class BaseHelper {
    val serializer = Moshi.Builder().add(KotlinJsonAdapterFactory()).build()!!
}
```
```java
// RestAssuredResponse.java — the sole implementation of IAPIResponse
public <T> T deserialize(Class<T> cls) throws JsonProcessingException {
    return new ObjectMapper().readValue(this.responseText, cls);              // Jackson
}
public <T> T deserializeKt(Class<T> cls) throws IOException {
    Moshi serializer = new Moshi.Builder().add(new KotlinJsonAdapterFactory()).build();
    return serializer.adapter(cls).fromJson(this.responseText);               // Moshi
}
```
Rule of thumb: **Jackson `deserialize()` for Java DTOs, Moshi `deserializeKt()` for Kotlin data
classes** — both hang off the same `IAPIResponse` your Client returns.

## 3. Test lifecycle / base class hierarchies

There is no single root `BaseTest`. Four separate chains exist; extend the nearest one rather
than inventing a fifth:

- **TMS**: `tms/base/TMSBaseTest.java` (implements `ITest`, sets a descriptive per-invocation
  test name from the method + case description, pushes a click-stream event in `@BeforeSuite`)
  -> `tms/shipments/ShipmentBaseTest.java` (adds `@DataProvider`s reading JSON case files, plus
  shared helpers like `createOrderWithLatLong`, `setDriverRouteId`) -> `gokilat/tms/route/
  RouteBaseTest.java`, `tms/spmd/TMSShipmentBundleBaseTest.java`, `tms/performance/
  PerformanceBaseTest.java`.
- **GoKilat consignor/store**: an external `helpers.BaseHelper` -> `gokilat/consignor/store/
  booking/BaseHelper.java` (adds `provideConsumer()`, the same `@BeforeMethod` test-naming
  pattern, a `@BeforeSuite` click-stream push) -> `StoreBookingBaseTest.java` (~10
  `@DataProvider`s: `makeBooking`, `cancelBooking`, `bookingDetailByOrderId`, `groupingBooking`,
  distance-bucket cases, ...) -> `CalculatePriceBaseTest.java`, `DirectIntegrationBaseTest`,
  `DriverTippingBaseTest`, `LiveTrackingBaseTest`.
- **GoSend / GoShop / GoBox / Dispatch**: no dedicated intermediate base — these extend
  `helpers.GologisticBaseHelper` (`src/main/java/helpers/GologisticBaseHelper.java`) directly, or
  its empty marker subclass `goSend/GoSendBaseHelper.java`. This is the de facto shared base for
  everything outside TMS/GoKilat-store: `@BeforeMethod` test naming, and — critically — the
  **auth entry point** most tests actually call: `provideConsumer()` /
  `provideConsumerWithPayment(country, paymentType)`, which goes through `LoginHelper` to pull a
  pooled, pre-authenticated consumer. There is no global `@BeforeSuite` login; each test method
  provisions its own consumer on demand.

Read a concrete example from each chain before writing a new test in that vertical:
`tms/shipments/ShipmentTests.java`, `gokilat/consignor/store/booking/StoreBookingTest.java`,
`goSend/consumer/bookings/GetBookingsV12Tests.java`, `goShop/GoShopBookingTest.java`,
`dispatch/DispatchTestsV3.java`.

**Correction worth internalizing**: it's tempting to assume `IAPIResponse` usage correlates with
"newer" folders (goSend/goShop) vs. "legacy" folders (gokilat/tms). It doesn't, cleanly. In
practice, almost every vertical's happy-path assertions still go through a typed-DTO-returning
Controller method, and `IAPIResponse` gets reached for ad hoc, specifically for raw status-code
checks on negative/error paths — in TMS files, GoShop files, Dispatch files, everywhere. The only
place the "modern" pattern is fully, consistently applied end-to-end is the unused Kotlin
`goShop/{clients,controllers}` scaffold described in `references/modern-kotlin-pattern.md`.

## 4. Auth flow

- **Consumer auth is pool-based, not a fresh login call per test.**
  `helpers/LoginHelper.java`/`GologisticBaseHelper.provideConsumer()` first try
  `RSCustomerPool.getCustomerFromAEPTestDataPool(...)` (a shared, pre-authenticated test-data
  pool service), falling back to `RHSClient` "borrow a customer" (`RHSCustomerEndPoint` ->
  `LogisticsProperties.borrowCustomerUrl`) if that pool is exhausted/unavailable.
  `getConsumerFromPoolAndLogin(UserType userType)` picks a random entry from
  `src/test/resources/kilat/testData/userPools/consumers_with_country_codes.json` (keyed by
  `UserType`: blacklisted, pay-later, zero-GoPay-balance, per-country buckets), then resolves a
  bearer token via `UserHelper.returnCustomerToken(phoneNumber)`.
- **Token caching**: `dto/login/TokenCache.java` caches tokens in Redis keyed by phone number,
  and validates liveness not by decoding the JWT but by making a real API call
  (`BookingsController.getCitiesResponseV11("intercity")`) and checking for HTTP 200.
- **Attaching the token**: the shared, current convention is a `ConsumerHeaders(bearerToken,
  CountryAndLanguage)` object built once per Client instance and threaded into every Endpoint
  constructor (`headers.getToken()` read inside header-builder classes as
  `"Bearer " + consumerHeaders.getToken()`). Older code threads the raw access-token string
  through the Endpoint constructor directly instead — recognize it, don't write new code that way.
- **Driver-side auth has two distinct variants** (`endpoint/tms/TmsDriverHeaderBuilder.java`):
  hitting TMS **directly** uses a static, long-lived test JWT under a header literally named
  `token`; hitting TMS **through the Kong gateway** uses a real per-driver
  `Authorization: Bearer <driverContext.getAccessToken()>`. Both also set country-specific
  `X-User-Locale`/`Gojek-Country-Code` headers via a switch on `driverContext.getCountry()`
  (`"indonesia"|"vietnam"|"singapore"`). Pick the variant matching which host you're calling.
- **Country is a parameter, not a system property.** No file in `src/main` reads
  `System.getProperty("country")`. It flows through explicit method args and enums (`Country`,
  `CountryAndLanguage`, `DriverContext.getCountry()` as a lowercase string). The Gradle
  `-Dcountry` flag is consumed at the test-selection/fixture level (which JSON file gets loaded),
  not inside the framework's request-building code.
- Service-to-service auth (Basic-Auth headers, partner client-id/pass-key pairs, an MD5-based
  request-signing scheme for the TikTok-Shop direct-integration API in
  `utilities/SignatureGenerationUtility.java`) appears hardcoded in several header-builder and
  endpoint classes for non-user-facing internal/partner calls. If you need to add a new
  partner/service credential, follow the existing pattern in the sibling file for that
  integration, and flag to the user that any real secret value should move to environment/vault
  injection rather than being committed as a literal — several existing files already have
  committed-looking Basic-Auth/API-key literals that predate that discipline; don't add to them.

## 5. Test data / fixtures

- **JSON templates** (`src/test/resources/<vertical>/templates/**`) are literal example request
  payloads matching a request DTO's shape exactly. Loaded via
  `ReadFile.readFileAsString(path)` + `Utilities.convertJsonToDto(json, Class.getCanonicalName())`
  (Java) or a `*SerializerVx.getBodyFromTemplate()` Moshi call (Kotlin, GoShop only). Some
  helpers do a literal `String.replace("8583426409", realPhoneNumber)` on the raw JSON text
  *before* deserializing, to swap a hardcoded placeholder for a real test value — not a
  `{{token}}` templating engine.
- **DataProvider case files** (`src/test/resources/<vertical>/testData/**`) are JSON arrays of
  "case" objects (`case_id`, `case_category`, `case_description`, input fields, a nested
  `assertions{status_code, errors}` block carrying the *expected* outcome alongside the input) —
  deserialized into a `*Cases` wrapper DTO, one case per TestNG data row. Small/fixed case spaces
  are sometimes inline literal `Object[][]` arrays directly in the `@DataProvider` method instead
  — both are acceptable, match whichever the sibling `@DataProvider`s in the same base class do.
- **Country-specific fixtures use two coexisting conventions** — pick whichever the directory
  you're touching already uses:
  - Subfolder-per-country: `kilat/testData/countries/{id,vn,th}/consumer_make_booking.json`.
  - Filename-suffix-per-country: `kilat/templates/makeBooking/consumer/
    consumer_v11_make_booking_id.json` vs. `..._th.json`.
  A `country` field is also often present inside each case object itself, so filtering can
  happen at the case level in addition to (or instead of) the file/folder level.
- **User pools**: `userPools/{consumers.json, consumers_with_details.json,
  consumers_with_country_codes.json, drivers.json}`. If you add a new test account to
  `consumers.json`, run the `GetConsumerInfo.kt` script (per `README.md`) to refresh
  `consumers_with_details.json` — don't hand-edit the details file.
- **Synthetic data**: `com.github.javafaker.Faker` for names/addresses/ID numbers;
  `utilities/PhoneNoGenerator.java` for country-valid phone numbers (country-specific prefix
  lists + a validation retry loop via `com.gojek.commons.phoneutils.PhoneNoValidator`).
- **DB verification (not seeding)**: `helpers/AliceDBHelper.java` (direct `JdbcTemplate` query
  against the allocation-service DB, wrapped in a `Failsafe` retry-until-condition poll) +
  `db/alice/AliceDBValidations.java` (assertion-style wrappers around it) — used to confirm
  downstream state (e.g. a driver got assigned to a booking) that the API response alone doesn't
  surface, not to seed data before a test runs.

## 6. Assertions

- **TestNG only** — `org.testng.Assert` (hard) and `org.testng.asserts.SoftAssert` (soft, collect
  multiple failures then call `.assertAll()` once). No AssertJ, no Hamcrest, and **no JSON-schema
  validation anywhere in the codebase** — all contract checking is field-by-field against
  deserialized DTOs.
- Assertion classes (`src/test/java/assertions/<domain>/**`) are plain POJOs with
  `verify/check/validate<Thing>(...)` methods. The safer of two coexisting conventions found in
  this codebase: **accept `SoftAssert` as a method parameter** (don't instantiate one as an
  instance field inside the assertion class — several existing classes do this and then forget
  to ever call `.assertAll()` internally, silently swallowing failures) and let the calling test
  method call `.assertAll()` once, at the end.
- Recurring **"router" pattern** for endpoints with many possible outcomes: one assertion method
  switches on the expected HTTP status code and dispatches to per-status sub-assertions, e.g.
  `CalculateAssertions.CreateCalculateAssertions(...)` (switches 200/401/default) and
  `ShipmentAssertion.verifyCreateShipmentErrorResponse(...)` (switches 400/422/500). Use this
  shape for a single data-provider-driven test method that needs to validate several
  status-code-keyed outcomes with one assertion call.
- Two recurring **negative-error shapes** — match whichever the vertical already uses:
  GoShop's `(code, message, message_title)` triad vs. TMS's `(code, message)` pair.
- **Structural difference, positive vs. negative test**: negative tests either (a) call a
  distinct Controller/Client method whose return type is itself an Error-shaped DTO (e.g.
  `createShipmentError(...)` vs. `createShipment(...)`), or (b) call the same method with
  corrupted/missing input and assert `IAPIResponse.getStatusCode().getCode()` together with a
  specific error `code`/`message` — never status code alone for a business-rule failure.

## 7. Grouping, retry, parallelism, reporting

- **Groups** are defined as Kotlin `object TestGroups` constants in
  `src/main/kotlin/common/constants/test/TestGroups.kt` — always reference a constant from here
  in `@Test(groups = {...})`, never a raw string literal; add a new constant if the
  domain/suite doesn't have one yet. Groups map to **suite/feature**, not country (only a couple
  of legacy constants have `_INDO`/`_ID` baked into the name — country selection is a separate
  `-Dcountry` CLI flag + explicit `Country` enum in code, orthogonal to groups).
- **Retry**: use `retryAnalyzer = retrier.RetryAnalyzer.class` on a `@Test` for a flaky/
  timing-sensitive scenario — this is the mechanism actually exercised across the codebase
  (retries once, after a 5s sleep). Two other retry mechanisms exist in the dependency graph
  (`listeners.retry.AnnotationTransformer`/`RetryAnalyzer` from `aep-backend-core`, opt-in via
  `-DautoRetryFailedTests=true`; and a local, currently-**unwired**
  `listeners.LogisticTestAnnotationTransformer`/`LogisticRetryAnalyzer` pair, commented out in
  `build.gradle`) — don't rely on either for a new test; use the per-`@Test` annotation instead.
- **`SkipException`**: throw this (rather than failing) when a precondition genuinely can't be
  met — an unrelated upstream 422, a required ID that never got generated mid-flow. Accepted
  idiom, used throughout `dispatch/`, `tms/spmd/`, etc.
- **Parallelism**: `./gradlew :go-logistics:runTests -Dtag=<group>` (sequential-per-class),
  `runTestsInParallel` (`parallel="methods"`, 10 threads), `singleTest -DtestName=<name>`
  (ad-hoc single test/method run, lighter listener set), `runFailedTestsInParallel`
  (`parallel="methods"`, 20 threads, re-runs `test-output/testng-failed.xml` from the previous
  run). `subprojects { maxParallelForks = Runtime.runtime.availableProcessors() }` additionally
  parallelizes at the JVM-fork/class level, independent of TestNG's own method-level threading.
- **System properties** consumed by the framework: `env` (default `integration`), `tag` (default
  `NONE`, the group filter), `oms` (default `consignor`), `country` (default `id`),
  `usePropsOverrides` (default `true`), `slackNotif` (Slack channel key from
  `slack_configuration.yml`). `maxFailureRetries` is set but not consumed anywhere in
  go-logistics's own source — likely read by an external listener jar.
- **Reporting/notification listeners** (ReportPortal, Extent HTML, Slack, an internal QA
  dashboard, BrowserStack SDK boilerplate) are wired in `build.gradle` as external published
  artifacts, not present as source in this repo — nothing to configure in a new test for these to
  "just work," they attach automatically based on the Gradle task used.
- **`@TestInfo(projectId=, suiteId=, owner=, testCaseIds={...})`** (from the sibling
  `gojek-test-integrations` repo) + **`@Ownership(author = GojekEngineer.X)`**
  (`src/main/java/utilities/{Ownership,GojekEngineer}.java`) are the live TestRail-traceability
  and ownership annotations — put both on every new `@Test`. The old in-repo
  `utilities/testRail/@TestRail` custom annotation + `LogisticsTestRailListener` are dead
  (zero usages) — don't use them.
- **`Reporter.log("<b>...</b>")`** at the top of a test method to narrate intent, surfaced in the
  Extent HTML report — documentation, not an assertion.
