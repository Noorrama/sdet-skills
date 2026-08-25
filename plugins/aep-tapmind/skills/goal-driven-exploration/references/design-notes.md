# Design notes

Condensed from the original design doc (`tapmind-mcp-clean/docs/GOAL_DRIVEN_EXPLORATION.md`,
owner: ashish.sharma) — keep this in sync if that doc changes. This file exists because
`aep/skills` and `tapmind-mcp-clean` are separate repos; the skill can't read the other one at
runtime.

## Run directory layout

```
~/tapmind-runs/<ts>-<slug>/
├── report.html            # deliverable — self-contained, trace inlined
├── trace.json              # machine-readable record
├── screens/step-NN.png
├── pagesource/step-NN.{json,xml}
├── findings/step-NN.json   # lint.py output
├── logs/step-NN.log        # only around failures
└── run.log
```

## `trace.json` shape (contract between the skill and `report-template.html`)

```jsonc
{
  "run": {
    "id": "...", "goal": "...", "platform": "Android", "runMode": "local",
    "device": "Pixel_6_API_34 · Android 14",       // from device-info.json, not a bare adb serial
    "app": "com.gojek.app.staging 5.412.0 (build 41207)",  // from device-info.json's dumpsys read
    "conversationId": "...",
    "startedAt": "...", "durationMs": 0,
    "verdict": "PASSED | FAILED | PARTIAL", "verdictReason": "...",
    "sessionUrl": null, "stepBudget": 40,
    "model": "claude-sonnet-5", "modelEffort": "high",
    "tokenUsage": { "inputTokens": 0, "outputTokens": 0,
                    "cacheReadTokens": 0, "cacheWriteTokens": 0 },  // null fields if unknown
    "costUsd": 0.0, "costEstimated": true,            // false only when sourced from /cost
    "themes": ["light"],                              // ["light"] | ["dark"] | ["light","dark"]

    // --- Copied verbatim from device-info.json at close-out. Never re-derived.
    "deviceKind": "android-emulator",   // android-device|android-emulator|ios-simulator|ios-device|browserstack
    "capabilities": { "screenshots": "adb", "pageSource": "uiautomator", "deviceLogs": "logcat",
                      "liveness": "pidof", "crashDiagnosis": "stacktrace",
                      "hangSignal": "anr-dialog", "networkToggle": "adb",
                      "rotation": "adb", "locale": "adb", "phoneCall": "adb-emu",
                      "permissionControl": "mcp" },

    // What this target could NOT check. One line each. Anything `capabilities` reported as
    // "none", plus every screen where health-check.sh returned a "NOT checked" note.
    //
    // This field is what separates "we looked and it was clean" from "we never looked". Only
    // the run knows which happened, and a report that omits it reads as the first when it was
    // the second. An empty array is a claim that everything was checkable — don't default to it.
    "coverageGaps": [
      "lint.py did not run (pageSource: none on browserstack) — no deterministic UI checks",
      "step 12: liveness NOT checked (no hierarchy file passed)"
    ]
  },
  "nodes": [
    { "id": "gofood_home", "label": "GoFood Home", "kind": "screen | popup | deadend",
      "firstStep": 4, "visits": [4, 11], "screenshot": "screens/step-04.png",
      "pageSource": "pagesource/step-04.json", "pageSourceSnippet": "...",
      "elementCount": 63, "findings": ["f3"] }
      // "screenshot" and "pageSource" are required on every node once step 4+ has run — a null
      // here is a bug in the skill's loop (§3.5 of SKILL.md), not an acceptable gap. The report
      // silently falls back to placeholder art when either is missing, which is why this needs
      // to be enforced while writing the trace, not caught by eyeballing the rendered report.
  ],
  "edges": [
    { "id": "e4", "step": 4, "from": "home", "to": "gofood_home",
      "action": "Tap the GoFood service tile", "tool": "appium_tap_element",
      "args": { "elementId": "element_14" },
      "outcome": "ok | retry | backtrack | blocked | unexpected | crashed",
      "phase": "goal | explore | focus",
      // "explore" = a side-quest probe (§3a.9), not on the path to the goal
      // "focus"   = an injected condition (§3c) — backgrounding, permission denial, deep link
      //             mid-flow. Requires focusArea; that pairing is what lets the report show
      //             focus-area coverage as its own axis instead of burying it in the goal path.
      "focusArea": "lifecycle-background",   // required iff phase == "focus"; id from
                                             // references/focus-areas.md
      "durationMs": 1830, "note": "" }
  ],
  "findings": [
    { "id": "f3", "severity": "high|medium|low", "confidence": "high|medium|low",
      "source": "lint|model|kb",
      "type": "price-mismatch | crash | anr | hang | visual-defect | dark-mode-contrast | ...",
      "node": "cart", "step": 9,
      // REQUIRED on type crash/anr/hang, omitted otherwise. Copied from health-check.sh's
      // output, never guessed:
      //   "stacktrace"     — logPath holds the trace; summarise the top frames in `evidence`
      //   "detection-only" — the app died and we CANNOT say why. Write that plainly; do not
      //                      infer a cause from what was on screen. On BrowserStack, point at
      //                      run.sessionUrl so a human can pull the logs there.
      "diagnosis": "stacktrace | detection-only",
      "title": "...", "detail": "...", "evidence": "...", "kbRef": "BUG-1183" }
  ],
  "logs": [ { "step": 9, "source": "logcat", "file": "logs/step-09.log", "excerpt": "..." } ]
}
```

Edges carry the steps — there's no separate `steps` array to keep in sync. A dead button is a
self-loop edge (`from === to`) with `outcome: "blocked"`.

## Graph model (what the report renders)

| Element | Meaning | Rendering |
|---|---|---|
| Node | one screen state | card: thumbnail, label, visit count, findings badge |
| Node `kind: popup` | interstitial/dialog/promo | offset right of the spine, amber outline |
| Node `kind: deadend` | non-recoverable / goal-blocking | red outline, terminal |
| Edge `ok` | forward progress | solid, downward |
| Edge `unexpected` | something appeared the goal didn't ask for | amber, diagonal to the offset node |
| Edge `retry` | same action repeated, no effect | solid + retry marker |
| Edge `backtrack` | returned to an already-visited screen | dashed arc up the left side |
| Edge `blocked` | no effect / goal can't continue | red; self-loop when the screen didn't change |
| Edge `crashed` | app process died or hung (ANR) right after this action | thick red, double-dash; target node is `kind: "deadend"` |
| Edge `phase: "explore"` | a side-quest probe, not on the path to the goal (§3a of `SKILL.md`) | rendered at reduced opacity regardless of outcome, so the goal path stays visually primary |

Layout is computed in the browser from the trace — the skill never computes coordinates.

## Token cost: exact, via the session's own transcript (preferred) — a formula (last resort)

**Preferred**: `assets/session-usage.py`, no arguments. Claude Code writes every turn's real
usage to `~/.claude/projects/<cwd with "/" -> "-">/$CLAUDE_CODE_SESSION_ID.jsonl` — both the
directory and the session id are derivable with no user interaction ($CLAUDE_CODE_SESSION_ID is
a real env var). The script sums it (deduped by message id — a single turn can log its usage
more than once, once per content block) and prices it. This is exact, not an estimate; set
`costEstimated: false`. Likewise, `run.modelEffort` should come from `echo $CLAUDE_EFFORT` via
Bash, not self-reported from memory — a production run recorded `"medium"` when the user had
actually configured `"low"`, because the model guessed instead of checking the env var.

Only if `session-usage.py` errors (e.g. running outside Claude Code CLI, or against an
unpriced model) fall back to asking the user for `/cost`'s output, and only if that's also
unavailable, estimate from step count using the model in the original design doc §11:

- **Fixed prefix** ≈22k tokens/request (MCP tool definitions + system prompt + `SKILL.md`).
- **Per step** ≈4k tokens of new content (`get_view_hierarchy` result + tool call/result turns).
- A step is ~2.5 model turns; history grows roughly linearly, so **total input processed** for
  an N-step run ≈ `22k + N * 4k * (turns so far)`, dominated by re-sent history — in practice a
  30-step run processes on the order of **6M input tokens** (mostly cache reads) and **~100k
  output** including thinking.
- Per-token list prices at time of writing (see the original doc for citations/currency of this
  table — it will go stale): Haiku 4.5 $1/$5 per MTok, Sonnet 5 $2/$10 (promo) or $3/$15
  (standard) per MTok, Opus 5 $5/$25 per MTok. With prompt caching (cache reads ≈0.1× input
  price), a 30-step Sonnet 5 run lands around **$2.6-3.9**; without caching, roughly **4-5× more**.
- Mark any number produced this way `costEstimated: true` — it is a rough model, not a bill.

## Why these choices (don't relitigate without reading the original doc)

- Screenshots via `adb exec-out screencap`, not `appium_get_screenshot` — the MCP tool returns
  base64 into context and deletes its temp file; a multi-step run would spend most of its budget
  on images and still have nothing on disk for the report.
- Lint is a script over `assets/lint.py`, not a model instruction — deterministic, free, and
  consistent build-to-build; reasoning over the hierarchy for mechanical checks is neither.
- Lint reads the uiautomator XML, not `get_view_hierarchy` — `bounds` is stripped server-side
  from the latter, and every geometry-based check needs it.
- Report is one self-contained HTML file, trace inlined — a `file://` page can't `fetch()` a
  sibling JSON.
- Session is destroyed and re-provisioned per run — one TapMind server pins one session; reusing
  it bleeds state between runs.
