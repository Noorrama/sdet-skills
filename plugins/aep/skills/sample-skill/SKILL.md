---
name: sample-skill
description: Template skill — use as a starting point when writing a new AEP skill. Not meant to trigger on its own; copy this directory and replace the content.
---

This is a placeholder. Copy this directory (`plugins/aep/skills/sample-skill/`) to
`plugins/aep/skills/<your-skill-name>/`, then:

1. Rename `name` above to match the directory.
2. Rewrite `description` to state exactly what the skill does and when Claude should
   use it — this is the only thing Claude reads to decide whether to invoke it, so
   be concrete rather than generic.
3. Replace this body with the actual instructions Claude should follow.
4. Delete this file's placeholder content once you've made your own — it shouldn't
   ship alongside real skills.

See the `add-a-skill` skill for the full contribution steps (versioning, local test, review).
