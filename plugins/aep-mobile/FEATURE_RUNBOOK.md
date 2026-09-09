# QA / Test Generation Skill Pipeline — Onboarding & Feature Runbook

**Audience:** PICs setting up and running the AEP QA test-generation pipeline  
**Scope:** Frontend (mobile) and Backend workflows via Claude Code and Cursor  
**Repo / Marketplace:** https://source.golabs.io/aep/skills.git  
**Plugin version (mobile):** `aep-mobile` **0.13.2+**

### Pipeline at a glance

| Phase | When | What you type |
|---|---|---|
| **Pre-build** | Before any APK | `/mobile-sdet-plan-generator` |
| **Post-build** | APK / MRs exist | `/mobile-test-code-gen` |

Mobile exposes **only these two** user-facing `/command`s. Extractors, setup, regression, and test-data provisioning run as **agents inside** those commands — they are not separate slash skills.

```
PRE-BUILD
  /mobile-sdet-plan-generator
    setup → parallel: prd / rfc / design / task extractors
        │
        ▼
    human scope + category confirm
        │
        ▼
    sdet-plan-runner
      ├─ regression-extractor   ← after PRD/RFC (not a PIC /command)
      └─ → SDET_plan.json + analysis.md + test_cases.csv
        │
   ── HUMAN REVIEW GATE (CSV edits → SYNC) ──
        ▼
POST-BUILD
  /mobile-test-code-gen
    code-change → impact-shortlist → test-code
         └─ test-data-provisioner (agent, not a /command)
```

Frontend and backend each use **their own working folder** (`…_frontend` and `…_backend`). Open the one you are running. The RFC is a different file on each side.

---

## 1. Overview

This runbook walks a PIC through:

1. One-time environment setup (per person)
2. One-time feature-folder preparation (per feature)
3. Pre-build pipeline (one command → extractors + SDET plan → human gate → CSV SYNC to BrowserStack)
4. Post-build pipeline after the APK exists (one command → code-change → impact shortlist → test-code)

---

## 2. One-Time Environment Setup (per person)

### 2.1 Install prerequisites

- Claude Code and/or Cursor Desktop
- `python3` + `jsonschema` (needed by SDET validation scripts)
- Network access to the AEP skills marketplace and BrowserStack

### 2.2 Install the plugin marketplace

Run in a terminal:

```bash
claude plugin marketplace add https://source.golabs.io/aep/skills.git
claude plugin install aep-mobile@aep
claude plugin install aep-backend@aep
```

**Important:** Quit Claude Code fully and reopen it — skills load only on restart.

**Cursor:** Install the same marketplace plugin, or symlink/copy `plugins/aep-mobile/skills/` into the project’s `.cursor/skills/` or `~/.cursor/skills/`. Restart Cursor after install.

### 2.3 Hook up BrowserStack

1. Get your username + access key from:  
   https://www.browserstack.com/accounts/settings
2. Add the BrowserStack MCP server:
   - **Claude Code:** edit `~/.claude.json` → `mcpServers`
   - **Cursor:** Settings → MCP, or `~/.cursor/mcp.json`

```json
{
  "mcpServers": {
    "browserstack": {
      "command": "npx",
      "args": ["-y", "@browserstack/mcp-server@latest"],
      "env": {
        "BROWSERSTACK_USERNAME": "<your-username>",
        "BROWSERSTACK_ACCESS_KEY": "<your-access-key>"
      }
    }
  }
}
```

3. Restart Claude Code / Cursor once more.

**Backend only:** additional one-time setup applies (GBT clone, TestBuddy, GitLab token). Fill per backend PIC guidance.

### 2.4 Verify setup

In Claude Code or Cursor chat, paste:

> Run aep-mobile-setup and tell me what is missing.

That routes through **`/mobile-sdet-plan-generator`**, which runs the setup agent and **stops** after the preflight table.

**Gate:** Do not generate a plan until the following are green for a full GENERATE:

- `python3`
- `jsonschema`
- the SDET scripts
- the BrowserStack MCP (required for regression pull + BrowserStack upload; extractors can still run without it)

### 2.5 Update the plugins later

Nothing updates by itself unless marketplace auto-update is on. When AEP ships a new skill version:

```bash
claude plugin marketplace update aep
claude plugin update aep-mobile@aep
claude plugin update aep-backend@aep
```

Then quit Claude Code fully and reopen it. The version number can change immediately; skill content only loads on the next session.

In the desktop app you can type the same commands in the message box. In Cursor, refresh/reinstall the plugin and restart.

**BACKEND PIC** — fill any extra update step for backend (GBT clone pull, etc.).

---

## 3. Every-New-Feature Preparation

### 3.1 Create the working folder

Create two folders (lowercase, underscores). Put files in the **folder root**. Example:

```text
/Users/<you>/qa-runs/gofood_save_group_m5_frontend/
/Users/<you>/qa-runs/gofood_save_group_m5_backend/
```

### 3.2 Put files in the folder root (no subfolders)

Do **not** create `prd/`, `rfc/`, `design/`, or `tasks/` subfolders.

| Track | Put in folder root |
|---|---|
| **Frontend** | `PRD.pdf` (or similarly named PRD), frontend RFC (if any), `figma_export.json`, and `task_input.json` only if task-generation already produced it |
| **Backend** | Same PRD copy is fine, the **backend** RFC (different from frontend), plus any extra files the backend PIC names (`TASKS.md`, OpenAPI, …) |

### 3.3 Open the folder as the working directory

In Claude Code: **File → Open folder** → select the frontend folder (or the backend folder when you run backend). Skills write outputs in that same folder.

Do **not** open the `aep/skills` plugin repo as the working folder.

### 3.5 Export Figma (frontend)

1. Open the Ready for Development page (not exploration).
2. Select the page, or only this milestone’s screens.
3. Run the plugin **Export Design Raw JSON**.
4. Save as `figma_export.json` in the frontend folder.
5. Validate the file — it must contain `exportedAt`, `formatVersion: 2`, `truncatedCount: 0`, and a `nodes` value.

**Way 2 — API** (fallback; prefer Way 1 if design-extractor rejects a REST dump):

```bash
export FIGMA_TOKEN="<your-figma-token>"
curl --request GET \
  --url "https://api.figma.com/v1/files/<FILE_KEY>/nodes?ids=<NODE_ID>" \
  --header "X-Figma-Token: ${FIGMA_TOKEN}" \
  -o figma_export.json
```

File key and node id come from the Figma URL (`node-id=6703-72195` → `6703:72195`).

### 3.6 Export tasks

- If task-generation produced `task_input.json` → drop it in the frontend folder.
- If not → skip task extraction (the orchestrator will skip the task agent automatically).

---

## 4. Pre-build (before any APK)

All of section 4 happens **before** the APK exists. BrowserStack MCP must stay connected for GENERATE / SYNC. Do **not** run `/mobile-test-code-gen` yet.

### 4.1 Run `/mobile-sdet-plan-generator` (one command)

Type `/` and pick **`mobile-sdet-plan-generator`**.

You do **not** run separate `/mobile-prd-extractor`, `/mobile-rfc-extractor`, `/mobile-design-extractor`, or `/mobile-task-extractor` skills anymore. Put inputs in the folder (or attach them), then run the one command.

What it does:

1. **Setup** — dependency preflight table  
2. **Parallel extractors** (only for inputs that are present; skips the rest):
   - PRD → `prd_context.json` (or `prd_context.<app_id>.json` if multi-app)
   - RFC → `rfc_context.json` (skip if no frontend RFC)
   - Design → `design_context.json` (from `figma_export.json`)
   - Tasks → `task_context.json` (skip if no `task_input.json`)
3. **Human scope prompts** in the same chat (app / team / milestone / categories)
4. **`sdet-plan-runner`** — pulls regression via BrowserStack **internally**, then GENERATE

Creates:

- `<feature_key>_SDET_plan.json`
- `<feature_key>_analysis.md` (open questions)
- `<feature_key>_test_cases.csv`

**Setup-only** (no plan):

> Run aep-mobile-setup and tell me what is missing.

**Extract-only** (no plan yet): ask to extract contexts / attach inputs and say you only want extraction — the skill stops after the extractor table.

If a design render HTML was created, open it next to Figma. Wrong screens or arrows → follow **§4.3** (new `figma_export.json`, delete `design_context.json`, re-run `/mobile-sdet-plan-generator`). Do **not** edit `design_context.json` by hand.

### 4.2 Human gate (mandatory, after the first SDET plan)

**Who:** SDET + feature lead. Bring PM / Design / Eng only for questions they own.

1. Review `<feature_key>_analysis.md`. Read Inputs & Open Points, Blocked — Awaiting PM/Design, Blocked — Awaiting Dev, coverage gaps, and `[NAVIGATION NOT CONFIRMED]`.
2. Resolve every open question / open point. Get answers. Update the **source docs** (PRD, RFC, Figma, tasks) — not the JSON by hand.
3. If any source doc changed, follow **§4.3**, then re-run **`/mobile-sdet-plan-generator`** (GENERATE). Repeat until the analysis has no blocking `NEEDS_ANSWER` items you still owe. FYI notes can stay.
4. Review `<feature_key>_test_cases.csv`. Add, drop, or edit titles / steps / priority / execution mode. Do **not** import this CSV into BrowserStack yourself.
5. Give the updated CSV back for **SYNC**. Type **`/mobile-sdet-plan-generator`** and attach the edited `<feature_key>_test_cases.csv`. Leave the CSV in the same frontend folder.

The skill merges your CSV edits into `<feature_key>_SDET_plan.json`, uploads only **new** cases to BrowserStack (`is_legacy_regression = false`; it does not re-upload legacy cases), stamps BrowserStack ids onto the plan, and writes `<feature_key>_automation_plan_generator.json` (automatable scenarios + BS case ids) for later test-code gen.

**Pre-build is done when:** the analysis is accepted, the CSV is accepted, new cases are in BrowserStack, and `*_automation_plan_generator.json` exists. Wait for the APK.

**BACKEND PIC** — fill the same human-gate loop for backend: review `*_qa_analysis.md` / backend analysis, update PRD/RFC/tasks, re-run only changed backend extractors / plan skill, edit the CSV, return the CSV for BrowserStack upload. All of this is still pre-build. Open the **backend** folder.

### 4.3 When PRD / RFC / design / tasks are updated

Use this whenever a **source doc** changes after you already have context files (and usually a first SDET plan). Do **not** hand-edit any `*_context.json`.

**PIC steps**

1. In the working folder, **replace only the updated source file(s)** with the new version (PRD, RFC, `figma_export.json`, and/or `task_input.json`). Leave unchanged source files alone.
2. For each source you replaced, **delete its matching context file** (delete only — do not create or paste a new context). Leave other context files as they are.
3. Re-run **`/mobile-sdet-plan-generator`** (GENERATE, not SYNC).

The skill sees which `*_context.json` files are **missing**, re-runs **only those extractors**, and keeps the other contexts on disk. Same rule if several docs changed: replace those sources, delete those contexts, re-run once.

| Source you replaced | Delete this context (leave others) |
|---|---|
| PRD | `prd_context.json` and any `prd_context.<app_id>.json` |
| RFC | `rfc_context.json` (and `rfc_context.<app_id>.json` if present) |
| Design (`figma_export.json`) | `design_context.json` |
| Tasks (`task_input.json`) | `task_context.json` |

**Do not** delete context files for sources that did not change — if the context is still present, the skill skips that extractor.

After GENERATE, review analysis + CSV again (§4.2). Use SYNC only when you are returning an edited CSV for BrowserStack upload / automation-plan JSON.

### 4.7 Post-build (APK / MRs exist)

Run this only after an Android/iOS build (or equivalent) exists and MRs are up. Still use the **frontend** folder as the working directory.

#### Run `/mobile-test-code-gen` (one command)

You do **not** run separate `/mobile-code-change-extractor`, `/mobile-impact-shortlister`, `/mobile-test-code-generator`, or `/mobile-test-data-provisioner` skills anymore.

Preconditions in the folder (or from the user):

- Approved plan: `*_automation_plan_generator.json` (preferred) or `*SDET_plan.json`
- What landed: `dev_manifest.json` (preferred) or GitLab MR refs for the EPIC
- Optional but useful: `regression_context.json`, `design_context.json`

Type `/` and pick **`mobile-test-code-gen`**. It runs **sequentially**:

| Step | Agent (internal) | Creates |
|---|---|---|
| 1 | code-change-extractor | `change_context.json`, `compliance.json` |
| 2 | impact-shortlister | `impact_shortlist.json` (which legacy BS cases must still run; does not invent new cases) |
| 3 | test-code-generator | TapMind NLP (default) + GMT Java where needed; `test-code-generator.json` + test files |

`test-data-provisioner` is spawned **by** test-code-generator when fixtures are needed (TestBuddy handles, never raw accounts). PICs do not call it as a `/command`.

If `compliance.json` / id compliance is **FAIL**, stop — eng must bind missing locators/deeplinks, then re-run **`/mobile-test-code-gen`** (or ask it to redo the code-change step). Defer a case rather than guessing a locator or nav path. New automatable scenarios only (`is_legacy_regression = false`).

**BACKEND PIC** — fill post-build: when the service is QA-ready, run your code-change / Pass 2 plan / automation-plan / test-data / GBT test-code / validator / MR. Open the **backend** folder. Do not use the frontend folder.

---

## 5. Working Folder Layout

Use this layout everywhere. Files sit at the **folder root**. Frontend and backend are two different folders.

```text
/Users/<you>/qa-runs/gofood_save_group_m5_frontend/
  PRD.pdf
  <frontend-rfc>.md          # optional
  figma_export.json
  task_input.json            # optional
  # outputs (examples):
  prd_context.json
  design_context.json
  rfc_context.json
  task_context.json
  regression_context.json    # written by the plan runner, not by you
  <feature_key>_SDET_plan.json
  <feature_key>_analysis.md
  <feature_key>_test_cases.csv
  <feature_key>_automation_plan_generator.json
  change_context.json        # post-build
  compliance.json
  impact_shortlist.json
  test-code-generator.json

/Users/<you>/qa-runs/gofood_save_group_m5_backend/
  PRD.pdf
  <backend-rfc>.md
  # … backend-specific inputs / outputs
```

Frontend and backend do **not** share a folder. Open the folder for the track you are running.

---

## 6. Input Checklist

| Input | Frontend | Backend | Notes |
|---|---|---|---|
| PRD | Required for plan | Required for plan | Same copy OK across tracks |
| RFC | Optional but recommended | Required (backend RFC) | Different files per track |
| Figma export | Required for design-driven UI | N/A | `formatVersion: 2` plugin export preferred |
| `task_input.json` | Optional | Per backend PIC | Skip agent if absent |
| BrowserStack MCP | Required for GENERATE/SYNC | Per backend | Plan stops without it on GENERATE |
| `dev_manifest.json` / MR refs | Required for post-build | Per backend | Prefer manifest |
| `*_automation_plan_generator.json` | Required for post-build | Per backend | From SYNC |

---

## 7. Behavior After Extraction / Plan

- **PARTIAL** is normal. Read `extraction_notes`. Do not invent missing facts in the JSON.
- The SDET plan needs `prd_context.json` + `design_context.json`; `rfc_context.json` and tasks are helpful but optional on frontend.
- The plan skill fetches existing BrowserStack cases itself (via the regression agent inside the runner). If MCP is down on GENERATE, stop — do not generate (you will duplicate old cases).
- Two apps in one PRD → run the SDET plan once per app (or as the skill prompts). Several teams/milestones → pick one per run.
- First run of `/mobile-sdet-plan-generator` = **GENERATE**. Attach an edited CSV = **SYNC** (upload + automation-plan JSON).

---

## 8. Troubleshooting

| Problem | Fix |
|---|---|
| Skills not listed / old behaviour (many extractor `/` skills) | `claude plugin marketplace update aep` then `claude plugin update aep-mobile@aep` (and backend). Quit and reopen. Expect only `/mobile-sdet-plan-generator` and `/mobile-test-code-gen` for mobile. Version **0.13.2+**. |
| Setup fails (python3 / jsonschema) | Install them; re-run setup-only prompt |
| BrowserStack MCP down on GENERATE | Fix MCP; do not generate without it |
| Design looks wrong | Fix Figma → re-export → follow §4.3 (replace `figma_export.json`, delete `design_context.json`) → re-run `/mobile-sdet-plan-generator`. Do not hand-edit `design_context.json` |
| PRD / RFC / design / tasks updated | Follow §4.3: replace source(s), delete matching context(s) only, re-run `/mobile-sdet-plan-generator` |
| id / locator compliance FAIL | Eng binds locators/deeplinks; re-run `/mobile-test-code-gen` |
| Want only extraction, not a plan | Ask `/mobile-sdet-plan-generator` to extract only; it stops after the extractor table |
| Cursor still shows old skills | Refresh/reinstall plugin; restart Cursor; confirm plugin version ≥ 0.13.2 |

---

## 9. Skill & Agent Reference

### Frontend — user-facing commands (only these)

| Command | Phase | What it does |
|---|---|---|
| `/mobile-sdet-plan-generator` | Pre-build | Setup + parallel extractors + human-gated SDET plan (GENERATE → review → SYNC) |
| `/mobile-test-code-gen` | Post-build | Sequential code-change → impact-shortlist → test-code (TDP agent inside) |

### Frontend — agents (not `/` commands; do not teach PICs to type these)

| Agent | Called by | Role |
|---|---|---|
| `aep-mobile-setup` / setup | `/mobile-sdet-plan-generator` | Dependency preflight |
| `prd-extractor` | `/mobile-sdet-plan-generator` | `prd_context.json` |
| `rfc-extractor` | `/mobile-sdet-plan-generator` | `rfc_context.json` |
| `design-extractor` | `/mobile-sdet-plan-generator` | `design_context.json` |
| `task-extractor` | `/mobile-sdet-plan-generator` | `task_context.json` |
| `sdet-plan-runner` | `/mobile-sdet-plan-generator` | GENERATE / SYNC computation |
| `regression-extractor` | `sdet-plan-runner` (not parallel with other extractors) | `regression_context.json` from BrowserStack |
| `code-change-extractor` | `/mobile-test-code-gen` | `change_context.json`, `compliance.json` |
| `impact-shortlister` | `/mobile-test-code-gen` | `impact_shortlist.json` |
| `test-code-generator` | `/mobile-test-code-gen` | NLP + GMT artefacts |
| `test-data-provisioner` | `test-code-generator` | TestBuddy handles (never raw secrets) |

### Removed as PIC `/` skills (do not document these as commands)

`/mobile-prd-extractor` · `/mobile-rfc-extractor` · `/mobile-design-extractor` · `/mobile-task-extractor` · `/aep-mobile-setup` (as a standalone skill) · `/mobile-code-change-extractor` · `/mobile-impact-shortlister` · `/mobile-test-code-generator` · `/mobile-test-data-provisioner` · `/mobile-code-gen` (renamed to `/mobile-test-code-gen`)

Natural-language still works, e.g.:

- *“Extract the PRD context for this mobile feature”* → `/mobile-sdet-plan-generator`
- *“Generate the SDET plan”* → `/mobile-sdet-plan-generator`
- *“The build is in — generate the tests”* → `/mobile-test-code-gen`

### Backend (unchanged shape — fill exact skill names per backend PIC)

**Pre-build (backend folder):** `/backend-prd-extractor` · `/backend-rfc-extractor` · `/backend-tasks-extractor` · `/backend-regression-extractor` · `/backend-sdet-plan-generator` → review analysis → update sources → re-run changed extractors → re-run plan → edit CSV → return CSV for BrowserStack upload.

**Post-build (backend folder, after the service is QA-ready):** code-change / Pass 2 · automation-plan · test-data · test-code · validator · MR. Name the exact `/` skills and output files.

Open the backend folder. Use the backend RFC.

---

## 10. Version & layout notes (for maintainers)

| Item | Current |
|---|---|
| Mobile plugin version | `0.13.2` in `.claude-plugin/plugin.json` and `.cursor-plugin/plugin.json` |
| Agent instruction bodies | `plugins/aep-mobile/agents/` (source of truth + Claude model pins) |
| Cursor model-pin stubs | `plugins/aep-mobile/cursor-agent-stubs/` (load bodies from `agents/`) |
| Copilot | Not wired yet |

Edit agent **logic** only in `agents/`. Touch `cursor-agent-stubs/` only when adding an agent or changing a Cursor model pin.
