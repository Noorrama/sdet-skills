---
name: mobile-design-extractor
description: Extract the UI flow and element map from a mobile app's design (Figma + navigation + accessibility IDs) into design_context.json — screens, element IDs (logical), interactions, states, ui_flow, and project-level ambiguity tracking. Collapses loading/scroll/error/locale variants into screen-level states instead of fragmenting them into separate screens, and reports unresolved navigation or content in blocking_issues rather than inventing it. App-agnostic; the frontend-primary stage. Its element IDs are the logical half of the locator mapping.
---

# Mobile Design Extractor (all 5 GoTo apps)

Design is the frontend-primary stage. This skill produces the screen/element map whose logical
`element_id`s later join to real per-platform locators from the Code Diff (see code-change-extractor).

## Config
`${CLAUDE_PLUGIN_ROOT}/config/<app>.json` → `naming_convention.element_id_pattern` and `role_vocabulary` govern the
`<ACTION>_<ELEMENT_TYPE>` segment of each `element_id` (see Extract §1). Set `app` on the output object
— the schema doesn't require it, but the rest of the pipeline keys off it for multi-app runs.

## Preflight — resolve, or record and continue
**Never stop, never guess.** Work through these before extracting. Anything that cannot be
resolved becomes an `extraction_notes` entry and the run continues — a partial, honestly
labelled output is always better than no output. What is forbidden is inventing a value to
fill the hole.

1. **App set — how many apps does this export cover?** Never assume one. Scan the frame tree
   before extracting and collect every app in scope from: top-level Figma pages or frame-group
   names per app, a frame-name prefix (`[GoPay] …` / `Gojek — …`), the file/export name, or the
   user naming them. Map each to an app id: `gojek-consumer`, `gojek-driver`,
   `gofood-merchant`, `gopay-consumer`, `gopay-merchant`.
   - **One app** → one output file, as before.
   - **Two or more** → one output file per app (see *Output files*). Common when one Figma file
     holds a shared component's screens for every host app.
   - **Separate exports already supplied per app** → nothing to split; run once per file.
   - **None resolvable** → emit a single file, leave `app` absent, add a `NEEDS_ANSWER` note on `app`.
     Do **not** guess from visual style; a dark-themed frame is not proof of an app.
   Report the decision in your reply before extracting: *"2 apps detected — gopay-consumer
   (pages 'GoPay Transfer', 'GoPay Tagihan'), gojek-consumer (page 'Gojek Tagihan'). Writing 2
   context files."*
2. **Config, per app in the set** — `${CLAUDE_PLUGIN_ROOT}/config/<app>.json`. Unreadable → add a `WORTH_CHECKING` note on
   `ENVIRONMENT` with reason *"cannot read ${CLAUDE_PLUGIN_ROOT}/config/<app>.json — plugin install
   may be incomplete"* and action *"run `claude plugin update aep-mobile@aep`, restart Claude,
   re-run"*. Set `extraction_status: LIMITED`. Continue. **`naming_convention.element_id_pattern` and `role_vocabulary` come from this file only.** If it is unreadable, do NOT improvise a convention — emit IDs verbatim from the Figma accessibility IDs, and raise a `WORTH_CHECKING` note warning that IDs are unverified against the app convention and may not join to real locators at code-gen.
   In a multi-app split this is the whole point of splitting: **each file's `element_id`s must
   follow its own app's pattern and `role_vocabulary`.** IDs generated under the wrong app's
   convention silently fail to join to real locators at code-gen, which surfaces much later as a
   broken test rather than a bad extraction.
3. **Schema** — `${CLAUDE_PLUGIN_ROOT}/schemas/design_context.schema.json`. Unreadable → `WORTH_CHECKING` note on `ENVIRONMENT`, same install action.
   Fall back to the field list in this document **only** in that case, and say so in the note.
4. **Input.** Figma JSON attached and parses. No frames → emit with `PARTIAL` and a `NEEDS_ANSWER` note saying the export looks empty. That is a bad export, not a design with zero screens.

## Output files — one per app in scope
| Apps in scope | Files written |
| :--- | :--- |
| 1 | `design_context.json` |
| 2+ | `design_context.<app_id>.json` for each — e.g. `design_context.gopay-consumer.json`, `design_context.gojek-consumer.json` |

Each file is a complete, independently valid `design_context`. Set `app` on the output object —
the schema doesn't require it, but `sdet-plan-generator` keys off it to match contexts for a run,
so omitting it in a split defeats the purpose.

**What goes in each file:**
- Only that app's screens, elements and `ui_flow` edges. A Gojek frame never appears in the
  GoPay file, and no `ui_flow` edge may cross between apps — the two host apps have no shared
  navigation, so a cross-app edge is a mis-attributed frame. Raise it in `blocking_issues`
  rather than emitting the edge.
- `project_context.blocking_issues` scoped to that app's frames, so each QA sees only their own
  design gaps.

**A screen reused by every app** (a shared SDK component rendered identically in both) gets the
**same `screen_id` in every file** — that shared id is what lets the QA reviewing both plans see
it as one component, not two. Its `element_id`s still follow each file's own app convention, so
the same logical screen can legitimately carry different element ids per file.

**Never split on visual style alone.** GoPay Tagihan renders dark and Gojek Tagihan renders
light, but theme is a `screen_states` variant, not an app boundary. Split only on structural
evidence — page names, frame-group names, an explicit prefix.

## Notes on what the document didn't say — required on every run
Every output carries two fields. They are a to-do list for the document's author, **not** a
verdict on your work — a doc still being written will always produce some, and that is the
normal, expected result.

- `extraction_status`
  - `COMPLETE` — everything the document specified was captured.
  - `PARTIAL` — the document didn't specify some things; they're listed below. Normal for a
    work-in-progress doc.
  - `LIMITED` — a config file, schema or the validator wasn't available, so part of the run had
    less grounding than usual.
- `extraction_notes[]` — `{ field, reason, action, follow_up }`, where `follow_up` is:
  - `NEEDS_ANSWER` — someone has to supply this before the tests can cover it.
  - `WORTH_CHECKING` — a value was produced, but without its usual reference source. Confirm it.
  - `FYI` — optional content the document simply doesn't have. No action needed.

Rules:
- A field you cannot resolve is **left empty** and noted. Never filled with a placeholder, a
  plausible default, or a value carried over from another feature.
- `reason` says what you checked and what was there (*"PRD section 4.2 states the rule but names
  no module"*), not a bare *"not found"*.
- `action` is the concrete next step (*"confirm the target module with the PM"*), so the note can
  be acted on without re-reading the doc.
- Staying silent is the failure being designed out here. An empty `extraction_notes` on a
  half-written document is a worse outcome than a field left empty and explained.
## Matching the source document — normalise, don't invent
Source docs are human-written. Labels and values vary; the schema does not. Reading a value that
**is** in the document and expressing it in the schema's vocabulary is normalisation, and it is
required. Supplying a value the document does not contain is invention, and it is forbidden.
Do not confuse the two — refusing to normalise is not caution, it is a false open-point report.

**Field labels — match by meaning, not by key name.** Schema keys are output names, never strings
to search for. Look for the concept, whatever the doc calls it. An accessibility id may be
named `a11y id`, `Accessibility ID`, `testID` or `Layer name` depending on who built the frame.

**Enum values — match case-insensitively, emit the canonical spelling.** Compare the document's
value to the schema's allowed values ignoring:
- letter case — `DRAFT`, `draft`, `Draft` all → `"Draft"`
- surrounding whitespace, and any trailing punctuation or checkbox glyph (`☑ DRAFT` → `"Draft"`)
- separator style — `state injection`, `state_injection`, `State-Injection` → `"state-injection"`

Emit the schema's exact spelling, never the document's. This applies to **every** enum in the
schema, not just the ones named here.

**Synonyms — allowed when unambiguous, recorded when used.** `In Progress` → `"In Review"` is a
fair mapping; make it, and add an `FYI` note noting the source value so the mapping is auditable.
A pure case or whitespace fix needs no note — it is not a judgement call.

**When nothing matches, say what you found.** If no allowed value fits even case-insensitively,
leave the field absent and make the note specific — quote the document's value and list the legal
ones: *"header reads `PRD WALKTHROUGH`; not a legal value (allowed: …)"*. Never report it as
*"not found"* — the field was found, its value could not be expressed, and those send the reader
to different places. Never pick the nearest-looking value to dodge the note.

## Reads
JSON representation of the Figma design export (`.json` file) containing:
- Frames (navigational screens)
- Component instances and variants
- Prototype/connector links (ALL connector lines must be extracted)
- Text layers and accessibility IDs
- Element interactions and state definitions

Input is read-only; no Figma API calls made.

## Model
Fast tier — Haiku / Composer 2.5. Escalate to reasoning when:
- A frame's screen-vs-state grouping is ambiguous after applying the rules below.
- A connector's destination is unclear (e.g. target node ID is null or orphaned).
- Extracting connectors from a very large or deeply nested Figma file (to ensure 100% coverage).

## Tool usage & permissions
Minimize tools requiring user approval:
- **Read from JSON representation only** — accept pre-exported Figma design data as JSON input; no
  Figma API/MCP calls required. This eliminates Figma tool approval overhead.
- **Output JSON directly to stdout/artifact** — return design_context.json as structured output that can
  be piped or captured without requiring a Write tool.
- **Avoid intermediate file operations** — process the input JSON in-memory and output the result once at
  the end. This reduces approval prompts to zero (input is JSON provided inline or via Read).

## Screen vs. state (CRITICAL GUARDRAIL)
A screen is a unique navigational destination; a state is a visual variation of the same screen. Do
**not** create a new `screen_id` for:
- Loading, scroll-position, or pagination variants of the same frame.
- Form states (empty / typing / typed / error) of the same field or button.
- Platform, locale ("as-is vs redesign", ID vs EN), or viewport-crop variants that share the same
  purpose and destination.
- A dialog / overlay / bottom-sheet whose only exit is back to the screen that opened it — fold it in
  as a `screen_states` entry on that screen and document the open/close trigger under the opening
  element's `interactions` instead.

Only start a new `screen_id` when the frame is a genuinely different destination (distinct Figma frame
title *and* distinct purpose/route), including a component that is reused as its own destination from
multiple callers (e.g. a shared error dialog, native date/month picker, share sheet). Give each of those
one `screen_id` and reference it from every caller's `ui_flow` entry — never duplicate it per caller.

## Extract (→ `${CLAUDE_PLUGIN_ROOT}/schemas/design_context.schema.json`)

**CRITICAL: Extract ALL connector lines first, then filter elements by relevance to ui_flow.**

1. **ui_flow** (extract FIRST) — `{from_screen_id, trigger_element_id, to_screen_id, condition}` edges.
   - Traverse entire JSON tree to find ALL prototype/connector links (both element-level and frame-level).
   - Record the source element ID, destination screen, and explicit connector condition.
   - This becomes the ground truth for which elements matter.

2. **screens** — `screen_id` (`^[A-Z0-9_]+$`, UPPER_SNAKE from frame title, state/variant qualifiers
   stripped), `screen_name`, `purpose`, `screen_states` (empty/loading/error/success/offline), `screen_notes`.
   Include only screens that appear in ui_flow (as from_screen_id or to_screen_id).

3. **elements** (per screen, FILTERED) — `element_id` matching `^[A-Z0-9_]+\.[A-Z0-9_]+(\.[A-Z0-9_]+)?$`.
   **Include ONLY elements that:**
   - Appear as `trigger_element_id` in ui_flow, OR
   - Have explicit interactions/states defined in the design (multi-state buttons, form fields with
     validation states), OR
   - Are labeled text/content with semantic purpose.
   
   **Omit:** decorative elements (vectors, spacers, dividers), icons without interactions, nested groups
   with no functional purpose. Keep output concise — only functional, navigational, and state-bearing elements.

4. **project_context** — `{overall_ambiguity_rating: LOW/MEDIUM/HIGH, blocking_issues: []}`.
   - Missing connector traces (tappable elements with no traced destination).
   - Unreachable screens (appear in design but not in any ui_flow edge).
   - Incomplete or contradictory design annotations.

## Rules
- No locators — labels, types, states, interactions, flow only. Locators come from code-change-extractor.
- `label` = visible copy; `element_id` = stable functional token (UPPER_SNAKE, not text content).
- **Extract all connector lines first** — before filtering elements. Traverse full tree for every
  prototype/connector link (element-level ON_CLICK and frame-level AFTER_TIMEOUT transitions).
- **Filter elements by ui_flow relevance** — only include elements that trigger navigation (appear in
  ui_flow as `trigger_element_id`), or define interaction/state behaviors. Omit decorative elements.
- **Deduplicate ui_flow** — same from/to/trigger across frame variants = one ui_flow entry.
- **Never invent** — every gap (missing connector, unreachable screen, placeholder text) becomes a
  `blocking_issues` entry, not a filled assumption.
- Output design_context.json concisely — only functional elements that matter for test automation.

## Guardrails
Output valid JSON only, conforming to `${CLAUDE_PLUGIN_ROOT}/schemas/design_context.schema.json`. All `screen_id`,
`trigger_element_id`/`element_id`, `from_screen_id`, and `to_screen_id` values must satisfy the schema's
regex patterns exactly — no lowercase, no stray punctuation.

**Never invent.** Every gap — missing connector, unreachable screen, placeholder text, a frame
you cannot classify as screen-vs-state — becomes a `blocking_issues` entry. Never a filled
assumption, never an element ID guessed from a layer name when the accessibility ID is absent.

**Never merge two apps into one file.** If the export covers several apps, write several files —
do not pick the app with the most frames and drop the rest, and never generate one app's
`element_id`s under another app's `element_id_pattern`.

## Validate — report, never block
Run once **per output file** — every file in a multi-app split is validated separately, and the
ID-pattern checks below are re-run per file against **that file's own** app convention.
```
python3 -c "import json,jsonschema; jsonschema.validate(
  json.load(open('<each design_context file>')),
  json.load(open('${CLAUDE_PLUGIN_ROOT}/schemas/design_context.schema.json')))"
```
- Passes → `extraction_status: COMPLETE` (when `extraction_notes` is empty).
- Fails → **still write the file.** Convert every validator error into an `extraction_notes`
  entry (`field` = the validator's JSON path, `follow_up: NEEDS_ANSWER`) and set
  `extraction_status: PARTIAL`. Never patch a value in just to make validation pass.
- Validator unavailable (`jsonschema` not installed) → write the file, add a `WORTH_CHECKING` note on
  `ENVIRONMENT`, **and say so in your reply to the user** — not only in the JSON, which they may
  not open. Give them the command for their platform:
  - macOS / Linux with a system Python: `pip3 install --break-system-packages jsonschema`
    (plain `pip3 install` fails with an *externally-managed-environment* error under PEP 668)
  - inside a virtualenv, or with `uv`: `pip install jsonschema` / `uv pip install jsonschema`
  Never report an unvalidated output as valid — well-formed JSON is not schema conformance.
  Do not attempt the install yourself; it is the user's environment to change.
- **Connector completeness:** Count all visible prototype/connector lines in JSON and verify each appears
  in `ui_flow` (or flag missing ones in `blocking_issues`). Zero false positives/negatives.
- **Element filtering:** Every element in `elements` either (a) appears in `ui_flow` as trigger, or (b)
  has explicit interactions/states. No decorative/unused elements.
- **ID patterns:** All `screen_id` and `element_id` values match regex exactly — `^[A-Z0-9_]+$` and
  `^[A-Z0-9_]+\.[A-Z0-9_]+(\.[A-Z0-9_]+)?$` respectively. No lowercase, no stray punctuation.
- **Conciseness:** Output size is minimal; only functional elements included. Verify by comparing element
  count to connector count — should be roughly proportional.
