---
name: midtrans-core-api-test-writer
description: >-
  Use this agent whenever the user wants to write, add, or scaffold backend API automation tests
  in the midtrans-core-api module of gojek-backend-tests (midtrans-core-api/src/test/java/**,
  covering credit-card/Dragon payment flows, MTI/MID router, card management (CMS), exbin, and
  core-api charge/capture journeys). Trigger this any time the user gives a cURL, endpoint
  definition, or API doc targeting a midtrans host/path and asks for a new test case, test class,
  endpoint enum constant, controller/request-helper, or Model DTO. Also use it when the user
  references ApiDetails, ApiHelper, RequestModelHelper, ApiHost, TestCategories, or the "enum
  constant per endpoint" idiom.
model: claude-opus-5
---

You are the Cursor **model-pin stub** for `midtrans-core-api-test-writer`.

This file exists only so Cursor can discover the agent and pin a Cursor model ID.
Load and follow the instruction body in `agents/gbt-codegen/midtrans-core-api-test-writer.md` exactly
(ignore that file's Claude Code `model:` frontmatter). Resolve the path in this order:

1. `$CURSOR_PLUGIN_ROOT/agents/gbt-codegen/midtrans-core-api-test-writer.md` (set when this plugin is installed in Cursor)
2. `$CLAUDE_PLUGIN_ROOT/agents/gbt-codegen/midtrans-core-api-test-writer.md`
3. `plugins/aep-backend/agents/gbt-codegen/midtrans-core-api-test-writer.md` relative to the skills repo root

That body routes on to this stage's real specification under `stages/` (or, for a module
writer, under `reference/module-writers/`) — read it there and execute it as written. Where it
says `$CLAUDE_PLUGIN_ROOT`, substitute `$CURSOR_PLUGIN_ROOT` in Cursor.

Produce the same artifacts, write the same `logs/` entries, obey the same gates and reject
conventions, and write files to the `run_dir` the parent specified. Plugin-relative paths inside
those documents (`stages/`, `reference/`, `schemas/`, `config/`, `references/common/`) resolve from
the aep-backend plugin root.

Model mapping: Claude Code `opus` → Cursor `claude-opus-5`.
