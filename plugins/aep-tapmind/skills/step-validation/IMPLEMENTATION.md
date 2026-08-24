# step-validation → TapMind mobile-test emission

Extends the existing `step-validation` skill so a validated run also emits a `@Test` method that
pastes straight into `tapmind-mobile-tests` and runs — locally or on CI.

No new skill. The validation loop already produces everything the generator needs (the app's real
labels, which rung resolved each element, which steps were inserted, which transient screens
fired); a second skill would have forked ~370 lines of device procedure and drifted.

## What changed

| File | |
|---|---|
| `SKILL.md` | §0 input modes + module resolution · **new §6 emit** · §7 close-out |
| `references/direct-api-map.md` | **new** — which steps must not become `runStep` |
| `assets/module-profile.sh` | **new** — derives package/base class/groups from any module |
| `references/trace-schema.md` | `run.tapmindTest` + invariants 12–15 |
| `assets/report-template.html` | **TapMind test** tab, copy button |
| `assets/render-report.sh` | enforces the new invariants |

## The four design calls

**1. Input mode B — SDET plans.** Point the skill at a `*_sdet_plan.json`; it reads
`scenario_list[]` and uses the scenario's **`automation_steps[]`** (already one action per line in
TapMind vocabulary), not `steps[]` (manual-QA prose). `existing_case_ref`, `requirement_ref` and
`platform` flow through into `@TestInfo`. One scenario per run — several in one session breaks the
linear step spine and every counter in §5.

**2. One line per state-changing tool call, not per author step.** The MCP loop already makes
exactly one call per action, and that is the same constraint `runStep` has: the server's system
prompt requires *"exactly ONE tool"* per turn, and `ActionVerbExtractor` only reads the **leading**
verb (`stripped.split("\s+", 2)[0]`) — a compound sentence doesn't error, it silently does half
the step. So emission reads the tool-call trace instead of parsing English. A step that took a
scroll then a tap emits two lines, for free. No splitter, no `" and "` heuristics.

**3. Direct API beats `runStep`.** Anything not touching the UI — mock location, backdoor login,
deeplink, kill/launch — has a client method. `runStep` would spend a server LLM turn on it and can
drift. The repo itself gets this wrong (`FCTGoFoodBooking` opens with
`runStep("Mock location to latitude: …")` when `setMockLocation(lat, lng)` exists).

Two traps documented, both from real repo usage:
- `performBackdoorLogin(String)` / `getDataFromTDP(String)` take an **NLP prompt**, not an id —
  `"get bike driver from TDP"`. Only the 2-arg overload is `(bearerToken, refreshToken)`. Emitted
  code carries the prompt, **never a literal credential**; `render-report.sh` fails the run's
  invariants if a token-shaped literal appears.
- `verifyTransientText` is **not** a transient-screen guard — it's an Android page-dump toast
  catcher. I had this wrong earlier in the design.

**4. Transient screens are conditionals.** Every interruption emits `… if visible`. This is a real
server feature, not a phrasing convention: `patterns/conditional_actions.pattern` routes to the
conditional prompt, whose contract is **condition UNMET ⇒ `appium_report_skip`, never a failure**.
So a first-login-only walkthrough can't make the test pass once and fail forever — the exact
repeat-safety requirement. `render-report.sh` warns on any `kind: "guard"` line lacking the clause.

## Works across all modules, by derivation not by table

`module-profile.sh` reads package, base class, groups and a sample test **out of the module's own
tests**. The 19 modules agree on nothing — packages range over `io.gojek.gofood.tests`,
`com.gopay.tests`, plain `tests`; base classes are `BaseTest`, `GoFoodTestBase`,
`CarePlatformBaseTest`, `LogisticsBase`; groups are sometimes literals (`"driverTest"`) and
sometimes constants (`FoodProjectConfig.CA_SMOKE`). A hardcoded map would be wrong for module #20.

Verified on all 19: 18 resolve, `commons` correctly reports it holds no tests. The module normally
falls out of the active profile path for free (`driverApp/driver_android.json` → `driverApp`).

**When unsure, emit the base API.** `TapMind.setMockLocation(-6.200000, 106.816666)` compiles in
every module; an invented `SomeModule.mockLocation(PLACE)` compiles in none. Module helpers
(`DriverMockLocation`) all bottom out in the same client call, so they're an optional nicety —
used only when `$SAMPLE_TEST` proves the module uses them.

## Phrasing rules that make a line survive the hundredth run

- Start every line with a verb in `single-verb-map`, or gesture-family correction is lost.
- `scroll`, not `swipe`, for revealing content — different families.
- **Quote only what resolved at the `hierarchy` rung.** Rule F makes single quotes strict,
  case-sensitive, no-translation; a `fuzzy` match (`profile` → `Akun`) must stay unquoted or the
  test breaks on the next locale. Only a validation run knows the rung — this is the thing offline
  code-gen structurally cannot do.
- Failed assertion with `fault: "app"` **keeps its line**, marked `// FAILS TODAY`. Never weakened
  to green.
- Only two line types get `// verify once`: ambiguous matches (Rule I tie-breaks to first-in-array)
  and vision-resolved elements (no stable hierarchy anchor). Everything else is emitted clean.

## Verification performed

- `module-profile.sh` swept across **all 19 modules**; graceful prompt for the one without tests.
- Caught a live bug during testing: `GROUPS` is a **bash builtin array** — assignment is silently
  ignored and yields `20` (the `staff` gid). Renamed to `TEST_GROUPS`.
- All five new invariants confirmed firing on a deliberately corrupted trace, and silent on a good one.
- Template JS syntax-checked; `javaSource()` lifted verbatim from the template and executed.
- **The emitted method was written into `driverApp` and compiled with
  `./gradlew :driverApp:compileTestJava` — exit 0.** Scratch file removed; tree clean.
- `@TestInfo` members confirmed against the compiled annotation: `countryName`, `projectId`,
  `suiteId`, `testCaseIds`, `owner`.

Emitted output for the Level Saya scenario:

```java
@Test(description = "Level Saya — Pencapaian Saya calendar shows the Lebaran eligibility period", groups = {"driverTest"})
@TestInfo(countryName = "ID", projectId = "122", suiteId = "28586233", testCaseIds = {"5354919"}, owner = "ashish.sharma@gojek.com")
public void testPencapaianSayaCalendarPeriod() {
    try {
        TapMind.setMockLocation(-6.200000, 106.816666);
        TapMind.performBackdoorLogin("get bike driver from TDP");
        runStep("Skip the walkthrough if visible");
        runStep("Tap 'Oke, lanjut' if visible");
        runStep("Dismiss the set-vehicle-information card if visible");
        runStep("Tap the profile icon"); // verify once
        runStep("Tap 'Pencapaian Saya' tab");
        assertStep("Verify the year selector shows 2027", "Year selector did not default to 2027");
    } catch (Exception e) {
        Assert.fail(e.getMessage());
    }
}
```

## Known limit

The loop drives MCP primitives; `runStep` re-resolves server-side through
`ActionVerbExtractor` → pattern match → Rules A–I. Those agree in the ordinary case, which is why
the design doesn't pay for proof on every line — only ambiguous and vision-resolved lines are
flagged. If you ever want hard proof, `POST /tapmind/execute` is the same endpoint `runStep` uses
and could replay the emitted lines in the open session. Deliberately not built: it costs a server
LLM turn per step to close a narrow gap.

Not built (add when something actually hurts): multi-scenario batching, `runStepByPlatform`
pairing (a single run only ever observes one platform), a standalone `.java` file on disk (the tab
copies a method; the author already has a class).
