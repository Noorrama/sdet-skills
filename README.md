# aep/skills

Claude Code skills marketplace for the AEP team.

## Install

Our Claude Code deployment is enterprise-managed, so `claude plugin marketplace add`
is locked down for end users — that's the same reason ponytail had to be installed
by going through the CLI directly rather than self-service. Getting this marketplace
in front of every engineer needs an admin, not a per-user step:

**One-time, by whoever owns `managed-settings.json`** (see [admin-setup docs](https://code.claude.com/docs/en/admin-setup.md)):
```json
{
  "extraKnownMarketplaces": {
    "aep": {
      "source": { "source": "url", "url": "https://source.golabs.io/aep/skills.git" }
    }
  }
}
```
(`strictKnownMarketplaces` needs an entry too if that's what's blocking self-service adds.)

**Every engineer, after that's in place:**
```
claude plugin install aep@aep
```
No `marketplace add` needed — the marketplace is already pre-registered org-wide.

## Structure

```
.claude-plugin/marketplace.json   # marketplace manifest, lists plugins below
plugins/
  aep/                            # starter plugin — one skill per team workflow
    .claude-plugin/plugin.json
    skills/
      add-a-skill/SKILL.md        # how to contribute a new skill here
```

Add a new plugin directory under `plugins/` (with its own `.claude-plugin/plugin.json`)
when a set of skills is specific enough to a service or sub-team that it shouldn't
ship to everyone who installs `aep`.

## Contributing

See the `add-a-skill` skill (`plugins/aep/skills/add-a-skill/SKILL.md`) for how
to add or propose a new skill.

Skills that turn out to be broadly useful beyond AEP should graduate to the
org-wide marketplace rather than living here indefinitely.
