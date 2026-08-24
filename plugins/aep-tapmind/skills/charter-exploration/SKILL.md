---
name: charter-exploration
description: Turn documented BrowserStack test cases into a set of goal-driven exploratory charters, get them approved, then run each one on a real device via TapMind and report back with traceability to the source cases. Use when someone asks for exploratory testing derived from an existing test suite — "create exploratory charters for GoRide from PR-176", "run 5 exploratory sessions off our Transport test cases", "what do our documented cases not cover" — rather than a single ad-hoc goal (that's goal-driven-exploration) or a written step list (that's step-validation).
---

# Charter-driven exploratory testing (TapMind × BrowserStack)

Fetch a project's documented test cases, derive N **exploratory charters** that probe what those
cases *don't*, stop for approval, then run each approved charter on a real device and report with
a coverage matrix that links every finding back to the BrowserStack cases it came from.

**This skill orchestrates; it does not re-implement.** Each charter is executed by invoking
`aep-tapmind:goal-driven-exploration` as a bounded sub-run. That skill owns the device loop, the
anomaly checks, and the per-charter journey graph. Nothing here changes its behaviour.

**Deterministic, not random.** Every charter traces to at least one fetched case. Same project,
same folder, same N ⇒ substantially the same charters. A charter that cites no source case is an
invented charter, and `render-charters.py` rejects the plan.

## Token discipline — read this first

This skill is the most expensive of the three, and most of the cost is avoidable. Three rules:

1. **BrowserStack payloads never enter this thread.** One `listFolders` call is ~6k tokens (the
   MCP prints a summary *and* the raw JSON). Phase A runs in a sub-agent that returns a ~2k digest.
2. **Each charter runs in its own sub-agent.** A 10-charter suite must not accumulate ten runs'
   worth of view hierarchies here. The parent holds charter specs and returned verdicts, nothing
   more.
3. **Never compute what a script computes.** Findings roll-ups, the coverage matrix, cost totals,
   `charters.md`, the HTML — all scripted. Don't sum a column by hand or hand-write markdown.

Held correctly, the parent thread stays small enough for Sonnet to drive.

## Phases

A scope → B synthesise → C **gate** → C.5 assign (agent / manual) → D execute → E report →
F write-back (only on explicit request) → G archive.

---

## A. Scope — resolve project, folders, cases

Ask for what you need in **one** message, not four:

> "I'll pull the documented cases and derive charters from them. I need:
>  **1.** BrowserStack project id (e.g. `PR-176`)
>  **2.** the area — product, folder, or feature
>  **3.** how many charters (5 is a good default; 10 for a broad sweep)
>  **4.** run mode + theme — local device or BrowserStack, light / dark / both
>  **5.** selection strategy — which cases to draw from. Default `priority` + `coverage-gap`
>     (P0/P1 that are still manual or pending automation). Others: `stale-docs`,
>     `recently-changed`, `folder-diff`, or `all`."

On strategy, recommend rather than survey: **`priority` + `coverage-gap` is the right default** —
it targets exactly the risk the documented suite is not covering, and it's what the source PRD
asks for as its first milestone. Reach for the others when the user has a reason.
`recent-failures` is named in the PRD but **not implemented** — say so if asked rather than
approximating it from build data.

Strategies **intersect**: a case must satisfy all of them. Pass them through to the sub-agent
verbatim and record them in `run.strategy`.

Then scaffold and scope:

- Bash: `assets/new-charter-run.sh <slug>` → run dir. (No device gate here — this phase touches
  nothing. `goal-driven-exploration`'s own preflight handles the server and device checks in
  phase D, where they matter.)
- **Agent (Task) tool → a `general-purpose` sub-agent.** Give it the project id, the area, the run dir,
  and the full contents of `references/scoping.md` as its brief. It returns the digest only.

If the digest reports the area was **ambiguous** (e.g. "Transport" matches seven folders in
PR-176), put the candidates and their case counts to the user and let them pick before synthesis.
Don't pick for them — scope chosen wrong wastes the entire run.

If the digest reports **zero cases**, stop. Say so. There is nothing to derive charters from, and
inventing them would defeat the point of the skill.

If the digest reports **zero *selected*** (cases were fetched, but the strategy kept none), that is
also a stop — and a genuinely useful answer: "this folder has no P0/P1 automation gap." Report it
as a finding about the corpus, offer to widen the strategy or the scope, and **don't quietly fall
back to `all`** — that produces charters the user didn't ask for against risk they didn't pick.

## B. Charter synthesis

Read `references/charter-grammar.md` and `<run-dir>/source-cases.json`. Write
`<run-dir>/charters.json`:

```jsonc
{
  "run": {
    "id": "<run dir basename>", "createdAt": "<ISO8601>",
    "project": "PR-176", "projectName": "...", "scopeLabel": "Transport - 4W",
    "folders": [ { "id": 30304164, "name": "Transport - 4W" } ],
    "casesIngested": 41, "requested": 5,
    "runMode": "local", "themes": ["light"],
    "budget": { "perCharterSteps": 30, "perCharterMinutes": 12 }
  },
  "charters": [ /* see references/charter-grammar.md for every field */ ]
}
```

**The generation rule is `charter = one documented flow × one focus area → one question`.** Both
halves are required — the flow gives the charter real artifacts to name, the focus area gives it a
single risk axis and, with it, a runnable size. See `references/charter-grammar.md`.

Four things decide whether a charter is actually runnable, and all four are easy to skip:

- **`probes`** — 3-6 concrete openers naming real artifacts from `source-cases.json` (the deep link
  URI, the config key, the account state, the threshold). Without them the sub-run invents its own
  entry points and skips the charter's real subject. A charter about deep links that never names a
  URI will not open one.
- **`focus_area`** — exactly one id from
  `goal-driven-exploration/references/focus-areas.md`. **Check its availability table against this
  run's target before choosing**: `permission-denial` is Android-only, `network-loss` /
  `orientation` / `locale-switch` need a local Android device, and `token-expiry` has no confirmed
  lever at all. A charter whose focus area can't fire on the chosen target will run, find nothing,
  and report as covered.
- **`oracle`** — 2+ concrete clauses stating what must be true once the focus area is applied.
  Without one, a manual tester reports "seemed fine" and the agent has no basis to call anything a
  bug. Start from the focus area's own oracle and specialise it to this flow.
- **grounded `risk_areas`** — quote and cite the source case wherever one carries an `observed`
  note; prefix everything else `Hypothesis:`. A list that mixes the two silently reads as evidence
  when half of it is guesswork.

Then Bash `python3 assets/render-charters.py <run-dir>`. It validates and writes `charters.md`.
**Fix what it rejects; don't work around it.** Its checks are the ones that keep this skill
honest — charter form, at-least-one source case, at-least-two concrete probes, a known
`focus_area`, a 2+ clause `oracle`, no duplicate ids, and no two charters in the same
`area` × `focus_area` cell.

Two rejections have a specific fix that isn't "edit the field":

- **timebox outside 15-30 steps / 8-20 min** → the charter is trying to answer more than one
  question. **Split it into two charters with different focus areas.** Do not shorten the mission
  to fit; that produces a charter that reads small and still isn't.
- **duplicate `area` × `focus_area` cell** → move one charter to an empty cell of the grid. Same
  budget, real extra coverage.

## C. Approval gate — hard stop

**Zero device actions before the user says go.** No `start_appium_session`, no `new-run.sh`, no
TDP call. If you have touched a device by this point, the gate has failed.

Show the `charters.md` table (not the whole file — the run dir has it) and ask:

> "N charters, ~M minutes total, in `<run-dir>/charters.md`. Run them all, a subset, or do you
>  want to change any first?"

Settle here, and record into `charters.json`:

- which charters to run — `assets/charter-status.py <run-dir> <id> approved|dropped`
  (**drop, never delete**; the report's "Not covered" section names what was dropped, and a
  deleted charter can't be named). Use the script rather than hand-editing `charters.json` — it
  changes one field and can't clobber the user's other gate edits.
- order — reorder the array; execution follows it
- timeboxes — any the user wants changed
- run mode, theme, and any `data_needs` overrides
- **the test-data asks.** `charters.md` now has a Test data table grouping charters by recipe.
  Every recipe in `references/test-data-recipes.md` is marked unverified until a real run confirms
  TDP can satisfy it — say so here and let the user correct an ask *before* a device is
  provisioned against it. Also flag any `preconditions` naming a data state TDP has no lever for
  (an expired card, a blocked wallet, a manual-accept merchant): those are charters to drop now,
  not to run hopefully.

Re-run `render-charters.py` after **any** edit — including a mission the user rewrote, which still
has to pass the charter-form check.

Then render the plan-state report once so the user has it before anything runs:
Bash `assets/render-report.sh <run-dir>`.

## C.5 Assign each charter — agent or human

Release QA is mostly manual, and TapMind's NLP fidelity against generated charters is still
unvalidated (the source PRD's own first open question). So don't assume every charter runs as a
sub-agent. Ask once:

> "Which of these should I run on the device, and which go to a tester as a runsheet? Splitting
>  them is normal — and if you want a fidelity check, assign the same charter to both."

- `assets/charter-status.py <run-dir> <id> --assign agent|manual` per charter. Default `agent`.
- For the manual ones: Bash `python3 assets/render-runsheet.py <run-dir> [ids...]` →
  `runsheet.html`, a printable sheet per charter with the focus area expanded into literal device
  steps, the oracle as a tick-list, and a blank observation table. Charters are grouped by test-data
  recipe so a tester provisions once per group.
- When a sheet comes back: `python3 assets/import-observations.py <run-dir> <id> <obs.csv>
  [--tester NAME] [--verdict ...] [--minutes N]`. It writes a `trace.json` in the same shape an
  agent run produces, so `aggregate.py` folds it into the same report and the same coverage grid.
  Observations mentioning a crash or freeze are promoted to stability findings automatically —
  that's the number the suite is judged on and a human's wording shouldn't bury it.

**Assigning the same charter to both agent and tester is the cheapest way to measure TapMind's
execution fidelity** — the PRD's M1 definition of done asks for exactly that, and this is how you
get it without building anything extra: two traces, one charter, compare the findings.

A manual charter left in `running` is a runsheet still out with a tester; `--recover` deliberately
leaves those alone rather than marking them aborted.

## D. Execution — one sub-agent per charter, in order

**Sequential.** Not a budget choice: one TapMind server pins one Appium session, so two charters
cannot run at once against the same server. (A `--parallel` mode would need one server per
concurrent charter; out of scope here.)

**Order by `data_needs.recipe`, not by charter id.** Run every charter sharing a recipe
back-to-back so one TDP provisioning serves all of them. Provisioning is the fixed cost of a
15-minute charter — amortised across three, it's what makes charters this size economical, and
for a manual runsheet (phase C.5) it's the difference between one setup and three. `charters.md`
already groups by recipe in its Test data table; follow that grouping. Within a recipe group,
keep priority order.

**Before the first charter, always** Bash `assets/charter-status.py <run-dir> --recover`. If a
previous suite was killed or crashed mid-charter, a charter is still marked `running`; it counts as
pending forever and understates what the report says was not covered. `--recover` resolves each one
against what is actually on disk. This costs one call and has caught a real dead run.

For each `approved` charter, in array order:

1. `assets/charter-status.py <run-dir> <id> running`
2. **Agent (Task) tool → a `general-purpose` sub-agent**, one per charter. Its prompt must carry
   everything the sub-run needs, because it cannot come back and ask:

   - Invoke `aep-tapmind:goal-driven-exploration` with the charter's **`mission` as the goal**.
   - Slug: `<charter-id>-<area-slug>`.
   - Budget: the charter's `timebox.steps` / `timebox.minutes`, overriding that skill's 60/25
     default.
   - **Pre-answer all four of its §0 inputs** — location, test data (the resolved recipe's TDP
     `message`, verbatim), backdoor login (always), theme — so it never blocks on a question no
     one is there to answer. This is the most common way a charter sub-run stalls.
   - **Pass `probes` verbatim** as the concrete openers, and say they are openers to go *past*,
     not a script to execute. This is the field that stops the sub-run inventing its own generic
     entry points and skipping the charter's actual subject.
   - **Pass `focus_area` and `oracle` verbatim**, and point the sub-run at
     `goal-driven-exploration/references/focus-areas.md` §3c. Without the focus area it runs a
     plain goal-driven exploration and the charter's whole risk axis goes untested — the run will
     still return a verdict, which is what makes this failure quiet. Say explicitly: *inject this
     condition at the state-bearing screens, evaluate each oracle clause, and if you never reach a
     screen it applies to, record that in `run.coverageGaps` rather than reporting it as covered.*
   - Pass `preconditions` (including how to reach the area cheaply — deep link beats a ten-tap
     walk) and `out_of_scope` (so it doesn't wander into another charter's territory).
   - **If TDP returns data that doesn't match the recipe's ask, abort the charter** — do not
     substitute a different customer to keep going. Findings from the wrong data look real and
     aren't. Say this in the prompt; it is not the sub-run's default instinct.
   - Return **only**: the run dir path, the verdict, one line per finding, and which `probes` it
     actually got to. Not the trace, not the hierarchies, not a step log.
3. `assets/charter-status.py <run-dir> <id> <status> <charter-run-dir>`:
   - `done` — ran to a verdict
   - `timeboxed` — hit the step/minute budget mid-charter
   - `aborted` — couldn't run at all (device gone, TDP data wrong or missing, session wouldn't
     start, the run was killed)

   The script warns if you mark `done`/`timeboxed` with no trace on disk to back it. Heed it: a
   false `done` renders as covered-and-clean, which is the worst thing this report can say.
4. Bash `assets/render-report.sh <run-dir>` — **after every charter, not at the end.** This is
   what lets the user open the report while charter 4 of 10 is still running. It costs one script
   call.
5. State clean between charters is `goal-driven-exploration`'s own contract (it destroys its
   session and relaunches the app per run) — don't add your own teardown on top.

If a charter aborts, continue to the next one. One bad charter is a row in "Not covered", not the
end of the suite. If **three in a row** abort, stop and tell the user — that's an environment
problem, and burning the remaining charters against it helps nobody.

## E. Report

`assets/render-report.sh <run-dir>` → `report.html`, already current from phase D. Run it once
more at the end so `run.complete` flips.

It renders: the mission brief; the **coverage matrix** (area × charters × source case ids ×
findings, cold rows flagged); each charter expandable with its mission, verdict, *budgeted vs
actually explored*, journey strip, findings, and a link to that charter's own full
`goal-driven-exploration` report; and **Not covered** — dropped, timeboxed, aborted, not-run, and
cold areas.

**Read the script's stderr.** A `WARNING: <id> ran but its trace could not be read` means that
charter's findings are silently missing from the matrix — fix it before handing the report over.

Tell the user where `report.html` landed. When summarising in chat, lead with the coverage matrix
and the "Not covered" section, not the finding count — what the run *didn't* establish is the part
a reader can't reconstruct for themselves.

## F. Write-back to BrowserStack — plan first, then ask, then post

Posting into BrowserStack is **outward-facing and effectively irreversible**: a test run in a
shared project is visible to the whole team and can't be quietly undone. So it is never automatic,
never inferred from "the user asked for exploratory testing", and never done in bulk without
review. **Only run this phase if the user explicitly asks for write-back.**

1. Bash `python3 assets/writeback-plan.py <run-dir>` → `writeback-plan.json`. **This calls nothing
   and writes nothing to BrowserStack.** It computes what *should* be posted: an `addTestResult`
   per source case a charter actually exercised, a proposed defect per high-severity finding, and
   any documentation gaps found along the way. Charters that didn't run are listed under
   `skipped` and never get a result — a result posted for a charter that didn't run is a false
   coverage claim inside the system of record, which is worse than no entry.
2. **Show the user the counts and ask.** Name the project, the number of results, the number of
   defects, and the cases affected:
   > "This would post N results across M cases in PR-176 and file K defects. Nothing has been
   >  written yet. Post all of it, a subset, or shall I leave the report as-is?"
   Wait for a clear yes. Approval for one suite is not approval for the next one.
3. Post **only what was approved**, one call at a time — `createTestRun` once for the suite, then
   `addTestResult` per approved entry. Report what landed. If a call fails, stop and say so rather
   than retrying blind; a partially-written run needs a human to look at it.
4. `updateTestCase` for a documentation gap (a `<Yet to add from gfpc>` placeholder in an expected
   result, missing preconditions) is a **separate ask**, per case, with the proposed text shown
   first. This edits someone else's test case — it is the most intrusive thing in this phase, and
   the fact that the run found the gap doesn't authorise fixing it.

**Carry the coverage gaps into the comment.** If the run couldn't execute lint or crash detection
on its target, a `passed` result is narrower than it reads, and the comment must say so. Posting an
unqualified pass from a run that couldn't check half of what it implies is the one outcome that
makes this whole practice less trustworthy than not writing back at all.

## G. Archive the evidence

Bash `../goal-driven-exploration/assets/archive-run.sh <charter-run-dir> <charter-id>` per
executed charter (the script lives with the skill that produces the evidence). It bundles `logs/`, `screens/`, `pagesource/`, `findings/` and `trace.json`
into `~/tapmind-runs/_archive/<charter-id>-<timestamp>.tar.gz` with a sidecar manifest carrying
the verdict, focus area, findings and coverage gaps.

Default retention is 90 days — about one release cycle plus slack — which is what lets a "worked
fine but felt slow" observation be revisited when a related crash surfaces weeks later. Prune with
`--prune` when disk matters; an unreadable manifest is never grounds for deleting evidence.

## Model

Parent thread on Sonnet is the design target — that's what the sub-agent boundaries buy. Phase B
(synthesis) is the one reasoning-heavy step; if charters come back thin or duplicative, that's the
step to re-run at higher effort, not the whole skill. Charter sub-runs inherit
`goal-driven-exploration`'s own guidance: default or higher effort, never low.
