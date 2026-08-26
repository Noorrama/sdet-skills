# gRPC prompt test — InitTaskProgress

## Input grpcurl

```bash
grpcurl -plaintext -d '{"user_id":"8427051","group_id":"1","task_ids":["2","4"]}' \
  grpc-gami-orbit-cgk.service.q.gojek.com:80 orbit.v1.RewardService/InitTaskProgress
```

## Step 1 — Alias lookup (HTTP, not MCP)

```bash
# QA example
curl -sS "https://tapmind-backend-q.golabs.io/v1/grpc/targets"

# Integration example
curl -sS "https://tapmind-backend-i.golabs.io/v1/grpc/targets"
```

Match host `grpc-gami-orbit-cgk.service.q.gojek.com` port `80` → `gami-orbit-grpc`.

If curl fails → connect to respective VPN and retry (`CONTROL_PLANE.md`).

Override without lookup: `# alias: gami-orbit-grpc` as first line of curl_reference.

## Step 2 — Generated prompt (local conversion, §3.8)

```
call mcp grpc grpc.invoke for rpc_alias: gami-orbit-grpc service: orbit.v1.RewardService Method: InitTaskProgress request: {"user_id":"8427051","group_id":"1","task_ids":["2","4"]} | verify: status is OK
```

## Step 3 — Verify (MCP: tapmind_verify_prompt only)

```json
{
  "prompt": "call mcp grpc grpc.invoke for rpc_alias: gami-orbit-grpc service: orbit.v1.RewardService Method: InitTaskProgress request: {\"user_id\":\"8427051\",\"group_id\":\"1\",\"task_ids\":[\"2\",\"4\"]} | verify: status is OK",
  "productGroup": "<pdg>",
  "targetServiceId": "<service_name>",
  "dryRunLlm": true
}
```

## Step 4 — Execute (MCP: tapmind_run_nlp_command only)

```json
{
  "command": "<same prompt string>",
  "pdg": "<pdg>",
  "targetServiceId": "<service_name>"
}
```

If error `no tool_call.target set` → gRPC target not registered; check
`GET /v1/grpc/targets` on the same environment host.

**Do not** use `grpc_invoke` MCP for this workflow — execute goes through NLP command only.
