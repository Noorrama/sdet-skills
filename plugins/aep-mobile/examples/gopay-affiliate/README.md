# GoPay Affiliate — golden regression corpus for design-extractor

A real "Export Design Raw JSON" **format v2** export (geometry, label chips, dashed
nodes, board-level lines) of the GoPay Affiliate main flow, plus the extractor's
expected output. Exported 2026-08-21, plugin v0.6.0, 9,977 nodes, 47 connectors.

| File | What |
| :--- | :--- |
| `figma_export.json` | the raw plugin export — the extractor's input |
| `design_context.json` | expected output (`--app gopay-merchant`) |
| `design_context.report.json` | expected sidecar — tallies, conservation, `unclassified_states` |

## Re-run and compare

```bash
python3 ../../scripts/extract_design_context.py figma_export.json \
    --app gopay-merchant --config ../../config/gopay-merchant.json \
    -o /tmp/regen.json --report
diff <(jq -S 'del(.design_source.exported_at)' /tmp/regen.json) \
     <(jq -S 'del(.design_source.exported_at)' design_context.json)
```

The extractor is deterministic: same input, byte-identical output (only
`exported_at` provenance differs between re-exports of the board itself). Any
diff after a script change is a behaviour change — intended ones update this
corpus, unintended ones are regressions.

## What this board exercises

- 94 state frames collapsing to 33 screens (name qualifiers + variants)
- 42 label-chip states swept proactively (standard #6) — e.g. `CONFIRM_ACCOUNT`
  gains "Not eligible to become upliner yet" / "Code incorrect / not found"
- 47-connector conservation across all six buckets, incl. 16 note connectors,
  1 decision contraction, 12 honestly-unresolved
- Dashed `COMPONENT_SET` borders correctly ignored as group boxes (Figma chrome)
- 2,800px+ section rule LINEs correctly ignored as arrows
- 25 `unclassified_states` entries — input for the State normalisation pass
- 2 `ambiguous_collapses` flagged (e.g. `OVERLAY` collapsing "For Level 1/2") —
  possibly-distinct screens sharing a base name, reported instead of trusted
