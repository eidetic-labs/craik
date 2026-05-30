# Flow: `AnthropicAPI`

**Adapter id (envelope `source`):** `anthropic-api`
**Surface:** API — craik drives the tool loop and gates each caller-executed tool call before running it through its own sandbox/policy/receipt layer.
**Live-gate verdict:** ✓.
**Derived from:** the Backend Adapter Layer design spec (§4.5, §5, §6.2, §6.5, §7) and [`vendor-capabilities.md`](../vendor-capabilities.md) (Anthropic API).

This is a *drive-the-model* adapter: craik owns the loop, decides nothing the model wouldn't, but **executes** the requested side effect through its own side-effects layer. Per-token cost. This surface is also a home for craik's own multi-agent orchestration (debates, handoffs, scope-change protocol).

---

## 1. Invocation

craik calls the **Messages API** directly over HTTP (the `APIAdapter` base provides generic HTTP / auth headers / tool loop):

- **Prompt:** sent as the user message in the Messages request.
- **Injected instructions:** craik's governance/system instructions are sent as the `system` prompt (and tool definitions) on the request — craik composes the request, not the model.
- **Tools:** craik declares **only custom (caller-executed) function tools** in the request. **Hosted / server-side tools are declared NOT at all by default** (see §3) — enabling one would silently bypass craik's veto.
- **Loop:** craik runs the tool loop itself: send request → model returns `tool_use` block(s) → craik gates and executes each → feeds `tool_result` back → repeat until the model returns a final answer.

## 2. Event mapping

The Messages response (`tool_use` blocks, assistant text, stop reasons) is mapped to canonical `BackendEvent`s via the shared builder spine:

- Every emitted event carries the envelope `source = "anthropic-api"`.
- Assistant text → typed text events; `tool_use` blocks → typed tool events.
- **`receipt.created`** carries:
  - `execution = "craik"` — craik physically ran the side effect itself (strongest attestation: craik ran it and signed the result).
  - `mode` — the active craik governance mode.
  - `decision` — `allow` | `deny`.
  - `decided_by` — `operator` | `policy` | `bypass`.

`vendor`/`surface` derive from `source`; same event type ⇒ same fields.

## 3. Governance / live-gating

craik drives the loop, so it gates **inline, before executing**:

1. The model returns a `tool_use` tool call.
2. `AnthropicAPI` maps it to a `SideEffect` with craik's sandbox `executor`.
3. The side-effects layer (`src/craik/runtime/side_effects.py`) **authorizes** the action against the `PolicyEnvelope` + `CapabilityGrant`s (plus operator approval where required):
   - **Deny path:** persist a signed denial receipt; return `allowed=False`; **nothing runs**.
   - **Allow path:** run the operation through the pluggable `executor` (local or Docker/SSH/remote sandbox), redact the output, mint a signed capability receipt, return the result.
4. The (redacted) result is fed back to the model.

**Governance-critical constraint:** only custom function tools are gateable, because the model returns each call for craik to gate-then-execute. **Vendor hosted / server-side tools execute on Anthropic's infrastructure before craik sees a result and are therefore ungateable.** `APIAdapter` declares no hosted tools by default; any hosted-tool use is an explicit, audited, observe-only / policy-flagged opt-out of live gating (see [`vendor-capabilities.md` § Cross-cutting](../vendor-capabilities.md#cross-cutting-hostedserver-side-api-tools-bypass-gating)).

## 4. Auth acquisition

- **Mode:** **API key.** (Also Bedrock / Vertex.)
- **Acquisition responsibility (surface-owned):** craik's `credential_storage` (keyring/file) + `secret_ref_name`, resolved at request time in `_provider_headers()`. Unlike the CLI surface, craik holds and supplies the credential.
- Per-token cost.

## 5. Failure / interrupt

- **Deny:** the side-effects layer returns `allowed=False`, persists a denial receipt, and the tool result fed back to the model reflects the denial; nothing runs.
- **API errors / rate limits:** classified through the shared per-vendor error/rate-limit/retry path (`provider_failover` / `provider_execution`); retried or surfaced as gateway error events.
- **Interrupt:** because craik owns the loop, an interrupt halts the loop between turns and craik stops issuing further tool executions — a cleaner interrupt than the CLI's process-kill.

## 6. Verification

Smoke the gated loop end-to-end with a custom function tool that performs a shell side effect:

```sh
# With an Anthropic API key configured in craik's credential storage:
craik chat -q -   # or the adapter-level harness for anthropic-api
# Issue a prompt that triggers a custom tool call; confirm:
#   - the model returns a tool_use block,
#   - the side-effects layer authorizes (allow → executes via the sandbox executor; deny → nothing runs),
#   - a receipt.created is emitted with source=anthropic-api, execution=craik,
#   - no hosted tool is enabled (the request declares only custom function tools).
```

Confirm a denied call persists a denial receipt and executes nothing, and an allowed call executes through the sandbox `executor` and mints a signed capability receipt.
