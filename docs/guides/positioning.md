# Positioning

<p className="craik-meta"><span>5 min read</span><span>For contributors</span><span>Updated 2026-05-24</span></p>

<div className="craik-lead">

**Why Craik exists**

Craik is an audit-first agent runtime. It is built for durable project work
where operators need evidence, policy, receipts, and handoffs to be first-class
runtime objects rather than after-the-fact logs.

</div>

## The Product Shape

Craik is not trying to be a general chat wrapper or a loose automation script
runner. It is a local-first runtime for governed agent work:

- project context is assembled into typed case files
- prompts are compiled through policy-aware runtime contracts
- provider calls produce receipts and redacted side evidence
- handoffs, work graphs, and review artifacts persist across sessions
- operator and credential boundaries are explicit when audited mode is enabled

The useful comparison is not "which model can answer a prompt." The useful
comparison is "which runtime can make a long-running agent action inspectable,
recoverable, and governable."

## Adjacent Product Shapes

| Capability | Personal assistant | Self-improving agent | Audit-first runtime |
|---|---|---|---|
| Primary workflow | Converse, delegate, and automate across many surfaces. | Accumulate skills and improve repeated task execution. | Execute governed project work with evidence, receipts, and recoverable state. |
| Memory posture | User preference and conversation memory. | Skill, strategy, or task memory shaped by model feedback. | Evidence-backed project state, assumptions, contradictions, and handoffs. |
| Trust boundary | Often optimized for convenience and broad connectivity. | Often optimized for iteration speed and autonomy. | Optimized for review, policy, redaction, and auditable side effects. |
| Failure recovery | Usually conversational retry. | Usually rerun or refine learned behavior. | Persisted run state, recovery views, deltas, and explicit continuation records. |
| Contribution focus | Connectors, assistant UX, and task surfaces. | Skill libraries, task learning, and evaluation loops. | Runtime contracts, policy gates, storage integrity, provider adapters, and operator workflows. |

Craik can borrow good user-experience patterns from adjacent shapes, but its
center of gravity stays the audit-first runtime contract.

## Where Contributors Can Help

Craik is a good fit for contributors who care about one or more of these
properties:

- agents that leave inspectable evidence for what they used and changed
- CLI and TUI workflows that make governance understandable without hiding it
- provider integrations that preserve credential and operator boundaries
- local-first persistence that can recover interrupted work
- tests that encode security, migration, release, and product behavior

Small contributions are welcome when they improve a real operator path: a more
precise error, a clearer receipt, a better migration report, a safer default, or
a test that pins an important failure mode.

## What to Avoid

Avoid changes that make side effects easier to trigger but harder to review.
Avoid hidden network calls, implicit credential fallback, broad ambient
authority, or opaque model-curated state. Those may look convenient in a demo,
but they weaken the runtime contract Craik is designed to protect.

