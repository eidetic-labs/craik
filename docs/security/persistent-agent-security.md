# Persistent agent security

<p className="craik-meta"><span>4 min read</span><span>Security</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll find here**

The security posture for v0.9.0 persistent agent sessions: operator
binding, credential boundaries, recovery-state redaction, sandbox
failures, and the difference between reconnecting and resuming.

</div>

## Trust boundaries

Persistent sessions store references, not secrets. A session may link to
an operator subject and issuer, project id, provider id, model id, auth
profile id, policy envelope id, task/run ids, receipt ids, handoff ids,
and recovery metadata. It must not store provider API keys, refresh
tokens, session tokens, raw credential values, or unredacted provider
errors.

The prompt loop rejects active operators that do not match the stored
session subject and issuer. This prevents one local operator session
from driving another operator's persistent agent record.

## Recovery states

Craik uses explicit recoverable states instead of hiding failures inside
generic notes:

| State | Meaning | Next action |
| --- | --- | --- |
| `failed` | Stale pid or stale background endpoint state. | Reconnect the session process, then resume. |
| `auth_expired` | Provider credential context can no longer be used. | Reauthenticate, then resume. |
| `provider_unavailable` | Provider route is temporarily unavailable. | Retry or switch provider, then resume. |
| `sandbox_failed` | Sandbox policy or backend failed before safe execution. | Inspect sandbox controls, then resume. |

`craik agent recover SESSION --reason ...` records one of these states.
`craik agent recover SESSION --action reconnect` moves a recoverable
session back to `running`. `--action resume` moves it to `idle` while
preserving the existing task, run, receipt, handoff, and recovery links.

## Redaction

Recovery detail and metadata are redacted before persistence. Secret-like
keys and values such as API keys, bearer tokens, passwords, provider
tokens, and credential strings are replaced with `[REDACTED]`.
Supervision notes record only a normalized reason such as
`provider unavailable`; they do not include raw provider or sandbox
error text.

## Sandbox failures

Sandbox failures are represented as `sandbox_failed`, not as a completed
or partially completed run. Operators should inspect the sandbox backend
policy, capability grant, and environment receipts before resuming. The
session remains recoverable, but Craik does not infer that the failed
sandbox action is safe to retry without operator review.

## Operator guidance

Use `craik agent status` before recovery. It can detect stale pid and
background endpoint state and persist the recovery metadata for later
operator views. Use `craik agent recover --reason ...` for auth,
provider, or sandbox failures surfaced by direct runtime callers. Use
`--action reconnect` when a process or endpoint must be reattached; use
`--action resume` after credentials, provider routing, or sandbox policy
have been corrected.
