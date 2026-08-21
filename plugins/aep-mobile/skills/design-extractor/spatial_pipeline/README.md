# Spatial-first design-context pipeline

The engine behind the `mobile-design-extractor` skill (see `../SKILL.md` for
the workflow, model policy, and preflight contract). Deterministic-first
extraction of `design_context.json` from an "Export Design Raw JSON"
(formatVersion 2) Figma export. Phase A is pure geometry + names —
byte-reproducible, zero LLM. Phase B is a constrained LLM enrichment (Haiku
agents; `escalations.json` names the few screens worth a Sonnet pass) that can
only decorate the skeleton, never add structure.

## Stages

| script | in | out | role |
|---|---|---|---|
| `spatial_scan.py` | export.json | (library / console digest) | groups, swim-lane rows, columns, chip/banner/caption association. All thresholds derived from the modal portrait-frame size. |
| `connector_resolve.py` | export.json | `flow_edges.json` | connector endpoints → screens (element-in-screen, chip label, variant box, small-section entry ≤8 screens); arrowhead = direction; reactions checked (usually library wiring → INFO). |
| `phase_a.py` | export.json | `design_context.json` + `phase_a.report.json` | proto-screen collapse, states, scenario sections, ui_flow, deterministic elements from connector triggers. Schema-validated. |
| `viz_export.py` + `viz_shell.html` | export + edges | `flow_map.html` | board-replica artifact for human side-by-side verification against Figma. |
| `phase_b_packets.py` | export + design_context | `phase_b_packets.jsonl` | one grounded packet per screen: bindable candidate layers, nearby designer notes, states, edges. |
| (LLM pass) | packets | `phase_b_out.jsonl` | enrichment per the contract in `phase_b_merge.py` docstring. |
| `phase_b_merge.py` | skeleton + packets + enrichment | `design_context.enriched.json` | enforces the no-invention contract, rebuilds element_ids, re-validates schema. |

## Collapse rules (user-validated on GoFood Group Order)

- **Proto-screen** = consecutive same-frame-name run inside one column.
- **Identity**: multi-frame proto → frame name; single-frame proto → chip title
  unless it starts with the frame name.
- **States** = chip titles (identity prefix stripped). Chip `Type` variant
  (New screen / Changes / Existing) is change-status metadata, never a state.
- **Scenario sections** (sub-section whose screens' identities exist outside) =
  preconditions: states get "<scenario> — " prefix, internal edges carry the
  title as condition. Never separate screens.
- **Attached rows** (dialog shelves under x-overlapping parents, no left
  caption) → OVERLAY navigation targets.
- **Self-loops after collapse** = state transitions (report), never ui_flow.
- **Rows** cluster by top-line, never y-interval overlap (tall scroll frames
  bridge lanes transitively).
- **Section-attached connectors** resolve only into sections holding ≤8 screens
  (the export has no attachment position on section endpoints; a bigger target
  would fabricate a screen — caught by ground truth on MPS 10882:10702).

## Honesty invariants

Anything unresolvable is *reported*, never guessed: `SECTION_AMBIGUOUS`
connectors, excluded reference screenshots, draft loose clusters, ambiguous
generic-name collapses, external prototype-reaction destinations. Ground-truth
spot checks: pick any screen node id in Figma, count its connectors, compare
with edges touching that id's collapsed screen.

## Run

```bash
python3 phase_a.py <export.json>          # skeleton + report, schema-validated
python3 phase_b_packets.py <export.json>  # packets for the LLM pass
# ... run the enrichment pass per phase_b_merge.py docstring ...
python3 phase_b_merge.py                  # enriched context, schema-validated
```
