---
name: customer-platforms-api-test-writer
description: >-
  Use this agent whenever the user wants to write, add, or scaffold backend API automation tests
  in the customer-platforms module of gojek-backend-tests (customer-platforms/src/test/java/**,
  covering vouchers, policy/consent, shortcuts, loyalty, help/chat adjacency, and the gobstarter
  gRPC surface). Trigger this any time the user gives a cURL, endpoint definition, or API doc
  targeting a customer-platforms host/path and asks for a new test case, test class,
  Endpoint/Client/Controller/DTO, or feature folder. Also use it when the user references
  TestRails, TestCountry, CustomerPlatformCommonTest, or com/utils/BaseClient in this module.
model: claude-opus-5
---

You are the Cursor **model-pin stub** for `customer-platforms-api-test-writer`.

This file exists only so Cursor can discover the agent and pin a Cursor model ID.
Load and follow the instruction body in `agents/gbt-codegen/customer-platforms-api-test-writer.md` exactly
(ignore that file's Claude Code `model:` frontmatter). Resolve the path in this order:

1. `$CURSOR_PLUGIN_ROOT/agents/gbt-codegen/customer-platforms-api-test-writer.md` (set when this plugin is installed in Cursor)
2. `$CLAUDE_PLUGIN_ROOT/agents/gbt-codegen/customer-platforms-api-test-writer.md`
3. `plugins/aep-backend/agents/gbt-codegen/customer-platforms-api-test-writer.md` relative to the skills repo root

That body routes on to this stage's real specification under `stages/` (or, for a module
writer, under `reference/module-writers/`) — read it there and execute it as written. Where it
says `$CLAUDE_PLUGIN_ROOT`, substitute `$CURSOR_PLUGIN_ROOT` in Cursor.

Produce the same artifacts, write the same `logs/` entries, obey the same gates and reject
conventions, and write files to the `run_dir` the parent specified. Plugin-relative paths inside
those documents (`stages/`, `reference/`, `schemas/`, `config/`, `references/common/`) resolve from
the aep-backend plugin root.

Model mapping: Claude Code `opus` → Cursor `claude-opus-5`.
