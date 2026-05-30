# Flow: `GoogleAPI`

**Adapter id (envelope `source`):** `google-api`
**Surface:** API — craik drives the tool loop and gates each caller-executed function call before executing it through its own sandbox/policy/receipt layer.
**Live-gate verdict:** ✓.
**Derived from:** the Backend Adapter Layer design spec (§4.3, §4.5, §5, §6.2, §6.5, §7) and [`vendor-capabilities.md`](../vendor-capabilities.md) (Google API).

> Naming: the legacy `gemini` provider token is normalized to **`google`** (§4.3). The adapter id and envelope `source` are `google-api`.

This is a *drive-the-model* adapter: craik owns the loop and **executes** the requested side effect through its own side-effects layer. Per-token cost. Also a home for craik's own multi-agent orchestration.

---

## 1. Invocation

craik calls **`generateContent`** directly over HTTP (the `APIAdapter` base provides generic HTTP / auth headers / tool loop):

- **Prompt:** sent as the user `content`.
- **Injected instructions:** craik's governance/system instructions are sent as the system instruction plus the tool (function) declarations; craik composes the request.
- **Tools:** craik declares **only custom (caller-executed) function declarations**. **Hosted / server-side tools (Google's equivalents) are NOT declared by default** — see §3.
- **Loop:** craik runs the tool loop itself: send request → model returns `functionCall` part(s) → craik gates and executes each → feeds the function response back → repeat to final answer.

## 2. Event mapping

The `generateContent` response (`functionCall` parts, text parts, finish reasons) maps to canonical `BackendEvent`s via the shared builder spine:

- Every emitted event carries the envelope `source = "google-api"`.
- Text parts → typed text events; `functionCall` parts → typed tool events.
- **`receipt.created`** carries:
  - `execution = "craik"` — craik physically ran the side effect itself (strongest attestation).
  - `mode` — the active craik governance mode.
  - `decision` — `allow` | `deny`.
  - `decided_by` — `operator` | `policy` | `bypass`.

`vendor`/`surface` derive from `source`.

## 3. Governance / live-gating

craik drives the loop and gates **inline, before executing**:

1. The model returns a `functionCall` part.
2. `GoogleAPI` maps it to a `SideEffect` with craik's sandbox `executor`.
3. The side-effects layer (`src/craik/runtime/side_effects.py`) authorizes against the `PolicyEnvelope` + `CapabilityGrant`s (plus operator approval where required):
   - **Deny path:** persist a signed denial receipt; return `allowed=False`; **nothing runs**.
   - **Allow path:** run via the pluggable `executor` (local or Docker/SSH/remote sandbox), redact the output, mint a signed capability receipt, return the result.
4. The redacted result is fed back to the model as a function response.

**Governance-critical constraint:** only custom function calls are gateable, because the model returns each for craik to gate-then-execute. **Vendor hosted / server-side tools execute on Google's infrastructure before craik sees a result and are therefore ungateable.** `APIAdapter` declares no hosted tools by default; any hosted-tool use is an explicit, audited, observe-only / policy-flagged opt-out (see [`vendor-capabilities.md` § Cross-cutting](../vendor-capabilities.md#cross-cutting-hostedserver-side-api-tools-bypass-gating)).

## 4. Auth acquisition

- **Mode:** **AI Studio API key**, or **Vertex** (google-auth / ADC).
- **Acquisition responsibility (surface-owned):** craik's `credential_storage` (keyring/file) + `secret_ref_name` for the AI Studio key; for Vertex, google-auth / Application Default Credentials resolved at request time. craik holds and supplies the credential.
- Per-token cost.

## 5. Failure / interrupt

- **Deny:** the side-effects layer returns `allowed=False`, persists a denial receipt; nothing runs; the denial is reflected in the function response fed back to the model.
- **API errors / rate limits:** classified through the shared per-vendor error/rate-limit/retry path (`provider_failover` / `provider_execution`); retried or surfaced as gateway error events.
- **Interrupt:** because craik owns the loop, an interrupt halts it between turns; craik issues no further tool executions.

## 6. Verification

Smoke the gated loop with a custom function declaration that performs a shell side effect:

```sh
# With an AI Studio API key (or Vertex ADC) configured for craik:
craik chat -q -   # or the adapter-level harness for google-api
# Issue a prompt that triggers a functionCall; confirm:
#   - the model returns a functionCall part,
#   - the side-effects layer authorizes (allow → executes via the sandbox executor; deny → nothing runs),
#   - a receipt.created is emitted with source=google-api, execution=craik,
#   - NO hosted tool is enabled (the request declares only custom function declarations).
```

Confirm a denied call persists a denial receipt and executes nothing, and an allowed call executes through the sandbox `executor` and mints a signed capability receipt.
