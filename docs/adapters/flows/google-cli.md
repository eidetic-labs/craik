# Flow: `GoogleCLI`

**Adapter id (envelope `source`):** `google-cli`
**Surface:** CLI — wrap the Gemini CLI; craik governs/audits around it via the CLI's blocking pre-tool hook.
**Live-gate verdict:** ✓ live-gates (verified, workspace-trust gated).
**Derived from:** the Backend Adapter Layer design spec (§4.3, §4.5, §5, §6, §7) and [`vendor-capabilities.md`](../vendor-capabilities.md) (Google CLI, pinned `gemini` 0.43.0).

> Naming: the design normalizes the legacy `gemini` provider token to **`google`** as the vendor vocabulary (§4.3). The CLI binary is still named `gemini`; the adapter id and envelope `source` are `google-cli`.

---

## 1. Invocation

craik spawns the Gemini CLI headless:

```sh
gemini -p --output-format json   # or stream-json
```

- **Prompt:** supplied as the `-p` argument.
- **Injected instructions:** craik's instructions are injected through the Gemini CLI's configuration surface before the turn; the CLI runs the loop.
- **Workspace trust (load-bearing):** the hook fires only with a trusted workspace — craik launches with `GEMINI_CLI_TRUST_WORKSPACE=true` (or in an already-trusted workspace). The hook does **not** fire in an untrusted workspace.
- **Hook config:** a `BeforeTool` hook is registered in `.gemini/settings.json`, pointing at craik's hook script. A declarative **Policy Engine** is also available; craik implements its operator-facing modes itself in the hook (consistent with the Anthropic CLI surface, §6.3).

## 2. Event mapping

The Gemini CLI's JSON-stream vocabulary is `init` / `message` / `tool_use` / `result`. The `CLIAdapter` stream parser maps these to canonical `BackendEvent`s via the shared builder spine:

- Every emitted event carries the envelope `source = "google-cli"`.
- Assistant `message` content → typed text events; `tool_use` → typed tool events (the `run.event` catch-all is split into proper typed events).
- **`receipt.created`** carries:
  - `execution = "delegated-observed"` — the Gemini CLI executed the side effect; craik authorized (pre-tool hook) and observed/recorded the reported result.
  - `mode` — the active craik governance mode (`ask` / `auto` / `acceptEdits` / `plan` / `default` / `bypassPermissions`).
  - `decision` — `allow` | `deny`.
  - `decided_by` — `operator` | `policy` | `bypass`.

`vendor`/`surface` derive from `source`.

## 3. Governance / live-gating

Live gating runs through the CLI's blocking `BeforeTool` hook (same shape as the Anthropic CLI path, with Gemini's hook dialect):

1. On each tool call the CLI **blocks synchronously** and invokes craik's hook script.
2. The hook script **RPCs to craik's already-running gateway daemon** (the `tui-backend` process).
3. The decision surfaces in the TUI — **the approval modal is the operator decision point** (in `ask` mode); craik's policy decides in `auto`/`acceptEdits`/`plan`.
4. The hook returns the decision: **allow** via JSON, or **deny** via JSON `decision: "deny" | "block"` with a `reason` — or, for the reliable hard-block, **exit code 2**.
5. craik mints a receipt for the decision (`execution = "delegated-observed"`).

The per-vendor hook-protocol translator presents this Gemini-dialect decision as craik's uniform decision to the gateway daemon. **Workspace trust is the load-bearing precondition** — without a trusted workspace the hook does not fire, so craik must enforce the trust flag at launch.

## 4. Auth acquisition

- **Mode:** **API key (AI Studio)** or a **Vertex service account**. Consumer OAuth is interactive-only and is **not** an automation path — do **not** promise subscription auth for this CLI surface (§4.5 consequence 3).
- **Acquisition responsibility (surface-owned):** the CLI surface supplies the API key / Vertex SA credential to the Gemini CLI.

## 5. Failure / interrupt

- **Untrusted workspace:** the hook silently does not fire — treat a missing trust flag as a governance failure; craik must not launch a governed run without it.
- **Hook timeout:** treat an operator-approval timeout as **deny** (fail-closed).
- **Deny:** a denied call is blocked (JSON `deny`/`block` or exit 2); craik persists a denial receipt.
- **Errors:** CLI/process errors surface as gateway error events; the run terminates.
- **Interrupt:** an interrupt kills the one-shot CLI process; the hook → daemon RPC path is craik's per-call intervention point.

## 6. Verification

Re-smoke (from [`vendor-capabilities.md` § Google](../vendor-capabilities.md#google--gemini-cli-beforetool)):

```sh
gemini --version
# Register a BeforeTool hook in .gemini/settings.json:
#   allow case: emit JSON allowing the call
#   deny case:  emit {"decision":"deny","reason":"..."} (or exit 2)
export GEMINI_CLI_TRUST_WORKSPACE=true   # or run in an already-trusted workspace
gemini -p --output-format json "run: echo smoke-test"
```

Expected (verified 2026-05-30 @ `gemini` 0.43.0): hook fires with the workspace trusted; allow → tool runs; deny → tool blocked. **Confirm it does NOT fire in an untrusted workspace** (the trust gate is load-bearing). The craik-side daemon RPC + TUI approval round-trip must be smoke-tested end-to-end separately.
