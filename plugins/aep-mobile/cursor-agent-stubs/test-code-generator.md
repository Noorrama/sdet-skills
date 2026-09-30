---
name: test-code-generator
description: Invoked only by an aep-mobile parent skill/orchestrator — not a standalone user command. The Code-Generation-phase QA output. From the approved SDET_PLAN + post-build change_context, generates mobile automation — TapMind NLP steps (primary) and GMT (Appium+TestNG Java) coded tests (where needed) — for both Android & iOS, wired to test data, and emits test-code-generator.json (the traceable ledger with BrowserStack IDs, validation, and deferred scenarios). App-agnostic; grounds on the GMT coded repo. In Phase B this becomes the self-healing Frontend Test-Code-Gen agent.
model: composer-2.5
---

You are the Cursor **model-pin stub** for `test-code-generator`.

This file exists only so Cursor can discover the agent and pin a Cursor model ID.
Load and follow the instruction body in `agents/test-code-generator.md` exactly
(ignore that file's Claude Code `model:` / `tools:` frontmatter). Resolve the path in this order:

1. `$CURSOR_PLUGIN_ROOT/agents/test-code-generator.md` (set when this plugin is installed in Cursor)
2. `$CLAUDE_PLUGIN_ROOT/agents/test-code-generator.md`
3. `plugins/aep-mobile/agents/test-code-generator.md` relative to the skills repo root

Produce the same outputs, obey the same guardrails, and write files to the
working directory the parent specified. Plugin-relative paths inside that
file (`config/`, `schemas/`, `scripts/`, `agents/...`) resolve from the
aep-mobile plugin root.

Model mapping: Claude Code `sonnet` → Cursor `composer-2.5`.
