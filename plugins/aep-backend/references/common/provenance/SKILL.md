---
name: phase-a-provenance
description: >-
  Shared Phase A provenance, staleness, re-extract, and context-diff workflow for
  backend QA extractors. Stamps prd_context.json / rfc_context.json with source
  revision + content hash; detects when a PRD/RFC was updated after extraction;
  re-extracts into a new dated run folder and diffs against the prior context.
  Use whenever extracting or re-extracting a PRD/RFC, when the user says the doc
  was updated/finalised, before sdet-plan-generator, or when checking if a
  qa-artifacts context is stale. Referenced by prd-extractor and rfc-extractor —
  read this skill whenever those extractors write or refresh a context.
---

# Phase A Provenance (shared — PRD + RFC)

Common skill for **both** `prd-extractor` and `rfc-extractor`. Do not duplicate
these rules inside the extractors — **read and follow this file** when stamping,
checking freshness, re-extracting, or diffing contexts.

## Shared Phase A contract (prd-extractor ↔ rfc-extractor)

`prd-extractor` and `rfc-extractor` are the two Phase A extractors. Downstream
`sdet-plan-generator` joins their JSON with `tasks_context` later — keep these
contracts stable. Artifact paths and the `provenance` shape are defined in the
sections below; the rest of the shared contract lives here.

### Source-of-truth split

| Concern | Owner |
|---|---|
| ACs / business error intent | `prd_context` |
| API / event / DB / business-logic contract | `rfc_context` |
| Error code & flag *names* in PRD | cross-check keys only |
| Error code *shape* & flag on/off behaviour | RFC |
| PRD ↔ RFC drift | **rfc-extractor** → `prd_drift_flags` (`null` if no PRD) |

### Gap shape (identical fields across both)

PRD: `needs_clarification[]`   RFC: `extraction_gaps[]`

```json
{ "field": "<json-path or logical field>", "reason": "<code>", "detail": "<literal>", "blocking": false }
```

- Shared reason codes: `missing_from_source`, `ambiguous`
- PRD-only: `non_verifiable`, `missing_boundary`, `undefined_value`, `missing_error_copy`
- RFC-only: `contract_incomplete`, `flag_underspecified`, `missing_timeline`, `status_ambiguous`

`blocking: true` → plan gen must not treat the related AC/contract as build-ready / executable oracle. The enforced enum lives in each schema's `ClarificationGap` — keep this list in sync with those schemas.

### Join keys

- Stable IDs: `US-###`, `REQ-###`, `AC-###` (PRD); `BL-###` optional (RFC).
- RFC contracts, `business_logic` items, and `sequence_flows` may carry `requirement_refs[]` / `ac_refs[]` **only when the RFC (or linked PRD) states the link** — never invent.
- Milestone IDs (`M1`, `M2`, …) must match string-for-string across both contexts when both state them.

### Draft contracts

RFC `contract_status`: `ready` | `draft` | `not_specified`. Plan gen must not emit executable scenarios against non-`ready` contracts unless the user accepts a provisional plan.

### PRD comment + approach rules (prd-extractor)

- Comment / review-thread evidence → `comment_resolutions[]` (`resolves` | `clarifies` | `unanswered`). Do **not** embed comment narrative in `open_decisions[]`.
- Mutually exclusive approaches → `approach_branches`. Emit parallel contingent REQ/AC paths **only** while `status=undecided`; if decided, keep only `chosen_branch`.

### Schema + adoption

The context contract lives **only** in the JSON Schemas — there is no pydantic/`models_*.py` layer and nothing to re-export. Extractors validate the written JSON against the schema file with `jsonschema` (report, don't block).

1. `schemas/prd_context.schema.json` → the `prd_context` contract (shared `ClarificationGap`, structured `user_flow`, mobile enrichments, `involved_teams`, `comment_resolutions`, `approach_branches`, `provenance`).
2. `schemas/rfc_context.schema.json` → the `rfc_context` contract (same `ClarificationGap`, contracts with join refs, `provenance`).
3. `Provenance` is defined inline under `#/definitions/Provenance` in **both** schemas — one shape, kept in sync by hand.
4. Copy this `common/provenance/SKILL.md` (+ `common/scripts/`) into the target repo's `references/common/` (or keep a personal `~/.claude/skills/phase-a-provenance`) and ensure both extractors can read it.
5. Run DeepEval for both skills.

## When to use

| Trigger | Action |
|---|---|
| Fresh extract (first time) | Stamp `provenance`, write to a **dated** run folder |
| User says PRD/RFC updated / finalised / republished | Staleness check → re-extract → context diff |
| Before `sdet-plan-generator` | Staleness check; refuse or warn if stale |
| User asks "is this context still valid?" / "re-review" | Staleness check (+ optional re-extract/diff) |
| `approach_finalised` / readiness flipped since extract | Mandatory re-extract |

## Artifact layout (never overwrite blindly)

```
qa-artifacts/{epic}/run-YYYY-MM-DD[T HHMM]/prd_context.json
qa-artifacts/{epic}/run-YYYY-MM-DD[T HHMM]/rfc_context.json
```

- Prefer `run-YYYY-MM-DD` (add `THHMM` if multiple runs the same day).
- **Do not overwrite** an existing run that already has a context for that doc type unless the user explicitly asks to replace it.
- `adhoc/` is allowed for scratch extracts, but tell the user it is not a durable baseline for staleness — next durable extract should use a dated run.
- Keep the prior run on disk so diffs are possible.

## `provenance` object (required on every new extract)

Embed on both `prd_context.json` and `rfc_context.json`:

```json
{
  "provenance": {
    "source_ref": "https://… or local path or ticket id",
    "source_type": "prd",
    "source_revision": "Confluence v12 | docx mtime 2026-08-10T11:51:00+05:30 | null if unknown",
    "source_content_hash": "sha256:<hex>",
    "extracted_at": "2026-08-10T10:05:00Z",
    "extractor_skill": "rfc-extractor",
    "extractor_skill_version": "2026-08-10",
    "status_at_extract": "IN REVIEW",
    "finalised_at_extract": false,
    "prior_run": "qa-artifacts/RFC-618/run-2026-08-01"
  }
}
```

| Field | Rule |
|---|---|
| `source_ref` | Canonical link/path/id used for this extract |
| `source_type` | `"prd"` or `"rfc"` |
| `source_revision` | Human revision marker if available (Confluence version, Google Doc revision, Jira updated, file mtime). `null` only when truly unavailable — then rely on hash |
| `source_content_hash` | `sha256` of the **normalised extractable text** (see hashing). Always required for file/paste sources; for URL-only sources hash the fetched/exported text you actually read |
| `extracted_at` | UTC ISO-8601 |
| `extractor_skill` | `"prd-extractor"` or `"rfc-extractor"` |
| `extractor_skill_version` | Date or semver of the skill revision used (skill folder mtime date is fine) |
| `status_at_extract` | Literal status/readiness string captured at extract time (`DRAFT`, `IN REVIEW`, PRD readiness, …) |
| `finalised_at_extract` | RFC: value of `approach_finalised`. PRD: `true` only if readiness/status clearly means final/approved; else `false` |
| `prior_run` | Relative path of the previous run being superseded, or `null` on first extract |

Schema: the shared `Provenance` object is defined inline (identically) in both `schemas/prd_context.schema.json` and `schemas/rfc_context.schema.json` — keep the two copies in sync when either changes.

## Hashing

Use the helper when possible:

```
python ${CLAUDE_PLUGIN_ROOT}/references/common/scripts/hash_source.py <file-or-->
```

Rules:
- Hash **UTF-8 text you extracted from**, not the raw `.docx`/PDF binary (binaries change without content changes).
- Normalise: NFKC, strip trailing whitespace per line, join with `\n`, ensure trailing newline.
- Prefix with `sha256:`.
- If source is only a URL and you cannot fetch bytes, set `source_content_hash` to `null`, keep `source_revision` if any, and add a non-blocking gap: provenance hash unavailable — staleness will rely on revision/user confirmation.

## Staleness check

Inputs: existing context path + current source (file/URL/paste).

1. Load `provenance` from the context (if missing → treat as **stale / unknown**, recommend re-extract).
2. Recompute hash (and/or read current revision) from the live source.
3. Compare:

| Condition | Result |
|---|---|
| `source_content_hash` matches live hash | Content-fresh |
| Hash mismatch | **Stale (content)** |
| `source_revision` differs (when both non-null) | **Stale (revision)** |
| Live status/finalised ≠ `status_at_extract` / `finalised_at_extract` | **Stale (status)** — even if hash somehow matches |
| Hash null and revision null | **Unknown** — ask user to confirm or re-extract |

Chat readout for a check (no file write unless re-extracting):

- Context path + `extracted_at`
- Fresh / Stale (content|revision|status) / Unknown
- What changed at the source level (revision bump, finalised flip, hash delta)
- Recommended next step (none / re-extract / re-extract+diff)

## Re-extract workflow

1. Run staleness check (above).
2. Choose a **new** dated run folder (do not clobber the prior run).
3. Invoke the owning extractor skill (`prd-extractor` or `rfc-extractor`) fully — do not patch fields by hand onto the old JSON.
4. Stamp new `provenance` with `prior_run` pointing at the old run.
5. Produce a **context diff** (below) in chat.
6. If RFC/PRD is now finalised, re-score draft gates (`contract_status`, readiness, blocking gaps) under the extractor’s normal rules — never leave `draft` solely because the *old* run was draft.

## Context diff (re-review)

Diff **structured contexts**, not only the source docs. Compare prior vs new JSON and report:

**Always**
- `provenance` stamp changes (hash, revision, status/finalised flags)
- Closed vs new gaps (`needs_clarification` / `extraction_gaps`)
- Open decisions / open questions closed or added

**PRD-focused**
- REQ/AC added, removed, or text-changed
- Scope in/out changes
- Error code / feature flag name set changes
- Readiness / approach_branches changes

**RFC-focused**
- `contract_status` flips (`draft`/`not_specified` → `ready`, or reverse)
- REST/gRPC/Kafka/other contracts added/removed/shape-changed
- `error_codes`, `feature_flags`, `business_logic`, `db_schema_changes`
- `prd_drift_flags` (re-run drift if PRD context exists)

Keep the diff factual. Do not editorialize who was “wrong.”

Optional machine-readable sidecar (only if user asks):

```
qa-artifacts/{epic}/{new_run}/context_diff.json
```

```json
{
  "prior_run": "…",
  "new_run": "…",
  "stale_reasons": ["content", "status"],
  "summary": ["…"],
  "added": {},
  "removed": {},
  "changed": {}
}
```

## Downstream gate (for plan-gen / users)

Before treating a context as an oracle:

1. Provenance present.
2. Not stale (or user explicitly accepts a provisional plan on a draft/stale context).
3. RFC: `approach_finalised` / contract `ready` rules from `rfc-extractor` still apply.
4. If stale → **re-extract first**; do not silently plan from the old run.

## Guardrails

- Never invent a hash or revision.
- Never delete prior runs unless the user asks.
- Never “refresh” by editing a few fields in place — full extractor pass into a new run.
- This skill does **not** replace extractor faithfulness rules; it only tracks freshness and re-review.

## Invoking

- Standalone: “Check if `qa-artifacts/RFC-618/adhoc/rfc_context.json` is stale against this RFC”
- Via extractor: extractors must stamp provenance on every write and offer re-extract+diff when status was non-final or user supplies an updated doc
- “Re-extract RFC-618 and diff against the previous run”
