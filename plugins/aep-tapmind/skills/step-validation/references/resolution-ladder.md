# The resolution ladder

How a written step's target gets turned into something tappable, and how to describe the outcome
honestly in the report.

Climb the rungs in order. **Stop at the first rung that resolves.** Record which one it was —
`resolution.rung` is the single most useful column in the report, because it tells the step author
whether their step is robust or accidentally passing.

| # | Rung | Try this | If it resolves |
|---|---|---|---|
| 1 | `hierarchy` | Exact match on visible `text`, `content-desc`, or `resource-id`. Exactly one candidate. | `verdict: "pass"`. No deviation. The step is well written. |
| 2 | `fuzzy` | Case-insensitive, partial, or cross-language match. "profile" → "Akun", "Continue" → "Lanjutkan", "cart" → "Keranjang". Still exactly one plausible candidate. | `pass_with_deviation`, type `reworded-target`, `fault: "authoring"`. Suggest the real label. |
| 3 | `scroll` | Not present in the current dump. Scroll the plausible container (`appium_scroll_on_screen` / `appium_scroll_on_element`), re-dump, re-run rungs 1–2. Up to 3 scrolls in the likely direction, then 2 the other way. | `pass_with_deviation`, type `scroll-needed`, `fault: "authoring"`. Suggest adding an explicit scroll step. |
| 4 | `vision` | Read `screens/step-NN-before.png` and locate the target visually. Read the *file on disk* — never `appium_get_screenshot`. | `pass_with_deviation`, type `vision-fallback`, `fault: "authoring"`. See below. |
| 5 | `coordinates` | Tap the bounds vision produced, via `appium_tap_element_by_coordinates`. | Same as rung 4 — the vision rung is what did the work; coordinates are just how the tap was delivered. |
| — | *none* | Nothing resolved after 2 attempts. | `verdict: "fail"`. Decide `fault` — see "Whose fault" below. |

## Rung 3 is a gate, not an optimisation

**You may not report "the element is not in the hierarchy" until the scroll rung has failed.**

The overwhelming majority of apparently-missing elements are simply below the fold. If those get
written up as vision fallbacks, the report cries wolf: the author reads "your step can't be
resolved from the hierarchy," rewrites a step that was perfectly fine, and stops trusting the
tool. The distinction the report is selling is precisely *"addressable vs not addressable"* — it's
worthless if rung 3 leaks into rung 4.

`scroll-needed` is still useful feedback in its own right: the step assumed the target was
visible, and it isn't. That's a real (small) defect in the step list.

## Rung 4: always explain *why* the hierarchy failed

A vision fallback without a diagnosis is half a finding. Before writing the step record, look at
the dump and name the cause:

| Cause | What the author sees in the dump | What to write |
|---|---|---|
| No accessibility label | `clickable="true"` node with empty `text` and `content-desc` | "The account icon has no `content-desc` — nothing in the hierarchy to match on." Cross-reference lint's `missing-a11y-label` finding for this element and cite its id. |
| Custom-drawn / Canvas | a single large `View`/`SurfaceView` covering the region | "This screen is custom-rendered; individual controls don't appear as separate nodes." |
| WebView | `android.webkit.WebView` in the ancestry | "Target is inside a WebView — try `appium_switch_context` to the web context before falling back to vision." Attempt the context switch *before* rung 4. |
| Label differs from what's rendered | `content-desc` says something unrelated to the visible text | Quote both. The author should target the `content-desc`. |
| Genuinely absent | nothing near those bounds at all | The element may be conditional. Note what the screen actually offers instead. |

The lint cross-reference matters: `missing-a11y-label` is an **app** accessibility bug as well as
an authoring problem. Raising it as a finding gives the author something concrete to hand the app
team, and if it gets fixed their original step starts working as written. Say that in the report.

## Attempts and the retry budget

- 2 attempts per step, total, across the whole ladder.
- Attempt 2 must **re-resolve down the ladder** — a fresh dump, a fresh match. Repeating the
  identical tool call with the identical `elementId` is not a retry; element ids are regenerated
  on every `get_view_hierarchy` and a stale one is a different bug.
- A step that succeeded only on attempt 2 is `pass_with_deviation`, type `retry-needed`. Say what
  changed between the attempts — that's usually a timing/flakiness signal worth reporting.
- After 2 failed attempts: `verdict: "fail"`, and the run **stops** (actions only — a failed
  *assertion* doesn't stop the run; see SKILL.md §4).

## Whose fault

`fault` drives which half of the report a row lands in, so get it right.

**`fault: "authoring"` — the step needs rewriting:**
- target named by a label the app doesn't use
- element real, but below the fold, and no scroll step was written
- element real, but unaddressable from the hierarchy (the *step* must change even though the
  underlying cause is an app a11y gap — raise both)
- a required step is missing from the list
- an assertion too vague to evaluate

**`fault: "app"` — the step is fine, the app is broken:**
- element resolved and was tapped, but the screen didn't change after 2 attempts (dead control)
- the app crashed or ANR'd
- an assertion resolved cleanly and is genuinely false (wrong total, unchecked checkbox,
  missing error message)
- navigation landed somewhere other than where the control claims to go

**`fault: null`** — clean `pass`, or an `interruption` row with `impact: "neutral"`.

When both are true — a vision fallback caused by a missing `content-desc` — set
`fault: "authoring"` on the step (that's the actionable fix for the person reading) **and** raise
a separate `fault: "app"` finding for the a11y gap. The report shows both.
