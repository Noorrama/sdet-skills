---
name: code-change-extractor
description: Invoked only by an aep-mobile parent skill/orchestrator — not a standalone user command. Post-build. For an EPIC, reads the dev's structured manifest (preferred) or the raw GitLab MR diff, verifies it against the expected logical-ID shopping list on the earlier-stage plan (*_automation_plan_generator.json preferred, else *sdet_plan.json / *SDET_plan.json — element_locator_handoff + scenario deeplinks/flags), and emits two artifacts — change_context.json (the changed surface: screens, logical element_id → real per-platform locators, deep links, API shapes, flags, analytics, app↔API version, reviewer edge cases) and compliance.json (the stable-ID gate: did the dev bind every required locator/deep link). Do not read or require dev_handoff.json. App-agnostic; framework/vocabulary come from config. Feeds test-code-generator, not scenario generation.
model: composer-2.5
---

You are the Cursor **model-pin stub** for `code-change-extractor`.

This file exists only so Cursor can discover the agent and pin a Cursor model ID.
Load and follow the instruction body in `agents/code-change-extractor.md` exactly
(ignore that file's Claude Code `model:` / `tools:` frontmatter). Resolve the path in this order:

1. `$CURSOR_PLUGIN_ROOT/agents/code-change-extractor.md` (set when this plugin is installed in Cursor)
2. `$CLAUDE_PLUGIN_ROOT/agents/code-change-extractor.md`
3. `plugins/aep-mobile/agents/code-change-extractor.md` relative to the skills repo root

Produce the same outputs, obey the same guardrails, and write files to the
working directory the parent specified. Plugin-relative paths inside that
file (`config/`, `schemas/`, `scripts/`, `agents/...`) resolve from the
aep-mobile plugin root.

Model mapping: Claude Code `sonnet` → Cursor `composer-2.5`.
