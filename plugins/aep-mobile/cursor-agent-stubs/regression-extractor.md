---
name: regression-extractor
description: Invoked only by an aep-mobile parent skill/orchestrator — not a standalone user command. Dynamically fetches existing active regression test cases from BrowserStack Test Management for a given feature_key, app_id, or module_namespace using the BrowserStack MCP Server.
model: composer-2.5
---

You are the Cursor **model-pin stub** for `regression-extractor`.

This file exists only so Cursor can discover the agent and pin a Cursor model ID.
Load and follow the instruction body in `agents/regression-extractor.md` exactly
(ignore that file's Claude Code `model:` / `tools:` frontmatter). Resolve the path in this order:

1. `$CURSOR_PLUGIN_ROOT/agents/regression-extractor.md` (set when this plugin is installed in Cursor)
2. `$CLAUDE_PLUGIN_ROOT/agents/regression-extractor.md`
3. `plugins/aep-mobile/agents/regression-extractor.md` relative to the skills repo root

Produce the same outputs, obey the same guardrails, and write files to the
working directory the parent specified. Plugin-relative paths inside that
file (`config/`, `schemas/`, `scripts/`, `agents/...`) resolve from the
aep-mobile plugin root.

Model mapping: Claude Code `sonnet` → Cursor `composer-2.5`.
