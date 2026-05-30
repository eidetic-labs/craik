# Flow: `OpenAIAPI`

**Adapter id (envelope `source`):** `openai-api`
**Surface:** API — craik drives the tool loop and gates each caller-executed function tool before executing it through its own sandbox/policy/receipt layer.
**Live-gate verdict:** ✓ (custom function tools only — hosted tools NOT gateable).
**Derived from:** the Backend Adapter Layer design spec (§4.5, §5, §6.2, §6.5, §7) and [`vendor-capabilities.md`](../vendor-capabilities.md) (OpenAI API).

This is **the** live-governance path for OpenAI: because [`OpenAICLI`](./openai-cli.md) is observe-only, all governed OpenAI runs route here, where caller-executed function tools give a complete enforcement boundary. Per-token cost. Also a home for craik's own multi-agent orchestration.

---

## 1. Invocation

craik calls the **Responses API** (or Chat Completions) directly over HTTP (the `APIAdapter` base provides generic HTTP / auth headers / tool loop):

- **Prompt:** sent as the input/user message.
- **Injected instructions:** craik's governance/system instructions are sent as the system/instructions field plus the tool definitions; craik composes the request.
- **Tools:** craik declares **only custom (caller-executed) `function` tools**. **Hosted / server-side tools are NOT declared by default** (`web_search` / `code_interpreter` / `file_search` / `computer_use` / hosted MCP) — see §3.
- **Loop:** craik runs the documented OpenAI tool loop itself: send request → model returns a function tool call → **"Execute code on the application side"** (craik gates then executes) → feed the result back → repeat to final answer.

## 2. Event mapping

The Responses/Chat output (function tool calls, assistant text, finish reasons) maps to canonical `BackendEvent`s via the shared builder spine:

- Every emitted event carries the envelope `source = "openai-api"`.
- Assistant text → typed text events; function tool calls → typed tool events.
- **`receipt.created`** carries:
  - `execution = "craik"` — craik physically ran the side effect itself (strongest attestation).
  - `mode` — the active craik governance mode.
  - `decision` — `allow` | `deny`.
  - `decided_by` — `operator` | `policy` | `bypass`.

`vendor`/`surface` derive from `source`.

## 3. Governance / live-gating

craik drives the loop and gates **inline, before executing** — the documented OpenAI loop's step 3 ("Execute code on the application side") **is** craik's gate-then-execute step:

1. The model returns a custom `function` tool call.
2. `OpenAIAPI` maps it to a `SideEffect` with craik's sandbox `executor`.
3. The side-effects layer authorizes against the `PolicyEnvelope` + `CapabilityGrant`s (plus operator approval where required):
   - **Deny path:** persist a signed denial receipt; return `allowed=False`; **nothing runs**.
   - **Allow path:** run via the pluggable `executor`, redact the output, mint a signed capability receipt, return the result.
4. The redacted result is fed back to the model.

**Governance-critical constraint (verified against OpenAI docs 2026-05-30):** only **custom function tools** are gateable — the model returns each call for craik to gate-then-execute. **Hosted / server-side tools (`web_search`, `code_interpreter`, `file_search`, `computer_use`, hosted MCP) execute on OpenAI's infrastructure *before* craik sees a result and are therefore ungateable.** Enabling one on a governed run would silently bypass craik's veto. `APIAdapter` declares no hosted tools by default; any hosted-tool use is an explicit, audited, observe-only / policy-flagged opt-out (see [`vendor-capabilities.md` § Cross-cutting](../vendor-capabilities.md#cross-cutting-hostedserver-side-api-tools-bypass-gating)).

## 4. Auth acquisition

- **Mode:** **API key.** (Also Azure.)
- **Acquisition responsibility (surface-owned):** craik's `credential_storage` (keyring/file) + `secret_ref_name`, resolved at request time in the auth-header path. craik holds and supplies the credential.
- Per-token cost.

## 5. Failure / interrupt

- **Deny:** the side-effects layer returns `allowed=False`, persists a denial receipt; nothing runs; the denial is reflected in the result fed back to the model.
- **API errors / rate limits:** classified through the shared per-vendor error/rate-limit/retry path (`provider_failover` / `provider_execution`); retried or surfaced as gateway error events.
- **Interrupt:** because craik owns the loop, an interrupt halts it between turns; craik issues no further tool executions.

## 6. Verification

Smoke the gated loop with a custom function tool that performs a shell side effect:

```sh
# With an OpenAI API key configured in craik's credential storage:
craik chat -q -   # or the adapter-level harness for openai-api
# Issue a prompt that triggers a custom function tool call; confirm:
#   - the model returns a function call,
#   - the side-effects layer authorizes (allow → executes via the sandbox executor; deny → nothing runs),
#   - a receipt.created is emitted with source=openai-api, execution=craik,
#   - NO hosted tool is enabled (the request declares only custom function tools).
```

Confirm a denied call persists a denial receipt and executes nothing. Because the [`OpenAICLI`](./openai-cli.md) surface is observe-only, this API smoke is the authoritative proof that OpenAI runs can be live-governed.
