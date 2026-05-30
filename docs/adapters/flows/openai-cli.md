# Flow: `OpenAICLI` (observe-only)

**Adapter id (envelope `source`):** `openai-cli`
**Surface:** CLI — wrap Codex; craik audits around it.
**Live-gate verdict:** ✗ **observe-only** (verified negative). **Live governance over OpenAI MUST go through the [`OpenAIAPI`](./openai-api.md) surface.**
**Derived from:** the Backend Adapter Layer design spec (§4.5, §5, §6, §7, §9) and [`vendor-capabilities.md`](../vendor-capabilities.md) (OpenAI CLI, pinned `codex` 0.135.0).

This adapter **cannot reliably live-gate**. It is documented as observe-only because Codex's headless pre-tool hook does not fire for the shell tool. Do not route governed OpenAI runs through this surface.

---

## 1. Invocation

craik spawns Codex headless:

```sh
codex exec --json
```

- **Prompt:** supplied to `codex exec`.
- **Injected instructions:** craik's instructions are injected through Codex's configuration surface before the turn; the `codex` CLI runs the loop.
- **Hook config:** a `PreToolUse` / `PermissionRequest` hook can be registered in `.codex/hooks.json` or `config.toml` — but it does **not** fire for the shell tool at the pinned version (§3), so it is not a relied-upon control point.

## 2. Event mapping

Codex's `stream-json` vocabulary is `thread` / `turn` / `item.*`. The `CLIAdapter` stream parser maps these to canonical `BackendEvent`s via the shared builder spine:

- Every emitted event carries the envelope `source = "openai-cli"`.
- Assistant text and tool/item events map to typed text/tool events (the `run.event` catch-all is split into proper typed events).
- **`receipt.created`** carries:
  - `execution = "delegated-observed"` — the `codex` CLI executed the side effect; craik **observed** and recorded the reported result. Note: because the hook does not fire, craik did **not** authorize the call pre-execution — these receipts attest observation only, not an enforced authorization decision.
  - `mode`, `decision`, `decided_by` — recorded as observed; on this surface craik cannot enforce a `deny`, so the audit record reflects observe-only governance.

`vendor`/`surface` derive from `source`.

## 3. Governance / live-gating — observe-only

**This surface cannot live-gate.** Codex's `PreToolUse` hook **did NOT fire** for the shell tool under `codex exec` (v0.135.0). The negative was confirmed across a controlled test surface — project-local AND user-level config, `--full-auto`, `approval_policy="untrusted"`, isolated `CODEX_HOME` — and with **both** a `.*` wildcard matcher AND an explicit `Bash` matcher. It is **not** a config error or a matcher problem.

**Root cause (OpenAI's own documentation):** Codex's PreToolUse *"doesn't intercept all shell calls yet, only the simple ones"*; the `unified_exec` shell path's interception is *"incomplete"*; the hook is *"a guardrail rather than a complete enforcement boundary."*

**Consequence:** `OpenAICLI` is **observe-only**. To live-govern OpenAI, use the [`OpenAIAPI`](./openai-api.md) surface, where custom function tools are caller-executed and form a complete enforcement boundary. Re-smoke on each Codex upgrade — this may improve as `unified_exec` interception matures (§6).

## 4. Auth acquisition

- **Mode:** **API key.** consumer-subscription headless use is unsupported / a gray-zone path and is **not** an automation surface craik relies on — there is no sanctioned headless subscription token for Codex.
- **Acquisition responsibility:** API key supplied to the CLI. Do **not** promise subscription auth for this surface (§4.5 consequence 3).

## 5. Failure / interrupt

- **No enforced deny:** since the hook does not fire, craik cannot block a tool call on this surface — the chief reason it is observe-only.
- **Errors:** CLI/process errors surface as gateway error events; the run terminates.
- **Interrupt:** an interrupt kills the one-shot CLI process.

## 6. Verification

Re-smoke (from [`vendor-capabilities.md` § OpenAI](../vendor-capabilities.md#openai--codex-pretooluse--permissionrequest)):

```sh
codex --version
# Register a PreToolUse/PermissionRequest hook in .codex/hooks.json or config.toml.
# Controlled surface used to confirm the negative:
#   - project-local config AND user-level config
#   - both a ".*" wildcard matcher AND an explicit "Bash" matcher
#   - isolated CODEX_HOME, approval_policy="untrusted", and --full-auto
codex exec --json "run: echo smoke-test"
```

Expected at v0.135.0: the hook does **NOT** fire for the shell tool (`unified_exec` interception is incomplete) → **observe-only**. If a future version begins firing, record the new result, and re-evaluate the observe-only verdict (and whether OpenAI live governance can move to the CLI surface).
