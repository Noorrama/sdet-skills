---
name: gopay-api-test-writer
description: >-
  Use this agent whenever the user wants to write, add, or scaffold API automation test cases in
  the gopay backend-tests repo, specifically under gopay/src/test/java/userJourneyTests/userspend/
  (or a similar userJourneyTests subtree). Trigger this any time the user gives a scenario
  description plus a target package/folder and asks for a new test case, a new test class, or a
  new feature folder for an API, even if they do not say skill or name the pattern explicitly.
  Also use it when the user references MiniAppClient, MiniAppHelper, ServiceEndpoint, RequestBody
  or ResponseBody POJOs, or asks to follow the miniapp/parking test pattern. This skill knows the
  exact layered convention (Endpoint to RequestBody/Response POJOs to Client to Helper to TestNG
  test class) used across this repo and should be consulted before writing any new Java test file
  here.
model: claude-opus-5
---

You are the Cursor **model-pin stub** for `gopay-api-test-writer`.

This file exists only so Cursor can discover the agent and pin a Cursor model ID.
Load and follow the instruction body in `agents/gbt-codegen/gopay-api-test-writer.md` exactly
(ignore that file's Claude Code `model:` frontmatter). Resolve the path in this order:

1. `$CURSOR_PLUGIN_ROOT/agents/gbt-codegen/gopay-api-test-writer.md` (set when this plugin is installed in Cursor)
2. `$CLAUDE_PLUGIN_ROOT/agents/gbt-codegen/gopay-api-test-writer.md`
3. `plugins/aep-backend/agents/gbt-codegen/gopay-api-test-writer.md` relative to the skills repo root

That body routes on to this stage's real specification under `stages/` (or, for a module
writer, under `reference/module-writers/`) — read it there and execute it as written. Where it
says `$CLAUDE_PLUGIN_ROOT`, substitute `$CURSOR_PLUGIN_ROOT` in Cursor.

Produce the same artifacts, write the same `logs/` entries, obey the same gates and reject
conventions, and write files to the `run_dir` the parent specified. Plugin-relative paths inside
those documents (`stages/`, `reference/`, `schemas/`, `config/`, `skills/common/`) resolve from
the aep-backend plugin root.

Model mapping: Claude Code `opus` → Cursor `claude-opus-5`.
