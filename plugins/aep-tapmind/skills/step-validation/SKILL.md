---
name: step-validation
description: Run a list of written test steps — pasted by hand, or a scenario's automation_steps from enriched_automation_plan.json, *_automation_plan_generator.json, or *_sdet_plan.json / *_SDET_plan.json — against a real Android/iOS device via TapMind, report step by step exactly how each one was carried out (which resolved from the view hierarchy, which needed a vision fallback, a scroll or a retry, which extra steps had to be inserted, which transient screens were dismissed), and emit a ready-to-paste TapMind mobile-test @Test method built only from steps that actually ran. Use when someone hands over "here are my steps, they aren't working", or asks to validate/verify/debug a written test-step list. For generating a suite of NLP tests from a plan into tapmind-mobile-tests (kb-only or one pioneer, then clone), use nlp-codegen — not for open-ended exploration (that's goal-driven-exploration).
---

# Step validation (TapMind)

Take a list of written steps, execute them in order on a real device, and produce a
`report.html` that tells the **author of those steps** what is wrong with them.

## Philosophy: this is a diagnostic for the step author, not a test result

Someone wrote steps. The steps don't work, and they don't know why. Usually it's one of:

- the element they named **isn't in the view hierarchy** (an icon with no `content-desc`, a
  custom-drawn control, a WebView),
- the target's **real label differs** from what they wrote,
- the element **is off-screen** until something scrolls,
- **a step is missing** — the app demands a confirm/continue the list never mentions,
- **a transient screen** (permission dialog, rating prompt, promo, forced update) interrupts
  the flow and nothing in the list handles it.

The run's job is to find out which, and say so per step. So:

- **There is no PASS/FAIL badge.** The run-level result is about *completion*:
  `Completed`, `Completed with N deviations`, `Stopped at step K`.
- **Every step gets a line in the report**, including the boring ones that just worked. A
  10-step list produces 10 author rows plus whatever had to be inserted.
- **How a step succeeded matters as much as that it succeeded.** "Tapped the profile button"
  and "couldn't find 'profile' in the hierarchy, located it visually at (912,148)" are the same
  outcome and completely different information. Always report the mechanism.
- **Separate "your step was wrong" from "the app is broken"** — `fault: "authoring"` vs
  `fault: "app"`. They need opposite fixes, and an author who can't tell them apart starts
  rewriting steps that were never the problem. A dead button, a crash, or a genuinely false
  assertion is the app's fault and the step stands as written.
- **No exploration.** The steps are the contract. Never probe a tab or banner "while you're
  here" — that's `goal-driven-exploration`'s job and it would pollute this report.

## 0. Resolve inputs before touching a device

**First, work out where the steps are coming from.** Two input modes:

- **A — a written list.** Pasted in chat, or a file. Use it as given.
- **B — an automation ledger.** The user names a file, a folder, or a scenario. Resolve the
  file in this order (first match wins; if they named a file, use that file):
  1. **`enriched_automation_plan.json` / `*enriched_automation_plan.json`** — the ledger.
     Same `automation_scenarios[]` as APG, plus `test_data[].test_data_output[].test_buddy_prompt`
     and resolved `browserstack_case_id`. This is the primary input for running the suite.
  2. **`*_automation_plan_generator.json`** — automatable subset, unenriched.
  3. **`*_sdet_plan.json` / `*_SDET_plan.json`** — last resort.

  | File | Array | Steps field |
  |---|---|---|
  | `enriched_automation_plan.json` | `automation_scenarios[]` | `automation_steps[]` |
  | `*_automation_plan_generator.json` | `automation_scenarios[]` | `automation_steps[]` |
  | `*_sdet_plan.json` / `*_SDET_plan.json` | `scenario_list[]` | `automation_steps[]` (not `steps[]`, which is manual-QA prose) |

  `automation_steps` is already one action per line in TapMind vocabulary — **leave them as
  written**. Carry `csv_title_association` (or APG `description`), `requirement_ref`,
  `existing_case_ref`, `browserstack_case_id`, `priority_tier`, `platform` and `test_data`
  through as metadata for §6; they populate `@Test(description=…)` and `@TestInfo`. Record
  `source.kind` as `enriched_automation_plan`, `automation_plan`, or `sdet_plan` accordingly.

  **One scenario per run.** A plan holds many; validating several in one session breaks the linear
  `steps[]` spine and every counter in §5. If the user wants the whole plan, run the skill once
  per scenario and paste the emitted methods into one class.

  Some `automation_steps` are written as pseudo-calls rather than prose —
  `loginToDriver(<test driver account>)`. Those are **direct-API steps**: they map to a client
  method, not to a UI interaction. Resolve them against
  `references/direct-api-map.md` at §0 (they are setup, and §0 is where setup is resolved
  anyway), and mark them so §6 emits the call rather than a `runStep`.

**Then parse and echo the steps back.** Normalize the list into numbered entries, each tagged
`action` or `assertion`, and show it to the user once for confirmation before any device work:

```
Parsed 10 steps (7 actions, 3 assertions):
  1  action     Open GoFood
  2  action     Tap the profile button
  ...
  7  assertion  Verify the "Save card" checkbox is checked
```

A misparse discovered at step 8 wastes the whole run; this confirmation is cheap. If a line is
ambiguous ("check the address" — tap it, or verify it?), ask about that specific line here rather
than guessing silently. Do not re-ask after this point.

**Then the four run-context resolutions** — location, TDP test data, backdoor login, theme. These
are identical to `goal-driven-exploration` §0; read
`${CLAUDE_PLUGIN_ROOT}/skills/goal-driven-exploration/SKILL.md` §0 and follow it verbatim rather
than reinventing it. Three step-validation-specific notes:

- **TDP / TestBuddy query comes from `test_buddy_prompt` when it exists.** Do not invent an
  account. Resolve the `tdp_test_data_tool` message (and the `performBackdoorLogin` prompt) in
  this order, then pass it **verbatim**:
  1. **Primary — `test_data[].test_data_output[].test_buddy_prompt`.** Pick the fixture whose
     `required_state` matches the scenario's `driver_type` / `country` / `platform` (e.g. SC-001
     `driver_type: "2W"` → `fixture-driver-active-2w`, not the 4W fixture). Then take
     `test_buddy_prompt` from that fixture's `test_data_output[]` (match `fixture_id` /
     `scenario_id` when several outputs exist). Example for SC-001 2W:
     `"get me an onboarded Indonesia bike driver with loyalty enabled and update driver tier to GOLD"`
     That string is the only value sent to TDP / TestBuddy. Ignore `identification_steps`,
     `tdp_request`, and operations — they are audit, not the query.
  2. **Fallback — only when `test_buddy_prompt` is missing** (unenriched APG / SDET plan). Then
     compose from that fixture's `description` + `required_state`. If `test_data[]` itself is
     missing or empty, follow goal-driven-exploration §0 (ask the user). Do not compose a
     prompt from scratch while a `test_buddy_prompt` exists.
  Never emit raw tokens, phones, or account ids — emit the prompt, not what TDP returned.
- **Backdoor login is still mandatory** and still happens *after* the TDP fetch. If step 1 of the
  author's list is "log in", that step is satisfied by the backdoor login — record it as
  `origin: "author"`, `verdict: "pass_with_deviation"`, deviation type `reworded-target`, and say
  plainly that the UI login was bypassed. Never drive the real login UI here.
- **Theme**: default to a single theme (ask which). Running both doubles the run and duplicates
  every step row, which makes the report harder to read for its actual purpose. Only run both if
  the user explicitly wants theme coverage.

**Then the target module** — which `tapmind-mobile-tests` module the emitted test belongs to, so
§6 can match its package, base class and groups:

```
bash assets/module-profile.sh "$(bash assets/resolve-config.sh --path)" [repo-root]
```

The active profile usually *is* the module's own config (`driverApp/driver_android.json`), so the
module falls out of the path for free. Pass the repo root explicitly, or export
`TAPMIND_TESTS_REPO`, if the checkout isn't findable from there. If the script can't derive a
module it prints the list and stops — ask the user which one, then re-run it with that name.
Everything it prints (`PACKAGE`, `BASE_CLASS`, `TEST_GROUPS`, `SAMPLE_TEST`) is read from that
module's own tests, so it stays correct for modules that don't exist yet. **Never hardcode a
module table, and never guess a package or base class** — read `$SAMPLE_TEST`.

## 1. Preflight

**Two commands, in this order. The first is not optional.**

```
eval "$(bash assets/resolve-config.sh)"
bash ${CLAUDE_PLUGIN_ROOT}/skills/goal-driven-exploration/assets/new-run.sh <slug> [app-package-id]
```

`resolve-config.sh` works out which profile the **already-running server** is using and exports
`TAPMIND_CONFIG` so `new-run.sh` reads the right one. Skipping it is how a BrowserStack run gets
misread as local:

- The server resolves its config as `System.getProperty("config", System.getenv("DARKSEID"))` —
  the `-Dconfig` JVM flag first, `DARKSEID` env second.
- `new-run.sh` reads `$TAPMIND_CONFIG` or `~/.tapmind/profile.json`.
- The `tapmind` CLI bridges them (it reads `$TAPMIND_CONFIG` and forwards it as `-Dconfig`), but
  **anyone launching the jar by hand sets only `-Dconfig`** and never sets `TAPMIND_CONFIG`.
  `new-run.sh` then finds no profile, silently defaults to `run_mode=local`, and the whole run
  loses its adb-dependent captures. This has happened in production.

`resolve-config.sh` closes the gap by reading `-Dconfig` straight off the running JVM's command
line, which is authoritative — whatever that process started with *is* what every session uses.
It warns loudly if `$TAPMIND_CONFIG` disagrees with the server, and **exits non-zero if it can't
determine the profile at all.** If it fails, stop and fix that; do not proceed into `new-run.sh`
and let it guess `local`.

Then the scaffold:

```
bash ${CLAUDE_PLUGIN_ROOT}/skills/goal-driven-exploration/assets/new-run.sh <slug> [app-package-id]
```

It reads the active TapMind profile once for `run_mode` and app package, health-checks and starts
the server, enforces the single-adb-device gate for local runs only, and writes
`device-info.json` into the run dir. Everything `goal-driven-exploration` §1 says about it applies
here unchanged — in particular: **read `device-info.json` once and treat `runMode` as fixed for
the whole run.** Never re-derive it mid-run from an indirect signal like a failed `pm list` grep.
If the script exits 0, what it wrote is correct.

Then MCP: `start_appium_session(conversationId, sessionName)`.

### 1a. What this run mode can and cannot capture

**Read `runMode` from `device-info.json` and know this table before the loop starts.** A
BrowserStack run has no local device, so every `adb`-based check is simply unavailable — not
"try it and see". Getting this wrong is how a run produces a report with no screenshots at all.

| Capability | `runMode: local` | `runMode: remote` (BrowserStack) |
|---|---|---|
| Screenshots | ✅ `assets/capture.sh` | ✅ `assets/capture.sh` — same command, same cost |
| View hierarchy | ✅ MCP `get_view_hierarchy` | ✅ MCP `get_view_hierarchy` |
| Page source with `bounds` | ✅ uiautomator via adb | ❌ **not obtainable** |
| `lint.py` findings | ✅ | ❌ needs `bounds`; nothing to run it on |
| Crash check (`pidof`) | ✅ | ❌ — infer from the hierarchy instead |
| `logcat` | ✅ | ❌ — use the BrowserStack session log |

On a remote run you lose deterministic lint and logs. You do **not** lose screenshots — those
work identically, and there is no excuse for a remote report without them. Record what was
unavailable in `run.captureLimitations` (§5) so the report states it plainly: a remote run with
zero lint findings means lint never ran, not that the screens were clean.

## 2. The per-step loop

For each step in order. Capture is cheap and costs zero tokens — do all of it every time.

1. **Capture the "before" state.**
   - MCP `get_view_hierarchy(conversationId, context)` — the only payload that enters context.
   - Bash `assets/capture.sh <run-dir> <seq> before <conversationId>`

   `capture.sh` handles both run modes. It pulls the screenshot from TapMind's own
   `GET /tapmind/screenshot/{conversationId}` endpoint and decodes the base64 straight to disk, so
   it works on BrowserStack exactly as it does locally and **never puts the image into context**.
   It also grabs the uiautomator XML when adb is genuinely available, and prints a `SKIP` line
   when it isn't.

   **Read its stderr.** A `WARN` line means the screenshot did not land — leave that step's
   `screenBefore` null and say so, rather than writing a path to a file that doesn't exist.

   **Never substitute `appium_get_screenshot`** in either mode. It base64-encodes the image into
   this conversation's context and deletes its temp file server-side, so it can never reach the
   report — it burns tokens and produces nothing. `capture.sh` is the only screenshot path.

2. **Check for an interruption** — is the current screen something the step list doesn't
   mention? See §3. Handle it first, then come back to this step.

3. **Liveness + ANR.**
   - *Local:* `adb shell pidof <appPackage>` empty ⇒ crash. Capture
     `adb logcat -b crash -d > logs/step-NN.log`.
   - *Remote:* no `pidof` and no logcat. Infer a crash from the hierarchy instead — the app's
     package disappearing from the tree, a launcher/home screen appearing unprompted, or the
     Appium call erroring with a session/context failure. Record
     `evidence: "inferred from hierarchy (no adb on a remote run)"` and cite the BrowserStack
     session URL in the finding rather than a logcat excerpt.

   Either way a crash is a `fault: "app"` finding, severity high, and it **stops the run** — a
   dead process means every remaining step is `not_reached`. Scan the hierarchy for the system
   "isn't responding" copy ⇒ ANR, same treatment (tap "Wait" once if offered before giving up).
   Note that on remote, `source` is `"model"`, not `"lint"` — nothing deterministic produced it.

4. **Lint.** *Local only.* `python3 ${CLAUDE_PLUGIN_ROOT}/skills/goal-driven-exploration/assets/lint.py
   pagesource/step-NN.xml` → `findings/step-NN.json`. Deterministic, free.

   On a remote run there is no page source, so **skip this step entirely and do not compensate
   by eyeballing the hierarchy for the same defects and tagging them `source: "lint"`.** Anything
   you spot yourself is `source: "model"` — see the labelling rule below. A remote run legitimately
   produces fewer findings; that gap belongs in `run.captureLimitations`, not papered over.

   `source: "lint"` is reserved for findings that literally came out of this script's stdout.
   Anything you noticed by reading the hierarchy yourself is `source: "model"`, however mechanical
   it looks. Mislabeling overstates the finding's determinism to whoever reads the report.

   **Lint output explains vision fallbacks.** When step 5 forces a vision fallback, check whether
   lint flagged *the same element* as `missing-a11y-label` on this screen — if so, cite that
   finding id in the step's `deviation.why`. "No `content-desc` on the icon (finding f3)" is a
   far more actionable diagnosis than "not found in hierarchy," and it hands the author a concrete
   bug to file against the app team.

5. **Resolve the target — the ladder.** Full detail in `references/resolution-ladder.md`. Summary,
   in order, stopping at the first rung that resolves:

   | Rung | What it means |
   |---|---|
   | `hierarchy` | exact/unambiguous match on text, content-desc, or resource-id |
   | `fuzzy` | partial, case-insensitive, or translated match ("profile" → "Akun") |
   | `scroll` | not on screen; scroll to reveal, then re-resolve |
   | `vision` | Read `screens/step-NN-before.png` and locate it visually |
   | `coordinates` | tap by the bounds vision produced |
   | *(none)* | unresolvable → `fail` |

   **`scroll` must be exhausted before you may claim "not in the hierarchy."** Most apparent
   missing elements are simply below the fold, and reporting those as vision fallbacks cries wolf
   — the author rewrites a step that was fine. Only a failure *past* the scroll rung earns
   "the element is not in the hierarchy."

   Record `resolution.rung`, `attempts`, and what actually matched. This is the report's
   most valuable column.

6. **Act** (`kind: "action"`) — MCP `appium_tap_element` / `appium_input_value` / scroll /
   `appium_open_deeplink` / etc. **Or assert** (`kind: "assertion"`) — see §4.

7. **Capture the "after" state**: `assets/capture.sh <run-dir> <seq> after <conversationId>`.
   Both before and after, every step, no exceptions and in **every run mode** — the report shows
   them as a pair, and a missing one is a bug in this loop. A production run once shipped a report
   with zero screenshots because the loop emitted raw `adb` commands on a BrowserStack run where
   adb reaches nothing; `capture.sh` exists precisely so that can't recur. If you find yourself
   typing `adb` for a screenshot, you have taken a wrong turn.

8. **Classify** — write the step record (§5 schema). `verdict`, `fault`, `deviation`, and for any
   deviation a `suggestedRewrite` where one exists.

**Retry budget: 2 attempts per step.** If the first attempt produces no state change (`after`
hierarchy byte-identical to `before`), try once more — re-resolving down the ladder, not
repeating the identical call. If the second attempt also fails, the step is `fail` and the run
**stops**. Do not attempt step N+1.

Stopping is the right call and it was decided deliberately: these lists are one linear workflow,
so once the screen state diverges every later step is testing something other than what it says.
Marking them `not_reached` is honest; pretending to run them is not. Still write the full report —
a run that stopped at step 4 of 10 is a *successful diagnosis*, not a wasted run.

## 3. Interruptions (transient screens)

Any screen that appears which the step list does not account for: OS permission dialogs, forced
updates, rating prompts, promo/coupon interstitials, coachmarks, cookie/consent sheets, "what's
new" carousels.

Handle it, then record it as its own row with `origin: "interruption"`, `verdict: "dismissed"`,
and **all** of:

- a screenshot of the interruption itself (`screens/step-NN-before.png` — it gets its own `seq`),
- **how** it was dismissed: the ✕ control, a back press, "Not now", tapping through, or two taps
  because the first landed on the CTA underneath. Be specific — this is the author's guard clause.
- **`impact`**: `neutral` or `state-changing`.

The `impact` call matters more than anything else in the row. Dismissing a promo banner changes
nothing. Denying a location permission, skipping a forced update, or closing a coachmark that was
gating a tooltip target changes what every subsequent step is actually testing. Mark those
`state-changing` and say what changed — the report surfaces them separately and loudly.

Interruptions **count toward the extra-actions total** alongside inserted steps, but are counted
and displayed as a separate category: *"3 steps I had to insert, 2 interruptions I dismissed."*
The author's fix differs — an insertion means "add this step", an interruption means "add a guard
or expect this".

**Inserted steps** (`origin: "inserted"`) are the other extra-action category: an action the app
required that the list never mentioned — a "Lanjutkan" confirm sheet, a mandatory address
selection, an OTP-less re-auth. Same treatment: screenshot, what you did, why it was necessary,
and the exact line the author should add.

## 4. Assertions

Assertion steps ("verify the checkbox is checked", "verify the total shows Rp 56.000", "verify the
error message is visible") are first-class and get real validation. See
`references/assertions.md` for the per-type method.

Rules:

- **Evidence is mandatory.** Every assertion record carries the raw hierarchy line or the
  screenshot region it was judged from. `"looked correct"` is not a result — if you can't produce
  evidence, the assertion is unresolvable, not passed.
- **Prefer hierarchy over vision.** `checked="true"`, `enabled`, `selected`, and visible `text`
  are all directly readable attributes. Use `appium_get_element_attribute` for state that the
  hierarchy dump renders ambiguously. Fall back to reading the screenshot only for genuinely
  visual assertions (colour, layout, an image rendered) — and say so via `assertion.method`.
- **A failed assertion is `fault: "app"` by default.** The author asserted the total is
  Rp 56.000 and it shows Rp 45.000 — their step is fine, the app is wrong. Only mark it
  `fault: "authoring"` when the assertion is unresolvable because of how it was *written* (names
  an element that doesn't exist, is too vague to check).
- **A failed assertion does not stop the run** — unlike a failed action. The screen state hasn't
  diverged, so later steps are still meaningful. Record `verdict: "fail"`, `fault: "app"`, raise a
  finding, and continue. This is the one exception to §2's stop rule.

## 5. Record shape (`trace.json`)

`mode: "steps"`. Full schema and field semantics in `references/trace-schema.md`. The spine is a
flat `steps[]` array in execution order — there is no node/edge graph here (this flow is linear;
the sibling skill's graph exists because exploration branches).

```jsonc
{
  "run": { "mode": "steps", "result": "COMPLETED | COMPLETED_WITH_DEVIATIONS | STOPPED",
           "stepsGiven": 10, "actionsTaken": 13, "insertedSteps": 2, "interruptions": 1, ... },
  "steps": [
    { "id":"s2", "seq":2, "n":2, "origin":"author", "kind":"action",
      "given":"Tap the profile button",
      "did":"Tapped \"Akun\" (element_31)",
      "verdict":"pass_with_deviation", "fault":"authoring",
      "deviation": { "type":"vision-fallback",
                     "why":"No hierarchy match for \"profile\"; the account icon has no content-desc (finding f3).",
                     "suggestedRewrite":"Tap \"Akun\"" },
      "resolution": { "rung":"vision", "attempts":1, "matched":"account icon at [880,120][944,176]" },
      "screenBefore":"screens/step-02-before.png", "screenAfter":"screens/step-02-after.png",
      ... }
  ],
  "findings": [ ... ], "logs": [ ... ]
}
```

`verdict` values: `pass` · `pass_with_deviation` · `fail` · `not_reached` · `dismissed`.
`fault`: `authoring` · `app` · `null`.
Deviation types: `vision-fallback` · `scroll-needed` · `reworded-target` · `retry-needed` ·
`inserted-step` · `interruption`.

## 6. Emit the TapMind mobile test

The run just proved which steps work and what the app really calls things. Turn that into a
`@Test` method the author pastes straight into their module and runs — locally or on CI.

Write it into `run.tapmindTest` (schema in `references/trace-schema.md`); the report renders it
as the **TapMind test** tab with a copy button.

### 6a. One line per state-changing tool call — not per author step

The MCP loop already makes exactly one tool call per action, and `runStep` has the same
constraint: the server's system prompt requires it to *"complete your turn by invoking exactly ONE
tool"*, and `ActionVerbExtractor` only ever reads the **leading** verb of the sentence
(`stripped.split("\\s+", 2)[0]`). A compound line doesn't error — it silently does half the step.

So don't try to split English. **Emit from the tool calls you actually made.** The decomposition
already happened:

- one author step that took a scroll then a tap → **two** lines
- "Skip the walkthrough and tooltip prompts" that took two taps → **two** lines
- an interruption dismissed with two taps → two lines, or one if the first tap was a misfire
  (emit the corrected action only, and say so in the line's `note`)

Excluded: reads (`get_view_hierarchy`, `appium_get_element_attribute`, `capture.sh`) emit nothing,
and a retry of the same intent is **one** line, not two. Assertions don't come from tool calls at
all — they come from the step's `assertion` record.

### 6b. Which call to emit

Follow the ladder in `references/direct-api-map.md` — **direct API → `assertStep` → `runStep`** —
and its "when in doubt, emit the base API" rule. `TapMind.setMockLocation(-6.200000, 106.816666)`
compiles in every module; an invented `SomeModule.mockLocation(PLACE)` compiles in none.

The §0 setup resolutions emit deterministically from the run context, with the values that
actually ran — never a placeholder:

```java
TapMind.setMockLocation(-6.2615, 106.8106);
TapMind.performBackdoorLogin("get me an onboarded Indonesia bike driver with loyalty enabled and update driver tier to GOLD");
```

**Never emit a literal credential, token, phone number or account id** — emit the `test_buddy_prompt`
(or the TDP prompt that actually ran), not what TDP returned. If the run used tokens from config, emit the
config-reading expression `$SAMPLE_TEST` uses, not the values.

### 6c. Phrasing rules for `runStep` lines

These are what make a line resolve the same way on the hundredth run as on this one:

- **Start every line with a verb the server maps.** `single-verb-map` has `tap/click/press/touch/
  hit/choose/select/toggle`, `type/enter/input/fill/write`, `scroll/browse`, `swipe/fling/flick/
  pull`, `drag/slide`. `"On the home screen, tap GoRide"` loses gesture-family correction because
  the leading token is `on`; `"Tap GoRide on the home screen"` keeps it.
- **`scroll`, not `swipe`, for revealing content.** Different gesture families. Prefer
  `TapMind.scrollToText(Direction.DOWN, "GoRide")` over a `runStep` sentence when the target is
  just off-screen.
- **Quote only what resolved at the `hierarchy` rung.** Rule F makes single quotes a strict,
  case-sensitive, no-translation exact match; Rule G makes unquoted text fuzzy. A label that
  resolved at the `fuzzy` rung — including any translation like `profile` → `Akun` — **must stay
  unquoted**, or the test breaks the first time it meets another locale.
- **Use the label the app actually renders**, from `deviation.suggestedRewrite`, not the author's
  wording.

### 6d. Transient screens are conditionals, not steps

Every `origin: "interruption"` row emits an `if visible` guard rather than a bare action:

```java
runStep("Skip the walkthrough if visible");
runStep("Dismiss the set-vehicle-information card if visible");
```

This is a real server feature, not a phrasing convention: `patterns/conditional_actions.pattern`
routes the sentence to the conditional prompt, whose contract is **condition UNMET ⇒
`appium_report_skip`, never a failure**. So the line passes whether or not the screen appears —
which is the whole point, because a walkthrough that only fires on first login would otherwise
make the test pass once and fail forever.

Place `impact: "state-changing"` guards at the exact position they fired and comment why; a
`neutral` one can sit with the other guards. Never guard a step the flow genuinely depends on —
an `if visible` on a required action turns a real failure into a silent skip.

### 6e. Assertions

Intermediate checks → `assertStep("Verify …", "<why this failing matters>")`. The terminal
assertion follows the module's own idiom from `$SAMPLE_TEST`, usually:

```java
StepResult result = runStep("Verify Order screen visible");
Assert.assertTrue(result.passed(), "Test Case <methodName> Failed");
```

An assertion that **failed with `fault: "app"` keeps its line**, marked
`// FAILS TODAY — app bug (f2)`. Never weaken or drop an assertion to make the emitted test green;
that converts a found bug into a hidden one. An assertion that was unresolvable is emitted
commented out with the reason.

### 6f. Mark the two lines that can drift

The run resolved elements itself; `runStep` re-resolves them server-side. That agrees almost
always, but flag the two cases where it might not — **don't tax every line for it**:

- the match was **ambiguous** (several candidates; `resolution.candidates > 1`) — Rule I
  tie-breaks to the parent container, then first-in-array, which may not be what you picked
- the element resolved only at the **`vision`/`coordinates`** rung — the server has vision too, so
  the line can run, but with no hierarchy anchor the mark isn't stable run to run

Both get `// verify once` and a `note`. Everything else is emitted clean.

### 6g. Wrap it in the module's own shape

Read `$SAMPLE_TEST` from §0 and copy its annotations, imports, and try/catch shape. Fill
`@TestInfo` `testCaseIds` from input mode B in this order: `browserstack_case_id` first
(e.g. `"TC-766717"`), else `existing_case_ref`. Leave a field empty rather than inventing an id.
Pick `groups` from `$TEST_GROUPS` — those strings
are what CI selects on, so a guessed group means the test never runs there. Emit the method, not
a whole file: the author already has a class.

## 7. Close out

- MCP `appium_destroy_session(conversationId, errorMessage)` — **always**, even on a stopped run.
  One TapMind server pins one active session; leaving it alive corrupts the next run.
- **Verify every step has both `screenBefore` and `screenAfter`** before writing the trace. A null
  here is a bug in §2, not an acceptable gap.
- **Write the corrected step list** into `run.correctedSteps` — the author's steps, rewritten:
  reworded targets using the app's real labels, inserted steps marked, interruption guards added,
  original numbering preserved. This is the artifact the author copy-pastes back into their test,
  and it's the point of the whole run. Don't skip it because the run stopped early — write it for
  the steps that did execute and mark the rest `not verified`.

  **It is a list of objects, not a list of strings.** A production run emitted flat prose lines
  and every field came back `undefined`, so the tab rendered ten blank rows:

  ```jsonc
  // WRONG — renders blank
  ["1. Tap the GoRide tile — rewrite step 3 for clarity", "..."]

  // RIGHT
  [ { "n": "3", "text": "Tap the \"GoRide\" tile", "change": "reworded",
      "was": "Tap the Go Ride tile",
      "why": "The app renders it as \"GoRide\", no space." } ]
  ```

  `change` must be one of `unchanged` · `reworded` · `inserted` · `guard` · `not-verified`;
  anything else loses its colour coding. Keep the prose *inside* `why`, not smuggled into `text` —
  `text` is the literal line the author pastes into their test, nothing else.

- **Every finding must be routable.** A finding with a title and nothing else cannot be acted on.
  Required on each: `fault` (`app` or `authoring` — never null; this is what decides whether it's
  filed as a bug or fixed in the steps), `evidence`, `detail`, `severity`, and `step` or `seq`.
  A run once emitted a navigation defect with all of these null; it rendered with an empty
  evidence box, a "step not recorded" chip, and — because `fault` was missing — filed under
  *step-authoring issues* when it was plainly an app bug.

- **Link findings to the step that raised them.** Set `step.findings = ["f1", ...]`, not `null`.
  An unlinked finding never appears in that step's detail panel. Conversely, every step marked
  `fault: "app"` needs a matching `fault: "app"` finding carrying the evidence — the renderer
  reconciles the two counts and warns when they disagree.
- Populate `run.runMode`, `run.device`, `run.app` from `device-info.json` (§1) — copy, don't
  re-derive.
- Populate `run.model` / `run.modelEffort` from the model name and `echo $CLAUDE_EFFORT` **read
  via Bash**, not self-reported from memory.
- Populate `run.tokenUsage` / `run.costUsd` by running
  `python3 ${CLAUDE_PLUGIN_ROOT}/skills/goal-driven-exploration/assets/session-usage.py` with no
  arguments. It's exact — set `costEstimated: false`. Only fall back to `/cost` if it errors.
- **Populate `run.tapmindTest`** (§6). Every `lines[]` entry needs `fromSeq` pointing at the step
  it came from, so the tab can show provenance; a line with no `fromSeq` is a line nobody proved.
- Write `trace.json`, then `bash assets/render-report.sh <run-dir>` → `report.html`.
- **Read render-report.sh's stderr.** It warns on steps missing screenshots, assertions with no
  evidence, deviations with no `why`, an author-step count that disagrees with `stepsGiven`, and
  `source:"lint"` findings with no lint output behind them. Every warning is a bug to fix before
  handing the report over, not noise.
- Tell the user where `report.html` landed.

## Model

Sonnet 5, default or higher reasoning effort — same rationale as the sibling skill: this is a long
procedural checklist across dozens of tool calls, and the observed production failure mode is a
model making an ungrounded assumption early and not cross-checking it against config it already
read. Don't switch models mid-run; it invalidates prompt caching.
