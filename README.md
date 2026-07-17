# aep/skills

Claude Code skills marketplace for the AEP team.

## Install

```
claude plugin marketplace add https://source.golabs.io/aep/skills.git
claude plugin install aep@aep
```

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
