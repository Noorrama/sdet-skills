---
name: mobile-regression-extractor
description: Dynamically fetches existing active regression test cases from BrowserStack Test Management for a given feature_key, app_id, or module_namespace using the BrowserStack MCP Server.
---

# Mobile Regression Extractor

## Purpose
Bridges the test generation pipeline and the BrowserStack Test Management database. It executes during the pre-build ingest phase of the `sdet-plan-generator` to query and retrieve currently documented active regression cases, ensuring that newly authored test plans never duplicate existing coverage.

---

## Input Contracts

Receives search metadata extracted from the core contexts:
* **`app_id`**: The target app (e.g., `gojek-driver`, `gojek-consumer`).
* **`feature_key`**: The specific feature being planned (e.g., `OneKYC`).
* **`module_namespace`**: The active sub-system/module (e.g., `Onboarding`).

---

## Execution Workflow

### 1. Match Project and Execute BrowserStack Query (via MCP)
- Establish connection to the **BrowserStack MCP Server** (relying on client-configured OAuth or credentials).
- **Retrieve and Map Project:** First, query the BrowserStack MCP server to list or identify all active Test Management projects in your workspace. Map the local `app_id` (e.g., `gojek-driver`) or display name to its corresponding BrowserStack `project_identifier` (e.g. `PR-xxxxx`).
- **Fetch Folder Hierarchy (Optional):** If a `module_namespace` is provided, query folders using the `listFolders` tool to find the folder ID corresponding to the target module.
- **Fetch Test Cases:** Invoke the **`listTestCases`** tool with the mapped `project_identifier` (and folder ID if resolved), passing the extracted `feature_key` and `module_namespace` as filters/tags.

### 2. Format Output (`regression_context.json`)
Consolidate the retrieved test cases into a structured JSON payload. Each retrieved case object must include:
* **`id`**: BrowserStack unique testcase ID (e.g., `BS-TC-5921`).
* **`title`**: The exact title of the existing test case.
* **`status`**: Current state in BrowserStack (e.g., `Active`, `Draft`).
* **`priority`**: Severity tier (`P0`, `P1`, `P2`).
* **`is_automated`**: Boolean (`true`/`false`) reflecting whether it is already automated.
* **`steps`**: The list of text-based execution steps.
* **`preconditions`**: Extracted environment or configuration requirements.

---

## Guardrails
- **No Hallucinations:** Only return test cases actually returned by the BrowserStack MCP tool. If the query yields zero results, return an empty scenario array `[]` (never invent mock regression tests).
- **Secure Credentials:** Never attempt to prompt for, read, or print BrowserStack API tokens. All authorization is handled securely at the client-mcp level.
