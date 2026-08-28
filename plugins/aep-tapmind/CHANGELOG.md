# aep-tapmind changelog

## 1.1.6

**`nlp-codegen` mode choice.** Ask once before any device work: knowledge-base-only
(faster MR, no pioneer), reuse a pasted `@Test`, or device-pioneer (one
step-validation per cluster). Do not start step-validation autonomously.

## 1.1.5

**Cursor TapMind MCP + reload.** Documents `~/.cursor/mcp.json` (`mcp-remote` →
`http://localhost:7777/mcp`) and how to reload skills vs MCP in Cursor Desktop
(Reload Window + new chat). Plugin README.

## 1.1.4

**Cursor plugin manifest.** `aep-tapmind` now ships `.cursor-plugin/plugin.json`
(`skills: ./skills/`) like `aep-mobile`, plus `scripts/plugin-root.sh` so bash
resolves the plugin whether `CLAUDE_PLUGIN_ROOT`, `CURSOR_PLUGIN_ROOT`, or
`TAPMIND_PLUGIN_ROOT` is set. Install notes: `plugins/aep-tapmind/README.md`.

## 1.1.3

**`nlp-codegen` README.** QA/engineer guide covering prerequisites, pipeline
slot vs `test-code-generator`, clustering, design-context limits, shallow clone,
and GitLab MR auth — `skills/nlp-codegen/README.md`.

## 1.1.2

**`nlp-codegen` clarifications.** Clusters are similar-flow groups inside one
module (not Driver-vs-GoFood). `design_context.json` is optional Figma copy —
the SDET plan cannot reconstruct it. If `tapmind-mobile-tests` is not on disk,
shallow-clone `aep/tapmind-mobile-tests` (`--depth 1`); do not require the
skill to be run from that repo.

## 1.1.1

**`nlp-codegen` MR step is GitLab-explicit.** No numeric project id is stored —
the target is the `tapmind-mobile-tests` checkout's `origin`
(`aep/tapmind-mobile-tests` on `source.golabs.io`). Opening the MR needs
`GITLAB_TOKEN` / `glab auth` with write scopes; if missing, the skill commits
and prints `git push` + `glab mr create` instead of guessing GitHub or a token.

## 1.1.0

**New skill: `nlp-codegen`.** Generates TapMind NLP `@Test` methods into
`tapmind-mobile-tests` from an enriched / automation / SDET plan plus
`change_context`, without running step-validation on every scenario.

Per similar-flow cluster (e.g. ten Driver BAM cases that share login → feature
and differ on one assertion) it step-validates **one** pioneer scenario, harvests
the proven method — including `if visible` transients the plan JSON never listed
(`Tap 'Allow'…`, `Tap 'Lewati'…`) — and clones the siblings from that template.
Then writes one class in the module's house style and opens an MR scoped to that
module.

Orchestrates; does not fork the device loop. Reuses `step-validation`'s
`module-profile.sh` and `direct-api-map.md`. A pasted proven `@Test` or
`trace.json` skips the device run for that cluster.

## 1.0.1

**`step-validation` input wiring only — device loop, capture, emit rules, and report renderer
are unchanged.** Mode B now resolves the plan file in order: `enriched_automation_plan.json`
(the automation ledger), then `*_automation_plan_generator.json`, then the SDET plan. TDP /
`performBackdoorLogin` uses `test_data[].test_data_output[].test_buddy_prompt` verbatim when
present; compose or ask only if that field is missing. `@TestInfo.testCaseIds` prefers
`browserstack_case_id` over `existing_case_ref`. `automation_steps[]` are still used as written.

## 1.0.0

**Extended `step-validation` to emit ready-to-paste TapMind mobile-test `@Test` methods.** A
validated run now produces a `@Test` method in the module's own house style (imports, base class,
groups, `@TestInfo` annotation) that the author pastes into their test class and runs — locally or
on CI. The method is built only from steps that actually executed on the device, with direct API
calls for everything not touching the UI (mock location, backdoor login, deeplink, kill/launch),
and transient screens guarded with `if visible` conditionals so first-login-only flows don't break
repeat runs.

Rendered as the **TapMind test** tab in the report with a copy button.

### Design

- **One line per state-changing tool call, not per author step.** The MCP loop already makes
  exactly one call per action, matching the server's `runStep` constraint: `ActionVerbExtractor`
  only reads the leading verb, so a compound sentence silently does half the step. Emission reads
  the tool trace instead of parsing English — a step that scrolled then tapped emits two lines,
  for free.
- **Direct API beats `runStep`.** Anything not touching the UI has a client method
  (`TapMind.setMockLocation()`, `performBackdoorLogin()`, `openDeeplink()`, etc.). Using `runStep`
  would spend a server LLM turn and can drift; the base API compiles everywhere.
- **Transient screens are conditionals.** Every `if visible` guard is routed through the
  server's conditional prompt, whose contract is **condition UNMET ⇒ `appium_report_skip`, never
  a failure**. So a first-login-only walkthrough can't break repeat runs.
- **Module derivation, not hardcoding.** New `assets/module-profile.sh` reads package, base
  class, test groups, and a sample test *from each module's own tests* — no hardcoded map. The 19
  modules have no agreement on packages, base classes, or groups; derivation stays correct for
  modules that don't exist yet.
- **Phrasing rules that survive the hundredth run** — captured in SKILL.md §6: leading verb
  from `single-verb-map`, quote only at `hierarchy` rung (fuzzy matches stay unquoted or tests
  break on locale changes), and flag only vision-resolved and ambiguous-match lines as
  `// verify once`.

### New files

- `references/direct-api-map.md` — which steps must not become `runStep`, with the trap of
  `performBackdoorLogin(String)` taking an NLP prompt (not an id) and never carrying a literal
  credential.
- `assets/module-profile.sh` — works out the target module from a config path or name, derives
  package/base class/groups by reading the module's own tests, gracefully fails on modules with
  no tests.

### Updated files

- `SKILL.md` — §0 gains input mode B (SDET plans) and module resolution; new §6 (emit rules);
  §7 (close-out) gains `run.tapmindTest` population.
- `references/trace-schema.md` — `run.tapmindTest` with line-level provenance and confidence;
  new invariants 12–15.
- `assets/report-template.html` — **TapMind test** tab rendering, shared copy-button handler.
- `assets/render-report.sh` — enforces the new invariants, warns on missing module fields, guards
  without conditionals, flagged lines with no explanation, and any literal-looking credentials.

### Verification

- Swept all 19 modules; 18 resolve automatically, `commons` correctly reports it has no tests.
- Caught and fixed a live bash bug: `GROUPS` is a builtin array — assignment is silently ignored.
  Renamed to `TEST_GROUPS`.
- All five new invariants confirmed firing on a corrupted trace, silent on a good one.
- Emitted method compiled in `driverApp` with `./gradlew :driverApp:compileTestJava` → exit 0.

## 0.6.0

**New skill: `charter-exploration`.** Derives goal-driven exploratory charters from a
BrowserStack Test Management project, gates them on human approval, then runs each one on a real
device and reports with traceability back to the source test case ids.

Additive only — `goal-driven-exploration` and `step-validation` are byte-identical to 0.5.2.

- **Orchestrates, doesn't re-implement.** Each charter is executed by invoking
  `goal-driven-exploration` as a bounded sub-run, with the charter mission as the goal and its
  timebox as the step budget. That skill still owns the device loop, the anomaly checks, and the
  per-charter journey graph; this one owns scoping, synthesis, the gate, and aggregation.
- **Sub-agent boundaries are load-bearing, not stylistic.** A single `listFolders` call against
  PR-176 measured ~6k tokens (the BrowserStack MCP prints a summary *and* the raw JSON), and a
  real scope walk is 5-15 such calls — a measured 155k tokens for Transport - 4W. Phase A runs in
  a sub-agent that writes `source-cases.json` to disk and returns a ~1k digest; each charter runs
  in its own sub-agent so a 10-charter suite doesn't accumulate ten runs of view hierarchies in
  the parent. That's what keeps the parent thread small enough for Sonnet.
- **Hard approval gate.** `charters.md` + `charters.json` are emitted and the run stops. Zero
  device actions before the user selects, reorders, retimeboxes, or rewrites. Dropped charters
  are marked `dropped`, never deleted, so the report can name them.
- **`render-charters.py` is the honesty check**, not decoration. It rejects a plan whose mission
  isn't in charter form ("Explore … with … to discover …"), a charter citing zero source test
  cases, duplicate ids, or an out-of-range timebox; it warns on near-duplicate missions.
- **The report is incremental.** `render-report.sh` runs after *every* charter, not once at the
  end — same document, filling in, so nobody waits for charter 10 to see charter 1. It renders a
  coverage matrix (area × charters × source case ids × findings, cold rows flagged), per-charter
  budgeted-vs-actually-explored, and a **Not covered** section listing dropped, timeboxed,
  aborted, not-run, and cold areas.
- An `aborted` charter counts as *not run* — it lands in Not covered rather than inflating the
  coverage count.
- **Write-back to BrowserStack is deliberately absent.** Creating runs, posting results, or
  filing defects is outward-facing and irreversible; the skill says so rather than improvising it.

### Fixes from the first review, before release

Comparing the skill's output against a hand-written charter set for GoFood - Booking exposed one
root-cause defect and two consequences of it.

- **Compaction was throwing away the concrete hooks.** Scoping capped every case at a one-sentence
  `gist`, so deep link URIs, config keys, account states and thresholds never reached synthesis.
  The charters it produced named none of them — a deep-link charter that could not name a deep
  link. `source-cases.json` now carries a verbatim `artifacts` list per case, plus an `observed`
  note where a case body describes an actual defect. Token cost is negligible; these are short
  verbatim strings on a minority of cases, and they replace work synthesis was doing badly.
- **New required field: `probes`** — 3-6 concrete openers per charter naming real artifacts, the
  executable half of a charter. `render-charters.py` requires 2, warns below 3, and **rejects
  probes that name nothing concrete** ("Explore deep link behaviour"). Where the corpus has no
  artifact for something a charter needs, the probe must say so rather than invent a
  plausible-looking URI — an invented deep link fails silently and looks like a bug.
- **Risk areas must be grounded.** Quote and cite the source case where one carries an `observed`
  note; prefix speculation `Hypothesis:`. The renderer warns when no risk area in a charter cites
  a case, i.e. when the list is probably all guesswork presented as evidence.
- **Test-data recipes are now marked unverified**, because they were written from the shape of the
  corpus rather than from TDP's actual catalogue and read as authoritative anyway. `charters.md`
  gains a Test data table grouping charters by recipe so an unsatisfiable ask gets corrected at the
  gate, not after a device is provisioned. If TDP returns data that doesn't match the ask, the
  charter aborts — substituting a customer produces findings that look real and aren't.
- **New `charter-status.py`** for status transitions, replacing hand-edits to `charters.json`
  (which meant rewriting a whole plan for a one-word change, at some risk to the user's gate
  edits). It refuses unknown statuses and charter ids, and warns when a charter is marked
  `done`/`timeboxed` with no trace on disk to back it — a false `done` renders as
  covered-and-clean, the worst thing this report can say.
- **`--recover` for dead runs.** A suite killed mid-charter leaves a charter marked `running`
  forever, counting as pending and understating Not-covered. `--recover` resolves each against
  what is on disk; `aggregate.py` warns when any charter is stuck and names the fix. Found by
  killing a real run.
- **Fixed a validator that never fired.** The vague-probe check folded a case-sensitive test into
  an `re.I` regex, which made `[A-Z]{2,}` match lowercase and the negative lookahead always hold.
  Replaced with an explicit `is_vague()`; verified against 13 probes, no false positives.

## 0.5.2

Fixes from the second real run (`20260806-1259-gofood-go-ride-booking`). The `0.5.1` capture and
config fixes worked — screenshots landed and `run_mode=remote` was detected correctly — but the
trace was written with the wrong shape in three places and **nothing caught it**.

- **Corrected-steps tab rendered ten blank rows.** `run.correctedSteps` was written as an array
  of prose strings; the schema is an array of `{n, text, change, was, why}` objects, so every
  field read as `undefined`. The template now salvages strings via regex (parsing the leading
  `N.` and inferring `change`), and `render-report.sh` warns so the writer gets fixed.
- **A finding was filed under the wrong heading.** `fault` was null, and the template's
  `f.fault !== "app"` default dropped it into *Step-authoring issues* — so an app navigation
  defect ("payment method row opens Vouchers") was presented as the author's mistake. Findings
  with no `fault` now get their own **Unclassified** section instead of a silent default.
- **`seq undefined` chip and an empty evidence box.** `evidence`, `detail`, `step` and `seq` were
  all null. Missing fields now render as explicit "not recorded" labels rather than blanks.
- **New invariants** (renderer now warns on all of these): `correctedSteps` entry shape and
  `change` vocabulary; per-finding `fault`/`evidence`/`detail`/`severity`/`step|seq`; orphaned
  findings not linked from any step; steps referencing non-existent finding ids; every step with
  `findings: null`; and any step marked `fault: "app"` that links no `fault: "app"` finding.
  Deliberately *not* enforced: equal counts of app-fault steps and app-fault findings — plenty of
  app defects (missing a11y label, truncated text) are found on screens where the step passed.
- SKILL.md §6 and `trace-schema.md` now spell out both shapes, with the wrong form shown
  alongside the right one.
- Fixed the shipped sample trace, which had an orphaned finding (`f2` unlinked from step 4).

## 0.5.1

Fixes for two defects found on the first real `step-validation` run
(`20260806-1154-goride-blokm-booking`), which produced a report with **no screenshots, no page
sources, no lint findings and no logs**. Both were skill bugs, not run bugs.

### The run mode was misdetected as `local`

`new-run.sh` reads `$TAPMIND_CONFIG` (or `~/.tapmind/profile.json`), but the server resolves its
own config as `System.getProperty("config", System.getenv("DARKSEID"))` — the `-Dconfig` JVM flag
first. The `tapmind` CLI bridges the two by forwarding `$TAPMIND_CONFIG` as `-Dconfig`, but
launching the jar by hand sets only `-Dconfig`. `new-run.sh` then found no profile and silently
defaulted to `run_mode=local` for what was actually a BrowserStack run.

- **New `assets/resolve-config.sh`** — reads `-Dconfig` off the running JVM's command line
  (authoritative: whatever that process started with is what every session uses), falling back to
  `$TAPMIND_CONFIG` → `$DARKSEID` → `~/.tapmind/profile.json`. Exports `TAPMIND_CONFIG` for
  `new-run.sh`, warns loudly on disagreement with the server, and exits non-zero rather than
  letting anything default to `local`.
- SKILL.md §1 now runs it before `new-run.sh`.

### Capture was hardcoded to `adb`, which reaches nothing on BrowserStack

SKILL.md §2 emitted `adb exec-out screencap`, `adb shell uiautomator dump`, `adb shell pidof` and
`adb logcat` inline. Only the local path was ever written.

- **New `assets/capture.sh`** — screenshots now come from TapMind's own
  `GET /tapmind/screenshot/{conversationId}` endpoint (backed by `driver.getScreenshotAs(BASE64)`,
  so it works wherever the session lives), decoded straight to disk. Zero context cost, identical
  in both run modes. Page source is still adb-only and reports a `SKIP` line when unavailable.
- **New SKILL.md §1a** — an explicit capability table per run mode, so the loop knows up front
  what it can and cannot check.
- **New `run.captureLimitations`** — required on remote runs, rendered as a banner above the
  tiles. Without it, "0 lint findings" reads as "the screens were clean" when it means "that
  check never ran".
- `render-report.sh` is now run-mode aware: it no longer false-alarms about empty `pagesource/`
  and `findings/` on remote (inherent, not a defect), gets stricter about missing screenshots
  (never acceptable in any mode, and it names `adb` as the likely cause), cross-checks
  `run.runMode` against `device-info.json`, and requires `captureLimitations` on remote.

### Also

- Fixed an invalid CSS attribute selector that silently killed the `not-verified` styling rule in
  the report (one bad selector invalidates the whole selector list).
- Fixed headline arithmetic that miscounted "N of yours" on a run that stopped early.

`goal-driven-exploration` is unchanged and byte-identical to 0.4.0.

## 0.5.0

- **New skill: `step-validation`.** Runs a written step list against a real device and reports,
  per step, how each one was carried out — hierarchy vs fuzzy vs scroll vs vision resolution,
  steps that had to be inserted, transient screens dismissed (with state-impact), and app faults
  separated from step-authoring faults. Produces a filmstrip + step table report and a
  copy-pasteable corrected step list.
- Reuses `new-run.sh`, `lint.py` and `session-usage.py` from `goal-driven-exploration` in place
  via `${CLAUDE_PLUGIN_ROOT}` rather than copying them.

## 0.4.0 and earlier

`goal-driven-exploration` only — see that skill's `references/design-notes.md`.
