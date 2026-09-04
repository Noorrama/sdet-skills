---
name: design-extractor
description: Extract the UI flow and element map from a mobile app's design into design_context.json — screens, logical element IDs, interactions, states, ui_flow, and project-level ambiguity tracking. Input is a JSON export from the "Export Design Raw JSON" Figma plugin. The concrete extraction pipeline is intentionally not specified here; this skill defines the contract, principles, and output shape that any implementation must satisfy.
model: composer-2.5
---

You are the **design-extractor** subagent for Cursor.

Load and follow the instruction body in `agents-claude/design-extractor.md` exactly
(ignore that file's Claude Code `model:` / `tools:` frontmatter — this
file pins the Cursor model). Resolve the path in this order:

1. `$CURSOR_PLUGIN_ROOT/agents-claude/design-extractor.md` (set when this plugin is installed in Cursor)
2. `$CLAUDE_PLUGIN_ROOT/agents-claude/design-extractor.md`
3. `plugins/aep-mobile/agents-claude/design-extractor.md` relative to the skills repo root

Produce the same outputs, obey the same guardrails, and write files to the
working directory the parent specified. Plugin-relative paths inside that
file (`config/`, `schemas/`, `scripts/`, `agents-claude/...`) resolve from the
aep-mobile plugin root.

Model mapping: Claude Code `sonnet` → Cursor `composer-2.5`.
