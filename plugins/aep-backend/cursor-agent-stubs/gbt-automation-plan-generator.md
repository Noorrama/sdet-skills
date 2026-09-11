---
name: gbt-automation-plan-generator
description: >-
  Upstream stage of the GBT codegen pipeline. Turns an approved sdet_plan.json into
  automation_plan.json — one automation_scenario per test scenario with test class, package,
  method name, fixture IDs, required state, and curl references. Spawned by code-gen-orchestrator
  only, and only when the epic has no plan yet.
model: claude-opus-5
---

You are the Cursor **model-pin stub** for `gbt-automation-plan-generator`.

This file exists only so Cursor can discover the agent and pin a Cursor model ID.
Load and follow the instruction body in `agents/gbt-codegen/gbt-automation-plan-generator.md` exactly
(ignore that file's Claude Code `model:` frontmatter). Resolve the path in this order:

1. `$CURSOR_PLUGIN_ROOT/agents/gbt-codegen/gbt-automation-plan-generator.md` (set when this plugin is installed in Cursor)
2. `$CLAUDE_PLUGIN_ROOT/agents/gbt-codegen/gbt-automation-plan-generator.md`
3. `plugins/aep-backend/agents/gbt-codegen/gbt-automation-plan-generator.md` relative to the skills repo root

That body routes on to this stage's real specification under `stages/` (or, for a module
writer, under `reference/module-writers/`) — read it there and execute it as written. Where it
says `$CLAUDE_PLUGIN_ROOT`, substitute `$CURSOR_PLUGIN_ROOT` in Cursor.

Produce the same artifacts, write the same `logs/` entries, obey the same gates and reject
conventions, and write files to the `run_dir` the parent specified. Plugin-relative paths inside
those documents (`stages/`, `reference/`, `schemas/`, `config/`, `skills/common/`) resolve from
the aep-backend plugin root.

Model mapping: Claude Code `opus` → Cursor `claude-opus-5`.
