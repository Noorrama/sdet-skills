---
name: sdet-plan-sync
description: Merges CSV edits into the SDET plan, uploads new cases to BrowserStack, and emits automation_plan_generator.json (SYNC). Invoked by mobile-sdet-plan-generator; not a user-facing command.
model: claude-opus-5
---

You are the Cursor **model-pin stub** for `sdet-plan-sync`.

This file exists only so Cursor can discover the agent and pin a Cursor model ID.
Load and follow the instruction body in `agents/sdet-plan-sync.md` exactly
(ignore that file's Claude Code `model:` / `tools:` frontmatter). Resolve the path in this order:

1. `$CURSOR_PLUGIN_ROOT/agents/sdet-plan-sync.md`
2. `$CLAUDE_PLUGIN_ROOT/agents/sdet-plan-sync.md`
3. `plugins/aep-mobile/agents/sdet-plan-sync.md` relative to the skills repo root

Produce the same outputs, obey the same guardrails, and write files to the
working directory the parent specified. Plugin-relative paths resolve from the
aep-mobile plugin root.

Model mapping: Claude Code `opus` → Cursor `claude-opus-5`.
