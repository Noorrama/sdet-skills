# GitLab pipeline — Agentic_nlp_tests (agentic codegen)

After codegen and MR push (§7), offer **once** to trigger pipelines on the MR
branch. Do not poll; return pipeline URLs only.

Same jobs as release — group **`Agentic_nlp_tests`** on skill-emitted methods.

## Jobs (`tapmind-mobile-tests`)

| Job | Platform |
|---|---|
| `agentic_nlp_release_android` | Consumer Android |
| `agentic_nlp_release_ios` | Consumer iOS |

Defined in `.gitlab/ci_configurations/.tapmind-agentic-nlp-release.yml`.

## Trigger variables

| Variable | Example | Notes |
|---|---|---|
| `ref` | `feat/pam_8_levels-nlp` | MR branch from §7 |
| `TAG` | `Agentic_nlp_tests` | TestNG group on emitted methods |
| `MODULE` | `driverApp` / `gofood` | Gradle module |
| `TAPMIND_CONFIG` | `gofood_android.json` | Under module dir |
| `APP_TYPE` | `gojek-android` or `gojek-ios` | |
| `INFRA` | `qa` | |

Optional: `BS_PROJECT_ID`, `AGENTIC_LARK_CHANNEL`, `REPORT_TO_TESTRAIL`.

Use **GitLab MCP** `gitlab_manage_pipeline` (create) on `aep/tapmind-mobile-tests`.

Run Android and iOS in **separate** pipelines when both platforms are in scope.

## Module config map (common)

| MODULE | Android | iOS |
|---|---|---|
| gofood | gofood_android.json | gofood_ios.json |
| driverApp | (module’s `*_android.json`) | (module’s `*_ios.json`) |
| transport | transport_android.json | transport_ios.json |
| cartography | cartography_android.json | cartography_ios.json |

When unsure, list `*android*.json` under the module directory.

## Finalise

After successful runs, user may **finalise** — [finalise-mr.md](finalise-mr.md).
Keep pipeline URLs from this step for the verification table.
