# `trace.json` — step-validation mode

The contract between the skill and `assets/report-template.html`. `mode` is `"steps"`.

Unlike `goal-driven-exploration`'s trace, there is **no `nodes`/`edges` graph**. A written step
list is one linear workflow; the spine is a flat `steps[]` array in execution order, and the
report renders it as a filmstrip plus a table. Don't add a graph — the linearity is the point.

## Run directory layout

```
~/tapmind-runs/<ts>-<slug>/
├── report.html                    # deliverable — self-contained, trace inlined
├── trace.json
├── device-info.json               # written by new-run.sh
├── screens/step-NN-before.png
├── screens/step-NN-after.png      # both, every step, no exceptions
├── pagesource/step-NN.xml
├── findings/step-NN.json          # lint.py output
├── logs/step-NN.log               # only around failures
└── run.log
```

`NN` is the step's **`seq`** (execution order), zero-padded — not the author's `n`. Inserted steps
and interruptions have a `seq` but no `n`, and they need screenshots too.

## Shape

```jsonc
{
  "run": {
    "id": "20260806-1432-gofood-checkout-steps",
    "mode": "steps",
    "title": "GoFood checkout with saved address",   // short name for this step list
    "platform": "Android",
    "runMode": "local",                              // copied from device-info.json
    "device": "Pixel 7 · Android 14",
    "app": "com.gojek.app 5.412.0 (build 41207)",
    "conversationId": "...",
    "startedAt": "2026-08-06T14:32:11+07:00",
    "durationMs": 318000,
    "theme": "light",

    // Checks that could not run in this environment. REQUIRED (non-empty) whenever
    // runMode != "local" — a remote run has no adb, so no page source, no lint.py, no logcat.
    // The report renders these as a banner above the tiles, because "0 lint findings" otherwise
    // reads as "the screens were clean" rather than "that check never ran".
    // Screenshots are NOT a limitation in any mode — assets/capture.sh works everywhere.
    "captureLimitations": [
      "lint.py did not run — a BrowserStack run has no uiautomator page source, so no element bounds to check.",
      "No logcat — crash/ANR detection was inferred from the view hierarchy only.",
      "Deterministic UI checks (truncation, overlap, off-screen, missing images) were not performed."
    ],

    "result": "COMPLETED | COMPLETED_WITH_DEVIATIONS | STOPPED",
    "resultReason": "Reached step 10 of 10. 3 steps needed a deviation; 2 actions inserted.",
    "stoppedAtStep": null,          // author step number where the run stopped, or null

    // headline counters — the report's tiles read straight from these.
    // They MUST agree with steps[]; render-report.sh checks and warns.
    "stepsGiven": 10,               // author steps in the original list
    "actionsTaken": 13,             // total rows in steps[] that were actually executed
    "insertedSteps": 2,             // origin === "inserted"
    "interruptions": 1,             // origin === "interruption"
    "deviations": 3,                // author steps with verdict "pass_with_deviation"
    "appFaults": 1,                 // rows with fault === "app"

    "correctedSteps": [             // §6 — the copy-pasteable artifact
      { "n": "1",  "text": "Open GoFood", "change": "unchanged" },
      { "n": "2",  "text": "Tap \"Akun\"", "change": "reworded",
        "was": "Tap the profile button",
        "why": "No hierarchy match for \"profile\"; the icon has no content-desc." },
      { "n": "2a", "text": "Dismiss the \"Rate your last order\" prompt if shown",
        "change": "inserted", "why": "Transient modal, appeared after login." },
      { "n": "8",  "text": "Verify the total shows Rp 56.000", "change": "not-verified",
        "why": "Run stopped at step 7." }
    ],

    "model": "claude-sonnet-5", "modelEffort": "high",
    "tokenUsage": { "inputTokens": 0, "outputTokens": 0,
                    "cacheReadTokens": 0, "cacheWriteTokens": 0 },
    "costUsd": 0.0, "costEstimated": false
  },

  "steps": [
    {
      "id": "s2",
      "seq": 2,                     // execution order, 1..M — drives screenshot filenames
      "n": 2,                       // author's step number; null for inserted/interruption
      "origin": "author | inserted | interruption",
      "kind": "action | assertion",

      "given": "Tap the profile button",        // verbatim author text; null when origin !== "author"
      "did": "Tapped \"Akun\" (element_31)",    // what actually happened — always present

      "verdict": "pass | pass_with_deviation | fail | not_reached | dismissed",
      "fault": "authoring | app | null",

      "deviation": {                // null when verdict === "pass"
        "type": "vision-fallback | scroll-needed | reworded-target | retry-needed | inserted-step | interruption",
        "why": "No hierarchy match for \"profile\"; the account icon has no content-desc (finding f3).",
        "suggestedRewrite": "Tap \"Akun\""      // null when there's nothing to rewrite
      },

      "resolution": {
        "rung": "hierarchy | fuzzy | scroll | vision | coordinates | none",
        "attempts": 1,
        "matched": "account icon at [880,120][944,176]",
        "candidates": 1             // how many plausible matches the rung produced
      },

      "tool": "appium_tap_element",
      "args": { "elementId": "element_31", "reason": "..." },

      "assertion": {                // only when kind === "assertion"; null otherwise
        "expected": "the \"Save card\" checkbox is checked",
        "actual": "checked=\"false\"",
        "method": "hierarchy | vision",
        "evidence": "element_44 CheckBox checked=\"false\" [64,1188][112,1236]",
        "passed": false
      },

      "impact": "neutral | state-changing",   // only when origin === "interruption"; null otherwise
      "dismissedBy": "✕ control (element_7), tapped twice — the first tap landed on the CTA underneath",

      "screenBefore": "screens/step-02-before.png",   // required on every executed step
      "screenAfter":  "screens/step-02-after.png",    // required on every executed step
      "pageSource":   "pagesource/step-02.xml",
      "hierarchySnippet": "element_29 ImageView  content-desc=\"\"  clickable=true  [880,120][944,176]\n...",

      "durationMs": 1830,
      "observation": "",            // free text: timing, anything odd but not a finding
      "findings": ["f3"]
    }
  ],

  // Every field below except kbRef is REQUIRED. A finding that is only a title cannot be acted
  // on: `fault` decides whether it gets filed as a bug or fixed in the steps, `evidence` is what
  // makes it credible, and `step`/`seq` is what says where it happened. A real run emitted all
  // of these as null and the report showed an empty evidence box, a "step not recorded" chip,
  // and an app navigation defect filed under "step-authoring issues".
  "findings": [
    { "id": "f3", "severity": "high|medium|low", "confidence": "high|medium|low",
      "source": "lint|model|kb",
      "fault": "app|authoring",          // NEVER null — this is what routes the finding
      "type": "missing-a11y-label | dead-control | crash | anr | assertion-failed | visual-defect | ...",
      "step": 2, "seq": 2,               // at least one of the two
      "title": "...", "detail": "...", "evidence": "...", "kbRef": "BUG-1183" }
  ],

  "logs": [ { "seq": 9, "source": "logcat", "file": "logs/step-09.log", "excerpt": "..." } ]
}
```

## Invariants `render-report.sh` enforces

It warns (never fails) on each of these. Treat every warning as a bug in the trace writer:

0. `run.runMode` matches `device-info.json`'s `runMode` (copy it, never re-derive), and
   `run.captureLimitations` is non-empty whenever that mode isn't `local`.
1. Every executed step has both `screenBefore` and `screenAfter` — **in every run mode.**
   `assets/capture.sh` pulls screenshots from TapMind's HTTP endpoint, which is backed by the
   Appium driver and therefore works identically on BrowserStack. A remote run with no
   screenshots means the loop reached for `adb`, which reaches nothing there.
2. `run.stepsGiven` equals the count of `origin === "author"` rows.
3. `run.actionsTaken`, `insertedSteps`, `interruptions`, `deviations`, `appFaults` all agree
   with `steps[]`.
4. `verdict: "pass_with_deviation"` implies a non-null `deviation` with a non-empty `why`.
5. `kind: "assertion"` implies a non-null `assertion` with non-empty `evidence`.
6. `origin: "interruption"` implies non-null `impact` and `dismissedBy`.
7. No `source: "lint"` finding when `findings/` is empty — lint can't have produced it.
8. `seq` is a dense 1..M sequence with no gaps or duplicates.
9. `run.correctedSteps` is non-empty when at least one author step executed, and every entry is
   an **object** with `n`, `text` and a valid `change` — never a plain string. Strings make every
   field `undefined` and the tab renders blank rows.
10. Every finding has `fault` (`app`|`authoring`), `evidence`, `detail`, a valid `severity`, and
    at least one of `step`/`seq`.
11. Every finding id appears in some `step.findings[]`, every id referenced by a step exists, and
    the count of `fault: "app"` steps matches the count of `fault: "app"` findings.

## Why counters live in `run` as well as in `steps[]`

The report's headline tiles ("10 given → 13 taken") are the first thing the author reads, and the
template shouldn't have to recompute them from `steps[]` to render above the fold. The duplication
is deliberate; invariant 3 is what keeps it honest.
