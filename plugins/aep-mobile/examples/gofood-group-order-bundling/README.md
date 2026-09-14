# GoFood Group Order — bundling items (design bundle trial)

Example expectations for running **`design-extractor`** against the **figma-design-bundle** trial export scoped to section **Group Order - Bundling items** (selection node id `14090:111176`).

## Input (agent)

Point the agent at the bundle **root directory** (contains `manifest.json` with `generator.name: "figma-design-bundle"`):

- Local trial: `~/Downloads/GoFood-Group-Order--MVP---Group-Order-v5.46-Trial` (or set `AEP_TRIAL_BUNDLE` to that path)

Plugin root: `plugins/aep-mobile`. Do **not** commit multi‑MB JPG screenshots in the first MR unless requested; `tests/fixtures/gofood-bundling-min/` is the committed minimal slice for CI.

### Human export (not agent input)

Maintainers obtain the trial bundle by exporting from the GoFood Group Order board in Figma (section **Group Order - Bundling items**, node `14090:111176`) using the **figma-design-bundle** generator. That step is outside Phase A — agents only read the exported folder on disk, not live Figma.

## Regenerate `design_context.json`

```bash
export AEP_TRIAL_BUNDLE=~/Downloads/GoFood-Group-Order--MVP---Group-Order-v5.46-Trial

python3 scripts/run_design_extractor.py \
  --bundle "$AEP_TRIAL_BUNDLE" \
  --plugin-root . \
  --app gofood-consumer \
  --out examples/gofood-group-order-bundling/design_context.json
```

## Expected `design_context.json` shape

After a bundle run (see [BUNDLE_INPUT.md](../../references/design-extractor/BUNDLE_INPUT.md)):

| Field | Expected |
|-------|----------|
| `app` | `gofood-consumer` (from `config/gofood-consumer.json` when GoFood file/user context applies) |
| `design_source.scope` | `selection` |
| `design_source.has_geometry` | `true` (raw nodes include x/y) |
| `screens[]` | **8** rows; `screen_id` values: `MPS`, `LANDING`, `SHIMMER`, `BUNDLING_FULL_DATA`, `SHARED_CART`, `CHECKOUT`, `MERCHANT_PROFILE_REQUIRED`, `DISH_DETAILS_4_ITEMS` |
| State coverage | **18** state names across `screen_states` (include disambiguated names such as `MPS - Scroll~2`, `Added item details~3`) |
| `ui_flow[]` | **14** deduplicated outgoing connector edges **plus ≥1 `ENTRY → …` edge** when manifest state labels or topology imply a flow start |
| `ui_flow` triggers | **≥12** connector edges with `trigger_element_id`; spot-check labels **Go to checkout** / **Edit** / **Plus** on connectors `14107:120764`, `14107:120070`, `15959:86946` |
| `elements[]` | Non-empty on **Landing** (billing radios with copy labels, primary CTA, Learn more link), **Shared cart**, **MPS** |
| `extraction_status` | **`INCOMPLETE`** while dangling connectors or manifest warnings remain gapped — **`OK` only if `extraction_gaps` is empty** |

### Spot checks

- Landing node **`14090:111409`**: label **Create & invite friends** with interaction via connector **`14090:118193`**
- Landing billing: **Everyone pays for their items**, **Everyone pays an equal share**, **You pay for everyone**; **Learn more about billing methods**
- Shared cart host state **`14107:119629`**: host cart with bundled items present in element map
- `ui_flow[].to_screen_id` / `from_screen_id` reference only ids listed in `screens[]` (plus pseudo **`ENTRY`** on incoming edges)
- First `ui_flow` edge is **`ENTRY → MPS`** when the MPS state carries an entry-point label in the bundle manifest

## Validation

From plugin root:

```bash
python3 scripts/validate_design_context.py \
  examples/gofood-group-order-bundling/design_context.json \
  --schema schemas/design_context.schema.json \
  --fixture gofood-group-order-bundling
```

Tests (minimal fixture always; full trial when `AEP_TRIAL_BUNDLE` is set):

```bash
python3 -m pytest tests/test_design_extractor_bundle.py
```

A snapshot from the trial bundle run is checked in as [`design_context.json`](./design_context.json) (`extraction_status: INCOMPLETE`, 8 screens, 14 connector `ui_flow` edges + ENTRY, improved trigger labels).
