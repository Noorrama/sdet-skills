# GitLab pipeline — Agentic_nlp_tests (generic jobs)

After codegen and MR push, offer **once** to trigger a pipeline on the MR
branch. Do not poll; return only the pipeline URL.

## Jobs (tapmind-mobile-tests)

| Job | Platform |
|---|---|
| `agentic_nlp_release_android` | Consumer Android |
| `agentic_nlp_release_ios` | Consumer iOS |

Defined in `.gitlab/ci_configurations/.tapmind-agentic-nlp-release.yml` (not
per-module YAML). App download uses existing `download_gojek_android_app` /
`download_gojek_ios_app`.

## Required trigger variables

| Variable | Example | Notes |
|---|---|---|
| `ref` | `feat/gofood-release-nlp-agentic` | MR branch |
| `TAG` | `Agentic_nlp_tests` | TestNG group on emitted methods |
| `MODULE` | `gofood` | Gradle module (`settings.gradle`) |
| `TAPMIND_CONFIG` | `gofood_android.json` | File under module dir |
| `APP_TYPE` | `gojek-android` or `gojek-ios` | Selects download + test job |
| `INFRA` | `qa` | Same as other consumer jobs |

Optional: `BS_PROJECT_ID`, `AGENTIC_LARK_CHANNEL`, `REPORT_TO_TESTRAIL`,
`EXISTING_TEST_PLAN`.

## MCP (GitLab)

Use `gitlab_manage_pipeline` with action **create** (or equivalent) on project
`aep/tapmind-mobile-tests`, `ref` = branch, and variables above.

Example Android trigger for GoFood booking release on branch
`feat/gofood-release-nlp-agentic`:

```
TAG=Agentic_nlp_tests
MODULE=gofood
TAPMIND_CONFIG=gofood_android.json
APP_TYPE=gojek-android
INFRA=qa
BS_PROJECT_ID=2880292
```

Run iOS in a separate pipeline with `APP_TYPE=gojek-ios` and
`TAPMIND_CONFIG=gofood_ios.json`.

## Module config map (common)

| MODULE | Android config | iOS config |
|---|---|---|
| gofood | gofood_android.json | gofood_ios.json |
| customer-platforms | customerplatform_android.json | customerplatform_ios.json |
| transport | transport_android.json | transport_ios.json |
| cartography | cartography_android.json | cartography_ios.json |

When unsure, list `*android*.json` under the module directory.
