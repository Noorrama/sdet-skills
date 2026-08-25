---
name: scp-api-test-writer
description: >-
  Use this skill whenever the user wants to write, add, or scaffold backend API automation tests
  in the scp module of gojek-backend-tests (scp/src/test/java/tests/gotoauth/**) — this module's
  real, live content is entirely GoTo Auth (login/identity/OTP/CVS/account-list/token) REST tests,
  despite the module's name and its ~62 .proto files suggesting a gRPC "Account/Profile" service.
  Trigger this any time the user gives a cURL targeting a goto-auth host/path (login, cvs, otp,
  account-list, token, uiw callback, goid) and asks for a new test case or test class. Also use it
  when the user references LoginClient, GoAuthController, AuthHeaderGenerator, or GotoAuthRedishClient.
---

# scp API Automation Test Writer

**Prerequisite:** read `.claude/skills/backend-automation/SKILL.md` first if you haven't already
this task — it defines the common module-identification, local-framework-discovery,
search-before-create, never-invent-data, and compile-check workflow. This file only covers what's
specific to scp on top of that.

**Read this before touching anything gRPC-shaped here.** `scp/src/main/proto/**` has 62 `.proto`
files and a full protoc/grpc build setup, but this is **entirely dead scaffolding**: `git log`
shows exactly one commit ever touched the generated gRPC code (2023-10-26), gRPC runtime
dependencies (`grpc-netty`, `grpc-protobuf`, `grpc-stub`, `protobuf-java`) are commented out in
`scp/build.gradle`, and zero test files reference any generated stub. **Do not write a gRPC test
here based on the proto files or generated stubs — they have no live consumer to model from.**
The 24 real test classes under `tests/gotoauth/**` are pure REST identity/login tests, actively
maintained (most recent commit as of analysis: 2025-08-12).

## Architecture

```
TestNG @Test (extends tests.SCPBaseTest)
    →  Controller (controllers.GoAuthController — lives in gojek-commons, NOT in scp itself)
        →  Client (clients.goauth.LoginClient — also in gojek-commons)
            →  Endpoint (entities.goAuth.**, implements IServiceEndpoint — also in gojek-commons)
                →  RequestHandler.processRequest(endpoint)  →  Response.as(XxxResponse.class)
                                                                + manually set httpStatusCode
```

**The important, non-obvious fact**: the actual REST client/controller/endpoint code this module
exercises is **not defined in `scp` itself** — `LoginClient` and `GoAuthController` live in
`gojek-commons` (`gojek-commons/src/main/java/clients/goauth/LoginClient.java`,
`.../controllers/GoAuthController.java`). `scp` only supplies the **test classes**, some
**module-local `@DataProvider`s** (`scp/src/main/java/testutils/dataprovider/OtpDataProvider.java`),
and **fixture data** (`scp/src/main/java/testutils/testdata/Customers.java`). If you need a new
endpoint that doesn't exist yet on `LoginClient`/`GoAuthController`, you're extending
`gojek-commons`, not `scp` — check there first, and be aware a change there affects every other
module that also depends on `gojek-commons`.

## Request/response conventions

Request POJOs are built with Lombok-style builders directly (`LoginMethodRequest.builder()...build()`)
or, for more complex/reused flows, via dedicated builder-helper classes
(`new CvsInitiateRequestBuilder(setBaseAuthRequest(clientDetails)).withVerificationId(...).buildRequest()`,
`new TokenRequestBuilder.GeneralTokenRequestBuilder().buildCvsTokenRequest(...)`) — check for an
existing `*RequestBuilder` before hand-assembling a request POJO field by field. Response POJOs
are asserted via `getHttpStatusCode()` on the deserialized wrapper.

## Authentication

REST headers (not gRPC metadata — there is no gRPC here) are built via
`testutils.dataprovider.AuthHeaderGenerator` (in `gojek-commons`), which conditionally adds
`Content-Type`, `Transaction-ID`, `X-AppId`, `X-AppVersion`, `X-User-Type`, `X-ClientID`,
`X-ClientSecret`, and `authorization: Bearer <token>` when a token is present. These header lists
are passed into each Endpoint constructor. Host resolution goes through `utils.AuthBaseClient.getGotoAuthHost()`
(env var `GOTO_AUTH_HOST`, falling back to a properties file keyed by `INFRA`) — never hardcode
the goto-auth host.

## Test-data conventions

- Module-local `@DataProvider`s in `testutils/dataprovider/OtpDataProvider.java`
  (`OTP_DATA`, `OTP_VALIDATE_DATA`, `OTP_RETRY_DATA`, etc.), combining headers, request POJOs, and
  expected HTTP status codes in one row.
- Shared DataProviders also exist in `gojek-commons` (`LoginDataProvider`, `AccountListDataProvider`,
  `CvsDataProvider`) — check there too before writing a new one.
- Fixture enum: `testutils.testdata.Customers` (e.g. `Customers.E2eID1`, `Customers.GojekIndoCustomer`) —
  named test accounts mapping to real pre-provisioned staging identities. Use these, don't invent
  a phone number/user ID.
- `OtpDataProvider.getHeader(String type)` hardcodes static test-environment client credentials
  used to exercise 401 "invalid credential" negative paths — this is existing checked-in test
  fixture data for authorized negative testing, not something to copy into new contexts or echo
  back if a user pastes it to you.

## Validation patterns

- Status-code assertions directly on the response POJO (`Assert.assertEquals(response.getHttpStatusCode(), 200)`),
  chained across sequential REST calls for multi-step flows (login-methods → CVS-initiate →
  CVS-verify → account-list → token → revoke — see the canonical test below).
- Negative tests assert status code plus, where available, a structured error field
  (`Assert.assertEquals(shortcodeResponse.getErrors().get(0).getCode(), expectedResponse.getCode())`
  against a fixture `ApiError` POJO) — don't invent the expected error code/text; use an existing
  `ApiError` fixture or ask for a real sample.
- **Downstream Redis validation is real and live**: `testutils.GotoAuthRedishClient` (direct
  `io.lettuce.core.RedisClient` connection) reads verification codes/OTP tokens straight out of
  Redis after a callback API call, feeding them into the next request — this is genuinely used
  end-to-end in `UIWTest`, though the specific test method demonstrating the full pattern is
  currently `@Test(enabled = false, ...)`. Confirm a test using this pattern is actually enabled
  before assuming it's a running example.

## Canonical tests (read these directly, don't guess)

- `scp/src/test/java/tests/gotoauth/LoginTests.java` (`E2ELogin`) — canonical multi-step REST
  chain (6 sequential calls), showing the real request-builder-helper usage pattern.
- `scp/src/test/java/tests/gotoauth/contractTest/otp/OtpTest.java` (`otpInitiateTest`,
  `otpInitiateNegativeTests`) — canonical data-driven positive+negative pair using
  `OtpDataProvider`.

## Module-specific pitfalls

- Don't write a gRPC test based on the `.proto` files or generated stubs — they're dead scaffolding
  with zero live consumers; treat their presence as a historical artifact, not a template.
- Don't assume the Client/Controller/Endpoint you need lives in `scp` — for goto-auth calls it's
  in `gojek-commons`.
- Don't invent OTP/phone-number/error-code test values — use `Customers`, `OtpDataProvider`, or
  an existing `ApiError` fixture.

## Legacy/dead patterns that must not be copied

- `scp/src/main/proto/**` and `scp/src/main/java/generatedCode/**` — dead gRPC scaffolding (one
  commit, 2023, zero consumers). This is the canonical repo-wide example of "don't assume a module
  with lots of `.proto` files is gRPC-heavy" from the common skill.

## Test-method contract (mandatory — verified)

Read `backend-automation/references/test-annotation-rules.md` first.

### Real module size (corrected)

**22** test classes (not 24), 18 files carrying `@TestInfo`. Most recent activity **2026-03-24** —
earlier versions of this skill said 2025-08-12 and therefore missed the entire 2025-10 → 2026-03
refactor wave. Re-read the sibling files rather than trusting older descriptions.

### The annotation block

```java
@Test(groups = {TestGroup.<GROUP>}, dataProvider = "…")
@TestInfo(projectId = SuiteConstant.SCP_PROJECT, suiteId = SuiteConstant.SCP_BACKEND,
          testCaseIds = {"<real id>"}, owner = "first.last@gojek.com")
public void someTest(String testName, ...) {
```

- **The constants class is `constant.SuiteConstant` — SINGULAR.** Not `SuiteConstants`. 87 usages of
  `SuiteConstant.SCP_PROJECT` + `SuiteConstant.SCP_BACKEND`. (Two stragglers use the raw literal
  `"194"`; don't copy those.)
- **Groups come from `testutils.TestGroup`** — never named in earlier versions of this skill. CI
  selects tests **only** by group, so a test with no wired group silently never runs.
- `owner` is a quoted email literal (89 uses).

### ⚠️ Two silent-failure traps unique to scp

1. **The data-provider dispatch is a `switch (method.getName())`.** Providers branch on the calling
   test method's name. If your new test method's name is not added to that switch, it receives no
   data and **silently does not execute**.
2. **The first data column must be `String testName`** — 49 methods rely on it. Omit it and the
   report/execution wiring breaks.

Both were absent from earlier versions of this skill.

### Data providers — all 11 are scp-local

Earlier guidance claimed `LoginDataProvider` / `AccountListDataProvider` / `CvsDataProvider` "also
exist in `gojek-commons`". **They do not.** All 11 providers are scp-local. `gojek-commons`'
provider directory holds exactly one file, `AuthHeaderGenerator.java`.

### Base class and framework

- `tests.SCPBaseTest` (`scp/src/test/java/tests/SCPBaseTest.java`) — the module's **only** local
  base class.
- **scp defines no endpoint class at all** (0 matches for `implements *Endpoint` in `scp/src`). It
  borrows `gojek-commons` endpoints under `entities/goAuth/**`, and its client is `gojek-commons`'
  `clients/goauth/LoginClient.java`, which extends no `BaseClient`. Host resolution goes through
  `gojek-commons` `utils/AuthBaseClient.java`.
- `IServiceEndpoint` is **not** in `gojek-commons` — it is in the external jar (declared exactly
  once in the whole repo, inside `gopay`).
- `scp` **does** depend on `gojek-commons` (`scp/build.gradle:132-134`), plus `customer-platforms`
  and `icp`.

### Assertions

**`SoftAssert` is used in 0 files here** (vs 103 in go-logistics). Do not inject it.

### Still true: the gRPC scaffolding is dead

The 62 `.proto` files and gRPC build setup remain entirely unexercised. The real tests are plain
REST identity/login.

### Compile check

```
./gradlew :scp:compileTestJava
```
