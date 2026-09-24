# Maintainer design-extractor tree (not Phase A)

This directory holds **golden inputs/outputs** and a **legacy** extraction pipeline for spatial regression and maintainer workflows. It is **not** the path the `design-extractor` agent uses in pre-build Phase A.

## Phase A (production)

- Input: **figma-design-bundle** directory on disk only (see [references/design-extractor/BUNDLE_INPUT.md](../../references/design-extractor/BUNDLE_INPUT.md)).
- Runner: `scripts/run_design_extractor.py` with `--bundle` and `--plugin-root`.
- Workflow: [references/design-extractor/WORKFLOW.md](../../references/design-extractor/WORKFLOW.md).

## This directory (maintainer only)

- `golden/` — legacy Export Design Raw JSON v2 fixtures and expected `design_context.json` snapshots.
- `run_design_extractor.py` — legacy golden pipeline; **do not** invoke from the Phase A agent or orchestrator.
- `extract_design_context.py`, `recover_design_context.py`, `render_design.py` — supporting maintainer tooling.

When updating goldens, run the maintainer scripts locally; commit outputs under `golden/outputs/` as today. Orchestrated QA extractors should never depend on this tree as input.
