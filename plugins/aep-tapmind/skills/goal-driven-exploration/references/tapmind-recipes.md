# TapMind MCP recipes

Exact tool signatures and gotchas for the tools this skill's loop calls most. Full tool list is
resident in every request already (77 `@Tool` methods) — this file is only the parts worth
getting right on purpose.

## Mock location

`appium_mock_location(conversationId, latitude, longitude, reason)` — `reason` is required and
shows up in the tool's own success message, so make it genuinely explain *why* this coordinate
(e.g. "South Jakarta default mock location for this run" or "goal specified Bandung").

Default mock location for this skill, when the goal doesn't name one: **South Jakarta,
-6.2615, 106.8106**. Not read from any TapMind config — it's this skill's own convention, agreed
with the user per run (§0 of `SKILL.md`).

Coordinates must be valid degrees (`lat` in [-90,90], `lng` in [-180,180]) or the tool throws
before it ever touches the driver.

## TDP test data

`tdp_test_data_tool(conversationId, message)` — `message` is described as "Exact test data
query/request from user. Do not modify." Pass the user's own words for what customer/state they
want; TDP's own agent interprets it, retrying up to 3 times server-side before it gives up.

What TDP returns gets **auto-stored** against `conversationId` for later tools to read —
`accessToken`, `refreshToken`, `customerId`, `customerPhone`, `customerEmail`, plus wallet/
booking/driver fields when the response includes them. This is exactly what
`appium_backdoor_login` reads next — no need to copy values around yourself.

If TDP comes back with no customer data at all for a customer-shaped ask, that's a hard failure,
not a "try a different action" moment — surface it to the user rather than improvising a login.

**Group order note:** TDP's data model is per-entity (one customer/driver/booking per response).
For a group order you need data for the host *and* however many other participants the goal (or
the user, once asked — see `SKILL.md` §0.2) calls for. Ask TDP once per participant with a
distinguishing message (e.g. "a second active customer with GoPay balance, different from the
host") rather than assuming one call returns a list.

## Backdoor login

`appium_backdoor_login(conversationId, reason, credentials?)` — skips the login UI entirely.
`credentials` is optional and only needed when you already have `accessToken`/`refreshToken` in
hand directly (e.g. the user pasted them); otherwise omit it and the handler reads whatever
`tdp_test_data_tool` just stored.

**Order matters**: call this *after* the TDP fetch. If no access/refresh token has been stored
for the conversation yet, the underlying handler throws immediately with "accessToken/refresh
token not found. Please generate the data first using TDP tools." — that's not a bug to work
around, it's the intended dependency.

The tool detects the app under test from the driver's bundle/app id automatically and picks the
matching login handler (customer / driver / GoPay merchant) — you don't select which handler.

On Android it overrides the app's stored auth preferences and relaunches via deeplink
(`gojek://gocore/home`); on iOS it opens a signed backdoor deeplink. Both wait up to 30s for a
home-screen element before declaring success — if that wait times out, treat it as a `blocked`
step (home never loaded), not a silent retry.

## Landing on a specific restaurant/merchant (e.g. "Pinky Porky")

There's no dedicated "search restaurant" tool — this is ordinary UI navigation through the loop
in `SKILL.md` §3: reach the GoFood search/home screen, `set_text` the restaurant name into the
search field, `appium_tap_element` the matching result. Treat "restaurant not found in search"
as a goal-blocking finding (`severity: high`, likely `deadend` node) rather than retrying the
same search many times — one retry to rule out a slow-loading list, then stop and report it.

## Dark mode toggle

No TapMind MCP tool for this — it's a plain `adb`/`simctl` call, done once before the run (or
once per theme pass — see `SKILL.md` §0.4), not mid-run.

- **Android 10+**: `adb shell cmd uimode night yes` (dark) / `adb shell cmd uimode night no`
  (light). If `cmd uimode` isn't supported on the target OS, fall back to
  `adb shell settings put secure ui_night_mode 2` (dark) / `1` (light) and relaunch the app.
- **iOS simulator**: `xcrun simctl ui <device> appearance dark` / `appearance light`.
- **iOS real device**: no equivalent public command — this is a known gap; dark-mode testing on
  a physical iOS device needs a manual toggle before the run starts, or BrowserStack's own
  appearance setting if the session supports it.

Toggling relaunches or otherwise disturbs the app's state, so do it once at the start of a theme
pass, not between steps — that's why `SKILL.md` §0.4 has the skill run the whole goal once per
theme rather than switching mid-journey.

## Crash / ANR liveness checks

No dedicated MCP tool — plain `adb`, checked at the start of every new-screen visit (§3a of
`SKILL.md`), not only when a step looks like it failed:

- **Crash**: `adb shell pidof <appPackage>` — empty output means the process is gone. Follow with
  `adb logcat -b crash -d` (the crash-specific logcat buffer, not the main one) to capture the
  stack trace, then `appium_launch_app` to recover the session for the next branch.
- **ANR**: no adb liveness check catches this (the process is alive, just not responding) — the
  signal is the system dialog itself, visible in `get_view_hierarchy`'s text as something like
  "X isn't responding" with "Wait"/"Close app" buttons. Confirm with
  `adb logcat -d | grep -E "ANR in|Input dispatching timed out"` for the evidence to attach to
  the finding.

Both end the current branch as a `deadend` node — don't keep trying the same action against a
dead or hung process.

## Vision review for UI/dark-mode defects

The design doc's screenshots-never-enter-context rule (§2) is about the *driving loop* — it still
holds for the bulk of steps. Vision review (§3a.7 of `SKILL.md`) is a deliberate, narrow
exception, and as of the fallback-gating in §3a.7 it's **conditional, not automatic**: it fires
only for a dark-mode run, an element hierarchy couldn't resolve, a screen that looks transient, or
a screen `lint.py` already flagged — never as a blanket "every new node" pass. When it does fire,
read the already-captured `screens/step-NN.png` with the **Read tool directly on the file path**
— not `appium_get_screenshot`, which re-encodes the same pixels as base64 into context through the
MCP server for no benefit here, and whose temp file is deleted immediately after
(`ScreenshotService.java`). The file is already on disk from the `adb exec-out screencap` you just
ran; reading it directly is strictly cheaper.

Keep this bounded to *new* nodes even when a trigger fires — reviewing every revisit defeats the
point of gating by uniqueness and reintroduces the cost problem the original design was avoiding.
This gating exists because vision review's own image tokens are the single largest per-screen
context cost in the loop (SKILL.md's step-cost model doesn't include it) — once an image is read
into this conversation, every later turn re-sends and re-caches it, so a 25-screen light-mode run
that vision-reviewed every node was paying for ~25 images' worth of accumulated context, most of
which never surfaced a finding. Gating to dark-mode-always plus three narrow fallback signals is
meant to keep the theme-adaptation coverage (the actual point of this step) while cutting that
accumulation on runs where it wasn't earning its cost.

## Payment method fallback (insufficient balance)

Purpose: a goal that reaches checkout should still complete *a* booking when the default/
specified payment method can't cover it, rather than reporting `blocked` — see the **Payment
fallback** bullet in `SKILL.md` §3b for when this applies and how it's bounded (exactly one
switch attempt).

**Detecting insufficient balance** — no dedicated MCP signal; read it from
`get_view_hierarchy`'s text on the checkout/pay screen after the pay action:
- An inline error/toast/modal with copy to the effect of "Insufficient balance" / "Saldo GoPay
  tidak cukup" / a "Top up" prompt appearing where a success state was expected.
- Or the Pay button stays on the same screen with that copy visible nearby instead of navigating
  forward — treat this the same as an explicit error text match, don't wait for a second signal.

**Recovery sequence** (generic — element ids are resolved from the live hierarchy each run, never
hardcoded per the design doc's "skill never computes coordinates" rule):
1. `appium_tap_element` on the payment-method row/selector on the checkout screen (usually shows
   the currently-selected method's name/logo next to or above the Pay button).
2. From the resulting list, `appium_tap_element` on **Cash** ("Bayar Tunai" on `id-ID` locale) if
   present; otherwise the first other available method in the list.
3. Confirm the selection if the list requires an explicit confirm/back action, then re-trigger the
   pay action.
4. Log the edge `outcome: "ok"`, `phase: "goal"`, `note: "Insufficient <method> balance — switched
   to <method> and retried checkout"`.

**Bound**: exactly one switch attempt per checkout. If step 1 finds no payment-method selector, or
step 2's list contains no method other than the one that just failed, stop — file an `outcome:
"blocked"` finding instead (`severity: high` — the goal genuinely can't complete data-as-given).
Don't reopen the selector hoping for a different list; that's the same self-loop pattern §3b's
stuck detection already guards against elsewhere in the run.

## Run modes

**`new-run.sh` resolves `run_mode` for you, once, by reading the active profile directly** — you
should never need to `cat ~/.tapmind/profile.json` yourself or infer the mode from an adb probe.
Read `device-info.json`'s `runMode` field and treat it as fixed for the rest of the run.

This wasn't always true — `new-run.sh` used to just assume local and always gate on `adb`, which
is what led to the incident below. Two real, separate bugs, both now fixed in the script itself
rather than left for the driving model to work around:

1. A run's `adb shell pm list packages | grep <appname>` came back empty (wrong grep pattern or
   serial, not a real signal). The model concluded from that alone that the device must be remote
   on BrowserStack, and silently substituted `appium_get_screenshot` + skipped every adb-dependent
   step for the rest of the run — despite having already read `"run_mode": "local"` from the
   profile minutes earlier in the same session. `new-run.sh` now reads `run_mode` directly and
   only gates on `adb` when it's actually `"local"`, so there's no probe result to misread in the
   first place.
2. `new-run.sh`'s own app-version lookup (`dumpsys package | grep versionName`) could silently
   kill the *entire script* under `set -e -o pipefail` whenever the target app wasn't installed
   on the connected device — `grep` finding no match exits 1, `pipefail` propagates that through
   the pipe, and `errexit` treats even a `VAR=$(...)` assignment as a failing command. No error
   message, just a dead script. Fixed with `|| true` on that specific pipeline; if you're adding
   new adb pipelines to this skill's scripts, assume the same footgun applies.

| | Local Android | BrowserStack |
|---|---|---|
| Screenshots | `adb exec-out screencap -p` — free, full-res | no local `adb`; fall back to `appium_get_screenshot` for **key screens only** (it returns base64 into context — expensive, use sparingly), link the BrowserStack session instead |
| Device logs | `adb logcat -d -t 400` | already on the BrowserStack session; link it, don't try to fetch it |
| Video | none | BrowserStack records it — put the session URL in `trace.run.sessionUrl` |

iOS simulator screenshots: `xcrun simctl io booted screenshot` — same code path as Android
`adb`, different command.

## Session lifecycle

One TapMind server pins exactly one active Appium session. Always `appium_destroy_session` at
the end of a run — including failed ones — before starting the next. Reusing a session across
runs bleeds state (leftover cart items, still-logged-in user) into the next run's trace.
