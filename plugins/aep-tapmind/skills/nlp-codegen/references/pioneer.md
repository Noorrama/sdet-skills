# Cluster + pioneer pick

A **cluster** is a group of scenarios that share the **same login → feature-screen
stem**, so one device run can teach transients and labels for all of them. It is
**not** "Driver vs GoFood." Those are different **apps / Gradle modules**.

## Split by module first (not a cluster)

If a plan somehow mixed apps (Driver PAM + GoFood order), that is **two runs**,
not two clusters:

1. `change_context.app` / scenario `platform` + app → TapMind directory
   (`gojek-driver` → `driverApp`, GoFood consumer → `gofood`).
2. Write and MR **inside that module only**.
3. **Then** cluster *inside* the module by flow.

Normal input is already one app per epic (PAM_08 is all `gojek-driver`). You
will almost never see Driver and GoFood in one `automation_scenarios[]`.

## Then cluster by similar flow

Inside one module, group with:

1. `mapped_user_flow.destination_screen` (or the screen the last verify names).
2. Split a destination group when two scenarios share **fewer than half** of
   their non-setup `automation_steps` intents.
   Setup = `loginToDriver` / `loginToCustomer` / `openDeeplink` / mock-location /
   permission lines.

Same destination + same stem = **one cluster** → **one** pioneer (device or
reused `@Test`) **or** one kb-only reference scenario.
Ten Driver BAM cases that all open the same BAM screen and differ on one
assert = one cluster. Profile-banner entry vs catalogue deeplink to the same
intro page stay together: login transients are shared; the entry action is the
delta.

A second destination (e.g. onboarding) in the **same** Driver plan = a second
cluster = a second pioneer. Still `driverApp`, still one MR.

## Pick the pioneer

Inside a cluster, pick **one**:

1. **Longest shared stem.** The scenario whose `automation_steps` cover the
   most of the cluster's common prefix (login → transients → feature screen).
2. Tie-break: `priority_tier` P0 over P1.
3. Tie-break: a case that still **logs in through the app** (so home-level
   transients can fire). A deeplink case is fine **if** it still performs
   backdoor login first — PAM's catalogue test does, and that is how Allow /
   Lewati showed up. Prefer a home-walk only when some siblings never deeplink
   and you need labels on that walk (e.g. the profile banner).
4. Prefer `execution_mode: Automatable` with a non-empty `automation_steps`.

Echo the pick and the reason. If the user names a different pioneer, use theirs.

## What the pioneer is for

The plan JSON will not contain:

```java
runStep("Tap 'Allow' on the phone call permission dialog if visible");
runStep("Tap 'Lewati' on the walkthrough if visible");
```

Those are `origin: "interruption"` (or inserted) rows from the device. The
pioneer is the cheapest way to observe them once and copy the `if visible`
guards onto every sibling.

**`kb-only` does not observe these.** Copy `if visible` only from tests already
in `$MODULE`. Do not invent `Lewati`.

It also yields:

- Real rendered labels (`Lewati`, `Akun`, `Bulanan`) via `suggestedRewrite`
- Direct-API setup that actually ran (`setMockLocation`, `performBackdoorLogin`,
  `updateAppPermission`, `openDeeplink`)
- Scrolls that were required to reveal content

## Reuse beats a second device run

Any of these, if they belong to the cluster's stem, **skip** step-validation
(`reuse-pioneer` or `kb-only`):

- User chose **knowledge base only** — no device; reference scenario is a
  phrasing template from the plan + module tests
- A `@Test` the user pasted (see `examples.md`)
- `trace.json` → `run.tapmindTest` from an earlier step-validation
- An existing method in the module that already has the same login + feature
  deeplink / screen and `if visible` guards (`AgenticTests` PAM catalogue is
  this for PAM)

Run `device-pioneer` only when QA asked for it and nothing proven covers this
cluster's login → feature stem.
