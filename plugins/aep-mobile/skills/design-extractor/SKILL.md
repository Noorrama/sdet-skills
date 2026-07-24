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

## Extract (→ schemas/design_context.schema.json)

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
Output valid JSON only, conforming to `schemas/design_context.schema.json`. All `screen_id`,
`trigger_element_id`/`element_id`, `from_screen_id`, and `to_screen_id` values must satisfy the schema's
regex patterns exactly — no lowercase, no stray punctuation.

## Validate
- `jsonschema.validate(output, schemas/design_context.schema.json)` — confirms JSON structure & naming.
- **Connector completeness:** Count all visible prototype/connector lines in JSON and verify each appears
  in `ui_flow` (or flag missing ones in `blocking_issues`). Zero false positives/negatives.
- **Element filtering:** Every element in `elements` either (a) appears in `ui_flow` as trigger, or (b)
  has explicit interactions/states. No decorative/unused elements.
- **ID patterns:** All `screen_id` and `element_id` values match regex exactly — `^[A-Z0-9_]+$` and
  `^[A-Z0-9_]+\.[A-Z0-9_]+(\.[A-Z0-9_]+)?$` respectively. No lowercase, no stray punctuation.
- **Conciseness:** Output size is minimal; only functional elements included. Verify by comparing element
  count to connector count — should be roughly proportional.
