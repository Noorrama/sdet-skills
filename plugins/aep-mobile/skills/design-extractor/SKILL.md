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
- `element_id` casing and role suffixes are the join key to the code-change context; once established, downstream stages must not re-case or re-derive them. Recognised role suffixes include `_btn`, `_button`, `_input`, `_label`, `_lbl`, `_toggle`, `_tab`, `_list`, `_container`, `_img`, and `_image`.

## Workflow outline

1. **Preflight**: verify the export can be parsed, carries geometry, and contains the expected Figma document structure. Emit a `DEGRADED` context if not.
2. **App set**: determine how many apps the export covers. Do not assume a single app from visual style or dark theme alone. Report the decision before extracting.
3. **Extract**: derive screens, states, elements, and `ui_flow` from the export. Keep the derivation deterministic and reproducible.
4. **Enrich**: use a constrained, fast-tier model pass only for decoration, labels, and note-traced validations. Escalate to a stronger tier only when a screen is flagged as genuinely ambiguous.
5. **Review**: produce a human-verifiable side-by-side artifact so reviewers can confirm collapse, identity, and edge decisions against the Figma board.
6. **Validate**: ensure the final context passes schema validation and referential integrity checks.

## Pipeline scripts

Five Python scripts implement the extraction pipeline. Run them from the skill directory.

### Full fresh run (`run_design_extractor.py`)

```
python3 run_design_extractor.py -i <input.json> -w <workdir>
```

**Always use this entry point for a complete pipeline run.** It:

1. **Deletes** every known artefact in `<workdir>` (fresh run — no reuse).
2. **Runs Step 1** — `render_design.py`
3. **Runs Step 2** — `extract_design_context.py`
4. **Runs Step 3** — writes empty `id_refinement_map.json` scaffold (agent review overwrites when refinements are needed)
5. **Runs Step 4** — `recover_design_context.py`

No step is skipped. After a mechanical run, perform agent review (Step 3 below) to replace the scaffold with refinements, then re-run Step 4 only.

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
    [--inventory <workdir>/stem_inventory.json]  # optional override \
    [-o <workdir>/design_context.temp.json]  # default
```

Reads `_pre-process.json` and the Step 1 inventory sidecar (`<stem>_inventory.json`, resolved from the preprocess path unless `--inventory` is set). Writes `design_context.temp.json`, `element_id_quality.json`, and `screen_collapse_map.json` (mechanical AUTO/AMBIGUOUS scaffold). Validates against `../../schemas/design_context.schema.json` before writing.

**Screen collapse (mechanical):** Frames with identical raw Figma names and compatible outgoing flow signatures are AUTO-collapsed into one `screens[]` record with `source_refs[]` listing every frame id. Semantic element twins across collapsed frames share a canonical `element_id` with per-row `states_represented` and distinct `source_ref`. Ambiguous groups (name variants or divergent flows) stay split and appear in `screen_collapse_map.json` `candidates[]` for agent review.

**Element extraction (inventory-driven):** For each screen, Step 2 extracts **all per-screen `flow_element_ids`** from the inventory — including nested nodes not present as direct children of the screen frame in `_pre-process.json`. Nodes are located via DFS in the screen subtree (`node_tree`). When the inventory file is missing, Step 2 falls back to direct-child extraction (legacy behavior) and records an `extraction_gaps` INFO entry.

**Dedup policy (prefer outgoing):** Among inventory candidates on the same screen, incoming-only ancestor containers are omitted when a descendant candidate has an outgoing connector edge (or is a leaf among candidates). This prevents duplicate elements for wrapper frames that only receive connectors while the actual trigger lives on a nested child.

The `_render.html` hierarchy is unchanged (Step 1); only `design_context` element coverage improves.

### Step 3 — Agent Review & Refinement

On a fresh `run_design_extractor.py` run, Step 3 emits an empty `id_refinement_map.json` scaffold. Step 2 already wrote `screen_collapse_map.json` with mechanical `auto_collapsed[]` and `candidates[]`. **Agent review** replaces those scaffolds when element IDs or ambiguous screen groups need human decisions.

#### 3a — Element ID refinements

Once `design_context.temp.json` is generated, check `<workdir>/element_id_quality.json` (produced by Step 2) to quickly identify which element IDs have `"quality": "BAD"`. This file covers both outgoing `trigger_element_id` values from `ui_flow` **and** incoming connector-destination element IDs from `screens[].elements[]` (elements that connectors land on but are not themselves triggers). Prioritize reviewing all BAD entries — not only those appearing as `trigger_element_id` in `ui_flow`. Then identify and highlight any remaining flow-relevant element IDs where the mechanical name is still too generic or ambiguous.

Note: `recover_design_context.py` already renames matching `element_id` values in `screens[]` and scoped `ui_flow[]` edges (prefer `trigger_source_ref` when present); incoming-only elements do not need `trigger_element_id` updates in `ui_flow`.

For each identified element, suggest the most appropriate replacement id based on contextual clues on that element — e.g. its label/text content, accessibility name, role, position within the screen hierarchy, and the interaction semantics of its `ui_flow` edge. The suggested id must follow the same casing/role-suffix conventions as the rest of the context (see Principles), since it is the join key to downstream code-change locators.

**Overwrite** `<workdir>/id_refinement_map.json` with proposed renames:

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

#### 3b — Ambiguous screen collapse review

Read `<workdir>/screen_collapse_map.json` `candidates[]`, `<stem>_render.html` for layout context, and `element_id_quality.json` for remaining BAD ids. Optionally validate flagged groups via Figma MCP (labels, notes, connector targets).

Append agent decisions to `decisions[]` (only `medium`/`high` confidence are applied in Step 4):

```json
{
  "decisions": [
    {
      "screen_id": "MPS",
      "action": "collapse",
      "frame_ids": ["10882:10702", "10882:10914"],
      "confidence": "high",
      "rationale": "Same MPS chrome; states differ only by order-type chip; flows are state variants not separate screens."
    }
  ]
}
```

Actions: `collapse` | `keep_split`. Mechanical `recommendation` on each candidate is a hint only.

Do not edit `design_context.temp.json` directly; reviewers use the mapping files to confirm decisions before Step 4. After Step 3, **re-run Step 4** to refresh `design_context.json`.

### Step 4 — Apply refinements (`recover_design_context.py`)

```
python3 recover_design_context.py \
    [-w <workdir>] \
    [--refinements <workdir>/id_refinement_map.json] \
    [-c <workdir>/design_context.temp.json]  # default input \
    [-o <workdir>/design_context.json]       # default output
```

Reads `design_context.temp.json`, `screen_collapse_map.json` (when present), and `id_refinement_map.json`. Applies collapse decisions and refinements with `confidence: "medium"` or `"high"`, updates `element_id` in screens and scoped `trigger_element_id` in `ui_flow` (match via `trigger_source_ref` when set), validates against schema, and writes `design_context.json`. Re-run after Step 3 when either mapping file changes.

**Trigger disambiguation:** When multiple `ui_flow` edges share a canonical `trigger_element_id`, use `trigger_source_ref` → `screens[].elements[].source_ref` to resolve the Figma node. `trigger_source_ref` is never rewritten on id rename (node id is stable).

### Mandatory output artefacts (workdir convention)

All run outputs go to a workdir, never into the skill directory itself. **After `run_design_extractor.py` completes, every path below must exist.**

```
golden/outputs/<stem>/
  <stem>_pre-process.json         # Step 1
  <stem>_inventory.json           # Step 1
  <stem>_render.html              # Step 1
  design_context.temp.json        # Step 2
  element_id_quality.json         # Step 2
  screen_collapse_map.json        # Step 2 (mechanical scaffold; agent adds decisions[])
  id_refinement_map.json          # Step 3 (scaffold; agent overwrites)
  design_context.json             # Step 4
```

#### Validation (`<stem>_inventory.json`)

The inventory sidecar is produced during Step 1 preprocess and supports automated review before Step 2:

- `summary.connectors_unresolved` — should be `0` when every connector resolved.
- `summary.elements_without_screen` — count of elements whose `screen_id` is still null after resolution (should be `0` for complete exports).
- `summary.unreachable_screens` — screens not reachable from entry points via screen-to-screen edges (warn-only for partial exports).
- `flow_audit.checks[]` — structured pass/fail checks for connector resolution and screen reachability.

**Element ↔ screen mapping**

- Each record in `elements[]` includes `screen_id` (resolved screen node id, or null) and `screen_resolution_method` (`subtree`, `contextual`, `distance_snap`, or `unresolved`).
- Each record in `screens[]` includes reverse mappings:
  - `flow_element_ids` — element node ids with `classification == "FLOW_RELEVANT"` on that screen.
  - `contextual_element_ids` — element node ids with `classification == "CONTEXTUAL_ANNOTATION"` on that screen.
  - `contextual_information_ids` — ids from spatial contextual-info association (kept for backward compatibility; may overlap with `contextual_element_ids`).

Example one-liner:

```bash
python3 -c "
import json, sys
inv = json.load(open(sys.argv[1]))
assert inv['summary']['connectors_unresolved'] == 0
assert inv['summary']['elements_without_screen'] == 0
" <workdir>/<stem>_inventory.json
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
- **Fresh runs only:** use `run_design_extractor.py`. It deletes all known workdir artefacts before Step 1. Never reuse `_pre-process.json`, `design_context.temp.json`, `id_refinement_map.json`, `design_context.json`, or `element_id_quality.json` from a prior run.
- **No skipped steps:** Steps 1 → 2 → 3 → 4 always execute in order. Do not invoke individual scripts in a way that omits a step.
- **Agent review:** after a mechanical run, replace the Step 3 scaffold with refinements when needed, then re-run Step 4.
