---
name: mobile-design-extractor
description: Extract the UI flow and element map from a mobile app's design (Figma + navigation + accessibility IDs) into design_context.json — screens, element IDs (logical), interactions, states, ui_flow, and a per-element/per-project ambiguity rating. Collapses loading/scroll/error/locale variants into screen-level states instead of fragmenting them into separate screens, and reports unresolved navigation or content as an ambiguity/blocking issue rather than inventing it. App-agnostic; the frontend-primary stage. Its element IDs are the logical half of the locator mapping.
---

# Mobile Design Extractor (all 5 GoTo apps)

Design is the frontend-primary stage. This skill produces the screen/element map whose logical
`element_id`s later join to real per-platform locators from the Code Diff (see code-change-extractor).

## Config
`config/<app>.json` → `naming_convention.element_id_pattern` and `role_vocabulary` govern the
`<ACTION>_<ELEMENT_TYPE>` segment of each `element_id` (see Extract §1). Set `app` on the output object
— the schema doesn't require it, but the rest of the pipeline keys off it for multi-app runs.

## Reads
Figma file/export for the affected screens — frames, component instances + variants, prototype/connector
links, sticky-note annotations, and text layers — plus the navigation/deep-link map and the
accessibility-ID / component spec.

## Model
Fast tier — Haiku / Composer 2.5. Escalate to reasoning only when a frame's screen-vs-state grouping,
or a connector's destination, is still ambiguous after applying the rules below.

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
   implied by the design.
3. **element_ambiguity** (per element) and **project_context** (per output) — `{rating: LOW/MEDIUM/HIGH,
   reason}`. This is where ambiguity belongs, not silently resolved:
   - A tappable element with no traced connector/prototype link to a destination.
   - A frame/dialog with no captured copy, or copy that is truncated, contradictory, or a literal
     placeholder (e.g. `"PLACEHOLDER"`, `"TBD"`, `"[Placeholder Copy]"`).
   - Two design iterations disagreeing on terminology/copy for what is otherwise the same screen (keep
     one `screen_id`, list both variants under `screen_states`/`screen_notes`, and flag the conflict here
     rather than picking one silently).
   - Roll the worst per-element rating up into `project_context.overall_ambiguity_rating`, and put
     project-wide gaps (e.g. a whole flow with no design coverage) into `project_context.blocking_issues`.
4. **ui_flow** — `{from_screen_id, trigger_element_id, to_screen_id, condition}` edges between screens
   (state changes within one screen are *not* ui_flow entries — see guardrail). Prefer edges backed by an
   explicit prototype/connector link; when a destination is only inferred (e.g. a menu label with no
   traced connector), say so in `condition` (e.g. `"inferred from label, no connector traced"`) instead of
   asserting it as fact. If a deep link is known for a screen, note it in that screen's `screen_notes`.
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
  becomes an `element_ambiguity`/`blocking_issues` entry instead of being filled in.

## Guardrails
Output valid JSON only, conforming to `schemas/design_context.schema.json`. All `screen_id`,
`trigger_element_id`/`element_id`, `from_screen_id`, and `to_screen_id` values must satisfy the schema's
regex patterns exactly — no lowercase, no stray punctuation.

## Validate
`jsonschema.validate(output, schemas/design_context.schema.json)`
