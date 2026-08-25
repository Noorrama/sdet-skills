---
name: mobile-test-data-provisioner
description: The one shared skill. Resolves each scenario's data_needs into a data handle via the TestBuddy MCP (CustomerAgent/VoucherAgent/BookingAgent/DriverAgent/PaymentAgent), with a GBT builder fallback and synthetic generation for sensitive data. App-agnostic; used at both scenario time (validate availability) and code-gen time (provision). Returns handles, never raw values.
---

# Mobile Test-Data Provisioner (shared, all 5 GoTo apps)

The single separate shared skill. It turns a scenario's `data_needs` into runnable test data by
calling **TestBuddy** (the ground-truth provisioner), falling back to GBT builders, and generating
synthetic data for sensitive states.

## Config
`config/<app>.json` → `testbuddy.agents` and `testbuddy.segments` (logical state → segment name).

## Reads
A scenario's `data_needs` (from `scenario.schema.json`): `entity`, `state`, `provision`, `sensitive`, `testbuddy_hint`.

## Model
Fast tier — Haiku / Composer 2.5 (parse intent → tool calls). Most work is deterministic MCP calls.

## Resolve (in order) → data_handle.schema.json
1. Parse `data_needs` into a spec.
2. **TestBuddy MCP** (source of truth). Map intent → agent/tool, e.g.:
   - GoPay balance: `CustomerAgent.get_customer_gopay_balance` / `recharge_customer_gopay`
   - segment (first-time/verified): `CustomerAgent.get_customer_segments` / `get_and_add_customer_to_segment`
   - saved address: `CustomerAgent.get_customer_saved_addresses` / `edit_customer_saved_address`
   - token/OTP: `CustomerAgent.refresh_customer_token`
   - promo/voucher (e.g. SAVE20): `VoucherAgent.get_voucher_by_...`
   - booking state: `BookingAgent.*`; driver state: `DriverAgent.*`; dynamic QR: `PaymentAgent.generate_dynamic_qr`
   If a matching entity exists → **lease** it (allocation lock, avoid parallel-run collisions).
3. **GBT builder fallback** — construct the state when TestBuddy lacks the capability (e.g., a very specific boundary).
4. **Synthetic** — for sensitive states (KYC identity, card, PII) generate synthetic; never copy prod PII.
5. **override** — for flags/remote-config states.
6. Return a **handle**: `{handle_id, for_data_need, entity, provision_method, source, refs, credentials_ref, ttl_seconds, cleanup_token}`.

## Rules
- **Isolation** — lease/lock or unique-per-run entities; no shared mutable accounts.
- **Never hard-code** accounts/promo codes/tokens/PII — resolve from TestBuddy or the vault; mask in logs.
- **Sensitive** (`sensitive:true`) data is synthetic/constructed, never real prod PII.
- **Teardown** — return leased entities to the pool / delete constructed ones via `cleanup_token` (TTL-bounded).

## Two call sites
- **Scenario time (Impl. Planning):** validate availability (does TestBuddy have this?) — flag if not.
- **Code-gen time (Code Generation):** actually provision and bind the handle to the test.

## Guardrails
Output valid JSON only, conforming to `schemas/data_handle.schema.json`.
