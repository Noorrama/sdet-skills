# Anomaly detection

Every finding carries `source` (`lint` | `model` | `kb`) and `confidence` (`high` | `medium` |
`low`) — that's what keeps the report's signal-to-noise defensible.

## Deterministic lint (`source: "lint"`) — `assets/lint.py`, run over every uiautomator XML dump

Zero tokens, byte-identical build-to-build. Reads `pagesource/step-NN.xml` (has element
`bounds`), never `get_view_hierarchy`'s JSON (bounds are stripped server-side).

**Android-local only.** These checks need a bounds-bearing uiautomator dump, which exists only
where `capabilities.pageSource == "uiautomator"`. On iOS and BrowserStack every row below is
unavailable — a real coverage gap that belongs in `run.coverageGaps`, not a silent zero.

| Check | Signal |
|---|---|
| Truncated text | text ends in `…`/`...`, or text bounds exceed the element's own bounds |
| Overlapping elements | two interactive elements with intersecting bounds |
| Missing a11y label | interactive element (`clickable=true`) with no `text`/`content-desc` |
| Missing or broken image | image-class node with zero-size bounds or a placeholder resource id |
| Untranslated string | Latin copy alongside an `id-ID`-locale screen, or a raw resource key (`gofood_cart_title`) leaking into visible text |
| Off-screen interactive element | tappable element whose bounds fall outside the device viewport |

Two checks need cross-step context the script doesn't have on its own — the skill supplies it
from the trace as it runs, not `lint.py`:

| Check | Signal |
|---|---|
| Dead button | tap performed on an element → next hierarchy is byte-identical, no navigation |
| Navigation trap | same node id (by label) revisited 3+ times without goal progress |

## Crashes and hangs (`source: "lint"`) — checked on every new screen in §3a

These are the two failure modes a straight-line, goal-only run is most likely to walk past
entirely — the process can die or hang between two steps that each individually looked fine.
Both are cheap to check (no vision, no reasoning) so there's no excuse to skip them.

**One call does it: `assets/health-check.sh <run-dir> NN <hierarchy-file>`.** It reads
`capabilities` from `device-info.json` and picks the mechanism. Never hand-write the commands
below — they're documented here so you can read the script's output, not so you can reproduce it.

### Detection vs diagnosis

The distinction the report hangs on, and the answer to "can we even do this on iOS?":

- **Detection** — *did the app die or hang?* Needs only process liveness or the view hierarchy.
  **Available on every target**, including BrowserStack and physical iOS.
- **Diagnosis** — *why?* Needs device logs. **Not available everywhere.**

So a crash is always catchable; the stack trace is not. `health-check.sh` returns `diagnosis`,
and it must be carried onto the finding. `detection-only` means *we know it died and we cannot
say why* — write exactly that, and never speculate a cause nobody captured.

| `deviceKind` | Liveness | Hang signal | Diagnosis |
|---|---|---|---|
| `android-device` / `android-emulator` | `adb shell pidof` | system "isn't responding" dialog in the hierarchy | `stacktrace` — `adb logcat -b crash -d` |
| `ios-simulator` | `simctl spawn launchctl list` | timing (no dialog exists) | `stacktrace` — `.ips` report in `~/Library/Logs/DiagnosticReports`, else recent process log |
| `ios-device` | hierarchy (springboard visible) | timing | `stacktrace` if `idevicesyslog` is installed, else `detection-only` |
| `browserstack` | hierarchy | timing | `detection-only` — logs live on the BS session; link `trace.run.sessionUrl` |

**ANR is Android-only.** It is a system dialog, and iOS has none — the watchdog kills the app
(`0x8badf00d`) silently. On `hangSignal: "timing"` targets a hang is inferred from an
interaction that changed nothing; see SKILL.md §3a.5 for the `.unresponsive` convention.

### Reading the result honestly

Both crash and hang are `severity: "high"`, `confidence: "high"` — a dead or hung process is
never a false positive. But two results are **not** findings and must not be treated as clean:

- `note` contains *liveness NOT checked* — the device didn't answer, or no hierarchy was passed.
  That screen has **no** crash coverage. It belongs in `run.coverageGaps`, not in a pass column.
- `capabilities.pageSource == "none"` — `lint.py` never ran on this target, so the deterministic
  UI checks above produced nothing. An empty findings list there means *unmeasured*, not *clean*.

The guards that produce those notes exist because the alternative is worse: an unreachable device
makes `pidof` return empty on every screen, which without a guard would file a high-severity
crash finding per screen for a crash that never happened.

This is incidental crash-finding as a byproduct of thorough exploration, not a replacement for
the dedicated intelligent-monkey-testing skill (use case #2 in `TAPMIND_USE_CASES.md`), which
exists specifically to hunt for these systematically.

## Model findings (`source: "model"`) — report only at `confidence: "high"`

Two distinct sources, both gated to high confidence so low-confidence hunches don't dilute the
list:

**Cross-screen reasoning** no lint rule can express: price/total mismatches between a cart's
line items and its displayed total, a screen that rendered but is semantically wrong for the
goal, a flow that "completed" without actually reaching the goal state.

**Vision review** (§3a.7 of `SKILL.md`) — a screenshot read for what an accessibility-tree-based
lint check structurally cannot see: unreadable text-on-background contrast, colors or icons that
didn't adapt to the active theme (the main dark-mode failure mode — a light-mode asset rendered
unchanged against a dark background, or vice versa), stretched/cropped images, and misaligned
layout that isn't a pure bounds-overlap. Tag these `type: "visual-defect"` or
`type: "dark-mode-contrast"` as appropriate. Gated per unique screen, not automatic: always on for
a dark-mode run, otherwise only as a fallback when hierarchy couldn't resolve an element, the
screen looks transient, or `lint.py` already flagged something on it — see
`references/tapmind-recipes.md` for the full trigger list and the cost rationale.

## KB findings (`source: "kb"`) — matched against `known-bugs.md`

When a lint or model finding matches an entry there, carry its `kbRef` forward into the finding
— "this is BUG-1183 again" triages faster than "possible anomaly."
