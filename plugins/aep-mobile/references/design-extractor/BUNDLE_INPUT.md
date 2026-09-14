# Figma design bundle input (`figma-design-bundle`)

Memorised contract for **`design-extractor`** when the orchestrator passes a **directory** export from the Figma **figma-design-bundle** generator (v0.1.0+).

> **Agent input:** Only the **bundle root directory** on disk. Never open, fetch, or use live Figma URLs as input. If the user provides only a URL → `INCOMPLETE` + **BLOCKING** gap: re-export as a bundle.

Reference trial scope (labels only): export folder `GoFood-Group-Order--MVP---Group-Order-v5.46-Trial`, selection node id **`14090:111176`** (“Group Order - Bundling items”).

---

## Detection

| Input shape | Rule |
|-------------|------|
| **Bundle directory (required for Phase A)** | Path is a directory whose root contains `manifest.json` with `generator.name === "figma-design-bundle"` and `formatVersion === 1`. |
| **Missing or wrong manifest** | `INCOMPLETE` + **BLOCKING** gap — human must re-export as figma-design-bundle; agents do not accept legacy single-file Raw JSON as orchestrated input. |

Index files at bundle root:

- `manifest.json` — screens, states, stats, warnings, conventions
- `links.json` — optional traceability map of screen/state → `figmaUrl` **inside the bundle** (not live Figma access); per-state `figmaUrl` in manifest is likewise file-local metadata

Per state under `{screen.dir}/{state.dir}/`:

| File | Role |
|------|------|
| `raw.json` | Export Design Raw JSON **v2** envelope scoped to one state (`scope: "state"`) |
| `connectors.json` | Incoming/outgoing connector edges with pre-resolved `owner.screenId` / `stateId` and layer `path` |
| `Screenshot_*.jpg` | Visual reference only — do not infer copy from pixels |
| `smart.json` | Listed in manifest `files` when exporter ships it; **may be absent on disk** — record `INFO` gap, do not invent smart metadata |

---

## `manifest.json` envelope

| Field | Use in extraction |
|-------|-------------------|
| `source.fileKey`, `source.fileName`, `source.pageName`, `source.scope`, `source.selectionIds` | `design_source` provenance; when `scope === "selection"`, note in gaps that flows leaving the selection cannot be verified outside the bundle |
| `exportedAt` | `design_source.exported_at` |
| `conventions.stateVocabulary` | Map state names → `state_kinds` (see below) |
| `screens[]` | One `design_context.screens[]` row per `screens[].id` |
| `screens[].states[]` | `screen_states`, `source_refs`, per-state element walks |
| `screens[].defaultStateId` | Default state's `nodeId` → `source_ref` |
| `stats` | Sum into `design_source.node_count`; `truncated_count: 0` across trial states |
| `warnings[]` | `extraction_gaps[]` — cite `code`, `nodeId`, `message` |

Raw v2 per state (`raw.json`):

- `scope: "state"`, `export.formatVersion: 2`, `export.maxDepth`, `export.nodeCount`, `export.truncatedCount`
- `nodes[]` tree: `TEXT.characters`, `INSTANCE` + `variantProperties` / `componentProperties`, optional `x`/`y`/`width`/`height`

`connectors.json`:

- `connectors[]` with `role`: `"incoming"` | `"outgoing"`
- `source` / `target` with `nodeId`, `path`, `owner: { screenId, stateId, stateNodeId }`
- `text` — connector label → `ui_flow[].condition` (empty string if absent)

---

## Mapping cheat sheet (bundle → `design_context`)

| `design_context` | Source |
|------------------|--------|
| `design_source` | Aggregate from `manifest.source` + summed `stats` + `has_geometry: true` if any raw node has `x`/`y` |
| `screens[]` | One row per `manifest.screens[].id`; `screen_id` = **upper snake of manifest id** (replace `-` with `_`, collapse repeated `_`, uppercase — e.g. `Bundling_-_Full_data` → `BUNDLING_FULL_DATA`) |
| `screen_states` / `state_kinds` | Each `states[].name`; map `Loading` → `LOADING`, vocabulary names (`Default`, `Empty`, …) → matching enum; otherwise `OTHER` |
| `source_ref` / `source_refs` | Default state `nodeId` + all state `nodeId`s for that screen |
| `elements[]` | Walk each state's `raw.json` tree (see **elements[] rules** below); always index **outgoing connector** `source.nodeId` layers so `ui_flow` triggers can resolve |
| `interactions[]` | Outgoing `connectors.json` entries whose `source.owner.stateId` matches the state being walked; set `connector_id`, `destination_screen_id`, `action` |
| `ui_flow[]` | Dedupe outgoing connectors by `connector.id` across all states; map `owner.screenId` → `screen_id`; set `trigger_element_id` only when source `nodeId` maps to an element; `condition` from connector `text` or `""`; `edge_source: "CONNECTOR"`, `confidence: "EXPLICIT"`, `source_ref` = connector id |
| `extraction_gaps` | Manifest `warnings[]` (group by `code` or one row per warning — never omit `CONNECTOR_DANGLING`); missing `smart.json` (`INFO`); selection scope on `design_source.scope` (`WARN` or `INFO`) |

**Principle:** deterministic facts come only from bundle files. Ambiguous labels, dangling targets, or missing config become `extraction_gaps[]` or `project_context.blocking_issues[]` — never invented copy, deep links, or conditions.

### `screen_id` helper

```
manifest id "Shared_cart"     → SHARED_CART
manifest id "Bundling_-_Full_data" → BUNDLING_FULL_DATA
manifest id "Dish_details_-_4_items" → DISH_DETAILS_4_ITEMS
```

### State paths on disk

Primary layout: `{bundle}/{screens[].dir}/{states[].dir}/raw.json` (and sibling `connectors.json`). Some exports flatten paths so `states[].dir` already includes the screen segment — then `{bundle}/{states[].dir}/raw.json` is correct (e.g. `MPS/MPS/raw.json`). The extractor script resolves paths from `manifest.json`; agents preflight manifest only.

### Connector endpoint semantics (`ui_flow` vs `screens[]`)

| Field | Meaning |
|-------|---------|
| `screens[].source_ref` / `source_refs[]` | Figma **frame** node ids for the screen (state roots). Join when resolving which screen owns a layer. |
| `ui_flow[].from_source_ref` / `to_source_ref` | `connectorStart.endpointNodeId` / `connectorEnd.endpointNodeId` — the exact layers the arrow attaches to (often a button instance or label chip, not always the destination frame). |
| `ui_flow[].trigger_source_ref` | Figma node id of the **trigger element**; must match `screens[].elements[].source_ref` on `from_screen_id` when `trigger_element_id` is set. |

Downstream **Navigation Ladder rung 2** (sdet-plan-runner): prefer `trigger_source_ref` → element `source_ref`, then `trigger_element_id`, then connector endpoints.

### `elements[]` rules (bundle Python extractor)

1. **Scope** — Full interactive tree walk on **`defaultStateId` / `isDefault`** state only. Other states add **`ensure_connector_source_element`** rows for outgoing `connectors.json` `source.nodeId` only (no full INSTANCE walk). Post-merge **`dedupe_elements_by_source_ref`** keeps one row per `source_ref` (prefer higher-quality labels; union `states_represented`).
2. **Connector sources** — For every outgoing connector in a state, ensure an element exists for `source.nodeId` (label from button text `Button text#` / nested TEXT, meaningful TEXT in row/footer frame, normalized instance path, else sibling TEXT in row `FRAME`, else instance `name` with `element_ambiguity: MEDIUM`). When label is still generic (`Text`, `button/circular`, `properties/…/chips`) and connector `text` is non-empty, set `label` from **`connector.text`** with `element_ambiguity: MEDIUM`.
3. **Radio / billing rows** — Row `FRAME` containing `selection_control/radio` + TEXT `characters`: `role: TOGGLE`, unique `element_id` from slug(label) + `_toggle`. Skip duplicate **`selection_control/radio` INSTANCE** walk when the row FRAME already registered that radio id.
4. **Button labels** — Prefer TEXT under `Button text#`; use visible copy for `element_id` suffix (`create_invite_friends_btn`). **`element_id` strings are assigned by `scripts/design_extractor` heuristics** (screen slug + role suffix); they align with config `naming_convention` shape in docs but are not built from `element_id_pattern` at runtime.
5. **Exclude loaders** — Do not treat `indicator/spinner`, full-screen loaders, or skeleton placeholders as buttons or `ui_flow` triggers.
6. **LIST / SKU instances** — Skip generic list/sku INSTANCE rows unless the node is an outgoing connector `source.nodeId` (connector pass adds them when needed).
7. **Footer / link copy** — Long TEXT nodes (e.g. “Learn more…”) emit as `role: LINK` when present in raw (not inferred from screenshots).

**GoTo / Asphalt heuristics (not locale-neutral)** — Label and list rules that match strings such as `checkout`, `Edit`, `Rp` price patterns, instance paths like `merchant_profile_sku`, or connector text **Plus / minus** are tuned for GoTo/Asphalt exports. Other apps may need configuration or future manifest convention fields.

### `ui_flow` ENTRY edges

When `manifest.screens[].states[].labels[]` contains entry hints (`entry point`, `1st time`, `starting point`), emit **`from_screen_id: "ENTRY"`** edges with `edge_source: "ENTRY_LABEL"` and set **`screens[].entry_point: true`** on targeted screens (plus zero in-degree screens). If no label hits, emit a single **`ENTRY_TOPOLOGY`** edge: widest forward BFS reach among zero in-degree screens; if the graph is closed (no zero in-degree screens), the default-state screen (else first manifest screen). Sort **`ui_flow`** with all **`navigation_kind: "ENTRY"`** edges first, then connector BFS.

Resolve **`trigger_element_id`** using the element map from the connector **`source.owner`** state when available (not a scroll-variant row from another state).

### `ui_flow` gaps

When a deduplicated outgoing connector has no `trigger_element_id` and the source node has no user-meaningful label in raw, emit `extraction_gaps[]` with `field: ui_flow[i].trigger_element_id`, `severity: WARN` (do not invent triggers).

---

## Trial bundle appendix

The GoFood bundling trial marks the entry screen with a state label chip **“MPS - Entry point”**, so production output shows **`ENTRY → MPS`** via **`ENTRY_LABEL`** (not topology bias).

### Scope

- **8** logical screens, **18** states (`label-instance` grouping from Screen label chips)
- **14** deduplicated screen-to-screen outgoing connector edges (see table)
- Raw richness: TEXT `characters`, INSTANCE variants, `boundVariables`; per-state `truncatedCount: 0`
- **Gaps in source:** 2× `CONNECTOR_DANGLING` in manifest; heavy `LABEL_HEURISTIC` / `NON_STANDARD_STATE`; `smart.json` not on disk though manifest lists it
- **App:** GoFood consumer host flow → `app: "gofood-consumer"` when file name or user implies GoFood

### Screen / state inventory

| Manifest `screens[].id` | `screen_id` | States (count) |
|-------------------------|-------------|----------------|
| MPS | MPS | MPS, MPS - Scroll, Share - Native, MPS - Default GO, MPS - Scroll~2/~3/~4 (7) |
| Landing | LANDING | Landing (1) |
| Shimmer | SHIMMER | Loading (1) |
| Bundling_-_Full_data | BUNDLING_FULL_DATA | SKU details - All require custom; SKU details - Item customized (2) |
| Shared_cart | SHARED_CART | GO - Host item added; GO - Member item added (2) |
| Checkout | CHECKOUT | Checkout - No promo (1) |
| Merchant_Profile_-_Required | MERCHANT_PROFILE_REQUIRED | SKU variants (1) |
| Dish_details_-_4_items | DISH_DETAILS_4_ITEMS | Added item details, ~2, ~3 (3) |

### Connector-derived `ui_flow` (14 edges)

| From | To | Connector id | Notes |
|------|-----|----------------|-------|
| MPS | LANDING | 14090:118188 | Order type entry |
| LANDING | MPS | 14090:118193 | Primary CTA (node 14090:111409) |
| MPS | MPS | 14090:118198 | In-screen |
| MPS | SHIMMER | 14090:118395 | |
| BUNDLING_FULL_DATA | MERCHANT_PROFILE_REQUIRED | 14090:118598 | |
| MERCHANT_PROFILE_REQUIRED | BUNDLING_FULL_DATA | 14090:118949 | |
| MPS | DISH_DETAILS_4_ITEMS | 14107:119606 | |
| BUNDLING_FULL_DATA | MPS | 14107:119622 | |
| MPS | SHARED_CART | 14107:119837 | |
| SHARED_CART | DISH_DETAILS_4_ITEMS | 14107:120070 | |
| SHARED_CART | CHECKOUT | 14107:120764 | |
| MPS | MPS | 15959:86809 | In-screen |
| DISH_DETAILS_4_ITEMS | DISH_DETAILS_4_ITEMS | 15959:86946 | condition `Plus / minus` |
| CHECKOUT | DISH_DETAILS_4_ITEMS | 17429:142749 | Edit line |

Dangling (not in table): `13056:83229`, `19803:139829` — record in `extraction_gaps` / `blocking_issues`.

### Spot-check strings (QA)

- **Landing** `14090:111409`: button label **Create & invite friends** → outgoing to Share / MPS flow via connector `14090:118193`
- **Landing** billing radios: **Everyone pays for their items**, **Everyone pays an equal share**, **You pay for everyone**; footer **Learn more about billing methods**
- **Shared cart** host state `14107:119629`: bundle line items and footer CTAs (host view)

### Fixture path

Keep the full bundle outside the repo (e.g. `~/Downloads/GoFood-Group-Order--MVP---Group-Order-v5.46-Trial`). For CI later, commit **manifest + one state folder** only unless asked to store screenshots.

---

## Related docs

- Agent procedure: [agents/design-extractor.md](../../agents/design-extractor.md)
- Output schema: [schemas/design_context.schema.json](../../schemas/design_context.schema.json)
- Workflow pointer: [WORKFLOW.md](./WORKFLOW.md)
