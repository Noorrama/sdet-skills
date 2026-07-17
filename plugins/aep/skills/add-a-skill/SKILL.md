---
name: add-a-skill
description: Use when an AEP engineer wants to add, propose, or contribute a new skill to the aep/skills marketplace repo.
---

Add a new skill to this repo.

1. Pick a plugin under `plugins/`. One skill doesn't need a new plugin — add it to
   `plugins/aep/skills/<skill-name>/SKILL.md` unless it's a distinct enough
   surface (e.g. a specific service's tooling) to warrant its own plugin directory
   and its own entry in `.claude-plugin/marketplace.json`.
2. Write `SKILL.md` with frontmatter:
   ```yaml
   ---
   name: skill-name
   description: What it does and when to use it — this is what triggers auto-invocation, be specific.
   ---
   ```
3. Bump the plugin's `version` in its `.claude-plugin/plugin.json` — users only get
   updates when that string changes.
4. Test locally before opening a merge request. Marketplace add is locked down by
   enterprise policy for regular use, but should still work against a local path
   for testing (check with whoever manages `managed-settings.json` if it doesn't):
   ```
   claude plugin marketplace add ./path/to/this/repo
   claude plugin install aep@aep
   ```
5. Open an MR. Someone who owns the affected plugin directory should review it.
