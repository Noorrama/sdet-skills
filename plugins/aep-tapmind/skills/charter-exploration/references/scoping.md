# Phase A — scoping protocol (run this inside the scoping sub-agent)

This file is the sub-agent's whole brief. The parent thread never reads it and never sees a raw
BrowserStack payload.

## Why a sub-agent at all

Measured, not theoretical: a single `listFolders(PR-176)` call returns **~6k tokens** — the BS MCP
prints a human-readable summary *and* the full raw JSON of every folder, duplicated. PR-176 has 36
top-level folders, and cases live several levels down (`Transport - 4W` alone has 37 sub-folders).
A realistic scope walk is 5-15 such calls. Left in the main thread that is 30-90k tokens spent
before a single charter exists, and it makes the skill unrunnable on a smaller model.

So: the scoping agent absorbs all of it in throwaway context, writes `source-cases.json` to disk,
and returns **only a compact digest** (target: under 2k tokens). Everything downstream reads the
file, not the payloads.

## Steps

### 1. Resolve the folder(s)

`listFolders(project_identifier)` once for the top level.

The user's word for an area rarely maps to exactly one folder. "Transport" in PR-176 matches seven:
Partnership, GoCorp, Iron Bank and Growth, Booking Experience, Journeys, 2W, 4W. **Do not silently
pick one, and do not silently take all seven** — the first invents scope, the second explodes it.
Return the candidate list in the digest with case counts and let the parent confirm with the user.

If the user named something unambiguous ("GoFood - Group Order"), match it and move on.

Prefer folders with a non-zero `cases_count` somewhere in their subtree. A top-level folder showing
`0 case(s), 21 sub-folder(s)` is a container, not an empty area — descend it.

### 2. Descend to where the cases are

`listFolders(project_identifier, parent_id=<id>)` for each candidate.

Bounded walk — this is the step that runs away if you let it:
- **Depth 2 below the chosen top-level folder**, no further.
- **Stop descending a branch once you have found cases in it.**
- **Hard cap 12 `listFolders` calls total.** If you hit it, stop and say so in the digest;
  a partial scope the user can widen beats a scope walk that eats the budget.

### 3. Fetch cases

`listTestCases(project_identifier, folder_id)` per resolved folder.

- **Never call `listTestCases` without a `folder_id`.** Project-wide on PR-176 is thousands of
  cases and will blow the sub-agent's own context, not just the parent's.
- Page (`p`) only while cases remain **and** you are under **200 cases total**. 200 is far more
  than charter synthesis can use; past that you are paying for cases that will never be cited.
- If a folder returns more than 200, take page 1 and record `truncated: true` for that folder. Say
  it in the digest — the user may want a narrower folder.

### 3.5 Apply the selection strategy

The parent passes a `strategy`. It decides *which* cases become charter material — the other axis
from `focus_area`, which decides what condition to push them under. Default is `all`.

**All filtering except `priority` happens client-side, in this sub-agent.** `listTestCases`
supports only `case_type`, `priority` and `p` as server-side filters — everything below is
computed from fields in the response. That's fine: you already have the payload, and the parent
never sees it.

**Field reference — verified against PR-176, not assumed:**

| Field | Values seen | Used by |
|---|---|---|
| `priority` | `P0`…`P3` | `priority` |
| `status` | `Active` | every strategy — **drop non-Active cases always** |
| `automation_status` | `automated`, `not_automated` | `coverage-gap` |
| `last_updated_at`, `created_at` | ISO8601 | `recently-changed` |
| `tags` | `AI Generated`, `AI Generated Details` | `stale-docs` |
| `preconditions`, `steps[].step`, `steps[].result` | free text, sometimes empty | `stale-docs` |
| `custom_fields[]` | see below | `coverage-gap`, `stale-docs` |

`custom_fields` is a name/value list, Gojek-specific and richer than `automation_status`:

- `Android Automation Status v2` / `iOS Automation Status v2` — `ID Automated`,
  `ID Pending Automation`
- `Android Automatable` / `iOS Automatable` — bool
- `Execution Mode` — `Automatable`, `Manual`
- `Platform` — `["Android", "iOS"]`
- `TapMind Automated` — bool
- `Reviewed` — bool
- `Country v2` — `["Indonesia"]`

**The per-platform status is the important one.** A case can be automated on Android and pending
on iOS. So a coverage gap is platform-specific, and a run targeting iOS should be selecting iOS
gaps — the top-level `automation_status` alone flattens that distinction and will point charters
at the wrong cases.

#### The strategies

| `strategy` | Keep a case when | Notes |
|---|---|---|
| `all` | always | current behaviour; the default |
| `priority` | `priority` in P0/P1 | filter server-side via `listTestCases(priority=...)` — cheaper than fetching everything |
| `coverage-gap` | the run's platform is `Pending Automation`, **or** `automation_status == "not_automated"`, **or** `Execution Mode == "Manual"` | **the PRD's M1 starter.** Prefer the platform-specific custom field; fall back to `automation_status` when it's absent. Combine with `priority` for the PRD's actual ask ("P0/P1 manual + pending automation gap") |
| `stale-docs` | any of: a `steps[].result` is empty or holds placeholder text (`<Yet to add`, `TBD`, `TODO`); `preconditions` is null/empty; `tags` contains `AI Generated` and `Reviewed` is false | under-documented cases. The PRD cites C4601439/438/434 with literal `<Yet to add from gfpc>` in expected results — this finds that class. An unreviewed AI-generated case is documentation nobody has checked |
| `recently-changed` | `last_updated_at` within N days (default 30) | uses the real per-case timestamp; no snapshot needed |
| `folder-diff` | the case or its folder is absent from the previous snapshot | new/changed areas. Run `assets/folder-diff.py` — see below |
| `recent-failures` | — | **not implemented.** Needs `listTestRuns`/`fetchBuildInsights`, a different API surface, and it is unresolved whether the signal lives in test-management runs or App Automate builds. Say so rather than approximating it |

Strategies **combine** — the parent may pass several, and a case is kept if it satisfies all of
them (intersection, not union). `priority` + `coverage-gap` is the recommended starting pair.

**If a strategy selects zero cases, say so in the digest and stop.** Do not silently widen to
`all` — "there is no P0/P1 automation gap in this folder" is a real and useful answer, and
quietly substituting a different selection produces charters the user didn't ask for.

Record on each kept case which strategies matched it (`selectedBy`), so a charter can cite why
its sources were chosen.

#### `folder-diff`

Bash `python3 assets/folder-diff.py <project> <run-dir>` after writing `source-cases.json`. It
compares against a snapshot at `~/.tapmind/bs-snapshots/<project>.json` and rewrites the file
keeping only new/changed cases, then updates the snapshot. First run has no baseline: it says so
and keeps everything.

This is deliberately not built on folder timestamps — `listFolders` returns none. Diffing the
persisted case list is more robust anyway and catches *changed* cases, not just new folders.

### 4. Compact and write `source-cases.json`

This is the contract with phase B. One line of *summary* per case — plus, and this part is not
optional, the **concrete artifacts copied verbatim**.

```jsonc
{
  "project": "PR-176",
  "projectName": "...",
  "folders": [ { "id": 30304164, "name": "Transport - 4W", "path": "Transport - 4W / Booking",
                 "casesFetched": 41, "truncated": false } ],
  "casesIngested": 41,
  "cases": [
    { "id": "TC-1234",              // BrowserStack's own identifier, verbatim
      "title": "...",
      "folder": "Transport - 4W / Booking",
      "priority": "P0",             // omit if BS didn't give one — never invent
      "type": "functional",
      "automated": false,
      // Per-platform, from custom_fields' "<Platform> Automation Status v2". A case can be
      // automated on one platform and pending on the other; the top-level automation_status
      // flattens that and will point charters at the wrong cases.
      "automationStatus": { "android": "ID Automated", "ios": "ID Pending Automation" },
      "executionMode": "Manual",    // custom_fields "Execution Mode"
      "tapmindAutomated": false,    // custom_fields "TapMind Automated"
      "lastUpdatedAt": "2026-07-09T11:41:22.000Z",
      "selectedBy": ["priority", "coverage-gap"],   // which strategies kept this case
      "gist": "One sentence: what this case actually exercises, from its steps/preconditions.",
      "artifacts": ["gojek://gocar", "CONCURRENT_BOOKING_THRESHOLD", "GoPay balance < fare"],
      "observed": "Toast re-appears when Give Feedback is tapped a second time.",
      "tags": ["payment", "cancellation"] }
  ]
}
```

**`artifacts` — the field that makes charters actionable.** Copy verbatim, never paraphrase, up to
~6 per case. Anything an explorer could not guess and would otherwise have to invent:

- deep link URIs (`gojek://gocar`, `gojek://gofood/aos?order_id=`)
- config / flag / BCS keys (`exp_schedule_booking_revamp`, `max_scheduled_rides`)
- named account or data states (`expired card`, `blocked wallet`, `zero GoPay balance`,
  `first-time canceller`, `MAF auto-accept merchant`)
- concrete thresholds and values (`50 m`, `1 km`, `4 active bookings`, `100% voucher discount`)
- exact UI copy or labels a check depends on (`"Batal gratis"`, label `Home`/`Work`)
- API/screen names the case pins (`orderbff history API`, `AOS`)

Omit the field entirely when a case genuinely has none. Do **not** pad it with generic app
vocabulary — `["booking", "payment"]` is noise and costs tokens for nothing.

**`observed` — only when the case body describes an actual defect or a known-flaky behaviour**
(wording like "note that", "currently", "bug", "should not but does"). One sentence, close to the
source's own words. Omit otherwise. This is what lets phase B write risk areas that are *grounded
in the corpus* instead of hypotheses, which is the single biggest quality difference between a
charter that finds something and one that goes fishing.

`gist` is the only field you write freely, and it stays capped at one sentence. Do not copy step
bodies into it.

**Why the extra fields don't blow the budget:** they are short, verbatim strings on a minority of
cases, and they replace work phase B would otherwise do badly. A prior version of this skill
capped every case at `gist` alone, and the charters it produced named no deep links, no account
states, and no thresholds — the explorer had to guess them at run time. Compaction that strips the
concrete hooks has optimised away the useful part.

### 5. Return the digest

Return **this and nothing else** to the parent. No case list, no folder JSON, no narration of the
calls you made.

```
project: PR-176 — <name>
resolved folders: <path> (<n> cases)[, ...]
ambiguous: <list of candidate folder names + case counts>   # only if step 1 was ambiguous
strategy: <the strategies applied, or "all">
selected: <n kept> of <n fetched>    # if a strategy ran; say "zero selected" loudly
casesIngested: <n>
truncated: <folders that hit the 200 cap, or "none">
areas: <8-15 area labels you observed across the cases, with a case count each>
themes: <3-6 recurring risk themes visible in the corpus — e.g. "payment method switching",
         "cancellation windows", "driver allocation timeouts">
artifacts: <count of cases carrying artifacts> · <5-10 of the most reusable ones, verbatim>
observed: <count of cases carrying an observed-defect note>
wrote: <run-dir>/source-cases.json
```

The `areas` and `themes` lines are what phase B actually reasons over first, so make them real
observations from the corpus rather than generic app vocabulary.

## Guardrails

- **Only report cases BrowserStack actually returned.** Zero results is a legitimate answer that
  ends the run — never invent cases to have something to synthesise from.
- **Never print or ask for BrowserStack credentials.** Auth is handled at the MCP layer.
- Case IDs are copied verbatim. The whole coverage matrix hangs off them; a reformatted or
  guessed ID breaks traceability silently.
