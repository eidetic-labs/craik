# Flow: `AnthropicCLI`

**Adapter id (envelope `source`):** `anthropic-cli`
**Surface:** CLI — wrap Claude Code; craik governs/audits around it via the CLI's blocking pre-tool hook.
**Live-gate verdict:** ✓ live-gates (verified).
**Derived from:** the Backend Adapter Layer design spec (§4.5, §5, §6, §7) and [`vendor-capabilities.md`](../vendor-capabilities.md) (Anthropic CLI, pinned `claude` 2.1.156).

This adapter is the realization of craik's governance thesis on the cheapest auth path: live per-call gating billed to the user's Claude subscription, no per-token cost.

---

## 1. Invocation

craik spawns the Claude Code CLI headless:

```sh
claude -p --output-format stream-json --verbose --permission-mode dontAsk
```

- **Prompt:** supplied as the `-p` argument (the run prompt).
- **Injected instructions:** craik's system/governance instructions are injected through Claude Code's own configuration surface (system-prompt / settings) before the turn — craik does not run an agent loop; the CLI runs the loop.
- **Base mode:** the CLI launches under `--permission-mode dontAsk` so that craik's `PreToolUse` hook is the authoritative decision point. craik implements the operator-facing modes (`ask`/`auto`/`acceptEdits`/`plan`/`bypassPermissions`) itself, inside the hook, under a `dontAsk` + allowlist baseline (§6.3) — it does not pass through the CLI's native classifier.
- **Hook config:** a `PreToolUse` hook is registered in `.claude/settings.json` (project) or `~/.claude/settings.json` (user), pointing at craik's hook script.
- **Settings hygiene:** craik's launch settings must carry **no** managed/user/project native `deny` rules, which would override a hook `allow` (§6.3, §9).

## 2. Event mapping

The CLI emits a `stream-json` stream with the vocabulary `assistant` / `result` / `system`. The `CLIAdapter` stream parser maps these to canonical `BackendEvent`s via the shared builder spine (no inline ad-hoc dicts):

- Every emitted event carries the envelope `source = "anthropic-cli"` alongside `type` / `run_id` / `task_id` / `created_at`.
- **Assistant text** (`assistant` lines): Claude Code emits one `assistant` line per *cumulative* update. The parser **coalesces** these cumulative frames into one streamed/finalized text event (§5.2) — it does not re-emit each cumulative frame as a fresh text event (that was the repeated-line bug).
- **Tool results** map to typed tool events (the `run.event` catch-all is split into proper typed events).
- **`receipt.created`** (the self-contained governance record) carries:
  - `execution = "delegated-observed"` — the CLI executed the side effect in its own shell; craik authorized (pre-tool hook) and observed/recorded the reported result.
  - `mode` — the active craik governance mode (`ask` / `auto` / `acceptEdits` / `plan` / `default` / `bypassPermissions`).
  - `decision` — `allow` | `deny`.
  - `decided_by` — `operator` (human approved in the modal) | `policy` (craik auto) | `bypass` (ungoverned, under `bypassPermissions`).
- A single turn legitimately emits **two distinct receipts** — an **approval receipt** and an **execution receipt** (§5.1). These are **not** duplicates and must not be deduped; `purpose`/`scope` in the typed payload distinguishes them.

`vendor`/`surface` are derivable from `source` and are not duplicated in the payload.

## 3. Governance / live-gating

Live gating runs through the CLI's blocking `PreToolUse` hook:

1. On each tool call the CLI **blocks synchronously** and invokes craik's hook script.
2. The hook script **RPCs to craik's already-running gateway daemon** (the `tui-backend` process).
3. The decision surfaces in the TUI — **the approval modal is the operator decision point** (in `ask` mode); in `auto`/`acceptEdits`/`plan` craik's policy decides.
4. The hook returns the decision to the CLI: **allow** via JSON (`hookSpecificOutput.permissionDecision: "allow"`) or **deny** via **exit code 2** (the reliable hard-block; the `permissionDecision: "deny"` JSON is subject to native settings precedence, exit-2 is not).
5. craik mints a receipt for the decision (`execution = "delegated-observed"`).

Hooks block synchronously with a 600 s default timeout (configurable) and may do arbitrary work while blocking — ample for a human-approval round-trip. The hook **still fires under `bypassPermissions`** (verified), so governance is preserved even in the escape-hatch mode; such a decision is receipted with `decided_by = "bypass"` as the audit flag that the tool ran ungoverned.

## 4. Auth acquisition

- **Mode:** the user's **Claude subscription / OAuth**, acquired via `claude setup-token` — or an API key.
- **Acquisition responsibility (surface-owned):** the CLI surface **delegates to Claude Code's own auth** (`claude setup-token` / `claude auth status`) and bypasses craik's credential storage at runtime. craik does not hold the subscription credential.
- Anthropic is the **only** vendor exposing a sanctioned headless subscription token, so subscription-billed live gating is Anthropic-only. **No per-token cost.**

## 5. Failure / interrupt

- **Hook timeout:** the >600 s timeout is undocumented; craik treats an operator-approval timeout as **deny** (fail-closed).
- **Deny:** a denied tool call is hard-blocked (exit 2) and appears in the CLI's `permission_denials`; craik persists a denial receipt (`decision = "deny"`).
- **Errors:** CLI/process errors surface as gateway error events on the run; the run terminates.
- **Interrupt:** today an interrupt kills the one-shot CLI process; the live control channel (hook → daemon RPC) is the path that lets craik intervene per-call. End-to-end daemon RPC + TUI approval round-trip is the craik-side build to smoke before claiming live governance works (§9).

## 6. Verification

Re-smoke (from [`vendor-capabilities.md` § Anthropic](../vendor-capabilities.md#anthropic--claude-code-pretooluse)):

```sh
claude --version
# Register a PreToolUse hook in .claude/settings.json:
#   allow case: emit {"hookSpecificOutput":{"permissionDecision":"allow"}}
#   deny case:  exit 2
claude -p --output-format stream-json --verbose --permission-mode dontAsk "run: echo smoke-test"
# Repeat with --permission-mode bypassPermissions to confirm the hook still fires.
```

Expected (verified 2026-05-30 @ `claude` 2.1.156): hook fires (payload includes `tool_name`, `command`, `session_id`, `permission_mode`); allow → tool runs; deny (exit 2) → tool blocked, appears in `permission_denials`; fires even under `bypassPermissions`. The craik-side daemon RPC + TUI approval round-trip must be smoke-tested end-to-end separately (§9).
