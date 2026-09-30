# GBT Code Generation — Reference

## Negative / edge scenario catalogue (generate when the cases imply them)

- Validation failure: missing/invalid required field -> 4xx + error body.
- Authorization failure: missing/expired/insufficient token -> 401/403.
- Resource not found: unknown id -> 404.
- Duplicate resource: re-create existing -> 409/duplicate error.
- Boundary conditions: min/max lengths, limits, pagination edges.
- Idempotency: repeated identical request behaves as specified.

## Recommended `notes` structure

Keep `notes` concise but structured:

```
Repository analysis: <framework + key patterns reused>
Workflow: <setup -> main -> verify -> cleanup>
Implemented: <which cases/files>
Skipped: <frontend-only or out-of-scope cases>
Risks: <flaky/coverage gaps, if any>
```

## Path/package examples

- Test for `POST /v1/wallet/topup` in module `:driver-platform`, mirroring
  exemplar `driver-platform/src/test/java/wallet/topup/TopupTests.java`:
  -> `driver-platform/src/test/java/wallet/topup/<Name>Test.java`
  with `package wallet.topup;`
- A new client helper, mirroring `.../src/main/java/wallet/topup/...`:
  -> `driver-platform/src/main/java/wallet/topup/<Name>.java`
  with `package wallet.topup;`
