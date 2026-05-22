# Agent lifecycle

<p className="craik-meta"><span>4 min read</span><span>Reference</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll find here**

The persistent agent session lifecycle introduced in v0.9.0: command
surface, status values, transition rules, prompt-loop records,
operator gating, and the relationship to one-shot task runs.

</div>

## Command boundary

| Surface | Purpose | Persistence |
| --- | --- | --- |
| `craik run execute` | Execute one bounded task run. | `craik.task_run`, outputs, receipts, handoffs. |
| `craik agent launch` | Create a persistent agent session. | `craik.agent_session_state`. |
| `craik agent prompt` | Send one prompt through the session provider. | Task, run, outputs, receipts, handoff, session links, and `craik.agent_session_event`. |
| `craik agent status` | Inspect one persistent session. | May mark stale pid sessions failed. |
| `craik agent stop` | Stop an active persistent session. | Clears pid and records `stopped_at`. |
| `craik agent restart` | Restart a stopped or failed session. | Clears `stopped_at` and records a new start time. |
| `craik agent list` | List persisted sessions. | Read-only. |

## Status values

| Status | Meaning |
| --- | --- |
| `starting` | A session launch has started but is not ready. |
| `running` | A session is available for work. |
| `idle` | A session is alive and waiting for work. |
| `stopping` | Stop has begun but cleanup is not finished. |
| `stopped` | The session was intentionally stopped. |
| `failed` | The session failed or a stored pid became stale. |
| `auth_expired` | The provider credential context can no longer be used. |
| `provider_unavailable` | The provider route is temporarily unavailable. |
| `sandbox_failed` | The sandbox route failed before safe execution. |

Active statuses are `starting`, `running`, `idle`, and `stopping`.
Restartable statuses are `stopped`, `failed`, `auth_expired`,
`provider_unavailable`, and `sandbox_failed`.

## Transition rules

<div className="craik-fields">

<div>
<dt>Launch</dt>
<dt><span className="craik-fields__type">active state</span></dt>
<dd>Creates a new `running` foreground session. Launch refuses to replace an existing active session id.</dd>
</div>

<div>
<dt>Status</dt>
<dt><span className="craik-fields__type">read with recovery check</span></dt>
<dd>Reads one session and marks stale pid-backed active sessions `failed` with a supervision note.</dd>
</div>

<div>
<dt>Stop</dt>
<dt><span className="craik-fields__type">active to stopped</span></dt>
<dd>Only active sessions can stop. Stop clears `pid`, sets `stopped_at`, and appends the operator reason.</dd>
</div>

<div>
<dt>Restart</dt>
<dt><span className="craik-fields__type">recoverable to running</span></dt>
<dd>Active sessions cannot restart. Restart clears `stopped_at`, refreshes lifecycle timestamps, and preserves provider references.</dd>
</div>

</div>

## Prompt loop

`craik agent prompt SESSION_ID "prompt text"` accepts prompts only for
active sessions. The command checks that the active operator session
matches the stored session subject and issuer before creating work. A
prompt run creates a task in the session project, executes the
provider-backed runner path, records provider receipts, writes a
handoff, and updates the session with the active task id, active run id,
receipt ids, handoff ids, and recovery metadata.

Prompt completion returns the session to `idle`. Interruption is
explicit: max-iteration and token-budget interruptions keep the session
idle, store `exit_behavior: interrupted`, and link the incomplete
handoff for recovery. `/exit`, `exit`, `/quit`, and `quit` stop the
session without creating a provider run.

## Event records

`craik.agent_session_event` is the append-only event record for
persistent sessions. Events are redacted and store references rather
than credential material:

| Event | When it is emitted |
| --- | --- |
| `prompt_received` | A non-exit prompt is accepted and converted into a task. |
| `run_completed` | The provider-backed run finishes without interruption. |
| `run_interrupted` | The provider-backed run writes an incomplete handoff for recovery. |
| `exited` | The operator sends an explicit exit prompt. |

Events include session, operator, project, provider, model, policy,
task, run, handoff, receipt, metadata, and recovery references. Prompt
text is represented by a short hash in event metadata.

## Operator gate

Every `craik agent` lifecycle command requires an active operator
session. The persisted session stores the operator subject and issuer,
and prompt execution rejects sessions owned by a different operator.
Provider sessions, recovery records, and receipts can therefore link
runtime state to an authenticated operator without storing credentials
or tokens in the local store.

## Foreground and background state

v0.9.0 starts with foreground lifecycle state and a provider-backed
prompt loop. The `pid` and `endpoint_url` fields are optional because
foreground launch does not require a daemon pid. When background
execution is added, pid-backed sessions use the same status path and
stale pid recovery semantics.

## Validation

```sh
uv run --extra dev pytest tests/test_cli_agents.py tests/test_agent_sessions.py
```

Expected output: lifecycle commands, prompt execution, event
persistence, receipt and handoff linkage, interruption handling,
explicit exits, and typed session helpers enforce operator gates and
valid transitions.
