---
name: backend-test-code-generator
description: Generate GBT Java test code from the approved automation_plan.json using TapMind NLP conventions. Runs in parallel with test-data-generator. Produces Java test classes with fixture ID references (not hardcoded data). Output goes to test-code-validator before human review and MR raise.
---

# Backend Test Code Generator

Translate the automation plan into runnable GBT Java test classes. Runs in the **Code Lane** in parallel with test-data-generator (Data Lane).

## Reads

| File | Purpose |
|---|---|
| `automation_plan.json` (approved, dedup-flagged) | Test class structure, method specs, fixture IDs, curl references |
| `tasks_context.json` | Import paths, model class names, exact field names for request/response |
| `code_change_context.json` | Enum values, error code constants, response model shapes for assertions |

## Model
Fast tier — Haiku

## GBT Java conventions

**Class structure:**
```java
@GBTTest
@Feature("Feature Name")
public class PaymentComponentTest extends BaseGBTTest {
    @Autowired
    private TDPClient tdpClient;

    @Test
    @Story("SCN-003: Invalid amount validation")
    @Severity(SeverityLevel.CRITICAL)
    @Tags({@Tag("negative"), @Tag("boundary"), @Tag("P0")})
    public void shouldReturnInvalidAmountErrorWhenAmountExceedsLimit() { ... }
}
```

**TapMind NLP steps (exactly 3 per method):**
```java
@Step("Given a user with an active account and sufficient balance")
@Step("When POST /v2/payments is called with amount = 10000001")
@Step("Then response status is 422 and error_code is INVALID_AMOUNT")
```
- "When" step derives from `curl_reference` — the API endpoint call, not a UI action.
- "Given" step derives from `required_state` in automation_plan.
- "Then" step derives from `expected_result` in sdet_plan scenario step_descriptions.

**Fixture ID reference pattern (no hardcoded IDs):**
```java
String userId = tdpClient.resolve("FIX-PAYMENT-001", "user_ref_1");
String accountId = tdpClient.resolve("FIX-PAYMENT-001", "account_ref_1");
```

**Assertion pattern (use enum constants, never hardcode string error codes):**
```java
assertThat(response.getStatus()).isEqualTo(422);
assertThat(response.getErrorCode()).isEqualTo(PaymentErrorCode.INVALID_AMOUNT);
```

## Generation rules
- Skip methods where `is_dedup: true` in automation_plan.json.
- One Java file per test class; method order within class: P0 first, then P1, then P2.
- All imports must be resolvable from tasks_context package paths — do not invent package names.
- Enum constants and error codes from tasks_context / code_change_context `new_enums` — never hardcode strings.
- Feature flags: `flag_on` tag → `@FeatureFlag("flag_name", enabled = true)`; `flag_off` → `enabled = false`.
- One scenario = one test method = one assertion focus. Do not add logic beyond what the scenario specifies.

## Output format
- One `.java` file per test class: `generated-tests/src/test/java/{package_path}/{ClassName}.java`
- `generation_manifest.json` listing all generated files with `class_name`, `file_path`, `method_count`, `scenario_ids[]`

## Output flow
Output goes directly to `test-code-validator` — do not present to humans yet.

## Log
N classes generated, N methods, N methods skipped (dedup).
