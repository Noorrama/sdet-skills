---
name: mobile-design-extractor
description: Extract the UI flow and element map from a mobile app's design (Figma + navigation + accessibility IDs) into design_context.json — screens, element IDs (logical), interaction types, states, flows and deep links. App-agnostic; the frontend-primary stage. Its element IDs are the logical half of the locator mapping.
---

# Mobile Design Extractor (all 5 GoTo apps)

Design is the frontend-primary stage. This skill produces the screen/element map whose logical
`element_id`s later join to real per-platform locators from the Code Diff (see code-change-extractor).

## Config
`config/<app>.json` → `naming_convention.element_id_pattern` (`<screen_id>.<element_role>`) and
`role_vocabulary`. Set `design_context.app = app_id`.

## Reads
Figma file/export for the affected screens; navigation/deep-link map; accessibility-ID / component spec.

## Model
Fast tier — Haiku / Composer 2.5.

## Extract (→ design_context.schema.json)
1. **screens** — `screen_id` (UPPER_SNAKE from the Figma frame, app-prefixed if shared); per-screen
   **elements** each with `element_id`, `element_role` (functional, not the visible label),
   `label`, `type`, and states; plus screen-level states (empty/loading/error/success/offline).
2. **flows** — navigation edges/paths between screens (with guards). These feed the NLP navigation walk.
3. **deep_links**.
4. **missing_ids** — interactive elements lacking a stable id → testability feedback (not automatable until fixed).

## Rules
- No locators here — labels/types/states/flows only. Physical locators come from code (code-change-extractor).
- `element_role` is functional (`promo_input`), never the copy/locale-dependent label.
- Every P0 screen must have error/empty/loading states designed, and every P0 flow must appear in `flows`.

## Guardrails
Output valid JSON only, conforming to `schemas/design_context.schema.json`.
