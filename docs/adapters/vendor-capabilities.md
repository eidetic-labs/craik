# Vendor Capability Reference

**Status:** Maintained reference for the unified backend adapter layer.
**Derived from:** the Backend Adapter Layer design spec (§4.5 per-vendor validation matrix, §6 control model + empirical smoke results, §7 auth/billing).
**Last re-smoke:** 2026-05-30.
**CLI versions at last smoke:** `claude` 2.1.156 · `codex` 0.135.0 · `gemini` 0.43.0.

This is the repo-resident record of per-vendor CLI/API capabilities that the adapter layer depends on. The load-bearing facts here — tool names, hook events, the **headless hook-firing smoke results**, auth models per surface, and the Codex shell-interception limitation — were empirically validated, not assumed. They are **version-pinned** and MUST be re-validated on each vendor CLI/API version bump using the [Re-smoke checklist](#re-smoke-checklist) at the end of this document.

Two integration surfaces per vendor:

- **CLI (`<Vendor>CLI`):** wrap the vendor's own agent CLI; craik governs/audits around it via the CLI's blocking pre-tool permission hook. Subscription/OAuth auth where available; no per-token cost.
- **API (`<Vendor>API`):** craik drives the tool loop and gates each caller-executed tool call before running it through its own sandbox/policy/receipt layer. API-key auth; per-token cost.

---

## Summary matrix (vendor × surface)

| | Anthropic | OpenAI | Google |
|---|---|---|---|
| **CLI name** | Claude Code (`claude`) | Codex (`codex`) | Gemini CLI (`gemini`) |
| **CLI pinned version** | 2.1.156 | 0.135.0 | 0.43.0 |
| **CLI headless invocation** | `claude -p --output-format stream-json --verbose` | `codex exec --json` | `gemini -p --output-format json\|stream-json` (requires trusted workspace) |
| **Pre-tool hook event** | `PreToolUse` | `PreToolUse` / `PermissionRequest` | `BeforeTool` (+ declarative Policy Engine) |
| **Hook config location** | `.claude/settings.json` / `~/.claude/settings.json` | `.codex/hooks.json` or `config.toml` | `.gemini/settings.json` |
| **Hook decision protocol** | JSON `hookSpecificOutput.permissionDecision: allow/deny` **or** exit code 2 | `permissionDecision: "deny"` **or** exit code 2 | JSON `decision: "deny"/"block"` + `reason` **or** exit code 2 |
| **Hook headless-firing (smoke 2026-05-30)** | **✓ fires + allow + deny** | **✗ did NOT fire** for the shell tool under `codex exec` | **✓ fires + allow + deny** |
| **CLI live-gate verdict** | **✓ live-gates** | **✗ observe-only** | **✓ live-gates** |
| **CLI auth (automation)** | subscription/OAuth via `claude setup-token`, **or** API key | API key (ChatGPT-subscription headless = unsupported/gray-zone) | API key (AI Studio) **or** Vertex SA (consumer OAuth interactive-only) |
| **API surface** | Messages API (`tool_use`) | Responses API + Chat Completions (`function` tools) | `generateContent` (`functionCall`) |
| **API caller-executes custom tools** | yes | yes (custom function tools only) | yes |
| **API auth** | API key (+ Bedrock / Vertex) | API key (+ Azure) | AI Studio key / Vertex (google-auth / ADC) |
| **API live-gate verdict** | **✓** | **✓ (custom function tools only — hosted tools NOT gateable)** | **✓** |

**Read of the matrix:** the two-surface pattern generalizes across all three vendors — each ships an agentic CLI with a headless JSON-stream mode and a third-party-usable blocking pre-tool hook, and each API returns caller-executed tool/function calls. The one material divergence is **Codex's headless hook does not fire for the shell tool** (see [OpenAI](#openai) below), so `OpenAICLI` is observe-only and live governance over OpenAI goes through the API surface.

---

## Anthropic

### CLI — `AnthropicCLI`

- **CLI:** Claude Code (`claude`), pinned **2.1.156**.
- **Headless invocation:** `claude -p --output-format stream-json --verbose`.
- **Pre-tool hook:** `PreToolUse`, configured in `.claude/settings.json` (project) or `~/.claude/settings.json` (user).
- **Decision protocol:** JSON `hookSpecificOutput.permissionDecision: "allow" | "deny"`, or exit code 2 to hard-block. Exit-2 is the reliable deny path — the `permissionDecision: "deny"` JSON is subject to native settings precedence; exit-2 hard-blocks regardless.
- **Headless-firing result — VERIFIED ✓:** under `--permission-mode dontAsk` with `-p`, the hook fires, and both **allow** and **deny** take effect. It **still fires under `bypassPermissions`** (governance is preserved even in the escape-hatch mode). Hooks block **synchronously** (600 s default timeout, configurable) and may do arbitrary work while blocking — ample for an operator-approval round-trip.
- **CLI auth (automation):** the user's **Claude subscription / OAuth** via `claude setup-token`, or an API key. Anthropic is the **only** vendor exposing a sanctioned headless subscription token, so subscription-billed live gating is Anthropic-only.

### API — `AnthropicAPI`

- **API:** Messages API. Tool calls returned as `tool_use` blocks; the **caller executes** them and feeds results back. Fully gateable.
- **Auth:** API key (also Bedrock / Vertex).

**Live-gate verdict:** CLI ✓ and API ✓.

---

## OpenAI

### CLI — `OpenAICLI` (observe-only)

- **CLI:** Codex (`codex`), pinned **0.135.0**.
- **Headless invocation:** `codex exec --json`.
- **Pre-tool hook:** `PreToolUse` / `PermissionRequest`, configured in `.codex/hooks.json` or `config.toml`.
- **Decision protocol:** `permissionDecision: "deny"`, or exit code 2.
- **Headless-firing result — VERIFIED NEGATIVE ✗ for the shell tool:** the hook **did NOT fire** under `codex exec` (v0.135.0). This was confirmed across a controlled test surface — project-local config, user-level config, `--full-auto`, and `approval_policy="untrusted"` — and with **both** a `.*` wildcard matcher **and** an explicit `Bash` matcher. The negative is therefore not a config error or a matcher problem; it is the documented behavior of this version.

  **Root cause (OpenAI's own documentation):** Codex's PreToolUse *"doesn't intercept all shell calls yet, only the simple ones"*; the `unified_exec` shell path's interception is *"incomplete"*; the hook is *"a guardrail rather than a complete enforcement boundary."*

  **Consequence:** `OpenAICLI` is **observe-only** — it cannot reliably live-gate shell tool calls. **Live governance over OpenAI MUST go through the `OpenAIAPI` surface** (caller-executed function tools = complete enforcement boundary). Re-smoke on CLI upgrades; this may improve as `unified_exec` interception matures.
- **CLI auth (automation):** API key. ChatGPT-subscription headless use is unsupported / a gray-zone path and is not an automation surface craik relies on.

### API — `OpenAIAPI`

- **API:** Responses API + Chat Completions. **Custom function tools are caller-executed** — the model returns each call for craik to gate-then-execute (OpenAI's documented loop: "Execute code on the application side"). These are fully gateable.
- **Hosted / server-side tools are NOT gateable.** `web_search`, `code_interpreter`, `file_search`, `computer_use`, and hosted MCP run on the vendor's infrastructure *before* craik sees a result. They MUST be disabled on governed runs (or surfaced as explicit, audited, observe-only opt-outs). See [Cross-cutting: hosted/server-side tools bypass gating](#cross-cutting-hostedserver-side-api-tools-bypass-gating).
- **Auth:** API key (also Azure).

**Live-gate verdict:** CLI ✗ (observe-only) · API ✓ (custom function tools only).

---

## Google

### CLI — `GoogleCLI`

> Note: the design normalizes the legacy `gemini` provider token to **`google`** as the vendor vocabulary. The CLI binary is still named `gemini`.

- **CLI:** Gemini CLI (`gemini`), pinned **0.43.0**.
- **Headless invocation:** `gemini -p --output-format json|stream-json`. Requires `GEMINI_CLI_TRUST_WORKSPACE=true` or an already-trusted workspace — the hook does not fire in an untrusted workspace.
- **Pre-tool hook:** `BeforeTool`, configured in `.gemini/settings.json`. A declarative **Policy Engine** is also available.
- **Decision protocol:** JSON `decision: "deny" | "block"` with a `reason`, or exit code 2.
- **Headless-firing result — VERIFIED ✓:** under `-p` with the workspace trusted, the hook fires and both **allow** and **deny** take effect.
- **CLI auth (automation):** API key (AI Studio) or a Vertex service account. Consumer OAuth is interactive-only and is **not** an automation path.

### API — `GoogleAPI`

- **API:** `generateContent`. Tool calls returned as `functionCall` parts; the **caller executes** them. Fully gateable.
- **Auth:** AI Studio API key, or Vertex (google-auth / ADC).

**Live-gate verdict:** CLI ✓ and API ✓.

---

## Cross-cutting: hosted/server-side API tools bypass gating

This applies to **every** vendor's API surface, not just OpenAI.

Vendor **hosted / server-side tools** — OpenAI's `web_search` / `code_interpreter` / `file_search` / `computer_use` / hosted MCP, and the Anthropic and Google equivalents — execute on the **vendor's infrastructure before craik ever sees a result**. craik's gate sits at the point where the model returns a tool call for the caller to execute; a hosted tool never returns such a call, so there is **nothing to veto**.

Enabling a hosted tool on a governed run would therefore **silently bypass craik's enforcement boundary**. The rules:

- `APIAdapter` declares **no hosted tools by default**.
- Any hosted-tool use is an **explicit, audited opt-out of live gating** — it must be surfaced as observe-only / policy-flagged, never enabled implicitly.
- **Only custom (caller-executed) function tools are gateable.** They are the dependable, uniform gate across all three API surfaces and the fallback wherever a CLI hook proves unreliable (e.g. OpenAI's `codex exec` shell tool).

---

## Re-smoke checklist

The hook headless-firing facts above are **version-pinned** and must be re-validated whenever a vendor's CLI is upgraded. Re-run the relevant smoke below, then append a row to the corresponding results table. If a result changes, update the [Summary matrix](#summary-matrix-vendor--surface) and the per-vendor section, and revisit the `OpenAICLI` observe-only verdict.

For each smoke: register a craik-style pre-tool hook that logs the payload it received and can return both an **allow** and a **deny** decision, then run a headless prompt that triggers a shell/tool call and confirm (a) the hook fired, (b) an allow let the tool run, (c) a deny blocked it.

### Anthropic — Claude Code `PreToolUse`

```sh
claude --version
# Register a PreToolUse hook in .claude/settings.json (or ~/.claude/settings.json):
#   allow case: emit {"hookSpecificOutput":{"permissionDecision":"allow"}}
#   deny case:  exit 2
claude -p --output-format stream-json --verbose --permission-mode dontAsk "run: echo smoke-test"
# Repeat with --permission-mode bypassPermissions to confirm the hook still fires.
```

Expected: hook fires (payload includes `tool_name`, `command`, `session_id`, `permission_mode`); allow → tool runs; deny (exit 2) → tool blocked, appears in `permission_denials`; fires even under `bypassPermissions`.

| CLI version | Date | Hook fires? | Allow works? | Deny (exit 2) works? | Fires under bypassPermissions? | Pass/Fail |
|---|---|---|---|---|---|---|
| 2.1.156 | 2026-05-30 | YES | YES | YES | YES | PASS |
| | | | | | | |

### OpenAI — Codex `PreToolUse` / `PermissionRequest`

```sh
codex --version
# Register a PreToolUse/PermissionRequest hook in .codex/hooks.json or config.toml.
# Test the controlled surface that was used to confirm the negative:
#   - project-local config AND user-level config
#   - both a ".*" wildcard matcher AND an explicit "Bash" matcher
#   - isolated CODEX_HOME, approval_policy="untrusted", and --full-auto
codex exec --json "run: echo smoke-test"
```

Expected at v0.135.0: hook does **NOT** fire for the shell tool (`unified_exec` interception is incomplete). A future version may begin firing — if so, record it and re-evaluate the observe-only verdict.

| CLI version | Date | Hook fires (shell tool)? | Allow works? | Deny works? | Pass/Fail (PASS = fires reliably) |
|---|---|---|---|---|---|
| 0.135.0 | 2026-05-30 | NO | n/a | n/a | FAIL (observe-only) |
| | | | | | |

### Google — Gemini CLI `BeforeTool`

```sh
gemini --version
# Register a BeforeTool hook in .gemini/settings.json:
#   allow case: emit JSON allowing the call
#   deny case:  emit {"decision":"deny","reason":"..."} (or exit 2)
export GEMINI_CLI_TRUST_WORKSPACE=true   # or run in an already-trusted workspace
gemini -p --output-format json "run: echo smoke-test"
```

Expected: hook fires with the workspace trusted; allow → tool runs; deny → tool blocked. Confirm it does **not** fire in an untrusted workspace (the trust gate is load-bearing).

| CLI version | Date | Workspace trusted? | Hook fires? | Allow works? | Deny works? | Pass/Fail |
|---|---|---|---|---|---|---|
| 0.43.0 | 2026-05-30 | YES | YES | YES | YES | PASS |
| | | | | | | |
