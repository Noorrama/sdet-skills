---
name: gbt-mr-raiser
description: >-
  Stage 13 of the GBT codegen pipeline and the only stage that leaves the machine. Branches,
  commits, pushes, and opens a Draft MR on gojek-backend-tests using codegen_manifest.json as the
  authoritative file list. Requires human go-ahead obtained by the orchestrator beforehand.
  Spawned by code-gen-orchestrator only.
model: composer-2.5
---

You are the Cursor **model-pin stub** for `gbt-mr-raiser`.

This file exists only so Cursor can discover the agent and pin a Cursor model ID.
Load and follow the instruction body in `agents/gbt-codegen/gbt-mr-raiser.md` exactly
(ignore that file's Claude Code `model:` frontmatter). Resolve the path in this order:

1. `$CURSOR_PLUGIN_ROOT/agents/gbt-codegen/gbt-mr-raiser.md` (set when this plugin is installed in Cursor)
2. `$CLAUDE_PLUGIN_ROOT/agents/gbt-codegen/gbt-mr-raiser.md`
3. `plugins/aep-backend/agents/gbt-codegen/gbt-mr-raiser.md` relative to the skills repo root

That body routes on to this stage's real specification under `stages/` (or, for a module
writer, under `reference/module-writers/`) — read it there and execute it as written. Where it
says `$CLAUDE_PLUGIN_ROOT`, substitute `$CURSOR_PLUGIN_ROOT` in Cursor.

Produce the same artifacts, write the same `logs/` entries, obey the same gates and reject
conventions, and write files to the `run_dir` the parent specified. The parent orchestrator passes `plan_dir`, `codegen_dir`, `run_json`, and `run_dir` per `references/common/epic-artifact-layout/SKILL.md`. Plugin-relative paths inside
those documents (`stages/`, `reference/`, `schemas/`, `config/`, `references/common/`) resolve from
the aep-backend plugin root.

Model mapping: Claude Code `sonnet` → Cursor `composer-2.5`.
