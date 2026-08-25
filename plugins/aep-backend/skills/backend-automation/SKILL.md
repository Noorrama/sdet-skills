---
name: backend-automation
description: >-
  Use this skill whenever asked to create, write, add, or scaffold a backend API automation test
  anywhere in this repo (gojek-backend-tests) from a cURL command, an endpoint/API description, or
  a request like "add a test for this endpoint" — in any of the ~38 Gradle modules (go-logistics,
  gopay, gofood, driver-platform, transport, payment-core, scp, marketplace, driver-incentives,
  and others), even when the module isn't named explicitly. ALWAYS load this skill FIRST for any
  such request, before any module-specific test-writer skill, even if the module already looks
  obvious from the cURL's host/path — this file defines the module-identification and
  local-framework-discovery workflow every module-specific skill in this repo builds on, and it
  tells you which module-specific skill (if one exists) to load next.
---

# Backend Automation Test Generation — Common Entry Point

This is the single source of truth for generating backend automation tests in this repo from a
cURL. It is deliberately tool-agnostic: nothing below assumes Claude Code, Cursor, or any other
specific agent — it assumes only that you can read files, grep/search the repo, and run a shell
command. Both `.claude/skills/backend-automation/` (Claude Code) and `.cursor/skills/backend-automation/`
(Cursor) point at this exact file (see the bottom of this document) — there is one copy of this
content, not two.

**Evidence backing every claim in this file** comes from a full repository analysis written to
`REPO_TEST_AUTOMATION_ANALYSIS.md` at the repo root. If you want the full reasoning/evidence
behind any rule here, read that file. This skill is the actionable distillation of it.

## The one rule that matters more than any other

> **The nearest proven sibling pattern beats an assumed repo-wide convention.**

This repo has 38 independent Gradle modules. Some depend on a shared module (`gojek-commons`),
some don't. Some are pure REST, some mix REST and gRPC. Some have "modern" and "legacy" versions
of the same layer coexisting, with the modern one sometimes being the *unused* one. **Every module
implements the same conceptual shape (`Endpoint → Client → Controller → Test`) independently** —
sometimes via a shared interface, sometimes via a from-scratch local reimplementation of the same
idea under a different name. Do not assume any specific class, base, or convention exists just
because it exists in a module you've seen before. Confirm it exists **in the target module**
before using it.

## ...but a few things DO hold repo-wide — and they are compiler-enforced

The rule above is about *architecture* (Endpoint/Client/Controller shapes), which genuinely varies
per module. It is **not** a licence to skip the small set of invariants that hold everywhere they
apply. The most important one:

> **Every test method in the 32 modules that use it carries `@TestInfo`, with all four of
> `projectId`, `suiteId`, `testCaseIds`, `owner` populated — omitting any one is a compile error.**

`com.gojek.TestInfo` comes from the external `com.gojek:common-integrations` JAR (not in-repo
source, so you cannot read its definition from the tree). It is `@Target(METHOD)`, so it goes on
the test method, never the class. A full scan of 29,363 usages found exactly two attribute-set
combinations and zero structural deviation.

**The values, however, are per-module** — there is no repo-wide `SuiteConstants`. `gofood`,
`marketplace` and `driver-platform` read from their own `config/TestRailConfig`; `scp` uses
`SuiteConstant` (singular); `transport` deliberately passes `projectId=""`/`suiteId=""`; seven
modules use raw string literals; and 10 modules — including **`payment-core`**, which does not have
the JAR on its classpath at all — must **not** have `@TestInfo` added.

**A second invariant, equally silent when missed:** `@Test(groups = …)` is present on 40,055 of
40,606 `@Test` annotations, and every Gradle task selects tests by group
(`includeGroups System.getProperty('tag','NONE')`). A test whose group isn't selected **never runs,
without failing**. The group constant class is per-module too (`GoFoodCategories`,
`MarketplaceCategories`, `TransportCategories`, `constants.Groups`, `testutils.TestGroup`, …).

**Before writing any `@Test` method, read
[`references/test-annotation-rules.md`](references/test-annotation-rules.md).** It carries the
decompiled annotation contract, the per-module `projectId`/`suiteId`/`owner` table, the
`testCaseIds` placeholder convention, the gopay groups silent-skip trap, and a pre-flight
checklist. Guessing these produces either a build failure or a test that silently never runs.

## Do NOT assume — verified counterexamples

Every one of these has been directly disproven somewhere in this repo. Treat them as "check
first," not "safe defaults":

| Assumption | Why it's wrong | Verified counterexample |
|---|---|---|
| There is no shared endpoint convention at all | Overcorrection. There **is** a dominant convention — it just isn't declared in this repo, which is why grepping for `interface IServiceEndpoint` makes the repo look convention-less. `restidioms.security.core.template.IServiceEndpoint` ships in the external `com.gojek.aep-backend-core:core` jar and is imported **3,037** times. Only **one** module declares its own type by that name: `gopay` (1,426 imports of its fork). Other outliers clone it under a *different* name — `payment-core` and `iris` both define a local `HttpServiceEndpoint`. So: check whether your module is mainstream (use the jar) or an outlier (use its local clone) — don't assume either | Mainstream: `customer-platforms` — 0 own declarations, 249 jar imports, 246 implementors. Outliers: `gopay` (own `IServiceEndpoint`), `payment-core`/`iris` (own `HttpServiceEndpoint`) |
| Every module has a universal `BaseClient` every Client extends | Often only a minority of Clients use it | In `driver-platform`, only 5 of ~48 client classes extend `clients.BaseClient` — the rest call `RequestHandler` directly |
| Every module depends on `gojek-commons` | 8 modules opt out entirely | `cartography`, `crypto`, `data-platform`, `midtrans-core-api`, `iris`, `payment-core`, `ep-web-platform`, `vehicle-financing` have no `gojek-commons` dependency |
| Every module uses the same authentication | Auth varies per-domain even within one module | `payment-core` uses none/Basic-header-literal/API-key/HMAC-SHA512-signing/mTLS depending on the sub-domain being called |
| Every module uses the same assertion helper convention | Both "assertions in a helper class" and "inline `Assert.*`" coexist everywhere | Documented explicitly as a recurring mistake in `gopay/.gitlab/skills/qa-intern/MISTAKES_LOG.md` MISTAKE-007 |
| Every module uses the same DTO/Lombok convention | 3+ different Jackson-naming styles coexist even inside the shared `gojek-commons` module itself | `gojek-commons` mixes raw-snake_case-field-names, per-field `@JsonProperty`, and class-level `@JsonNaming` in sibling files |
| Every module uses the same async-validation mechanism | DB polling, HTTP-status retry, business-state polling, and disabled Kafka assertions all coexist, sometimes 3 different hand-rolled versions in one module | `transport` has 3 separate hand-rolled sleep/retry loops for the same "wait for async state" problem |
| A module with lots of `.proto` files is gRPC-heavy | File/proto count is not a reliable signal of what's actually exercised | `scp` has 62 `.proto` files and a full gRPC build setup that is **entirely dead** (one commit in 2023, zero test consumers, gRPC deps commented out in `build.gradle`) — its 24 real tests are pure REST |
| The "newer"-looking helper is the one to use | Sometimes the newer thing was built and never adopted | `driver-platform`'s real OAuth login helper (`DriverLoginUtil`) has zero call sites; the header-spoofing approach is what's actually live |
| Documentation/READMEs are accurate | Confirmed stale/broken in three places already | `transport/README.md` is ~4 years stale (claims Java 1.8; the module is on Java 17); `gopay/.gitlab/skills/qa-intern/qa-intern.md` and `INDEX.md` reference three playbook files (`decision-hierarchy.md`, `quality-gates.md`, `csv-generation.md`) that do not exist on disk; root `COPILOT_SKILLS_SETUP_CHECKLIST.md` claims files at paths that don't exist |

## The workflow

Follow these steps in order for **any** "create an automation test for this cURL" request.

```
Step 1  — Understand the cURL: method, host, path, headers, body, and (if given) a sample response.
Step 2  — Identify the likely module from the host/path (see "Module identification" below).
Step 3  — Confirm the module — don't blindly commit to step 2's guess. Grep the repo for the path
          fragment across modules; if more than one module plausibly owns it, ask the user or pick
          based on which module's other endpoints share the same host.
Step 4  — Load this common skill's guidance (you're doing that now).
Step 5  — Check the "Module routing" table below. If a module-specific skill exists for the
          identified module, load it now (see "How to load a module-specific skill"). If none
          exists, say so explicitly and proceed with fresh discovery using Steps 6-9 below against
          that module's actual source — do not assume it works like a module that does have a
          skill.
Step 6  — Search for the exact endpoint/path already being tested (see "Search before creating").
          If found, this is a Case-1 "extend existing" task, not a Case-2 "build everything" task.
Step 7  — Search for similar tests in the same module/feature folder — these are your style
          template, not just inspiration. Match their imports, annotation shape, and assertion
          style exactly.
Step 8  — Discover the local Client/Endpoint/Controller/DTO architecture for the specific feature
          area you're touching (see "Local framework discovery"). Do this even if a module skill
          exists — module skills describe the general shape, not every corner.
Step 9  — Determine whether an existing Endpoint/Client/Controller/DTO can be reused or extended
          rather than duplicated (see "Search before creating" and the reuse-hierarchy idea below).
Step 10 — Implement only what's missing. If Steps 6-9 found a full existing chain, you may only
          need a new `@Test` method.
Step 11 — Follow the nearest proven sibling file's exact convention (Lombok annotation choice,
          snake_case-vs-`@JsonProperty`, status-only-vs-status+body assertions, naming) — not a
          repo-wide rule, not this skill's own examples verbatim.
Step 12 — Add validations matching what the module actually verifies for similar endpoints (see
          "Determining validation strategy"). Don't add DB/Kafka checks the module doesn't
          actually use for this kind of call, and don't skip them if siblings do.
Step 12a— Annotate the test method per references/test-annotation-rules.md: `@Test` then
          `@TestInfo` then the signature, all four @TestInfo attributes populated from THIS
          module's constants holder, and `@Test` groups that satisfy the module's filtering
          listener. Skip @TestInfo only for the 10 modules listed there that don't use it.
Step 13 — Never invent: TestRail case IDs, hostnames, credentials/tokens, error codes/messages,
          or customer/merchant/order test-data IDs. If you don't have a real one, insert an
          obviously-marked placeholder and tell the user what they need to supply.
Step 14 — Compile-check: run `./gradlew :<module>:compileTestJava` (or the closest equivalent the
          module documents) before calling the work done.
Step 15 — Summarize what was reused vs. newly created, file by file, and list anything you left
          as a placeholder for the user to fill in.
```

## Module identification

Look at the cURL's host and path first:

- A distinctive path segment or product name in the host often maps directly to a module
  (`.../gosend/...` → `go-logistics`, `.../merchant/v1/restaurants/...` → `gofood`,
  `.../dispatch/bookings/...` → `go-logistics`).
- If the host/path is ambiguous, **grep the repo** for the literal path fragment across all
  `*/src/main/java/**/*Properties*.java` / `*/src/main/java/**/properties/**` files — whichever
  module's properties class already has a matching URL constant is almost certainly the right one.
- If the user names the module explicitly, trust that over your own guess, but still verify it
  (Step 3) rather than assuming they're right — property files are cheap to grep and confirm.

## Module routing

Modules with a dedicated, deep module-specific skill today. **Load the named skill** once you've
confirmed the module — do not try to re-derive everything from scratch when one already exists,
and do not load a module skill for a module it doesn't cover.

| Module | Skill to load | One-line reason it has its own skill |
|---|---|---|
| `go-logistics` | `go-logistics-api-test-writer` | TMS/GoKilat/GoSend/GoBox/GoShop layering, TMS gateway-prefix quirk, Kotlin scaffold abandoned since 2021 (Java is the living convention) |
| `gopay` | `gopay-api-test-writer` | Two coexisting paradigms (REST/miniapp vs gRPC/OMS); also see `gopay/.gitlab/skills/qa-intern/` for its own domain playbooks (payment flows, OMS state machine) — read those too when working in `paymentTooling/**` |
| `gofood` | `gofood-api-test-writer` | In-progress Controller/Client/Endpoint migration alongside legacy `*ClientWrapper`s; narrow-but-real gRPC surface for OpenAPI/web-order |
| `driver-platform` | `driver-platform-api-test-writer` | No universal BaseClient; header-spoofed driver auth (not a real login helper); disabled Kafka assertions |
| `transport` | `transport-api-test-writer` | Flow-controller orchestration layer; `TransportController` god-object; 4-year-stale README |
| `payment-core` | `payment-core-api-test-writer` | Standalone module (no `gojek-commons`); per-sub-domain auth (Basic/API-key/HMAC/mTLS); settlement domain data conventions |
| `scp` | `scp-api-test-writer` | Looks gRPC-heavy (62 `.proto` files) but is 100% dead scaffolding — real tests are plain REST identity/login |
| `marketplace` | `marketplace-api-test-writer` | 21 test bases routed by feature area; `EndPoint`/`testName=` conventions inverted vs gofood; `ConfigManager` mutates service configs from the DataProvider row |
| `midtrans-core-api` | `midtrans-core-api-test-writer` | Endpoints are **enum constants**, not classes; no client layer; static-imported `@TestInfo` values; hardcoded card/credential literals to avoid copying |
| `customer-platforms` | `customer-platforms-api-test-writer` | Umbrella module with four coexisting sub-conventions needing a routing step; on the mainstream jar `IServiceEndpoint` path; `countryName` via `TestCountry` constant |
| `iris` | `iris-api-test-writer` | Local `HttpServiceEndpoint` clone + local `Param`/`RequestBody`/`RequestHandler`; **no controller layer** (helpers instead); ~50/50 HTTP/gRPC; 9-line base class; `TC-`-prefixed case ids |

**Modules with no dedicated skill yet** (not because they're unimportant — because they haven't
been deep-analyzed): `icp`,
`driver-incentives`, `midtrans-enterprise`, `care-platform`, `courier`, `helpcenter`,
`app-platform`, `gopaylater`, `ticket-arbitration`, `go-sure`, `pricing`, `clloanplatform`, `gtl`,
`merchantlending`, `gomodal`, `gomart`, `gopay-merchant`, `gojek-e2e`, `merchant-platform`,
`ep-web-platform`, `vehicle-financing`, `core`, `data-generator`, `fleet-portal-backend`. If asked
to generate a test in one of these: **do not assume it behaves like any module above.** Run the
"Local framework discovery" steps below fresh, from scratch, against that module's real source.
If the same session ends up doing substantial work in one of these and the patterns turn out
genuinely different from anything documented here, that's a signal a new module skill might be
worth proposing to the user afterward — don't create one preemptively on thin evidence.

### How to load a module-specific skill

If you have a `Skill`-invocation tool available, invoke it by the exact name in the table above.
If you don't (e.g. you're reading these files directly rather than through a skill-loading tool),
just read `.claude/skills/<name>/SKILL.md` (or the equivalent path your tool exposes) in full
before writing any code for that module.

## Local framework discovery

Before writing a single line of new code, answer these questions **by reading the target
module's actual files**, not by assuming:

1. **Does this module depend on `gojek-commons`?** Check `<module>/build.gradle` for
   `implementation project(":gojek-commons")`. If yes, the shared `entities.BaseResponse`,
   `utils.properties.ConfigurationReader`, `helper.AEPFortknoxReaderHelper`, and dozens of
   ready-made `restidioms/serviceEndpoints/<service>/` classes may already cover part of what
   you need — check there before writing something new. If no, the module has its own local
   equivalent of the `IServiceEndpoint`/`RequestHandler`/`RequestBody` stack under its own
   package — find it (usually `com.<module>.backendtests.core.template.*` or similar) before
   assuming the shared one applies.
2. **What does a sibling `*Client` class in the same feature area actually extend/call?** Open
   one. Does it extend a local `BaseClient`? Does it call `RequestHandler.processRequest(...)` or
   `.processAPIRequest(...)`? Copy that exact shape, not a different module's.
3. **What does a sibling `*Endpoint`/`*ServiceEndpoint` class implement?** Confirm the interface
   name and package before writing `implements IServiceEndpoint` — it might be a module-local
   interface with the same method names under a different fully-qualified name.
4. **Where do URLs come from?** Every module resolves hosts through its own `*Properties`/
   `ConfigurationReader`-equivalent class, backed by an environment-keyed properties file. Find
   the module's version and add your URL constant there — never hardcode a host in an Endpoint.
5. **How is auth attached for this specific call?** Don't assume bearer-token auth. Open a
   sibling Endpoint/Client in the *same feature area* (not just the same module — auth style can
   vary by sub-domain within one module, as in `payment-core`) and copy its exact header/auth
   construction.
6. **What does the assertion-helper convention look like here?** Is there a dedicated
   `assertions.*`/`asserts.*` package? Do sibling tests assert inline instead? Match whichever the
   nearest sibling test does.
7. **What DTO/Lombok/Jackson convention does this feature area use?** `@Data` vs. `@Getter/@Setter`,
   `@Builder` vs. plain setters, snake_case fields vs. `@JsonProperty`, `@JsonIgnoreProperties`
   presence — copy the nearest sibling DTO's exact shape.
8. **How does this module validate async/eventual state, if at all?** Hand-rolled
   `Thread.sleep` polling loops are the repo norm (no Awaitility usage was found anywhere), but
   check whether the loop is at the business-state layer, the HTTP-retry layer, or a DB-polling
   layer — and check whether any existing Kafka/DB assertion code for this feature is actually
   live or commented-out/disabled (see "Anti-patterns to actively avoid" below).

## Search before creating

Before writing a new Endpoint/Client/Controller/DTO, search for one that already covers this
exact call. Duplicating an existing implementation is one of the most common, most explicitly
documented mistakes in this repo (see `gopay/.gitlab/skills/qa-intern/MISTAKES_LOG.md` MISTAKE-008
— two helpers that should have been one).

```bash
# By URL path fragment, across the target module's properties/endpoint layer
rg "path/fragment/from/curl" <module>/src/main/java/

# By a distinctive response field name from the sample response
rg "distinctiveFieldName" <module>/src/main/java/

# By the HTTP method + nearby domain word, in the test tree, to find a sibling test to copy the shape of
rg "verify.*<FeatureWord>" <module>/src/test/java/
```

If you find a matching Endpoint/Client/Controller method: **reuse it**. Only add a new `@Test`
method (Case 1). If you find a near-match that's missing one field/header your cURL needs: **extend**
it (add the field/header) rather than cloning the whole class. Only build all layers from scratch
(Case 2) when nothing close exists.

## Determining validation strategy

- Check what **existing sibling tests for the same endpoint/feature area** actually assert — not
  what's theoretically possible. Some modules have real DB or Kafka validation for a feature area;
  others only ever check the HTTP response.
- **Before copying a DB/Kafka assertion call from a sibling test, confirm it isn't disabled.**
  Real, confirmed examples of disabled-but-still-present validation code in this repo: `driver-platform`'s
  `ActiveBookingsLogKafkaAssertions` calls are commented out in every real test with an explicit
  "consumer not present" comment; `transport`'s `GopayCoinsPaymentTests` has ~15 lines of
  commented-out DB-log assertions per test method. Copying the surrounding pattern without
  noticing the actual assertion call is commented out will silently produce a test with no real
  validation.
- For negative/error-path tests: assert the status code **and**, if any sibling negative test in
  the same feature area does, the specific error code/message too — never invent the exact error
  text; if you don't have a real sample error response, ask for one or leave the status-code-only
  assertion with a clear note that the error-body assertion is a placeholder.

## Never invent

Do not fabricate, ever — insert a clearly-marked placeholder and tell the user what's missing
instead:

- TestRail/test-case IDs
- Hostnames or internal service URLs
- Credentials, tokens, API keys, HMAC secrets, client IDs/pass-keys
- Specific business error codes or error message text you haven't seen in a real response
- Customer/merchant/driver/order IDs that need to exist in a real environment

Real, checked-in violations of this rule already exist in this repo (a hardcoded-looking driver
`passkey` literal asserted directly in `driver-platform`'s `GetDriverClientNPassKey.java`, and
various per-partner Basic-Auth/API-key literals across several modules) — recognize this pattern,
never add to it.

## Verify before trusting any documentation, including this file

Three confirmed cases of stale/broken repo documentation exist today (see the table above).
Before relying on a citation from **any** doc — this skill, a module skill, a README, or a
playbook — confirm the referenced file/class actually exists (`ls`, `find`, or a quick `rg` for
the class name). If it doesn't, say so explicitly rather than fabricating plausible-sounding
content for it, and don't silently route around the gap — tell the user.

## Anti-patterns to actively avoid copying

These were found as real, checked-in code during the repository analysis. Recognize them; do not
propagate them into new tests:

- **Dead gRPC/proto scaffolding mistaken for a live pattern** — `scp`'s 62 `.proto` files, one
  commit in 2023, zero test consumers. Always confirm a pattern has real test-class consumers
  (grep for actual usages, not just presence of generated stubs) before treating it as canonical.
- **An "unused modern implementation" sitting next to the actually-proven legacy one** —
  go-logistics's Kotlin `goShop/{clients,controllers,endpoints}` rewrite has zero test-class
  consumers; every real GoShop test still calls the legacy Java classes.
- **Two competing interfaces/builders for the same gRPC concept mid-migration** — `gofood` has two
  separate `IGrpcServiceEndpoint` interfaces and two curl-logging builders implemented across
  different endpoint classes in the same client.
- **A "god object" aggregating dozens of controllers via Lombok `@Delegate`** — `transport`'s
  `TransportController`; even its own code comments flag parts of it as risky to depend on
  directly. Don't add new methods to a pattern like this without checking whether the module's
  own comments already warn against it.
- **Disabled Kafka/DB assertions left in place, commented out** — see "Determining validation
  strategy" above.
- **Hardcoded credential-looking literals in test assertions** — see "Never invent" above.
- **Stale READMEs/playbooks describing files or versions that no longer match reality** — see
  "Verify before trusting any documentation" above.

## Compile-check and summarize

Before reporting the task done:

1. Run `./gradlew :<module>:compileTestJava` (or the module's documented equivalent — some
   module skills name a more specific task). If the sandbox can't run Gradle, say so explicitly
   rather than claiming it compiles.
2. Summarize, file by file: what was **reused** (existing Endpoint/Client/Controller/DTO/Helper
   you called into unchanged), what was **extended** (existing class you added a field/method
   to), and what was **newly created**. List every placeholder you left (TestRail ID, error text,
   credentials) and what the user needs to supply.

## Other resources referenced by this skill (read when relevant, not by default)

- `references/test-annotation-rules.md` — **read this before writing any `@Test` method.** The
  decompiled `@TestInfo` contract, the per-module `projectId`/`suiteId`/`owner` constants table for
  all 32 modules that use it, the 10 modules that must not, `testCaseIds` placeholder convention,
  the gopay groups silent-skip trap, and the `description=`/`testName=` inversion.
- `REPO_TEST_AUTOMATION_ANALYSIS.md` (repo root) — the full evidence trail behind every claim in
  this file, including a structural fingerprint table for every module and 11 fully-traced
  end-to-end examples across 6 modules.
- `skills/generate-api-boilerplate/SKILL.md` — an older, still-accurate, git-tracked recipe
  covering the mechanical side of this same task (cURL-parsing rules, JSON→POJO type-mapping
  table, inline code templates). It is **not** an auto-loaded skill in this repo today (it lives
  outside `.claude/skills/`/`.cursor/skills/`, so neither tool discovers it automatically) — but
  its content is correct and worth reading for the low-level mechanics this file doesn't repeat.
- `gopay/.gitlab/skills/qa-intern/` — gopay's own mature task-flow/playbook system (confirmation
  gates, a self-maintaining `MISTAKES_LOG.md`). Genuinely useful when working in gopay, but three
  of its own referenced playbook files (`decision-hierarchy.md`, `quality-gates.md`,
  `csv-generation.md`) do not exist on disk — don't assume you can load them; if the user needs
  that content, tell them it's missing rather than inventing it.
