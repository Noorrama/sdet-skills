---
name: mobile-design-extractor
description: Extract the UI flow and element map from a mobile app's design into design_context.json — screens, element IDs (logical), interactions, states, ui_flow, and project-level ambiguity tracking. Input is a JSON export from the "Export Design Raw JSON" Figma plugin (formatVersion 2 with geometry). Spatial-first pipeline — deterministic Python derives groups, swim lanes, screen collapse, and connector-resolved flows from geometry alone; a constrained fast-tier LLM pass only enriches (element labels, note-traced validations), and a stronger model is pulled in only for flagged escalations. Collapses state variants into screen-level states instead of fragmenting them into separate screens, and reports unresolved navigation in blocking_issues rather than inventing it. App-agnostic; the frontend-primary stage. Its element IDs are the logical half of the locator mapping.
---

# Mobile Design Extractor — spatial-first pipeline

Design is the frontend-primary stage. This skill produces the screen/element map whose logical
`element_id`s later join to real per-platform locators from the Code Diff (code-change-extractor).

**Architecture: the scripts decide, the model decorates.** Everything structural — grouping,
swim lanes, screen collapse, states, `ui_flow`, deterministic elements — comes byte-reproducibly
from `spatial_pipeline/` scripts. The model pass (Phase B) may only enrich what the scripts
emitted, under a merge contract that rejects anything it cannot trace to the export. If you ever
find yourself counting connectors, classifying frames, or walking the board by hand — stop; the
script exists so that never happens.

## Scripts (all in `spatial_pipeline/`, pure stdlib + jsonschema)

| script | role |
| :--- | :--- |
| `phase_a.py` | THE extractor: spatial analysis → collapse → skeleton `design_context.json` + `phase_a.report.json`, schema-validated |
| `preflight.py` | ALL mechanical preflight checks in one deterministic pass — never hand-write these |
| `phase_b_packets.py` | one grounded packet per screen for the enrichment pass |
| `phase_b_autobind.py` | deterministic element auto-bind (zero tokens) + light packets for the notes-only LLM pass |
| `phase_b_merge.py` | applies enrichment under the no-invention contract, writes `escalations.json`, re-validates |
| `spatial_scan.py`, `connector_resolve.py` | libraries used by the above; each also runs standalone as a diagnostic |
| `viz_export.py` + `viz_shell.html` | optional: board-replica HTML for human side-by-side verification against Figma |

## Preflight — resolve, or record and continue

**Never stop, never guess.** Anything unresolvable becomes an `extraction_gaps` entry and the run
continues — a partial, honestly labelled output beats no output. Inventing a value is forbidden.

1. **Mechanical checks — one script, never hand-written.** Run
   `python3 spatial_pipeline/preflight.py <export.json> [--app <app_id>]`. It performs EVERY
   mechanical preflight check in one deterministic pass — jsonschema availability, export parse,
   `formatVersion: 2` + geometry, `truncatedCount`, app config readability, schema readability —
   and prints a JSON verdict with ready-made `extraction_gaps` entries to copy into the context,
   plus the raw app-set evidence (file name/page, top-level sections, bracket prefixes, known app
   ids) for step 2. **Never write ad-hoc code to inspect the export envelope** — that is exactly
   the failure mode this script removes. `status: BLOCKED` (formatVersion 1 / no geometry) →
   emit a `DEGRADED` context with empty screens carrying the script's `BLOCKING` gap and stop
   the pipeline there; `DEGRADED` entries → copy the gaps and continue.
2. **App set — how many apps does this export cover?** Never assume one. Check `file.name`,
   `file.page`, top-level SECTION names, frame-name prefixes (`[GoPay] …`), or the user naming
   them. Map to: `gojek-consumer`, `gojek-driver`, `gofood-merchant`, `gopay-consumer`,
   `gopay-merchant`.
   - One app → `phase_a.py <export> --app <app_id>` → `design_context.json`.
   - Separate exports per app → run the whole pipeline once per file, writing
     `design_context.<app_id>.json` each.
   - **One export mixing several apps** → the pipeline has no app-splitting stage yet: emit one
     file, leave the dominant app on `app`, and raise a `BLOCKING` note naming the frames that
     belong elsewhere with the action "re-export per app as a selection export". Do NOT hand-split.
   - None resolvable → one file, `app` absent, `BLOCKING` note on `app`. Never guess from visual
     style; a dark-themed frame is not proof of an app.
   Report the decision in your reply before extracting.
3. **Config** — `${CLAUDE_PLUGIN_ROOT}/config/<app>.json` supplies
   `naming_convention.role_vocabulary` (the `_btn/_input/…` suffixes phase_a and the merge use).
   Unreadable → scripts fall back to their built-in default vocabulary; add a `DEGRADED` gap
   warning IDs are unverified against the app convention.
4. **Schema** — `${CLAUDE_PLUGIN_ROOT}/schemas/design_context.schema.json`. The scripts locate it
   relative to the plugin root automatically; unreadable → `DEGRADED` gap, same install action as
   other skills (`claude plugin update aep-mobile@aep`).

## Output files — one per app in scope

| Apps in scope | Files written |
| :--- | :--- |
| 1 | `design_context.json` |
| 2+ (separate exports) | `design_context.<app_id>.json` each |

Each file is a complete, independently valid `design_context`. Always set `app` — the schema
doesn't require it, but `sdet-plan-generator` keys off it to match contexts in a run.
`phase_a.report.json` is a pipeline-internal sidecar (provenance: protos, merges, exclusions,
unresolved endpoints); keep it next to the context for reviewers, never feed it downstream.

## Workflow

```bash
cd ${CLAUDE_PLUGIN_ROOT}/skills/design-extractor/spatial_pipeline

# 1. deterministic skeleton (screens, states, ui_flow, connector-trigger elements)
python3 phase_a.py <export.json> --app <app_id> --out <workdir>

# 2. packets for the enrichment pass
python3 phase_b_packets.py <export.json> <workdir>/design_context.json <workdir>/phase_b_packets.jsonl
```

**3. Phase B — light mode (the default).** Element binding is deterministic; only note
interpretation needs a model.

```bash
# 3a. auto-bind elements from the packets (zero tokens, instant) and emit the
#     light packets for the notes-only pass
python3 phase_b_autobind.py <workdir>/phase_b_packets.jsonl \
        <workdir>/autobind_out.jsonl <workdir>/phase_b_light.jsonl

# 3b. merge the auto-bound elements (same contract, same validator)
python3 phase_b_merge.py <workdir>/design_context.json <workdir>/phase_b_packets.jsonl \
        <workdir>/autobind_out.jsonl <workdir>/design_context.autobound.json
```

Then run the **notes-only LLM pass** over `phase_b_light.jsonl` (screens with notes, OTHER
state kinds, or ambiguity flags — typically half the screens at ~6% of the full packet bytes):
split into batches of ~21 lines, one **Haiku** agent per batch, in parallel. Each agent outputs
one JSON object per screen in EXACTLY this shape — paste this block into every agent prompt
verbatim; it is the merge contract, and any other shape (a boolean `ambiguity`, a string list,
anything improvised) is rejected by `phase_b_merge.py` and burns a pointless escalation:

```json
{"screen_id": "<copied from the packet>",
 "state_kind_map": {"<state name>": "DEFAULT|LOADING|EMPTY|ERROR|SUCCESS|OFFLINE|DISABLED|PERMISSION_DENIED|DARK_THEME|LIGHT_THEME|LOCALE_VARIANT|RTL|OTHER"},
 "screen_validations": ["<one sentence, traced to a note — never invented>"],
 "ambiguity": {"rating": "LOW|MEDIUM|HIGH", "reason": "<one concrete sentence naming the conflict>"}}
```

`ambiguity` is optional and is an OBJECT, never a boolean. Instruct agents to rate against the
consequence: HIGH means a design-team question is required — it puts the screen in
`blocking_issues` and `escalations.json`, and requires a non-empty reason a PM can answer.
Conflicting notes that are per-lane/persona variants (host vs member) are MEDIUM at most;
states with no note evidence are simply unannotated, not ambiguous — omit the field. No
`elements`, no `element_updates`; instruct agents so explicitly. Never do this pass inline in
your own context.

```bash
# 4. merge the light outputs; writes escalations.json
cat light_out_*.jsonl > light_out.jsonl
python3 phase_b_merge.py <workdir>/design_context.autobound.json \
        <workdir>/phase_b_packets.jsonl light_out.jsonl \
        <workdir>/design_context.enriched.json
```

**Full mode (opt-in, only when the user asks for maximum element curation):** instead of 3a/3b,
run one Haiku agent per ~14-packet batch of the FULL packets with the contract from the
`phase_b_merge.py` docstring verbatim — the model then also selects/refines elements. Costs
roughly 10x the light-mode tokens for modestly better decoration filtering; the merge's
auto-repair makes light mode's naming just as safe.

**5. Escalation pass — stronger model, only when earned.** `phase_b_merge.py` writes
`escalations.json`: one entry per screen that needs judgment beyond the fast tier —
HIGH-ambiguity flags from the enrichment agents, ambiguous generic-name collapses from phase_a,
and screens whose enrichment was rejected by the contract. If the file is empty (`[]`), skip this
step entirely — do not escalate "just in case".
For each escalated screen, spawn ONE agent on **Sonnet** with: that screen's packet line, the
escalation reason, and the same contract. Merge its output with a second `phase_b_merge.py` run
(input context = the enriched file; the merge is additive and rejects duplicates, so re-running
is safe). A HIGH call that survives escalation stays in `blocking_issues` — escalation exists to
refine bindings and wording, not to argue flags away.

**6. Finalize.** Rename/move `design_context.enriched.json` to the output location as
`design_context.json` (or `design_context.<app_id>.json`), confirm the merge printed
`schema: VALID`, and summarize: screens, edges, elements, blocking issues, escalations run.

## Model policy

- **Default tier: Haiku.** Structure comes from scripts; Phase B batch enrichment is
  closed-vocabulary language work and runs on Haiku agents.
- **Escalate to Sonnet** only for screens listed in `escalations.json` (step 5), or for the two
  preflight judgment calls a fast tier shouldn't make alone: an app split the page names don't
  settle, and wording of user-facing blocking issues when the source notes conflict. Keep
  escalation prompts minimal — one screen packet plus the contract, nothing else — so the Sonnet
  spend stays proportional to the judgment actually needed.
- **HARD CAP: Sonnet.** No agent in this skill may ever run on a tier above Sonnet (no Opus, no
  Fable) — not for escalations, not for retries, not under any pressure. If Sonnet cannot settle
  a question, the answer is a `blocking_issues` entry for a human, never a bigger model.
- **Never escalate to redo structure.** If the structure looks wrong, the fix is a script fix or
  a Figma fix — re-running a bigger model over the same export must produce the same skeleton by
  construction.

## What the scripts already guarantee (do not re-derive, do not override)

- **Calibration**: every threshold derives from the modal portrait-frame size — no hardcoded
  pixels, no reliance on component names, colors, or team-specific conventions.
- **Swim lanes**: rows by top-line clustering; persona bands (wide banners) and flow-cluster
  banners scoped per band; left captions as lane names; attached dialog shelves as overlays.
- **Screen collapse** (validated against the GoFood Group Order board):
  proto = consecutive same-frame-name run in a column; multi-frame proto → frame name,
  single-frame proto → chip title; chip `Type` (New screen/Changes/Existing) is change-status
  metadata, never a state; scenario sub-sections become state prefixes and edge conditions, never
  screens; self-loops after collapse are state transitions in the report, never `ui_flow`.
- **Connector resolution**: arrowhead = direction (never draw order); endpoints resolve via
  element-in-screen → chip label → variant box → small-section entry (≤8 screens only — a bigger
  section carries no per-screen information and resolving it fabricates an edge); everything else
  lands in the report as unresolved-with-reason.
- **Entry points**: `ui_flow` starts with edges from the reserved `ENTRY` pseudo-node
  (statechart initial-state pattern). Explicit signals win — an "Entry point"/"1st time"
  qualifier on a screen label chip or a flow-cluster banner, or a prototype flow starting
  point (`edge_source: ENTRY_LABEL`, `confidence: EXPLICIT`, `source_ref` = the chip/banner
  node id). Only when the board carries no explicit signal does topology infer them: the
  zero-in-degree root with the widest forward reach, plus per-persona-band coverage
  (`ENTRY_TOPOLOGY`, `INFERRED`, plus an INFO gap advising an explicit chip). All root
  candidates with reach counts land in `phase_a.report.json` (`entry_candidates`). `ENTRY`
  is never a screen, never a `to_screen_id`, and Phase B may never create or touch it —
  `context_checks.py` enforces all three.
- **ui_flow ordering**: breadth-first from `ENTRY` — entry edges first, then each reached
  screen's out-edges wave by wave (ties broken by target board position, condition,
  source_ref), then components unreachable from any entry, appended per component by board
  position. Purely presentational, byte-reproducible; no consumer may read semantics into
  array position.
- **Enrichment naming**: packets dedupe candidates repeating identical (name, type, text)
  across a screen's state-variant frames and stamp each survivor with a deterministic,
  screen-unique `suggested_purpose` derived from its own text. The merge auto-repairs the
  fast tier's naming mistakes deterministically — generic purposes (`element_container`,
  ...) are re-derived from the candidate's own text, colliding ids get a source_ref-derived
  suffix, truncated source_refs snap to their unique candidate — and counts the repairs as
  `auto_repaired` in its report. Escalations therefore mean genuine ambiguity, not cleanup;
  do not re-run the fast tier to fix names.
- **Honesty**: reference screenshots without chips, unlabeled draft clusters, external
  prototype-reaction destinations, and ambiguous collapses are reported, never guessed at.

## Rules

- Never invent `screen_id`, `element_id`, states, or edges. The merge enforces this for Phase B;
  you enforce it for yourself by never editing the context by hand.
- `element_id` casing and role suffixes come from the scripts + app config. Never re-case or
  re-derive them — they are the join key to `change_context`.
- Blocking issues are questions for the design team, phrased so a PM can answer them, each naming
  the Figma node id involved.
- One Write per output file. Intermediates stay in the workdir; never commit run outputs into the
  skill directory.

## Verify

- The merge run must end `schema: VALID` and `referential checks: OK` — phase_a and the merge
  both run `context_checks.py` (screen/element/edge referential integrity, the checks the JSON
  schema cannot express) and exit non-zero on failure. That is the gate, not a manual checklist.
  Standalone: `python3 context_checks.py <design_context.json>`.
- Ground-truth spot check (recommended on a new board or new design team): pick 2-3 screen node
  ids in Figma, count their connectors, compare with edges touching those ids' collapsed screens
  in `ui_flow` + `phase_a.report.json`. Any mismatch is a pipeline bug or a board convention the
  scripts haven't met — report it, don't patch the output.
- For human review, `python3 viz_export.py <export.json> <edges.json> <out.json>` +
  `viz_shell.html` renders the board replica used to validate this pipeline.
