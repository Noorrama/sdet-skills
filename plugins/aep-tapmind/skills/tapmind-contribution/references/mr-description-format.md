# MR description format (test-case contributions)

The skill counts **list items** under platform sections in each merged MR description.
Use this layout so parsing is reliable (copy into new MRs or ask authors to follow it).

## Recommended template

```markdown
## Test case contributions

Contributors: @noor.daulay

### Android
- GOFOOD-1234 — Place order with voucher
- GOFOOD-1235 — Cancel active booking

### iOS
- GOFOOD-2001 — Place order with voucher
```

Rules:

1. Top-level heading must be `## Test case contributions` (exact text, case-insensitive).
2. Platform blocks use `### Android` and/or `### iOS` (case-insensitive).
3. Each bullet (`-`, `*`, or `1.`) under a platform block counts as **one** test case.
4. Optional BrowserStack / internal ids at the start of the line (`GOFOOD-1234`, `TC-42`, etc.) are labels only — still one case per bullet.
5. Put `@gitlab_username` in **Contributors:** or in a `#### @username` subheading when several people contribute in one MR.

## Per-contributor sections (optional)

When one MR mixes authors, split by handle:

```markdown
## Test case contributions

#### @noor.daulay

##### Android
- CASE-A1

##### iOS
- CASE-I1
```

Handles must match entries in `config/teams/<team>.yaml` (`gitlab_handle` without `@`).

## What is ignored

- Pipelines, checklists, and tables outside the contributions section.
- Bullets under other `##` headings (e.g. `## Agentic NLP verification`).
- Empty platform sections (zero bullets ⇒ zero count).

## Attribution when the template is missing

If there is no `## Test case contributions` block, the skill does **not** guess from the diff.
It only attributes MRs whose **author username** matches a configured `gitlab_handle`, and only if
the description contains at least one `### Android` or `### iOS` block anywhere (legacy layout).
