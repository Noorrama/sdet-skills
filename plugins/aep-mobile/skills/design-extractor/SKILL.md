---
name: mobile-design-extractor
description: Extract the UI flow and element map from a mobile app's design (Figma + navigation + accessibility IDs) into design_context.json — screens, element IDs (logical), interactions, states, ui_flow, and project-level ambiguity tracking. Collapses loading/scroll/error/locale variants into screen-level states instead of fragmenting them into separate screens, and reports unresolved navigation or content in blocking_issues rather than inventing it. App-agnostic; the frontend-primary stage. Its element IDs are the logical half of the locator mapping.
---

# Mobile Design Extractor (all 5 GoTo apps)

Design is the frontend-primary stage. This skill produces the screen/element map whose logical
`element_id`s later join to real per-platform locators from the Code Diff (see code-change-extractor).

## Config
`config/<app>.json` → `naming_convention.element_id_pattern` and `role_vocabulary` govern the
`<ACTION>_<ELEMENT_TYPE>` segment of each `element_id` (see Extract §1). Set `app` on the output object
— the schema doesn't require it, but the rest of the pipeline keys off it for multi-app runs.

## Reads
JSON representation of the Figma design (exported structure containing frames, component instances +
variants, prototype/connector links, sticky-note annotations, text layers, navigation/deep-link map,
and accessibility-ID / component spec). Input is read-only; no Figma API calls are made.

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

## Extract (→ schemas/design_context.schema.json)
1. **screens** — `screen_id` (`^[A-Z0-9_]+$`, UPPER_SNAKE derived from the Figma frame title with any
   state/variant qualifier stripped first; app-prefixed if shared), `screen_name`, `purpose`,
   `screen_states` (empty/loading/error/success/offline — see guardrail above), `screen_notes`.
2. **elements** (per screen) — `element_id` matching `^[A-Z0-9_]+\.[A-Z0-9_]+(\.[A-Z0-9_]+)?$`, i.e.
   `<SCREEN_ID>.<ACTION>_<ELEMENT_TYPE>.<STATE>` — the trailing `.<STATE>` segment is optional; omit it
   when the element has several states, and list them all in `states_represented` instead of minting one
   ID per state. `type` and `label` are freeform (label = visible copy; type = e.g. `TextField`,
   `Button`). `interactions` is `{trigger, action}` pairs, including where a tap navigates to another
   screen or opens a dialog. `validations_and_edge_cases` captures business rules stated or clearly
   implied by the design. **Omit decorative/spacer elements:** Do not include elements with no `label`,
   no `interactions`, no `states_represented`, and no semantic purpose (pure visual separators, spacers,
   decorative backgrounds). Include all labeled, interactive, or state-bearing elements.
3. **project_context** (per output) — `{overall_ambiguity_rating: LOW/MEDIUM/HIGH, blocking_issues: []}`.
   This is where project-level ambiguity and gaps belong, not resolved silently:
   - Tappable elements with no traced connector/prototype link to a destination.
   - Frames/dialogs with no captured copy, or copy that is truncated, contradictory, or a literal
     placeholder (e.g. `"PLACEHOLDER"`, `"TBD"`, `"[Placeholder Copy]"`).
   - Design iterations disagreeing on terminology/copy for what is otherwise the same screen (keep
     one `screen_id`, list both variants under `screen_states`/`screen_notes`, and flag the conflict in
     `blocking_issues` rather than silently picking one).
   - Missing or incomplete connector traces, unreachable screens, design gaps in critical flows.
   - Set `overall_ambiguity_rating` to the worst case across the design, and put all project-wide gaps
     into `blocking_issues` array with a brief description of each.
4. **ui_flow** — `{from_screen_id, trigger_element_id, to_screen_id, condition}` edges between screens
   (state changes within one screen are *not* ui_flow entries — see guardrail). **CRITICAL: Capture ALL
   prototype/connector lines visible in the Figma file** — traverse every frame, component, and nested
   element to extract all `interactions` with a `NAVIGATE` action or `destinationId`. Include both:
   - **Element-level interactions** (buttons, icons, tappable regions with ON_CLICK, ON_HOVER, etc.)
   - **Frame-level interactions** (auto-transitions with AFTER_TIMEOUT, auto-play animations)
   
   Prefer edges backed by an explicit prototype/connector link in the condition field. When a destination
   is only inferred (e.g. a menu label with no traced connector), say so in `condition` (e.g.
   `"inferred from label, no connector traced"`) instead of asserting it as fact. If a deep link is known
   for a screen, note it in that screen's `screen_notes`. Deduplicate flows that appear in multiple frame
   variants (same from/to/trigger).
5. **visual_analysis_scratchpad** — 2-3 sentences up front listing every distinct navigational screen
   found, before compiling the structured fields below it.

## Rules
- No locators here — labels/types/states/interactions/flow only. Physical locators come from code
  (code-change-extractor).
- `label` is the visible, locale-dependent copy; don't fold it into `element_id` — the ID stays a stable
  functional token (`ENTER_PROMO_CODE_FIELD`, not the placeholder text).
- Every P0 screen must have error/empty/loading states in `screen_states`, and every P0 navigation must
  appear in `ui_flow`.
- Never invent a destination, a piece of copy, or a business rule the export doesn't state — every gap
  becomes a `blocking_issues` entry instead of being filled in.
- **Extract all connector lines:** Traverse the full node tree to find every interaction with a destination.
  This includes element-level taps/clicks and frame-level auto-transitions. Deduplicates flows across
  frame variants (multiple Homescreen variants shouldn't produce multiple identical HOMESCREEN→SCREEN_X flows).
- **Omit elements with no informational value:** Exclude any element that meets ALL of these criteria:
  has no `interactions` (no taps, clicks, or other triggers), no `states_represented` (static visual only),
  no `label` or copy (decorative spacers, dividers, or purely visual separators), and no references from
  other elements' `validations_and_edge_cases`. This minimizes output noise while keeping all functional
  and labeled elements.

## Guardrails
Output valid JSON only, conforming to `schemas/design_context.schema.json`. All `screen_id`,
`trigger_element_id`/`element_id`, `from_screen_id`, and `to_screen_id` values must satisfy the schema's
regex patterns exactly — no lowercase, no stray punctuation.

## Validate
- `jsonschema.validate(output, schemas/design_context.schema.json)` — confirms JSON structure & naming
- **ui_flow completeness:** Count all visible prototype/connector lines in the Figma file and verify
  `ui_flow` entries match (or flag missing ones in `blocking_issues` with "connector not traced" rationale).
  Use Figma's inspector or connector layer to confirm all interactions are extracted.
- All `element_id` and `screen_id` values must satisfy regex patterns exactly — no lowercase or special chars.
