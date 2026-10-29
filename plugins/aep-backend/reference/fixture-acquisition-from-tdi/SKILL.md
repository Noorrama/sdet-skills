# Fixture acquisition from TDI (`test_data_output`)

**Applies to every GBT module** that codegen targets via a `reference/module-writers/*-api-test-writer/SKILL.md`.
`gbt-test-code-generator` rule 18 is the orchestration summary; **this file + the module writer** are
the mechanism source of truth.

## Inputs (on each `automation_plan.automation_scenarios[].test_data[]` entry)

After **test-data-identification**, each fixture carries `test_data_output[]` with at least
`test_data_status`, `test_data_details`, and often `test_buddy_prompt`.

## Universal routing

| `test_data_status` | Codegen must emit |
|---|---|
| `TDP_SUPPORTED` | **Test data pool** for the **target module** — map `tdp_test_data_category` to the pool API/helpers siblings already use. **Do not** call `TDP2Controller` when the fixture is fully pool-covered. |
| `TESTBUDDY_SUPPORTED` · `TESTBUDDY_OPERATION_FALLBACK` | When `test_buddy_prompt` ≠ null: **TestBuddy NLP via TDP2** (below). When null: `TODO(agent-pm)`. |
| `TESTBUDDY_HYBRID_FALLBACK` | Pool step when `tdp_test_data_category` is set, then TDP2 when `test_buddy_prompt` ≠ null. |
| `TDP_PARTIAL` | Pool and/or TDP2 for the served portion; `TODO(agent-pm)` for gaps in manifest. |
| `TDP_NOT_SUPPORTED` | Placeholder + `TODO(agent-pm)` — no silent class-default entity. |

Legacy status `TDP_OPERATION_FALLBACK` → treat as `TESTBUDDY_OPERATION_FALLBACK`.

## TestBuddy NLP (all modules that use `testdatapool.tdp2`)

When status is `TESTBUDDY_*` and `test_buddy_prompt` is non-null:

```java
TDP2Request req = new TDP2Request();
req.setMessage(<verbatim test_buddy_prompt>);
req.setClient(<module client string — see table below>);
req.setConversationId(<per sibling pattern — UUID or fixed label>);
TDP2Response response = TDP2Controller.getTDP2Response(req);
// Bind response → Customer/Driver/Merchant fields the test uses
```

- **Never** paraphrase `test_buddy_prompt`.
- **Never** leave `getTDP2Response` unused — bind ids/tokens into the same objects the scenario's API calls use.
- Prefer an existing **helper** in the module (e.g. `TDP2Helper.createAndLoginCustomer`) when siblings do; pass the plan prompt as the `message` argument.
- **`test_buddy_prompt` is not a Java comment** for `TESTBUDDY_*` statuses.

## Module pool vs TDP2 (`client` string)

Codegen **must** open the target module's writer and copy a **sibling test** in the same feature area.
This table is an index — writers may add detail or overrides.

| Module | `TDP_SUPPORTED` — typical pool mechanism | `TESTBUDDY_*` — TDP2 `client` / helper |
|---|---|---|
| **gofood** | `foodTestDataController.setAEPPoolCustomer(CustomerType.…)`; `@FoodTestDataManager` | `"GoFood"`; `TDP2Controller` or `GoFoodTestBase.topUpCustomer` pattern |
| **gofood** (gRPC) | Same pool as REST in base class | Same TDP2 as REST |
| **transport** | `RSCustomerPool` borrow/return via `RHSBorrowManager` | `tests.testutils.TDP2Helper` (`client` = `"cartography"`) or `"transport"` in e2e tests |
| **driver-platform** | `BookingHelper.getDriverFromTestDataPool` / `getCustomerFromTestDataPool`; `TestDataPoolController.getTestData` | Use TDP2 only if a sibling in `driver-platform` already does; else helper in `testdatapool` with `Client` / requesting module `"DriverPlatform"` on pool calls |
| **marketplace** | `TestDataPoolHandler` on `MarketplaceTestBase` | TDP2 if siblings use it; else pool + `TODO` |
| **driver-incentives** | Same family as marketplace (`TestDataPoolHandler`) | Same |
| **customer-platforms** | `TestDataPoolCP`, `TestDataPoolController.getCustomersFromTestDataPoolUsingRequestingModule(..., "customer-platforms")` | TDP2 if siblings use it |
| **go-logistics** | `RSCustomerPool.getCustomerFromAEPTestDataPool` / `RSDriverPool.getDriverFromAEPTestDataPool` with requesting module `"go-logistics"` | TDP2 only if feature siblings use it |
| **gomart** | `TestDataPoolController.getTestData` | TDP2 if siblings use it |
| **icp** | `CommsAEPDataPoolingHelper` (pool + TDP2 inside helper) | `"ICP"` on `TDP2Request` |
| **care-platform** | `CareAEPDataPoolingHelper` | TDP2 inside helper (`"ICP"` client in some paths — copy sibling) |
| **gamification** | `GamificationAEPDataPoolingHelper` | Module name constant on `setClient` |
| **gojek-e2e** | `TestDataPoolUtils.getTDPCustomer` / `getTDPDriver` | Category + client string per util |
| **gopay** / **gopay** gRPC | Journey helpers / fixtures in `userJourneyTests` — **no** `TestDataPoolController` in tests; map category to existing helper or `TODO` | Add TDP2 only if a sibling imports `TDP2Controller`; set `client` per sibling |
| **iris** / **scp** | Helpers and constants in feature tests — grep pool in package | TDP2 if present in module; else `TODO` |
| **midtrans-core-api** | Feature-specific test data helpers / static pools | TDP2 if siblings use it |
| **payment-core** | Per-environment constants / `MerchantData` — **no** `@TestInfo`; follow payment-core writer | Usually N/A — document `TODO` if TDI marks TESTBUDDY |

If the **target module** is not listed, grep `gojek-backend-tests/<module>` for
`TestDataPoolController`, `TDP2Controller`, and `getTDP2Response`, then mirror the nearest sibling.

## Relation to `test_data_payloads`

- **`test_data_output`** → **how to provision** in `@BeforeMethod` / test setup (pool vs TDP2).
- **`test_data_payloads`** (from `gbt-test-data-generator` merge) → **resolve** `{{FX-….field}}` at
  runtime in CI — orthogonal to the setup code above.

## Module writer obligation

Every `*-api-test-writer` and `*-grpc-api-test-writer` must document the **exact** pool entrypoints
and TDP2 helpers for that module under **Fixture setup from enriched plan**. Codegen reads the
writer for the resolved `(module, transport)` before emitting setup code.
