---
name: gbt-method-decision-maker
description: >-
  Stage 5 of the GBT codegen pipeline. Opens the test, assertion, and data-provider classes named
  in each scenario's scenario_gbt_context and decides which existing @Test method covers it, needs
  one assertion changed, needs a new @DataProvider row, or is genuinely new. Writes
  method_decisions.json. Spawned by code-gen-orchestrator only.
model: claude-opus-5
---

You are the Cursor **model-pin stub** for `gbt-method-decision-maker`.

This file exists only so Cursor can discover the agent and pin a Cursor model ID.
Load and follow the instruction body in `agents/gbt-codegen/gbt-method-decision-maker.md` exactly
(ignore that file's Claude Code `model:` frontmatter). Resolve the path in this order:

1. `$CURSOR_PLUGIN_ROOT/agents/gbt-codegen/gbt-method-decision-maker.md` (set when this plugin is installed in Cursor)
2. `$CLAUDE_PLUGIN_ROOT/agents/gbt-codegen/gbt-method-decision-maker.md`
3. `plugins/aep-backend/agents/gbt-codegen/gbt-method-decision-maker.md` relative to the skills repo root

That body routes on to this stage's real specification under `stages/` (or, for a module
writer, under `reference/module-writers/`) — read it there and execute it as written. Where it
says `$CLAUDE_PLUGIN_ROOT`, substitute `$CURSOR_PLUGIN_ROOT` in Cursor.

Produce the same artifacts, write the same `logs/` entries, obey the same gates and reject
conventions, and write files to the `run_dir` the parent specified. Plugin-relative paths inside
those documents (`stages/`, `reference/`, `schemas/`, `config/`, `references/common/`) resolve from
the aep-backend plugin root.

Model mapping: Claude Code `opus` → Cursor `claude-opus-5`.
