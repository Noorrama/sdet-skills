# GoPay Affiliate — design-extractor golden example (spatial pipeline)

Real-board golden for `skills/design-extractor` (spatial-first pipeline).
Export 2026-08-21, plugin v0.6.0, 9,977 nodes, 47 connectors.

| file | what |
| :--- | :--- |
| `figma_export.json` | "Export Design Raw JSON" v2 export of the GoPay Affiliate board |
| `design_context.json` | full-pipeline output: Phase A + Haiku Phase B enrichment + Sonnet escalation pass, schema-valid, referential checks OK |
| `phase_a.report.json` | Phase A provenance sidecar (protos, merges, state transitions, unresolved endpoints) |

Regenerate the deterministic half (must reproduce byte-identically):

```bash
cd ../../skills/design-extractor/spatial_pipeline
python3 phase_a.py ../../../examples/gopay-affiliate/figma_export.json \
        --app gopay-merchant --out /tmp/gpa
```

Expected Phase A counters: 47 connectors → 20 edges (2 of them
`CONNECTOR_CONTRACTED` through the "Does user have GoPay+?" decision box),
3 state transitions, 47 screens from 92 frames, `schema: VALID`,
`referential checks: OK`. The enriched `design_context.json` additionally
carries the LLM-pass elements (250) and note-traced validations; it is a
reference output, not byte-reproducible (two model passes).
