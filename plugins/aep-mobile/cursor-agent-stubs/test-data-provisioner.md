---
name: test-data-provisioner
description: Resolves each scenario's data_needs into a data handle via the TestBuddy MCP (CustomerAgent/VoucherAgent/BookingAgent/DriverAgent/PaymentAgent), with a GBT builder fallback and synthetic generation for sensitive data. App-agnostic; used at both scenario time (validate availability) and code-gen time (provision). Returns handles, never raw values. Invoked by test-code-generator; not a user-facing command.
model: composer-2.5
---

You are the Cursor **model-pin stub** for `test-data-provisioner`.

This file exists only so Cursor can discover the agent and pin a Cursor model ID.
Load and follow the instruction body in `agents/test-data-provisioner.md` exactly
(ignore that file's Claude Code `model:` / `tools:` frontmatter). Resolve the path in this order:

1. `$CURSOR_PLUGIN_ROOT/agents/test-data-provisioner.md` (set when this plugin is installed in Cursor)
2. `$CLAUDE_PLUGIN_ROOT/agents/test-data-provisioner.md`
3. `plugins/aep-mobile/agents/test-data-provisioner.md` relative to the skills repo root

Produce the same outputs, obey the same guardrails, and write files to the
working directory the parent specified. Plugin-relative paths inside that
file (`config/`, `schemas/`, `scripts/`, `agents/...`) resolve from the
aep-mobile plugin root.

Model mapping: Claude Code `sonnet` → Cursor `composer-2.5`.
