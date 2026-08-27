---
name: design-extractor
description: Extract the UI flow and element map from a mobile app's design into design_context.json — screens, logical element IDs, interactions, states, ui_flow, and project-level ambiguity tracking. Input is a JSON export from the "Export Design Raw JSON" Figma plugin. The concrete extraction pipeline is intentionally not specified here; this skill defines the contract, principles, and output shape that any implementation must satisfy.
---

# Mobile Design Extractor

This skill is the frontend-primary stage of the AEP mobile pipeline. It produces the screen/element map whose logical `element_id`s later join to real per-platform locators from the code-change-extractor stage.

## Golden input

The current POC reference export is `golden/inputs/GoFood-Group-Order-Bundling-Items.json` (Figma selection export, `formatVersion: 2`, 3 540 nodes). Its schema and observed conventions are memoised in `INPUT_SCHEMA.md`. Any new extraction implementation must be validated against this golden input before it replaces the previous pipeline.

## Output contract

One `design_context.json` per app in scope. The file must validate against the plugin-level `design_context` schema and contain at least:

- `app`: the app identifier, when resolvable.
- `screens`: a list of screens, each with its states and logical elements.
- `elements`: logical element IDs with role hints derived from the design, not fabricated.
- `ui_flow`: directed edges representing navigation, starting from the reserved `ENTRY` pseudo-node.
- `extraction_gaps`: anything that could not be resolved, with a reason and a Figma node reference when available.
- `blocking_issues`: questions that require a design-team answer before downstream stages can proceed safely.

## Principles

- Never invent `screen_id`, `element_id`, states, or edges.
- Collapse state variants into screen-level states; do not fragment them into separate screens.
- Report unresolved navigation in `blocking_issues` rather than fabricating it.
- Any unresolvable ambiguity becomes an `extraction_gaps` entry and the run continues. A partial, honestly labelled output is preferable to no output.
- The model may enrich labels, validations, and wording, but it must not create structure that the design export does not support.
- `element_id` casing and role suffixes are the join key to the code-change context; once established, downstream stages must not re-case or re-derive them.

## Workflow outline

1. **Preflight**: verify the export can be parsed, carries geometry, and contains the expected Figma document structure. Emit a `DEGRADED` context if not.
2. **App set**: determine how many apps the export covers. Do not assume a single app from visual style or dark theme alone. Report the decision before extracting.
3. **Extract**: derive screens, states, elements, and `ui_flow` from the export. Keep the derivation deterministic and reproducible.
4. **Enrich**: use a constrained, fast-tier model pass only for decoration, labels, and note-traced validations. Escalate to a stronger tier only when a screen is flagged as genuinely ambiguous.
5. **Review**: produce a human-verifiable side-by-side artifact so reviewers can confirm collapse, identity, and edge decisions against the Figma board.
6. **Validate**: ensure the final context passes schema validation and referential integrity checks.

## Pipeline scripts

Four Python scripts implement the extraction pipeline. Run them from the skill directory.

### Step 1 — Preprocess & render (`render_design.py`)

```
python3 render_design.py -i <input.json> -w <workdir>
```

Runs both the `preprocess` phase (spatial analysis → `<stem>_pre-process.json`) and the `render` phase (HTML wireframe → `<stem>_render.html`). Pass `preprocess` or `render` as a positional argument to run only one phase.

### Step 2 — Extract design context (`extract_design_context.py`)

```
python3 extract_design_context.py \
    --preprocess <workdir>/stem_pre-process.json \
    --input      <original-input.json> \
    [-w <workdir>] \
    [-o <workdir>/design_context.temp.json]  # default
```

Reads `_pre-process.json` and writes a schema-valid `design_context.temp.json` (intermediate artifact). Validates the output against `../../schemas/design_context.schema.json` before writing.

### Step 3 — Agent Review & Refinement
Once `design_context.temp.json` is generated, first check `<workdir>/element_id_quality.json` (produced by Step 2) to quickly identify which `trigger_element_id`s have `"quality": "BAD"`. Prioritize reviewing those flagged elements in the `ui_flow` array. Then identify and highlight any remaining `trigger_element_id` where the mechanical name is still too generic or ambiguous.

For each identified element, suggest the most appropriate replacement id based on contextual clues on that element — e.g. its label/text content, accessibility name, role, position within the screen hierarchy, and the interaction semantics of its `ui_flow` edge. The suggested id must follow the same casing/role-suffix conventions as the rest of the context (see Principles), since it is the join key to downstream code-change locators.

Output the proposed renames as a separate mapping JSON file, `<workdir>/id_refinement_map.json`, with one entry per refined element:

```json
{
  "refinements": [
    {
      "screen_id": "...",
      "old_id": "button_1",
      "suggested_id": "checkout_apply_promo_button",
      "confidence": "high",
      "rationale": "Element label reads 'Apply promo' and triggers a checkout action"
    }
  ]
}
```

Do not edit `design_context.temp.json` directly; reviewers use the mapping file to confirm or reject each rename before it is applied.

### Step 4 — Apply refinements (`recover_design_context.py`)

```
python3 recover_design_context.py \
    --refinements <workdir>/id_refinement_map.json \
    [-w <workdir>] \
    [-c <workdir>/design_context.temp.json]  # default input \
    [-o <workdir>/design_context.json]       # default output
```

Reads `design_context.temp.json` and `id_refinement_map.json`, applies all refinements with `confidence: "medium"` or `"high"`, updates both `element_id` in screens and `trigger_element_id` in `ui_flow`, validates against schema, and writes the final `design_context.json`.

### Output artefacts (workdir convention)

All run outputs go to a workdir, never into the skill directory itself. Suggested layout:

```
golden/outputs/<stem>/
  <stem>_pre-process.json
  <stem>_render.html
  design_context.temp.json      # Step 2 output (intermediate)
  id_refinement_map.json        # Step 3 output (reviewer-produced)
  design_context.json           # Step 4 output (final)
```

## Model policy

- Default enrichment work runs on the fast tier.
- Escalate only for screens flagged as genuinely ambiguous by the pipeline.
- Never escalate to redo structure. If the structure looks wrong, the fix belongs in the Figma board or the extraction logic, not in a larger model call.
- Do not use a tier above Sonnet for any design-extractor task.

## Rules

- One write per output file. Keep intermediates in a work directory; never commit run outputs into the skill directory.
- Blocking issues must be phrased so a PM can answer them and must name the Figma node id involved.
- Never edit the final `design_context.json` by hand.
- **Always re-run all pipeline steps from scratch** — never reuse previous run outputs (e.g. `_pre-process.json`, `design_context.temp.json`, `id_refinement_map.json`, `design_context.json`, `element_id_quality.json`). Each run must be fully reproducible from the original Figma input.
