# Sibling emit from a proven pioneer

The pioneer `@Test` / `run.tapmindTest.lines[]` is the template. Each other
scenario in the cluster is that template with a **delta** applied — not a
fresh wrap of `automation_steps`.

Read `${CLAUDE_PLUGIN_ROOT}/skills/step-validation/SKILL.md` §6 and
`references/direct-api-map.md` for phrasing and the emit ladder. This file only
covers what to copy vs replace.

## Shared (copy onto every sibling)

| Pioneer line `kind` | Rule |
|---|---|
| `direct-api` setup | Copy. Swap `performBackdoorLogin("…")` when the sibling's `test_buddy_prompt` differs. Swap `openDeeplink` / mock location when `preconditions_metadata` differs. |
| `guard` (`if visible`) | Copy at the **same relative position** (after login, before the feature action). This is how Allow / Lewati reach tests the plan never mentioned. |
| Permissions | Copy `updateAppPermission(...)` if the pioneer needed it. |

Never drop a guard because the sibling's `automation_steps` omitted it. The plan
is the source of assertions; the pioneer is the source of transients.

Place `impact: "state-changing"` guards where they fired; `neutral` ones can
sit with the other post-login guards. Never put `if visible` on a required
action — that turns a real miss into a skip.

## Delta (per sibling)

From that sibling's `automation_steps[]` (not `steps[]`):

- **Feature actions** the pioneer didn't take (profile banner tap vs deeplink)
  → extra `runStep` / `openDeeplink` after the shared guards.
- **Assertions** unique to the sibling → `assertStep` / terminal `StepResult`
  per `$SAMPLE_TEST`. Do not copy the pioneer's unique asserts.
- **Flags / toggles** from `preconditions_metadata.active_experiment_flags` →
  module helpers only when `$SAMPLE_TEST` uses them (`DriverToggleSettings`).
- **Given:** if the sibling is an **entry-point** test (banner, tab), keep that
  walk. If it is **screen content**, prefer the pioneer's deeplink when
  `change_context.screens[].deep_links` has one. Don't replace an entry-point
  case with a shortcut.

`loginToDriver(<test_driver_2w>)` in the plan is already satisfied by the
pioneer's `performBackdoorLogin`. Don't emit a second login.

## Labels

| Source | Quotes |
|---|---|
| Pioneer hierarchy match / `suggestedRewrite` | Quote if the pioneer quoted it |
| Pioneer fuzzy match (`profile` → `Akun`) | Unquoted |
| `design_context` copy / module tests / nav_index | Quote only if that source used an exact string |
| `change_context.locator_fallback` | Unquoted |
| Plan English that the pioneer never resolved | **Unquoted.** `id-ID` locale: do not Rule-F quote `'8 level Program Apresiasi Mitra'` |
| Android `resource-id` | Never put in `runStep`. GMT only. |

Unknown label → `// verify once` and a note, or defer that one assertion.
Don't invent Indonesian copy.

Verb-first lines. One verb per `runStep`. `scroll`, not `swipe`, to reveal
content. Prefer `TapMind.scrollToText` / `TapMind.scroll(Direction.RIGHT)` when
the pioneer used the direct API.

## Offline fallback (no device, no proven `@Test`)

Still emit. Harvest guards **only** from existing tests in `$MODULE` that share
this app's login stem. If the module has no such guards, emit none — don't
guess `Lewati`. Mark `validation.mode: generated`. Recommend a pioneer
step-validation as follow-up.

## Ledger (optional)

If the caller is `mobile-test-code-generator`, also write a
`test-code-generator.json` entry per method: `op`, `artifact_ref`,
`nl_steps`, `validation.mode` = `validated_on_device` for the pioneer and
`cloned_from_pioneer` for siblings (`pioneer_scenario_id` set).
