# GoPay Affiliate — design-extractor golden example (spatial pipeline)

Real-board golden for `agents/design-extractor` (spatial-first pipeline).
Export 2026-08-21, plugin v0.6.0, 9,977 nodes, 47 connectors.
Regenerated 2026-08-24 after the screen-identity split landed.

| file | what |
| :--- | :--- |
| `figma_export.json` | "Export Design Raw JSON" v2 export of the GoPay Affiliate board |
| `design_context.json` | full-pipeline output: Phase A + deterministic auto-bind + Haiku notes-only pass + one Sonnet escalation, schema-valid, referential checks OK |
| `phase_a.report.json` | Phase A provenance sidecar (protos, merges, `identity_splits`, state transitions, unresolved endpoints) |
| `flow_map.html` | the required review page — open it beside the Figma board; self-contained, no server |

Regenerate the deterministic half (must reproduce byte-identically):

```bash
cd ../../agents/design-extractor/spatial_pipeline
python3 phase_a.py ../../../examples/gopay-affiliate/figma_export.json \
        --app gopay-merchant --out /tmp/gpa
```

Expected Phase A counters: 47 connectors → 21 edges (2 of them
`CONNECTOR_CONTRACTED` through the "Does user have GoPay+?" decision box),
3 state transitions, 23 unresolved, **54 screens from 92 frames**,
4 identity splits adding 7 screens, `schema: VALID`, `referential checks: OK`.

The identity splits are the point of this golden — `SCROLL_VIEW` was one screen
holding four unrelated screens' frames before the split rule, and is now
`SCROLL_VIEW`, `SCROLL_VIEW__RIWAYAT_KOMISI`, `SCROLL_VIEW__WELCOME_PAGE`,
`SCROLL_VIEW__AFFILIATE_ACTIVATION`. Same for `SCROLL_VIEW_WITH_PAGINATION_LOAD`
(3), `EMPTY_STATE` (2) and `LOADING` (2). This board carries no screen-label
chips, so the flow context does the seeding.

The finished `design_context.json` additionally carries 813 elements (auto-bind,
zero tokens), 47 states, note-traced validations from two Haiku batches, and one
Sonnet-confirmed HIGH ambiguity (`EMPTY` — the designer's own unanswered
annotation about whether the member list shows all members or only productive
ones for the selected period). It ends `INCOMPLETE` with 4 gaps, rating MEDIUM,
2 blocking issues — the honest state of this board, not a defect.

The two model passes are not byte-reproducible; the Phase A half and the
auto-bound elements are.

```bash
# review page (required step of the skill)
python3 connector_resolve.py <export> /tmp/gpa/flow_edges.json
python3 viz_export.py <export> /tmp/gpa/flow_edges.json /tmp/gpa/viz_data.json \
        /tmp/gpa/design_context.json --html /tmp/gpa/flow_map.html
```
