---
name: mobile-design-extractor
description: Extract the UI flow and element map from a mobile app's design into design_context.json — screens, element IDs (logical), interactions, states, ui_flow, deep links, and project-level ambiguity tracking. Input is a JSON export from the "Export Design Raw JSON" Figma plugin (connectors, prototype reactions, variants, Dev Mode annotations, and — format v2 — geometry, label chips, dashed group boxes, hand-drawn arrows). Collapses loading/scroll/error/locale variants into screen-level states instead of fragmenting them into separate screens, applies the design team's six flow-authoring conventions with recorded fallbacks, and reports unresolved navigation or content in blocking_issues rather than inventing it. App-agnostic; the frontend-primary stage. Its element IDs are the logical half of the locator mapping.
---

# Mobile Design Extractor (all 5 GoTo apps)

Design is the frontend-primary stage. This skill produces the screen/element map whose logical
`element_id`s later join to real per-platform locators from the Code Diff (see code-change-extractor).

## Config
`${CLAUDE_PLUGIN_ROOT}/config/<app>.json` → `naming_convention.element_id_pattern` and `role_vocabulary` govern the
role segment of each `element_id` (see *Element IDs*). Set `app` on the output object — the schema
doesn't require it, but the rest of the pipeline keys off it for multi-app runs.

## Preflight — resolve, or record and continue
**Never stop, never guess.** Work through these before extracting. Anything that cannot be
resolved becomes an `extraction_gaps` entry and the run continues — a partial, honestly
labelled output is always better than no output. What is forbidden is inventing a value to
fill the hole.

1. **App set — how many apps does this export cover?** Never assume one. Scan the frame tree
   before extracting and collect every app in scope from: `file.page` and `file.name` in the export
   envelope, `SECTION` / top-level frame-group names, a frame-name prefix (`[GoPay] …` /
   `Gojek — …`), or the user naming them. Map each to an app id: `gojek-consumer`, `gojek-driver`,
   `gofood-merchant`, `gopay-consumer`, `gopay-merchant`.
   - **One app** → one output file, as before.
   - **Two or more** → one output file per app (see *Output files*). Common when one Figma file
     holds a shared component's screens for every host app.
   - **Separate exports already supplied per app** → nothing to split; run once per file.
   - **None resolvable** → emit a single file, leave `app` absent, add a `BLOCKING` note on `app`.
     Do **not** guess from visual style; a dark-themed frame is not proof of an app.
   Report the decision in your reply before extracting: *"2 apps detected — gopay-consumer
   (pages 'GoPay Transfer', 'GoPay Tagihan'), gojek-consumer (page 'Gojek Tagihan'). Writing 2
   context files."*
2. **Config, per app in the set** — `${CLAUDE_PLUGIN_ROOT}/config/<app>.json`. Unreadable → add a `DEGRADED` note on
   `ENVIRONMENT` with reason *"cannot read ${CLAUDE_PLUGIN_ROOT}/config/<app>.json — plugin install
   may be incomplete"* and action *"run `claude plugin update aep-mobile@aep`, restart Claude,
   re-run"*. Set `extraction_status: DEGRADED`. Continue. **`naming_convention.element_id_pattern` and `role_vocabulary` come from this file only.** If it is unreadable, do NOT improvise a convention — derive IDs from the layer names per standard #3, and raise a `DEGRADED` note warning that IDs are unverified against the app convention and may not join to real locators at code-gen.
   In a multi-app split this is the whole point of splitting: **each file's `element_id`s must
   follow its own app's pattern and `role_vocabulary`.** IDs generated under the wrong app's
   convention silently fail to join to real locators at code-gen, which surfaces much later as a
   broken test rather than a bad extraction.
3. **Schema** — `${CLAUDE_PLUGIN_ROOT}/schemas/design_context.schema.json`. Unreadable → `DEGRADED` note on `ENVIRONMENT`, same install action.
   Fall back to the field list in this document **only** in that case, and say so in the note.
4. **Input.** The Figma export JSON is attached and parses as the envelope in *Input contract* below.
   - Not that shape (no `nodes[]`, no `export` block) → it is not an `Export Design Raw JSON` plugin
     export. Extract what you can, set `extraction_status: DEGRADED`, and add a `DEGRADED`
     note on `ENVIRONMENT` naming the shape you actually got.
   - `nodes[]` present but nothing classifies as `SCREEN` (see *Board node classification*) → emit with `INCOMPLETE` and a
     `BLOCKING` note saying the export looks empty. That is a bad export, not a design with
     zero screens.
   - `scope: "selection"` → connectors and destination frames outside the selection are simply not
     in the file. Add a `DEGRADED` note on `ENVIRONMENT`: *"export scope is `selection`;
     flows leaving the selected layers cannot be seen — re-export with `Export page` for full
     `ui_flow` coverage"*. Never report connector completeness as verified on a selection export.
   - `export.truncatedCount > 0` → the depth cap dropped children. Add a `DEGRADED` note on
     `ENVIRONMENT` listing `export.truncatedNodes[].name`. If any truncated node is (or contains) a
     screen frame, that is a `blocking_issues` entry too — elements below it were never exported.

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
  - `OK` — every field resolved from the export.
  - `INCOMPLETE` — one or more fields could not be resolved and were left absent. Normal for a
    work-in-progress board.
  - `DEGRADED` — a config file, schema or the validator wasn't available, so part of the run had
    less grounding than usual.
- `extraction_gaps[]` — `{ field, reason, action, severity }`, where `severity` is:
  - `BLOCKING` — a schema-required field is absent; someone has to supply it before tests can cover it.
  - `DEGRADED` — a value was produced, but without its usual grounding. Confirm it.
  - `INFO` — optional content genuinely absent from the source. No action needed.

Rules:
- A field you cannot resolve is **left empty** and noted. Never filled with a placeholder, a
  plausible default, or a value carried over from another feature.
- `reason` says what you checked and what was there (*"PRD section 4.2 states the rule but names
  no module"*), not a bare *"not found"*.
- `action` is the concrete next step (*"confirm the target module with the PM"*), so the note can
  be acted on without re-reading the doc.
- Staying silent is the failure being designed out here. An empty `extraction_gaps` on a
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
fair mapping; make it, and add an `INFO` note noting the source value so the mapping is auditable.
A pure case or whitespace fix needs no note — it is not a judgement call.

**When nothing matches, say what you found.** If no allowed value fits even case-insensitively,
leave the field absent and make the note specific — quote the document's value and list the legal
ones: *"header reads `PRD WALKTHROUGH`; not a legal value (allowed: …)"*. Never report it as
*"not found"* — the field was found, its value could not be expressed, and those send the reader
to different places. Never pick the nearest-looking value to dodge the note.

## Reads
One `.json` file produced by the **Export Design Raw JSON** Figma plugin (or by its REST-parity
script `tools/figma_rest_export.py`, which emits a byte-identical payload). Input is read-only; no
Figma API/MCP calls are made.

---

## Input contract — the Figma plugin export
This is the **only** input shape this skill accepts. Everything in *Extract* is derived from these
fields; there are no others. Read this before mapping anything.

### Envelope
```jsonc
{
  "exportedAt": "2026-08-11T04:12:07.331Z",  // ISO-8601, when the export ran
  "scope": "page" | "selection",             // "page" = whole active page; "selection" = picked layers only
  "file": { "name": "<Figma file name>", "page": "<Figma page name>" },
  "export": {
    "formatVersion": 2,                      // absent = v1 (no geometry, no board shapes). 2 adds
                                             // geometry, connector caps, board-level shapes, dashed, rotation
    "maxDepth": 30,                          // walk depth cap (v1 exports were cut at 15)
    "nodeCount": 1842,                       // nodes kept (after hidden/decorative pruning)
    "truncatedCount": 3,                     // nodes whose children the cap dropped — 0 = nothing cut
    "truncatedNodes": [ { "id": "12:34", "name": "Icon Grid", "type": "INSTANCE" } ]  // ≤20 samples
  },
  "nodes": [ /* Node */ ]                    // page scope: one PAGE node; selection scope: one per selected layer
}
```

### Node
Every key is **omitted when absent, null, `[]` or `{}`** — the plugin prunes empties, so *absence
carries meaning*. No `reactions` key means the node has no prototype interaction. No `children`
key means no kept children (all pruned, or the depth cap hit).

```jsonc
{
  "id": "2015:31162",                 // always present — use for source_ref
  "name": "History Page",             // layer name — the naming standards below parse this
  "type": "PAGE"|"CANVAS"|"SECTION"|"FRAME"|"GROUP"|"COMPONENT"|"COMPONENT_SET"|"INSTANCE"
        |"TEXT"|"CONNECTOR"|"STICKY"|"SHAPE_WITH_TEXT"|"RECTANGLE"|"VECTOR"|...,
  "characters": "Approve",            // TEXT nodes only — the visible copy
  "connectorStart": ConnectorEndpoint, // CONNECTOR only
  "connectorEnd":   ConnectorEndpoint, // CONNECTOR only
  "connectorLineType": "ELBOWED"|"STRAIGHT",                    // CONNECTOR only
  "connectorStartStrokeCap": "NONE"|"ARROW_LINES"|"ARROW_EQUILATERAL"|"TRIANGLE_FILLED"|...,
  "connectorEndStrokeCap":   "NONE"|"ARROW_LINES"|...,          // no arrowhead => a tether, not a flow
  "x": 1204, "y": 880, "width": 390, "height": 844,  // FRAME/INSTANCE/COMPONENT/COMPONENT_SET/SECTION/GROUP/TEXT/
                                                     // STICKY/SHAPE_WITH_TEXT and kept board shapes (RECTANGLE/LINE/…),
                                                     // integers, PARENT-RELATIVE
  "rotation": -45,                    // v2, LINE/VECTOR only, non-zero only — picks which bbox
                                      // diagonal a hand-drawn arrow occupies
  "dashed": true,                     // v2, only when dashPattern is non-empty — a dashed board
                                      // rectangle is a group box clustering the state frames inside it
  "componentPropertyDefinitions": {    // COMPONENT_SET / COMPONENT — the declared state surface
    "State": { "type": "VARIANT", "defaultValue": "Default", "variantOptions": ["Default","Error","Loading"] },
    "Label#12:3": { "type": "TEXT", "defaultValue": "Approve" }
  },
  "componentProperties": {             // INSTANCE — the overridden values
    "Label#12:3": { "type": "TEXT", "value": "Approve Disbursement" }
  },
  "variantProperties": { "State": "Error", "Type": "Primary" },  // INSTANCE of a variant, or COMPONENT inside a set
  "reactions": [ Reaction ],           // prototype interactions
  "annotations": [                     // Dev Mode annotations — where a11y / testIDs are usually written
    { "label": "a11y id: approve_btn", "labelMarkdown": "...", "properties": [ { "type": "..." } ], "categoryId": "..." }
  ],
  "flowStartingPoints": [ { "nodeId": "12:3", "name": "Disbursement Flow" } ],  // PAGE node only
  "text": { "characters": "if amount > 5jt" },  // sublayer — CONNECTOR / STICKY / SHAPE_WITH_TEXT / TABLE_CELL
  "textBackground": { },                        // normally pruned away entirely
  "children": [ Node ]
}
```

### Optional enrichment — capture when present, never require, never flag
Two things are **nice to have**, not part of the contract:

| Field | Read from | When absent |
| :--- | :--- | :--- |
| `elements[].accessibility_id` / `platform_hints` | Dev Mode `annotations[]` | normal — most files have no annotations at all |
| `screens[].deep_link` | a `URL` prototype action matching the config `deeplink_scheme`, or a `Note`/`Context` note stating one | normal — designers are not expected to document routing |

For both:
- **Never** emit an `extraction_gaps` entry, a `blocking_issues` entry, or any other flag because
  a node has no `annotations`, because no element has an `accessibility_id`, or because a screen
  has no `deep_link`.
- **Never** let their absence change `extraction_status` or `overall_ambiguity_rating`.
- **Never** treat either as the required source for anything. Every mandatory field is derived from
  names, reactions, variants and connectors — the things every Figma file has. These two only ever
  *add*.
- **Never** construct a plausible value to fill them. A guessed URI is worse than an absent one:
  downstream will navigate straight to it and the test fails somewhere unrelated.

Both have a real source later in the pipeline. Locators arrive post-build from
code-change-extractor; deep links come from `plan_context` test hooks and `rfc_context`
`navigation_changes`. An empty pre-build locator handoff, and a screen with no deep link, are the
expected state — not gaps in the design.

### The same rule covers every intent field
`screen_notes` and `validations_and_edge_cases` describe **intent**, not structure. A board carries
them only when a designer happened to write a note. The script derives what the board supports —
note text routed by connector, else by position — and:

- **Never raise a gap, at any severity, because one is empty.** A `BLOCKING` gap means a
  schema-required field could not be filled *and* something downstream needs it. An empty intent
  field is neither. A run once raised `BLOCKING` on `screens[].purpose` for all 33 screens; the
  field had no consumer anywhere in the pipeline, and the claim that the board lacked the content
  was false.
- **`purpose` and `states_represented` are no longer produced at all.** Both were audited against
  every skill and schema and had zero readers. They are optional in the schema so hand-authored
  files stay valid; the extractor does not emit them. Do not reintroduce them, and never flag their
  absence.
- **The gaps you do report are the ones the script derived** — unresolvable connectors,
  non-descriptive names, unreachable screens, truncation. They are computed from counters, not
  judged. Add a gap of your own only for something genuinely semantic that the script cannot see.

**`ConnectorEndpoint`** — exactly one of two forms, and the difference decides whether a flow is
resolvable at all:
```jsonc
{ "endpointNodeId": "2015:31170", "magnet": "AUTO"|"TOP"|"BOTTOM"|"LEFT"|"RIGHT"|"CENTER" }  // attached to a node
{ "position": { "x": 1204, "y": 880 } }                                                       // floating — attached to nothing
```
A floating endpoint is a connector the designer never snapped to a layer. It is **never**
resolvable — it goes to `blocking_issues`, never to a guessed nearest frame.

**`Reaction`**:
```jsonc
{
  "trigger": { "type": "ON_CLICK"|"ON_PRESS"|"ON_HOVER"|"ON_DRAG"|"AFTER_TIMEOUT"
                     |"MOUSE_ENTER"|"MOUSE_LEAVE"|"MOUSE_UP"|"MOUSE_DOWN"
                     |"ON_KEY_DOWN"|"ON_MEDIA_HIT"|"ON_MEDIA_END",
               "timeout": 3000, "delay": 0 },
  "actions": [
    { "type": "NODE", "destinationId": "2015:31200"|null,
      "navigation": "NAVIGATE"|"SWAP"|"OVERLAY"|"SCROLL_TO"|"CHANGE_TO",
      "transition": { }, "preserveScrollPosition": false },
    { "type": "BACK" },
    { "type": "CLOSE" },
    { "type": "URL", "url": "gopaymerchant://disbursement/history" },
    { "type": "SET_VARIABLE", "variableId": "...", "variableValue": { } },
    { "type": "CONDITIONAL", "conditionalBlocks": [ { "condition": { }, "actions": [ /* … */ ] } ] }
  ],
  "action": { }   // legacy single-action mirror; when both exist they say the same thing — read `actions`
}
```
`destinationId: null` **survives the pruning** (only empty arrays/objects are dropped, not nulls).
A tap whose `destinationId` is null, or a reaction with a `trigger` and no `actions` key at all, is
exactly the "tap prototype with no destination" case standard #2 exists to prevent — flag it.

### What the plugin already threw away — do not look for it
| Dropped | Consequence for you |
| :--- | :--- |
| Hidden layers (`visible: false`), whole subtree | A designed-but-hidden state is invisible here. Never infer one. |
| Decorative leaf shapes **inside frames** with no `reactions` / `annotations` — `VECTOR`, `RECTANGLE`, `ELLIPSE`, `POLYGON`, `BOOLEAN_OPERATION`, `LINE`, `STAR` | Icons and backing shapes are gone. One that survives is **signal, not noise**: it is tappable, annotated, a connector points at it — or (v2) it sits at **board level** (ancestors all PAGE/CANVAS/SECTION/GROUP), where the same types are convention carriers: dashed group boxes, label bars, hand-drawn arrow lines. |
| Styling, colour, fonts, effects | No aesthetic reasoning is possible, and none is needed. The single exception is the v2 `dashed` bit — one boolean, kept because it separates a group box from a label bar. |
| Children below `export.maxDepth` (30; v1 exports were cut at 15) | Reported in `export.truncatedCount` / `truncatedNodes`, never silent. |
| Every empty `[]` / `{}` at any depth | Absence = "none", not "unknown". |

**Kept, and load-bearing: `x` / `y` / `width` / `height`** on every layout-bearing type. This is the
only thing that separates a screen from a caption box, a decision box or a note box — Figma draws
all four as the same kind of frame. Sizes are integers and positions are **parent-relative**, which
is sufficient because every comparison you make is between siblings (a banner against the screens
beside it, screens against each other for reading order). Never compare `x`/`y` across different
parents. This is *not* licence to reason about appearance: use size and position for classification
and ordering only, never to infer that something "looks like a dialog".

**A shape a connector points at is never pruned**, whatever its type — designers do anchor flow
arrows to plain rectangles.

### Board node classification — what everything else keys off
A **board node** is a node of type `FRAME`, `COMPONENT` or `INSTANCE` whose ancestor chain up to the
export root contains only `PAGE` / `CANVAS` / `SECTION` / `GROUP` nodes — a top-level object on the
flow board, including one wrapped in a section or a group.

**Not every board node is a screen.** A flow board also carries caption boxes, lane banners,
decision boxes and note boxes, and Figma draws all of them as the same kind of frame under the same
kind of section. Treating them all as screens is what produces phantom screens and dead connectors.

> **The script does this classification.** The table below documents *what it decides and why*, so a
> reviewer can audit a `node_class` / `classified_by` value or adjust a threshold. You do not run it
> by hand. Bare board-level `TEXT` nodes classify by the same rules — a question with ≥2 outgoing
> connectors is a `DECISION` ('Gopay Plus or not?' written as naked text), anything else
> text-bearing is a `CAPTION` — so a decision or state chip needs no frame around it to be read.
> The classes are, in priority order:

| Class | Test |
| :--- | :--- |
| `NOTE` | Name matches an annotation-component name — default `Notes`, `Note`, `Annotation`, `Comment`, `Info`, `tooltip*`, matched case-insensitively with `*` as a prefix wildcard — **or** its subtree holds a `TEXT` whose copy starts `Note` / `Context`. **Never fires on a device-sized frame**: annotation names are generic words that can name a real screen, and an annotation component is never screen-sized (geometry-less exports keep the old name-only read). |
| `DECISION` | Small (see *Size*), text-bearing, its text ends in `?`, **and** it has ≥2 outgoing connectors. All three conditions — a small question with one exit is a caption, not a branch. |
| `CAPTION` / `LANE_BANNER` | Small, text-only, and a sibling of at least one node classified `SCREEN`. It labels the group it sits in. |
| `SCREEN` | Device-sized (see *Size*). This is the only class that gets a `screen_id`. |
| `UNKNOWN` | Everything else → `blocking_issues`, never silently promoted to `SCREEN`. |

**Size — the primary test.** `width` / `height` are on every `FRAME` / `INSTANCE` / `COMPONENT` /
`SECTION` / `GROUP` / `TEXT` in the export. A `SCREEN` is device-**width** with no upper bound on
height: `width` roughly 300-520, `height` ≥ 500.

**Width does the work; height only rules out strips.** There is no maximum height — a scrolling
screen is routinely two or three viewports tall (a real board has a 360×2066 welcome screen beside
360×918 dialogs, and both are screens). Capping height rejects exactly the long screens that matter.
What the height floor excludes is the label strip: caption and decision boxes on a real board
measure 360×37, 302×116, 358×118 — the same width as a screen, a fraction of the height. When a
frame sits on the boundary, prefer `SCREEN` and record an `INFO` gap.

**Fallback when the export carries no geometry** (an older export, or a `truncatedNodes` casualty):
use descendant count. On a measured board, screens hold 200-690 descendants and caption/decision/note
boxes hold ≤ 6 — the split is wide and unambiguous. It is still a proxy: a genuinely minimal screen
could fall under it. **Say which test you used** in `extraction_gaps` whenever it was the fallback.

**A `FRAME` nested inside a `SCREEN` is an element of that screen**, never a screen — unless a
connector or reaction targets it directly, which promotes it to a board node to be classified here
and then judged under *Screen vs. state*.

### Collapsed screens keep every frame id — connectors resolve against all of them
*(Script behaviour, documented here because it is the single most expensive thing to get wrong.)*

A screen is routinely drawn as **N sibling frames sharing one base name**, one per state, laid out
side by side. They collapse into one `screen_id` (see *Screen vs. state*), and when they do:

- Record **every** collapsed frame id in `screens[].source_refs`, with `source_ref` as the
  representative. A screen drawn as 9 state frames has 9 ids.
- **Resolve every connector endpoint against the whole set.** An endpoint whose ancestor is *any*
  collapsed frame resolves to that `screen_id`.
- Populate `screen_states` with each frame's **qualifier**, not its base name. Nine entries all
  reading `"Confirm account"` carry no information and are a symptom of this step being skipped.

Getting this wrong is silent and expensive: designers draw the outgoing arrow from whichever state
the transition happens in — the error state, the filled-form state — not from the first frame. On a
real board, `Confirm account` collapses 9 frames, and the one chosen as representative had a single
inbound connector while **six outgoing connectors hung off four of the others**. Resolving against
the representative alone dropped all six, and the screen looked like a dead end.

An endpoint that resolves to the same `screen_id` at both ends is **intra-screen**: a state
transition or an annotation, not navigation. Count it in the sidecar's `connectors_intra_screen`
and do not emit an edge — but never let it silently vanish into the unresolved bucket.

**Two more clustering signals collapse frames a shared base name cannot (v2 exports, script
behaviour).** Both run before `frame_to_screen` is built, same as banner renames, so no element or
edge ever references a screen_id that later disappears:

- **Dashed group box.** A dashed board-level shape drawn around ≥2 sibling screen frames is the
  design convention for "these are states of one screen" — the frames merge whatever their names.
  A box whose screens carry **two or more different proper names** is a conflict, not a merge:
  it lands in `blocking_issues` and `label_attach_conflicts`, never a guessed winner. Each merge
  is recorded in the sidecar's `group_box_merges[]` and counted in `group_box_clusters`.
- **Component fingerprint (fallback, recorded).** Sibling frames that are ALL default-named
  (`Frame 2117130859` …) and share ≥80% of their component-instance names (≥3 components each)
  merge as state frames of one screen. Deliberately narrow: **properly named screens never merge
  by fingerprint** — Login and Register legitimately share components. Every merge is a
  `DEGRADED` gap plus a sidecar `fingerprint_merges[]` entry, so it can be audited and challenged.

**Component names come from the defaults; the app config only overrides them.** The names above are
the built-in defaults, and **an app config that says nothing about `design_components` is the normal
case** — apply the defaults, silently. Read
`${CLAUDE_PLUGIN_ROOT}/config/<app>.json` → `design_components` only to *override* them:
- Block absent, key absent, or list empty → use the default for that key. Never a note, never a
  flag; absence is not a configuration gap.
- List present and non-empty → it **replaces** the default for that key, so an app that names its
  annotation component something else does not inherit names that would misfire.
- `decision` and `lane` default to **empty**, which is deliberate: no such components exist, and the
  classifier does not need them. If design ever introduces one, adding it to that app's config makes
  it an extra first-priority trigger on the matching row — a config edit, not a skill change.

> The `NOTE` row is the only one keyed on a name, and only because that component already exists on
> these boards. It is a hint that happens to be there, **not** something the design must supply —
> every other class is decided from geometry, text and connector degree, so the classifier works on
> a board that follows no naming convention at all.

---

## Design conventions — how the design team writes flows
The design team has standardised on the six conventions below. Each has a **read** (the compliant
case), a **fallback** (the inference you may make when it was not followed — always within reason,
always recorded), and a **flag** (when even the fallback is not defensible).

Every fallback you take is an `extraction_gaps` entry with `severity: DEGRADED`, and every
flag is a `project_context.blocking_issues` entry. Tally both into
the sidecar `design_context.report.json` so the design team gets one actionable list per export.

### 1. Connectors point element → **screen**, not element → element
- **Read.** `connectorStart.endpointNodeId` resolves to an element inside a screen frame;
  `connectorEnd.endpointNodeId` resolves to a screen frame. → `from_screen_id` = the source's
  nearest screen-frame ancestor, `trigger_element_id` = the source element, `to_screen_id` = the
  destination frame. `edge_source: "CONNECTOR"`, `confidence: "EXPLICIT"`.
- **Fallback.** The destination is an element *inside* a different screen frame → walk its
  ancestors to the nearest screen frame and use that. `edge_source: "CONNECTOR_INFERRED"`,
  `confidence: "INFERRED"`, plus a `DEGRADED` note naming the connector `id`.
- **Fallback.** The source is the screen frame itself (frame → frame connector) → emit the edge
  with **no** `trigger_element_id` if the source screen has no single obvious trigger; if it has
  exactly one interactive element whose own reaction targets the same destination, use that one and
  mark `INFERRED`. Never invent a trigger token to satisfy the schema.
- **Fallback — destination is a `CAPTION` / `LANE_BANNER`.** The connector points at the *label* of
  a group rather than at a screen. The destination is that group's **entry screen**: among the
  `SCREEN` siblings sharing the banner's parent, the topmost-then-leftmost by `y`, then `x`. Emit
  `edge_source: "CONNECTOR_INFERRED"`, `confidence: "INFERRED"`, and a `DEGRADED` note naming
  the banner. No `SCREEN` sibling → do not guess an entry; flag it.
  - **Order by `y`/`x` only — never by array order.** Children are stored in z-order, which has no
    relationship to reading order; picking the first array element selects an arbitrary screen that
    looks plausible and is silently wrong. Without geometry this fallback is **not available**:
    flag the connector instead, and say the export predates geometry.
  - **A lane banner usually contains nothing — resolve it as a spatial band, not a parent.** On a
    real board the banner is a full-width strip (1416×64) sitting *beside* the screens it fronts,
    not wrapping them; walking up its ancestors finds only the `SECTION`. So: take the banner's
    top-level ancestor, look at its **siblings**, and select the `SCREEN`s whose `y` is below the
    banner and above the **next banner** (the next sibling of comparable width and under ~150pt
    tall). The entry screen is the topmost-then-leftmost of that band.
    Walking up to the `SECTION` and taking its first screen is the trap here: every banner in the
    section resolves to the same screen, so two branches of one decision silently collapse onto a
    single destination and the branch looks real while being wrong.
  - **Self-loop guard.** If the resolved entry screen is the same screen the connector started
    from, the resolution is wrong by construction — drop the edge and flag it. A lane you enter
    from outside never resolves back to the caller.
- **Fallback — destination is (or sits inside) a `SECTION` with no board-node ancestor.** Some
  teams draw the arrow into a section rather than at a screen — the lane-banner semantic expressed
  with an explicit container. The destination is the section's **entry screen**: topmost-then-
  leftmost `SCREEN` among the section's direct children (the only siblings whose coordinates are
  comparable); a section with no direct screen defers to the next section out. Emit
  `edge_source: "CONNECTOR_INFERRED"`, `confidence: "INFERRED"`, counted in
  `section_entry_inferred`. Same self-loop guard: an entry resolving back to the source screen is
  flagged, never emitted.
- **Fallback — destination is a `DECISION`.** See *Contraction* below.
- **Flag.** Either endpoint is floating (`position`, no `endpointNodeId`); or the destination
  resolves into the *same* screen frame as the source (an intra-screen connector is an annotation,
  not a flow — check standard #5 first); or the destination node id is not present anywhere in the
  export (orphaned, or cut by the depth cap).

#### Contraction — reaching a screen through a decision box
A branch is drawn as *screen → decision box → (labelled connectors) → destinations*, so the
condition sits one hop away from the screen it belongs to. Collapse that hop:

1. Source is a `SCREEN`, destination is a `DECISION` → for **each** labelled connector leaving the
   decision, emit one edge from the source screen, `condition` = that connector's label, resolving
   its own destination by the rules above (including the lane-banner fallback).
2. **Normalise the entry/exit seam.** A decision box is typically *entered* on its child `TEXT` and
   *exited* from the parent `FRAME` — two different node ids, so the path looks broken. Lift a
   `TEXT` endpoint **exactly one level** to its parent before matching. One level, never more.
3. Mark every edge produced this way `edge_source: "CONNECTOR_CONTRACTED"`. `source_ref` holds the
   **exit connector** (as on every other edge); the box itself goes in `decision_node_id`.
4. **Compose the condition rather than copying a label.** A bare `YES` is meaningless without the
   question it answers, and the question is sitting in the decision box. Emit
   `"<question> — <value>"` — `Does user have GoPay+? — YES` — normalising the designer's spacing
   (`GoPay+ ?` → `GoPay+?`), and keep any label from the connector *into* the decision in front via
   `" / "` so no authored text is lost. `decision_question` and `decision_value` carry the same two
   halves separately, so a consumer can build a precondition without re-parsing the string.

**Hard limits — these are not tuning knobs.** Contraction that chases hops through the tree
manufactures flows that do not exist: on a real board an unbounded version (lift to any
connector-bearing ancestor, up to 3 hops) produced **853 edges, 595 carrying fabricated
conditions**, because lane and section containers act as hubs joining every path to every other. So:
- **At most one hop.** A destination still not a `SCREEN` after one hop → `blocking_issues`.
- **Fan-out ≤ 4.** A hop node with more than four outgoing connectors is a hub, not a decision —
  abort and flag.
- **Never hop through** a `SECTION`, `PAGE`, `GROUP` or any lane container.
- If total edges ever approach the connector count multiplied by the average fan-out, contraction
  has escaped its bounds — stop and flag rather than emit.

### 2. Tap prototypes always name their destination
Read every `reactions[]` entry on every node.

| Action | Meaning | Emit |
| :--- | :--- | :--- |
| `NODE` + `navigation: "NAVIGATE"` | real navigation | `ui_flow` edge, `navigation_kind: "NAVIGATE"` |
| `NODE` + `"OVERLAY"` | dialog / bottom sheet | fold into the **source** screen's `screen_states` (see *Screen vs. state*), `navigation_kind: "OVERLAY"`; own `screen_id` only when ≥2 screens open it |
| `NODE` + `"SWAP"` / `"CHANGE_TO"` | variant / state change | **not** a `ui_flow` edge, and not recorded anywhere — a variant swap is presentation, and nothing downstream consumes element-level states |
| `NODE` with a destination **outside this export** | link into a library component | counted in `reactions_destination_outside_export`, never an edge — the destination cannot be resolved from here. On a measured board **all 29** destination-bearing links were of this kind, so prototyping contributed no navigation at all |
| `NODE` + `"SCROLL_TO"` | intra-screen scroll | **not** a `ui_flow` edge |
| `BACK` | return to caller | edge with `navigation_kind: "BACK"` **only if** exactly one caller exists in `ui_flow`; otherwise flag |
| `CLOSE` | dismiss overlay | closes the overlay state; no new screen |
| `URL` | deep link or external | if the URL starts with the config's `deeplink_scheme`, set `screens[].deep_link` on the destination screen and emit `navigation_kind: "DEEP_LINK"`; any other URL is an external link — record it on the element's `interactions` and move on. Neither case is ever a blocker |
| `CONDITIONAL` | branch | one `ui_flow` edge per `conditionalBlocks[]` entry, `condition` from that block; if the block's condition does not serialise readably, flag |
| `SET_VARIABLE` | prototype bookkeeping | ignore for flow; may inform `condition` |

- **Fallback.** `AFTER_TIMEOUT` with a `NODE` destination is a real edge — `condition` = *"after
  <timeout>ms"*. `ON_HOVER` / `MOUSE_ENTER` / `MOUSE_LEAVE` are desktop-only prototype
  scaffolding on a mobile design; drop them and note once, not per node.
- **Flag.** Tap-family trigger (`ON_CLICK` / `ON_PRESS` / `ON_DRAG`) with `destinationId: null`, or
  with no `actions` at all → `blocking_issues`: *"tappable element `<name>` (`<id>`) has a
  prototype trigger with no destination — standard #2"*. Never guess where it goes.

### 3. Human-readable frame and layer names
- **Screen frame name → `screen_name` verbatim.** `screen_id` = the name with any trailing state
  qualifier stripped, then UPPER_SNAKE (non-alphanumerics → `_`, repeats collapsed, ends trimmed).
  A state qualifier is the segment after the **first** ` — `, ` – `, ` - ` or ` / ` separator.
  **Keep the base, drop the qualifier — never the reverse.** `Confirm account / EN` is
  `CONFIRM_ACCOUNT` with `EN` as a state; emitting a screen called `EN` is the failure mode here,
  and it produces an id that means nothing and collides across features. Split once, from the left,
  and take element 0.
  - `History Page` → `HISTORY_PAGE`
  - `Confirm Disbursement Dialog` → `CONFIRM_DISBURSEMENT_DIALOG`
  - `Approve Disbursement — Error` → `APPROVE_DISBURSEMENT`, and `"Error"` joins that screen's
    `screen_states` (and `state_kinds: ["ERROR"]`)
- **Interactive layer name → `element_id`.** The convention is `<Role>/<Variant> — <what it does>`
  or `<Role> — <what it does>`; the role is the token before the first `/` or ` — `, the purpose is
  the remainder.
  - `Button/Brand — Approve` → role `Button`, purpose `Approve`
  - `Field — Affiliator Search` → role `Field`, purpose `Affiliator Search`
  Build the id from the app config's `naming_convention` — see *Element IDs* below.
- **Fallback (role).** Role token missing or unrecognised → derive the role from the node's `type`
  and `reactions` (`TEXT` with no reactions → `LABEL`; any node with a tap reaction → `BUTTON`;
  a node with a `TEXT`-typed `componentProperties` entry and a tap reaction → `INPUT`). Record a
  `DEGRADED` note.
- **Fallback (purpose).** No purpose in the layer name → use the element's visible copy: the node's
  own `characters`, or the `characters` of its single TEXT descendant, or a `componentProperties`
  `TEXT` `value`. Record a `DEGRADED` note.
- **Flag.** The name is a default or a visual-only description (`Frame 427`, `Group 12`,
  `Rectangle`, `Component 3`, `Blue Button`, `Icon/24`) **and** no copy is available → the element
  gets no id and goes to `blocking_issues`: *"element `<id>` has a non-descriptive name and no
  visible copy — cannot produce a stable element_id (standard #3)"*. A screen frame in this state
  is always a blocker, because every element id under it inherits the screen id.

### 4. Branching conditions live on the connector label
- **Read.** A connector's label is its text sublayer: `text.characters`. Copy it into the edge's
  `condition` verbatim.
- **Fallback.** No label and only **one** outgoing edge from that trigger element → `condition` =
  `""` (unconditional). That is normal and needs no note.
- **Flag.** No label and **two or more** outgoing edges from the same trigger element → the branch
  is undecidable → `blocking_issues`: *"`<element>` has N unlabelled outgoing connectors — which
  condition selects which destination is not stated (standard #4)"*. Emit every edge with an empty
  `condition` so the flows are not lost; do not invent the discriminator.
- A free-floating `TEXT` / `STICKY` node that reads like a condition but is attached to nothing is
  **not** a condition — it is unattached commentary. Note it as `INFO`, do not bind it to an edge.

### 5. Notes and context are connected to what they describe
- **Read.** A `CONNECTOR` is a **note connector** when either endpoint — or **any ancestor of
  either endpoint** — is classified `NOTE`. It is not a flow. Append the note's text to the other
  endpoint's `screen_notes` (or, if the other endpoint is an element, to that element's
  `validations_and_edge_cases`). Classify these **before** running standard #1, so a note connector
  is never counted as a missing flow.
  - **Match on the node, not on the copy.** A note is normally an `INSTANCE` of an annotation
    component, and the word "Note" then lives in a *child* `TEXT` (`Notes / Annotation`) while the
    body text says something else entirely. Testing the endpoint's own `characters` for a `Note` /
    `Context` prefix therefore matches **nothing** on a real board — it is kept below only as an
    additional trigger, never as the only one.
  - The ancestor walk is what makes this work: a connector usually lands on a child *inside* the
    note component, not on the component node itself.
- **Fallback.** A `NOTE` node with no connector at all → attach it to the `SCREEN` that geometrically
  contains it, else the nearest `SCREEN` by centre-point distance, with an `INFO` note recording that
  the attachment was positional. Without geometry, fall back to the section it sits in and say so.
- **Flag.** A `NOTE` node outside every screen, with no connector and no near neighbour → it belongs
  to nothing → `blocking_issues`, quoting the first ~100 characters so the designer can find it.

### The arrowhead defines direction, not the order the line was drawn
Figma lets a connector's arrowhead be flipped independently of which end was drawn first, so
`connectorStart` is **not** reliably the source. On a real board 2 of 47 connectors point backwards,
and reading them as drawn produced two **silently reversed** flow edges — a wrong edge is worse than
a missing one, because nothing downstream can tell.

The script reads `connectorStartStrokeCap` / `connectorEndStrokeCap`:

| end cap | start cap | direction | stamped |
| :--- | :--- | :--- | :--- |
| arrow | not arrow | as drawn | (nothing — the ordinary case) |
| not arrow | arrow | **swapped** | `edge_direction_source: ARROWHEAD_REVERSED` |
| arrow | arrow | as drawn, bidirectional | `AMBIGUOUS` |
| neither | neither | as drawn, undirected | `UNDIRECTED` |

`connector_direction_flipped` in the sidecar counts the swaps. Non-zero is worth raising with
design: the line reads backwards on the board even though the extraction is now correct.

### 6. States drawn as separate frames are labelled beside the frame
Designers rarely use Figma variants for QA-facing states — variants are invisible on the board. The
convention instead: **one frame per state, with the state named by a label chip or bar sitting
directly above the frame** (*"Empty State"*, *"Loading"*, *"Not eligible to become upliner yet"*),
optionally clustered by a dashed box, optionally bound by a hand-drawn arrow. The chips keep Figma's
default names; the text inside them carries everything.

Two caption shapes, and the difference is width:

| Shape | Size | Means |
| :--- | :--- | :--- |
| **State label** | ≤ the screen's width (360×37) | names the state of the **one** screen directly below |
| **Lane / section banner** | ≫ any screen (1416×64) | heads a **band** of screens |

- **Read (v2 exports — the script sweeps these proactively, on every board).** Evidence order per
  label, strongest first:
  1. **Arrow-bound** — a board-level LINE whose endpoints touch the label on one end and a screen
     frame on the other. Explicit binding; counted in `arrow_bound_labels`.
  2. **Column-aligned** — exactly **one** screen 0-120px below the label with ≥80% horizontal
     overlap. Counted in `state_labels_attached`.
  Either way the label's text joins that screen's `screen_states`, and its normalised kind joins
  `state_kinds`. Candidates are CAPTION-classified frames and board-level TEXT nodes; anything
  wider than 1.5× the screens beside it is a lane banner, not a state label.
- **Read (dashed group box).** A dashed board shape around ≥2 sibling screen frames merges them
  into one screen — see *Collapsed screens* above.
- **Fallback (v1 exports, connector-triggered).** On an export with geometry but no proactive
  sweep result, the old path still runs: when a connector fails to resolve and its destination is a
  gibberish-named text strip, the strip is tested as a label of the one properly-named screen below
  it (`label_frames_resolved`). Measured on a real board it accepted the two genuine label frames
  and rejected an external-file pointer and a decision box.
- **Fallback (fingerprint).** Default-named sibling frames sharing a component skeleton merge as
  states of one screen — recorded as a `DEGRADED` gap, see *Collapsed screens*.
- **Flag.** A label aligning with **2+ screens**, or a dashed box surrounding screens with 2+
  distinct proper names → `label_attach_conflicts` + a `blocking_issues` entry naming the label
  text and candidate screens. Never guessed. A label aligning with zero screens is silence — most
  captions are just captions.

**What this means for design:** the chip row above state frames is genuinely machine-readable now.
Drawing the connector to the screen frame itself (standard #1) is still better for *navigation*,
but for naming states, a chip per frame plus a dashed box around the set is the compliant pattern.

### Convention compliance is reported, not enforced
A non-compliant export still produces a full `design_context`. Falling back is the default
behaviour; refusing to extract is not. What is forbidden is a silent fallback — every one is in
`extraction_gaps`, and the totals are in the sidecar `design_context.report.json`.

---

## Element IDs — built from the app config, never from memory
`naming_convention.element_id_pattern` is `<screen_id>.<element_role>` and `role_vocabulary` lists
the role suffixes (`_btn`, `_input`, `_label`, `_toggle`, `_tab`, `_list`). Take both **verbatim**,
including their casing:

```
element_id = <SCREEN_ID> "." <purpose_lower_snake> <role_suffix>
```
`Button/Brand — Approve` on frame `Approve Disbursement` → `APPROVE_DISBURSEMENT.approve_btn`.
`Field — Affiliator Search` on frame `History Page` → `HISTORY_PAGE.affiliator_search_input`.

**Casing is mixed, and deliberately so:** the screen half is UPPER_SNAKE because it is the
`screen_id`; the role half is lower_snake because that is how `role_vocabulary` writes it and how
developers name the real locators it joins to. The schema's pattern enforces exactly this —
`^[A-Z0-9_]+\.[a-z0-9_]+(\.[a-z0-9_]+)?$`. Do not "normalise" either half.

Map the design role token to the config's vocabulary — never to a suffix the config does not list:

| Layer role token | `role_vocabulary` entry → emitted suffix | `role` enum |
| :--- | :--- | :--- |
| Button, CTA, Action, FAB | `_btn` | `BUTTON` |
| Field, Input, TextField, Search, Form | `_input` | `INPUT` |
| Label, Text, Title, Caption, Error, Message | `_label` | `LABEL` |
| Toggle, Switch, Checkbox, Radio | `_toggle` | `TOGGLE` |
| Tab, Segment, Chip (navigational) | `_tab` | `TAB` |
| List, Row, Card, Item, Cell, Carousel | `_list` | `LIST` |

The suffix is emitted exactly as the config writes it. `role` is the separate normalised enum field
and stays UPPER — the two are different things and do not have to match in case.

A role that maps to none of these → use the closest listed suffix, set `role` to the honest enum
value (or `OTHER`), and record a `DEGRADED` note naming the source token. Do **not** invent a
seventh suffix — downstream locator joins are keyed on this vocabulary.

A third `.state` segment (lower_snake, same rule) is only appended when the design genuinely ships
that element as a separate variant (`variantProperties.State`) *and* a flow depends on the
distinction.

This is the form every downstream stage joins on:

```
design_context   GOFOOD_CART_REVIEW.promo_input      (logical — this skill)
change_context   GOFOOD_CART_REVIEW.promo_input  ->  com.gojek.app:id/promo_input   (real locator — code diff)
nlp_steps        enter "SAVE20" into "GOFOOD_CART_REVIEW.promo_input"                (test code)
```

The `element_id` is the join key across all three. Emit it once, here, in this form; every later
stage copies it verbatim and never re-derives or re-cases it. An id that does not match the pattern
does not silently fail — it fails at code-gen, months later, as a test that cannot find its element.

---

## Field derivation — Figma node → `design_context`
| `design_context` field | Comes from |
| :--- | :--- |
| `app` | Preflight §1 — `file.name`, `file.page`, `SECTION` names, or a frame-name prefix |
| `design_source` | `exportedAt`, `scope`, `file.*`, `export.*` — copied verbatim for provenance |
| `screens[].screen_id` / `screen_name` | `SCREEN`-classified board node's `name` (standard #3) |
| `screens[].source_ref` | screen frame `id` |
| `screens[].screen_states` | frame-name state qualifiers, `componentPropertyDefinitions.*.variantOptions`, `variantProperties` across sibling frames, `OVERLAY` destinations folded in, and (v2) label chips attached by the proactive sweep / arrow binding / group-box absorption (standard #6) |
| `screens[].state_kinds` | the canonical enum those states normalise to (`ERROR`, `LOADING`, `OFFLINE`, `DARK_THEME`, `LOCALE_VARIANT`, …) — this is what makes downstream category triggers deterministic. Texts the keyword table cannot map land in the sidecar's `unclassified_states[]` for the post-run normalisation pass |
| `screens[].deep_link` | a `URL` action whose url starts with the config `deeplink_scheme`, or a `Note`/`Context` note that states one. Optional — see *Optional enrichment* |
| `screens[].entry_point` / `flow_name` | the PAGE node's `flowStartingPoints[]` — `nodeId` matches the screen frame |
| `screens[].screen_notes` | note connectors and in-frame `Note` / `Context` text (standard #5) |
| `elements[].element_id` / `role` | layer `name` + config `naming_convention` (*Element IDs*) |
| `elements[].source_ref` | node `id` |
| `elements[].type` | node `type` plus the design role token |
| `elements[].label` | `characters`, or a `componentProperties` `TEXT` `value`, or the single TEXT descendant's `characters` |
| `elements[].interactions` | one entry per connector leaving the element, carrying `connector_id`, `destination_node_id` (the literal endpoint) and `destination_screen_id` (the resolved screen, omitted when it would be the element's own screen). Note tethers produce no entry |
| `elements[].accessibility_id` / `platform_hints` | `annotations[].label` when it reads as an id (`a11y id: x`, `testID: x`, `resource-id: x`, or a bare `^[a-z0-9_]+$` token). Prose annotations go to `validations_and_edge_cases` instead |
| `elements[].validations_and_edge_cases` | prose `annotations[].label` / `labelMarkdown`, and note connectors landing on the element |
| `ui_flow[]` | `CONNECTOR` nodes (standard #1) + `reactions[]` (standard #2), deduped. On a contracted branch `condition` is **composed** — `<decision question> — <value>` — with the parts also exposed as `decision_question` / `decision_value` / `decision_node_id` |
| `project_context.blocking_issues` | every **Flag** case above |
| `design_context.report.json` (sidecar) | the tallies from the six standards, plus the classifier counts (`decision_nodes`, `caption_endpoints`, `label_frames_resolved`, `contracted_edges`, `lane_entry_inferred`, `screen_id_from_banner`, and the v2 set: `state_labels_attached`, `arrow_bound_labels`, `label_attach_conflicts`, `group_box_clusters`, `fingerprint_merged_frames`), the audit lists (`screen_renames`, `group_box_merges`, `fingerprint_merges`) and `unclassified_states[]` — **not** inside `design_context.json` |

---

## Model
**Fast tier — Haiku / Composer 2.5, and that is now a safe claim** because the graph work moved into
`scripts/extract_design_context.py`. Model tier no longer changes `screens`, `ui_flow` or
the sidecar's tallies: those come from the script byte-for-byte. What is left for the model is
naming, purpose, note placement and gap wording — language work.

This was not true before. The same skill on Haiku, executing the passes in prose, produced 6 edges
where the script produces 13, and reported zero gaps while dropping 41 of 47 connectors. If you ever
find yourself counting connectors or walking ancestors by hand, stop — the script exists so that
never happens.

The *State normalisation* pass is fast-tier-safe by construction: closed vocabulary, one
`unclassified_states` entry at a time, no traversal, "leave it" a legal answer.

Escalate to a reasoning tier only for genuinely semantic calls: an app split that the page names
don't settle, or a note whose wording needs judgement to place.

## Tool usage & permissions
Minimize tools requiring user approval:
- **Read from JSON representation only** — accept pre-exported Figma design data as JSON input; no
  Figma API/MCP calls required. This eliminates Figma tool approval overhead.
- **Avoid intermediate file operations** — process the input JSON in-memory and write the result once
  at the end. One Write per output file (see *Output files*), nothing else.

## Screen vs. state (CRITICAL GUARDRAIL)
A screen is a unique navigational destination; a state is a visual variation of the same screen. The
export carries size but no styling, so this decision is made from **names, variants, reactions and
frame size** — never from how a frame *looks*. Do **not** create a new `screen_id` for:
- Loading, scroll-position, or pagination variants of the same frame.
- Form states (empty / typing / typed / error) of the same field or button.
- Platform, locale ("as-is vs redesign", ID vs EN), or viewport-crop variants that share the same
  purpose and destination.
- A dialog / overlay / bottom-sheet whose only exit is back to the screen that opened it — fold it in
  as a `screen_states` entry on that screen and document the open/close trigger under the opening
  element's `interactions` instead.

Five mechanical signals decide it, in this order:
1. **Same base name after stripping the state qualifier** (standard #3) → one screen, the qualifiers
   are `screen_states`. `Approve Disbursement`, `Approve Disbursement — Error`,
   `Approve Disbursement — Loading` are **one** screen with three states.
2. **`variantProperties` differ but the component set is the same** → states of one screen, not
   screens. `componentPropertyDefinitions.*.variantOptions` on the set enumerates them for you.
3. **`navigation: "OVERLAY"`** → a state of the screen that opens it, **unless** ≥2 distinct screens
   have an `OVERLAY` reaction targeting the same frame — then it is a shared destination and gets its
   own `screen_id`, referenced from every caller.
4. **Dashed group box around sibling frames** (v2, standard #6) → states of one screen, whatever
   their names — unless ≥2 distinct proper names sit inside the box, which is a flagged conflict.
5. **Shared component fingerprint across default-named siblings** (v2, fallback) → states of one
   screen, always recorded as a `DEGRADED` gap. Never applied to properly named frames.

Only start a new `screen_id` when the frame is a genuinely different destination (distinct base name
*and* distinct purpose/route), including a component that is reused as its own destination from
multiple callers (e.g. a shared error dialog, native date/month picker, share sheet). Give each of those
one `screen_id` and reference it from every caller's `ui_flow` entry — never duplicate it per caller.

A frame you cannot place under any of the three signals is **not** silently promoted to a screen:
emit it as a screen, and record a `blocking_issues` entry saying the screen-vs-state call is unresolved.

The reverse doubt is flagged too, by the script: a collapse (≥2 frames) where **no** qualifier reads
as a state — `dialog / refund-confirm` + `dialog / confirm-recreate` under a generic `dialog` — may
be distinct screens sharing a lazy base name. It stays collapsed (splitting would fabricate
screen_ids nothing references), is counted in `ambiguous_collapses`, and lands in `blocking_issues`
for design to confirm. Scroll/pagination/typing qualifiers count as states and are never flagged.

## Extract — run the script, then fill the semantic fields

**The mechanical half is not yours to do.** Indexing the tree, classifying board nodes, collapsing
state frames, resolving connector endpoints, contracting decision boxes, resolving lane bands and
tallying the conservation buckets are graph operations over ~10,000 nodes. Executing them in prose
produces **schema-valid output with wrong values** — measured on a real board: 94 screen objects for
33 screens, 6 of 47 connectors resolved, 41 dropped with `blocking_issues: []`, and zero schema
errors. Nothing downstream catches that. So it runs as code:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/extract_design_context.py" \
    <figma-export.json> --app <app_id> \
    --config "${CLAUDE_PLUGIN_ROOT}/config/<app>.json" \
    -o design_context.json --report
```

This writes **two** files: `design_context.json`, and `design_context.report.json` beside it holding
the convention tallies and the conservation proof. Hand the QA both — the report is the feedback
loop back to design, and the checker needs it.

Run it **once per app in scope** (see *Output files*), with that app's config and `--app` id.

### What the script returns, already correct
`screens[]` (collapsed — by name, group box and fingerprint — with `source_refs`, `screen_states`
including swept label chips, `state_kinds`, `entry_point`, `node_class`, `classified_by`),
`elements[]` (filtered to connector triggers and interactive layers, with `element_id` built from
the config's `role_vocabulary`), `ui_flow[]` (with `navigation_kind`, `edge_source`, `confidence`,
`source_ref`, `trigger_element_id` where known), `project_context.blocking_issues` and
`design_source` — plus the sidecar `design_context.report.json` carrying the convention tallies,
the conservation proof, the merge audit lists (`screen_renames`, `group_box_merges`,
`fingerprint_merges`) and `unclassified_states[]` (input to the *State normalisation* pass).

`--report` prints a one-line summary to stderr. **Read it and repeat it in your reply** — it is how
the QA sees coverage without opening the JSON.

The script **exits non-zero** if the compliance buckets do not sum to `connectors_total`. That means
a connector was dropped without landing in a bucket. Do not work around it and do not hand-patch the
output: report the failure.

### What you fill in afterwards
The script leaves these empty because they need judgement, not traversal:

| Field | What to write |
| :--- | :--- |
| `visual_analysis_scratchpad` | 2-3 sentences on what the board contains — screen count, how flows are drawn, what is missing |
| `screens[].deep_link` | Only if a `URL` action or a note states one (see *Optional enrichment*) |
| `elements[].label` | Refine the script's raw first-text into the visible copy a tester would read |
| `screens[].state_kinds` | Normalise the sidecar's `unclassified_states[]` into the enum — see *State normalisation* below. The only structural field the model may touch, and only additively |
| `extraction_gaps[]` | One entry per real gap, with `severity` and a concrete `action` |
| `extraction_status` | `OK` only when `extraction_gaps` is empty |
| `project_context.overall_ambiguity_rating` | `HIGH` if any screen or trigger was unresolved; `MEDIUM` if flows resolved through inference; `LOW` if every edge is `EXPLICIT` |

### State normalisation — the one model pass over the sidecar
The script's keyword table maps English state words (`error`, `loading`, `empty` …). Everything it
cannot map — Indonesian copy (*"Gagal memuat konten"*), feature-specific validation labels (*"Code
incorrect / not found"*, *"Not eligible to become upliner yet"*), designer shorthand (*"Filled
State"*) — lands in the sidecar's `unclassified_states[]` as `{screen_id, state_text}`. For each
entry, in order:

1. **Map by meaning** into the `state_kinds` enum: `LOADING`, `EMPTY`, `ERROR`, `SUCCESS`,
   `OFFLINE`, `DISABLED`, `PERMISSION_DENIED`, `DARK_THEME`, `LIGHT_THEME`, `LOCALE_VARIANT`,
   `RTL`, `DEFAULT`. Any language. A validation-failure label **is** an `ERROR` state — *"Kode
   tidak ditemukan"* → `ERROR`; *"Filled State"* → `DEFAULT`. This is normalisation of a value the
   board states, and it is required — refusing it is a false open point.
2. **Apply additively.** Add the mapped kind to that screen's `state_kinds` (dedupe, keep sorted).
   **Never** remove or reword the verbatim text in `screen_states` — the specific label is what
   becomes a distinct test case downstream; two different error labels stay two states.
3. **Remove `OTHER`** from a screen's `state_kinds` only when **every** `unclassified_states` entry
   for that screen was mapped. Any entry left unmapped → `OTHER` stays.
4. **No fit → leave it.** Do not stretch the enum; the text stays in `screen_states`, `OTHER`
   stays in `state_kinds`, and no gap is raised — an exotic state is content, not a defect.
5. **Record the mappings** in one `INFO` gap on `screens[].state_kinds` listing each
   `state_text → KIND`, so the normalisation is auditable (same rule as every synonym mapping).

Closed vocabulary, one entry at a time, no traversal — safe at the fast tier. Everything else in
`screens`, `ui_flow` and the sidecar is still the script's output, copied through untouched.

**Turn the script's numbers into gaps.** A non-zero `connectors_unresolvable`,
`non_descriptive_names` or `unreachable_screens` is a gap the QA must see — the script counts them
and lists the specifics in `blocking_issues`, but only you can write the `reason` and `action`.
Reporting `extraction_status: INCOMPLETE` with an empty `extraction_gaps[]` is the failure this
section exists to prevent.

**If the script cannot run** (missing, or python3 unavailable) → do **not** attempt the traversal in
prose. Emit `extraction_status: DEGRADED` with a `DEGRADED` gap on `ENVIRONMENT` naming the failure,
and say so in your reply.

## Rules
- No locators — labels, types, states, interactions, flow only. **Exception:** *if* the designer
  happened to write an accessibility id into a Dev Mode `annotation`, transcribe it verbatim into
  `accessibility_id` / `platform_hints`. That is transcription of a design artefact, not a locator
  you derived — real per-platform locators still come from code-change-extractor. Annotations are
  optional everywhere: their absence is the normal case and is never noted or flagged.
- `label` = visible copy; `element_id` = stable functional token (`<SCREEN_ID>.<element_role>`, not
  text content). Casing is not a style choice — see *Element IDs*.
- **Classify note connectors before flow connectors** — standard #5 runs before standard #1.
- **Absence in the export means "none", not "unknown"** — the plugin prunes empty arrays and
  objects. No `reactions` key = no prototype interaction, and that is a fact you may rely on. The one
  thing absence does *not* tell you about is anything hidden, decorative, or below the depth cap.
- **Never infer from appearance.** Geometry is in the file, but it answers exactly two questions:
  *is this frame device-sized* (classification) and *which sibling comes first* (reading order).
  "It looks like a bottom sheet", "it is styled like an error" and anything about colour, contrast
  or shadow are not available to you and are not valid reasons for any decision.
- **Never invent** — every gap (missing connector, unreachable screen, placeholder text) becomes a
  `blocking_issues` entry, not a filled assumption.
- **Every fallback is recorded** — a `DEGRADED` note plus a tally in the sidecar.
- **Never hand-compute what the script reports.** Screens, elements, `ui_flow` and
  the sidecar's tallies are the script's output, copied through untouched. Adding an edge you
  reasoned out, or adjusting a count so the buckets look tidier, breaks the one property that makes
  this skill model-independent. The **single sanctioned exception** is the *State normalisation*
  pass: additive edits to `screens[].state_kinds` driven by the sidecar's `unclassified_states[]`,
  each mapping recorded in an `INFO` gap. Nothing else in the structural output is yours to edit.
- Output design_context.json concisely — only functional elements that matter for test automation.

## Guardrails
Output valid JSON only, conforming to `${CLAUDE_PLUGIN_ROOT}/schemas/design_context.schema.json`. All `screen_id`,
`trigger_element_id`/`element_id`, `from_screen_id`, and `to_screen_id` values must satisfy the schema's
regex patterns exactly — no lowercase, no stray punctuation.

**Never invent.** Every gap — missing connector, unreachable screen, placeholder text, a frame
you cannot classify as screen-vs-state — becomes a `blocking_issues` entry. Never a filled
assumption. Element IDs come from layer names per standard #3 — that is the source, not a
fallback for a missing accessibility ID.

**Never merge two apps into one file.** If the export covers several apps, write several files —
do not pick the app with the most frames and drop the rest, and never generate one app's
`element_id`s under another app's `element_id_pattern`.

## Validate — one command, not a checklist

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_design_context.py" <design_context file> \
    --schema "${CLAUDE_PLUGIN_ROOT}/schemas/design_context.schema.json" \
    --report <design_context>.report.json
```

**Always pass `--report`.** Without it, conservation, counters-complete and note accounting print
`SKIPPED` and verify nothing — the checker says so out loud rather than passing quietly, but a
SKIPPED run is not a checked run.

Run it **per output file** and **paste its output into your reply verbatim**. It prints `OK` plus a
one-line summary, or `FAILED` with one line per problem, and exits non-zero.

This replaced a nine-bullet prose checklist because the checklist did not work: a run walked past it
and reported `blocking_issues: []` while dropping 41 of 47 connectors — and passed schema validation
while doing so. Every check in the script is one the schema cannot express or a model got wrong:

| It checks | Because |
| :--- | :--- |
| schema conformance | well-formed JSON is not conformance |
| duplicate `screen_id` | draft-07 cannot express uniqueness-by-property; duplicates mean state frames were not collapsed, which drops every flow drawn from the other states |
| connector conservation | a silent drop is the failure mode that produced 6 edges where 13 exist |
| every counter present | an absent counter and a zero look identical to a reader |
| note accounting | note text vanishing without trace |
| no `BLOCKING` gap on an intent field | the bug this section exists to prevent |
| gaps vs `extraction_status` | an `INCOMPLETE` run that reports nothing |
| dropped fields absent | `purpose` / `states_represented` creeping back |
| ids resolve, no self-loops | dangling references, and intra-screen connectors emitted as navigation |
| v2 counters present, `unclassified_states` ids resolve | a hand-written compliance block, and a sidecar naming screens the context does not have |

**If it fails, fix the cause — never the output.** Editing the JSON to satisfy the checker
reintroduces exactly the silent-wrongness it exists to catch. If `jsonschema` is missing it says so;
give the user the install command and record a `DEGRADED` gap on `ENVIRONMENT`.

**Never report a file as valid without pasting the checker's output.**
