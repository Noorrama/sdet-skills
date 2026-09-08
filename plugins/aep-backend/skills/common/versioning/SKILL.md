---
name: artifact-versioning
description: >
  Shared artifact versioning convention for all Phase A–B skills. Artifacts are written to
  a flat output directory with doc-version-derived filenames (prd_context_v2.json). A
  version-less copy (prd_context.json) always points to the latest version so downstream
  skills need no changes. Referenced by prd-extractor, rfc-extractor, tasks-extractor,
  regression-extractor, and sdet-plan-generator — read this before writing any output file.
---

# Artifact Versioning (shared — all Phase A–B skills)

All Phase A–B skills write artifacts to a **flat output directory** chosen by the user or
orchestrator. No dated run subfolders. Each re-extraction or re-generation produces a new
versioned file alongside prior versions — nothing is ever overwritten.

---

## Naming convention

```
{artifact}_{version}.json          ← versioned copy  (permanent, never overwritten)
{artifact}.json                    ← current pointer (always = latest versioned copy)
```

Examples:
```
prd_context_v2.json        ← PRD doc says "Version 2"
prd_context.json           ← copy of prd_context_v2.json
rfc_context_v1.3.json      ← RFC doc says "v1.3"
rfc_context.json           ← copy of rfc_context_v1.3.json
tasks_context_v1.json      ← no version in doc, first extract
sdet_plan_v1.json          ← first plan generation
sdet_plan_v2.json          ← after Review-mode revision
sdet_plan.json             ← copy of sdet_plan_v2.json
```

---

## Version resolution algorithm

Run these steps in order and stop at the first match:

### Step 1 — Extract version from upstream document

Scan the source document for a version string. Common patterns (case-insensitive):

| Pattern | Example text | Extracted version |
|---|---|---|
| `Version X` / `Version X.Y` | "Version 2", "Version 1.3" | `v2`, `v1.3` |
| `v X` / `vX.Y` | "v2", "v1.0", "v 3.1" | `v2`, `v1.0`, `v3.1` |
| `Rev X` / `Revision X` | "Rev 3", "Revision 2" | `v3`, `v2` |
| `Doc version: X` | "Doc version: 2.0" | `v2.0` |
| Confluence page version | API returns version number N | `vN` |
| DOCX revision property | `Revision: 4` in metadata | `v4` |

Normalise to lowercase `v{N}` or `v{N}.{M}` — strip whitespace, leading zeros in minor
only if zero (`v1.0` stays `v1.0`; `v01` becomes `v1`).

### Step 2 — Check for version conflict in the output directory

If a file named `{artifact}_{resolved_version}.json` already exists in the output directory:
- **Content-identical** (same SHA-256): skip write, log "already at {version}, no change".
- **Content differs**: the doc version string did not change but the content did. Append a
  run counter: `_v2.1` → `_v2.1r2`, `_v2.1r3`, … Log the conflict as a warning.

### Step 3 — Numbered fallback (no version in doc)

When Step 1 finds no version string:
1. Scan the output directory for files matching `{artifact}_v*.json`.
2. Extract the numeric suffix from each filename (ignore `r` run counters).
3. Take the maximum numeric value found; increment by 1.
4. If no matching files exist, start at `v1`.

Examples:
```
No existing files          → v1
prd_context_v1.json exists → v2
prd_context_v2.json exists → v3
```

---

## Write sequence (every skill, every output)

1. Resolve version using the algorithm above.
2. Write `{artifact}_{version}.json` to the output directory. **Never overwrite** an existing
   versioned file with different content — use the conflict rule (Step 2) instead.
3. Write `{artifact}.json` to the same directory as an exact copy of the versioned file just
   written. This is always overwritten — it is the "current" pointer, not a history record.
4. Log the version in the skill's run output:
   ```
   Written: prd_context_v2.json  (current pointer: prd_context.json)
   ```

---

## How downstream skills find the current artifact

Downstream skills (e.g. `sdet-plan-generator` reads `prd_context.json`) always read the
**version-less current pointer**. They do not need to know the version number. The versioned
files are for human inspection, diff, and rollback — not for skill-to-skill handoff.

---

## `artifact_version` field in every output JSON

Every Phase A–B output JSON must carry a root-level `artifact_version` field:

```json
{
  "artifact_version": "v2",
  "generatedAt": "2026-09-08T10:00:00Z",
  ...
}
```

The value must match the version suffix in the filename. Downstream skills may log this
field for traceability but must not gate on it — they gate on content, not version strings.

---

## Version lineage in `provenance`

When a skill already stamps a `provenance` block (`prd-extractor`, `rfc-extractor`), add
two fields to it:

```json
"provenance": {
  ...existing fields...,
  "artifact_version": "v2",
  "supersedes": "prd_context_v1.json"
}
```

For skills without a full provenance block (`tasks-extractor`, `regression-extractor`,
`sdet-plan-generator`), add a lightweight `version_lineage` block instead:

```json
"version_lineage": {
  "artifact_version": "v1",
  "supersedes": null,
  "generated_at": "2026-09-08T10:00:00Z",
  "source_version": "v2"
}
```

`source_version` is the `artifact_version` of the primary upstream input (e.g.
`sdet-plan-generator` records the `artifact_version` of the `prd_context.json` it read).

---

## Guardrails

- **Never delete a prior versioned file** unless the user explicitly asks.
- **Never version the current pointer** — `prd_context.json` is always a plain copy, never
  `prd_context_latest.json` or `prd_context_current.json`.
- **Never invent a version string** — if the doc has no version and no prior files exist,
  start at `v1`. Do not use dates, timestamps, or hashes as version identifiers in filenames.
- **The version-less file is always writable** — it is expected to be overwritten on each run.
  Protect only the versioned copies.
