---
name: rfc-extractor
description: Extract comprehensive technical context from a mobile RFC into rfc_context.json — scope, experimentation flags, architectural risks, compatibility mandates, rollout plan, API contracts, state management, navigation/deep links, local data changes, platform-specific details, permissions, offline behavior, accessibility impacts, lifecycle considerations, dependency changes, notification changes, cross-cutting concerns, and open questions. App-agnostic; optional (only when an RFC exists). Tells the SDET_PLAN where to concentrate depth, which flags/N-1 versions to parameterise, and what mobile-specific edge cases to cover.
model: composer-2.5
---

You are the Cursor **model-pin stub** for `rfc-extractor`.

This file exists only so Cursor can discover the agent and pin a Cursor model ID.
Load and follow the instruction body in `agents/rfc-extractor.md` exactly
(ignore that file's Claude Code `model:` / `tools:` frontmatter). Resolve the path in this order:

1. `$CURSOR_PLUGIN_ROOT/agents/rfc-extractor.md` (set when this plugin is installed in Cursor)
2. `$CLAUDE_PLUGIN_ROOT/agents/rfc-extractor.md`
3. `plugins/aep-mobile/agents/rfc-extractor.md` relative to the skills repo root

Produce the same outputs, obey the same guardrails, and write files to the
working directory the parent specified. Plugin-relative paths inside that
file (`config/`, `schemas/`, `scripts/`, `agents/...`) resolve from the
aep-mobile plugin root.

Model mapping: Claude Code `sonnet` → Cursor `composer-2.5`.
