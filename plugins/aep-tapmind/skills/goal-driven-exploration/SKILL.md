---
name: goal-driven-exploration
description: Drive a real Android/iOS device through a plain-English QA goal (e.g. "do a GoFood booking using a customer from TDP", "run a group order on Pinky Porky"), thoroughly probing each screen for bugs — UI/layout defects, dark-mode issues, ANRs, crashes — along the way, not just racing to the goal. Produces a self-contained interactive HTML report with the journey as a graph. Use whenever someone asks TapMind to explore, test, or walk through a user flow rather than issue single taps.
---

# Goal-driven exploratory testing (TapMind)

Turn a plain-English goal into a real device run through the TapMind MCP server, and a
`report.html` that shows the journey as a graph — screens as nodes, actions as edges,
anomalies pinned where they were seen. Full design rationale: `references/design-notes.md`
(mirrors `tapmind-mcp-clean/docs/GOAL_DRIVEN_EXPLORATION.md`).

**Zero TapMind code changes.** Everything below is the existing MCP tools + Bash.

## Philosophy: finding bugs is the point, reaching the goal is not

The goal is a **scaffold for direction and a stopping condition** — it is not the success
metric. A run that explores every screen thoroughly, files three real findings, and never
reaches checkout has done its job. A run that beelines to the goal, reports `PASSED`, and
explored nothing along the way has not — even though it "succeeded." Concretely:

- On every **new** screen, spend a bounded amount of effort probing what's *not* on the direct
  path to the goal (tabs, banners, menus, filters) before taking the goal-directed action — §3.
- Look for the things a straight-line run would walk past entirely: layout/UI defects, dark-mode
  rendering issues, ANRs, and crashes — not just "did the goal step work."
- `verdict: PARTIAL` or even `FAILED` alongside a findings list is not a worse outcome than
  `PASSED` with an empty one. Don't let goal-completion pressure cut exploration short.

## 0. Resolve inputs before touching a device

A goal almost never spells out everything a run needs. Do not guess silently on these four —
guessing wrong burns a whole device run. Ask once, up front, then proceed without re-asking.

1. **Location.** If the goal names a place or coordinates, use it. Otherwise ask:
   > "This doesn't name a location — run at the default mock location, **South Jakarta
   > (-6.2615, 106.8106)**, or do you want to give a different one?"
   Call `appium_mock_location(conversationId, latitude, longitude, reason)` with whatever is
   agreed before the exploration loop starts. Skip this only if the goal is location-irrelevant
   (e.g. a login-only smoke check).

2. **Test data.** If the goal names a specific customer (phone/ID/segment), use that verbatim.
   Otherwise **do not invent a customer** — ask the user exactly what TDP should provide:
   > "What customer should I pull from TDP for this run? For example: any active customer with
   > a GoPay balance, a first-time customer, or a specific phone/customer ID."
   Take their answer **verbatim** as the `message` to `tdp_test_data_tool(conversationId,
   message)` — the tool description says not to modify it, and TDP's own agent does the
   interpretation. For a **group order**, the goal needs a host customer *and* one or more other
   participants; if the goal doesn't say how many or where their data comes from, ask that too
   before calling TDP (e.g. one `tdp_test_data_tool` call per participant, or one call asking for
   "a host and 2 participants" if TDP's agent supports batch asks — try the single call first).

3. **Backdoor login is mandatory, always** — never drive the real login UI for this skill.
   Once TDP has responded (step 2 stores `accessToken`/`refreshToken`/`customerId` for the
   conversation automatically), call `appium_backdoor_login(conversationId, reason)` with no
   `credentials` argument — it reads what TDP just stored. If TDP wasn't asked for data because
   the user supplied a token/ID directly, pass that as the `credentials` map instead. Login order
   matters: TDP fetch **before** backdoor login, every time — the login tool throws if no token
   is on record yet.

4. **Theme.** Ask: "Test light mode, dark mode, or both?" Default suggestion: light only for a
   quick run, both if the user cares about UI coverage. Testing both roughly doubles run length —
   say so when asking. If both, run the whole goal once per theme rather than toggling mid-run
   (mid-run toggles relaunch the app — see `references/tapmind-recipes.md` — and would confuse
   the graph's node identity between passes). Record which theme(s) ran in `run.themes`.

Only after these four are settled does preflight run. See `references/tapmind-recipes.md` for
the exact tool signatures, the merchant/restaurant search pattern (how to land on a specific
restaurant like "Pinky Porky" rather than a generic home screen), the dark-mode toggle command,
and group-order specifics.

## 1. Preflight

**One script call. Don't re-derive anything it already tells you.**

- Bash: `assets/new-run.sh <slug> [app-package-id]`. It reads the active TapMind profile
  (`$TAPMIND_CONFIG` or `~/.tapmind/profile.json`) **once**, for `run_mode` and the app package
  (`mobile_capabilities.android_only.appPackage`) — that's the ground truth; you don't need to
  `cat` the profile yourself or grep `adb shell pm list packages` to figure either out. The
  `app-package-id` arg is only an override for when the profile doesn't have one; omit it in the
  common case.
- It health-checks the server via the real endpoint (`/actuator/health`) and starts it if down —
  don't run your own health check first, this one is authoritative and `tapmind start` is
  idempotent regardless.
- It only enforces the "exactly one `adb` device" gate when `run_mode == "local"`. For a
  BrowserStack run there's no local device to require, so it skips that gate and the
  adb-based model/OS/app-version lookups entirely — get those from the live Appium session's
  capabilities once it starts, not from the profile's `devices.android[]` list (that's a menu of
  *options* BrowserStack can pick from, not a confirmed assignment — a past run misread one of
  these entries, `"Samsung Galaxy S25"`, as "the currently connected device").
- It writes `device-info.json` into the run dir with `runMode`, `platform` (`android`/`ios`),
  `deviceKind` (`android-device` / `android-emulator` / `ios-simulator` / `ios-device` /
  `browserstack`), device model/OS/app-version for local runs, and a **`capabilities` block**.
  **Read this file once and treat all of it as fixed for the rest of the run** — a past run
  re-derived `runMode` mid-loop from an unrelated failed `pm list` grep, concluded (wrongly) that
  the device must be remote, and silently skipped every adb-dependent step (screenshots, page
  source, lint, crash/ANR checks) for the rest of the run. If `new-run.sh` exited 0, what it
  wrote is correct — full stop, don't second-guess it later from an indirect signal.

- **`capabilities` is the contract for what this target can actually check.** Each field names
  the *mechanism*, not a yes/no, so you know which command to reach for without testing the
  platform yourself:

  | Field | Values | Used by |
  |---|---|---|
  | `screenshots` | `adb` · `simctl` · `appium` · `none` | §3a.2 |
  | `pageSource` | `uiautomator` · `none` | §3a.2, §3a.6 (`lint.py`) |
  | `deviceLogs` | `logcat` · `simctl` · `idevicesyslog` · `session` · `none` | §3a.4-5, §3b.13 |
  | `liveness` | `pidof` · `simctl` · `hierarchy` | §3a.4 |
  | `crashDiagnosis` | `stacktrace` · `detection-only` | §3a.4, finding `diagnosis` |
  | `hangSignal` | `anr-dialog` · `timing` | §3a.5 |
  | `networkToggle`, `rotation`, `locale`, `phoneCall` | `adb` · `adb-emu` · `none` | focus areas (§3c) |
  | `permissionControl` | `mcp` · `none` | focus areas (§3c) — Android-only tool |

  **Never infer a capability by running a command and seeing whether it fails.** That is exactly
  the bug this block exists to kill: adb-shaped instructions silently no-op'd on iOS and
  BrowserStack, and a BrowserStack run would finish and report clean having never once checked
  whether the app was still alive. If `capabilities.pageSource` is `none`, `lint.py` doesn't run
  on this target and its absence is expected, not a defect in the loop.
- If it exits non-zero, the message on stderr says exactly what's wrong (server unreachable, no
  device for a local run, multiple devices) — fix that specific thing, don't work around it.
- MCP: `start_appium_session(conversationId, sessionName)`.

## 2. Goal decomposition

Turn the goal into an ordered intent list before acting, e.g. for "run a group order on Pinky
Porky": mock location → backdoor login as host → search GoFood for "Pinky Porky" → open the
restaurant → start a group order → add items → invite/simulate a participant → checkout. Name
the goal-blocking step explicitly (usually checkout/payment) so a `blocked` verdict is
recognizable rather than mistaken for a wrong turn. Treat this list as **waypoints to explore
around**, not a script to execute — §3 spends real effort at each one before moving to the next.

If the goal-blocking step is checkout/payment, decompose it as "pay with the goal's specified (or
default) method; if that method reports insufficient balance, switch to cash and retry once" —
see **Payment fallback** in §3b — rather than a single fixed pay action. The goal here is
completing *a* booking, not proving one specific payment method works.

**Mark the state-bearing waypoints** while decomposing — the steps after which the app holds user
state that would be expensive to lose (cart filled, address selected, payment method chosen, order
placed). §3c fires its focus area only at these, so naming them here is what stops the focus area
being spent on a splash screen. For a GoFood booking that's typically: cart populated → address
confirmed → payment selected → order submitted.

Budget: default 60 steps / 25 min (raised from a straight-line skill's 40/15 — exploring each
screen costs steps that a goal-only run wouldn't spend). Say so if the user hasn't been told;
raise or lower it if they'd rather trade thoroughness for speed on a given run.

## 3. The loop: explore the screen, then advance the goal

Repeat until the goal is met, the run is blocked, or the step budget is spent. Every **new**
screen gets both phases below; a **revisit** (node already in the trace) skips straight to 3b —
don't re-explore a screen you've already probed.

### 3a. Explore this screen (new screens only)

1. MCP `get_view_hierarchy(conversationId, context)` — the only payload that enters context.
2. **Capture the screen — the command depends on `capabilities` (§1), not on the platform you
   assume you're on.** Write the hierarchy text to `pagesource/step-NN.txt` regardless (§3a.4-5
   need a file to read):

   | `capabilities.screenshots` | Command |
   |---|---|
   | `adb` | `adb exec-out screencap -p > screens/step-NN.png` |
   | `simctl` | `xcrun simctl io booted screenshot screens/step-NN.png` |
   | `appium` | `appium_get_screenshot` — **key screens only**, it costs context (see below) |
   | `none` | no screenshot this step; leave `node.screenshot` null and say so in close-out |

   | `capabilities.pageSource` | Command |
   |---|---|
   | `uiautomator` | `adb shell uiautomator dump` → `pagesource/step-NN.xml` (has element bounds) |
   | `none` | no bounds-bearing dump exists on this target — **`lint.py` cannot run (§3a.6)** |

   **Never substitute `appium_get_screenshot` when `capabilities.screenshots` is `adb` or
   `simctl`** — it returns the image as base64 *into this conversation's context* and its temp
   file is deleted immediately server-side, so a screenshot taken that way can never end up in
   the report no matter what you set `node.screenshot` to afterward. This substitution is the
   single biggest failure mode observed in production use of this skill: it silently produces a
   report with placeholder art for every screen and burns image tokens doing it.
3. **Label the screen**, record the node immediately — `screenshot`/`pageSource` fields set the
   moment the files exist, not deferred to close-out (a missing `screenshot` is a bug in this
   loop; `render-report.sh` warns about it as a backstop, don't rely on the backstop).
4. **Health check — one script call, every new screen, every target.**

   Bash `assets/health-check.sh <run-dir> NN pagesource/step-NN.txt`

   It reads `capabilities` and picks the right mechanism itself (pid on Android, `simctl` on an
   iOS simulator, the hierarchy on a remote target), captures the right log, and returns one
   line of JSON: `{alive, crashed, hung, diagnosis, logPath, mechanism, note}`.

   **Do not hand-write `adb` commands for this.** That is what the old version of this step
   said, and on every non-Android-local target those commands quietly did nothing — a
   BrowserStack run would finish and report clean having never once checked whether the app was
   alive. Finding crashes is this skill's mandate; it cannot depend on translating a command per
   platform in the middle of a long run.

   Act on what comes back:

   - **`crashed: true`** → file a `crash` finding (severity high, confidence high, `source:
     "lint"`), **carry `diagnosis` onto the finding verbatim**, mark the edge that led here
     `outcome: "crashed"`, then `appium_launch_app` before deciding whether to continue this
     branch or end it (`kind: "deadend"`).
     - `diagnosis: "stacktrace"` → `logPath` has the trace; summarise the top frames.
     - `diagnosis: "detection-only"` → you know it died and **you cannot say why**. Write that.
       Do not speculate a cause, and on a BrowserStack run put the session URL in
       `trace.run.sessionUrl` so a human can pull the logs there.
   - **`hung: true`** → file an `anr` finding (severity high, confidence high, `source: "lint"`).
     On Android tap "Wait" if offered (one chance to recover), else "Close app" and relaunch.
   - **`note` is non-null** → read it. A note saying *liveness NOT checked* means this screen has
     **no** crash coverage — that is not the same as a clean screen, and it must be said in
     close-out rather than silently counted as healthy.

   Run this on every new screen, not only when something looks wrong — crashes don't always
   announce themselves before the process dies.

5. **Hang detection on targets with no ANR dialog** (`capabilities.hangSignal == "timing"` — iOS
   and BrowserStack). There is no system "isn't responding" dialog to scan for: iOS's watchdog
   kills the app outright (`0x8badf00d`) with no warning, so the Android dialog scan finds
   nothing there by construction. Detect it from behaviour instead: if an action produced **no
   change in the hierarchy and no navigation**, re-capture the hierarchy to
   `pagesource/step-NN.txt.unresponsive` and re-run `health-check.sh` against that path — the
   `.unresponsive` suffix is how you tell the script "nothing moved across an interaction."
   Distinguish this from a dead button (§3b, stuck detection): a dead button leaves the rest of
   the screen responsive, a hang doesn't.
6. Bash `python assets/lint.py pagesource/step-NN.xml` → deterministic UI findings, 0 tokens.
   **Only when `capabilities.pageSource == "uiautomator"`.** Where it's `none` (iOS, BrowserStack)
   there is no bounds-bearing dump for lint to read, so this step does not run and produces no
   findings — that is an expected coverage gap on those targets, not a skipped step. Say it in
   close-out; don't let an empty findings list read as a clean screen.
   **`source: "lint"` is reserved for findings that literally came out of this script's stdout —
   never for something you noticed yourself while reading the hierarchy, no matter how
   mechanical or obvious it looks.** If you spotted it by reasoning over `get_view_hierarchy`'s
   text (a raw resource key, a debug placeholder string, a button that didn't respond), that's
   `source: "model"`. Mislabeling it `"lint"` overstates the finding's determinism to whoever
   reads the report — the "Confirmed" section implies "a script found this, byte-identical every
   run," which isn't true of something you eyeballed. If you skipped this step entirely for a
   screen (e.g. because you incorrectly believed adb wasn't available — see §1), don't backfill
   `source: "lint"` findings anyway; they're `"model"` findings or nothing.
7. **Vision review — fallback, not default.** Hierarchy (step 1) is the primary source for both
   navigation and defect detection. Only Read `screens/step-NN.png` directly (not
   `appium_get_screenshot` — that base64-encodes into context redundantly and its temp file gets
   deleted anyway; the file §3a.2 captured is already on disk) for *this* node when at least one
   of these holds — check in order, stop at the first match.

   Where `capabilities.pageSource` is `none` (iOS, BrowserStack), `lint.py` never runs, so vision
   is the **only** defect source on those targets other than the hierarchy — weight it more
   heavily there and don't treat a clean hierarchy as a clean screen. Where
   `capabilities.screenshots` is `none`, there is no image to read and this step is unavailable
   entirely; record that gap in close-out.
   - **This run's theme is dark** (§0.4) — always review. Theme-adaptation bugs (a light-mode
     asset rendered unchanged against a dark background) are this skill's main reason to exist,
     and lint has zero signal for them — this is the one trigger that isn't really a "fallback."
   - **Hierarchy couldn't resolve the element step 10/11 needs** — no match, or more than one
     candidate with no clear best pick. Read the screenshot to locate/disambiguate visually
     before concluding the action is a dead end.
   - **This screen looks transient** — a loading/splash/interstitial state with few or no
     clickable elements in the hierarchy, or matching a known loading-screen signature. Hierarchy
     can't distinguish a stuck spinner from one mid-transition; a screenshot can.
   - **`lint.py` (step 6) already flagged something on this screen** — broken/missing image,
     overlapping elements, off-screen element, truncated text. One screenshot read confirms
     whether it's a real rendering defect or a false positive from stripped bounds before it's
     written up as a finding.

   Otherwise — light-mode run, hierarchy resolved cleanly, lint clean, screen isn't transient —
   skip this step, go straight to 3b. This deliberately trades away catching *light-mode-only*
   layout/contrast bugs on a screen with no other signal pointing at it; note that trade-off in
   the run's close-out if visual coverage matters for this goal. When you do read a screenshot,
   record only high-confidence hits (`source: "model"`, `confidence: "high"`) — this is a
   targeted look for visual defects, not a chance to hedge with low-confidence noise.
8. Skim `references/known-bugs.md` for this screen/flow — carry `kbRef` forward on any match.
9. **Probe secondary elements adaptively** — interactive elements visible here that are *not*
   the next goal-decomposition waypoint (a tab, a banner, a "See all", a filter chip, an icon).
   Try one, observe (repeat steps 1-3 for wherever it lands, or note the outcome if it's a no-op),
   then decide whether to keep going: **stop once 2 probes in a row surface nothing new** (no new
   screen, no new finding) — that's this screen exhausted, don't keep spending steps here. Hard
   cap regardless: 5 probes per screen, so one busy screen (e.g. a home page with 15 tiles) can't
   consume the whole run's budget. After each probe, navigate back to this node before trying the
   next one or moving to 3b. Tag every edge from this sub-step `phase: "explore"`.

### 3b. Advance the goal

10. Decide the next action toward the current goal-decomposition waypoint.
11. MCP act: `appium_tap_element` / `set_text` / `scroll` / `appium_mock_location` /
    `appium_backdoor_login` / `tdp_test_data_tool` / etc.
12. Append the edge (`phase: "goal"`, `outcome`: ok/retry/backtrack/blocked/unexpected/crashed —
    see `references/anomaly-checks.md` for how to classify).
13. On any failure, `blocked`, or `crashed` outcome, capture a log slice if §3a.4 hasn't already
    captured a more targeted one — again per `capabilities.deviceLogs`:
    `logcat` → `adb logcat -d -t 400 > logs/step-NN.log` · `simctl` → `xcrun simctl spawn booted
    log show --last 2m > logs/step-NN.log` · `session` → nothing to capture locally, make sure
    `trace.run.sessionUrl` is set · `none` → no log for this outcome; note it on the edge.

**Interruptions** (popups, permission dialogs, promos, forced updates): dismiss, record as an
`unexpected` edge into a `popup` node, continue toward the goal — don't treat them as failures,
but also don't skip 3a's liveness/vision checks for the popup itself before dismissing it.

**Payment fallback** (checkout/payment goals only): if the pay action surfaces an insufficient-
balance signal for the selected method (see `references/tapmind-recipes.md` for the exact
hierarchy text/element pattern) — switch to cash (or the first other available method if cash
isn't offered) and retry the pay action **once**. Log this as a normal `outcome: "ok"` edge with
`note: "Insufficient <method> balance — switched to <method> and retried"`, not `blocked` — the
app degrading gracefully to an alternative payment method is the system working, not a defect.
Bound to exactly one switch: if there's no alternative payment method to pick (the switcher shows
only the method that just failed, or doesn't open at all), that **is** a real `blocked` finding —
don't reopen the switcher and try again expecting a different list.

**Stuck detection**: same screen after an action ⇒ candidate dead button (`blocked`, self-loop).
Same node visited 3+ times without progress ⇒ navigation trap; end that branch, don't keep
looping — it will burn the step budget for nothing. A `crashed` outcome ends that branch outright
(kind: `deadend`) — don't retry the same action expecting a different result from a dead process.

### 3c. Apply the focus area (only when the run has one)

**Skip this section entirely for an ad-hoc goal with no focus area.** It applies when this run was
launched from a charter (`aep-tapmind:charter-exploration` passes exactly one `focus_area`), or
when the user named a condition to probe.

§3a.9 probes what is *on* the screen. This probes what **isn't** — backgrounding mid-checkout,
denying a permission at the moment it's asked, opening a deep link while a booking is in flight,
double-tapping Order. Scripted regression structurally cannot cover these, which is the whole
reason a charter exists. Read `references/focus-areas.md` once at the start of the run and follow
the entry for this run's focus area; everything below is how it slots into the loop.

1. **Check applicability before spending a step.** Every focus area has a *fires at* rule, and for
   almost all of them it's **state-bearing screens** — a screen holding user state that would be
   expensive to lose (filled cart, selected address, chosen payment method, in-flight booking,
   half-completed form). On a screen with no such state, skip it and continue. That is the rule
   working, not a step you missed — rotating a splash screen finds nothing and costs a step.
   §2's decomposition should have named the state-bearing waypoints already; use that list.
2. **Check the capability.** The entry names the mechanism per `capabilities` (§1). Where it's
   `none` on this target, the focus area **cannot run here** — add a line to `run.coverageGaps`
   and move on. Never substitute an adjacent action and report it as covered: a session-level
   BrowserStack network profile is not `network-loss`, and an iOS edge swipe is not the Android
   hardware BACK path.
3. **Inject the condition** with the exact call from the entry — signatures there were read off
   the live tool schemas, so use them verbatim rather than from memory.
4. **Evaluate against the oracle**, which is the part that makes this a test rather than a poke.
   Re-capture the hierarchy (and a screenshot where `capabilities.screenshots` allows) and check
   each oracle clause in turn. A clause that fails is a finding: `source: "model"`,
   `phase: "focus"`, and cite which clause failed in `detail` — "cart retained 3 of 5 items after
   a 30s background" is a finding; "backgrounding seemed fine" is not a result.
   **Run §3a.4's health check right after the injection**, before anything else: these conditions
   are the most likely in the whole run to kill or hang the app, which is exactly why they're
   worth injecting.
5. **Record the edge** with `phase: "focus"` and `focusArea: "<id>"`, so the report can show
   focus-area coverage as its own axis instead of burying it in the goal path.
6. **Restore state and continue.** Get back to the screen you were on and resume §3b toward the
   goal. If the injection left the app somewhere unrecoverable, that is itself a finding — record
   it, then relaunch rather than abandoning the run.

Budget: **2-4 injections per run.** A focus area is one condition applied at the few screens where
it's meaningful, not a thing to fire on every screen. If the goal has only one state-bearing
screen, one injection is the correct number — say so in close-out rather than padding.

If the run ends without ever reaching a screen the focus area applies to, **say that explicitly in
`run.coverageGaps`**. A charter whose focus area never fired did not test its focus area, and it
must not report as though it did.

## 4. Close out

- MCP `appium_destroy_session(conversationId, errorMessage)` — always, even on failure. One
  TapMind server pins one active session; leaving it alive corrupts the next run.
- Before writing `trace.json`, **double-check every node has a non-null `screenshot`** (see
  §3a.3) — this is the single most common defect in a first pass at this skill.
- Populate `run.runMode` straight from `device-info.json`'s `runMode` (§1) — it was already
  resolved once at preflight; this is a copy, not a re-derivation. Copy `platform`, `deviceKind`
  and the whole `capabilities` block into `run` as well.
- **Record what this target could not check, as `run.coverageGaps`** — a list of one-liners.
  Anything `capabilities` said was `none`, plus any screen where `health-check.sh` returned a
  *NOT checked* note. This is the difference between "we looked and it was clean" and "we never
  looked," and only the run itself knows which one happened. A report that omits this reads as
  the first when it was the second, which is the most misleading thing this skill can produce.
- Populate `run.device` / `run.app` from `device-info.json` (§1), not from memory:
  `run.device = "<avdName or model> · Android <osVersion>"`,
  `run.app = "<appPackage> <appVersionName> (build <appVersionCode>)"` (omit the version parens
  if `new-run.sh` wasn't given a package and couldn't detect one — don't invent a version).
- Populate `run.model` and `run.modelEffort` from `$CLAUDE_EFFORT` and the model name **read via
  Bash (`echo $CLAUDE_EFFORT`), not from memory** — don't self-report these; a prior run recorded
  `modelEffort: "medium"` when the user had actually set it to low, because the model guessed
  instead of checking the env var that was sitting right there.
- Populate `run.tokenUsage` / `run.costUsd` / `run.costEstimated` by running
  `python3 assets/session-usage.py` with no arguments — it reads `$CLAUDE_CODE_SESSION_ID` and
  the current working directory itself, finds this session's own Claude Code transcript, sums
  real per-turn usage (deduped by message id), and prices it. This is **exact**, not an estimate
  — set `costEstimated: false` and copy its output straight into `trace.json`. Only if it exits
  with an error (e.g. running outside Claude Code CLI, or an unrecognized model where it can't
  price the tokens) fall back to asking the user for `/cost`'s output, and only if that's also
  unavailable, estimate from step count using the formula in `references/design-notes.md`
  (§ Token cost estimate) with `costEstimated: true`.
- Write `trace.json` (schema in `references/design-notes.md`).
- Bash `assets/render-report.sh <run-dir>` → `report.html`. **Read its stderr** — it warns on
  unreferenced screenshots, an empty `pagesource/`/`findings/` despite several steps (the loop
  was abbreviated somewhere), and `source:"lint"` findings with no `lint.py` output to back them.
  Treat every one of these as a bug to fix before handing the report over, not as noise.
- Tell the user where `report.html` landed; open it if the environment supports it.

## Model

Drive the loop on Sonnet 5 (long-horizon tool use, needs the larger context for a 30+ step run).
**Use default/higher reasoning effort, not low** — this skill is a long procedural checklist
across dozens of tool calls (§3's two-phase loop, the liveness/ANR/vision checks, the close-out
bookkeeping), and the one production incident that skipped most of it traced back to the model
making an ungrounded assumption (wrongly concluding the device was remote) and not cross-checking
it against config it had already read minutes earlier — exactly the kind of lapse lower effort
makes more likely on a long tool-use session. If asked for a cheap smoke variant ("can a user
still log in and reach home?", 8-10 steps), Haiku is fine. Don't switch models mid-run — it
invalidates prompt caching.
