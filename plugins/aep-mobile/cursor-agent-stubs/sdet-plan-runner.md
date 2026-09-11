---
name: sdet-plan-runner
description: Cross-stage gap analysis and SDET plan computation — produces SDET_plan.json, analysis.md, test_cases.csv (GENERATE only). SYNC is agents/sdet-plan-sync.md. Invoked by mobile-sdet-plan-generator; not a user-facing command.
model: claude-opus-5
---

You are the Cursor **model-pin stub** for `sdet-plan-runner` (GENERATE).

This file exists only so Cursor can discover the agent and pin a Cursor model ID.
Load and follow the instruction body in `agents/sdet-plan-runner.md` exactly
(ignore that file's Claude Code `model:` / `tools:` frontmatter). Resolve the path in this order:

1. `$CURSOR_PLUGIN_ROOT/agents/sdet-plan-runner.md` (set when this plugin is installed in Cursor)
2. `$CLAUDE_PLUGIN_ROOT/agents/sdet-plan-runner.md`
3. `plugins/aep-mobile/agents/sdet-plan-runner.md` relative to the skills repo root

Produce the same outputs, obey the same guardrails, and write files to the
working directory the parent specified. Plugin-relative paths inside that
file (`config/`, `schemas/`, `scripts/`, `agents/...`) resolve from the
aep-mobile plugin root.

Model mapping: Claude Code `opus` → Cursor `claude-opus-5`.
For SYNC, the parent loads `agents/sdet-plan-sync.md` (stub: `sdet-plan-sync.md`).
