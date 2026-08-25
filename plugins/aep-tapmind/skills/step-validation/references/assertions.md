# Validating assertion steps

Assertion steps are the ones that read like *"verify X"*, *"check that Y"*, *"the total should
be Z"*, *"ensure the button is disabled"*. They are where most genuine app bugs surface, so they
get real validation — never a glance and a shrug.

## The rule that matters most

**Evidence is mandatory.** Every assertion record carries `assertion.evidence`: the raw hierarchy
line, the attribute value, or a description of the screenshot region it was judged from. If you
cannot produce evidence, the assertion is **unresolvable** — not passed. Record
`verdict: "fail"`, `fault: "authoring"`, and say what you couldn't find.

`"the checkbox looked checked"` is not evidence.
`element_44 CheckBox checked="false" [64,1188][112,1236]` is evidence.

## Prefer the hierarchy; fall back to vision only for visual claims

Set `assertion.method` to `hierarchy` or `vision` so the report can show which. The same honesty
rule as the resolution ladder applies: a hierarchy-verified assertion is stronger than a
vision-verified one, and the author deserves to know which they got.

| Assertion shape | Method | How |
|---|---|---|
| "X is visible" / "X is shown" | hierarchy | Node exists with non-zero bounds inside the viewport. Bounds `[0,0][0,0]` or off-screen ⇒ present in the tree but **not visible** — that's a fail, and a subtle one worth spelling out. |
| "X is not visible" / "no error is shown" | hierarchy | Absence in the dump. Scroll first if the container is scrollable — "not visible" and "below the fold" are different claims. |
| "the checkbox is checked" / "the toggle is on" | hierarchy | `checked` attribute. If the dump renders it ambiguously, confirm with `appium_get_element_attribute(elementId, "checked")`. |
| "the button is disabled/enabled" | hierarchy | `enabled` attribute — **not** `clickable`. A node can be `clickable="true"` and `enabled="false"`; asserting on the wrong one is a false pass. |
| "X is selected" | hierarchy | `selected` attribute. |
| "the total shows Rp 56.000" | hierarchy | Exact `text` match after normalising whitespace. Report the actual string verbatim on mismatch — formatting differences (`Rp56.000`, `Rp 56,000`) are themselves findings, but they are *authoring* faults if the step's expected string was sloppy and *app* faults if the app's formatting is genuinely inconsistent with its own conventions elsewhere on the screen. |
| "the field contains X" | hierarchy | `appium_get_value`, not the dump's `text` — an `EditText`'s displayed text can be a hint rather than a value. |
| "the total equals the sum of the line items" | hierarchy + arithmetic | Read every line item and the total, compute, compare. Put the arithmetic in the evidence. |
| "X appears above/below Y" | hierarchy | Compare `bounds` from the uiautomator XML (`get_view_hierarchy` strips bounds). |
| "the banner is green" / "the image loaded" / "the layout isn't broken" | vision | Read `screens/step-NN-before.png` from disk. Genuinely visual — the tree can't answer it. |
| "the screen looks correct" | — | Too vague. `verdict: "fail"`, `fault: "authoring"`. Ask the author what specifically should be true, and say so in `suggestedRewrite`. Do not quietly invent a criterion and pass it. |

## Failed assertions do not stop the run

This is the one exception to the stop-on-failure rule in SKILL.md §2. An action failing means the
screen state has diverged and everything after it is meaningless. An assertion failing means the
app is on the expected screen showing the wrong thing — later steps still test what they claim to.

So: record `verdict: "fail"`, raise a finding, and **continue to the next step**. A run that
surfaces three separate false assertions in one pass is worth far more than one that stops at the
first.

## Fault attribution

Default for a resolved-but-false assertion is **`fault: "app"`**. The author asserted the total
is Rp 56.000; it shows Rp 45.000. Their step is correct. The app is wrong. Do not soften this into
an authoring problem.

`fault: "authoring"` only when the *writing* is the problem:
- names an element that doesn't exist anywhere on the screen
- too vague to evaluate ("looks right", "works properly")
- asserts on the wrong property (`clickable` when they meant `enabled`)
- expected value formatted in a way the app never uses, where the underlying value is correct

Every `fault: "app"` assertion failure also gets a `findings[]` entry with the expected/actual
pair in `evidence`, so it surfaces in the report's app-fault section rather than being buried in
the step table.

## Timing

Assertions run against the state *after* the previous step settled. If an assertion targets
something asynchronous (a toast, a balance refresh, a loading list), give it one bounded wait —
`appium_wait` — re-dump, and re-evaluate before calling it false. Record the wait in
`observation`. One wait, not a polling loop: if the thing needs more than a couple of seconds to
appear, that latency is itself worth reporting.
