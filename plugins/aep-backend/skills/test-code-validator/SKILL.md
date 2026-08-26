---
name: backend-test-code-validator
description: Validate generated GBT Java test code before human review. Checks naming conventions, GBT annotation completeness, TapMind NLP step structure, fixture reference patterns, import validity, and compile verification. Does NOT execute tests — runtime execution is Phase B CI. Outputs validation_report.json.
---

# Backend Test Code Validator

Structural and compile checks on generated test code before the SDET review gate. Errors caught here are far cheaper than discovering them in CI.

## Reads

| File | Purpose |
|---|---|
| `generated-tests/` directory | Java files from test-code-generator |
| `generation_manifest.json` | List of expected files |
| `automation_plan.json` | Source of truth for expected class/method structure |
| `tasks_context.json` | Valid package paths and import targets |

## Model
Fast tier — Haiku

## Checks

| Check | Criteria |
|---|---|
| Naming convention | Class: `[Feature][Layer]Test`; Method: `should[Outcome]When[Condition]` camelCase, no underscores; File name matches class name exactly |
| GBT annotation completeness | Class: `@GBTTest`, `@Feature("...")`, extends `BaseGBTTest`. Method: `@Test`, `@Story("SCN-XXX: ...")`, `@Severity(SeverityLevel.X)`, `@Tags(...)` |
| TapMind NLP steps | Exactly 3 `@Step` annotations per method: one "Given", one "When", one "Then". "When" must reference the API endpoint from `curl_reference`. |
| Fixture references | No hardcoded entity IDs (UUIDs, numeric IDs in setup). All `tdpClient.resolve(fixture_id, ref_id)` calls use IDs existing in `test_data_requests.json`. |
| Import validity | All imports resolvable from tasks_context package paths. Error code constants from correct enum class (code_change_context new_enums). No invented package names. |
| Compile | `javac` dry-run — capture per-file errors on failure |
| Coverage completeness | Every `automation_plan.json` method with `is_dedup: false` must have a generated method — flag missing methods |
| One endpoint per test class | Every method added to an existing test class must target the same HTTP method + path that class already tests. A method whose endpoint differs → **FAIL**, remediation: new test class in the same package, named for that endpoint. Resolve each method's endpoint via the controller/client/endpoint chain it calls, not by name |
| Environment-specific constants | Any new `public static final String` holding a provisioned entity id (restaurant/merchant/customer/group/offer/voucher/outlet) added to a shared constants class → **FAIL** if that feature area has an `I<Domain>Constants` + `<Domain>Constants{Qa,Int,Uat}` family. Exempt: enum/protocol literals, locale/country/app-version headers, and deliberately-invalid ids. Also **FAIL** a getter added to the interface without an implementation in *every* environment class, and **WARN** on `DUMMY_`/`TODO_` in a public constant name |
| Request-chain completeness | When a diff adds a field to an existing request DTO, check the rest of the chain. **FAIL** if no body-builder method can set it. **FAIL** if a `*Failure` controller method is called with an expected status different from the one it pins. **WARN** if `@JsonInclude(NON_NULL)` is absent on a DTO that gained an optional field and has pre-existing callers. **WARN** if `@Builder` was moved from the class onto a constructor |
| Shared assertion mutation | **WARN** when an assertion is added to a `static assert*` helper that has callers outside the files in this change — list every caller so the reviewer can confirm it holds for each |

**Severity mapping:** P0 → `SeverityLevel.CRITICAL`, P1 → `NORMAL`, P2 → `MINOR`

**Scope — NOT checked here:**
- Runtime test execution (Phase B CI)
- Assertion logic correctness (human review)
- Test data validity (TDP at runtime)

## Output → validation_report.json

Schema root structure:
- `validation_date` (ISO8601), `overall_status: PASS|FAIL|WARN`
- `files_checked`, `files_passed`, `files_with_warnings`, `files_with_errors`
- `results[]` — per file: `file`, `status`, `checks[]` (each with `check`, `status`, `detail`), `missing_methods[]`
- `coverage_check` — `expected_methods`, `generated_methods`, `missing[]`

## Severity levels

| Status | Meaning | Blocks human review? |
|---|---|---|
| `FAIL` | Must be fixed before human review | Yes |
| `WARN` | Reviewer should be aware; can proceed | No |
| `PASS` | No issues | No |

If any file has overall `FAIL`: surface blocking issues clearly before any other output. Notify SDET with the report.

**Inline annotations:** Add `// VALIDATOR: [check] [detail]` comments to Java files for each FAIL/WARN.

## Validate
`jsonschema.validate(output, schemas/validation_report.schema.json)`

## Log
Overall status, N files checked, N failed, N warned. If overall FAIL, list blocking issues first.
