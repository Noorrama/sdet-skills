# Golden input schema memo

This document memoises the schema of the main golden input for the `design-extractor` subagent:
`golden_input.json` (exported from Figma via the "Export Design Raw JSON" plugin, page scope).

Capture date: 2026-08-24
Source file: `GoFood Group Order` / page `↪ MVP - Group Order [v5.46]`
Export metadata: `formatVersion: 2`, `nodeCount: 80797`, `truncatedCount: 0`

## Top-level envelope

```json
{
  "exportedAt": "2026-08-24T16:23:06.153Z",
  "scope": "page",
  "file": { "name": "GoFood Group Order", "page": "↪ MVP - Group Order [v5.46]" },
  "export": {
    "formatVersion": 2,
    "maxDepth": 30,
    "nodeCount": 80797,
    "truncatedCount": 0,
    "truncatedNodes": []
  },
  "nodes": [ { "type": "PAGE", ... } ]
}
```

| Field | Type | Meaning |
| :--- | :--- | :--- |
| `exportedAt` | string | ISO 8601 timestamp of the export. |
| `scope` | string | Always `"page"` for page exports. |
| `file.name` | string | Figma file name. |
| `file.page` | string | Page name; may contain unicode arrows and version tags. |
| `export.formatVersion` | int | Schema version. This skill targets `2`. |
| `export.maxDepth` | int | Maximum traversal depth used by the exporter. |
| `export.nodeCount` | int | Total nodes in the export. |
| `export.truncatedCount` | int | Nodes omitted due to depth limits. Must be `0` for full extraction. |
| `export.truncatedNodes` | array | Node ids of truncated nodes, normally empty. |
| `nodes` | array | Exactly one root `PAGE` node. |

## Node hierarchy

The export is a single rooted tree. All nodes share a core set of fields and add type-specific fields.

### Core fields (present on almost every node)

| Field | Type | Notes |
| :--- | :--- | :--- |
| `id` | string | Figma node id, e.g. `"13056:83189"`. |
| `name` | string | Layer name. Often generic (`"Section"`, `"Content"`) for atoms; semantic at group/section level. |
| `type` | string | Node type enum. |
| `x`, `y`, `width`, `height` | int | Bounding box in Figma canvas coordinates. Absent only on `PAGE`. |
| `children` | array | Nested child nodes. Absent on leaf nodes. |

### Node type census in the golden input

| Type | Count | Role |
| :--- | ---: | :--- |
| `FRAME` | 28,918 | Screens, containers, and most structural groups. |
| `INSTANCE` | 22,965 | Component instances, mostly design-system atoms. |
| `TEXT` | 19,779 | Label and body copy layers. |
| `GROUP` | 8,766 | Loose visual groups, often with semantic names. |
| `CONNECTOR` | 191 | Flow arrows between frames. |
| `RECTANGLE` | 139 | Decorative shapes / banners. |
| `SECTION` | 36 | Top-level Figma sections that partition the page. |
| `ELLIPSE` | 2 | Decorative. |
| `PAGE` | 1 | Root. |

### Type-specific fields

#### `SECTION`

Top-level page partitions. Some section names are empty strings; others are semantic such as `"Group Order - Booking & Post booking"` and `"Component spec"`.

Core fields only, plus `children`.

#### `FRAME`

Primary structural node. May contain `children` and optionally:

- `reactions` (array) — prototype interactions, see below. Present on 43 frames.
- `dashed` (boolean) — decorative stroke style. Present on 17 frames.

#### `INSTANCE`

Component instantiation. May contain `children` and optionally:

- `componentProperties` (object) — property bag with variant/config values.
- `variantProperties` (object) — flattened variant key/value map.
- `reactions` (array) — prototype interactions. Present on 181 instances.
- `dashed` (boolean) — rare.

Example `componentProperties`:

```json
{
  "Size": { "value": "Medium", "type": "VARIANT", "boundVariables": {} },
  "Type": { "value": "-", "type": "VARIANT", "boundVariables": {} }
}
```

Example `variantProperties`:

```json
{ "Size": "Medium", "Type": "-" }
```

#### `TEXT`

Leaf text layer.

| Field | Type | Notes |
| :--- | :--- | :--- |
| `characters` | string | Rendered text, may contain newlines. |

#### `CONNECTOR`

Flow arrow. Every connector has:

| Field | Type | Notes |
| :--- | :--- | :--- |
| `connectorStart` | object | `{ "endpointNodeId": "...", "magnet": "LEFT" }` |
| `connectorEnd` | object | `{ "endpointNodeId": "...", "magnet": "LEFT" }` |
| `connectorLineType` | string | e.g. `"ELBOWED"` |
| `connectorStartStrokeCap` | string | e.g. `"DIAMOND_FILLED"` |
| `connectorEndStrokeCap` | string | e.g. `"ARROW_LINES"` — direction indicator. |
| `text` | object | `{ "characters": "" }`. Non-empty on 24/191 connectors. |

Endpoint `magnet` values observed: `LEFT`, `RIGHT`, `TOP`, `BOTTOM`.

#### `GROUP`, `RECTANGLE`, `ELLIPSE`

Core geometry fields only, with `children` for `GROUP`.

### `reactions` prototype interaction

Observed on `FRAME` and `INSTANCE` nodes. Example:

```json
[
  {
    "action": {
      "type": "NODE",
      "destinationId": null
    },
    "trigger": { "type": "ON_CLICK" }
  }
]
```

Important: `destinationId` may be `null`. A `null` destination means the prototype destination was not exported or is unresolved, so the reaction should be treated as a `blocking_issue` rather than a fabricated edge.

**Fields actually consumed by the pipeline:**
- `trigger.type` — interaction trigger (defaults to `"ON_CLICK"` if absent)
- `action.type` — action type (defaults to `"NAVIGATE"` if absent)
- `action.destinationId` — target node id (`null` = unresolved)

## Conventions observed in the golden input

- Empty section names are common; semantic grouping must be inferred from position and child contents, not only section labels.
- Many frame and instance names are generic (`"Section"`, `"Content"`, `"Title"`). Semantic identity comes from the surrounding group/section context and the text content of descendant `TEXT` nodes.
- Connectors are sparse: only 191 edges across ~80k nodes. Most connectors carry no text label; flow conditions must come from nearby text chips or connector stroke caps when available.
- `formatVersion: 2` with geometry present. The skill should reject `formatVersion: 1` or exports with missing geometry.
