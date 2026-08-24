# Phase B — how to write the charters

Read this once, at synthesis time. Input is `source-cases.json` (from disk — never re-fetch from
BrowserStack) plus the digest's `areas`/`themes` lines.

## The form

> **Explore** \<area or resource\> **with** \<resources, data, constraints\> **to discover**
> \<the information you're after\>.

`render-charters.py` enforces this shape and will reject the plan if a mission doesn't match. That
check exists because the failure mode here is well-known and one-directional: given a pile of test
cases, a model drifts into restating them. Two examples of the same subject:

| Not a charter | A charter |
|---|---|
| Verify the user can cancel a 4W booking before driver allocation. | Explore **cancellation across the whole booking lifecycle** with **a TDP customer and a live allocation** to discover **where the cancel affordance, fee copy, and refund state disagree with each other**. |
| Check that GoPay falls back to cash when balance is insufficient. | Explore **payment-method switching under failure** with **a customer whose GoPay balance is below fare** to discover **whether every entry point to the switcher recovers, and what state a half-switched payment leaves behind**. |

The difference isn't wording. A test case names an expected result and passes or fails. A charter
names a **question** and comes back with information — including information nobody predicted.

## The generation rule — this is what keeps charters small

> **charter = (one documented flow from BrowserStack) × (one focus area) → one question**

Both halves are required, and the product is what makes a charter the right size:

- The **flow** comes from `source-cases.json` — a real journey the corpus documents, with real
  artifacts (deep link URIs, account states, thresholds) to name in `probes`.
- The **focus area** is the condition you inject, from
  `goal-driven-exploration/references/focus-areas.md` — backgrounding, permission denial, deep
  link mid-flow, rapid input. Exactly one. `render-charters.py` rejects anything else.

Applied mechanically, this yields charters that are one question, one setup, one risk axis. Skip
it and synthesis drifts straight back to "explore the whole booking lifecycle."

Look at what the source PRD's own appendix produced without this rule:

| A test plan wearing a charter's clothes | A charter |
|---|---|
| Explore the full delivery ordering journey across resto types (MAF auto-accept, manual-accept, non-MAF) and payment methods (GoPay, Card, PayLater, Cash), probing the driver lifecycle and GoClub accrual. **45 min.** | Explore **what survives backgrounding at each step of GoFood checkout** with **a TDP customer and a full cart** to discover **where cart, address and payment selection are lost on resume**. **12 min**, focus area `lifecycle-background`. |

The first is unfalsifiable: hand it to a release QA and you get a happy path and "looked fine";
hand it to the agent and it spends its budget reaching checkout and probes nothing. The second
can be run by either, in a lunch break, and both come back with comparable findings.

**Size: 15-30 steps, 8-20 minutes.** Enforced. If a charter won't fit, it is two charters — split
it by focus area, not by shortening the mission. A charter that finds nothing should have cost 20
minutes, not 45.

## The oracle — what makes it a test rather than a poke

`oracle` is a list of concrete statements that must be true after the focus area is applied. At
least 2, and they must name something checkable.

This field exists because of how manual exploratory testing actually fails. Without it, a tester
injects the condition, sees the app still standing, and writes "seemed fine" — and an agent has no
basis on which to call anything a bug either. With it, both have a checklist.

| Not an oracle | An oracle |
|---|---|
| App should work correctly after backgrounding. | Cart contents, quantities and item notes are unchanged; selected address and payment method are unchanged; no re-authentication prompt; no duplicate order. |
| Deep link should behave properly. | The deep link lands on AOS from both warm and cold start; back from it returns to the interrupted flow, not out of the app; exactly one draft booking exists afterwards. |

Take the focus area's own oracle from `focus-areas.md` as the starting point and **specialise it
to this flow** — name this charter's actual cart, address, and payment method rather than
restating the generic clause.

## The value-add is gap coverage

If a charter would be satisfied by executing the source cases it cites, it is worthless — those
cases already exist and are probably already automated. Every charter must probe *past* its
sources. Where the gaps reliably are:

- **Between cases.** Cases 12 and 13 each pass alone; nobody documents doing them back to back.
- **Interruption and resumption.** Backgrounding, network loss, a push notification mid-flow,
  process death. Documented cases are almost always uninterrupted happy paths.
- **The error branch of a documented happy path.** The case says "apply a valid voucher"; nothing
  says what an expired one does to the fare breakdown.
- **State left behind.** Cancel, then rebook. Abandon a cart, then return. Documented cases start
  from clean state and rarely check what they leave.
- **Ordering and re-entry.** Reaching the same screen by a different route — deep link, back
  stack, notification tap.
- **Areas the corpus barely covers.** Count cases per area; a thin area with real user traffic is
  a gap that the documented suite is silently declaring low-risk.

State the gap explicitly in `rationale` — "cases TC-x/TC-y cover A and B separately; nothing covers
doing them in sequence" is a good rationale. "This is an important area" is not.

## Probes — the charter's executable half

A mission is a question. `probes` are **3-6 concrete openers** that get an explorer into position
to answer it. Without them the sub-run has to invent its own entry points, and it will invent
generic ones — that is exactly how a charter about deep links ends up never opening a deep link.

Each probe is one imperative sentence naming **real artifacts from `source-cases.json`** — the URI,
the config key, the account state, the threshold. Not "test the deep link". Compare:

| Useless | A probe |
|---|---|
| Explore deep link behaviour. | Open `gojek://gocar` while a GoCar booking is already in FDS, and check where the back stack lands. |
| Check payment fallback. | With GoPay balance below fare, tap Order and follow the insufficient-balance nudge to top-up and back. |
| Verify the picker. | Set `max_scheduled_rides` to its limit, then open the time picker from all three entry points. |

Rules:

- **Every artifact your charter depends on must appear in a probe, verbatim.** If the charter needs
  a deep link, a probe names the URI. If it needs an account state, a probe names it. A charter
  that can't name what it needs is not runnable — it is a wish.
- If `source-cases.json` carries no artifact for something the charter needs, **say so in the probe**
  ("open the GoCar deep link — URI not in the source cases, resolve it at run time") rather than
  inventing a plausible-looking URI. An invented deep link fails silently and looks like a bug.
- Probes are openers, not a script. The explorer is expected to go past them — that's the point of
  a charter. Ordering them cheapest-first (deep link before a ten-tap walk) saves budget.
- `render-charters.py` requires at least 2 and warns below 3.

## Risk areas must be grounded, not guessed

Where a source case carries an `observed` note, the corresponding risk area should **quote it and
cite the case**. Those are defects the corpus already knows about; a charter that re-finds one is
cheap value, and one that goes hunting a risk nobody ever hinted at usually finds nothing.

- Grounded: *"Feedback toast re-appears on a second tap (C4601429 notes this explicitly)."*
- Guessed: *"Feedback submission may be unreliable."*

Guessed risk areas are allowed — a charter probing a genuine gap has no observed note to lean on
by definition — but **mark them**, e.g. prefix with `Hypothesis:`. Mixing the two silently makes
the whole list read as evidence when half of it is speculation. Aim for at least one grounded risk
area per charter whenever the source cases offer one.

## Deduplication

N charters must be N *different questions*, not one question in N costumes. The `area` ×
`focus_area` cell key does most of this mechanically — `render-charters.py` errors on two charters
sharing a cell, so you cannot ship the same question twice under different wording.

That check is necessary, not sufficient. It won't catch two charters in *different* cells that
still walk the same screens with the same data. Before finalising, check every pair: if two would
send an explorer down substantially the same path, merge them and spend the freed slot on an empty
cell of the grid.

## Spreading across the grid

With `area` on one axis and `focus_area` on the other, the plan is a grid and coverage means
filling cells that matter — not stacking charters on the richest area.

At N=5 across a 40-case corpus, prefer **breadth of areas first, then the highest-yield focus
areas**. On yield, from `focus-areas.md`: `deeplink-midflow`, `lifecycle-background` and
`rapid-input` find the most per minute, run on every target, and need no extra tooling. Reach for
`network-loss` or `orientation` only when the run is local-Android and the area genuinely warrants
it — a charter whose focus area can't fire on the chosen target is a wasted slot.

## Prioritising when N is small

The user picks N. At N=5 from a 40-case corpus you are discarding a lot, so rank by:

1. **Blast radius** — payment, auth, and booking-confirmation defects are user-visible and costly.
2. **Corpus thinness** — an area with two documented cases and heavy traffic is under-tested.
3. **Gap richness** — an area where the documented cases are all happy-path has more to find.
4. **Reachability inside a timebox** — a charter that needs 40 steps just to reach its area is a
   poor use of a 30-step budget. Prefer areas reachable by deep link or a short path, and say so
   in `preconditions`.

Spread across areas rather than stacking three charters on the richest one — coverage breadth is
what the matrix is measuring.

## Field-by-field

| Field | Rules |
|---|---|
| `id` | `CH-01`, `CH-02`, … in priority order. |
| `mission` | The charter sentence. Must match the form above. |
| `area` | Short label, reused across charters that share an area — this is the coverage matrix's row key, so keep the vocabulary tight (`Booking`, `Payment`, `Cancellation`), not a per-charter phrase. |
| `focus_area` | Exactly one id from `goal-driven-exploration/references/focus-areas.md`. With `area` this forms the coverage grid's cell key — **two charters sharing both is a hard error**, so a second charter in the same area must pick a different focus area. Check the availability table there first: `permission-denial` is Android-only, `network-loss`/`orientation`/`locale-switch` are local-Android-only, and `token-expiry` has no confirmed lever yet. |
| `oracle` | 2+ concrete clauses: what must be true once the focus area is applied. See above. Specialise the focus area's generic oracle to this flow. |
| `source_test_case_ids` | Verbatim BS ids, from `source-cases.json`. **At least one, always** — a charter with none is an invented charter and the script rejects it. Cite the cases the charter derives from *and* the ones it deliberately goes past. |
| `rationale` | The gap, concretely. See above. |
| `probes` | 3-6 concrete openers naming real artifacts. See above. Minimum 2 enforced. |
| `priority` | `P0`-`P3`. Inherit from the source cases where they agree; explain in `rationale` when you override. |
| `timebox` | `{steps, minutes}`. Default 25/12, bounded 15-30 steps and 8-20 min. Give a charter with a long path to its area more; a deep-link-reachable one less. Becomes the goal-driven-exploration step budget verbatim. Doesn't fit? Split it. |
| `data_needs` | `{recipe, notes}` — recipe name from `references/test-data-recipes.md`, notes for anything the recipe doesn't cover. |
| `preconditions` | What must be true before step 1, including how to *reach* the area cheaply. |
| `risk_areas` | What you expect might break. Quote + cite where a source case has an `observed` note; prefix speculation with `Hypothesis:`. See above. |
| `out_of_scope` | What this charter deliberately won't touch — keeps the explorer from wandering and keeps charters from overlapping. |
| `status` | `proposed` at synthesis. The gate changes it. |

## Sizing the plan against the budget

Sum the timeboxes before presenting. If the total exceeds what the user agreed to, do not silently
trim charters — present the full plan with the overage stated so they choose what to drop. That
choice is theirs; it is exactly what the gate is for.
