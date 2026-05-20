# Intent-Lock Coordination

Intent locks define the accepted task boundary for a run. Coordination
checks compare active runs and locks so one run does not silently
overlap or widen another run's authority.

## Runtime Behavior

Craik records coordination denials as receipts before side effects. A
blocked run stops with the denial reason attached to run state and the
work graph.

When a scope-change decision expands a lock, the updated lock is
persisted and the paused run is updated to reference the new lock. On
resume, Craik reloads that persisted lock before the loop evaluates
newly discovered scope.

## Operator Practice

Use scope-change decisions for work that falls outside the accepted
interpretation. Use sibling tasks for adjacent work that should not
share the same lock. Use handoffs when another agent or operator should
own the next bounded slice.
