# Approval Queue

<p className="craik-meta"><span>4 min read</span><span>For operators</span><span>Updated 2026-05-22</span></p>

<div className="craik-lead">

**What you'll find here**

How Craik surfaces runtime approval requests, how operators approve or deny
them, and which evidence is recorded for each decision.

</div>

## When approvals appear

Craik uses approval requests when a runtime action must stop for explicit
operator consent. Each request is stored as a human delegation point with the
information an operator needs before deciding:

- capability being requested
- target of the action
- risk summary
- policy profile or envelope
- intended operator, when scoped
- retry path after the decision

The request stays open until an operator approves or denies it. Decisions are
not advisory: resolving an approval emits a capability receipt and links that
receipt back to the approval record.

## Review the queue

Use the CLI when you need the full structured record:

```bash
craik approvals list
craik approvals show approval_shell
```

Inside the interactive shell or TUI, `/approvals` returns the same queue
payload. The local dashboard exposes the queue at `/approvals` and
`/api/approvals` after dashboard authorization succeeds.

## Decide a request

Approvals and denials both require an operator session and a reason:

```bash
craik approvals approve approval_shell --reason "scope is bounded"
craik approvals deny approval_shell --reason "target is too broad"
```

Approving records a passed `approval.decide` receipt. Denying records a denied
`approval.decide` receipt and preserves the retry path so the blocked workflow
can tell the operator what to change next.

## Desktop and dashboard surfaces

Desktop companion notifications deep-link to the dashboard approval page and
include redacted capability, target, risk, policy, and retry-path context. The
dashboard queue is local-only by default and requires either an active operator
session or a configured dashboard token.

## Audit behavior

Decision receipts include the approval id, decision, operator subject,
capability, target, risk, policy, and retry path. Secret-like text is redacted
before it is rendered in UI fixtures, notifications, and dashboard pages.
