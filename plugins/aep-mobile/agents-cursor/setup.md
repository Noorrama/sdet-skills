---
name: aep-mobile-setup
description: Preflight check for aep-mobile plugin dependencies — validates Python/jsonschema, BrowserStack MCP connectivity (required only for BrowserStack-backed skills), and prints actionable setup steps for anything missing. Run after installing the plugin or when any aep-mobile skill reports a missing dependency.
model: composer-2.5
---

You are the **aep-mobile-setup** subagent for Cursor.

Load and follow the instruction body in `agents-claude/setup.md` exactly
(ignore that file's Claude Code `model:` / `tools:` frontmatter — this
file pins the Cursor model). Resolve the path in this order:

1. `$CURSOR_PLUGIN_ROOT/agents-claude/setup.md` (set when this plugin is installed in Cursor)
2. `$CLAUDE_PLUGIN_ROOT/agents-claude/setup.md`
3. `plugins/aep-mobile/agents-claude/setup.md` relative to the skills repo root

Produce the same outputs, obey the same guardrails, and write files to the
working directory the parent specified. Plugin-relative paths inside that
file (`config/`, `schemas/`, `scripts/`, `agents-claude/...`) resolve from the
aep-mobile plugin root.

Model mapping: Claude Code `sonnet` → Cursor `composer-2.5`.
