# Known-bugs KB

Past, confirmed bugs in the shape below. When a lint or model finding matches one of these on
the same screen/flow, carry its id forward as the finding's `kbRef` — turns "possible anomaly"
into "this is BUG-1183 again."

**This file is a stub — empty on purpose.** Populate it with 10-15 real past bugs (symptom /
screen / how you'd detect it from a lint or model finding) before relying on `kbRef` matches in
a report; until then every finding will show up unmatched, which is correct, just less useful.

## Entry format

```markdown
## BUG-<id>: <one-line symptom>
- **Screen/flow:** <where it shows up>
- **Detect:** <what a lint check or model finding would look like for this>
- **Notes:** <anything a QA reading the match needs>
```

## Entries

_(none yet)_
