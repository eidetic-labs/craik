# Operator-runtime smoke checklist

**Purpose.** Most of the operator-runtime contract is now pinned by automated tests + CI
guards (see "Automated coverage" below). This checklist covers only the **small residual
surface that genuinely needs a human driving a real vendor CLI** — the interactive TUI
round-trip that cannot be exercised headlessly. Run it before a release that touched the
backend adapters, the gateway run loop, the permission-mode passthrough, or the TUI
approvals overlay.

craik's job here is to **capture what the behavior was**, not to force it: the operator
picks a mode, craik passes it through faithfully, and records (via receipts) what ran.

---

## Automated coverage (do NOT re-verify by hand)

| Concern | Pinned by |
|---|---|
| Every captured gateway stream satisfies the typed event contract, per vendor×surface | `tests/runtime/backend/gateway/test_operator_runtime_smoke.py` |
| `receipt.created` always carries `run_id` + `receipt_id` (the bug that crashed the gateway) | same smoke test + `scripts/check_gateway_event_emission.py` (CI guard) |
| Each vendor's real mode vocab reaches its CLI flag; fake modes (`auto`) are dropped, not silently coerced | `scripts/check_vendor_mode_passthrough.py` (CI guard) + `tests/test_check_vendor_mode_passthrough.py` |
| Operator approve→executes+operator receipt; deny→blocked+denial receipt; timeout→fail-closed deny | `tests/test_backend_jsonl_live_gating.py` |
| **Live gate round-trip through the REAL bridge + REAL `craik-hook` client** — a fake "CLI" runs the actual `craik-hook` console binary against the live bridge socket and honors its allow/deny: approve→ALLOW (exit 0, allow JSON)+operator receipt; deny→DENY (exit 2, deny JSON)+denial receipt; unreachable socket / no socket env / timeout→fail-closed DENY. This is the automatable core of the old "live eyeball" — the bridge↔client decision path is now covered headlessly. | `tests/runtime/backend/gateway/test_live_gate_e2e.py` |
| A gated run for a hook-capable vendor (anthropic-cli/google-cli) actually REGISTERS the craik-hook — no "ungated-while-claiming-gated" regression (claude via `--settings` PreToolUse; gemini via merged `BeforeTool`, operator's own hooks preserved) | `scripts/check_gated_run_registers_hook.py` (CI guard) + `tests/test_check_gated_run_registers_hook.py` |
| Observe-only (Codex) is excluded from gating, not errored | `tests/test_backend_jsonl_live_gating.py::test_observe_only_adapter_is_not_gated` |
| TUI high-risk two-press arming keys off the RAW `permission_mode` token (`bypassPermissions`/`yolo`/`danger-full-access`, case-insensitive) | `crates/craik-tui-rs/src/app.rs` tests `high_risk_bypass_approval_requires_two_press_arm`, `high_risk_gate_fires_for_yolo_and_danger_full_access`, `high_risk_match_is_case_insensitive`, `non_bypass_approval_approves_on_single_press` |
| `_active_permission_mode` resolves the active vendor's stored token (not a display form) | `tests/test_backend_jsonl_live_gating.py::test_active_permission_mode_returns_stored_token_or_none` |

Run the automated gate locally exactly as CI does:

```bash
.venv/bin/python -m pytest \
  tests/runtime/backend/gateway/test_operator_runtime_smoke.py \
  tests/test_backend_jsonl_live_gating.py \
  tests/runtime/backend/gateway/test_live_gate_e2e.py \
  tests/test_gateway_replay.py \
  tests/test_check_gateway_event_emission.py \
  tests/test_check_vendor_mode_passthrough.py \
  tests/test_check_gated_run_registers_hook.py -q
.venv/bin/python scripts/check_gateway_event_emission.py
.venv/bin/python scripts/check_vendor_mode_passthrough.py
.venv/bin/python scripts/check_gated_run_registers_hook.py
( cd crates/craik-tui-rs && cargo test && cargo clippy --all-targets -- -D warnings )
```

---

## Manual round-trip (real CLI + interactive TUI)

**What's left for a human.** The bridge↔client decision path — the `craik-hook` client
forwarding to the live bridge, the operator decision resolving, and the vendor-correct
allow/deny coming back (incl. all three fail-closed cases) — is now AUTOMATED end-to-end
(`tests/runtime/backend/gateway/test_live_gate_e2e.py`, which drives the **real** `craik-hook`
console binary against a **real** bridge socket). The TRUE residual eyeball is the one thing a
headless test cannot do: run a real `claude` / `gemini` prompt through the **interactive TUI**
and watch craik intercept a real vendor tool call (the vendor CLI actually invoking the
registered hook, the TUI modal, the two-press arm) and record the receipt.

Gate-mode status going in:

- **Claude (`anthropic-cli`)** — gate mode is **verified**: a gated run is forced to `dontAsk`
  (or honored `bypassPermissions`) with the PreToolUse `craik-hook` as the authoritative
  approval path (confirmed via the operator smoke).
- **Gemini (`google-cli`)** — gate mode is **PENDING** `scripts/smoke_gemini_hook.sh`: hook
  registration + workspace trust are correct, but *which* `--approval-mode` makes the
  `BeforeTool` hook the authoritative headless gate is not yet pinned, so no mode is force-set.

The pieces below require a real vendor CLI installed + authed and a human watching the TUI.
For each gatable vendor, drive one real prompt that triggers a tool call.

### Claude (`anthropic-cli`) — live-gating + approve-to-elevate

- [ ] `export CRAIK_CLAUDE_PERMISSION_MODE=bypassPermissions` (the high-risk bypass mode).
- [ ] Start the TUI, select an `anthropic/...` model, send a prompt that runs a shell tool
      (e.g. "run `git status` and summarize").
- [ ] Confirm the chosen mode reached the CLI (the agent is able to act; craik is not
      silently denying).
- [ ] When the gated tool surfaces an approval, confirm the TUI shows the **high-risk
      two-press** affordance (first `a` *arms* — footer shows armed; second `a` approves).
- [ ] **Approve** → the tool executes AND a `CapabilityReceipt` is recorded with
      `operator_subject` set (operator-attributed, "granted outside static policy").
- [ ] Repeat with a fresh prompt and **Deny** → the tool is blocked AND a denial receipt
      is recorded.
- [ ] No-decision (walk away) → the gate **fails closed** (denies) after the timeout.

### Gemini (`google-cli`) — live-gating + approve-to-elevate

- [ ] `export CRAIK_GEMINI_APPROVAL_MODE=yolo` (Gemini's high-risk bypass-equivalent).
- [ ] Same round-trip as Claude: chosen mode reaches the CLI; high-risk two-press arm
      appears (keyed off the raw `yolo` token); approve→executes+operator receipt;
      deny→blocked+denial receipt.

### Codex (`openai-cli`) — observe-only (honest limitation)

- [ ] `export CRAIK_CODEX_SANDBOX_MODE=danger-full-access`.
- [ ] Send a prompt that runs a tool. Confirm the chosen `--sandbox` mode reaches the
      Codex CLI and the agent behaves accordingly.
- [ ] Confirm craik **observes and records** receipts (`decided_by="bypass"`), and that
      **no approve-to-elevate prompt appears** — Codex's pre-tool hook does not fire
      (verified vendor limitation), so craik cannot live-gate it. This is expected, not a bug.

---

## If anything diverges

A manual divergence (mode not reaching the CLI, missing receipt, high-risk gate not firing,
Codex unexpectedly prompting) is a real regression. File it against the relevant adapter and,
where possible, capture the gateway stream (`gateway_event_history` in
`~/.craik/state/craik.sqlite3`) into a new `tests/fixtures/gateway/*.jsonl` and add a row to
`SMOKE_MATRIX` so the smoke test pins it going forward.
